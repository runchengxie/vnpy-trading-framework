import os
import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame
from dotenv import load_dotenv
from datetime import timedelta
import backtrader as bt
import multiprocessing
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from io import StringIO

# Import functions and classes from the new modules
from data_utils import fetch_historical_data, apply_kalman_filter, get_last_trading_day, add_technical_indicators
from strategies import EMACrossoverStrategy, MeanReversionZScoreStrategy, CustomRatioStrategy, PandasDataFiltered
from backtest_utils import analyze_optimization_results
from risk_manager import RiskManager
from websocket_handler import WebSocketDataHandler, MarketDataAggregator
from performance_analyzer import PerformanceAnalyzer, TradeRecord
from exception_handler import ExceptionHandler, ErrorCategory, ErrorSeverity
from consistency_validator import ConsistencyValidator

def run_backtest(strategy_cls, data_feed, initial_cash, commission,
                 single_run_params, optimize=False, opt_param_names=None,
                 opt_param_values=None,
                 use_filtered_price=False, printlog=False, strategy_name="Strategy", maxcpus=1,
                 enable_enhanced_features=True):
    """Runs a single backtest or parameter optimization for a given strategy."""
    logger = logging.getLogger(__name__)
    
    # 初始化增强功能组件
    risk_manager = None
    performance_analyzer = None
    exception_handler = None
    
    if enable_enhanced_features:
        try:
            risk_manager = RiskManager()  # 移除initial_capital参数
            performance_analyzer = PerformanceAnalyzer(initial_capital=initial_cash)
            exception_handler = ExceptionHandler()
            
            logger.info("增强功能组件初始化成功")
        except Exception as e:
            logger.warning(f"增强功能初始化失败，使用基础模式: {e}")
            enable_enhanced_features = False
    
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='tradeanalyzer')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    if optimize:
        logger.info(f"\n开始 {strategy_name} 参数优化...")
        if not opt_param_values:
            raise ValueError("opt_param_values must be provided for optimization")
        cerebro.optstrategy(
            strategy_cls,
            **opt_param_values,
            use_filtered_price=use_filtered_price,
            printlog=printlog
        )
        logger.info(f"\n正在运行 {strategy_name} 参数优化 (maxcpus={maxcpus})...")
        optimized_results = cerebro.run(maxcpus=maxcpus)
        logger.info(f"\n{strategy_name} 参数优化完成。")

        logger.info(f"\n分析 {strategy_name} 优化结果...")
        if opt_param_names is None:
            logger.warning(f"警告: 未提供 {strategy_name} 的 opt_param_names，无法分析优化结果。")
            return None
        logger.info(f"{strategy_name} 优化参数: {opt_param_names}")
        
        # 检查optimized_results是否为None或空
        if optimized_results is None:
            logger.error(f"{strategy_name} 优化结果为None，无法分析")
            return None
        
        opt_df = analyze_optimization_results(optimized_results, opt_param_names)

        if opt_df is not None and not opt_df.empty:
            logger.info(f"\n{strategy_name} 优化结果 (按 Final Value 排序 Top 10):\n{opt_df.sort_values(by='Final Value', ascending=False).head(10).to_string()}")
            if 'Sharpe Ratio' in opt_df.columns:
                logger.info(f"\n{strategy_name} 优化结果 (按 Sharpe Ratio 排序 Top 10 - 忽略 None):\n{opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10).to_string()}")
            else:
                logger.warning(f"{strategy_name} 优化结果中缺少 'Sharpe Ratio' 列。")
        else:
            logger.warning(f"{strategy_name} 优化分析未返回有效结果或结果为空。")
        return opt_df
    else:
        logger.info(f"\n开始 {strategy_name} 单次运行回测...")
        cerebro.addstrategy(strategy_cls, **single_run_params, use_filtered_price=use_filtered_price, printlog=printlog)
        logger.info(f"\n正在运行 {strategy_name} 单次回测...")
        results = cerebro.run()
        strat = results[0]
        logger.info(f"\n{strategy_name} 单次回测结果分析...")

        trade_analysis = strat.analyzers.tradeanalyzer.get_analysis()
        sharpe_ratio = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        returns = strat.analyzers.returns.get_analysis()

        analysis_results = {
            'Final Value': cerebro.broker.getvalue(),
            'Total Trades': trade_analysis.get('total', {}).get('total', 0),
            'Win Rate (%)': (
                trade_analysis.get('won', {}).get('total', 0)
                / trade_analysis.get('total', {}).get('total', 1)
                * 100
            ) if trade_analysis.get('total', {}).get('total', 0) > 0 else 'N/A',
            'Total Net PnL': trade_analysis.get('pnl', {}).get('net', {}).get('total', 'N/A'),
            'Sharpe Ratio': sharpe_ratio.get('sharperatio', 'N/A'),
            'Max Drawdown (%)': drawdown.get('max', {}).get('drawdown', 'N/A'),
            'Annualized Return (%)': returns.get('rnorm100', 'N/A')
        }
        return cerebro, analysis_results

if __name__ == '__main__':
    multiprocessing.freeze_support()

    # 创建logs目录（如果不存在）
    import os
    from datetime import datetime
    
    logs_dir = 'logs'
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = os.path.join(logs_dir, f'trading_log_{timestamp}.log')
    
    # 配置日志记录到文件和控制台
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"日志文件已创建: {log_filename}")

    load_dotenv()

    API_KEY = os.getenv('APCA_API_KEY_ID')
    SECRET_KEY = os.getenv('APCA_API_SECRET_KEY')
    BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

    if not API_KEY or not SECRET_KEY:
        logger.error("错误：在环境变量中未找到 Alpaca API 密钥或秘密密钥。")
        logger.error("请设置 APCA_API_KEY_ID 和 APCA_API_SECRET_KEY。")
        exit()

    logger.info(f"Initializing Alpaca API with base URL: {BASE_URL}")
    api = REST(API_KEY, SECRET_KEY, base_url=BASE_URL, api_version='v2')

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)

    api._session.mount("https://", adapter)
    api._session.mount("http://", adapter)
    logger.info("Retry logic added to Alpaca API session.")

    ticker = 'SPY'
    time_frame_value = 15
    time_frame_unit = TimeFrame.Minute
    start_date_str = "2023-01-01"
    end_date_str = "2023-01-07"

    logger.info(f"正在获取 {ticker} 从 {start_date_str} 到 {end_date_str} 的 1 分钟数据...")
    spy_data_1min = fetch_historical_data(api, ticker, TimeFrame.Minute, start_date_str, end_date_str)

    if spy_data_1min is not None and not spy_data_1min.empty:
        logger.info(f"\n原始 1 分钟数据样本（前 5 行）：\n{spy_data_1min.head()}")
        logger.info(f"\n原始 1 分钟数据样本（后 5 行）：\n{spy_data_1min.tail()}")
        buffer = StringIO()
        spy_data_1min.info(buf=buffer)
        logger.info(f"\n数据信息：\n{buffer.getvalue()}")

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

        logger.info(f"\n正在重采样到 {time_frame_value} 分钟...")
        resample_freq = f'{time_frame_value}min'  # 使用'min'替代已弃用的'T'
        spy_data_resampled = spy_data_1min.resample(resample_freq, label='right', closed='right').agg(agg_dict).dropna()

        if not spy_data_resampled.empty:
            logger.info("Applying Kalman Filter...")
            spy_data_resampled['filtered_close'] = apply_kalman_filter(spy_data_resampled['close'])

            logger.info("Adding technical indicators...")
            spy_data_resampled = add_technical_indicators(spy_data_resampled)
            logger.info("Technical indicators added.")
            logger.info(f"Columns after adding indicators: {spy_data_resampled.columns.tolist()}")

            logger.info(f"\n重采样后的 {time_frame_value} 分钟数据样本（前 5 行）：\n{spy_data_resampled.head()}")
            buffer_resampled = StringIO()
            spy_data_resampled.info(buf=buffer_resampled)
            logger.info(f"\n重采样后的数据信息：\n{buffer_resampled.getvalue()}")

            if 'openinterest' not in spy_data_resampled.columns:
                spy_data_resampled['openinterest'] = 0

            required_base_cols = ['open', 'high', 'low', 'close', 'volume', 'openinterest']
            required_filtered_cols = required_base_cols + ['filtered_close', 'sma_50']

            missing_base_cols = [col for col in required_base_cols if col not in spy_data_resampled.columns]
            missing_filtered_cols = [col for col in required_filtered_cols if col not in spy_data_resampled.columns]

            if missing_base_cols:
                logger.error(f"错误: 重采样后的数据缺少基础 Feed 所需的列: {missing_base_cols}")
                exit()
            if missing_filtered_cols:
                logger.error(f"错误: 重采样后的数据缺少过滤 Feed 所需的列: {missing_filtered_cols}")
                exit()

            data_feed_base = bt.feeds.PandasData(dataname=spy_data_resampled[required_base_cols], datetime=None)
            data_feed_filtered = PandasDataFiltered(dataname=spy_data_resampled, datetime=None)

            results_comparison = {}
            strategy_names = []
            cerebro_instances = {}
            initial_cash = 100000.0
            commission = 0.001

            cpu_count = multiprocessing.cpu_count()
            maxcpus_opt = max(1, cpu_count - 1 if cpu_count > 1 else 1)
            logger.info(f"将使用 {maxcpus_opt} 个 CPU 核心进行优化。")

            mr_opt_values_minimal = {
                'zscore_period': [20, 30],
                'zscore_upper': [2.0],
                'zscore_lower': [-2.0],
                'exit_threshold': [0.0],
            }

            tf_opt_values_minimal = {
                'ema_short': [10],
                'ema_long': [30],
                'adx_period': [14],
                'adx_threshold': [25.0, 30.0],
            }

            cr_opt_values_minimal = {
                'long_ma_period': [50],
                'buy_threshold': [0.98, 0.95],
                'sell_threshold': [1.02],
                'exit_threshold': [1.0],
            }

            mr_opt_param_names = list(mr_opt_values_minimal.keys())
            tf_opt_param_names = list(tf_opt_values_minimal.keys())
            cr_opt_param_names = list(cr_opt_values_minimal.keys())

            strategy_name_mr = 'Mean Reversion (Z-Score)'
            strategy_names.append(strategy_name_mr)
            mr_single_run_params = {
                'zscore_period': 20, 'zscore_upper': 2.0, 'zscore_lower': -2.0,
                'exit_threshold': 0.0
            }

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

            mr_opt_df = run_backtest(
                MeanReversionZScoreStrategy,
                data_feed=data_feed_filtered,
                initial_cash=initial_cash,
                commission=commission,
                single_run_params={},
                optimize=True,
                opt_param_names=mr_opt_param_names,
                opt_param_values=mr_opt_values_minimal,
                use_filtered_price=True,
                printlog=False,
                strategy_name=strategy_name_mr,
                maxcpus=maxcpus_opt
            )

            strategy_name_tf = 'Trend Following (EMA+ADX)'
            strategy_names.append(strategy_name_tf)
            tf_single_run_params = {
                'ema_short': 10,
                'ema_long': 30,
                'adx_period': 14,
                'adx_threshold': 25.0
            }

            cerebro_tf, results_tf = run_backtest(
                EMACrossoverStrategy,
                data_feed=data_feed_base,
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

            tf_opt_df = run_backtest(
                EMACrossoverStrategy,
                data_feed=data_feed_base,
                initial_cash=initial_cash,
                commission=commission,
                single_run_params={},
                optimize=True,
                opt_param_names=tf_opt_param_names,
                opt_param_values=tf_opt_values_minimal,
                use_filtered_price=False,
                printlog=False,
                strategy_name=strategy_name_tf,
                maxcpus=maxcpus_opt
            )

            strategy_name_cr = 'Custom Ratio Strategy'
            strategy_names.append(strategy_name_cr)
            cr_single_run_params = {
                'long_ma_period': 50, 'buy_threshold': 0.98, 'sell_threshold': 1.02,
                'exit_threshold': 1.0
            }

            cerebro_cr, results_cr = run_backtest(
                CustomRatioStrategy,
                data_feed=data_feed_filtered,
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

            cr_opt_df = run_backtest(
                CustomRatioStrategy,
                data_feed=data_feed_filtered,
                initial_cash=initial_cash,
                commission=commission,
                single_run_params={},
                optimize=True,
                opt_param_names=cr_opt_param_names,
                opt_param_values=cr_opt_values_minimal,
                use_filtered_price=False,
                printlog=False,
                strategy_name=strategy_name_cr,
                maxcpus=maxcpus_opt
            )

            logger.info("\n" + "="*30 + " 策略性能比较 (单次运行) " + "="*30)
            header = f"{'Metric':<25}"
            separator = "-" * 25
            for name in strategy_names:
                header += f" | {name:<30}"
                separator += "-|-" + "-" * 30
            logger.info(header)
            logger.info(separator)

            if strategy_names:
                first_strategy_name = strategy_names[0]
                if first_strategy_name in results_comparison and results_comparison[first_strategy_name]:
                    for metric in results_comparison[first_strategy_name]:
                        line = f"{metric:<25}"
                        for name in strategy_names:
                            val = results_comparison.get(name, {}).get(metric, 'N/A')
                            if isinstance(val, (int, float)):
                                val_str = f"{val:,.2f}"
                            else:
                                val_str = str(val)
                            line += f" | {val_str:<30}"
                        logger.info(line)
                else:
                    logger.warning("无法打印比较结果，因为第一个策略没有有效的分析结果。")
            logger.info(separator.replace("-", "="))

            # 创建charts目录（如果不存在）
            charts_dir = 'charts'
            if not os.path.exists(charts_dir):
                os.makedirs(charts_dir)
            
            for name, cerebro_instance in cerebro_instances.items():
                try:
                    logger.info(f"\n尝试生成 {name} 策略图表 (单次运行)...")
                    if cerebro_instance:
                        import matplotlib.pyplot as plt
                        
                        # 生成图表
                        figs = cerebro_instance.plot(style='candlestick', barup='green', bardown='red', returnfig=True)
                        
                        # 保存图表
                        if figs and len(figs) > 0 and len(figs[0]) > 0:
                            chart_filename = os.path.join(charts_dir, f'{name.replace(" ", "_").replace("(", "").replace(")", "")}_{timestamp}.png')
                            figs[0][0].savefig(chart_filename, dpi=300, bbox_inches='tight')
                            logger.info(f"图表已保存: {chart_filename}")
                            plt.close(figs[0][0])  # 关闭图表以释放内存
                        else:
                            logger.warning(f"无法保存 {name} 图表，图表生成失败")
                    else:
                        logger.warning(f"无法为 {name} 生成图表，因为 Cerebro 实例为空。")
                except Exception as e:
                    logger.error(f"\n无法生成 {name} 图表: {e}")

        else:
            logger.warning(f"\n重采样后数据为空，无法进行回测或优化。")

    else:
        logger.error(f"\n无法获取或处理 {ticker} 在 {start_date_str} 到 {end_date_str} 的数据。")