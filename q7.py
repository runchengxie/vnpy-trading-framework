import os
import pandas as pd
import pyarrow as pa # Import pyarrow
import pyarrow.parquet as pq # Import parquet module
from alpaca_trade_api.rest import REST, TimeFrame
from dotenv import load_dotenv
from datetime import date, timedelta
import backtrader as bt

# ===========================================================================================
# 第一部分：策略实施与回测（Python 重点）
# ===========================================================================================

# 1.  **数据获取与准备：**
#     *   [ ] 选择数据源（推荐 OpenBB/券商）。
#     *   [ ] 获取所选资产的历史高频数据（例如，15分钟、30秒）。
#     *   [ ] 将数据加载到合适的格式中（例如，pandas DataFrame）。
#     *   [ ] 清洗和预处理数据（处理缺失值，必要时进行时区转换）。

# 2.  **趋势跟踪策略实施：**
#     *   [ ] **指标选择：** 选择一个或多个指标（EMA、ADX、MACD、自定义比率）。
#     *   [ ] **指标计算：**
#         *   [ ] 实现所选标准指标（EMA、ADX、MACD）的计算逻辑。
#         *   [ ] *如果使用自定义比率：*
#             *   [ ] 实现短期重采样 (`DataFrame.resample`)。
#             *   [ ] 实现长期平均值计算。
#             *   [ ] 实现比率计算（短期价格/长期平均值）。
#     *   [ ] **信号生成：**
#         *   [ ] 根据指标值/交叉/阈值定义精确的买入/卖出信号规则（例如，EMA 交叉、ADX > 阈值、比率偏离 1）。
#         *   [ ] 实现从指标数据生成信号的逻辑。
#     *   [ ] **回测：**
#         *   [ ] 实现一个回测引擎（或使用像 `backtrader`、`zipline`、`vectorbt` 这样的库，注意提到的限制）。
#         *   [ ] 根据生成的信号模拟交易。
#         *   [ ] 计算性能指标（盈利/亏损、胜率等）。
#     *   [ ] **参数调整与分析：**
#         *   [ ] 试验不同的指标参数（例如，EMA 周期、ADX 周期、重采样间隔、比率阈值）。
#         *   [ ] 对不同的参数集运行回测。
#         *   [ ] 分析和总结结果，确定最优参数。
#         *   [ ] 记录所选指标的数学描述。

# 3.  **均值回归策略实施：**
#     *   [ ] **方法选择：** 选择一种方法（Z-score 偏差、距离度量、OU 过程模型）。
#     *   [ ] **指标/信号计算：**
#         *   [ ] 实现所选均值回归信号的计算逻辑（例如，计算 Z-score 的滚动均值/标准差）。
#     *   [ ] **信号生成：**
#         *   [ ] 根据与均值的偏差定义精确的买入/卖出信号规则（例如，Z-score 超过阈值）。
#         *   [ ] 实现生成信号的逻辑。
#     *   [ ] **回测：**
#         *   [ ] 使用相同的引擎为均值回归策略实施回测。
#         *   [ ] 计算性能指标。
#     *   [ ] **（可选）卡尔曼/无迹卡尔曼滤波：**
#         *   [ ] 如果采用此方法，则对价格序列实施滤波。
#         *   [ ] 使用滤波后的数据重新运行信号生成和回测。

# 4.  **第一部分分析与讨论：**
#     *   [ ] 比较趋势跟踪和均值回归策略的性能。
#     *   [ ] 基于回测结果或理论推理，讨论市场状况（波动性、跳跃）对每种策略性能的潜在影响。

# --- Helper Function to find the nearest previous trading day ---
def get_last_trading_day(api_instance, target_date_str):
    """
    Finds the trading day on or immediately preceding the target date.

    Args:
        api_instance (REST): Initialized Alpaca API client.
        target_date_str (str): The target date in 'YYYY-MM-DD' format.

    Returns:
        str: The date string of the actual trading day in 'YYYY-MM-DD' format, or None if an error occurs.
    """
    target_dt = date.fromisoformat(target_date_str)
    # Check a window around the target date for the calendar
    calendar_start = (target_dt - timedelta(days=10)).strftime('%Y-%m-%d')
    calendar_end = target_dt.strftime('%Y-%m-%d')

    try:
        calendar = api_instance.get_calendar(start=calendar_start, end=calendar_end)
        trading_days = {cal.date.date() for cal in calendar} # Use .date() to get date object

        current_dt = target_dt
        while current_dt >= date.fromisoformat(calendar_start):
            if current_dt in trading_days:
                print(f"目标日期 {target_date_str} 的交易日确定为: {current_dt.strftime('%Y-%m-%d')}")
                return current_dt.strftime('%Y-%m-%d')
            current_dt -= timedelta(days=1)

        print(f"错误：在 {calendar_start} 和 {target_date_str} 之间找不到交易日。")
        return None
    except Exception as e:
        print(f"获取交易日历时出错: {e}")
        return None


# 从 .env 文件加载环境变量
load_dotenv()

# Alpaca API 凭证
API_KEY = os.getenv('APCA_API_KEY_ID')
SECRET_KEY = os.getenv('APCA_API_SECRET_KEY')
BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets') # 默认为模拟交易

# 检查 API 密钥是否已加载
if not API_KEY or not SECRET_KEY:
    print("错误：在环境变量中未找到 Alpaca API 密钥或秘密密钥。")
    print("请设置 APCA_API_KEY_ID 和 APCA_API_SECRET_KEY。")
    # exit() # 或者适当地处理错误

# Define cache directory
CACHE_DIR = 'cache'
os.makedirs(CACHE_DIR, exist_ok=True) # Create cache directory if it doesn't exist

# 初始化 Alpaca API
api = REST(API_KEY, SECRET_KEY, base_url=BASE_URL, api_version='v2')

def fetch_historical_data(symbol, timeframe, start_date, end_date):
    """
    使用 Alpaca API 获取给定交易品种的历史 K 线数据，并使用 Parquet 格式进行缓存。

    Args:
        symbol (str): 交易品种代码 (例如, 'SPY')。
        timeframe (TimeFrame): K 线的时间范围 (例如, TimeFrame.Minute, TimeFrame.Hour, TimeFrame.Day)。
        start_date (str): 开始日期，格式为 'YYYY-MM-DD' 或 ISO 格式字符串。
        end_date (str): 结束日期，格式为 'YYYY-MM-DD' 或 ISO 格式字符串。

    Returns:
        pandas.DataFrame: 包含历史 K 线数据的 DataFrame，如果发生错误则返回 None。
    """
    # --- Cache Handling ---
    # Create a unique filename for the cache
    timeframe_str = str(timeframe).replace("TimeFrame.", "") # Get a string representation like 'Minute'
    cache_filename = f"{symbol}_{timeframe_str}_{start_date}_{end_date}.parquet"
    cache_filepath = os.path.join(CACHE_DIR, cache_filename)

    # Check if cached file exists
    if os.path.exists(cache_filepath):
        try:
            print(f"正在从缓存加载数据: {cache_filepath}")
            bars = pd.read_parquet(cache_filepath)
            # Parquet usually handles timezone better, but double-check
            if not isinstance(bars.index, pd.DatetimeIndex):
                 bars.index = pd.to_datetime(bars.index) # Ensure index is datetime
            if bars.index.tz is None:
                 bars.index = bars.index.tz_localize('UTC') # Assume UTC if no timezone
            bars.index = bars.index.tz_convert('America/New_York') # Convert to desired timezone
            print(f"成功从缓存加载 {len(bars)} 个数据点。")
            return bars
        except Exception as e:
            print(f"从缓存加载数据时出错: {e}. 将尝试从 API 获取。")
            # If loading fails, proceed to fetch from API

    # --- Fetch from API (if not cached or cache load failed) ---
    try:
        print(f"正在从 API 获取 {symbol} 从 {start_date} 到 {end_date} 的 {timeframe} 数据...")
        # Note: Alpaca's get_bars returns data in UTC.
        start_dt_iso = pd.Timestamp(start_date, tz='America/New_York').tz_convert('UTC').isoformat()
        end_dt_iso = (pd.Timestamp(end_date, tz='America/New_York') + timedelta(days=1) - timedelta(seconds=1)).tz_convert('UTC').isoformat()

        bars = api.get_bars(symbol, timeframe, start=start_dt_iso, end=end_dt_iso, adjustment='raw').df

        if not bars.empty:
            # Convert index to America/New_York timezone for consistency
            bars.index = bars.index.tz_convert('America/New_York')
            # Filter data strictly within the requested start/end dates in NY time
            bars = bars[(bars.index >= pd.Timestamp(start_date, tz='America/New_York')) &
                        (bars.index <= pd.Timestamp(end_date, tz='America/New_York') + timedelta(days=1))]

            print(f"成功从 API 获取 {len(bars)} 个数据点。")

            # --- Save to Cache ---
            try:
                # Use df.to_parquet. No need to reset index usually.
                # Specify the engine and potentially compression
                bars.to_parquet(cache_filepath, engine='pyarrow', compression='snappy') # 'snappy' is a common choice
                print(f"数据已缓存到: {cache_filepath}")
            except Exception as e:
                print(f"缓存数据时出错: {e}") # Log caching error but continue

            return bars
        else:
            print(f"未获取到 {symbol} 的数据。")
            return None # Return None if no data fetched

    except Exception as e:
        print(f"获取 {symbol} 数据时出错: {e}")
        return None

# --- Backtrader Strategy Definition ---
class EMACrossoverStrategy(bt.Strategy):
    params = (
        ('ema_short', 10), # 短周期 EMA
        ('ema_long', 30),  # 长周期 EMA
        ('adx_period', 14), # ADX 周期
        ('adx_threshold', 25.0), # ADX 阈值，用于过滤信号
        ('printlog', False), # 是否打印交易日志
    )

    # --- 指标数学描述 ---
    # EMA (Exponential Moving Average - 指数移动平均线):
    # EMA 通过给予近期价格比远期价格更高的权重来计算平均价格。
    # 计算公式通常是递归的：
    # EMA_today = (Price_today * alpha) + (EMA_yesterday * (1 - alpha))
    # 其中 alpha (平滑系数) = 2 / (period + 1)
    # period 是 EMA 的周期 (例如, params.ema_short 或 params.ema_long)。
    #
    # ADX (Average Directional Movement Index - 平均趋向指数):
    # ADX 用于衡量趋势的强度，而不是趋势的方向。它通常与 +DI 和 -DI 指标一起使用。
    # 计算涉及以下步骤：
    # 1. 计算真实波幅 (True Range, TR)。
    # 2. 计算方向性运动 (+DM, -DM)，基于当前高/低价与前一高/低价的比较。
    # 3. 平滑 TR, +DM, -DM (通常使用 Wilder 平滑法，周期为 params.adx_period)。
    # 4. 计算方向性指标 (+DI, -DI)：+DI = (Smoothed +DM / Smoothed TR) * 100, -DI = (Smoothed -DM / Smoothed TR) * 100。
    # 5. 计算趋向指数 (DX)：DX = (|(+DI) - (-DI)| / |(+DI) + (-DI)|) * 100。
    # 6. 计算 ADX：ADX 是 DX 的平滑移动平均 (通常也使用 Wilder 平滑法，周期为 params.adx_period)。
    # ADX 值越高，表示趋势越强 (无论上升或下降)。低于阈值 (例如 params.adx_threshold) 通常表示市场处于盘整或趋势较弱。
    # ---

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        # 保持对收盘价序列的引用
        self.dataclose = self.datas[0].close
        # Keep references to high, low as well for ADX
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # 跟踪挂单和持仓状态
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 添加 EMA 指标
        self.ema_short = bt.indicators.ExponentialMovingAverage(
            self.datas[0], period=self.params.ema_short)
        self.ema_long = bt.indicators.ExponentialMovingAverage(
            self.datas[0], period=self.params.ema_long)

        # 添加交叉信号指标
        self.crossover = bt.indicators.CrossOver(self.ema_short, self.ema_long)

        # 添加 ADX 指标
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            self.datas[0], period=self.params.adx_period)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # 买入/卖出订单 已提交/已接受 - 无事可做
            return

        # 检查订单是否已完成
        # 注意：如果现金不足，经纪商可能会拒绝订单
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        # 写出订单状态
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)


    def next(self):
        # 记录当前周期的收盘价
        # self.log(f'Close, {self.dataclose[0]:.2f}')
        # Log ADX value for debugging/observation
        # self.log(f'ADX: {self.adx.adx[0]:.2f}')

        # 如果有挂单，则不能发送第二个订单
        if self.order:
            return

        # 检查我们是否在市场中
        if not self.position:
            # 不在市场中，检查是否触发买入信号
            # 条件：EMA 短上穿长 AND ADX > 阈值 (表示趋势强劲)
            if self.crossover > 0 and self.adx.adx[0] > self.params.adx_threshold:
                self.log(f'BUY CREATE, Close: {self.dataclose[0]:.2f}, ADX: {self.adx.adx[0]:.2f}')
                # 保持跟踪创建的订单
                self.order = self.buy()

        else:
            # 已经在市场中，检查是否触发卖出信号
            # 条件：EMA 短下穿长 (退出信号不一定需要 ADX 过滤，但可以根据策略调整)
            # 如果希望仅在趋势减弱时退出，可以添加 ADX 条件，例如 self.adx.adx[0] < self.params.adx_threshold
            # 这里我们保持原始逻辑：只要发生死叉就退出
            if self.crossover < 0:
                self.log(f'SELL CREATE, Close: {self.dataclose[0]:.2f}, ADX: {self.adx.adx[0]:.2f}')
                # 保持跟踪创建的订单
                self.order = self.sell()

# --- 使用示例 ---
# 定义参数
ticker = 'SPY' # 标普 500 ETF
time_frame_value = 15 # 单位的值 (15 minutes)
time_frame_unit = TimeFrame.Minute # 使用 Alpaca 的 TimeFrame 枚举

# --- 修改日期范围以进行回测 ---
# 例如，回测 2023 年的数据
start_date_str = "2023-01-01"
end_date_str = "2023-12-31"

# 获取该时间段的 1 分钟数据用于重采样
print(f"正在获取 {ticker} 从 {start_date_str} 到 {end_date_str} 的 1 分钟数据...")
# 注意：对于长时间跨度的高频数据，Alpaca 可能会有限制或需要分块获取
# 这里我们尝试一次性获取，如果失败，需要实现分块逻辑
spy_data_1min = fetch_historical_data(ticker, TimeFrame.Minute, start_date_str, end_date_str)

if spy_data_1min is not None and not spy_data_1min.empty:
    print(f"\n原始 1 分钟数据样本（前 5 行）：\n{spy_data_1min.head()}")
    print(f"\n原始 1 分钟数据样本（后 5 行）：\n{spy_data_1min.tail()}")
    print(f"\n数据信息：\n")
    spy_data_1min.info()

    # 重采样到目标频率
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'trade_count': 'sum',
        'vwap': 'mean'
    }
    agg_dict = {k: v for k, v in agg_dict.items() if k in spy_data_1min.columns}

    print(f"\n正在重采样到 {time_frame_value} 分钟...")
    resample_freq = f'{time_frame_value}T'
    spy_data_resampled = spy_data_1min.resample(resample_freq).agg(agg_dict).dropna()

    # --- Backtrader 设置和运行 ---
    if not spy_data_resampled.empty:
        print(f"\n重采样后的 {time_frame_value} 分钟数据样本（前 5 行）：\n{spy_data_resampled.head()}")
        print(f"\n重采样后的数据信息：\n")
        spy_data_resampled.info()

        # --- 参数优化设置 ---
        print("\n开始参数优化...")

        # 1. 创建 Cerebro 引擎
        cerebro = bt.Cerebro(optreturn=False) # optreturn=False 更适合与分析器一起使用

        # 2. 添加策略进行优化
        #    为需要优化的参数提供范围或列表
        strats = cerebro.optstrategy(
            EMACrossoverStrategy,
            ema_short=range(5, 16, 5),       # 测试 5, 10, 15
            ema_long=range(20, 41, 10),      # 测试 20, 30, 40
            adx_period=range(10, 21, 5),     # 测试 10, 15, 20
            adx_threshold=[20.0, 25.0, 30.0] # 测试 20, 25, 30
            # printlog=False # 优化时通常关闭日志以保持输出清洁
        )

        # 3. 准备数据 (与之前相同)
        if 'openinterest' not in spy_data_resampled.columns:
            spy_data_resampled['openinterest'] = 0
        data_feed = bt.feeds.PandasData(dataname=spy_data_resampled, datetime=None, open='open', high='high', low='low', close='close', volume='volume', openinterest='openinterest')
        cerebro.adddata(data_feed)

        # 4. 设置初始资本 (与之前相同)
        cerebro.broker.setcash(100000.0)

        # 5. 设置佣金 (与之前相同)
        cerebro.broker.setcommission(commission=0.01)

        # 6. 添加分析器 (与之前相同，将在每次优化运行中计算)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns') # 添加年化收益率分析器

        # 7. 运行优化
        #    可以指定 maxcpus 来使用多核处理器加速，例如 maxcpus=os.cpu_count()
        #    注意：并行运行可能与某些复杂的 print 输出或调试冲突
        opt_results = cerebro.run(maxcpus=1) # 先用单核运行确保逻辑正确

        # 8. 分析优化结果
        print('\n--- 参数优化结果分析 ---')
        parsed_results = []
        for run in opt_results:
            for strategy_instance in run: # 每个 run 可能包含一个策略实例列表（虽然这里只有一个）
                params = strategy_instance.params # 获取当前运行的参数
                analyzers = strategy_instance.analyzers # 获取分析器
                trade_analysis = analyzers.tradeanalyzer.get_analysis()
                sharpe_ratio = analyzers.sharpe.get_analysis()
                drawdown = analyzers.drawdown.get_analysis()
                returns_analysis = analyzers.returns.get_analysis()

                total_trades = trade_analysis.total.total if trade_analysis.total else 0
                win_rate = (trade_analysis.won.total / total_trades * 100) if total_trades > 0 else 0
                net_pnl = trade_analysis.pnl.net.total if trade_analysis.pnl else 0

                parsed_results.append({
                    'ema_short': params.ema_short,
                    'ema_long': params.ema_long,
                    'adx_period': params.adx_period,
                    'adx_threshold': params.adx_threshold,
                    'final_value': strategy_instance.broker.getvalue(), # 获取最终组合价值
                    'pnl': net_pnl,
                    'sharpe_ratio': sharpe_ratio.get('sharperatio', None),
                    'max_drawdown': drawdown.max.drawdown,
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'annual_return': returns_analysis.get('rnorm100', None) # 获取年化收益率
                })

        # 将结果转换为 DataFrame 便于分析
        results_df = pd.DataFrame(parsed_results)

        # 按某个指标排序，例如最终价值或夏普比率
        results_df_sorted = results_df.sort_values(by='final_value', ascending=False)
        # 或者按夏普比率排序 (处理 None 值)
        # results_df_sorted = results_df.sort_values(by='sharpe_ratio', ascending=False, na_position='last')


        print("\n优化结果摘要 (按最终价值排序):")
        print(results_df_sorted.head()) # 打印表现最好的几组参数

        # 找到最优参数组合 (基于最终价值)
        best_params = results_df_sorted.iloc[0]
        print("\n最优参数组合 (基于最终价值):")
        print(best_params)

        # (可选) 可以将 results_df_sorted 保存到 CSV 文件
        # results_df_sorted.to_csv('optimization_results.csv', index=False)

        # --- (可选) 使用最优参数进行一次最终回测并绘图 ---
        print("\n使用最优参数进行最终回测...")
        final_cerebro = bt.Cerebro()
        final_cerebro.addstrategy(EMACrossoverStrategy,
                                  ema_short=int(best_params['ema_short']), # 从结果中获取最优参数
                                  ema_long=int(best_params['ema_long']),
                                  adx_period=int(best_params['adx_period']),
                                  adx_threshold=float(best_params['adx_threshold']),
                                  printlog=True) # 在最终回测中打开日志

        # 添加数据、资金、佣金、分析器 (与优化循环内类似)
        final_cerebro.adddata(data_feed)
        final_cerebro.broker.setcash(100000.0)
        final_cerebro.broker.setcommission(commission=0.01)
        final_cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        final_cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        final_cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

        # 运行最终回测
        final_results = final_cerebro.run()
        final_strat = final_results[0]

        # 打印最终回测的分析结果 (可以复用之前的打印逻辑)
        # ... (添加打印最终分析结果的代码) ...
        print(f'\n最终投资组合价值 (最优参数): {final_cerebro.broker.getvalue():,.2f}')

        # 绘制最终回测图
        try:
            print("\n尝试生成最终回测图表...")
            final_cerebro.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"\n无法生成图表: {e}")


    else:
        print(f"\n重采样后数据为空，无法进行回测或优化。")

else:
    print(f"\n无法获取或处理 {ticker} 在 {start_date_str} 到 {end_date_str} 的数据。")


# ===========================================================================================
# 第二部分：策略实施与回测（续）
# ===========================================================================================
# （您现有的策略实施代码将在此处继续，使用获取的数据 spy_data_15min）
# ...
# (后续可以添加均值回归策略的 Backtrader 实现)
# ...