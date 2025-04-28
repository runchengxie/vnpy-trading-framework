import os
import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame
from dotenv import load_dotenv
from datetime import timedelta
import backtrader as bt

# Import functions and classes from the new modules
from data_utils import fetch_historical_data, apply_kalman_filter, get_last_trading_day
from strategies import EMACrossoverStrategy, MeanReversionZScoreStrategy, CustomRatioStrategy, PandasDataFiltered
from backtest_utils import analyze_optimization_results

# ===========================================================================================
# 主执行脚本
# ===========================================================================================

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

# --- 使用示例 ---
# 定义参数
ticker = 'SPY' # 标普 500 ETF
time_frame_value = 15 # 单位的值 (15 minutes)
time_frame_unit = TimeFrame.Minute # 使用 Alpaca 的 TimeFrame 枚举
start_date_str = "2023-01-01"
end_date_str = "2023-12-31"

# 获取该时间段的 1 分钟数据用于重采样
print(f"正在获取 {ticker} 从 {start_date_str} 到 {end_date_str} 的 1 分钟数据...")
# Pass the initialized api object to the function
spy_data_1min = fetch_historical_data(api, ticker, TimeFrame.Minute, start_date_str, end_date_str)

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

    # --- Apply Kalman Filter ---
    if not spy_data_resampled.empty:
        spy_data_resampled['filtered_close'] = apply_kalman_filter(spy_data_resampled['close'])

    # --- Backtrader 设置和运行 ---
    if not spy_data_resampled.empty:
        print(f"\n重采样后的 {time_frame_value} 分钟数据样本（前 5 行）：\n{spy_data_resampled.head()}")
        print(f"\n重采样后的数据信息：\n")
        spy_data_resampled.info()

        # --- 准备数据 Feed ---
        if 'openinterest' not in spy_data_resampled.columns:
            spy_data_resampled['openinterest'] = 0
        # Base data feed (used for non-filtered strategies)
        data_feed_base = bt.feeds.PandasData(dataname=spy_data_resampled, datetime=None, open='open', high='high', low='low', close='close', volume='volume', openinterest='openinterest')
        # Data feed with filtered close (used for strategies needing it)
        data_feed_filtered = PandasDataFiltered(
            dataname=spy_data_resampled,
            datetime=None,
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest='openinterest',
            filtered_close='filtered_close'
        )


        # --- 存储结果 ---
        results_comparison = {}
        strategy_names = [] # Keep track of strategy names for printing

        # --- 运行策略 1: 均值回归 (Z-Score) - 单次运行 ---
        print("\n开始均值回归策略 (Z-Score) 单次运行回测...")
        strategy_names.append('Mean Reversion (Z-Score)')
        cerebro_mr = bt.Cerebro()
        # Use the filtered data feed
        cerebro_mr.adddata(data_feed_filtered)
        # Add strategy with specific parameters for the single run
        cerebro_mr.addstrategy(MeanReversionZScoreStrategy,
                               zscore_period=20, zscore_upper=2.0, zscore_lower=-2.0,
                               exit_threshold=0.0, use_filtered_price=True, printlog=False)
        cerebro_mr.broker.setcash(100000.0)
        cerebro_mr.broker.setcommission(commission=0.01)
        cerebro_mr.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_mr.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_mr.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_mr.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行均值回归单次回测...")
        results_mr = cerebro_mr.run()
        strat_mr = results_mr[0]

        print("\n均值回归单次回测结果分析...")
        trade_analysis_mr = strat_mr.analyzers.tradeanalyzer.get_analysis()
        sharpe_ratio_mr = strat_mr.analyzers.sharpe.get_analysis()
        drawdown_mr = strat_mr.analyzers.drawdown.get_analysis()
        returns_mr = strat_mr.analyzers.returns.get_analysis()

        # Store results for comparison table
        results_comparison['Mean Reversion (Z-Score)'] = {
            'Final Value': cerebro_mr.broker.getvalue(),
            'Total Trades': trade_analysis_mr.get('total', {}).get('total', 0),
            'Win Rate (%)': (
                trade_analysis_mr.get('won', {}).get('total', 0)
                / trade_analysis_mr.get('total', {}).get('total', 1) # Avoid division by zero
                * 100
            ) if trade_analysis_mr.get('total', {}).get('total', 0) > 0 else 'N/A',
            'Total Net PnL': trade_analysis_mr.get('pnl', {}).get('net', {}).get('total', 'N/A'),
            'Sharpe Ratio': sharpe_ratio_mr.get('sharperatio', 'N/A'),
            'Max Drawdown (%)': drawdown_mr.get('max', {}).get('drawdown', 'N/A'),
            'Annualized Return (%)': returns_mr.get('rnorm100', 'N/A')
        }

        # --- 运行策略 1: 均值回归 (Z-Score) - 参数优化 ---
        print("\n开始均值回归策略 (Z-Score) 参数优化...")
        cerebro_mr_opt = bt.Cerebro()
        cerebro_mr_opt.adddata(data_feed_filtered) # Use filtered data
        # Use optstrategy - parameters defined in the class
        cerebro_mr_opt.optstrategy(MeanReversionZScoreStrategy, use_filtered_price=True, printlog=False)
        cerebro_mr_opt.broker.setcash(100000.0)
        cerebro_mr_opt.broker.setcommission(commission=0.01)
        cerebro_mr_opt.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_mr_opt.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_mr_opt.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_mr_opt.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行均值回归参数优化...")
        optimized_results_mr = cerebro_mr_opt.run(maxcpus=1)
        print("\n均值回归参数优化完成。")

        print("\n分析均值回归优化结果...")
        # Define optimization parameter names manually for MeanReversionZScoreStrategy
        mr_param_names = ['zscore_period', 'zscore_upper', 'zscore_lower', 'exit_threshold']
        print(f"均值回归优化参数: {mr_param_names}")  # Debug info
        mr_opt_df = analyze_optimization_results(optimized_results_mr, mr_param_names)

        print("\n均值回归优化结果 (按 Final Value 排序 Top 10):")
        print(mr_opt_df.sort_values(by='Final Value', ascending=False).head(10))
        print("\n均值回归优化结果 (按 Sharpe Ratio 排序 Top 10 - 忽略 None):")
        print(mr_opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10))


        # --- 运行策略 2: 趋势跟踪 (EMA Crossover + ADX) - 单次运行 ---
        print("\n开始趋势跟踪策略 (EMA Crossover + ADX) 单次运行回测...")
        strategy_names.append('Trend Following (EMA+ADX)')
        cerebro_tf = bt.Cerebro()
        cerebro_tf.adddata(data_feed_base) # Use base data feed
        # Add strategy with specific parameters for the single run
        cerebro_tf.addstrategy(EMACrossoverStrategy,
                               ema_short=10, ema_long=30, adx_period=14,
                               adx_threshold=25.0, use_filtered_price=False, printlog=False)
        cerebro_tf.broker.setcash(100000.0)
        cerebro_tf.broker.setcommission(commission=0.01)
        cerebro_tf.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_tf.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_tf.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_tf.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行趋势跟踪单次回测...")
        results_tf = cerebro_tf.run()
        strat_tf = results_tf[0]

        print("\n趋势跟踪单次回测结果分析...")
        trade_analysis_tf = strat_tf.analyzers.tradeanalyzer.get_analysis()
        sharpe_ratio_tf = strat_tf.analyzers.sharpe.get_analysis()
        drawdown_tf = strat_tf.analyzers.drawdown.get_analysis()
        returns_tf = strat_tf.analyzers.returns.get_analysis()

        # Store results for comparison table
        results_comparison['Trend Following (EMA+ADX)'] = {
            'Final Value': cerebro_tf.broker.getvalue(),
            'Total Trades': trade_analysis_tf.get('total', {}).get('total', 0),
            'Win Rate (%)': (
                trade_analysis_tf.get('won', {}).get('total', 0)
                / trade_analysis_tf.get('total', {}).get('total', 1) # Avoid division by zero
                * 100
            ) if trade_analysis_tf.get('total', {}).get('total', 0) > 0 else 'N/A',
            'Total Net PnL': trade_analysis_tf.get('pnl', {}).get('net', {}).get('total', 'N/A'),
            'Sharpe Ratio': sharpe_ratio_tf.get('sharperatio', 'N/A'),
            'Max Drawdown (%)': drawdown_tf.get('max', {}).get('drawdown', 'N/A'),
            'Annualized Return (%)': returns_tf.get('rnorm100', 'N/A')
        }

        # --- 运行策略 2: 趋势跟踪 (EMA Crossover + ADX) - 参数优化 ---
        print("\n开始趋势跟踪策略 (EMA Crossover + ADX) 参数优化...")
        cerebro_tf_opt = bt.Cerebro()
        cerebro_tf_opt.adddata(data_feed_base) # Use base data
        # Use optstrategy
        cerebro_tf_opt.optstrategy(EMACrossoverStrategy, use_filtered_price=False, printlog=False)
        cerebro_tf_opt.broker.setcash(100000.0)
        cerebro_tf_opt.broker.setcommission(commission=0.01)
        cerebro_tf_opt.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_tf_opt.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_tf_opt.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_tf_opt.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行趋势跟踪参数优化...")
        optimized_results_tf = cerebro_tf_opt.run(maxcpus=1)
        print("\n趋势跟踪参数优化完成。")

        print("\n分析趋势跟踪优化结果...")
        # Define optimization parameter names manually for EMACrossoverStrategy
        tf_param_names = ['ema_short', 'ema_long', 'adx_period', 'adx_threshold']
        print(f"趋势跟踪优化参数: {tf_param_names}")  # Debug info
        tf_opt_df = analyze_optimization_results(optimized_results_tf, tf_param_names)

        print("\n趋势跟踪优化结果 (按 Final Value 排序 Top 10):")
        print(tf_opt_df.sort_values(by='Final Value', ascending=False).head(10))
        print("\n趋势跟踪优化结果 (按 Sharpe Ratio 排序 Top 10 - 忽略 None):")
        print(tf_opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10))


        # --- 运行策略 3: 自定义比率策略 - 单次运行 ---
        print("\n开始自定义比率策略单次运行回测...")
        strategy_names.append('Custom Ratio Strategy')
        cerebro_cr = bt.Cerebro()
        cerebro_cr.adddata(data_feed_base) # Use base data feed
        # Add strategy with specific parameters for the single run
        cerebro_cr.addstrategy(CustomRatioStrategy,
                               long_ma_period=50, buy_threshold=0.98, sell_threshold=1.02,
                               exit_threshold=1.0, use_filtered_price=False, printlog=False)
        cerebro_cr.broker.setcash(100000.0)
        cerebro_cr.broker.setcommission(commission=0.01)
        cerebro_cr.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_cr.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_cr.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_cr.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行自定义比率单次回测...")
        results_cr = cerebro_cr.run()
        strat_cr = results_cr[0]

        print("\n自定义比率单次回测结果分析...")
        trade_analysis_cr = strat_cr.analyzers.tradeanalyzer.get_analysis()
        sharpe_ratio_cr = strat_cr.analyzers.sharpe.get_analysis()
        drawdown_cr = strat_cr.analyzers.drawdown.get_analysis() 
        returns_cr = strat_cr.analyzers.returns.get_analysis()

        # Store results for comparison table
        results_comparison['Custom Ratio Strategy'] = {
            'Final Value': cerebro_cr.broker.getvalue(),
            'Total Trades': trade_analysis_cr.get('total', {}).get('total', 0),
            'Win Rate (%)': (
                trade_analysis_cr.get('won', {}).get('total', 0)
                / trade_analysis_cr.get('total', {}).get('total', 1) # Avoid division by zero
                * 100
            ) if trade_analysis_cr.get('total', {}).get('total', 0) > 0 else 'N/A',
            'Total Net PnL': trade_analysis_cr.get('pnl', {}).get('net', {}).get('total', 'N/A'),
            'Sharpe Ratio': sharpe_ratio_cr.get('sharperatio', 'N/A'),
            'Max Drawdown (%)': drawdown_cr.get('max', {}).get('drawdown', 'N/A'),
            'Annualized Return (%)': returns_cr.get('rnorm100', 'N/A')
        }

        # --- 运行策略 3: 自定义比率策略 - 参数优化 ---
        print("\n开始自定义比率策略参数优化...")
        cerebro_cr_opt = bt.Cerebro()
        cerebro_cr_opt.adddata(data_feed_base) # Use base data
        # Use optstrategy
        cerebro_cr_opt.optstrategy(CustomRatioStrategy, use_filtered_price=False, printlog=False)
        cerebro_cr_opt.broker.setcash(100000.0)
        cerebro_cr_opt.broker.setcommission(commission=0.01)
        cerebro_cr_opt.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro_cr_opt.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro_cr_opt.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro_cr_opt.addanalyzer(bt.analyzers.Returns, _name='returns')

        print("\n正在运行自定义比率参数优化...")
        optimized_results_cr = cerebro_cr_opt.run(maxcpus=1)
        print("\n自定义比率参数优化完成。")

        print("\n分析自定义比率优化结果...")
        # Define optimization parameter names manually for CustomRatioStrategy
        cr_param_names = ['long_ma_period', 'buy_threshold', 'sell_threshold', 'exit_threshold']
        print(f"自定义比率优化参数: {cr_param_names}")  # Debug info
        cr_opt_df = analyze_optimization_results(optimized_results_cr, cr_param_names)

        print("\n自定义比率优化结果 (按 Final Value 排序 Top 10):")
        print(cr_opt_df.sort_values(by='Final Value', ascending=False).head(10))
        print("\n自定义比率优化结果 (按 Sharpe Ratio 排序 Top 10 - 忽略 None):")
        print(cr_opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10))


        # --- 打印结果比较 (仅包含单次运行结果) ---
        print("\n" + "="*30 + " 策略性能比较 (单次运行) " + "="*30)
        header = f"{'Metric':<25}"
        separator = "-" * 25
        for name in strategy_names:
            header += f" | {name:<30}"
            separator += "-|-" + "-" * 30
        print(header)
        print(separator)

        # Assuming all strategies produce the same metrics
        if strategy_names:
            first_strategy_name = strategy_names[0]
            for metric in results_comparison[first_strategy_name]:
                line = f"{metric:<25}"
                for name in strategy_names:
                    val = results_comparison[name].get(metric, 'N/A') # Use .get for safety
                    # Format numbers for better readability
                    if isinstance(val, (int, float)):
                        val_str = f"{val:,.2f}"
                    else:
                        val_str = str(val)
                    line += f" | {val_str:<30}"
                print(line)
        print(separator.replace("-", "=")) # Use '=' for the bottom separator


        # --- (可选) 绘制图表 (仅绘制单次运行结果) ---
        try:
            print("\n尝试生成均值回归策略图表 (单次运行)...")
            cerebro_mr.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"\n无法生成均值回归图表: {e}")

        try:
            print("\n尝试生成趋势跟踪策略图表 (单次运行)...")
            cerebro_tf.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"\n无法生成趋势跟踪图表: {e}")

        try:
            print("\n尝试生成自定义比率策略图表 (单次运行)...")
            cerebro_cr.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"\n无法生成自定义比率图表: {e}")


    else:
        print(f"\n重采样后数据为空，无法进行回测或优化。")

else:
    print(f"\n无法获取或处理 {ticker} 在 {start_date_str} 到 {end_date_str} 的数据。")