import asyncio
import logging
import os
import signal
from dotenv import load_dotenv
import uuid # For generating unique client order IDs
import collections # For deque
import numpy as np # For mean/std calculations

# Import necessary components from your existing modules
from broker_handler import BrokerAPIHandler

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)


# --- Live Strategy Definition ---
class LiveMeanReversionStrategy:
    def __init__(self, symbol: str, zscore_period: int, zscore_upper: float, zscore_lower: float, exit_threshold: float, **kwargs):
        self.symbol = symbol
        self.zscore_period = zscore_period
        self.zscore_upper = zscore_upper
        self.zscore_lower = zscore_lower
        self.exit_threshold = exit_threshold
        self.prices = collections.deque(maxlen=self.zscore_period)
        self.current_zscore = None
        logger.info(
            f"LiveMeanReversionStrategy for {self.symbol} initialized with: "
            f"Period={self.zscore_period}, UpperZ={self.zscore_upper}, "
            f"LowerZ={self.zscore_lower}, ExitThresholdZ={self.exit_threshold}"
        )

    def _calculate_zscore(self):
        if len(self.prices) < self.zscore_period:
            self.current_zscore = None
            logger.debug(f"Not enough data for Z-score calculation for {self.symbol}. Have {len(self.prices)}, need {self.zscore_period}")
            return False

        prices_arr = np.array(self.prices)
        sma = np.mean(prices_arr)
        stdev = np.std(prices_arr)

        if stdev < 1e-6:
            self.current_zscore = None
            logger.warning(f"Standard deviation for {self.symbol} is too small ({stdev:.4f}) to calculate Z-score reliably.")
            return False

        current_price = self.prices[-1]
        self.current_zscore = (current_price - sma) / stdev
        logger.debug(f"Calculated Z-score for {self.symbol}: {self.current_zscore:.2f} (Price={current_price:.2f}, SMA={sma:.2f}, StdDev={stdev:.2f})")
        return True

    def get_signal(self, current_price: float, current_position_qty: float):
        self.prices.append(current_price)

        if not self._calculate_zscore() or self.current_zscore is None:
            return "HOLD"

        z = self.current_zscore
        signal = "HOLD"

        if current_position_qty > 0.01:
            if z >= self.exit_threshold:
                logger.info(f"Signal: CLOSE LONG for {self.symbol} (Z-score {z:.2f} >= Exit {self.exit_threshold}, Position: {current_position_qty})")
                signal = "CLOSE"
        elif current_position_qty < -0.01:
            if z <= self.exit_threshold:
                logger.info(f"Signal: CLOSE SHORT for {self.symbol} (Z-score {z:.2f} <= Exit {self.exit_threshold}, Position: {current_position_qty})")
                signal = "CLOSE"

        if signal == "HOLD" and abs(current_position_qty) < 0.01:
            if z < self.zscore_lower:
                logger.info(f"Signal: BUY for {self.symbol} (Z-score {z:.2f} < Lower {self.zscore_lower})")
                signal = "BUY"
            elif z > self.zscore_upper:
                logger.info(f"Signal: SELL for {self.symbol} (Z-score {z:.2f} > Upper {self.zscore_upper})")
                signal = "SELL"
        
        if signal == "HOLD":
            logger.debug(f"Signal: HOLD for {self.symbol} (Z-score {z:.2f}, Position: {current_position_qty})")

        return signal


# --- Phase 1: Basic State Management ---
class TradingState:
    """Manages the real-time state of the trading bot."""
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.current_position_qty: float = 0.0
        self.active_order_id: str | None = None
        self.target_position_qty: float = 0.0
        self.last_known_cash: float | None = None
        self.last_known_portfolio_value: float | None = None
        self.last_trade_price: float | None = None
        self.last_bar_close: float | None = None

    def update_position(self, new_qty: float):
        logger.info(f"Updating position for {self.symbol} from {self.current_position_qty} to {new_qty}")
        self.current_position_qty = new_qty

    def update_cash_and_value(self, cash: float, value: float):
        self.last_known_cash = cash
        self.last_known_portfolio_value = value
        logger.debug(f"Updated account state: Cash={cash}, PortfolioValue={value}")

    def set_active_order(self, order_id: str | None):
        logger.info(f"Setting active order ID to: {order_id}")
        self.active_order_id = order_id

    def update_last_price(self, price: float, source: str):
        if source == 'trade':
            self.last_trade_price = price
        elif source == 'bar':
            self.last_bar_close = price
        logger.debug(f"Updated last price ({source}) for {self.symbol} to {price}")


# --- Phase 1: Core Async Loop ---
async def main():
    """Main asynchronous function to run the live trading bot."""
    load_dotenv()
    logger.info("Starting Live Trader...")

    symbol_to_trade = 'SPY'
    ACCOUNT_REFRESH_INTERVAL = 300
    strategy_params = {
        'zscore_period': 20, 'zscore_upper': 2.0, 'zscore_lower': -2.0,
        'exit_threshold': 0.0, 'use_filtered_price': False
    }

    try:
        broker = BrokerAPIHandler()
        logger.info("BrokerAPIHandler initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize BrokerAPIHandler: {e}", exc_info=True)
        return

    state = TradingState(symbol=symbol_to_trade)

    strategy = LiveMeanReversionStrategy(
        symbol=symbol_to_trade,
        zscore_period=strategy_params['zscore_period'],
        zscore_upper=strategy_params['zscore_upper'],
        zscore_lower=strategy_params['zscore_lower'],
        exit_threshold=strategy_params['exit_threshold']
    )
    logger.info("LiveMeanReversionStrategy initialized.")

    data_queue = asyncio.Queue()

    logger.info("Fetching initial account and position state...")
    try:
        account_info = broker.get_account_info()
        if account_info:
            state.update_cash_and_value(float(account_info.cash), float(account_info.portfolio_value))
        else:
            logger.warning("Could not fetch initial account info.")

        position_info = broker.get_position(state.symbol)
        if position_info:
            state.update_position(float(position_info.qty))
        else:
            logger.info(f"No initial position found for {state.symbol}.")
            state.update_position(0.0)

    except Exception as e:
        logger.error(f"Error fetching initial state: {e}", exc_info=True)

    logger.info(f"Initial State: Position={state.current_position_qty}, Cash={state.last_known_cash}")

    async def handle_trade_update(update_data):
        # This function now handles both order updates and account updates from the trade_updates stream
        event = getattr(update_data, 'event', None)
        logger.info(f"Update Received: Event='{event}', Data={update_data}")

        if hasattr(update_data, 'order') and isinstance(update_data.order, dict):
            # This is an OrderUpdate
            order_info = update_data.order
            order_id = order_info.get('id')
            order_status = order_info.get('status')
            client_order_id = order_info.get('client_order_id')

            logger.info(f"Order Update Details: OrderID={order_id}, Status={order_status}, ClientOrderID={client_order_id}")

            if state.active_order_id and client_order_id == state.active_order_id:
                if order_status == 'filled':
                    filled_qty = float(order_info.get('filled_qty', 0))
                    side = order_info.get('side')
                    actual_qty_change = filled_qty if side == 'buy' else -filled_qty
                    
                    new_position = state.current_position_qty + actual_qty_change
                    state.update_position(new_position)
                    state.set_active_order(None)
                    logger.info(f"Order {order_id} filled. Position changed by {actual_qty_change}. New position: {state.current_position_qty}")

                elif order_status == 'partially_filled':
                    filled_qty = float(order_info.get('filled_qty', 0))
                    logger.info(f"Order {order_id} partially filled. Filled Qty: {filled_qty}. Active order {state.active_order_id} remains.")

                elif order_status in ['canceled', 'expired', 'rejected', 'done_for_day']:
                    logger.warning(f"Order {order_id} ({client_order_id}) reached final non-filled state: {order_status}. Clearing active order.")
                    state.set_active_order(None)
            
            await data_queue.put({'type': 'order_update', 'data': order_info})

        elif event == 'account_update' and hasattr(update_data, 'cash') and hasattr(update_data, 'portfolio_value'):
            # This is an AccountUpdate
            logger.info(f"Account Update Received: Cash={update_data.cash}, PortfolioValue={update_data.portfolio_value}")
            state.update_cash_and_value(float(update_data.cash), float(update_data.portfolio_value))
            await data_queue.put({'type': 'account_update', 'cash': update_data.cash, 'portfolio_value': update_data.portfolio_value})
        
        elif event in ['new', 'canceled', 'expired', 'done_for_day', 'replaced', 'pending_new', 'pending_cancel', 'pending_replace', 'calculated', 'suspended', 'stopped', 'rejected']:
            if hasattr(update_data, 'order') and isinstance(update_data.order, dict):
                order_info = update_data.order
                logger.info(f"Order lifecycle event: {event}, Order: {order_info.get('id')}, Status: {order_info.get('status')}")
                if state.active_order_id and order_info.get('client_order_id') == state.active_order_id and event in ['canceled', 'expired', 'rejected']:
                     logger.warning(f"Active order {state.active_order_id} is now {event}. Clearing active order.")
                     state.set_active_order(None)
                await data_queue.put({'type': 'order_update', 'data': order_info})
            else:
                logger.warning(f"Received order lifecycle event '{event}' without full order details in expected format: {update_data}")

        else:
            logger.warning(f"Received unhandled event type '{event}' or unexpected data structure in trade_updates stream: {update_data}")

    async def handle_trade(trade_data):
        logger.debug(f"Trade Received: {trade_data.symbol} Price={trade_data.price} Qty={trade_data.size}")
        if trade_data.symbol == state.symbol:
            state.update_last_price(trade_data.price, 'trade')
            await data_queue.put({'type': 'trade', 'symbol': trade_data.symbol, 'price': trade_data.price, 'size': trade_data.size, 'timestamp': trade_data.timestamp})

    async def handle_bar(bar_data):
        logger.debug(f"Bar Received: {bar_data.symbol} O={bar_data.open} H={bar_data.high} L={bar_data.low} C={bar_data.close} V={bar_data.volume}")
        if bar_data.symbol == state.symbol:
            state.update_last_price(bar_data.close, 'bar')
            await data_queue.put({'type': 'bar', 'symbol': bar_data.symbol, 'open': bar_data.open, 'high': bar_data.high, 'low': bar_data.low, 'close': bar_data.close, 'volume': bar_data.volume, 'timestamp': bar_data.timestamp})

    logger.info("Setting up data stream...")
    stream_setup_success = await broker.setup_stream(
        symbols=[state.symbol],
        trade_handler_cb=handle_trade,
        bar_handler_cb=handle_bar,
        order_update_handler_cb=handle_trade_update, # This now handles both order and account updates
        subscribe_trades=True,
        subscribe_bars=True, # Changed from False to True
        subscribe_updates=True # This subscribes to the trade_updates stream for order and account events
    )

    if not stream_setup_success:
        logger.error("Failed to set up data stream. Exiting.")
        return

    logger.info("Starting data stream task...")
    stream_task = asyncio.create_task(broker.start_streaming())

    logger.info("Starting main trading loop...")
    last_account_refresh_time = asyncio.get_event_loop().time()
    try:
        while True:
            try:
                current_time = asyncio.get_event_loop().time()
                if current_time - last_account_refresh_time >= ACCOUNT_REFRESH_INTERVAL:
                    logger.info("Performing periodic account and position refresh...")
                    try:
                        refreshed_account_info = broker.get_account_info()
                        if refreshed_account_info:
                            if state.last_known_cash is not None and abs(float(refreshed_account_info.cash) - state.last_known_cash) > 0.01:
                                logger.warning(f"Cash mismatch: Stream state {state.last_known_cash}, API state {refreshed_account_info.cash}")
                            state.update_cash_and_value(float(refreshed_account_info.cash), float(refreshed_account_info.portfolio_value))
                        else:
                            logger.warning("Periodic refresh: Could not fetch account info.")

                        refreshed_position_info = broker.get_position(state.symbol)
                        refreshed_qty = 0.0
                        if refreshed_position_info:
                            refreshed_qty = float(refreshed_position_info.qty)
                        
                        if abs(refreshed_qty - state.current_position_qty) > 0.01:
                            logger.warning(f"Position mismatch for {state.symbol}: Stream state {state.current_position_qty}, API state {refreshed_qty}. Syncing with API state.")
                        
                        last_account_refresh_time = current_time
                    except Exception as refresh_err:
                        logger.error(f"Error during periodic account/position refresh: {refresh_err}", exc_info=True)

                queued_item = await asyncio.wait_for(data_queue.get(), timeout=1.0)
                data_type = queued_item.get('type')
                logger.debug(f"Processing item from queue: Type={data_type}, Item={queued_item}")

                signal = None
                if data_type in ['trade', 'bar']:
                    current_price = state.last_trade_price
                    if not current_price and data_type == 'bar':
                        current_price = state.last_bar_close
                    
                    if current_price:
                        signal = strategy.get_signal(current_price, state.current_position_qty)
                        logger.info(f"Strategy generated signal: {signal} based on price {current_price:.2f} and position {state.current_position_qty}")
                    else:
                        logger.warning("No current price available (trade or bar) to generate signal.")

                if signal is not None and state.active_order_id is None:
                    logger.info(f"Received signal: {signal} for {state.symbol}")

                    if signal == 'BUY':
                        state.target_position_qty = 10
                    elif signal == 'SELL':
                        state.target_position_qty = -10
                    elif signal == 'CLOSE':
                        state.target_position_qty = 0
                    else:
                        state.target_position_qty = state.current_position_qty

                    qty_to_trade = state.target_position_qty - state.current_position_qty

                    if abs(qty_to_trade) > 0.01:
                        side = 'buy' if qty_to_trade > 0 else 'sell'
                        order_qty = abs(qty_to_trade)
                        client_order_id = f"live_{uuid.uuid4()}"

                        logger.info(f"Signal requires action: Target={state.target_position_qty}, Current={state.current_position_qty}. Attempting to {side} {order_qty} {state.symbol}")

                        order = broker.place_order(
                            symbol=state.symbol,
                            qty=order_qty,
                            side=side,
                            order_type='market',
                            time_in_force='day',
                            client_order_id=client_order_id
                        )

                        if order and hasattr(order, 'id') and order.id:
                            logger.info(f"Market order placed. ClientOrderID: {client_order_id}, API OrderID: {order.id}, Status: {order.status}")
                            state.set_active_order(client_order_id)
                            if order.status in ['rejected', 'canceled', 'expired']:
                                logger.warning(f"Order {order.id} was {order.status} immediately. Clearing active order flag.")
                                state.set_active_order(None)
                        else:
                            logger.error(f"Failed to place {side} order for {order_qty} {state.symbol}. Order object: {order}")
                    else:
                        logger.debug("No trade needed based on signal and current position.")
                
                elif signal is not None and state.active_order_id is not None:
                    logger.info(f"Holding off on new signal {signal}, active order exists: {state.active_order_id}")

                data_queue.task_done()

            except asyncio.TimeoutError:
                logger.debug("No data received from queue in the last 1 second. Checking for signals with current state.")
                if state.active_order_id is None:
                    current_price = state.last_trade_price or state.last_bar_close
                    if current_price:
                        pass
                continue
            except Exception as loop_error:
                logger.error(f"Error in main trading loop: {loop_error}", exc_info=True)
                await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("Main loop cancelled.")
    except Exception as e:
        logger.error(f"Critical error in main function: {e}", exc_info=True)
    finally:
        logger.info("Shutting down trader...")
        if 'stream_task' in locals() and not stream_task.done():
            logger.info("Cancelling stream task...")
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                logger.info("Stream task successfully cancelled.")
            except Exception as cancel_err:
                logger.error(f"Error during stream task cancellation: {cancel_err}")

        if 'broker' in locals() and broker.stream:
            logger.info("Stopping stream connection...")
            await broker.stop_streaming()

        logger.info("Live Trader shut down.")


async def shutdown(sig, loop):
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
