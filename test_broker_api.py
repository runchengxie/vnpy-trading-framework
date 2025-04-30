# test_broker_api.py
import time
import logging
import asyncio # Needed if testing async parts, though primary test is sync
from broker_handler import BrokerAPIHandler # Assuming your class is in broker_handler.py

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Synchronous Test Function ---
def run_sync_tests(handler, symbol_to_test='AAPL'):
    logger.info(f"\n--- 开始同步订单管理测试 ({symbol_to_test}) ---")

    # 0. Get account info first
    logger.info("\n[测试 0: 获取账户信息]")
    account_info = handler.get_account_info()
    if account_info:
        logger.info(f"账户 ID: {account_info.id}, 状态: {account_info.status}, 购买力: {account_info.buying_power}")
    else:
        logger.error("无法获取账户信息，测试中止。请检查 API 密钥和连接。")
        return

    # 1. 测试下单 (限价单，远离市价以避免立即成交)
    logger.info("\n[测试 1: 下达一个远离市场的限价买单]")
    test_limit_price_buy = 10.0 # Default low price
    try:
         # Use the synchronous REST API to get latest quote
         last_quote = handler.api.get_latest_quote(symbol_to_test)
         current_price = last_quote.ap # Ask price
         test_limit_price_buy = round(current_price * 0.90, 2) # 挂一个低于市价10%的买单
         logger.info(f"{symbol_to_test} 当前卖一价约为: {current_price:.2f}. 测试买入限价: {test_limit_price_buy}")
    except Exception as e:
         logger.warning(f"无法获取 {symbol_to_test} 最新报价，将使用默认低价 {test_limit_price_buy}: {e}")

    buy_order = handler.place_order(
        symbol=symbol_to_test,
        qty=1, # 测试数量: 1 share
        side='buy',
        order_type='limit',
        time_in_force='day',
        limit_price=test_limit_price_buy,
        client_order_id=f'test_buy_{int(time.time())}' # Example client order ID
    )

    buy_order_id = None
    if buy_order:
        buy_order_id = buy_order.id
        logger.info(f"买单已提交，订单 ID: {buy_order_id}, Client Order ID: {buy_order.client_order_id}")
        logger.info("等待 2 秒让订单状态更新...")
        time.sleep(2)

        # 2. 测试检查订单状态
        logger.info(f"\n[测试 2: 检查订单 {buy_order_id} 的状态]")
        order_status = handler.get_order_status(buy_order_id)
        if order_status:
            logger.info(f"订单 {buy_order_id} 当前状态: {order_status.status}") # Should be 'new' or 'accepted'
        else:
            logger.warning(f"无法获取订单 {buy_order_id} 状态。")

        time.sleep(1)

        # 3. 测试取消订单
        logger.info(f"\n[测试 3: 取消订单 {buy_order_id}]")
        cancel_success = handler.cancel_order(buy_order_id)
        if cancel_success:
            logger.info(f"订单 {buy_order_id} 取消请求成功。等待 2 秒确认状态...")
            time.sleep(2)
            # 再次检查状态确认取消
            logger.info(f"再次检查订单 {buy_order_id} 的状态...")
            final_status = handler.get_order_status(buy_order_id)
            if final_status:
                logger.info(f"订单 {buy_order_id} 最终状态: {final_status.status}") # 应该是 'canceled'
            else:
                logger.warning(f"无法获取最终订单 {buy_order_id} 状态。")
        else:
            logger.warning(f"取消订单 {buy_order_id} 失败。检查日志获取详情。")
    else:
        logger.error("测试 1 下单失败，后续相关测试跳过。")

    # 4. 测试列出当前 Open 订单 (应该为空，因为我们取消了唯一的订单)
    logger.info("\n[测试 4: 列出当前 Open 订单]")
    open_orders = handler.list_orders(status='open')
    if open_orders:
        logger.warning(f"发现 {len(open_orders)} 个 Open 订单，预期为 0:")
        for o in open_orders:
            logger.warning(f"  - ID: {o.id}, Symbol: {o.symbol}, Status: {o.status}")
    else:
        logger.info("未找到 Open 订单 (符合预期)。")

    # 5. 测试获取特定持仓
    logger.info(f"\n[测试 5: 查询 {symbol_to_test} 持仓]")
    position = handler.get_position(symbol_to_test)
    if position:
        logger.info(f"持有 {symbol_to_test}: Qty={position.qty}, Avg Entry Price={position.avg_entry_price}")
    else:
        # This is expected if the account doesn't hold the symbol
        logger.info(f"未持有 {symbol_to_test} 或查询失败 (请参考 DEBUG 日志区分)。")

    # 6. 测试获取所有持仓
    logger.info("\n[测试 6: 查询所有持仓]")
    all_positions = handler.list_positions()
    if all_positions:
        logger.info(f"当前总持仓数: {len(all_positions)}")
        for p in all_positions:
            logger.info(f"  - {p.symbol}: Qty={p.qty}, Avg Entry Price={p.avg_entry_price}, Market Value={p.market_value}")
    else:
        logger.info("当前无任何持仓或查询失败。")

    # 7. 测试取消所有订单 (以防万一有残留)
    logger.info("\n[测试 7: 取消所有 Open 订单]")
    handler.cancel_all_orders()
    time.sleep(1)
    logger.info("再次检查 Open 订单...")
    final_open_orders = handler.list_orders(status='open')
    if not final_open_orders:
        logger.info("确认没有 Open 订单。")
    else:
        logger.warning(f"取消所有订单后仍发现 {len(final_open_orders)} 个 Open 订单。")


    logger.info(f"\n--- 同步订单管理测试 ({symbol_to_test}) 结束 ---")

# --- (Optional) Async Test Function for Streaming ---
# async def run_async_stream_test(handler, symbols=['AAPL']):
#     logger.info(f"\n--- 开始异步数据流测试 ({symbols}) ---")
#     if await handler.setup_stream(symbols=symbols, subscribe_quotes=True, subscribe_trades=True):
#         logger.info("数据流设置成功。将运行 15 秒...")
#         try:
#             await asyncio.wait_for(handler.start_streaming(), timeout=15.0)
#         except asyncio.TimeoutError:
#             logger.info("15 秒测试时间到，停止数据流...")
#             await handler.stop_streaming()
#         except KeyboardInterrupt:
#             logger.info("接收到中断信号，停止数据流...")
#             await handler.stop_streaming()
#         except Exception as e:
#             logger.error(f"数据流测试期间出错: {e}", exc_info=True)
#             await handler.stop_streaming()
#     else:
#         logger.error("数据流设置失败，测试跳过。")
#     logger.info("--- 异步数据流测试结束 ---")


if __name__ == "__main__":
    try:
        # Initialize the handler
        broker_handler = BrokerAPIHandler()

        # --- Run Synchronous Tests ---
        run_sync_tests(broker_handler, symbol_to_test='AAPL') # Test with AAPL
        # run_sync_tests(broker_handler, symbol_to_test='SPY') # Optionally test with SPY

        # --- (Optional) Run Async Streaming Test ---
        # logger.info("\n准备运行异步测试...")
        # asyncio.run(run_async_stream_test(broker_handler, symbols=['AAPL', 'MSFT']))

    except ValueError as e:
        # Catch potential init errors (e.g., missing keys)
        logger.error(f"初始化 Broker Handler 失败: {e}")
    except Exception as e:
        logger.exception(f"测试过程中发生未预料的严重错误: {e}")
