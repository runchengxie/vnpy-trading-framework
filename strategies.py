import backtrader as bt
import pandas as pd
import logging
import backtrader.indicators as btind  # Add indicators import

# --- Logging Setup ---
logger = logging.getLogger(__name__) # Create logger for this module
# --- End Logging Setup ---

# --- Backtrader Strategy Definition ---
class EMACrossoverStrategy(bt.Strategy):
    params = (
        ('ema_short', 12), # Renamed from ema_short_period
        ('ema_long', 26),  # Renamed from ema_long_period
        ('adx_period', 14),       # Example: Use precalculated ADX 14
        ('adx_threshold', [20.0, 25.0, 30.0]),
        ('use_filtered_price', False),
        ('printlog', False),
    )

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        # Use logger instead of print
        dt = dt or self.datas[0].datetime.date(0)
        log_level = logging.INFO if doprint or self.params.printlog else logging.DEBUG
        logger.log(log_level, f'{dt.isoformat()}, {txt}')

    def __init__(self):
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close

        # Dynamically calculate indicators using Backtrader's built-ins
        self.ema_short = btind.EMA(self.dataclose, period=self.params.ema_short)
        self.ema_long  = btind.EMA(self.dataclose, period=self.params.ema_long)
        self.adx       = btind.ADX(self.datas[0], period=self.params.adx_period) # ADX needs the full data feed

        self.crossover = bt.indicators.CrossOver(self.ema_short, self.ema_long)

        self.adx_threshold_val = self.params.adx_threshold[0] if hasattr(self.params.adx_threshold, '__getitem__') else self.params.adx_threshold

        self.order = None
        self.buyprice = None
        self.buycomm = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            self.log(f'Order {order.ref} Submitted/Accepted')
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            elif order.issell():
                self.buycomm = order.executed.comm
            elif order.issell():
                self.log(f'SELL EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order {order.ref} Canceled/Margin/Rejected')

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        if self.order:
            return

        if pd.isna(self.ema_short[0]) or pd.isna(self.ema_long[0]) or pd.isna(self.adx[0]):
            return

        if not self.position:
            if self.crossover > 0 and self.adx[0] > self.adx_threshold_val:
                self.log(f'BUY CREATE, Close: {self.dataclose[0]:.2f}, ADX: {self.adx[0]:.2f}')
                self.order = self.buy()

        else:
            if self.crossover < 0:
                self.log(f'SELL CREATE (Exit), Close: {self.dataclose[0]:.2f}, ADX: {self.adx[0]:.2f}')
                self.order = self.sell()

# --- New Backtrader Strategy Definition: Mean Reversion Z-Score -----
class MeanReversionZScoreStrategy(bt.Strategy):
    params = (
        ('zscore_period', 20), # Example: Use precalculated SMA 20 and STDEV 20
        ('zscore_upper', [1.5, 2.0, 2.5]),
        ('zscore_lower', [-1.5, -2.0, -2.5]),
        ('exit_threshold', [0.0, 0.25, -0.25]),
        ('use_filtered_price', True),
        ('printlog', False),
    )

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        # Use logger instead of print
        dt = dt or self.datas[0].datetime.date(0)
        log_level = logging.INFO if doprint or self.params.printlog else logging.DEBUG
        logger.log(log_level, f'{dt.isoformat()}, {txt}')

    def __init__(self):
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close

        period = self.p.zscore_period
        sma_line_name = f'sma_{period}'
        stdev_line_name = f'stdev_{period}'

        rolling_mean = getattr(self.datas[0].lines, sma_line_name)
        rolling_std = getattr(self.datas[0].lines, stdev_line_name)

        epsilon = 1e-6
        self.zscore = (self.dataclose - rolling_mean) / (rolling_std + epsilon)

        self.zscore_lower_val = self.params.zscore_lower[0] if hasattr(self.params.zscore_lower, '__getitem__') else self.params.zscore_lower
        self.zscore_upper_val = self.params.zscore_upper[0] if hasattr(self.params.zscore_upper, '__getitem__') else self.params.zscore_upper
        self.exit_threshold_val = self.params.exit_threshold[0] if hasattr(self.params.exit_threshold, '__getitem__') else self.params.exit_threshold

        self.order = None
        self.buyprice = None
        self.buycomm = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            self.log(f'Order {order.ref} Submitted/Accepted')
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            elif order.issell():
                self.log(f'SELL EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
            self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order {order.ref} Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        if self.order:
            return

        if pd.isna(self.zscore[0]):
             return

        if not self.position:
            if self.zscore[0] < self.zscore_lower_val:
                self.log(f'BUY CREATE (Z < Lower), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                self.order = self.buy()
            elif self.zscore[0] > self.zscore_upper_val:
                 self.log(f'SELL CREATE (Z > Upper), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                 self.order = self.sell()

        else:
            if self.position.size > 0 and self.zscore[0] >= self.exit_threshold_val:
                self.log(f'CLOSE LONG (Z >= Exit), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                self.order = self.close()
            elif self.position.size < 0 and self.zscore[0] <= self.exit_threshold_val:
                 self.log(f'CLOSE SHORT (Z <= Exit), Close: {self.dataclose[0]:.2f}, Z-Score: {self.zscore[0]:.2f}')
                 self.order = self.close()

# --- New Backtrader Strategy Definition: Custom Ratio (Short-Term Price / Long-Term Average) ---
class CustomRatioStrategy(bt.Strategy):
    params = (
        ('long_ma_period', 50), # Example: Use precalculated SMA 50
        ('buy_threshold', [0.97, 0.98, 0.99]),
        ('sell_threshold', [1.01, 1.02, 1.03]),
        ('exit_threshold', [0.995, 1.0, 1.005]),
        ('use_filtered_price', False),
        ('printlog', False),
    )

    def log(self, txt, dt=None, doprint=False):
        ''' 日志记录函数 '''
        # Use logger instead of print
        dt = dt or self.datas[0].datetime.date(0)
        log_level = logging.INFO if doprint or self.params.printlog else logging.DEBUG
        logger.log(log_level, f'{dt.isoformat()}, {txt}')

    def __init__(self):
        if self.params.use_filtered_price:
            self.dataclose = self.datas[0].filtered_close
        else:
            self.dataclose = self.datas[0].close

        period = self.params.long_ma_period
        sma_line_name = f'sma_{period}'
        self.long_ma = getattr(self.datas[0].lines, sma_line_name)

        self.buy_threshold_val  = (self.params.buy_threshold[0]
                                   if hasattr(self.params.buy_threshold, '__getitem__')
                                   else self.params.buy_threshold)
        self.sell_threshold_val = (self.params.sell_threshold[0]
                                   if hasattr(self.params.sell_threshold, '__getitem__')
                                   else self.params.sell_threshold)
        self.exit_threshold_val = (self.params.exit_threshold[0]
                                   if hasattr(self.params.exit_threshold, '__getitem__')
                                   else self.params.exit_threshold)

        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.current_ratio = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            self.log(f'Order {order.ref} Submitted/Accepted')
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f'BUY EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            elif order.issell():
                self.log(f'SELL EXECUTED, Ref: {order.ref}, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}', doprint=True)
            self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order {order.ref} Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f'OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        if self.order:
            return

        if pd.isna(self.long_ma[0]) or self.long_ma[0] == 0:
            return

        self.current_ratio = self.dataclose[0] / self.long_ma[0]

        if not self.position:
            if self.current_ratio < self.buy_threshold_val:
                self.log(f'BUY CREATE (Ratio < Buy Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                self.order = self.buy()
            elif self.current_ratio > self.sell_threshold_val:
                 self.log(f'SELL CREATE (Ratio > Sell Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                 self.order = self.sell()

        else:
            if self.position.size > 0 and self.current_ratio >= self.exit_threshold_val:
                self.log(f'CLOSE LONG (Ratio >= Exit Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                self.order = self.close()
            elif self.position.size < 0 and self.current_ratio <= self.exit_threshold_val:
                 self.log(f'CLOSE SHORT (Ratio <= Exit Thr), Close: {self.dataclose[0]:.2f}, Ratio: {self.current_ratio:.4f}')
                 self.order = self.close()

# --- Custom PandasData Class ---
class PandasDataFiltered(bt.feeds.PandasData):
    # Define only the new lines specific to this class
    lines = (
        'filtered_close',
        'ema_12', 'ema_26', 'ema_50',
        'sma_20', 'sma_50',
        'adx_14',
        'stdev_20', 'stdev_30',
        # Add other pre-calculated indicator lines here if needed
    )

    params = (
        ('filtered_close', -1),
        ('ema_12', -1),
        ('ema_26', -1),
        ('ema_50', -1),
        ('sma_20', -1),
        ('sma_50', -1),
        ('adx_14', -1),
        ('stdev_20', -1),
        ('stdev_30', -1),
        # Add params for other indicators if they were added to lines
    )

    # Extend the parent's datafields with the new lines defined in this class
    datafields = list(bt.feeds.PandasData.datafields) + list(lines)
