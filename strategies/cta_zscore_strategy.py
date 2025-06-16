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
import numpy as np


class ZScoreStrategy(CtaTemplate):
    """
    Z-Score均值回归策略
    
    基于原有的LiveMeanReversionStrategy迁移而来，使用Z-Score指标
    识别价格偏离均值的程度，在极值时进行反向交易。
    
    策略逻辑：
    1. 计算价格的移动平均和标准差
    2. 计算Z-Score = (当前价格 - 移动平均) / 标准差
    3. 当Z-Score < 下阈值时买入（价格被低估）
    4. 当Z-Score > 上阈值时卖出/做空（价格被高估）
    5. 当Z-Score回归到退出阈值时平仓
    """
    
    author = "PATF Trading Framework"
    
    # 策略参数
    zscore_period: int = 20         # Z-Score计算周期
    zscore_upper: float = 2.0       # Z-Score上阈值
    zscore_lower: float = -2.0      # Z-Score下阈值
    exit_threshold: float = 0.0     # 退出阈值
    fixed_size: int = 100           # 固定交易数量
    
    # 策略变量
    zscore_value: float = 0.0       # 当前Z-Score值
    price_mean: float = 0.0         # 价格均值
    price_std: float = 0.0          # 价格标准差
    signal_type: str = "HOLD"       # 当前信号类型
    
    # 参数列表，用于图形界面显示和参数优化
    parameters = [
        "zscore_period",
        "zscore_upper",
        "zscore_lower",
        "exit_threshold",
        "fixed_size"
    ]
    
    # 变量列表，用于图形界面显示和状态保存
    variables = [
        "zscore_value",
        "price_mean",
        "price_std",
        "signal_type"
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
        self.write_log("Z-Score均值回归策略初始化")
        
        # 加载历史数据用于指标计算
        # 需要足够的数据来计算Z-Score
        history_days = self.zscore_period + 10
        self.load_bar(history_days)
        
    def on_start(self):
        """
        策略启动回调函数
        """
        self.write_log("Z-Score均值回归策略启动")
        
    def on_stop(self):
        """
        策略停止回调函数
        """
        self.write_log("Z-Score均值回归策略停止")
        
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
            
        # 计算Z-Score指标
        self._calculate_zscore()
        
        # 生成交易信号
        self._generate_signals()
        
        # 执行交易逻辑
        self._execute_trading_logic(bar)
        
        # 更新图形界面显示
        self.put_event()
        
    def _calculate_zscore(self):
        """
        计算Z-Score指标
        """
        # 获取收盘价数组
        close_array = self.am.close_array
        
        if len(close_array) < self.zscore_period:
            return
            
        # 计算最近N期的均值和标准差
        recent_prices = close_array[-self.zscore_period:]
        self.price_mean = np.mean(recent_prices)
        self.price_std = np.std(recent_prices)
        
        # 避免标准差为0的情况
        if self.price_std < 1e-6:
            self.zscore_value = 0.0
            self.write_log(f"警告：标准差过小({self.price_std:.6f})，Z-Score设为0")
            return
            
        # 计算当前价格的Z-Score
        current_price = close_array[-1]
        self.zscore_value = (current_price - self.price_mean) / self.price_std
        
    def _generate_signals(self):
        """
        生成交易信号
        """
        # 获取当前持仓
        current_pos = self.pos
        
        # 重置信号
        self.signal_type = "HOLD"
        
        # 如果Z-Score无效，不生成信号
        if self.price_std < 1e-6:
            return
            
        # 持有多头仓位时的信号判断
        if current_pos > 0:
            if self.zscore_value >= self.exit_threshold:
                self.signal_type = "CLOSE_LONG"
                self.write_log(
                    f"平多信号: Z-Score={self.zscore_value:.2f} >= 退出阈值{self.exit_threshold}, "
                    f"持仓={current_pos}"
                )
                
        # 持有空头仓位时的信号判断
        elif current_pos < 0:
            if self.zscore_value <= self.exit_threshold:
                self.signal_type = "CLOSE_SHORT"
                self.write_log(
                    f"平空信号: Z-Score={self.zscore_value:.2f} <= 退出阈值{self.exit_threshold}, "
                    f"持仓={current_pos}"
                )
                
        # 无仓位时的信号判断
        else:
            if self.zscore_value < self.zscore_lower:
                self.signal_type = "BUY"
                self.write_log(
                    f"买入信号: Z-Score={self.zscore_value:.2f} < 下阈值{self.zscore_lower}"
                )
            elif self.zscore_value > self.zscore_upper:
                self.signal_type = "SELL"
                self.write_log(
                    f"卖出信号: Z-Score={self.zscore_value:.2f} > 上阈值{self.zscore_upper}"
                )
                
    def _execute_trading_logic(self, bar: BarData):
        """
        执行交易逻辑
        """
        current_pos = self.pos
        
        # 执行买入
        if self.signal_type == "BUY" and current_pos == 0:
            self.write_log(
                f"执行买入: 价格={bar.close_price:.2f}, 数量={self.fixed_size}, "
                f"Z-Score={self.zscore_value:.2f}"
            )
            self.buy(bar.close_price, self.fixed_size)
            
        # 执行卖出/做空
        elif self.signal_type == "SELL" and current_pos == 0:
            self.write_log(
                f"执行做空: 价格={bar.close_price:.2f}, 数量={self.fixed_size}, "
                f"Z-Score={self.zscore_value:.2f}"
            )
            self.short(bar.close_price, self.fixed_size)
            
        # 平多头仓位
        elif self.signal_type == "CLOSE_LONG" and current_pos > 0:
            self.write_log(
                f"平多仓位: 价格={bar.close_price:.2f}, 数量={abs(current_pos)}, "
                f"Z-Score={self.zscore_value:.2f}"
            )
            self.sell(bar.close_price, abs(current_pos))
            
        # 平空头仓位
        elif self.signal_type == "CLOSE_SHORT" and current_pos < 0:
            self.write_log(
                f"平空仓位: 价格={bar.close_price:.2f}, 数量={abs(current_pos)}, "
                f"Z-Score={self.zscore_value:.2f}"
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
        
        # 计算当前盈亏
        if self.pos != 0:
            pnl = self.pos * (trade.price - self.price_mean)
            self.write_log(f"当前持仓盈亏: {pnl:.2f}")
            
        # 更新图形界面
        self.put_event()
        
    def on_stop_order(self, stop_order: StopOrder):
        """
        停止单状态更新回调函数
        """
        self.write_log(
            f"停止单回报: {stop_order.vt_orderid}, 状态: {stop_order.status.value}"
        )
        
    def get_strategy_stats(self) -> Dict[str, Any]:
        """
        获取策略统计信息
        """
        return {
            "zscore_value": self.zscore_value,
            "price_mean": self.price_mean,
            "price_std": self.price_std,
            "signal_type": self.signal_type,
            "position": self.pos,
            "zscore_upper": self.zscore_upper,
            "zscore_lower": self.zscore_lower,
            "exit_threshold": self.exit_threshold
        }