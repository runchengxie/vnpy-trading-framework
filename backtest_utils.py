import pandas as pd
import logging  # Add logging import

# --- Logging Setup ---
logger = logging.getLogger(__name__)  # Create logger for this module
# --- End Logging Setup ---

# --- Helper function to analyze optimization results ---
def analyze_optimization_results(optimized_results, param_names):
    """
    分析 Backtrader 优化结果并返回一个 DataFrame。

    Args:
        optimized_results (list): cerebro.run() 返回的优化结果。
        param_names (list): 策略中优化的参数名称字符串列表。

    Returns:
        pandas.DataFrame: 包含参数和性能指标的 DataFrame。
    """
    results_list = []
    for run_results in optimized_results:
        for strategy_instance in run_results:  # 通常内部列表只有一个策略实例
            params = strategy_instance.params  # 获取当前运行的参数
            param_values = {name: getattr(params, name) for name in param_names}

            try:
                # Ensure analyzers exist before accessing them
                trade_analyzer = strategy_instance.analyzers.getbyname('tradeanalyzer')
                sharpe_analyzer = strategy_instance.analyzers.getbyname('sharpe')
                drawdown_analyzer = strategy_instance.analyzers.getbyname('drawdown')
                returns_analyzer = strategy_instance.analyzers.getbyname('returns')

                trade_analysis = trade_analyzer.get_analysis() if trade_analyzer else {}
                sharpe_ratio = sharpe_analyzer.get_analysis() if sharpe_analyzer else {}
                drawdown = drawdown_analyzer.get_analysis() if drawdown_analyzer else {}
                returns = returns_analyzer.get_analysis() if returns_analyzer else {}

                total_trades = trade_analysis.get('total', {}).get('total', 0)
                won_trades = trade_analysis.get('won', {}).get('total', 0)
                win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
                total_pnl = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)
                final_value = strategy_instance.broker.getvalue()  # 获取最终价值

                result_row = {
                    **param_values,  # 合并参数字典
                    'Final Value': final_value,
                    'Total Trades': total_trades,
                    'Win Rate (%)': win_rate,
                    'Total Net PnL': total_pnl,
                    'Sharpe Ratio': sharpe_ratio.get('sharperatio', None),
                    'Max Drawdown (%)': drawdown.get('max', {}).get('drawdown', None),
                    'Annualized Return (%)': returns.get('rnorm100', None)
                }
                results_list.append(result_row)

            except AttributeError as e:
                logger.error(f"分析器数据提取错误 (AttributeError)，参数: {param_values} - 错误: {e}")  # Use logger
                result_row = {**param_values,
                              'Final Value': None,
                              'Total Trades': 0,
                              'Win Rate (%)': 0,
                              'Total Net PnL': 0,
                              'Sharpe Ratio': None,
                              'Max Drawdown (%)': None,
                              'Annualized Return (%)': None,
                              'Error': f'AttributeError: {e}'}
                results_list.append(result_row)
                continue  # Skip to the next iteration

            except Exception as e:
                logger.error(f"分析器数据提取错误，参数: {param_values} - 错误: {e}")  # Use logger
                result_row = {**param_values,
                              'Final Value': None,
                              'Total Trades': 0,
                              'Win Rate (%)': 0,
                              'Total Net PnL': 0,
                              'Sharpe Ratio': None,
                              'Max Drawdown (%)': None,
                              'Annualized Return (%)': None,
                              'Error': str(e)}
                results_list.append(result_row)

    return pd.DataFrame(results_list)
