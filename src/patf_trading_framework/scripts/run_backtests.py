import os
import sys
import pandas as pd
import yaml
from alpaca_trade_api.rest import REST, TimeFrame
from dotenv import load_dotenv
from datetime import datetime
import backtrader as bt
import multiprocessing
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from io import StringIO

# Import functions and classes from the modules
from patf_trading_framework.data_utils import fetch_historical_data, apply_kalman_filter, get_last_trading_day, add_technical_indicators
from patf_trading_framework.backtest_utils import analyze_optimization_results
from patf_trading_framework.risk_manager import RiskManager
from patf_trading_framework.websocket_handler import WebSocketDataHandler, MarketDataAggregator
from patf_trading_framework.performance_analyzer import PerformanceAnalyzer, TradeRecord
from patf_trading_framework.exception_handler import ExceptionHandler, ErrorCategory, ErrorSeverity
from patf_trading_framework.consistency_validator import ConsistencyValidator
import patf_trading_framework.strategies as strategies
from patf_trading_framework.strategies import PandasDataFiltered

def load_config(config_path):
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing configuration file: {e}")
        sys.exit(1)

def get_strategy_class(class_name_str):
    """Dynamically get strategy class from string"""
    try:
        return getattr(strategies, class_name_str)
    except AttributeError:
        logger.error(f"Strategy class '{class_name_str}' not found in strategies.py!")
        sys.exit(1)

def run_backtest(strategy_cls, data_feed, initial_cash, commission,
                 single_run_params, optimize=False, opt_param_names=None,
                 opt_param_values=None,
                 use_filtered_price=False, printlog=False, strategy_name="Strategy", maxcpus=1,
                 enable_enhanced_features=True):
    """Runs a single backtest or parameter optimization for a given strategy."""
    logger = logging.getLogger(__name__)
    
    # Initialize enhanced feature components
    risk_manager = None
    performance_analyzer = None
    exception_handler = None
    
    if enable_enhanced_features:
        try:
            risk_manager = RiskManager()  # Remove initial_capital parameter
            performance_analyzer = PerformanceAnalyzer(initial_capital=initial_cash)
            exception_handler = ExceptionHandler()
            
            logger.info("Enhanced feature components initialized successfully")
        except Exception as e:
            logger.warning(f"Enhanced feature initialization failed, using basic mode: {e}")
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
        logger.info(f"\nStarting {strategy_name} parameter optimization...")
        if not opt_param_values:
            raise ValueError("opt_param_values must be provided for optimization")
        cerebro.optstrategy(
            strategy_cls,
            **opt_param_values,
            use_filtered_price=use_filtered_price,
            printlog=printlog
        )
        logger.info(f"\nRunning {strategy_name} parameter optimization (maxcpus={maxcpus})...")
        optimized_results = cerebro.run(maxcpus=maxcpus)
        logger.info(f"\n{strategy_name} parameter optimization completed.")

        logger.info(f"\nAnalyzing {strategy_name} optimization results...")
        if opt_param_names is None:
            logger.warning(f"Warning: opt_param_names not provided for {strategy_name}, cannot analyze optimization results.")
            return None
        logger.info(f"{strategy_name} optimization parameters: {opt_param_names}")
        
        # Check if optimized_results is None or empty
        if optimized_results is None:
            logger.error(f"{strategy_name} optimization results are None, cannot analyze")
            return None
        
        opt_df = analyze_optimization_results(optimized_results, opt_param_names)

        if opt_df is not None and not opt_df.empty:
            logger.info(f"\n{strategy_name} optimization results (sorted by Final Value Top 10):\n{opt_df.sort_values(by='Final Value', ascending=False).head(10).to_string()}")
            if 'Sharpe Ratio' in opt_df.columns:
                logger.info(f"\n{strategy_name} optimization results (sorted by Sharpe Ratio Top 10 - ignoring None):\n{opt_df.dropna(subset=['Sharpe Ratio']).sort_values(by='Sharpe Ratio', ascending=False).head(10).to_string()}")
            else:
                logger.warning(f"{strategy_name} optimization results missing 'Sharpe Ratio' column.")
        else:
            logger.warning(f"{strategy_name} optimization analysis returned no valid results or empty results.")
        return opt_df
    else:
        logger.info(f"\nStarting {strategy_name} single run backtest...")
        cerebro.addstrategy(strategy_cls, **single_run_params, use_filtered_price=use_filtered_price, printlog=printlog)
        logger.info(f"\nRunning {strategy_name} single backtest...")
        results = cerebro.run()
        strat = results[0]
        logger.info(f"\n{strategy_name} single backtest results analysis...")

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

def main():
    """
    Main entry function for project backtesting.
    """
    multiprocessing.freeze_support()

    # Load configuration
    config = load_config('config.yml')
    
    # Create output directories
    for dir_path in [config['paths']['log_dir'], config['paths']['chart_dir'], config['paths']['cache_dir']]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # Generate timestamped log filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = os.path.join(config['paths']['log_dir'], f'trading_log_{timestamp}.log')
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config['logging']['level']),
        format=config['logging']['format'],
        datefmt=config['logging']['datefmt'],
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Log file created: {log_filename}")

    load_dotenv()

    # Get API credentials from environment variables
    API_KEY = os.getenv('APCA_API_KEY_ID')
    SECRET_KEY = os.getenv('APCA_API_SECRET_KEY')
    BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

    if not API_KEY or not SECRET_KEY:
        logger.error("Error: Alpaca API key or secret key not found in environment variables.")
        logger.error("Please set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")
        sys.exit(1)

    logger.info(f"Initializing Alpaca API with base URL: {BASE_URL}")
    api = REST(API_KEY, SECRET_KEY, base_url=BASE_URL, api_version='v2')

    # Setup retry strategy
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

    # Get data configuration
    data_config = config['data']
    ticker = data_config['ticker']
    time_frame_value = data_config['timeframe_value']
    time_frame_unit = getattr(TimeFrame, data_config['timeframe_unit'])
    start_date_str = data_config['start_date']
    end_date_str = data_config['end_date']

    # Loading the cache directory from config.yml
    cache_dir_path = config['paths']['cache_dir']
    
    logger.info(f"Fetching {ticker} 1-minute data from {start_date_str} to {end_date_str}...")
    # Adding the "cache_dir" parameter when calling fetch_historical_data 
    data_1min = fetch_historical_data(
        api, 
        ticker, 
        TimeFrame.Minute, 
        start_date_str, 
        end_date_str,
        cache_dir=cache_dir_path
    )

    if data_1min is not None and not data_1min.empty:
        logger.info(f"\nOriginal 1-minute data sample (first 5 rows):\n{data_1min.head()}")
        logger.info(f"\nOriginal 1-minute data sample (last 5 rows):\n{data_1min.tail()}")
        buffer = StringIO()
        data_1min.info(buf=buffer)
        logger.info(f"\nData information:\n{buffer.getvalue()}")

        # Aggregation dictionary for resampling
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'trade_count': 'sum',
            'vwap': 'mean'
        }
        agg_dict = {k: v for k, v in agg_dict.items() if k in data_1min.columns}

        logger.info(f"\nResampling to {time_frame_value} minutes...")
        resample_freq = data_config['resample_freq_template'].format(timeframe_value=time_frame_value)
        data_resampled = data_1min.resample(resample_freq, label='right', closed='right').agg(agg_dict).dropna()

        if not data_resampled.empty:
            logger.info("Applying Kalman Filter...")
            data_resampled['filtered_close'] = apply_kalman_filter(data_resampled['close'])

            logger.info("Adding technical indicators...")
            data_resampled = add_technical_indicators(data_resampled)
            logger.info("Technical indicators added.")
            logger.info(f"Columns after adding indicators: {data_resampled.columns.tolist()}")

            logger.info(f"\nResampled {time_frame_value}-minute data sample (first 5 rows):\n{data_resampled.head()}")
            buffer_resampled = StringIO()
            data_resampled.info(buf=buffer_resampled)
            logger.info(f"\nResampled data information:\n{buffer_resampled.getvalue()}")

            # Add openinterest column if missing
            if 'openinterest' not in data_resampled.columns:
                data_resampled['openinterest'] = 0

            # Validate required columns
            required_base_cols = ['open', 'high', 'low', 'close', 'volume', 'openinterest']
            required_filtered_cols = required_base_cols + ['filtered_close', 'sma_50']

            missing_base_cols = [col for col in required_base_cols if col not in data_resampled.columns]
            missing_filtered_cols = [col for col in required_filtered_cols if col not in data_resampled.columns]

            if missing_base_cols:
                logger.error(f"Error: Resampled data missing required columns for base feed: {missing_base_cols}")
                sys.exit(1)
            if missing_filtered_cols:
                logger.error(f"Error: Resampled data missing required columns for filtered feed: {missing_filtered_cols}")
                sys.exit(1)

            # Create data feeds
            data_feed_base = bt.feeds.PandasData(dataname=data_resampled[required_base_cols], datetime=None)
            data_feed_filtered = PandasDataFiltered(dataname=data_resampled, datetime=None)

            # Initialize tracking variables
            results_comparison = {}
            strategy_names = []
            cerebro_instances = {}
            
            # Get backtest configuration
            backtest_config = config['backtest']
            initial_cash = backtest_config['initial_cash']
            commission = backtest_config['commission']

            # Determine CPU cores for optimization
            cpu_count = multiprocessing.cpu_count()
            if backtest_config['max_cpus'] == 'auto':
                maxcpus_opt = max(1, cpu_count - 1 if cpu_count > 1 else 1)
            else:
                maxcpus_opt = min(backtest_config['max_cpus'], cpu_count)
            logger.info(f"Will use {maxcpus_opt} CPU cores for optimization.")

            # Loop through all strategies defined in configuration
            for strategy_key, strategy_config in config['strategies'].items():
                logger.info(f"\n===== Processing Strategy: {strategy_config['name']} =====")

                # Get strategy class dynamically
                strategy_cls = get_strategy_class(strategy_config['class_name'])
                
                # Prepare data feed based on use_filtered_data setting
                data_feed = data_feed_filtered if strategy_config.get('use_filtered_data', False) else data_feed_base
                
                # 1. Copy the parameter dictionary to avoid modifying the original config object.
                params_for_single_run = strategy_config.get('params', {}).copy()
                
                # 2. Safely "pop" the behavior control parameters from the copy.
                #    Using .pop() with a default value ensures the code runs even if these keys are missing in the config.
                use_filtered = params_for_single_run.pop('use_filtered_price', False)
                use_printlog = params_for_single_run.pop('printlog', False)
                
                # At this point, 'params_for_single_run' only contains the pure strategy numerical parameters (e.g., ema_short, zscore_period, etc.)
                
                # 3. Explicitly pass the separated parameters when calling run_backtest.
                logger.info(f"--- {strategy_config['name']}: Starting single run backtest ---")
                cerebro_single, results_single = run_backtest(
                    strategy_cls=strategy_cls,
                    data_feed=data_feed,
                    initial_cash=initial_cash,
                    commission=commission,
                    single_run_params=params_for_single_run,  # <-- Pass the processed dictionary of numerical parameters
                    optimize=False,
                    use_filtered_price=use_filtered,          # <-- Explicitly pass the behavior parameter
                    printlog=use_printlog,                    # <-- Explicitly pass the behavior parameter
                    strategy_name=strategy_config['name']
                )
                
                # Store results
                results_comparison[strategy_config['name']] = results_single
                cerebro_instances[strategy_config['name']] = cerebro_single
                strategy_names.append(strategy_config['name'])
                
                # 4. Apply the same logic for the optimization run.
                logger.info(f"--- {strategy_config['name']}: Starting parameter optimization ---")
                
                # The optimization parameters come from 'opt_ranges', but the behavior parameters are still extracted from 'params'.
                opt_ranges = strategy_config.get('opt_ranges', {})
                opt_param_names = list(opt_ranges.keys())
                
                opt_df = run_backtest(
                    strategy_cls=strategy_cls,
                    data_feed=data_feed,
                    initial_cash=initial_cash,
                    commission=commission,
                    single_run_params={},  # Single-run params are empty in this mode
                    optimize=True,
                    opt_param_names=opt_param_names,
                    opt_param_values=opt_ranges,
                    use_filtered_price=use_filtered,  # <-- Also pass explicitly to ensure optimization uses the correct data
                    printlog=use_printlog,            # <-- Ensure consistent logging behavior for optimization
                    strategy_name=strategy_config['name'],
                    maxcpus=maxcpus_opt
                )
                
                # Log optimization results
                if opt_df is not None and not opt_df.empty:
                    logger.info(f"\n{strategy_config['name']} optimization completed successfully")
                else:
                    logger.warning(f"\n{strategy_config['name']} optimization returned no results")

            logger.info("\n" + "="*30 + " Strategy Performance Comparison (Single Run) " + "="*30)
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
                    logger.warning("Cannot print comparison results because the first strategy has no valid analysis results.")
            logger.info(separator.replace("-", "="))

            # Generate charts for all strategies
            charts_dir = config['paths']['chart_dir']
            for name, cerebro_instance in cerebro_instances.items():
                try:
                    logger.info(f"\nAttempting to generate {name} strategy chart (single run)...")
                    if cerebro_instance:
                        import matplotlib.pyplot as plt
                        
                        # Generate chart
                        figs = cerebro_instance.plot(style='candlestick', barup='green', bardown='red', returnfig=True)
                        
                        # Save chart
                        if figs and len(figs) > 0 and len(figs[0]) > 0:
                            chart_filename = os.path.join(charts_dir, f'{name.replace(" ", "_").replace("(", "").replace(")", "")}_{timestamp}.png')
                            figs[0][0].savefig(chart_filename, dpi=300, bbox_inches='tight')
                            logger.info(f"Chart saved: {chart_filename}")
                            plt.close(figs[0][0])  # Close chart to free memory
                        else:
                            logger.warning(f"Cannot save {name} chart, chart generation failed")
                    else:
                        logger.warning(f"Cannot generate chart for {name} because Cerebro instance is empty.")
                except Exception as e:
                    logger.error(f"\nCannot generate {name} chart: {e}")

        else:
            logger.warning("\nResampled data is empty, cannot perform backtesting or optimization.")

    else:
        logger.error(f"\nCannot fetch or process {ticker} data from {start_date_str} to {end_date_str}.")


if __name__ == '__main__':
    # Call main function when running this script directly
    main()