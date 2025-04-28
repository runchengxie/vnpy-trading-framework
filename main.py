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

    # --- Helper Function for Backtesting and Optimization ---
    def run_backtest(strategy_cls, data_feed, initial_cash, commission,
                     single_run_params, optimize=False, opt_param_names=None,
                     use_filtered_price=False, printlog=False, strategy_name="Strategy", maxcpus=1):
        """Runs a single backtest or parameter optimization for a given strategy."""
        cerebro = bt.Cerebro()
        cerebro.adddata(data_feed)
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)

        # Add analyzers common to both single run and optimization
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

        if optimize:
            print(f"\n开始 {strategy_name} 参数优化...")
            # Add strategy for optimization (parameters defined in strategy class)
            cerebro.optstrategy(strategy_cls, use_filtered_price=use_filtered_price, printlog=printlog)
            print(f"\n正在运行 {strategy_name} 参数优化...")
            optimized_results = cerebro.run(maxcpus=maxcpus)
            print(f"\n{strategy_name} 参数优化完成。")

            print(f"\n分析 {strategy_name} 优化结果...")
            if opt_param_names is None:
                print(f"警告: 未提供 {strategy_name} 的 opt_param_names，无法分析优化结果。")
                return None
            print(f"{strategy_name} 优化参数: {opt_param_names}")
            opt_df = analyze_optimization_results(optimized_results, opt_param_names)

            print(f"\n{strategy_name} 优化结果 (按 Final Value 排序 Top 10):")
            print(opt_df.sort_values(by='Final Value', ascending=False).head(10))
            print(f"\n{strategy_name} 优化结果 (按 Sharpe Ratio 排序 Top 10 - 忽略 None):")
            print(opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10))
            return opt_df # Return the optimization results dataframe
        else:
            print(f"\n开始 {strategy_name} 单次运行回测...")
            # Add strategy for single run with specific parameters
            cerebro.addstrategy(strategy_cls, **single_run_params, use_filtered_price=use_filtered_price, printlog=printlog)
            print(f"\n正在运行 {strategy_name} 单次回测...")
            results = cerebro.run()
            strat = results[0]
            print(f"\n{strategy_name} 单次回测结果分析...")

            trade_analysis = strat.analyzers.tradeanalyzer.get_analysis()
            sharpe_ratio = strat.analyzers.sharpe.get_analysis()
            drawdown = strat.analyzers.drawdown.get_analysis()
            returns = strat.analyzers.returns.get_analysis()

            analysis_results = {
                'Final Value': cerebro.broker.getvalue(),
                'Total Trades': trade_analysis.get('total', {}).get('total', 0),
                'Win Rate (%)': (
                    trade_analysis.get('won', {}).get('total', 0)
                    / trade_analysis.get('total', {}).get('total', 1) # Avoid division by zero
                    * 100
                ) if trade_analysis.get('total', {}).get('total', 0) > 0 else 'N/A',
                'Total Net PnL': trade_analysis.get('pnl', {}).get('net', {}).get('total', 'N/A'),
                'Sharpe Ratio': sharpe_ratio.get('sharperatio', 'N/A'),
                'Max Drawdown (%)': drawdown.get('max', {}).get('drawdown', 'N/A'),
                'Annualized Return (%)': returns.get('rnorm100', 'N/A')
            }
            return cerebro, analysis_results # Return cerebro instance for plotting and results dict

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
        cerebro_instances = {} # Store cerebro instances for plotting
        initial_cash = 100000.0
        commission = 0.01
        maxcpus_opt = 1 # Set max CPUs for optimization

        # --- 运行策略 1: 均值回归 (Z-Score) ---
        strategy_name_mr = 'Mean Reversion (Z-Score)'
        strategy_names.append(strategy_name_mr)
        mr_single_run_params = {
            'zscore_period': 20, 'zscore_upper': 2.0, 'zscore_lower': -2.0,
            'exit_threshold': 0.0
        }
        mr_opt_param_names = ['zscore_period', 'zscore_upper', 'zscore_lower', 'exit_threshold']

        # Single Run
        cerebro_mr, results_mr = run_backtest(
            MeanReversionZScoreStrategy,
            data_feed=data_feed_filtered,
            initial_cash=initial_cash,
            commission=commission,
            single_run_params=mr_single_run_params,
            optimize=False,
            use_filtered_price=True,
            printlog=False,
            strategy_name=strategy_name_mr
        )
        results_comparison[strategy_name_mr] = results_mr
        cerebro_instances[strategy_name_mr] = cerebro_mr

        # Optimization
        mr_opt_df = run_backtest(
            MeanReversionZScoreStrategy,
            data_feed=data_feed_filtered,
            initial_cash=initial_cash,
            commission=commission,
            single_run_params={}, # Not used in optimization
            optimize=True,
            opt_param_names=mr_opt_param_names,
            use_filtered_price=True,
            printlog=False,
            strategy_name=strategy_name_mr,
            maxcpus=maxcpus_opt
        )

        # --- 运行策略 2: 趋势跟踪 (EMA Crossover + ADX) ---
        strategy_name_tf = 'Trend Following (EMA+ADX)'
        strategy_names.append(strategy_name_tf)
        tf_single_run_params = {
            'ema_short': 10, 'ema_long': 30, 'adx_period': 14,
            'adx_threshold': 25.0
        }
        tf_opt_param_names = ['ema_short', 'ema_long', 'adx_period', 'adx_threshold']

        # Single Run
        cerebro_tf, results_tf = run_backtest(
            EMACrossoverStrategy,
            data_feed=data_feed_base, # Use base data
            initial_cash=initial_cash,
            commission=commission,
            single_run_params=tf_single_run_params,
            optimize=False,
            use_filtered_price=False,
            printlog=False,
            strategy_name=strategy_name_tf
        )
        results_comparison[strategy_name_tf] = results_tf
        cerebro_instances[strategy_name_tf] = cerebro_tf

        # Optimization
        tf_opt_df = run_backtest(
            EMACrossoverStrategy,
            data_feed=data_feed_base, # Use base data
            initial_cash=initial_cash,
            commission=commission,
            single_run_params={}, # Not used in optimization
            optimize=True,
            opt_param_names=tf_opt_param_names,
            use_filtered_price=False,
            printlog=False,
            strategy_name=strategy_name_tf,
            maxcpus=maxcpus_opt
        )

        # --- 运行策略 3: 自定义比率策略 ---
        strategy_name_cr = 'Custom Ratio Strategy'
        strategy_names.append(strategy_name_cr)
        cr_single_run_params = {
            'long_ma_period': 50, 'buy_threshold': 0.98, 'sell_threshold': 1.02,
            'exit_threshold': 1.0
        }
        cr_opt_param_names = ['long_ma_period', 'buy_threshold', 'sell_threshold', 'exit_threshold']

        # Single Run
        cerebro_cr, results_cr = run_backtest(
            CustomRatioStrategy,
            data_feed=data_feed_base, # Use base data
            initial_cash=initial_cash,
            commission=commission,
            single_run_params=cr_single_run_params,
            optimize=False,
            use_filtered_price=False,
            printlog=False,
            strategy_name=strategy_name_cr
        )
        results_comparison[strategy_name_cr] = results_cr
        cerebro_instances[strategy_name_cr] = cerebro_cr

        # Optimization
        cr_opt_df = run_backtest(
            CustomRatioStrategy,
            data_feed=data_feed_base, # Use base data
            initial_cash=initial_cash,
            commission=commission,
            single_run_params={}, # Not used in optimization
            optimize=True,
            opt_param_names=cr_opt_param_names,
            use_filtered_price=False,
            printlog=False,
            strategy_name=strategy_name_cr,
            maxcpus=maxcpus_opt
        )

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
        for name, cerebro_instance in cerebro_instances.items():
            try:
                print(f"\n尝试生成 {name} 策略图表 (单次运行)...")
                cerebro_instance.plot(style='candlestick', barup='green', bardown='red')
            except Exception as e:
                print(f"\n无法生成 {name} 图表: {e}")

    else:
        print(f"\n重采样后数据为空，无法进行回测或优化。")

else:
    print(f"\n无法获取或处理 {ticker} 在 {start_date_str} 到 {end_date_str} 的数据。")