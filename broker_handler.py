# broker_handler.py
import os
import logging
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, APIError, TimeFrame
from alpaca_trade_api.stream import Stream
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import asyncio

logger = logging.getLogger(__name__)

class BrokerAPIHandler:
    def __init__(self):
        load_dotenv() # 确保环境变量已加载
        self.api_key = os.getenv('APCA_API_KEY_ID')
        self.secret_key = os.getenv('APCA_API_SECRET_KEY')
        # 强制使用 Paper Trading URL，防止误操作实盘
        self.base_url = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        self.stream = None # Initialize stream attribute

        if not self.api_key or not self.secret_key:
            logger.error("错误：在环境变量中未找到 Alpaca API 密钥。请检查 .env 文件。")
            raise ValueError("Missing Alpaca API Credentials")

        if 'live-api' in self.base_url:
             logger.warning("警告：检测到实盘 API URL，请确保你正在使用 Paper Trading 密钥和 URL 进行测试！")
             # Consider adding a confirmation step or raising an error here for safety
             # raise ValueError("Live API URL detected during paper trading setup.")

        logger.info(f"初始化 Alpaca API Handler，目标 URL: {self.base_url}")
        try:
            self.api = REST(self.api_key, self.secret_key, base_url=self.base_url, api_version='v2')
            # 添加重试逻辑
            retry_strategy = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST", "DELETE", "PATCH"] # Include PATCH for order modifications if needed
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.api._session.mount("https://", adapter)
            self.api._session.mount("http://", adapter)
            logger.info("已为 Alpaca API 会话添加重试逻辑。")

            # 测试连接：尝试获取账户信息
            account = self.get_account_info()
            if account:
                logger.info(f"成功连接到 Alpaca Paper Trading 账户。账户 ID: {account.id}, 状态: {account.status}")
                logger.info(f"当前购买力 (Buying Power): {account.buying_power}")
            else:
                 logger.error("连接测试失败：无法获取账户信息。可能 API 密钥无效或网络问题。")
                 # Depending on requirements, you might want to raise an exception here
                 # raise ConnectionError("Failed to connect to Alpaca API and retrieve account info.")
        except APIError as e:
            logger.error(f"连接 Alpaca API 时发生错误: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"初始化 BrokerAPIHandler 时发生未知错误: {e}", exc_info=True)
            raise

    def get_account_info(self):
        """获取账户信息"""
        logger.debug("尝试获取账户信息...")
        try:
            account = self.api.get_account()
            logger.debug(f"成功获取账户信息。ID: {account.id}")
            return account
        except APIError as e:
            logger.error(f"获取账户信息失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取账户信息时发生未知错误: {e}")
            return None

    def place_order(self, symbol, qty, side, order_type, time_in_force='day', limit_price=None, stop_price=None, client_order_id=None):
        """
        下单函数。

        Args:
            symbol (str): 交易品种代码 (e.g., 'SPY')
            qty (float): 交易数量 (Alpaca API v2 只接受正数 qty)
            side (str): 'buy' 或 'sell'
            order_type (str): 'market', 'limit', 'stop', 'stop_limit', 'trailing_stop'
            time_in_force (str): 订单有效时间 ('day', 'gtc', 'opg', 'cls', 'ioc', 'fok')
            limit_price (float, optional): 限价单的价格. Defaults to None.
            stop_price (float, optional): 止损单/止损限价单的触发价格. Defaults to None.
            client_order_id (str, optional): 自定义订单ID. Defaults to None.


        Returns:
            Order object or None: 成功则返回 Alpaca Order 对象, 失败返回 None
        """
        logger.info(f"尝试下单: {side} {qty} {symbol} @ {order_type} (limit={limit_price}, stop={stop_price}, tif={time_in_force})")
        try:
            abs_qty = abs(float(qty)) # Ensure qty is a positive float
            order_data = {
                "symbol": symbol,
                "qty": abs_qty,
                "side": side,
                "type": order_type,
                "time_in_force": time_in_force,
            }
            if limit_price is not None:
                order_data["limit_price"] = float(limit_price)
            if stop_price is not None:
                order_data["stop_price"] = float(stop_price)
            if client_order_id is not None:
                order_data["client_order_id"] = client_order_id
            # Add other potential parameters like trail_price, trail_percent if needed

            order = self.api.submit_order(**order_data)
            logger.info(f"下单请求已提交。订单 ID: {order.id}, 状态: {order.status}, Client Order ID: {order.client_order_id}")
            return order
        except APIError as e:
            logger.error(f"下单失败 ({symbol}, {side}, {qty}): {e}", exc_info=True)
            return None
        except ValueError as e:
             logger.error(f"下单参数错误 ({symbol}, {side}, {qty}): {e}", exc_info=True)
             return None
        except Exception as e:
            logger.error(f"下单时发生未知错误 ({symbol}, {side}, {qty}): {e}", exc_info=True)
            return None

    def get_order_status(self, order_id):
        """检查特定订单的状态"""
        logger.debug(f"查询订单状态: {order_id}")
        try:
            order = self.api.get_order(order_id)
            logger.debug(f"订单 {order_id} 状态: {order.status}")
            return order
        except APIError as e:
            if e.code == 404:
                 logger.warning(f"查询订单状态失败：找不到订单 {order_id}。")
            else:
                 logger.error(f"查询订单 {order_id} 状态失败: {e}")
            return None
        except Exception as e:
            logger.error(f"查询订单 {order_id} 状态时发生未知错误: {e}")
            return None

    def list_orders(self, status='open', limit=100, after=None, until=None, direction='desc', nested=True, symbols=None):
        """获取订单列表"""
        logger.debug(f"查询订单列表 (状态: {status}, 数量: {limit}, 方向: {direction})")
        try:
            orders = self.api.list_orders(
                status=status,
                limit=limit,
                after=after,
                until=until,
                direction=direction,
                nested=nested,
                symbols=symbols
            )
            logger.debug(f"找到 {len(orders)} 个符合条件的订单。")
            return orders
        except APIError as e:
            logger.error(f"查询订单列表失败: {e}")
            return []
        except Exception as e:
            logger.error(f"查询订单列表时发生未知错误: {e}")
            return []

    def cancel_order(self, order_id):
        """取消一个未成交的订单"""
        logger.info(f"尝试取消订单: {order_id}")
        try:
            self.api.cancel_order(order_id)
            logger.info(f"订单 {order_id} 取消请求已发送。")
            return True
        except APIError as e:
            if e.code == 404:
                 logger.warning(f"取消订单失败：找不到订单 {order_id}。")
            elif e.code == 422:
                 logger.warning(f"取消订单失败：订单 {order_id} 可能已成交或已被取消 ({e})。")
            else:
                 logger.error(f"取消订单 {order_id} 失败: {e}")
            return False
        except Exception as e:
            logger.error(f"取消订单 {order_id} 时发生未知错误: {e}")
            return False

    def cancel_all_orders(self):
        """取消所有未成交的订单"""
        logger.info("尝试取消所有未成交订单...")
        try:
            cancel_statuses = self.api.cancel_all_orders() # Returns list of status dicts or potentially None/empty list
            cancelled_count = 0
            failed_count = 0

            # --- FIX: Check if cancel_statuses is iterable ---
            if cancel_statuses is not None:
                # Check if it's an empty list (meaning no open orders to cancel)
                if not cancel_statuses:
                     logger.info("没有需要取消的 Open 订单。")
                else:
                    # Iterate only if it's a non-empty list
                    for status in cancel_statuses:
                        # The status object has 'id' and 'status' (HTTP status code) attributes
                        if hasattr(status, 'status') and status.status == 200:
                            cancelled_count += 1
                        elif hasattr(status, 'id'):
                            failed_count += 1
                            logger.warning(f"取消订单 {status.id} 可能失败，状态码: {getattr(status, 'status', 'N/A')}")
                        else:
                            # Handle unexpected status object format
                            failed_count += 1
                            logger.warning(f"收到未知的取消状态对象: {status}")
                    logger.info(f"取消所有订单请求处理完成。成功取消 {cancelled_count} 个，失败 {failed_count} 个。")
            else:
                # Handle the case where the API might return None explicitly
                logger.info("API 返回 None，可能没有需要取消的 Open 订单。")
            # --- End of FIX ---

            return True # Return True as the operation itself (attempting to cancel) was initiated
        except APIError as e:
            logger.error(f"取消所有订单时发生 API 错误: {e}", exc_info=True)
            return False
        except TypeError as e:
             # Catching the specific error we observed, though the check should prevent it
             logger.error(f"取消所有订单时发生类型错误 (可能在迭代时): {e}", exc_info=True)
             return False
        except Exception as e:
            logger.error(f"取消所有订单时发生未知错误: {e}", exc_info=True)
            return False

    def get_position(self, symbol):
         """获取特定资产的持仓信息"""
         logger.debug(f"查询持仓: {symbol}")
         try:
             position = self.api.get_position(symbol)
             logger.debug(f"持仓 {symbol}: Qty={position.qty}, AvgEntryPrice={position.avg_entry_price}")
             return position
         except APIError as e:
             if e.code == 404:
                 logger.debug(f"查询持仓：未持有 {symbol}。")
                 return None # Return None to indicate no position, not an error
             else:
                 logger.error(f"查询持仓 {symbol} 失败: {e}")
                 return None # Return None for actual errors too, caller needs to differentiate if necessary
         except Exception as e:
              logger.error(f"查询持仓 {symbol} 时发生未知错误: {e}")
              return None

    def list_positions(self):
         """获取所有持仓信息"""
         logger.debug("查询所有持仓...")
         try:
             positions = self.api.list_positions()
             logger.debug(f"当前总持仓数: {len(positions)}")
             return positions
         except APIError as e:
             logger.error(f"查询所有持仓失败: {e}")
             return []
         except Exception as e:
             logger.error(f"查询所有持仓时发生未知错误: {e}")
             return []

    # --- 实时数据流方法 (Phase 3) ---
    async def _stream_handler(self, data):
        """Generic handler to log received stream data."""
        logger.info(f"Stream Data Received: {data}")
        # Add specific handling based on data type (trade, quote, update) if needed

    async def setup_stream(self, symbols=None, subscribe_trades=True, subscribe_quotes=False, subscribe_bars=False, subscribe_updates=True, subscribe_account=True):
        """设置并连接到 Alpaca 数据流"""
        if self.stream:
            logger.warning("Stream already exists. Disconnecting existing stream first.")
            await self.stop_streaming() # Ensure clean state

        logger.info("设置 Alpaca 数据流...")
        try:
            self.stream = Stream(self.api_key,
                                 self.secret_key,
                                 base_url=self.base_url, # Use the same base URL (paper/live)
                                 data_feed='iex') # Or 'sip' for paid data

            # --- Define generic or specific handlers ---
            async def on_trade(trade):
                logger.info(f"实时交易: {trade.symbol} Price={trade.price} Qty={trade.size}")
                # Add your logic here

            async def on_quote(quote):
                logger.debug(f"实时报价: {quote.symbol} Ask={quote.ask_price} Bid={quote.bid_price}")
                # Add your logic here

            async def on_bar(bar):
                 logger.info(f"实时分钟 K 线: {bar.symbol} O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
                 # Add your logic here

            async def on_order_update(order_update):
                 logger.info(f"订单更新: Event={order_update.event}, Order ID={order_update.order['id']}, Status={order_update.order['status']}")
                 # Add your logic here (e.g., update internal order state)

            async def on_account_update(account_update):
                 logger.info(f"账户更新: {account_update}")
                 # Add your logic here (e.g., update buying power)

            # --- Subscribe based on flags ---
            if subscribe_trades and symbols:
                self.stream.subscribe_trades(on_trade, *symbols)
                logger.info(f"Subscribed to trades for: {symbols}")
            if subscribe_quotes and symbols:
                self.stream.subscribe_quotes(on_quote, *symbols)
                logger.info(f"Subscribed to quotes for: {symbols}")
            if subscribe_bars and symbols:
                 self.stream.subscribe_bars(on_bar, *symbols)
                 logger.info(f"Subscribed to bars for: {symbols}")
            if subscribe_updates:
                self.stream.subscribe_trade_updates(on_order_update)
                logger.info("Subscribed to trade (order) updates.")
            if subscribe_account:
                # Note: Account updates might be less frequent or require specific permissions
                self.stream.subscribe_account_updates(on_account_update)
                logger.info("Subscribed to account updates.")

            logger.info("数据流设置完成，准备运行...")
            return True
        except Exception as e:
            logger.error(f"设置数据流时出错: {e}", exc_info=True)
            self.stream = None
            return False

    async def start_streaming(self):
         """启动数据流 (需要在 asyncio 事件循环中运行)"""
         if self.stream:
             logger.info("启动 Alpaca 数据流...")
             try:
                 await self.stream.run() # This blocks until stopped or an error occurs
                 logger.info("数据流已停止。")
             except KeyboardInterrupt:
                 logger.info("数据流被中断。")
                 await self.stop_streaming()
             except Exception as e:
                 logger.error(f"数据流运行时出错: {e}", exc_info=True)
                 await self.stop_streaming() # Attempt to clean up
         else:
             logger.error("Stream 未设置，请先调用 setup_stream()")

    async def stop_streaming(self):
         """停止数据流"""
         if self.stream:
             logger.info("尝试停止 Alpaca 数据流...")
             try:
                 await self.stream.stop_ws() # Use the async stop method
                 self.stream = None # Clear the stream object
                 logger.info("数据流已成功停止。")
             except Exception as e:
                 logger.error(f"停止数据流时出错: {e}", exc_info=True)
         else:
             logger.debug("数据流未运行或已停止。")

# Example of how to run the stream (usually in your main execution script)
# async def main_stream_test():
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     handler = None
#     try:
#         handler = BrokerAPIHandler()
#         if await handler.setup_stream(symbols=['AAPL', 'MSFT'], subscribe_quotes=True):
#             await handler.start_streaming() # This will run indefinitely
#     except KeyboardInterrupt:
#         logger.info("Keyboard interrupt received. Stopping stream...")
#     except Exception as e:
#         logger.exception(f"An error occurred: {e}")
#     finally:
#         if handler and handler.stream:
#             logger.info("Ensuring stream is stopped in finally block.")
#             # Running async stop in a non-async finally block is tricky.
#             # Better to handle shutdown gracefully via signals or asyncio task management.
#             # For a simple script, this might be okay, but can cause issues.
#             try:
#                 loop = asyncio.get_event_loop()
#                 if loop.is_running():
#                     loop.create_task(handler.stop_streaming())
#                 else:
#                     asyncio.run(handler.stop_streaming()) # Run in a new loop if needed
#             except Exception as stop_err:
#                 logger.error(f"Error during final stream stop: {stop_err}")
#         logger.info("Stream test finished.")

# if __name__ == "__main__":
#     # To test streaming:
#     # asyncio.run(main_stream_test())
#     pass # Keep __main__ clean or use for basic non-async tests
