import pandas as pd
import logging

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
    if not optimized_results:
        logger.warning("Optimization returned no results.")
        return pd.DataFrame(results_list)

    for run_results in optimized_results:
        # *** 添加检查以跳过 None 或空结果 ***
        if run_results is None or not run_results:
            logger.warning("Skipping an empty or None result set from an optimization run.")
            error_row = {name: 'ErrorRun' for name in param_names}
            error_row.update({
                'Final Value': None, 'Total Trades': 0, 'Win Rate (%)': 0,
                'Total Net PnL': 0, 'Sharpe Ratio': None, 'Max Drawdown (%)': None,
                'Annualized Return (%)': None, 'Error': 'Empty or None run result'
            })
            results_list.append(error_row)
            continue # 跳到下一个 run_results

        # 通常内层列表只有一个策略实例
        for strategy_instance in run_results:
            # *** 添加对策略实例本身的检查 ***
            if strategy_instance is None:
                logger.warning("Skipping a None strategy instance within a run result.")
                # 尝试获取参数可能失败，所以用默认值
                error_row = {name: 'ErrorRun' for name in param_names}
                error_row.update({
                    'Final Value': None, 'Total Trades': 0, 'Win Rate (%)': 0,
                    'Total Net PnL': 0, 'Sharpe Ratio': None, 'Max Drawdown (%)': None,
                    'Annualized Return (%)': None, 'Error': 'None strategy instance'
                })
                results_list.append(error_row)
                continue # 跳到下一个 strategy_instance

            # --- 尝试获取参数 ---
            try:
                params = strategy_instance.params
                param_values = {name: getattr(params, name) for name in param_names}
            except Exception as param_e:
                logger.error(f"无法从 strategy_instance 获取参数: {param_e}")
                param_values = {name: 'ParamError' for name in param_names}

            try:
                trade_analyzer = strategy_instance.analyzers.getbyname('tradeanalyzer')
                sharpe_analyzer = strategy_instance.analyzers.getbyname('sharpe')
                drawdown_analyzer = strategy_instance.analyzers.getbyname('drawdown')
                returns_analyzer = strategy_instance.analyzers.getbyname('returns')

                # *** 改进：检查 get_analysis() 的结果是否为 None ***
                trade_analysis_raw = trade_analyzer.get_analysis() if trade_analyzer else None
                sharpe_ratio_raw = sharpe_analyzer.get_analysis() if sharpe_analyzer else None
                drawdown_raw = drawdown_analyzer.get_analysis() if drawdown_analyzer else None
                returns_raw = returns_analyzer.get_analysis() if returns_analyzer else None

                # 使用默认字典或检查 None
                trade_analysis = trade_analysis_raw if trade_analysis_raw is not None else {}
                sharpe_ratio = sharpe_ratio_raw if sharpe_ratio_raw is not None else {}
                drawdown = drawdown_raw if drawdown_raw is not None else {}
                returns = returns_raw if returns_raw is not None else {}
                # --- 结束改进 ---

                total_trades = trade_analysis.get('total', {}).get('total', 0)
                won_trades = trade_analysis.get('won', {}).get('total', 0)
                win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
                total_pnl = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)
                final_value = strategy_instance.broker.getvalue()

                result_row = {
                    **param_values,
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
                logger.error(f"分析器数据提取错误 (AttributeError)，参数: {param_values} - 错误: {e}")
                result_row = {**param_values,
                              'Final Value': None, 'Total Trades': 0, 'Win Rate (%)': 0,
                              'Total Net PnL': 0, 'Sharpe Ratio': None, 'Max Drawdown (%)': None,
                              'Annualized Return (%)': None, 'Error': f'AttributeError: {e}'}
                results_list.append(result_row)

            except Exception as e:
                # 记录更详细的错误，包括参数
                logger.error(f"分析器数据提取错误，参数: {param_values} - 错误类型: {type(e).__name__} - 错误: {e}", exc_info=True) # 添加 exc_info=True 获取 traceback
                result_row = {**param_values,
                              'Final Value': None, 'Total Trades': 0, 'Win Rate (%)': 0,
                              'Total Net PnL': 0, 'Sharpe Ratio': None, 'Max Drawdown (%)': None,
                              'Annualized Return (%)': None, 'Error': f'{type(e).__name__}: {e}'}
                results_list.append(result_row)

    return pd.DataFrame(results_list)
