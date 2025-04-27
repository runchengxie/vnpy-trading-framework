import os
import pandas as pd
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

# 初始化 Alpaca API
api = REST(API_KEY, SECRET_KEY, base_url=BASE_URL, api_version='v2')

def fetch_historical_data(symbol, timeframe, start_date, end_date):
    """
    使用 Alpaca API 获取给定交易品种的历史 K 线数据。

    Args:
        symbol (str): 交易品种代码 (例如, 'SPY')。
        timeframe (TimeFrame): K 线的时间范围 (例如, TimeFrame.Minute, TimeFrame.Hour, TimeFrame.Day)。
        start_date (str): 开始日期，格式为 'YYYY-MM-DD' 或 ISO 格式字符串。
        end_date (str): 结束日期，格式为 'YYYY-MM-DD' 或 ISO 格式字符串。

    Returns:
        pandas.DataFrame: 包含历史 K 线数据的 DataFrame，如果发生错误则返回 None。
    """
    try:
        print(f"正在获取 {symbol} 从 {start_date} 到 {end_date} 的 {timeframe} 数据...")
        # 注意：Alpaca 的 get_bars 返回 UTC 时间的数据。
        # Request data in RFC-3339 format for clarity with timezones
        start_dt_iso = pd.Timestamp(start_date, tz='America/New_York').tz_convert('UTC').isoformat()
        # For end_date, ensure it includes the full day if needed, or adjust as per API requirements
        # Let's fetch up to the end of the specified day in NY time
        end_dt_iso = (pd.Timestamp(end_date, tz='America/New_York') + timedelta(days=1) - timedelta(seconds=1)).tz_convert('UTC').isoformat()

        bars = api.get_bars(symbol, timeframe, start=start_dt_iso, end=end_dt_iso, adjustment='raw').df
        # 将索引转换为美国/东部时区，因为市场数据通常在此 TZ 中查看
        if not bars.empty:
            bars.index = bars.index.tz_convert('America/New_York')
            # Filter data to be strictly within the requested start/end dates in NY time
            bars = bars[(bars.index >= pd.Timestamp(start_date, tz='America/New_York')) &
                        (bars.index <= pd.Timestamp(end_date, tz='America/New_York') + timedelta(days=1))]

        print(f"成功获取 {len(bars)} 个数据点。")
        return bars
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

        # 1. 创建 Cerebro 引擎
        cerebro = bt.Cerebro()

        # 2. 添加策略
        # 可以传递 ADX 参数，或者使用默认值
        cerebro.addstrategy(EMACrossoverStrategy,
                            ema_short=10,
                            ema_long=30,
                            adx_period=14,
                            adx_threshold=25.0, # 仅在 ADX > 25 时入场
                            printlog=True) # 设置 printlog=True 查看交易日志

        # 3. 准备数据
        # Backtrader 需要特定的列名：datetime, open, high, low, close, volume, openinterest
        # 确保我们的 DataFrame 索引是 datetime 对象（已经是）
        # 如果缺少 openinterest，可以添加一列 0
        if 'openinterest' not in spy_data_resampled.columns:
            spy_data_resampled['openinterest'] = 0

        # 将 DataFrame 转换为 Backtrader 数据馈送
        data_feed = bt.feeds.PandasData(
            dataname=spy_data_resampled,
            datetime=None,  # 使用索引作为 datetime
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest='openinterest',
            # timeframe=bt.TimeFrame.Minutes, # 指定时间框架
            # compression=time_frame_value    # 指定压缩级别
        )

        # 4. 添加数据到 Cerebro
        cerebro.adddata(data_feed)

        # 5. 设置初始资本
        cerebro.broker.setcash(100000.0)

        # 6. 设置佣金 - 例如，每股 0.01 美元
        cerebro.broker.setcommission(commission=0.01)

        # 7. (可选) 添加分析器
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days) # 基于日收益率计算夏普比率
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

        # 8. 运行回测
        print('\n开始回测...')
        initial_portfolio_value = cerebro.broker.getvalue()
        print(f'初始投资组合价值: {initial_portfolio_value:,.2f}')

        results = cerebro.run() # 运行回测

        final_portfolio_value = cerebro.broker.getvalue()
        print(f'最终投资组合价值: {final_portfolio_value:,.2f}')
        print(f'净收益: {(final_portfolio_value - initial_portfolio_value):,.2f}')
        print(f'净收益率: {((final_portfolio_value / initial_portfolio_value) - 1) * 100:.2f}%')

        # 9. (可选) 打印分析结果
        strat = results[0] # 获取第一个策略实例
        analyzer_results = strat.analyzers.getnames()
        if 'tradeanalyzer' in analyzer_results:
            trade_analysis = strat.analyzers.tradeanalyzer.get_analysis()
            print("\n--- 交易分析 ---")
            if trade_analysis.total.total:
                print(f"总交易次数: {trade_analysis.total.total}")
                print(f"盈利交易次数: {trade_analysis.won.total}")
                print(f"亏损交易次数: {trade_analysis.lost.total}")
                print(f"胜率: {trade_analysis.won.total / trade_analysis.total.total * 100:.2f}%" if trade_analysis.total.total > 0 else "N/A")
                print(f"总净利润: {trade_analysis.pnl.net.total:.2f}")
                print(f"平均每次交易净利润: {trade_analysis.pnl.net.average:.2f}")
            else:
                print("没有发生交易。")

        if 'sharpe' in analyzer_results:
            sharpe_ratio = strat.analyzers.sharpe.get_analysis()
            print("\n--- 夏普比率 ---")
            print(f"年化夏普比率: {sharpe_ratio.get('sharperatio', 'N/A')}") # Sharpe ratio is often annualized by default depending on params

        if 'drawdown' in analyzer_results:
            drawdown = strat.analyzers.drawdown.get_analysis()
            print("\n--- 回撤分析 ---")
            print(f"最大回撤: {drawdown.max.drawdown:.2f}%")
            print(f"最大回撤金额: {drawdown.max.moneydown:.2f}")


        # 10. (可选) 绘制结果图
        # 注意：绘图可能需要 matplotlib 安装 (pip install matplotlib)
        # 在某些环境中（如无 GUI 的服务器），绘图可能会失败
        try:
            print("\n尝试生成回测图表...")
            cerebro.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"\n无法生成图表: {e}")
            print("请确保已安装 matplotlib 并且在支持 GUI 的环境中运行。")

    else:
        print(f"\n重采样后数据为空，无法进行回测。")

else:
    print(f"\n无法获取或处理 {ticker} 在 {start_date_str} 到 {end_date_str} 的数据。")


# ===========================================================================================
# 第二部分：策略实施与回测（续）
# ===========================================================================================
# （您现有的策略实施代码将在此处继续，使用获取的数据 spy_data_15min）
# ...
# (后续可以添加均值回归策略的 Backtrader 实现)
# ...