from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    ArrayManager,
)
from vnpy.trader.constant import Interval
from typing import Dict, Any


class EmaAdxStrategy(CtaTemplate):
    """
    EMA交叉与ADX趋势确认策略
    
    基于原有的EMACrossoverStrategy迁移而来，使用EMA交叉信号
    结合ADX指标确认趋势强度，提高信号质量。
    
    策略逻辑：
    1. 计算短期和长期EMA
    2. 计算ADX指标确认趋势强度
    3. 当短期EMA上穿长期EMA且ADX>阈值时买入
    4. 当短期EMA下穿长期EMA时卖出
    """
    
    author = "PATF Trading Framework"
    
    # 策略参数
    ema_short_period: int = 12      # 短期EMA周期
    ema_long_period: int = 26       # 长期EMA周期
    adx_period: int = 14            # ADX周期
    adx_threshold: float = 25.0     # ADX阈值
    fixed_size: int = 100           # 固定交易数量
    
    # 策略变量
    ema_short_value: float = 0.0    # 短期EMA值
    ema_long_value: float = 0.0     # 长期EMA值
    adx_value: float = 0.0          # ADX值
    crossover_signal: int = 0       # 交叉信号：1=金叉，-1=死叉，0=无信号
    
    # 参数列表，用于图形界面显示和参数优化
    parameters = [
        "ema_short_period",
        "ema_long_period", 
        "adx_period",
        "adx_threshold",
        "fixed_size"
    ]
    
    # 变量列表，用于图形界面显示和状态保存
    variables = [
        "ema_short_value",
        "ema_long_value",
        "adx_value",
        "crossover_signal"
    ]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """
        构造函数
        """
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        # 数组管理器，用于计算技术指标
        self.am = ArrayManager()
        
        # 上一根K线的EMA值，用于判断交叉
        self.last_ema_short = 0.0
        self.last_ema_long = 0.0
        
    def on_init(self):
        """
        策略初始化回调函数
        """
        self.write_log("策略初始化")
        
        # 加载历史数据用于指标计算
        # 需要足够的数据来计算最长周期的指标
        history_days = max(self.ema_long_period, self.adx_period) + 10
        self.load_bar(history_days)
        
    def on_start(self):
        """
        策略启动回调函数
        """
        self.write_log("策略启动")
        
    def on_stop(self):
        """
        策略停止回调函数
        """
        self.write_log("策略停止")
        
    def on_tick(self, tick: TickData):
        """
        Tick数据推送回调函数
        """
        # 基于K线的策略，不处理tick数据
        pass
        
    def on_bar(self, bar: BarData):
        """
        K线数据推送回调函数
        """
        # 更新数组管理器
        self.am.update_bar(bar)
        
        # 如果数据不足，直接返回
        if not self.am.inited:
            return
            
        # 计算技术指标
        self._calculate_indicators()
        
        # 生成交易信号
        self._generate_signals()
        
        # 执行交易逻辑
        self._execute_trading_logic(bar)
        
        # 更新图形界面显示
        self.put_event()
        
    def _calculate_indicators(self):
        """
        计算技术指标
        """
        # 保存上一根K线的EMA值
        self.last_ema_short = self.ema_short_value
        self.last_ema_long = self.ema_long_value
        
        # 计算EMA
        ema_short_array = self.am.ema(self.ema_short_period, array=True)
        ema_long_array = self.am.ema(self.ema_long_period, array=True)
        
        self.ema_short_value = ema_short_array[-1]
        self.ema_long_value = ema_long_array[-1]
        
        # 计算ADX
        adx_array = self.am.adx(self.adx_period, array=True)
        self.adx_value = adx_array[-1]
        
    def _generate_signals(self):
        """
        生成交易信号
        """
        # 重置信号
        self.crossover_signal = 0
        
        # 检查是否有足够的历史数据
        if self.last_ema_short == 0 or self.last_ema_long == 0:
            return
            
        # 检测金叉：短期EMA从下方穿越长期EMA
        if (self.last_ema_short <= self.last_ema_long and 
            self.ema_short_value > self.ema_long_value):
            self.crossover_signal = 1
            self.write_log(f"检测到金叉信号: EMA_Short={self.ema_short_value:.2f}, EMA_Long={self.ema_long_value:.2f}")
            
        # 检测死叉：短期EMA从上方穿越长期EMA
        elif (self.last_ema_short >= self.last_ema_long and 
              self.ema_short_value < self.ema_long_value):
            self.crossover_signal = -1
            self.write_log(f"检测到死叉信号: EMA_Short={self.ema_short_value:.2f}, EMA_Long={self.ema_long_value:.2f}")
            
    def _execute_trading_logic(self, bar: BarData):
        """
        执行交易逻辑
        """
        # 获取当前持仓
        current_pos = self.pos
        
        # 买入信号：金叉且ADX确认趋势强度
        if (self.crossover_signal == 1 and 
            self.adx_value > self.adx_threshold and 
            current_pos == 0):
            
            self.write_log(
                f"买入信号触发: ADX={self.adx_value:.2f} > {self.adx_threshold}, "
                f"价格={bar.close_price:.2f}"
            )
            self.buy(bar.close_price, self.fixed_size)
            
        # 卖出信号：死叉
        elif self.crossover_signal == -1 and current_pos > 0:
            self.write_log(
                f"卖出信号触发: 价格={bar.close_price:.2f}, 持仓={current_pos}"
            )
            self.sell(bar.close_price, abs(current_pos))
            
        # 做空信号：死叉且ADX确认趋势强度（如果允许做空）
        elif (self.crossover_signal == -1 and 
              self.adx_value > self.adx_threshold and 
              current_pos == 0):
            
            self.write_log(
                f"做空信号触发: ADX={self.adx_value:.2f} > {self.adx_threshold}, "
                f"价格={bar.close_price:.2f}"
            )
            self.short(bar.close_price, self.fixed_size)
            
        # 平空信号：金叉
        elif self.crossover_signal == 1 and current_pos < 0:
            self.write_log(
                f"平空信号触发: 价格={bar.close_price:.2f}, 持仓={current_pos}"
            )
            self.cover(bar.close_price, abs(current_pos))
            
    def on_order(self, order: OrderData):
        """
        委托状态更新回调函数
        """
        self.write_log(
            f"委托回报: {order.vt_orderid}, 状态: {order.status.value}, "
            f"方向: {order.direction.value}, 价格: {order.price}, 数量: {order.volume}"
        )
        
    def on_trade(self, trade: TradeData):
        """
        成交数据推送回调函数
        """
        self.write_log(
            f"成交回报: {trade.vt_tradeid}, 方向: {trade.direction.value}, "
            f"价格: {trade.price}, 数量: {trade.volume}, 时间: {trade.datetime}"
        )
        
        # 更新图形界面
        self.put_event()
        
    def on_stop_order(self, stop_order: StopOrder):
        """
        停止单状态更新回调函数
        """
        self.write_log(
            f"停止单回报: {stop_order.vt_orderid}, 状态: {stop_order.status.value}"
        )