import backtrader as bt
import pandas as pd

# --- Backtrader Strategy Definition ---
class EMACrossoverStrategy(bt.Strategy):
    params = (
        ('ema_short', range(10, 21, 5)), # 测试 10, 15, 20
        ('ema_long', range(30, 51, 10)), # 测试 30, 40, 50
        ('adx_period', range(10, 16, 2)), # 测试 10, 12, 14
        ('adx_threshold', [20.0, 25.0, 30.0]), # 测试 20, 25, 30
        ('use_filtered_price', False), # 是否使用滤波后的价格
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
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close
        # Keep references to high, low as well for ADX
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # 跟踪挂单和持仓状态
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 添加 EMA 指标
        period_short = self.params.ema_short[0] if hasattr(self.params.ema_short, '__getitem__') else self.params.ema_short
        period_long = self.params.ema_long[0] if hasattr(self.params.ema_long, '__getitem__') else self.params.ema_long
        self.ema_short = bt.indicators.ExponentialMovingAverage(self.datas[0], period=period_short)
        self.ema_long = bt.indicators.ExponentialMovingAverage(self.datas[0], period=period_long)

        # 添加交叉信号指标
        self.crossover = bt.indicators.CrossOver(self.ema_short, self.ema_long)

        # 添加 ADX 指标
        adx_period = self.params.adx_period[0] if hasattr(self.params.adx_period, '__getitem__') else self.params.adx_period
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.datas[0], period=adx_period)
        # Unwrap threshold for ADX optimization
        self.adx_threshold_val = self.params.adx_threshold[0] if hasattr(self.params.adx_threshold, '__getitem__') else self.params.adx_threshold

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
            if self.crossover > 0 and self.adx.adx[0] > self.adx_threshold_val:
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

# --- New Backtrader Strategy Definition: Mean Reversion Z-Score -----
class MeanReversionZScoreStrategy(bt.Strategy):
    params = (
        ('zscore_period', range(15, 31, 5)),  # 测试 15, 20, 25, 30
        ('zscore_upper', [1.5, 2.0, 2.5]),    # 测试 1.5, 2.0, 2.5
        ('zscore_lower', [-1.5, -2.0, -2.5]), # 测试 -1.5, -2.0, -2.5
        ('exit_threshold', [0.0, 0.25, -0.25]),# 测试 0.0, 0.25, -0.25
        ('use_filtered_price', True), # 固定为 True (因为是基于滤波的策略)
        ('printlog', False),     # 是否打印交易日志
    )

    # --- 指标数学描述 ---
    # Z-Score (标准分数):
    # Z-Score 衡量一个数据点偏离其均值的程度，以标准差为单位。
    # 计算公式：
    # Z = (X - μ) / σ
    # 其中：
    # X 是当前价格 (self.data.close[0])
    # μ 是价格在指定周期 (params.zscore_period) 内的滚动简单移动平均值 (SMA)
    # σ 是价格在相同周期内的滚动标准差
    #
    # 策略逻辑：
    # 当 Z-Score 低于一个负阈值 (params.zscore_lower) 时，表示价格相对于近期均值异常偏低，
    # 预期价格会回归均值（上涨），因此产生买入信号。
    # 当 Z-Score 高于一个正阈值 (params.zscore_upper) 时，表示价格相对于近期均值异常偏高，
    # 预期价格会回归均值（下跌），因此产生卖出（做空）信号。
    # 当价格回归到均值附近（Z-Score 接近 params.exit_threshold，通常为 0）时，平仓。
    # ---

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 计算滚动均值和标准差 using self.dataclose
        # Use self.p.param_name for optimization compatibility
        period = self.p.zscore_period[0] if hasattr(self.p.zscore_period, '__getitem__') else self.p.zscore_period
        rolling_mean = bt.indicators.SimpleMovingAverage(
            self.dataclose, period=period) # Use self.p
        rolling_std = bt.indicators.StandardDeviation(
            self.dataclose, period=period) # Use self.p

        # 计算 Z-score
        # 添加一个小的 epsilon 防止除以零 (虽然 StandardDeviation 应该处理)
        epsilon = 1e-6
        self.zscore = (self.dataclose - rolling_mean) / (rolling_std + epsilon)

        # Unwrap threshold params for comparisons
        self.zscore_lower_val = self.params.zscore_lower[0] if hasattr(self.params.zscore_lower, '__getitem__') else self.params.zscore_lower
        self.zscore_upper_val = self.params.zscore_upper[0] if hasattr(self.params.zscore_upper, '__getitem__') else self.params.zscore_upper
        self.exit_threshold_val = self.params.exit_threshold[0] if hasattr(self.params.exit_threshold, '__getitem__') else self.params.exit_threshold

    def notify_order(self, order):
        # (Identical to EMACrossoverStrategy's notify_order)
        if order.status in [order.Submitted, order.Accepted]:
            return
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
        self.order = None

    def notify_trade(self, trade):
        # (Identical to EMACrossoverStrategy's notify_trade)
        if not trade.isclosed:
            return
        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        # self.log(f'Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')

        # 检查是否有挂单
        if self.order:
            return

        # 检查 Z-score 是否有效 (指标需要预热期)
        # Backtrader 的指标会自动处理，但我们可以显式检查 NaN
        if pd.isna(self.zscore[0]):
             return

        # 检查是否持有仓位
        if not self.position:
            # 没有仓位，检查入场信号
            if self.zscore[0] < self.zscore_lower_val:
                self.log(f'BUY CREATE (Z < Lower), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                self.order = self.buy()
            # 如果允许做空，可以添加做空逻辑
            elif self.zscore[0] > self.zscore_upper_val:
                 self.log(f'SELL CREATE (Z > Upper), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                 self.order = self.sell() # 做空

        else:
            # 持有仓位，检查出场信号 (回归到均值)
            # 如果是多头仓位 (position.size > 0)
            if self.position.size > 0 and self.zscore[0] >= self.exit_threshold_val:
                self.log(f'CLOSE LONG (Z >= Exit), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                self.order = self.close() # 平多仓
            # 如果是空头仓位 (position.size < 0) 且允许做空
            elif self.position.size < 0 and self.zscore[0] <= self.exit_threshold_val:
                 self.log(f'CLOSE SHORT (Z <= Exit), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                 self.order = self.close() # 平空仓

# --- New Backtrader Strategy Definition: Custom Ratio (Short-Term Price / Long-Term Average) ---
class CustomRatioStrategy(bt.Strategy):
    params = (
        ('long_ma_period', range(40, 81, 10)), # 测试 40, 50, 60, 70, 80
        ('buy_threshold', [0.97, 0.98, 0.99]), # 测试 0.97, 0.98, 0.99
        ('sell_threshold', [1.01, 1.02, 1.03]),# 测试 1.01, 1.02, 1.03
        ('exit_threshold', [0.995, 1.0, 1.005]),# 测试 0.995, 1.0, 1.005
        ('use_filtered_price', False), # 是否使用滤波后的价格
        ('printlog', False),     # 是否打印交易日志
    )

    # --- 指标数学描述 ---
    # 自定义比率 (Custom Ratio):
    # 该策略计算当前价格与其长期移动平均值之间的比率。
    # 计算公式：
    # Ratio = Current Price / Long-Term Simple Moving Average (SMA)
    # 其中：
    # Current Price 是当前周期的收盘价 (self.data.close[0])
    # Long-Term SMA 是价格在指定周期 (params.long_ma_period) 内的滚动简单移动平均值
    #
    # 策略逻辑：
    # 当比率低于一个阈值 (params.buy_threshold) 时，表示当前价格相对于长期均值显著偏低，
    # 预期价格会回归均值（上涨），因此产生买入信号。
    # 当比率高于一个阈值 (params.sell_threshold) 时，表示当前价格相对于长期均值显著偏高，
    # 预期价格会回归均值（下跌），因此产生卖出（做空）信号。
    # 当价格回归到长期均值附近（比率接近 params.exit_threshold，通常为 1.0）时，平仓。
    # ---

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 计算长期移动平均线
        # Check if param is iterable (list/range) for optimization
        period = (self.params.long_ma_period[0]
                  if hasattr(self.params.long_ma_period, '__getitem__')
                  else self.params.long_ma_period)
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=period)

        # 解包阈值参数
        self.buy_threshold_val  = (self.params.buy_threshold[0]
                                   if hasattr(self.params.buy_threshold, '__getitem__')
                                   else self.params.buy_threshold)
        self.sell_threshold_val = (self.params.sell_threshold[0]
                                   if hasattr(self.params.sell_threshold, '__getitem__')
                                   else self.params.sell_threshold)
        self.exit_threshold_val = (self.params.exit_threshold[0]
                                   if hasattr(self.params.exit_threshold, '__getitem__')
                                   else self.params.exit_threshold)

        # 初始化比率变量 (将在 next 中计算)
        self.current_ratio = None

    def notify_order(self, order):
        # (Identical to other strategies' notify_order)
        if order.status in [order.Submitted, order.Accepted]:
            return
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
        self.order = None

    def notify_trade(self, trade):
        # (Identical to other strategies' notify_trade)
        if not trade.isclosed:
            return
        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        # 检查是否有挂单
        if self.order:
            return

        # 检查长期 MA 是否有效且不为零
        if len(self.long_ma) == 0 or pd.isna(self.long_ma[0]) or self.long_ma[0] == 0:
            return # 等待指标预热或避免除以零

        # 计算当前比率
        self.current_ratio = self.dataclose[0] / self.long_ma[0]
        # self.log(f'Close: {self.dataclose[0]:.2f}, Long MA: {self.long_ma[0]:.2f}, Ratio: {self.current_ratio:.4f}')

        # 检查是否持有仓位
        if not self.position:
            # 没有仓位，检查入场信号
            # 使用解包后的标量值进行比较
            if self.current_ratio < self.buy_threshold_val:
                self.log(f'BUY CREATE (Ratio < Buy Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                self.order = self.buy()
            # 如果允许做空，可以添加做空逻辑
            # 使用解包后的标量值进行比较
            elif self.current_ratio > self.sell_threshold_val:
                 self.log(f'SELL CREATE (Ratio > Sell Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                 self.order = self.sell() # 做空

        else:
            # 持有仓位，检查出场信号 (回归到均值)
            # 如果是多头仓位 (position.size > 0)
            # 使用解包后的标量值进行比较
            if self.position.size > 0 and self.current_ratio >= self.exit_threshold_val:
                self.log(f'CLOSE LONG (Ratio >= Exit Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                self.order = self.close() # 平多仓
            # 如果是空头仓位 (position.size < 0) 且允许做空
            # 使用解包后的标量值进行比较
            elif self.position.size < 0 and self.current_ratio <= self.exit_threshold_val:
                 self.log(f'CLOSE SHORT (Ratio <= Exit Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                 self.order = self.close() # 平空仓

# --- Custom PandasData Class ---
class PandasDataFiltered(bt.feeds.PandasData):
    lines = ('filtered_close',)
    params = (
        ('filtered_close', 7), # Default column index for filtered_close
    )
    datafields = bt.feeds.PandasData.datafields + ['filtered_close']
