#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vn.py框架回测脚本

这个脚本提供了完整的程序化回测功能，支持：
1. 多种策略的回测
2. 参数优化
3. 结果分析和可视化
4. 配置文件管理

使用方法：
1. 单策略回测：python run_backtest.py --strategy EmaAdxStrategy
2. 参数优化：python run_backtest.py --strategy EmaAdxStrategy --optimize
3. 批量回测：python run_backtest.py --batch
"""

import sys
import os
from pathlib import Path

# Load environment variables from .env BEFORE importing vnpy
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    dotenv_path = project_root / '.env'
    if dotenv_path.exists():
        print(f"Loading environment variables from {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
except ImportError:
    print("python-dotenv not found, using default settings.")

# Now vnpy will read the VNPY_HOME environment variable and use the local folder
import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# vnpy相关导入
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy_ctastrategy import CtaStrategyApp
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy.trader.constant import Interval, Exchange
from vnpy.trader.object import HistoryRequest
from vnpy_datamanager import DataManagerApp

# 策略导入
from strategies.cta_ema_adx_strategy import EmaAdxStrategy
from strategies.cta_zscore_strategy import ZScoreStrategy
from strategies.cta_custom_ratio_strategy import CustomRatioStrategy


class VnpyBacktester:
    """
    vn.py回测器
    
    提供完整的回测功能，包括单策略回测、参数优化、批量回测等
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化回测器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path or "config/backtest_config.json"
        self.config = self._load_config()
        
        # 初始化回测引擎
        self.engine = BacktestingEngine()
        
        # 策略映射
        self.strategy_classes = {
            "EmaAdxStrategy": EmaAdxStrategy,
            "ZScoreStrategy": ZScoreStrategy,
            "CustomRatioStrategy": CustomRatioStrategy
        }
        
        # 回测结果存储
        self.results = []
        
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
        """
        default_config = {
            "data": {
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "interval": "1m",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31"
            },
            "backtest": {
                "capital": 100000.0,
                "commission": 0.0003,
                "slippage": 0.0001,
                "size": 1,
                "pricetick": 0.01
            },
            "strategies": {
                "EmaAdxStrategy": {
                    "fast_window": 10,
                    "slow_window": 20,
                    "adx_window": 14,
                    "adx_threshold": 25.0,
                    "fixed_size": 100
                },
                "ZScoreStrategy": {
                    "window": 20,
                    "entry_threshold": 2.0,
                    "exit_threshold": 0.5,
                    "fixed_size": 100
                },
                "CustomRatioStrategy": {
                    "short_period": 5,
                    "long_period": 20,
                    "ratio_upper": 1.02,
                    "ratio_lower": 0.98,
                    "exit_ratio": 1.00,
                    "fixed_size": 100
                }
            },
            "optimization": {
                "EmaAdxStrategy": {
                    "fast_window": [5, 10, 15],
                    "slow_window": [20, 30, 40],
                    "adx_threshold": [20.0, 25.0, 30.0]
                },
                "ZScoreStrategy": {
                    "window": [15, 20, 25],
                    "entry_threshold": [1.5, 2.0, 2.5],
                    "exit_threshold": [0.3, 0.5, 0.7]
                },
                "CustomRatioStrategy": {
                    "short_period": [3, 5, 7],
                    "long_period": [15, 20, 25],
                    "ratio_upper": [1.015, 1.02, 1.025]
                }
            }
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                # 创建默认配置文件
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                print(f"已创建默认配置文件: {self.config_path}")
                return default_config
        except Exception as e:
            print(f"配置文件加载失败: {e}，使用默认配置")
            return default_config
            
    def setup_backtest_engine(self):
        """
        设置回测引擎参数
        """
        data_config = self.config["data"]
        backtest_config = self.config["backtest"]
        
        # 设置回测参数
        self.engine.set_parameters(
            vt_symbol=f"{data_config['symbol']}.{data_config['exchange']}",
            interval=getattr(Interval, data_config['interval'].upper()),
            start=datetime.strptime(data_config['start_date'], "%Y-%m-%d"),
            end=datetime.strptime(data_config['end_date'], "%Y-%m-%d"),
            capital=backtest_config['capital'],
            commission=backtest_config['commission'],
            slippage=backtest_config['slippage'],
            size=backtest_config['size'],
            pricetick=backtest_config['pricetick']
        )
        
        print(f"回测设置完成:")
        print(f"  标的: {data_config['symbol']}.{data_config['exchange']}")
        print(f"  周期: {data_config['interval']}")
        print(f"  时间: {data_config['start_date']} ~ {data_config['end_date']}")
        print(f"  资金: {backtest_config['capital']:,.0f}")
        print(f"  手续费: {backtest_config['commission']:.4f}")
        print(f"  滑点: {backtest_config['slippage']:.4f}")
        
    def run_single_backtest(self, strategy_name: str, strategy_setting: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行单个策略回测
        
        Args:
            strategy_name: 策略名称
            strategy_setting: 策略参数设置
            
        Returns:
            回测结果字典
        """
        if strategy_name not in self.strategy_classes:
            raise ValueError(f"未知策略: {strategy_name}")
            
        strategy_class = self.strategy_classes[strategy_name]
        
        # 使用配置文件中的参数或传入的参数
        if strategy_setting is None:
            strategy_setting = self.config["strategies"].get(strategy_name, {})
            
        print(f"\n开始回测策略: {strategy_name}")
        print(f"策略参数: {strategy_setting}")
        
        # 设置回测引擎
        self.setup_backtest_engine()
        
        # 添加策略
        self.engine.add_strategy(strategy_class, strategy_setting)
        
        # 加载数据
        print("正在加载历史数据...")
        self.engine.load_data()
        
        # 运行回测
        print("正在运行回测...")
        self.engine.run_backtesting()
        
        # 计算统计数据
        df = self.engine.calculate_result()
        statistics = self.engine.calculate_statistics()
        
        # 整理结果
        result = {
            "strategy_name": strategy_name,
            "strategy_setting": strategy_setting,
            "statistics": statistics,
            "trades_df": df,
            "timestamp": datetime.now().isoformat()
        }
        
        # 打印结果
        self._print_backtest_result(result)
        
        return result
        
    def run_optimization(self, strategy_name: str, target_name: str = "sharpe_ratio") -> List[Dict[str, Any]]:
        """
        运行参数优化
        
        Args:
            strategy_name: 策略名称
            target_name: 优化目标（如sharpe_ratio, total_return等）
            
        Returns:
            优化结果列表
        """
        if strategy_name not in self.strategy_classes:
            raise ValueError(f"未知策略: {strategy_name}")
            
        if strategy_name not in self.config["optimization"]:
            raise ValueError(f"策略 {strategy_name} 没有配置优化参数")
            
        strategy_class = self.strategy_classes[strategy_name]
        optimization_config = self.config["optimization"][strategy_name]
        
        print(f"\n开始参数优化: {strategy_name}")
        print(f"优化参数: {optimization_config}")
        print(f"优化目标: {target_name}")
        
        # 设置回测引擎
        self.setup_backtest_engine()
        
        # 添加策略
        base_setting = self.config["strategies"].get(strategy_name, {})
        self.engine.add_strategy(strategy_class, base_setting)
        
        # 加载数据
        print("正在加载历史数据...")
        self.engine.load_data()
        
        # 运行优化
        print("正在运行参数优化...")
        optimization_results = self.engine.run_optimization(
            optimization_setting=optimization_config,
            target_name=target_name
        )
        
        # 整理结果
        results = []
        for result in optimization_results:
            results.append({
                "strategy_name": strategy_name,
                "parameters": result[0],
                "target_value": result[1],
                "statistics": result[2] if len(result) > 2 else None,
                "timestamp": datetime.now().isoformat()
            })
            
        # 按目标值排序
        results.sort(key=lambda x: x["target_value"], reverse=True)
        
        # 打印最佳结果
        print(f"\n参数优化完成，共 {len(results)} 组结果")
        if results:
            best_result = results[0]
            print(f"最佳参数组合:")
            print(f"  参数: {best_result['parameters']}")
            print(f"  {target_name}: {best_result['target_value']:.4f}")
            
        return results
        
    def run_batch_backtest(self, strategy_names: List[str] = None) -> List[Dict[str, Any]]:
        """
        运行批量回测
        
        Args:
            strategy_names: 策略名称列表，None表示回测所有策略
            
        Returns:
            回测结果列表
        """
        if strategy_names is None:
            strategy_names = list(self.strategy_classes.keys())
            
        print(f"\n开始批量回测，策略数量: {len(strategy_names)}")
        
        results = []
        for strategy_name in strategy_names:
            try:
                result = self.run_single_backtest(strategy_name)
                results.append(result)
            except Exception as e:
                print(f"策略 {strategy_name} 回测失败: {e}")
                
        # 比较结果
        self._compare_strategies(results)
        
        return results
        
    def _print_backtest_result(self, result: Dict[str, Any]):
        """
        打印回测结果
        
        Args:
            result: 回测结果字典
        """
        statistics = result["statistics"]
        
        print(f"\n{'='*60}")
        print(f"策略: {result['strategy_name']}")
        print(f"参数: {result['strategy_setting']}")
        print(f"{'='*60}")
        
        # 核心指标
        print(f"总收益率: {statistics.get('total_return', 0):.2%}")
        print(f"年化收益率: {statistics.get('annual_return', 0):.2%}")
        print(f"最大回撤: {statistics.get('max_drawdown', 0):.2%}")
        print(f"夏普比率: {statistics.get('sharpe_ratio', 0):.4f}")
        print(f"卡尔马比率: {statistics.get('calmar_ratio', 0):.4f}")
        
        # 交易统计
        print(f"\n交易统计:")
        print(f"总交易次数: {statistics.get('total_trades', 0)}")
        print(f"盈利交易: {statistics.get('winning_trades', 0)}")
        print(f"亏损交易: {statistics.get('losing_trades', 0)}")
        print(f"胜率: {statistics.get('win_rate', 0):.2%}")
        print(f"平均盈利: {statistics.get('average_winning', 0):.2f}")
        print(f"平均亏损: {statistics.get('average_losing', 0):.2f}")
        print(f"盈亏比: {statistics.get('profit_loss_ratio', 0):.2f}")
        
    def _compare_strategies(self, results: List[Dict[str, Any]]):
        """
        比较多个策略的回测结果
        
        Args:
            results: 回测结果列表
        """
        if len(results) < 2:
            return
            
        print(f"\n{'='*80}")
        print(f"策略比较 (共{len(results)}个策略)")
        print(f"{'='*80}")
        
        # 表头
        print(f"{'策略名称':<20} {'总收益率':<10} {'夏普比率':<10} {'最大回撤':<10} {'胜率':<8}")
        print("-" * 80)
        
        # 按夏普比率排序
        sorted_results = sorted(results, key=lambda x: x["statistics"].get("sharpe_ratio", 0), reverse=True)
        
        for result in sorted_results:
            stats = result["statistics"]
            print(f"{result['strategy_name']:<20} "
                  f"{stats.get('total_return', 0):>9.2%} "
                  f"{stats.get('sharpe_ratio', 0):>9.4f} "
                  f"{stats.get('max_drawdown', 0):>9.2%} "
                  f"{stats.get('win_rate', 0):>7.2%}")
                  
    def save_results(self, results: List[Dict[str, Any]], filename: str = None):
        """
        保存回测结果到文件
        
        Args:
            results: 回测结果列表
            filename: 保存文件名
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_results_{timestamp}.json"
            
        # 创建结果目录
        results_dir = "results"
        os.makedirs(results_dir, exist_ok=True)
        
        filepath = os.path.join(results_dir, filename)
        
        # 处理不可序列化的对象
        serializable_results = []
        for result in results:
            serializable_result = result.copy()
            # 移除DataFrame对象
            if "trades_df" in serializable_result:
                del serializable_result["trades_df"]
            serializable_results.append(serializable_result)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=4, ensure_ascii=False)
            
        print(f"\n回测结果已保存到: {filepath}")
        

def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description="vn.py框架回测脚本")
    parser.add_argument("--strategy", type=str, help="策略名称")
    parser.add_argument("--optimize", action="store_true", help="运行参数优化")
    parser.add_argument("--batch", action="store_true", help="批量回测所有策略")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--target", type=str, default="sharpe_ratio", help="优化目标")
    parser.add_argument("--save", action="store_true", help="保存结果到文件")
    
    args = parser.parse_args()
    
    # 创建回测器
    backtester = VnpyBacktester(args.config)
    
    try:
        results = []
        
        if args.batch:
            # 批量回测
            results = backtester.run_batch_backtest()
            
        elif args.strategy:
            if args.optimize:
                # 参数优化
                optimization_results = backtester.run_optimization(args.strategy, args.target)
                print(f"\n优化完成，最佳参数组合数量: {len(optimization_results)}")
                
                # 使用最佳参数运行回测
                if optimization_results:
                    best_params = optimization_results[0]["parameters"]
                    print(f"\n使用最佳参数运行回测: {best_params}")
                    result = backtester.run_single_backtest(args.strategy, best_params)
                    results = [result]
            else:
                # 单策略回测
                result = backtester.run_single_backtest(args.strategy)
                results = [result]
                
        else:
            print("请指定策略名称 (--strategy) 或使用批量回测 (--batch)")
            print("可用策略:", list(backtester.strategy_classes.keys()))
            return
            
        # 保存结果
        if args.save and results:
            backtester.save_results(results)
            
    except Exception as e:
        print(f"回测执行失败: {e}")
        import traceback
        traceback.print_exc()
        

if __name__ == "__main__":
    main()