#!/usr/bin/env python3
"""
Refactored Live Trading System
Follows the correct live trading pattern using only BrokerAPIHandler for all interactions.
Eliminates redundant WebSocket connections and implements proper asyncio.Queue pattern.
"""

import os
import logging
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List
import yaml
from dotenv import load_dotenv
import re
import signal

# Import core modules
from patf_trading_framework.risk_manager import RiskManager
from patf_trading_framework.performance_analyzer import PerformanceAnalyzer, TradeRecord
from patf_trading_framework.exception_handler import ExceptionHandler, ErrorCategory, ErrorSeverity, handle_exceptions
from patf_trading_framework.consistency_validator import ConsistencyValidator
from patf_trading_framework.broker_handler import BrokerAPIHandler
from patf_trading_framework.live_trader import LiveMeanReversionStrategy, TradingState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class EnhancedTradingSystem:
    """
    Enhanced Trading System - Refactored
    Uses only BrokerAPIHandler for all interactions, following the correct live trading pattern.
    """
    
    def __init__(self, app_config: Dict):
        self.app_config = app_config
        
        # Get initial capital from config
        initial_capital = self.app_config.get('live_trading', {}).get('initial_capital', 100000)
        
        # Initialize core components
        self.risk_manager = RiskManager(
            var_window=self.app_config.get('live_trading', {}).get('risk_limits', {}).get('var_window', 252),
            var_confidence=self.app_config.get('live_trading', {}).get('risk_limits', {}).get('var_confidence', 0.95)
        )
        
        self.performance_analyzer = PerformanceAnalyzer(
            initial_capital=initial_capital
        )
        
        self.exception_handler = ExceptionHandler()
        self.consistency_validator = ConsistencyValidator()
        
        # Initialize trading components - ONLY broker_handler, no redundant WebSocket
        self.broker_handler = None
        self.trading_strategy = None
        self.trading_state = TradingState(
            symbol=self.app_config.get('live_trading', {}).get('symbol', 'AAPL')
        )
        
        # Data storage
        self.trade_history = []
        self.signal_history = []
        
        # Asyncio queue for data processing
        self.data_queue = None
        
        logger.info("Enhanced trading system initialization completed")
    
    @handle_exceptions(ErrorCategory.SYSTEM, ErrorSeverity.HIGH)
    def initialize_components(self):
        """
        Initialize all components - using ONLY broker_handler
        """
        logger.info("Starting to initialize trading components...")
        
        try:
            # Initialize ONLY Broker API - no redundant WebSocket handler
            self.broker_handler = BrokerAPIHandler()
            
            # Initialize trading strategy with correct parameter mapping
            strategy_config = self.app_config.get('strategies', {}).get('mean_reversion', {}).get('params', {})
            live_trading_config = self.app_config.get('live_trading', {})
            
            self.trading_strategy = LiveMeanReversionStrategy(
                symbol=live_trading_config.get('symbol', 'AAPL'),
                zscore_period=strategy_config.get('zscore_period', 20),
                zscore_upper=strategy_config.get('zscore_upper', 2.0),
                zscore_lower=strategy_config.get('zscore_lower', -2.0),
                exit_threshold=strategy_config.get('exit_threshold', 0.0)
            )
            
            # Initialize asyncio queue
            self.data_queue = asyncio.Queue()
            
            # Register exception handling callbacks
            self._register_error_callbacks()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Component initialization failed: {e}")
            raise
    
    def _register_error_callbacks(self):
        """
        Register error handling callbacks
        """
        def on_network_error(error_record):
            logger.warning(f"Network error handling: {error_record.message}")
        
        def on_api_error(error_record):
            logger.warning(f"API error handling: {error_record.message}")
        
        def on_order_error(error_record):
            logger.error(f"Order error handling: {error_record.message}")
        
        self.exception_handler.register_error_callback(ErrorCategory.NETWORK, on_network_error)
        self.exception_handler.register_error_callback(ErrorCategory.API, on_api_error)
        self.exception_handler.register_error_callback(ErrorCategory.ORDER_EXECUTION, on_order_error)
    
    async def handle_trade_update(self, update_data):
        """
        Handle trade updates from broker stream
        """
        event = getattr(update_data, 'event', None)
        logger.info(f"Update Received: Event='{event}', Data={update_data}")
        
        if hasattr(update_data, 'order') and isinstance(update_data.order, dict):
            order_info = update_data.order
            order_id = order_info.get('id')
            order_status = order_info.get('status')
            client_order_id = order_info.get('client_order_id')
            
            logger.info(f"Order Update Details: OrderID={order_id}, Status={order_status}, ClientOrderID={client_order_id}")
            
            if self.trading_state.active_order_id and client_order_id == self.trading_state.active_order_id:
                if order_status == 'filled':
                    filled_qty = float(order_info.get('filled_qty', 0))
                    side = order_info.get('side')
                    actual_qty_change = filled_qty if side == 'buy' else -filled_qty
                    
                    new_position = self.trading_state.current_position_qty + actual_qty_change
                    self.trading_state.update_position(new_position)
                    self.trading_state.set_active_order(None)
                    logger.info(f"Order {order_id} filled. Position changed by {actual_qty_change}. New position: {self.trading_state.current_position_qty}")
                
                elif order_status in ['canceled', 'expired', 'rejected', 'done_for_day']:
                    logger.warning(f"Order {order_id} ({client_order_id}) reached final non-filled state: {order_status}. Clearing active order.")
                    self.trading_state.set_active_order(None)
            
            await self.data_queue.put({'type': 'order_update', 'data': order_info})
        
        elif event == 'account_update' and hasattr(update_data, 'cash') and hasattr(update_data, 'portfolio_value'):
            logger.info(f"Account Update Received: Cash={update_data.cash}, PortfolioValue={update_data.portfolio_value}")
            self.trading_state.update_cash_and_value(float(update_data.cash), float(update_data.portfolio_value))
            await self.data_queue.put({'type': 'account_update', 'cash': update_data.cash, 'portfolio_value': update_data.portfolio_value})
    
    async def handle_trade(self, trade_data):
        """
        Handle trade data from broker stream
        """
        logger.debug(f"Trade Received: {trade_data.symbol} Price={trade_data.price} Qty={trade_data.size}")
        if trade_data.symbol == self.trading_state.symbol:
            self.trading_state.update_last_price(trade_data.price, 'trade')
            await self.data_queue.put({
                'type': 'trade', 
                'symbol': trade_data.symbol, 
                'price': trade_data.price, 
                'size': trade_data.size, 
                'timestamp': trade_data.timestamp
            })
    
    async def handle_bar(self, bar_data):
        """
        Handle bar data from broker stream
        """
        logger.debug(f"Bar Received: {bar_data.symbol} O={bar_data.open} H={bar_data.high} L={bar_data.low} C={bar_data.close} V={bar_data.volume}")
        if bar_data.symbol == self.trading_state.symbol:
            self.trading_state.update_last_price(bar_data.close, 'bar')
            await self.data_queue.put({
                'type': 'bar', 
                'symbol': bar_data.symbol, 
                'open': bar_data.open, 
                'high': bar_data.high, 
                'low': bar_data.low, 
                'close': bar_data.close, 
                'volume': bar_data.volume, 
                'timestamp': bar_data.timestamp
            })
    
    def _risk_check(self, signal_record: Dict) -> bool:
        """
        Execute risk check
        """
        try:
            symbol = signal_record['symbol']
            price = signal_record.get('price', 0)
            
            if price <= 0:
                logger.warning(f"Invalid price for {symbol}: {price}")
                return False
            
            # Simplified concentration check
            current_positions = self.trading_state.get_positions()
            total_position_value = sum(abs(qty) * price for qty in current_positions.values())
            portfolio_value = self.trading_state.get_portfolio_value()
            
            if portfolio_value > 0:
                concentration = total_position_value / portfolio_value
                max_concentration = self.app_config.get('live_trading', {}).get('risk_limits', {}).get('max_concentration', 0.8)
                if concentration > max_concentration:
                    logger.warning(f"Concentration risk too high: {concentration:.2%}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Risk check failed: {e}")
            return True
    
    @handle_exceptions(ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH)
    def _execute_trade(self, signal: str, current_price: float):
        """
        Execute trade using broker_handler
        """
        try:
            symbol = self.trading_state.symbol
            strategy_config = self.app_config.get('strategies', {}).get('mean_reversion', {}).get('params', {})
            quantity = strategy_config.get('position_size', 10)
            
            if signal == 'BUY':
                side = 'buy'
                target_qty = quantity
            elif signal == 'SELL':
                side = 'sell'
                target_qty = -quantity
            elif signal == 'CLOSE':
                target_qty = 0
                current_qty = self.trading_state.current_position_qty
                if current_qty > 0:
                    side = 'sell'
                    quantity = abs(current_qty)
                elif current_qty < 0:
                    side = 'buy'
                    quantity = abs(current_qty)
                else:
                    return  # No position to close
            else:
                return
            
            qty_to_trade = target_qty - self.trading_state.current_position_qty
            
            if abs(qty_to_trade) > 0.01:
                side = 'buy' if qty_to_trade > 0 else 'sell'
                order_qty = abs(qty_to_trade)
                client_order_id = f"live_{uuid.uuid4()}"
                
                logger.info(f"Signal requires action: Target={target_qty}, Current={self.trading_state.current_position_qty}. Attempting to {side} {order_qty} {symbol}")
                
                order_result = self.broker_handler.place_order(
                    symbol=symbol,
                    qty=order_qty,
                    side=side,
                    order_type='market',
                    time_in_force='day',
                    client_order_id=client_order_id
                )
                
                if order_result and hasattr(order_result, 'id') and order_result.id:
                    logger.info(f"Market order placed. ClientOrderID: {client_order_id}, API OrderID: {order_result.id}, Status: {order_result.status}")
                    self.trading_state.set_active_order(client_order_id)
                    
                    # Record trade for performance analysis
                    trade_record = TradeRecord(
                        timestamp=datetime.now(),
                        symbol=symbol,
                        side=side,
                        quantity=order_qty,
                        price=current_price,
                        commission=0.005 * order_qty * current_price,
                        order_id=order_result.id
                    )
                    
                    self.performance_analyzer.add_trade(trade_record)
                    self.trade_history.append(trade_record)
                    
                    if order_result.status in ['rejected', 'canceled', 'expired']:
                        logger.warning(f"Order {order_result.id} was {order_result.status} immediately. Clearing active order flag.")
                        self.trading_state.set_active_order(None)
                else:
                    logger.error(f"Failed to place {side} order for {order_qty} {symbol}. Order object: {order_result}")
                
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH,
                {'signal': signal, 'current_price': current_price}
            )
    
    async def start_live_trading(self):
        """
        Start live trading using the correct pattern from live_trader.py
        """
        logger.info("Starting live trading system...")
        
        try:
            # Initialize components
            self.initialize_components()
            
            # Get initial account and position state
            logger.info("Fetching initial account and position state...")
            try:
                account_info = self.broker_handler.get_account_info()
                if account_info:
                    self.trading_state.update_cash_and_value(float(account_info.cash), float(account_info.portfolio_value))
                else:
                    logger.warning("Could not fetch initial account info.")
                
                position_info = self.broker_handler.get_position(self.trading_state.symbol)
                if position_info:
                    self.trading_state.update_position(float(position_info.qty))
                else:
                    logger.info(f"No initial position found for {self.trading_state.symbol}.")
                    self.trading_state.update_position(0.0)
            
            except Exception as e:
                logger.error(f"Error fetching initial state: {e}", exc_info=True)
            
            logger.info(f"Initial State: Position={self.trading_state.current_position_qty}, Cash={self.trading_state.last_known_cash}")
            
            # Set up stream with multiple callbacks using ONLY broker_handler
            logger.info("Setting up data stream...")
            stream_setup_success = await self.broker_handler.setup_stream(
                symbols=[self.trading_state.symbol],
                trade_handler_cb=self.handle_trade,
                bar_handler_cb=self.handle_bar,
                order_update_handler_cb=self.handle_trade_update,
                subscribe_trades=True,
                subscribe_bars=True,
                subscribe_updates=True
            )
            
            if not stream_setup_success:
                logger.error("Failed to set up data stream. Exiting.")
                return
            
            logger.info("Starting data stream task...")
            stream_task = asyncio.create_task(self.broker_handler.start_streaming())
            
            # Main trading loop
            logger.info("Starting main trading loop...")
            ACCOUNT_REFRESH_INTERVAL = 300
            last_account_refresh_time = asyncio.get_event_loop().time()
            
            try:
                while True:
                    try:
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_account_refresh_time >= ACCOUNT_REFRESH_INTERVAL:
                            logger.info("Performing periodic account and position refresh...")
                            try:
                                refreshed_account_info = self.broker_handler.get_account_info()
                                if refreshed_account_info:
                                    if self.trading_state.last_known_cash is not None and abs(float(refreshed_account_info.cash) - self.trading_state.last_known_cash) > 0.01:
                                        logger.warning(f"Cash mismatch: Stream state {self.trading_state.last_known_cash}, API state {refreshed_account_info.cash}")
                                    self.trading_state.update_cash_and_value(float(refreshed_account_info.cash), float(refreshed_account_info.portfolio_value))
                                
                                refreshed_position_info = self.broker_handler.get_position(self.trading_state.symbol)
                                refreshed_qty = 0.0
                                if refreshed_position_info:
                                    refreshed_qty = float(refreshed_position_info.qty)
                                
                                if abs(refreshed_qty - self.trading_state.current_position_qty) > 0.01:
                                    logger.warning(f"Position mismatch for {self.trading_state.symbol}: Stream state {self.trading_state.current_position_qty}, API state {refreshed_qty}. Syncing with API state.")
                                
                                last_account_refresh_time = current_time
                            except Exception as refresh_err:
                                logger.error(f"Error during periodic account/position refresh: {refresh_err}", exc_info=True)
                        
                        # Process from the queue
                        queued_item = await asyncio.wait_for(self.data_queue.get(), timeout=1.0)
                        data_type = queued_item.get('type')
                        logger.debug(f"Processing item from queue: Type={data_type}, Item={queued_item}")
                        
                        signal = None
                        if data_type in ['trade', 'bar']:
                            current_price = self.trading_state.last_trade_price
                            if not current_price and data_type == 'bar':
                                current_price = self.trading_state.last_bar_close
                            
                            if current_price:
                                signal = self.trading_strategy.get_signal(current_price, self.trading_state.current_position_qty)
                                logger.info(f"Strategy generated signal: {signal} based on price {current_price:.2f} and position {self.trading_state.current_position_qty}")
                                
                                # Record signal
                                if signal != 'HOLD':
                                    signal_record = {
                                        'timestamp': datetime.now(),
                                        'symbol': self.trading_state.symbol,
                                        'signal': 1.0 if signal == 'BUY' else -1.0 if signal == 'SELL' else 0.0,
                                        'price': current_price,
                                        'confidence': self.trading_strategy.get_signal_confidence()
                                    }
                                    self.signal_history.append(signal_record)
                            else:
                                logger.warning("No current price available (trade or bar) to generate signal.")
                        
                        # Execute trades if signal generated and no active order
                        if signal is not None and self.trading_state.active_order_id is None:
                            logger.info(f"Received signal: {signal} for {self.trading_state.symbol}")
                            
                            # Risk check
                            if signal != 'HOLD':
                                signal_record = {
                                    'symbol': self.trading_state.symbol,
                                    'price': current_price
                                }
                                
                                if self._risk_check(signal_record):
                                    self._execute_trade(signal, current_price)
                                else:
                                    logger.warning(f"Risk check failed, skipping trading signal: {signal}")
                        
                        elif signal is not None and self.trading_state.active_order_id is not None:
                            logger.info(f"Holding off on new signal {signal}, active order exists: {self.trading_state.active_order_id}")
                        
                        self.data_queue.task_done()
                    
                    except asyncio.TimeoutError:
                        logger.debug("No data received from queue in the last 1 second. Continuing...")
                        continue
                    except Exception as loop_error:
                        logger.error(f"Error in main trading loop: {loop_error}", exc_info=True)
                        await asyncio.sleep(5)
            
            except asyncio.CancelledError:
                logger.info("Main loop cancelled.")
            finally:
                logger.info("Shutting down trader...")
                if 'stream_task' in locals() and not stream_task.done():
                    logger.info("Cancelling stream task...")
                    stream_task.cancel()
                    try:
                        await stream_task
                    except asyncio.CancelledError:
                        logger.info("Stream task successfully cancelled.")
                
                if self.broker_handler and self.broker_handler.stream:
                    logger.info("Stopping stream connection...")
                    await self.broker_handler.stop_streaming()
                
                logger.info("Live Trader shut down.")
        
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.SYSTEM, ErrorSeverity.CRITICAL
            )
            raise
    
    def generate_comprehensive_report(self) -> Dict:
        """
        Generate comprehensive report
        """
        logger.info("Generating comprehensive trading report...")
        
        try:
            # Performance report
            performance_report = self.performance_analyzer.generate_performance_report()
            
            # Risk report
            portfolio_value = self.trading_state.get_portfolio_value()
            current_positions = self.trading_state.get_positions()
            risk_metrics = self.risk_manager.get_risk_summary(portfolio_value)
            
            # Exception statistics
            error_statistics = self.exception_handler.get_error_statistics()
            
            # Trading statistics
            trading_stats = {
                'total_trades': len(self.trade_history),
                'total_signals': len(self.signal_history),
                'signal_to_trade_ratio': len(self.trade_history) / len(self.signal_history) if self.signal_history else 0,
                'current_positions': current_positions,
                'portfolio_value': self.trading_state.get_portfolio_value()
            }
            
            comprehensive_report = {
                'timestamp': datetime.now(),
                'performance_analysis': performance_report,
                'risk_analysis': risk_metrics,
                'trading_statistics': trading_stats,
                'error_statistics': error_statistics,
                'system_status': {
                    'emergency_stop': self.exception_handler.emergency_stop_triggered,
                    'active_positions': len(current_positions),
                    'active_order': self.trading_state.active_order_id
                }
            }
            
            logger.info("Comprehensive report generation completed")
            return comprehensive_report
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {'error': str(e)}
    
    async def stop_trading(self):
        """
        Stop trading
        """
        logger.info("Stopping trading system...")
        
        try:
            # Stop broker stream
            if self.broker_handler:
                await self.broker_handler.stop_streaming()
            
            # Generate final report
            final_report = self.generate_comprehensive_report()
            
            # Export reports
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            paths_config = self.app_config.get('paths', {})
            charts_dir = paths_config.get('chart_dir', 'output/charts')
            logs_dir = paths_config.get('log_dir', 'output/logs')
            
            os.makedirs(charts_dir, exist_ok=True)
            os.makedirs(logs_dir, exist_ok=True)
            
            self.performance_analyzer.plot_performance_charts(
                os.path.join(charts_dir, f'live_trading_performance_{timestamp}.png')
            )
            
            self.exception_handler.export_error_log(
                os.path.join(logs_dir, f'live_trading_errors_{timestamp}.json')
            )
            
            logger.info("Trading system stopped successfully")
            return final_report
            
        except Exception as e:
            logger.error(f"Error occurred while stopping trading system: {e}")
            return {'error': str(e)}

def load_app_config(config_path='config.yml'):
    """
    Load application configuration from YAML file with environment variable substitution.
    """
    load_dotenv()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config_content = file.read()
        
        # Substitute environment variables
        def replace_env_vars(match):
            env_var = match.group(1)
            return os.getenv(env_var, match.group(0))
        
        config_content = re.sub(r'\$\{([^}]+)\}', replace_env_vars, config_content)
        
        # Parse YAML
        config = yaml.safe_load(config_content)
        
        logger.info(f"Configuration loaded successfully from '{config_path}'.")
        return config
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {os.path.abspath(config_path)}")
        logger.error("Please ensure you are running this command from the project's root directory.")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration in '{config_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading configuration from '{config_path}': {e}")
        raise

async def shutdown(sig, loop):
    """Handle shutdown signals"""
    signal_name = sig
    if isinstance(sig, int):
        try:
            signal_name = signal.Signals(sig).name
        except ValueError:
            signal_name = f"Signal {sig}"
    elif hasattr(sig, 'name'):
        signal_name = sig.name
    
    logger.info(f"Received exit signal {signal_name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks...")
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All outstanding tasks have been processed.")
    else:
        logger.info("No other outstanding tasks to cancel.")

async def main():
    """
    Main asynchronous function for live trading
    """
    # Load configuration
    app_config = load_app_config()
    
    # Create trading system
    trading_system = EnhancedTradingSystem(app_config)
    
    try:
        # Start live trading
        await trading_system.start_live_trading()
        
    except Exception as e:
        logger.error(f"Trading system runtime error: {e}")
        await trading_system.stop_trading()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    
    try:
        for sig_val in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig_val, lambda s=sig_val: asyncio.create_task(shutdown(s, loop)))
    except NotImplementedError:
        logger.info("loop.add_signal_handler not implemented, falling back to signal.signal (Windows).")
        signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown(s, loop)))
        signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(shutdown(s, loop)))
    
    try:
        loop.run_until_complete(main())
    except asyncio.CancelledError:
        logger.info("Main task was cancelled.")
    finally:
        logger.info("Cleaning up event loop resources...")
        pending = asyncio.all_tasks(loop=loop)
        if pending:
            logger.info(f"Waiting for {len(pending)} pending tasks to complete before closing loop...")
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        
        logger.info("Event loop closed.")
        loop.close()