import os
import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame
from dotenv import load_dotenv

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
        start_date (str): 开始日期，格式为 'YYYY-MM-DD'。
        end_date (str): 结束日期，格式为 'YYYY-MM-DD'。

    Returns:
        pandas.DataFrame: 包含历史 K 线数据的 DataFrame，如果发生错误则返回 None。
    """
    try:
        print(f"正在获取 {symbol} 从 {start_date} 到 {end_date} 的 {timeframe} 数据...")
        # 注意：Alpaca 的 get_bars 返回 UTC 时间的数据。
        bars = api.get_bars(symbol, timeframe, start=start_date, end=end_date, adjustment='raw').df
        # 将索引转换为美国/东部时区，因为市场数据通常在此 T Z 中查看
        bars.index = bars.index.tz_convert('America/New_York')
        print(f"成功获取 {len(bars)} 个数据点。")
        return bars
    except Exception as e:
        print(f"获取 {symbol} 数据时出错: {e}")
        return None

# --- 使用示例 ---
# 定义参数
ticker = 'SPY' # 标普 500 ETF
# 选择时间范围（例如，15 分钟）
# 选项：TimeFrame.Minute, TimeFrame.Hour, TimeFrame.Day, TimeFrame.Week, TimeFrame.Month
# 对于像 15Min 这样的日内数据，使用 TimeFrame.Minute 然后重采样，或者检查是否支持特定的间隔。
# Alpaca v2 API 也直接支持字符串表示：1Min, 5Min, 15Min, 1H, 1D。
# 为了清晰起见，如果需要，可以使用字符串表示，或者使用枚举。
# time_frame = TimeFrame.Minute * 15 # 这样直接使用枚举是行不通的
time_frame_unit = TimeFrame.Minute # 基本单位
time_frame_value = 15 # 单位的值

# 或者，如果库版本/API 端点支持，直接使用字符串表示
# time_frame_str = "15Min" # 示例：查看 Alpaca 文档以获取确切格式

start = "2023-01-01" # 根据需要调整开始日期
end = "2023-12-31"   # 根据需要调整结束日期

# 使用枚举方法获取数据（如果 API 不直接支持，则需要后续重采样）
# 如果使用 TimeFrame.Minute，您将获取 1 分钟数据然后重采样。
# 让我们尝试直接获取 15 分钟数据，如果 API 通过字符串支持的话。
# get_bars 方法似乎更倾向于 TimeFrame 枚举。让我们获取 1 分钟数据并重采样。

print("首先获取 1 分钟数据用于重采样...")
spy_data_1min = fetch_historical_data(ticker, TimeFrame.Minute, start, end)

if spy_data_1min is not None and not spy_data_1min.empty:
    print(f"\n原始 1 分钟数据样本（前 5 行）：\n{spy_data_1min.head()}")
    print(f"\n原始 1 分钟数据样本（后 5 行）：\n{spy_data_1min.tail()}")
    print(f"\n数据信息：\n")
    spy_data_1min.info()

    # 重采样到 15 分钟频率
    # 定义聚合规则
    agg_dict = {
        'open': 'first',      # 开盘价取第一个值
        'high': 'max',        # 最高价取最大值
        'low': 'min',         # 最低价取最小值
        'close': 'last',      # 收盘价取最后一个值
        'volume': 'sum',      # 成交量求和
        'trade_count': 'sum', # 交易次数求和（如果可用）
        'vwap': 'mean'        # 成交量加权平均价取平均值（如果可用且有意义）
    }
    # 聚合前过滤掉不存在的列
    agg_dict = {k: v for k, v in agg_dict.items() if k in spy_data_1min.columns}

    print(f"\n正在重采样到 {time_frame_value} 分钟...")
    spy_data_15min = spy_data_1min.resample(f'{time_frame_value}T').agg(agg_dict).dropna() # 'T' 是分钟的别名

    print(f"\n重采样后的 {time_frame_value} 分钟数据样本（前 5 行）：\n{spy_data_15min.head()}")
    print(f"\n重采样后的 {time_frame_value} 分钟数据样本（后 5 行）：\n{spy_data_15min.tail()}")
    print(f"\n重采样后的数据信息：\n")
    spy_data_15min.info()

    # --- 数据清洗/预处理（示例） ---
    # 检查缺失值（尽管 resample().dropna() 处理了重采样间隙产生的 NaN）
    if spy_data_15min.isnull().values.any():
        print("\n警告：重采样后检测到缺失值。")
        # 决定处理策略（例如，向前填充、插值）
        # spy_data_15min.fillna(method='ffill', inplace=True)

    # 现在您可以使用 spy_data_15min 进行策略实施
    # 例如：在 spy_data_15min['close'] 上计算指标

else:
    print(f"\n无法获取或处理 {ticker} 的数据。")

# ===========================================================================================
# 第二部分：策略实施与回测（续）
# ===========================================================================================
# （您现有的策略实施代码将在此处继续，使用获取的数据）
# ...