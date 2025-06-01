# consistency_validator.py
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json
import warnings
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """验证结果"""
    test_name: str
    passed: bool
    score: float  # 0-1之间的分数
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

@dataclass
class TradeComparison:
    """交易对比数据"""
    backtest_trade: Dict[str, Any]
    live_trade: Dict[str, Any]
    time_diff: float  # 时间差异（秒）
    price_diff: float  # 价格差异
    quantity_diff: float  # 数量差异
    matched: bool

class ConsistencyTest(ABC):
    """一致性测试基类"""
    
    @abstractmethod
    def run_test(self, backtest_data: Dict, live_data: Dict) -> ValidationResult:
        """运行测试"""
        pass

class SignalConsistencyTest(ConsistencyTest):
    """信号一致性测试"""
    
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance
    
    def run_test(self, backtest_data: Dict, live_data: Dict) -> ValidationResult:
        """测试交易信号的一致性"""
        backtest_signals = backtest_data.get('signals', [])
        live_signals = live_data.get('signals', [])
        
        if not backtest_signals or not live_signals:
            return ValidationResult(
                test_name="信号一致性",
                passed=False,
                score=0.0,
                details={'error': '缺少信号数据'},
                warnings=['无法进行信号一致性测试']
            )
        
        # 转换为DataFrame便于分析
        bt_df = pd.DataFrame(backtest_signals)
        live_df = pd.DataFrame(live_signals)
        
        # 按时间对齐信号
        bt_df['timestamp'] = pd.to_datetime(bt_df['timestamp'])
        live_df['timestamp'] = pd.to_datetime(live_df['timestamp'])
        
        # 找到重叠的时间段
        start_time = max(bt_df['timestamp'].min(), live_df['timestamp'].min())
        end_time = min(bt_df['timestamp'].max(), live_df['timestamp'].max())
        
        bt_period = bt_df[(bt_df['timestamp'] >= start_time) & (bt_df['timestamp'] <= end_time)]
        live_period = live_df[(live_df['timestamp'] >= start_time) & (live_df['timestamp'] <= end_time)]
        
        if len(bt_period) == 0 or len(live_period) == 0:
            return ValidationResult(
                test_name="信号一致性",
                passed=False,
                score=0.0,
                details={'error': '没有重叠的时间段'},
                warnings=['回测和实盘数据时间段不重叠']
            )
        
        # 计算信号匹配度
        matched_signals = 0
        total_signals = 0
        signal_differences = []
        
        for _, bt_signal in bt_period.iterrows():
            # 在实盘数据中找到最接近的时间点
            time_diffs = abs(live_period['timestamp'] - bt_signal['timestamp'])
            closest_idx = time_diffs.idxmin()
            
            if time_diffs[closest_idx] <= timedelta(minutes=5):  # 5分钟容忍度
                live_signal = live_period.loc[closest_idx]
                
                # 比较信号值
                bt_value = bt_signal.get('signal', 0)
                live_value = live_signal.get('signal', 0)
                
                diff = abs(bt_value - live_value)
                signal_differences.append(diff)
                
                if diff <= self.tolerance:
                    matched_signals += 1
                
                total_signals += 1
        
        if total_signals == 0:
            match_rate = 0.0
        else:
            match_rate = matched_signals / total_signals
        
        avg_difference = np.mean(signal_differences) if signal_differences else float('inf')
        max_difference = np.max(signal_differences) if signal_differences else float('inf')
        
        passed = match_rate >= 0.8 and avg_difference <= self.tolerance
        
        details = {
            'match_rate': match_rate,
            'total_compared': total_signals,
            'matched_signals': matched_signals,
            'avg_difference': avg_difference,
            'max_difference': max_difference,
            'tolerance': self.tolerance
        }
        
        warnings = []
        recommendations = []
        
        if match_rate < 0.8:
            warnings.append(f"信号匹配率较低: {match_rate:.2%}")
            recommendations.append("检查策略参数配置是否一致")
        
        if avg_difference > self.tolerance:
            warnings.append(f"平均信号差异超过容忍度: {avg_difference:.4f}")
            recommendations.append("检查数据源和计算逻辑的一致性")
        
        return ValidationResult(
            test_name="信号一致性",
            passed=passed,
            score=match_rate,
            details=details,
            warnings=warnings,
            recommendations=recommendations
        )

class ExecutionConsistencyTest(ConsistencyTest):
    """执行一致性测试"""
    
    def __init__(self, time_tolerance: int = 300, price_tolerance: float = 0.001):
        self.time_tolerance = time_tolerance  # 秒
        self.price_tolerance = price_tolerance  # 价格容忍度
    
    def run_test(self, backtest_data: Dict, live_data: Dict) -> ValidationResult:
        """测试交易执行的一致性"""
        backtest_trades = backtest_data.get('trades', [])
        live_trades = live_data.get('trades', [])
        
        if not backtest_trades or not live_trades:
            return ValidationResult(
                test_name="执行一致性",
                passed=False,
                score=0.0,
                details={'error': '缺少交易数据'},
                warnings=['无法进行执行一致性测试']
            )
        
        # 匹配交易
        trade_comparisons = self._match_trades(backtest_trades, live_trades)
        
        if not trade_comparisons:
            return ValidationResult(
                test_name="执行一致性",
                passed=False,
                score=0.0,
                details={'error': '无法匹配任何交易'},
                warnings=['回测和实盘交易无法匹配']
            )
        
        # 分析匹配结果
        matched_count = sum(1 for comp in trade_comparisons if comp.matched)
        total_count = len(trade_comparisons)
        match_rate = matched_count / total_count
        
        # 计算执行质量指标
        time_diffs = [comp.time_diff for comp in trade_comparisons if comp.matched]
        price_diffs = [abs(comp.price_diff) for comp in trade_comparisons if comp.matched]
        quantity_diffs = [abs(comp.quantity_diff) for comp in trade_comparisons if comp.matched]
        
        avg_time_diff = np.mean(time_diffs) if time_diffs else float('inf')
        avg_price_diff = np.mean(price_diffs) if price_diffs else float('inf')
        avg_quantity_diff = np.mean(quantity_diffs) if quantity_diffs else float('inf')
        
        max_time_diff = np.max(time_diffs) if time_diffs else float('inf')
        max_price_diff = np.max(price_diffs) if price_diffs else float('inf')
        
        # 评分计算
        time_score = max(0, 1 - avg_time_diff / self.time_tolerance)
        price_score = max(0, 1 - avg_price_diff / self.price_tolerance)
        overall_score = (match_rate + time_score + price_score) / 3
        
        passed = (match_rate >= 0.8 and 
                 avg_time_diff <= self.time_tolerance and 
                 avg_price_diff <= self.price_tolerance)
        
        details = {
            'match_rate': match_rate,
            'matched_trades': matched_count,
            'total_trades': total_count,
            'avg_time_diff_seconds': avg_time_diff,
            'avg_price_diff': avg_price_diff,
            'avg_quantity_diff': avg_quantity_diff,
            'max_time_diff_seconds': max_time_diff,
            'max_price_diff': max_price_diff,
            'time_tolerance': self.time_tolerance,
            'price_tolerance': self.price_tolerance
        }
        
        warnings = []
        recommendations = []
        
        if match_rate < 0.8:
            warnings.append(f"交易匹配率较低: {match_rate:.2%}")
            recommendations.append("检查交易逻辑和触发条件")
        
        if avg_time_diff > self.time_tolerance:
            warnings.append(f"平均执行时间差异过大: {avg_time_diff:.1f}秒")
            recommendations.append("优化交易执行速度")
        
        if avg_price_diff > self.price_tolerance:
            warnings.append(f"平均价格差异过大: {avg_price_diff:.4f}")
            recommendations.append("检查滑点控制和订单类型")
        
        return ValidationResult(
            test_name="执行一致性",
            passed=passed,
            score=overall_score,
            details=details,
            warnings=warnings,
            recommendations=recommendations
        )
    
    def _match_trades(self, backtest_trades: List[Dict], live_trades: List[Dict]) -> List[TradeComparison]:
        """匹配回测和实盘交易"""
        comparisons = []
        
        for bt_trade in backtest_trades:
            bt_time = pd.to_datetime(bt_trade['timestamp'])
            bt_symbol = bt_trade.get('symbol', '')
            bt_side = bt_trade.get('side', '')
            
            best_match = None
            min_time_diff = float('inf')
            
            for live_trade in live_trades:
                live_time = pd.to_datetime(live_trade['timestamp'])
                live_symbol = live_trade.get('symbol', '')
                live_side = live_trade.get('side', '')
                
                # 检查基本匹配条件
                if bt_symbol == live_symbol and bt_side == live_side:
                    time_diff = abs((live_time - bt_time).total_seconds())
                    
                    if time_diff < min_time_diff and time_diff <= self.time_tolerance:
                        min_time_diff = time_diff
                        best_match = live_trade
            
            if best_match:
                price_diff = best_match.get('price', 0) - bt_trade.get('price', 0)
                quantity_diff = best_match.get('quantity', 0) - bt_trade.get('quantity', 0)
                
                matched = (min_time_diff <= self.time_tolerance and 
                          abs(price_diff) <= self.price_tolerance * bt_trade.get('price', 1))
                
                comparison = TradeComparison(
                    backtest_trade=bt_trade,
                    live_trade=best_match,
                    time_diff=min_time_diff,
                    price_diff=price_diff,
                    quantity_diff=quantity_diff,
                    matched=matched
                )
                
                comparisons.append(comparison)
        
        return comparisons

class PerformanceConsistencyTest(ConsistencyTest):
    """性能一致性测试"""
    
    def __init__(self, return_tolerance: float = 0.05, sharpe_tolerance: float = 0.2):
        self.return_tolerance = return_tolerance
        self.sharpe_tolerance = sharpe_tolerance
    
    def run_test(self, backtest_data: Dict, live_data: Dict) -> ValidationResult:
        """测试性能指标的一致性"""
        bt_performance = backtest_data.get('performance', {})
        live_performance = live_data.get('performance', {})
        
        if not bt_performance or not live_performance:
            return ValidationResult(
                test_name="性能一致性",
                passed=False,
                score=0.0,
                details={'error': '缺少性能数据'},
                warnings=['无法进行性能一致性测试']
            )
        
        # 比较关键性能指标
        metrics_comparison = {}
        
        # 收益率比较
        bt_return = bt_performance.get('total_return', 0)
        live_return = live_performance.get('total_return', 0)
        return_diff = abs(bt_return - live_return)
        
        metrics_comparison['total_return'] = {
            'backtest': bt_return,
            'live': live_return,
            'difference': return_diff,
            'relative_diff': return_diff / abs(bt_return) if bt_return != 0 else float('inf'),
            'within_tolerance': return_diff <= self.return_tolerance
        }
        
        # 夏普比率比较
        bt_sharpe = bt_performance.get('sharpe_ratio', 0)
        live_sharpe = live_performance.get('sharpe_ratio', 0)
        sharpe_diff = abs(bt_sharpe - live_sharpe)
        
        metrics_comparison['sharpe_ratio'] = {
            'backtest': bt_sharpe,
            'live': live_sharpe,
            'difference': sharpe_diff,
            'relative_diff': sharpe_diff / abs(bt_sharpe) if bt_sharpe != 0 else float('inf'),
            'within_tolerance': sharpe_diff <= self.sharpe_tolerance
        }
        
        # 最大回撤比较
        bt_drawdown = bt_performance.get('max_drawdown', 0)
        live_drawdown = live_performance.get('max_drawdown', 0)
        drawdown_diff = abs(bt_drawdown - live_drawdown)
        
        metrics_comparison['max_drawdown'] = {
            'backtest': bt_drawdown,
            'live': live_drawdown,
            'difference': drawdown_diff,
            'relative_diff': drawdown_diff / abs(bt_drawdown) if bt_drawdown != 0 else float('inf'),
            'within_tolerance': drawdown_diff <= 0.05  # 5%容忍度
        }
        
        # 胜率比较
        bt_winrate = bt_performance.get('win_rate', 0)
        live_winrate = live_performance.get('win_rate', 0)
        winrate_diff = abs(bt_winrate - live_winrate)
        
        metrics_comparison['win_rate'] = {
            'backtest': bt_winrate,
            'live': live_winrate,
            'difference': winrate_diff,
            'relative_diff': winrate_diff / abs(bt_winrate) if bt_winrate != 0 else float('inf'),
            'within_tolerance': winrate_diff <= 0.1  # 10%容忍度
        }
        
        # 计算总体一致性分数
        consistent_metrics = sum(1 for metric in metrics_comparison.values() if metric['within_tolerance'])
        total_metrics = len(metrics_comparison)
        consistency_score = consistent_metrics / total_metrics
        
        passed = consistency_score >= 0.75  # 至少75%的指标要一致
        
        warnings = []
        recommendations = []
        
        for metric_name, metric_data in metrics_comparison.items():
            if not metric_data['within_tolerance']:
                warnings.append(f"{metric_name}差异过大: {metric_data['difference']:.4f}")
                
                if metric_name == 'total_return':
                    recommendations.append("检查交易成本和滑点设置")
                elif metric_name == 'sharpe_ratio':
                    recommendations.append("检查风险管理和仓位控制")
                elif metric_name == 'max_drawdown':
                    recommendations.append("检查止损策略的实施")
                elif metric_name == 'win_rate':
                    recommendations.append("检查信号过滤和执行逻辑")
        
        return ValidationResult(
            test_name="性能一致性",
            passed=passed,
            score=consistency_score,
            details={
                'metrics_comparison': metrics_comparison,
                'consistent_metrics': consistent_metrics,
                'total_metrics': total_metrics,
                'consistency_score': consistency_score
            },
            warnings=warnings,
            recommendations=recommendations
        )

class ConsistencyValidator:
    """一致性验证器主类"""
    
    def __init__(self):
        self.tests: List[ConsistencyTest] = []
        self.validation_history: List[Dict] = []
        
        # 注册默认测试
        self.register_test(SignalConsistencyTest())
        self.register_test(ExecutionConsistencyTest())
        self.register_test(PerformanceConsistencyTest())
        
        logger.info("一致性验证器初始化完成")
    
    def register_test(self, test: ConsistencyTest):
        """注册测试"""
        self.tests.append(test)
        logger.info(f"已注册测试: {test.__class__.__name__}")
    
    def validate_consistency(self, 
                           backtest_data: Dict, 
                           live_data: Dict,
                           test_names: Optional[List[str]] = None) -> Dict[str, ValidationResult]:
        """执行一致性验证"""
        logger.info("开始执行一致性验证...")
        
        results = {}
        
        for test in self.tests:
            test_name = test.__class__.__name__
            
            # 如果指定了测试名称，只运行指定的测试
            if test_names and test_name not in test_names:
                continue
            
            try:
                result = test.run_test(backtest_data, live_data)
                results[test_name] = result
                
                logger.info(f"测试完成: {result.test_name} - {'通过' if result.passed else '失败'} (分数: {result.score:.2f})")
                
            except Exception as e:
                logger.error(f"测试执行失败 {test_name}: {e}")
                results[test_name] = ValidationResult(
                    test_name=test_name,
                    passed=False,
                    score=0.0,
                    details={'error': str(e)},
                    warnings=[f"测试执行异常: {e}"]
                )
        
        # 记录验证历史
        validation_record = {
            'timestamp': datetime.now(),
            'results': results,
            'overall_score': self._calculate_overall_score(results),
            'passed_tests': sum(1 for r in results.values() if r.passed),
            'total_tests': len(results)
        }
        
        self.validation_history.append(validation_record)
        
        logger.info(f"一致性验证完成，总体分数: {validation_record['overall_score']:.2f}")
        return results
    
    def _calculate_overall_score(self, results: Dict[str, ValidationResult]) -> float:
        """计算总体分数"""
        if not results:
            return 0.0
        
        total_score = sum(result.score for result in results.values())
        return total_score / len(results)
    
    def generate_validation_report(self, results: Dict[str, ValidationResult]) -> Dict:
        """生成验证报告"""
        overall_score = self._calculate_overall_score(results)
        passed_tests = sum(1 for r in results.values() if r.passed)
        total_tests = len(results)
        
        # 收集所有警告和建议
        all_warnings = []
        all_recommendations = []
        
        for result in results.values():
            all_warnings.extend(result.warnings)
            all_recommendations.extend(result.recommendations)
        
        # 去重
        all_warnings = list(set(all_warnings))
        all_recommendations = list(set(all_recommendations))
        
        # 确定总体状态
        if overall_score >= 0.8 and passed_tests == total_tests:
            status = "优秀"
        elif overall_score >= 0.6 and passed_tests >= total_tests * 0.75:
            status = "良好"
        elif overall_score >= 0.4:
            status = "需要改进"
        else:
            status = "严重问题"
        
        report = {
            'timestamp': datetime.now(),
            'overall_status': status,
            'overall_score': overall_score,
            'passed_tests': passed_tests,
            'total_tests': total_tests,
            'pass_rate': passed_tests / total_tests if total_tests > 0 else 0,
            'test_results': {name: {
                'passed': result.passed,
                'score': result.score,
                'warnings_count': len(result.warnings),
                'recommendations_count': len(result.recommendations)
            } for name, result in results.items()},
            'summary_warnings': all_warnings,
            'summary_recommendations': all_recommendations,
            'detailed_results': results
        }
        
        return report
    
    def export_validation_report(self, results: Dict[str, ValidationResult], file_path: str):
        """导出验证报告"""
        report = self.generate_validation_report(results)
        
        # 转换为可序列化的格式
        serializable_report = self._make_serializable(report)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_report, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"验证报告已导出到: {file_path}")
    
    def _make_serializable(self, obj):
        """将对象转换为可序列化的格式"""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, ValidationResult):
            return {
                'test_name': obj.test_name,
                'passed': obj.passed,
                'score': obj.score,
                'details': obj.details,
                'warnings': obj.warnings,
                'recommendations': obj.recommendations
            }
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        else:
            return obj
    
    def get_validation_history(self, days: int = 30) -> List[Dict]:
        """获取验证历史"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [record for record in self.validation_history 
                if record['timestamp'] >= cutoff_date]

# 示例使用
if __name__ == "__main__":
    # 创建验证器
    validator = ConsistencyValidator()
    
    # 模拟数据
    backtest_data = {
        'signals': [
            {'timestamp': '2024-01-01 10:00:00', 'signal': 1.0},
            {'timestamp': '2024-01-01 11:00:00', 'signal': -1.0}
        ],
        'trades': [
            {'timestamp': '2024-01-01 10:01:00', 'symbol': 'AAPL', 'side': 'buy', 'quantity': 100, 'price': 150.0},
            {'timestamp': '2024-01-01 11:01:00', 'symbol': 'AAPL', 'side': 'sell', 'quantity': 100, 'price': 151.0}
        ],
        'performance': {
            'total_return': 0.05,
            'sharpe_ratio': 1.2,
            'max_drawdown': -0.02,
            'win_rate': 0.6
        }
    }
    
    live_data = {
        'signals': [
            {'timestamp': '2024-01-01 10:00:30', 'signal': 0.98},
            {'timestamp': '2024-01-01 11:00:30', 'signal': -0.95}
        ],
        'trades': [
            {'timestamp': '2024-01-01 10:01:30', 'symbol': 'AAPL', 'side': 'buy', 'quantity': 100, 'price': 150.05},
            {'timestamp': '2024-01-01 11:01:30', 'symbol': 'AAPL', 'side': 'sell', 'quantity': 100, 'price': 150.95}
        ],
        'performance': {
            'total_return': 0.048,
            'sharpe_ratio': 1.15,
            'max_drawdown': -0.025,
            'win_rate': 0.58
        }
    }
    
    # 执行验证
    results = validator.validate_consistency(backtest_data, live_data)
    
    # 生成报告
    report = validator.generate_validation_report(results)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))