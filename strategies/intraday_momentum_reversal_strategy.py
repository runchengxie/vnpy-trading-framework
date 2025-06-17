from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    ArrayManager,
)
from vnpy.trader.constant import Interval, Direction, Offset
from typing import Dict, Any
import numpy as np


class IntradayMomentumReversalStrategy(CtaTemplate):
    """
    日内动量反转策略
    
    该策略是一个日内动量反转策略，不持有隔夜仓位。核心思想是在市场出现
    极端情绪（超买/超卖）后，等待动量衰竭的第一个信号入场，捕捉价格反转的利润。
    
    策略逻辑：
    1. 使用RSI(6)和KDJ(9,3,3)指标识别超买超卖状态
    2. 在极端状态下监控动量衰竭信号
    3. 根据当前价格相对于开盘价调整仓位大小
    4. 严格的日内交易，不持有隔夜仓位
    """
    
    author = "PATF Trading Framework"
    
    # 策略参数
    rsi_period: int = 6             # RSI周期
    kdj_period: int = 9             # KDJ周期
    kdj_smooth_k: int = 3           # KDJ K线平滑周期
    kdj_smooth_d: int = 3           # KDJ D线平滑周期
    rsi_overbought: float = 80.0    # RSI超买阈值
    rsi_oversold: float = 20.0      # RSI超卖阈值
    kdj_overbought: float = 100.0   # KDJ超买阈值
    kdj_oversold: float = 0.0       # KDJ超卖阈值
    position_size_high: float = 0.3 # 高仓位比例（30%）
    position_size_low: float = 0.1  # 低仓位比例（10%）
    
    # 策略变量
    rsi_value: float = 0.0          # 当前RSI值
    kdj_k: float = 0.0              # KDJ K值
    kdj_d: float = 0.0              # KDJ D值
    kdj_j: float = 0.0              # KDJ J值
    last_rsi: float = 0.0           # 上一个RSI值
    last_kdj_j: float = 0.0         # 上一个KDJ J值
    open_price: float = 0.0         # 当日开盘价
    monitoring_long: bool = False   # 做多监控状态
    monitoring_short: bool = False  # 做空监控状态
    current_date: str = ""          # 当前日期
    
    # 参数列表
    parameters = [
        "rsi_period",
        "kdj_period",
        "kdj_smooth_k",
        "kdj_smooth_d",
        "rsi_overbought",
        "rsi_oversold",
        "kdj_overbought",
        "kdj_oversold",
        "position_size_high",
        "position_size_low"
    ]
    
    # 变量列表
    variables = [
        "rsi_value",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "open_price",
        "monitoring_long",
        "monitoring_short"
    ]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """
        构造函数
        """
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        # 数组管理器，用于计算技术指标
        self.am = ArrayManager()
        
    def on_init(self):
        """
        策略初始化回调函数
        """
        self.write_log("日内动量反转策略初始化")
        
        # 加载历史数据用于指标计算
        history_days = max(self.rsi_period, self.kdj_period) + 10
        self.load_bar(history_days)
        
    def on_start(self):
        """
        策略启动回调函数
        """
        self.write_log("日内动量反转策略启动")
        
    def on_stop(self):
        """
        策略停止回调函数
        """
        self.write_log("日内动量反转策略停止")
        
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
        if not self.am.inited:
            return
            
        # 检查是否是新的交易日
        current_date = bar.datetime.strftime("%Y-%m-%d")
        if current_date != self.current_date:
            self.current_date = current_date
            self.open_price = bar.open_price
            # 新交易日开始，平掉所有仓位（日内策略）
            if self.pos != 0:
                self.close_all_positions()
            # 重置监控状态
            self.monitoring_long = False
            self.monitoring_short = False
            
        # 计算技术指标
        self.calculate_indicators()
        
        # 执行交易逻辑
        self.execute_trading_logic(bar)
        
        # 更新上一个指标值
        self.last_rsi = self.rsi_value
        self.last_kdj_j = self.kdj_j
        
        # 同步数据到界面
        self.put_event()
        
    def calculate_indicators(self):
        """
        计算技术指标
        """
        # 计算RSI
        self.rsi_value = self.am.rsi(self.rsi_period)
        
        # 计算KDJ
        kdj_k, kdj_d = self.am.kd(self.kdj_period, self.kdj_smooth_k, self.kdj_smooth_d)
        self.kdj_k = kdj_k
        self.kdj_d = kdj_d
        self.kdj_j = 3 * kdj_k - 2 * kdj_d
        
    def execute_trading_logic(self, bar: BarData):
        """
        执行交易逻辑
        """
        current_price = bar.close_price
        
        # 检查平仓条件
        self.check_exit_conditions()
        
        # 检查监控状态
        self.check_monitoring_conditions()
        
        # 执行开仓逻辑
        if self.pos == 0:  # 无仓位时才开仓
            # 做多信号检查
            if self.monitoring_long and self.check_long_entry_signal():
                size = self.calculate_position_size(current_price, "LONG")
                self.buy(current_price, size)
                self.monitoring_long = False
                self.write_log(f"做多开仓: 价格={current_price}, 数量={size}")
                
            # 做空信号检查
            elif self.monitoring_short and self.check_short_entry_signal():
                size = self.calculate_position_size(current_price, "SHORT")
                self.short(current_price, size)
                self.monitoring_short = False
                self.write_log(f"做空开仓: 价格={current_price}, 数量={size}")
                
    def check_monitoring_conditions(self):
        """
        检查进入监控状态的条件
        """
        # 做多监控条件：RSI < 20 且 KDJ J < 0
        if (self.rsi_value < self.rsi_oversold and 
            self.kdj_j < self.kdj_oversold and 
            not self.monitoring_long):
            self.monitoring_long = True
            self.write_log(f"进入做多监控状态: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
            
        # 做空监控条件：RSI > 80 且 KDJ J > 100
        if (self.rsi_value > self.rsi_overbought and 
            self.kdj_j > self.kdj_overbought and 
            not self.monitoring_short):
            self.monitoring_short = True
            self.write_log(f"进入做空监控状态: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
            
    def check_long_entry_signal(self) -> bool:
        """
        检查做多入场信号
        """
        # RSI上升或KDJ J上升
        rsi_rising = self.rsi_value > self.last_rsi
        kdj_j_rising = self.kdj_j > self.last_kdj_j
        
        return rsi_rising or kdj_j_rising
        
    def check_short_entry_signal(self) -> bool:
        """
        检查做空入场信号
        """
        # RSI下降或KDJ J下降
        rsi_falling = self.rsi_value < self.last_rsi
        kdj_j_falling = self.kdj_j < self.last_kdj_j
        
        return rsi_falling or kdj_j_falling
        
    def check_exit_conditions(self):
        """
        检查平仓条件
        """
        if self.pos > 0:  # 持有多头仓位
            # 多头平仓条件：RSI > 80 或 KDJ J > 100
            if (self.rsi_value > self.rsi_overbought or 
                self.kdj_j > self.kdj_overbought):
                self.sell(self.am.close[-1], abs(self.pos))
                self.write_log(f"多头平仓: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
                
        elif self.pos < 0:  # 持有空头仓位
            # 空头平仓条件：RSI < 20 或 KDJ J < 0
            if (self.rsi_value < self.rsi_oversold or 
                self.kdj_j < self.kdj_oversold):
                self.cover(self.am.close[-1], abs(self.pos))
                self.write_log(f"空头平仓: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
                
    def calculate_position_size(self, current_price: float, direction: str) -> int:
        """
        计算仓位大小
        """
        # 获取账户资金（这里使用简化计算）
        account_value = 100000  # 假设账户价值10万
        
        if direction == "LONG":
            # 做多：价格>=开盘价用30%，价格<开盘价用10%
            if current_price >= self.open_price:
                position_ratio = self.position_size_high
            else:
                position_ratio = self.position_size_low
        else:  # SHORT
            # 做空：价格>=开盘价用10%，价格<开盘价用30%
            if current_price >= self.open_price:
                position_ratio = self.position_size_low
            else:
                position_ratio = self.position_size_high
                
        position_value = account_value * position_ratio
        size = int(position_value / current_price)
        
        return max(size, 1)  # 至少1手
        
    def close_all_positions(self):
        """
        平掉所有仓位
        """
        if self.pos > 0:
            self.sell(self.am.close[-1], self.pos)
        elif self.pos < 0:
            self.cover(self.am.close[-1], abs(self.pos))
            
    def on_order(self, order: OrderData):
        """
        委托状态更新回调函数
        """
        pass
        
    def on_trade(self, trade: TradeData):
        """
        成交数据推送回调函数
        """
        self.put_event()
        
    def on_stop_order(self, stop_order: StopOrder):
        """
        停止单状态更新回调函数
        """
        pass