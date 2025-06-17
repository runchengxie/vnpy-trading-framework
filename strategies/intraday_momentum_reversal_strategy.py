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
    Intraday Momentum Reversal Strategy
    
    This is an intraday momentum reversal strategy that does not hold overnight positions.
    The core idea is to wait for the first signal of momentum exhaustion after the market
    shows extreme sentiment (overbought/oversold), and then enter the market to capture
    the profit from the price reversal.
    
    Strategy Logic:
    1. Use RSI(6) and KDJ(9,3,3) indicators to identify overbought and oversold states.
    2. Monitor for momentum exhaustion signals in extreme states.
    3. Adjust position size based on the current price relative to the opening price.
    4. Strictly intraday trading, no overnight positions are held.
    """
    
    author = "PATF Trading Framework"
    
    # Strategy Parameters
    rsi_period: int = 6             # RSI period
    kdj_period: int = 9             # KDJ period
    kdj_smooth_k: int = 3           # KDJ K-line smoothing period
    kdj_smooth_d: int = 3           # KDJ D-line smoothing period
    rsi_overbought: float = 80.0    # RSI overbought threshold
    rsi_oversold: float = 20.0      # RSI oversold threshold
    kdj_overbought: float = 100.0   # KDJ overbought threshold
    kdj_oversold: float = 0.0       # KDJ oversold threshold
    position_size_high: float = 0.3 # High position ratio (30%)
    position_size_low: float = 0.1  # Low position ratio (10%)
    
    # Strategy Variables
    rsi_value: float = 0.0          # Current RSI value
    kdj_k: float = 0.0              # KDJ K value
    kdj_d: float = 0.0              # KDJ D value
    kdj_j: float = 0.0              # KDJ J value
    last_rsi: float = 0.0           # Previous RSI value
    last_kdj_j: float = 0.0         # Previous KDJ J value
    open_price: float = 0.0         # Today's open price
    monitoring_long: bool = False   # Long monitoring status
    monitoring_short: bool = False  # Short monitoring status
    current_date: str = ""          # Current date
    
    # Parameter List
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
    
    # Variable List
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
        Constructor
        """
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        # Array manager for calculating technical indicators
        self.am = ArrayManager()
        
    def on_init(self):
        """
        Callback function for strategy initialization
        """
        self.write_log("Intraday Momentum Reversal Strategy initialized")
        
        # Load historical data for indicator calculation
        history_days = max(self.rsi_period, self.kdj_period) + 10
        self.load_bar(history_days)
        
    def on_start(self):
        """
        Callback function for strategy start
        """
        self.write_log("Intraday Momentum Reversal Strategy started")
        
    def on_stop(self):
        """
        Callback function for strategy stop
        """
        self.write_log("Intraday Momentum Reversal Strategy stopped")
        
    def on_tick(self, tick: TickData):
        """
        Callback function for tick data push
        """
        # Bar-based strategy, does not process tick data
        pass
        
    def on_bar(self, bar: BarData):
        """
        Callback function for bar data push
        """
        # Update the array manager
        self.am.update_bar(bar)
        if not self.am.inited:
            return
            
        # Check if it is a new trading day
        current_date = bar.datetime.strftime("%Y-%m-%d")
        if current_date != self.current_date:
            self.current_date = current_date
            self.open_price = bar.open_price
            # New trading day starts, close all positions (intraday strategy)
            if self.pos != 0:
                self.close_all_positions()
            # Reset monitoring status
            self.monitoring_long = False
            self.monitoring_short = False
            
        # Calculate technical indicators
        self.calculate_indicators()
        
        # Execute trading logic
        self.execute_trading_logic(bar)
        
        # Update previous indicator values
        self.last_rsi = self.rsi_value
        self.last_kdj_j = self.kdj_j
        
        # Synchronize data to the UI
        self.put_event()
        
    def calculate_indicators(self):
        """
        Calculate technical indicators
        """
        # Calculate RSI
        self.rsi_value = self.am.rsi(self.rsi_period)
        
        # Calculate KDJ
        kdj_k, kdj_d = self.am.kd(self.kdj_period, self.kdj_smooth_k, self.kdj_smooth_d)
        self.kdj_k = kdj_k
        self.kdj_d = kdj_d
        self.kdj_j = 3 * kdj_k - 2 * kdj_d
        
    def execute_trading_logic(self, bar: BarData):
        """
        Execute trading logic
        """
        current_price = bar.close_price
        
        # Check exit conditions
        self.check_exit_conditions()
        
        # Check monitoring conditions
        self.check_monitoring_conditions()
        
        # Execute entry logic
        if self.pos == 0:  # Only open positions when there is no current position
            # Check long entry signal
            if self.monitoring_long and self.check_long_entry_signal():
                size = self.calculate_position_size(current_price, "LONG")
                self.buy(current_price, size)
                self.monitoring_long = False
                self.write_log(f"Open long position: Price={current_price}, Size={size}")
                
            # Check short entry signal
            elif self.monitoring_short and self.check_short_entry_signal():
                size = self.calculate_position_size(current_price, "SHORT")
                self.short(current_price, size)
                self.monitoring_short = False
                self.write_log(f"Open short position: Price={current_price}, Size={size}")
                
    def check_monitoring_conditions(self):
        """
        Check conditions for entering monitoring state
        """
        # Long monitoring condition: RSI < 20 and KDJ J < 0
        if (self.rsi_value < self.rsi_oversold and 
            self.kdj_j < self.kdj_oversold and 
            not self.monitoring_long):
            self.monitoring_long = True
            self.write_log(f"Entering long monitoring state: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
            
        # Short monitoring condition: RSI > 80 and KDJ J > 100
        if (self.rsi_value > self.rsi_overbought and 
            self.kdj_j > self.kdj_overbought and 
            not self.monitoring_short):
            self.monitoring_short = True
            self.write_log(f"Entering short monitoring state: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
            
    def check_long_entry_signal(self) -> bool:
        """
        Check for long entry signal
        """
        # RSI is rising or KDJ J is rising
        rsi_rising = self.rsi_value > self.last_rsi
        kdj_j_rising = self.kdj_j > self.last_kdj_j
        
        return rsi_rising or kdj_j_rising
        
    def check_short_entry_signal(self) -> bool:
        """
        Check for short entry signal
        """
        # RSI is falling or KDJ J is falling
        rsi_falling = self.rsi_value < self.last_rsi
        kdj_j_falling = self.kdj_j < self.last_kdj_j
        
        return rsi_falling or kdj_j_falling
        
    def check_exit_conditions(self):
        """
        Check exit conditions
        """
        if self.pos > 0:  # Holding a long position
            # Long exit condition: RSI > 80 or KDJ J > 100
            if (self.rsi_value > self.rsi_overbought or 
                self.kdj_j > self.kdj_overbought):
                self.sell(self.am.close[-1], abs(self.pos))
                self.write_log(f"Closing long position: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
                
        elif self.pos < 0:  # Holding a short position
            # Short exit condition: RSI < 20 or KDJ J < 0
            if (self.rsi_value < self.rsi_oversold or 
                self.kdj_j < self.kdj_oversold):
                self.cover(self.am.close[-1], abs(self.pos))
                self.write_log(f"Closing short position: RSI={self.rsi_value:.2f}, KDJ_J={self.kdj_j:.2f}")
                
    def calculate_position_size(self, current_price: float, direction: str) -> int:
        """
        Calculate position size
        """
        # Get account funds (using a simplified calculation here)
        account_value = 100000  # Assuming account value is 100,000
        
        if direction == "LONG":
            # Long: Use 30% if price >= open price, 10% if price < open price
            if current_price >= self.open_price:
                position_ratio = self.position_size_high
            else:
                position_ratio = self.position_size_low
        else:  # SHORT
            # Short: Use 10% if price >= open price, 30% if price < open price
            if current_price >= self.open_price:
                position_ratio = self.position_size_low
            else:
                position_ratio = self.position_size_high
                
        position_value = account_value * position_ratio
        size = int(position_value / current_price)
        
        return max(size, 1)  # At least 1 lot/contract
        
    def close_all_positions(self):
        """
        Close all positions
        """
        if self.pos > 0:
            self.sell(self.am.close[-1], self.pos)
        elif self.pos < 0:
            self.cover(self.am.close[-1], abs(self.pos))
            
    def on_order(self, order: OrderData):
        """
        Callback function for order status update
        """
        pass
        
    def on_trade(self, trade: TradeData):
        """
        Callback function for trade data push
        """
        self.put_event()
        
    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback function for stop order status update
        """
        pass