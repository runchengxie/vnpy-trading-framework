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


class CustomRatioStrategy(CtaTemplate):
    """
    自定义比率趋势策略
    
    基于项目需求文档中的比率指标设计，通过短期价格与长期均价的比率
    来识别趋势信号。这是一个简单但实用的趋势指标。
    
    策略逻辑：
    1. 将价格按短期间隔重采样（如30秒）
    2. 计算长期平均价格（如5分钟）
    3. 计算比率 = 短期价格 / 长期平均价格
    4. 比率接近1表示无趋势，>1表示上涨趋势，<1表示下跌趋势
    5. 当比率偏离1超过阈值时开仓，回归时平仓
    """
    
    author = "PATF Trading Framework"
    
    # 策略参数
    short_period: int = 5           # 短期均价周期（分钟）
    long_period: int = 20           # 长期均价周期（分钟）
    ratio_upper: float = 1.02       # 比率上阈值（买入信号）
    ratio_lower: float = 0.98       # 比率下阈值（卖出信号）
    exit_ratio: float = 1.00        # 退出比率阈值
    fixed_size: int = 100           # 固定交易数量
    
    # 策略变量
    short_ma: float = 0.0           # 短期移动平均
    long_ma: float = 0.0            # 长期移动平均
    price_ratio: float = 1.0        # 价格比率
    trend_signal: str = "NEUTRAL"   # 趋势信号
    
    # 参数列表，用于图形界面显示和参数优化
    parameters = [
        "short_period",
        "long_period",
        "ratio_upper",
        "ratio_lower",
        "exit_ratio",
        "fixed_size"
    ]
    
    # 变量列表，用于图形界面显示和状态保存
    variables = [
        "short_ma",
        "long_ma",
        "price_ratio",
        "trend_signal"
    ]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """
        构造函数
        """
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        # 数组管理器，用于计算技术指标
        self.am = ArrayManager()
        
        # 上一个比率值，用于判断趋势变化
        self.last_ratio = 1.0
        
    def on_init(self):
        """
        策略初始化回调函数
        """
        self.write_log("自定义比率趋势策略初始化")
        
        # 加载历史数据用于指标计算
        # 需要足够的数据来计算长期移动平均
        history_days = max(self.short_period, self.long_period) + 10
        self.load_bar(history_days)
        
    def on_start(self):
        """
        策略启动回调函数
        """
        self.write_log("自定义比率趋势策略启动")
        
    def on_stop(self):
        """
        策略停止回调函数
        """
        self.write_log("自定义比率趋势策略停止")
        
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
            
        # 计算比率指标
        self._calculate_ratio()
        
        # 生成交易信号
        self._generate_signals()
        
        # 执行交易逻辑
        self._execute_trading_logic(bar)
        
        # 更新图形界面显示
        self.put_event()
        
    def _calculate_ratio(self):
        """
        计算价格比率指标
        """
        # 获取收盘价数组
        close_array = self.am.close_array
        
        if len(close_array) < self.long_period:
            return
            
        # 计算短期和长期移动平均
        self.short_ma = np.mean(close_array[-self.short_period:])
        self.long_ma = np.mean(close_array[-self.long_period:])
        
        # 避免除零错误
        if self.long_ma < 1e-6:
            self.price_ratio = 1.0
            self.write_log(f"警告：长期均价过小({self.long_ma:.6f})，比率设为1.0")
            return
            
        # 计算价格比率
        self.last_ratio = self.price_ratio
        self.price_ratio = self.short_ma / self.long_ma
        
    def _generate_signals(self):
        """
        生成交易信号
        """
        # 获取当前持仓
        current_pos = self.pos
        
        # 重置信号
        self.trend_signal = "NEUTRAL"
        
        # 如果比率无效，不生成信号
        if self.long_ma < 1e-6:
            return
            
        # 持有多头仓位时的信号判断
        if current_pos > 0:
            # 比率回归到退出阈值附近时平仓
            if abs(self.price_ratio - self.exit_ratio) <= 0.005:  # 0.5%的容忍度
                self.trend_signal = "CLOSE_LONG"
                self.write_log(
                    f"平多信号: 比率={self.price_ratio:.4f} 回归到退出阈值{self.exit_ratio:.4f}, "
                    f"持仓={current_pos}"
                )
            # 比率转为下跌趋势时止损
            elif self.price_ratio < self.ratio_lower:
                self.trend_signal = "STOP_LONG"
                self.write_log(
                    f"多头止损: 比率={self.price_ratio:.4f} < 下阈值{self.ratio_lower:.4f}, "
                    f"持仓={current_pos}"
                )
                
        # 持有空头仓位时的信号判断
        elif current_pos < 0:
            # 比率回归到退出阈值附近时平仓
            if abs(self.price_ratio - self.exit_ratio) <= 0.005:  # 0.5%的容忍度
                self.trend_signal = "CLOSE_SHORT"
                self.write_log(
                    f"平空信号: 比率={self.price_ratio:.4f} 回归到退出阈值{self.exit_ratio:.4f}, "
                    f"持仓={current_pos}"
                )
            # 比率转为上涨趋势时止损
            elif self.price_ratio > self.ratio_upper:
                self.trend_signal = "STOP_SHORT"
                self.write_log(
                    f"空头止损: 比率={self.price_ratio:.4f} > 上阈值{self.ratio_upper:.4f}, "
                    f"持仓={current_pos}"
                )
                
        # 无仓位时的信号判断
        else:
            # 上涨趋势信号：比率显著大于1
            if self.price_ratio > self.ratio_upper:
                self.trend_signal = "UPTREND"
                self.write_log(
                    f"上涨趋势信号: 比率={self.price_ratio:.4f} > 上阈值{self.ratio_upper:.4f}"
                )
            # 下跌趋势信号：比率显著小于1
            elif self.price_ratio < self.ratio_lower:
                self.trend_signal = "DOWNTREND"
                self.write_log(
                    f"下跌趋势信号: 比率={self.price_ratio:.4f} < 下阈值{self.ratio_lower:.4f}"
                )
                
    def _execute_trading_logic(self, bar: BarData):
        """
        执行交易逻辑
        """
        current_pos = self.pos
        
        # 执行买入（上涨趋势）
        if self.trend_signal == "UPTREND" and current_pos == 0:
            self.write_log(
                f"执行买入: 价格={bar.close_price:.2f}, 数量={self.fixed_size}, "
                f"比率={self.price_ratio:.4f}"
            )
            self.buy(bar.close_price, self.fixed_size)
            
        # 执行卖出/做空（下跌趋势）
        elif self.trend_signal == "DOWNTREND" and current_pos == 0:
            self.write_log(
                f"执行做空: 价格={bar.close_price:.2f}, 数量={self.fixed_size}, "
                f"比率={self.price_ratio:.4f}"
            )
            self.short(bar.close_price, self.fixed_size)
            
        # 平多头仓位
        elif self.trend_signal in ["CLOSE_LONG", "STOP_LONG"] and current_pos > 0:
            action = "正常平仓" if self.trend_signal == "CLOSE_LONG" else "止损平仓"
            self.write_log(
                f"平多仓位({action}): 价格={bar.close_price:.2f}, 数量={abs(current_pos)}, "
                f"比率={self.price_ratio:.4f}"
            )
            self.sell(bar.close_price, abs(current_pos))
            
        # 平空头仓位
        elif self.trend_signal in ["CLOSE_SHORT", "STOP_SHORT"] and current_pos < 0:
            action = "正常平仓" if self.trend_signal == "CLOSE_SHORT" else "止损平仓"
            self.write_log(
                f"平空仓位({action}): 价格={bar.close_price:.2f}, 数量={abs(current_pos)}, "
                f"比率={self.price_ratio:.4f}"
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
        
        # 计算比率偏离度
        ratio_deviation = abs(self.price_ratio - 1.0) * 100
        self.write_log(f"当前比率偏离度: {ratio_deviation:.2f}%")
        
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
        ratio_deviation = abs(self.price_ratio - 1.0) * 100
        
        return {
            "short_ma": self.short_ma,
            "long_ma": self.long_ma,
            "price_ratio": self.price_ratio,
            "ratio_deviation_pct": ratio_deviation,
            "trend_signal": self.trend_signal,
            "position": self.pos,
            "ratio_upper": self.ratio_upper,
            "ratio_lower": self.ratio_lower,
            "exit_ratio": self.exit_ratio
        }