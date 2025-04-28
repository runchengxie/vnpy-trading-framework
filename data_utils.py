import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from alpaca_trade_api.rest import REST, TimeFrame
from datetime import date, timedelta
from pykalman import KalmanFilter

# Define cache directory relative to this file's location or use an absolute path
# For simplicity, assuming it's run from the project root where 'cache' exists
CACHE_DIR = 'cache'
os.makedirs(CACHE_DIR, exist_ok=True) # Create cache directory if it doesn't exist

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


def fetch_historical_data(api, symbol, timeframe, start_date, end_date):
    """
    使用 Alpaca API 获取给定交易品种的历史 K 线数据，并使用 Parquet 格式进行缓存。

    Args:
        api (REST): Initialized Alpaca API client.
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

# --- Kalman Filter Function ---
def apply_kalman_filter(prices):
    kf = KalmanFilter(transition_matrices=[1],
                      observation_matrices=[1],
                      initial_state_mean=prices.iloc[0],
                      n_dim_obs=1)
    state_means, _ = kf.filter(prices.values)
    return pd.Series(state_means.flatten(), index=prices.index)
