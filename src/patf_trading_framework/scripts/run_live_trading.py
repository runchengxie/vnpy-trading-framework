# enhanced_trading_example.py
"""
Enhanced Trading System Example
Demonstrates how to use the newly added risk management, WebSocket data streaming, 
performance analysis, exception handling, and consistency validation features
"""

import os
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
import numpy as np
import yaml
from dotenv import load_dotenv
import re

# Import core modules
from patf_trading_framework.risk_manager import RiskManager
from patf_trading_framework.websocket_handler import WebSocketDataHandler, MarketDataAggregator
from patf_trading_framework.performance_analyzer import PerformanceAnalyzer, TradeRecord
from patf_trading_framework.exception_handler import ExceptionHandler, ErrorCategory, ErrorSeverity, handle_exceptions
from patf_trading_framework.consistency_validator import ConsistencyValidator
from patf_trading_framework.broker_handler import BrokerAPIHandler
from patf_trading_framework.live_trader import LiveMeanReversionStrategy, TradingState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedTradingSystem:
    """
    Enhanced Trading System
    Complete trading system integrating all newly added features
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
        
        # Initialize trading components
        self.broker_handler = None
        self.websocket_handler = None
        self.market_aggregator = None
        self.trading_strategy = None
        self.trading_state = TradingState(
            symbol=self.app_config.get('live_trading', {}).get('symbol', 'AAPL')
        )
        
        # Data storage
        self.market_data_buffer = []
        self.trade_history = []
        self.signal_history = []
        
        logger.info("Enhanced trading system initialization completed")
    
    @handle_exceptions(ErrorCategory.SYSTEM, ErrorSeverity.HIGH)
    def initialize_components(self):
        """
        Initialize all components
        """
        logger.info("Starting to initialize trading components...")
        
        try:
            # Initialize Broker API
            self.broker_handler = BrokerAPIHandler()
            
            # Initialize WebSocket data stream
            alpaca_config = self.app_config.get('alpaca', {})
            self.websocket_handler = WebSocketDataHandler(
                api_key=alpaca_config.get('api_key'),
                secret_key=alpaca_config.get('secret_key'),
                base_url=alpaca_config.get('base_url')
            )
            
            # Initialize market data aggregator (after websocket_handler)
            self.market_aggregator = MarketDataAggregator(self.websocket_handler)
            
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
            # Network reconnection logic can be added here
        
        def on_api_error(error_record):
            logger.warning(f"API error handling: {error_record.message}")
            # API retry logic can be added here
        
        def on_order_error(error_record):
            logger.error(f"Order error handling: {error_record.message}")
            # Order recovery logic can be added here
        
        self.exception_handler.register_error_callback(ErrorCategory.NETWORK, on_network_error)
        self.exception_handler.register_error_callback(ErrorCategory.API, on_api_error)
        self.exception_handler.register_error_callback(ErrorCategory.ORDER_EXECUTION, on_order_error)
    
    @handle_exceptions(ErrorCategory.DATA_QUALITY, ErrorSeverity.MEDIUM)
    def process_market_data(self, market_data: Dict):
        """
        Process market data
        """
        try:
            # Data quality check
            price = market_data.get('price', 0.0)
            volume = market_data.get('volume', 0.0)
            if not self.risk_manager.validate_market_data(price, volume):
                logger.warning("Market data quality check failed")
                return
            
            # Add to buffer
            self.market_data_buffer.append(market_data)
            
            # Maintain buffer size
            if len(self.market_data_buffer) > 1000:
                self.market_data_buffer = self.market_data_buffer[-1000:]
            
            # Generate trading signal
            signal = self.trading_strategy.generate_signal(market_data)
            
            if signal != 'hold':
                signal_record = {
                    'timestamp': datetime.now(),
                    'symbol': market_data.get('symbol'),
                    'signal': 1.0 if signal == 'buy' else -1.0 if signal == 'sell' else 0.0,
                    'price': market_data.get('price'),
                    'confidence': self.trading_strategy.get_signal_confidence()
                }
                
                self.signal_history.append(signal_record)
                
                # Risk check
                if self._risk_check(signal_record):
                    self._execute_trade(signal, market_data)
                else:
                    logger.warning(f"Risk check failed, skipping trading signal: {signal}")
            
            # Update performance analysis
            self._update_performance_metrics(market_data)
            
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.DATA_QUALITY, ErrorSeverity.MEDIUM,
                {'market_data': market_data}
            )
    
    def _risk_check(self, signal_record: Dict) -> bool:
        """
        Execute risk check
        """
        try:
            # Liquidity check
            symbol = signal_record['symbol']
            if not self.risk_manager.check_liquidity_risk(symbol, 100):
                return False
            
            # Concentration check
            current_positions = self.trading_state.get_positions()
            if not self.risk_manager.check_concentration_risk(current_positions, symbol, 100):
                return False
            
            # VaR check
            portfolio_value = self.trading_state.get_portfolio_value()
            risk_metrics = self.risk_manager.get_risk_summary(portfolio_value)
            
            max_var = self.app_config.get('live_trading', {}).get('risk_limits', {}).get('max_var', 0.05)
            if risk_metrics.get('var_95', 0) > max_var:
                logger.warning(f"VaR exceeds limit: {risk_metrics['var_95']:.4f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Risk check failed: {e}")
            return False
    
    @handle_exceptions(ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH)
    def _execute_trade(self, signal: str, market_data: Dict):
        """
        Execute trade
        """
        try:
            symbol = market_data['symbol']
            price = market_data['price']
            # Get position size from config instead of strategy
            strategy_config = self.app_config.get('strategies', {}).get('mean_reversion', {}).get('params', {})
            quantity = strategy_config.get('position_size', 100)
            
            if signal == 'buy':
                order_result = self.broker_handler.place_order(
                    symbol=symbol,
                    qty=quantity,
                    side='buy',
                    type='limit',
                    limit_price=price * 1.001  # Slightly above market price
                )
            elif signal == 'sell':
                order_result = self.broker_handler.place_order(
                    symbol=symbol,
                    qty=quantity,
                    side='sell',
                    type='limit',
                    limit_price=price * 0.999  # Slightly below market price
                )
            else:
                return
            
            if order_result and 'id' in order_result:
                # Record trade
                trade_record = TradeRecord(
                    timestamp=datetime.now(),
                    symbol=symbol,
                    side=signal,
                    quantity=quantity,
                    price=price,
                    commission=0.005 * quantity * price,  # Assume 0.5% commission
                    order_id=order_result['id']
                )
                
                self.performance_analyzer.add_trade(trade_record)
                self.trade_history.append(trade_record)
                
                # Update trading state
                self.trading_state.update_position(symbol, quantity if signal == 'buy' else -quantity)
                
                logger.info(f"Trade executed successfully: {signal} {quantity} {symbol} @ {price}")
            else:
                logger.error(f"Trade execution failed: {order_result}")
                
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH,
                {'signal': signal, 'market_data': market_data}
            )
    
    def _update_performance_metrics(self, market_data: Dict):
        """
        Update performance metrics
        """
        try:
            # Update portfolio value
            current_positions = self.trading_state.get_positions()
            market_prices = {market_data['symbol']: market_data['price']}
            
            self.performance_analyzer.update_portfolio_value(
                datetime.now(), market_prices
            )
            
        except Exception as e:
            logger.warning(f"Performance metrics update failed: {e}")
    
    async def start_live_trading(self):
        """
        Start live trading
        """
        logger.info("Starting live trading system...")
        
        try:
            # Initialize components
            self.initialize_components()
            
            # Subscribe to market data
            symbols = [self.app_config.get('live_trading', {}).get('symbol', 'AAPL')]
            
            # Start WebSocket data stream
            await self.websocket_handler.start_data_stream(
                symbols=symbols,
                data_callback=self.process_market_data
            )
            
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.SYSTEM, ErrorSeverity.CRITICAL
            )
            raise
    
    def run_consistency_validation(self, backtest_data: Dict) -> Dict:
        """
        Run consistency validation
        """
        logger.info("Starting consistency validation...")
        
        # Prepare live data
        live_data = {
            'signals': self.signal_history,
            'trades': [{
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'side': trade.side,
                'quantity': trade.quantity,
                'price': trade.price
            } for trade in self.trade_history],
            'performance': self.performance_analyzer.calculate_risk_metrics()
        }
        
        # Execute validation
        validation_results = self.consistency_validator.validate_consistency(
            backtest_data, live_data
        )
        
        # Generate report
        validation_report = self.consistency_validator.generate_validation_report(
            validation_results
        )
        
        logger.info(f"Consistency validation completed, overall status: {validation_report['overall_status']}")
        return validation_report
    
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
                    'data_buffer_size': len(self.market_data_buffer)
                }
            }
            
            logger.info("Comprehensive report generation completed")
            return comprehensive_report
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {'error': str(e)}
    
    def stop_trading(self):
        """
        Stop trading
        """
        logger.info("Stopping trading system...")
        
        try:
            # Stop WebSocket connection
            if self.websocket_handler:
                asyncio.create_task(self.websocket_handler.disconnect())
            
            # Close all positions (optional)
            current_positions = self.trading_state.get_positions()
            for symbol, quantity in current_positions.items():
                if quantity != 0:
                    logger.info(f"Closing position: {symbol} {quantity}")
                    # Position closing logic can be added here
            
            # Generate final report
            final_report = self.generate_comprehensive_report()
            
            # Export reports
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Create output directories
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            charts_dir = os.path.join(output_dir, 'charts')
            logs_dir = os.path.join(output_dir, 'logs')
            os.makedirs(charts_dir, exist_ok=True)
            os.makedirs(logs_dir, exist_ok=True)
            
            self.performance_analyzer.plot_performance_charts(
                os.path.join(charts_dir, f'performance_chart_{timestamp}.png')
            )
            
            self.exception_handler.export_error_log(
                os.path.join(logs_dir, f'error_log_{timestamp}.json')
            )
            
            logger.info("Trading system stopped")
            return final_report
            
        except Exception as e:
            logger.error(f"Error occurred while stopping trading system: {e}")

def load_app_config(config_path='config.yml'):
    """
    Load application configuration from YAML file with environment variable substitution.
    It assumes the config file is in the current working directory.
    """
    # Load environment variables from .env file, which should also be in the CWD
    load_dotenv()
    
    # The config file path is now relative to the Current Working Directory,
    # not the script's location. This is more robust for installed packages.
    config_file_path = config_path  # Directly use the provided path
    
    try:
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config_content = file.read()
        
        # Substitute environment variables
        def replace_env_vars(match):
            env_var = match.group(1)
            return os.getenv(env_var, match.group(0))  # Return original if env var not found
        
        config_content = re.sub(r'\$\{([^}]+)\}', replace_env_vars, config_content)
        
        # Parse YAML
        config = yaml.safe_load(config_content)
        
        logger.info(f"Configuration loaded successfully from '{config_file_path}' (relative to CWD).")
        return config
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {os.path.abspath(config_file_path)}")
        logger.error("Please ensure you are running this command from the project's root directory.")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration in '{config_file_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading configuration from '{config_file_path}': {e}")
        raise

# Example usage
async def async_main():
    """
    Asynchronous main function example
    """
    # Load configuration from config.yml
    app_config = load_app_config()
    
    # Create trading system
    trading_system = EnhancedTradingSystem(app_config)
    
    try:
        # Initialize components before any trading operations
        trading_system.initialize_components()
        
        # Start live trading (this is just an example, real API keys need to be configured for actual use)
        # await trading_system.start_live_trading()
        
        # Simulate running for a period of time
        logger.info("Simulated trading running...")
        
        # Get symbol from config
        symbol = app_config.get('live_trading', {}).get('symbol', 'AAPL')
        
        # Simulate some market data
        for i in range(10):
            market_data = {
                'symbol': symbol,
                'price': 150.0 + np.random.normal(0, 1),
                'volume': 1000000,
                'timestamp': datetime.now()
            }
            
            trading_system.process_market_data(market_data)
            await asyncio.sleep(0.1)  # Use async sleep instead of time.sleep
        
        # Generate report
        report = trading_system.generate_comprehensive_report()
        logger.info(f"Trading report: {report}")
        
        # Stop trading
        final_report = trading_system.stop_trading()
        
    except Exception as e:
        logger.error(f"Trading system runtime error: {e}")
        trading_system.stop_trading()

def main():
    """
    Synchronous entry point for setuptools/pip
    """
    try:
        # Run asynchronous main function
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Program exited via keyboard interrupt.")

if __name__ == "__main__":
    # When running this script directly, call the synchronous main function
    main()