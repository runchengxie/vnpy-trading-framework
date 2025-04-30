import asyncio
import logging
import os
import signal
from dotenv import load_dotenv
import uuid # For generating unique client order IDs

# Import necessary components from your existing modules
from broker_handler import BrokerAPIHandler
from strategies import MeanReversionZScoreStrategy # Or your chosen strategy
# from data_utils import apply_kalman_filter, add_technical_indicators # If needed for live updates

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# --- Phase 1: Basic State Management ---
class TradingState:
    """Manages the real-time state of the trading bot."""
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.current_position_qty: float = 0.0
        self.active_order_id: str | None = None
        self.target_position_qty: float = 0.0 # Desired position based on signal
        self.last_known_cash: float | None = None
        self.last_known_portfolio_value: float | None = None
        self.last_trade_price: float | None = None
        self.last_bar_close: float | None = None
        # Add more state variables as needed (e.g., entry price, P&L)

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

    # Configuration
    symbol_to_trade = 'SPY' # Example symbol
    # Add strategy parameters here if needed, load from config later
    strategy_params = {
        'zscore_period': 20, 'zscore_upper': 2.0, 'zscore_lower': -2.0,
        'exit_threshold': 0.0, 'use_filtered_price': False # Adjust as needed
    }

    # --- Initialization ---
    try:
        broker = BrokerAPIHandler() # Handles API communication
        logger.info("BrokerAPIHandler initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize BrokerAPIHandler: {e}", exc_info=True)
        return # Cannot proceed without the broker

    state = TradingState(symbol=symbol_to_trade) # Manages our bot's state
    strategy = MeanReversionZScoreStrategy(**strategy_params) # Your chosen strategy
    # Note: Strategy might need adaptation for live data (see Phase 1 notes)
    # For now, assume it has a method like `update_and_signal(data_point)`

    data_queue = asyncio.Queue() # Queue for communication between stream and main loop

    # --- Initial State Setup ---
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
            # If get_position returns None due to no position, this is expected
            logger.info(f"No initial position found for {state.symbol}.")
            state.update_position(0.0)

    except Exception as e:
        logger.error(f"Error fetching initial state: {e}", exc_info=True)
        # Decide if you want to proceed with potentially incomplete state

    logger.info(f"Initial State: Position={state.current_position_qty}, Cash={state.last_known_cash}")

    # --- Setup Streaming (Modified Broker Handler needed) ---
    # We need to modify BrokerAPIHandler's stream handlers to use the data_queue
    # For now, we'll define placeholder handlers here and pass them conceptually.
    # The actual modification to broker_handler.py is the next step.

    async def handle_trade_update(update_data):
        """Callback for order updates from the stream."""
        event = update_data.event
        order_info = update_data.order
        order_id = order_info['id']
        order_status = order_info['status']
        client_order_id = order_info.get('client_order_id') # Important for matching our orders

        logger.info(f"Order Update Received: Event={event}, OrderID={order_id}, Status={order_status}, ClientOrderID={client_order_id}")

        # Basic logic: If an order related to our active one is filled or done, update state
        if state.active_order_id and client_order_id == state.active_order_id: # Check if it's our order
             if order_status in ['filled']:
                 filled_qty = float(order_info.get('filled_qty', 0))
                 side = order_info.get('side')
                 # Simple update, assumes full fill matches target change for now
                 # More robust logic needed for partial fills
                 new_position = state.current_position_qty + (filled_qty if side == 'buy' else -filled_qty)
                 state.update_position(new_position)
                 state.set_active_order(None) # Order completed
                 logger.info(f"Order {order_id} filled. New position: {state.current_position_qty}")
             elif order_status in ['canceled', 'expired', 'rejected', 'done_for_day']:
                 logger.warning(f"Order {order_id} reached final state: {order_status}. Clearing active order.")
                 state.set_active_order(None) # Order is no longer active

        # Put the raw update onto the queue if needed for other processing
        await data_queue.put({'type': 'order_update', 'data': update_data})

    async def handle_account_update(update_data):
        """Callback for account updates."""
        logger.info(f"Account Update Received: {update_data}")
        # Update cash, portfolio value, etc.
        state.update_cash_and_value(float(update_data.cash), float(update_data.portfolio_value))
        await data_queue.put({'type': 'account_update', 'data': update_data})

    async def handle_trade(trade_data):
        """Callback for new trades."""
        logger.debug(f"Trade Received: {trade_data.symbol} Price={trade_data.price} Qty={trade_data.size}")
        if trade_data.symbol == state.symbol:
            state.update_last_price(trade_data.price, 'trade')
            # Potentially add more sophisticated data processing here
            await data_queue.put({'type': 'trade', 'symbol': trade_data.symbol, 'price': trade_data.price, 'size': trade_data.size, 'timestamp': trade_data.timestamp})

    async def handle_bar(bar_data):
        """Callback for new bars."""
        logger.debug(f"Bar Received: {bar_data.symbol} O={bar_data.open} H={bar_data.high} L={bar_data.low} C={bar_data.close} V={bar_data.volume}")
        if bar_data.symbol == state.symbol:
             state.update_last_price(bar_data.close, 'bar')
             # Add bar data to strategy's history if needed
             # await strategy.add_bar(bar_data) # Example
             await data_queue.put({'type': 'bar', 'symbol': bar_data.symbol, 'open': bar_data.open, 'high': bar_data.high, 'low': bar_data.low, 'close': bar_data.close, 'volume': bar_data.volume, 'timestamp': bar_data.timestamp})


    # --- Start Streaming Task ---
    # This requires modifying broker_handler.py's setup_stream and start_streaming
    # to accept these handlers and run within the asyncio loop.
    logger.info("Setting up data stream...")
    stream_setup_success = await broker.setup_stream(
        symbols=[state.symbol],
        trade_handler=handle_trade, # Pass our handlers
        # quote_handler=handle_quote, # Add if needed
        bar_handler=handle_bar,     # Add if needed
        order_update_handler=handle_trade_update,
        account_update_handler=handle_account_update,
        subscribe_trades=True,
        subscribe_bars=False, # Enable if strategy needs bars
        subscribe_updates=True,
        subscribe_account=True
    )

    if not stream_setup_success:
        logger.error("Failed to set up data stream. Exiting.")
        return

    logger.info("Starting data stream task...")
    stream_task = asyncio.create_task(broker.start_streaming())

    # --- Main Trading Loop ---
    logger.info("Starting main trading loop...")
    try:
        while True:
            try:
                # Wait for the next piece of data from the stream handlers
                queued_item = await asyncio.wait_for(data_queue.get(), timeout=60.0) # Add timeout
                data_type = queued_item.get('type')
                data = queued_item.get('data') # Raw data might be here or parsed fields

                logger.debug(f"Processing item from queue: Type={data_type}")

                # --- Signal Generation ---
                signal = None
                if data_type in ['trade', 'bar']: # Generate signal on new price data
                    # This part needs refinement based on how the strategy consumes data
                    # Option 1: Strategy takes single data points
                    # signal = strategy.update_and_signal(queued_item)

                    # Option 2: Strategy needs a history (managed internally or externally)
                    # For now, let's assume we use the latest price from TradingState
                    current_price = state.last_trade_price or state.last_bar_close
                    if current_price:
                         # Placeholder: Strategy needs adaptation for live data point processing
                         # signal = strategy.get_signal_from_single_price(current_price)
                         logger.debug(f"Skipping signal generation for now (strategy adaptation needed). Price: {current_price}")
                         pass # Replace with actual signal generation later
                    else:
                         logger.warning("No current price available to generate signal.")


                # --- Basic Order Logic ---
                if signal is not None and state.active_order_id is None:
                    logger.info(f"Received signal: {signal}") # Signal might be BUY, SELL, HOLD, or target quantity

                    # Determine target position based on signal (example)
                    if signal == 'BUY':
                        state.target_position_qty = 10 # Example fixed quantity
                    elif signal == 'SELL':
                        state.target_position_qty = -10 # Example fixed quantity (short)
                    elif signal == 'CLOSE':
                        state.target_position_qty = 0
                    else: # HOLD or invalid signal
                        state.target_position_qty = state.current_position_qty # Maintain current

                    qty_to_trade = state.target_position_qty - state.current_position_qty

                    if abs(qty_to_trade) > 0.01: # Threshold to avoid tiny orders
                        side = 'buy' if qty_to_trade > 0 else 'sell'
                        order_qty = abs(qty_to_trade)
                        client_order_id = f"live_{uuid.uuid4()}" # Unique ID for tracking

                        logger.info(f"Signal requires action: Target={state.target_position_qty}, Current={state.current_position_qty}, Trade={side} {order_qty}")

                        # Place Market Order (simplest for now)
                        order = broker.place_order(
                            symbol=state.symbol,
                            qty=order_qty,
                            side=side,
                            order_type='market',
                            time_in_force='day', # Or 'gtc' etc.
                            client_order_id=client_order_id
                        )

                        if order:
                            logger.info(f"Market order placed. ClientOrderID: {client_order_id}, API OrderID: {order.id}")
                            state.set_active_order(client_order_id) # Track the order we just placed
                            # Optimistic update (optional, depends on strategy)
                            # state.update_position(state.target_position_qty)
                        else:
                            logger.error(f"Failed to place {side} order for {order_qty} {state.symbol}.")
                            # Reset target? Add retry logic?
                    else:
                        logger.debug("No trade needed based on signal and current position.")

                elif state.active_order_id is not None:
                    logger.debug(f"Holding off on new orders, active order exists: {state.active_order_id}")

                # Mark task as done for the queue
                data_queue.task_done()

            except asyncio.TimeoutError:
                logger.debug("No data received from queue in the last 60 seconds.")
                # Check connection status, ping, etc. if needed
                continue # Continue waiting
            except Exception as loop_error:
                logger.error(f"Error in main trading loop: {loop_error}", exc_info=True)
                # Consider adding a delay or specific error handling here
                await asyncio.sleep(5) # Avoid tight loop on persistent errors

    except asyncio.CancelledError:
        logger.info("Main loop cancelled.")
    except Exception as e:
        logger.error(f"Critical error in main function: {e}", exc_info=True)
    finally:
        logger.info("Shutting down trader...")
        # --- Cleanup ---
        if 'stream_task' in locals() and not stream_task.done():
            logger.info("Cancelling stream task...")
            stream_task.cancel()
            try:
                await stream_task # Wait for cancellation to complete
            except asyncio.CancelledError:
                logger.info("Stream task successfully cancelled.")
            except Exception as cancel_err:
                logger.error(f"Error during stream task cancellation: {cancel_err}")

        if 'broker' in locals() and broker.stream:
            logger.info("Stopping stream connection...")
            await broker.stop_streaming()

        # Optional: Place closing orders if configured
        # if state.current_position_qty != 0:
        #     logger.info("Closing open position...")
        #     # Add logic to place closing order

        logger.info("Live Trader shut down.")


# --- Graceful Shutdown Handling ---
async def shutdown(sig, loop):
    """Graceful shutdown handler."""
    logger.info(f"Received exit signal {sig.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks...")
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Flushing metrics and stopping loop.")
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # Add signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
         loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))

    try:
        loop.run_until_complete(main())
    finally:
        logger.info("Event loop closed.")
        loop.close()
