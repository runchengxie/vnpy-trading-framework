#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VN.py框架快速开始示例

这个脚本展示了如何快速开始使用vnpy框架进行策略回测和实盘交易。
包含了最基本的使用方法和配置示例。

运行方法：
python quick_start.py
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
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# vnpy相关导入
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy.trader.constant import Interval, Exchange
from vnpy.trader.object import HistoryRequest

# 策略导入
from strategies.cta_ema_adx_strategy import EmaAdxStrategy
from strategies.cta_zscore_strategy import ZScoreStrategy
from strategies.cta_custom_ratio_strategy import CustomRatioStrategy


def quick_backtest_demo():
    """
    快速回测演示
    
    展示如何使用vnpy进行简单的策略回测
    """
    print("=" * 60)
    print("VN.py框架快速回测演示")
    print("=" * 60)
    
    # 创建回测引擎
    engine = BacktestingEngine()
    
    # 设置回测参数
    print("\n1. 设置回测参数...")
    engine.set_parameters(
        vt_symbol="AAPL.NASDAQ",  # 交易标的
        interval=Interval.MINUTE,  # K线周期
        start=datetime(2023, 1, 1),  # 开始时间
        end=datetime(2023, 6, 30),   # 结束时间
        capital=100000,              # 初始资金
        commission=0.0003,           # 手续费率
        slippage=0.0001,            # 滑点
        size=1,                     # 合约大小
        pricetick=0.01              # 最小价格变动
    )
    
    print("回测参数设置完成:")
    print(f"  标的: AAPL.NASDAQ")
    print(f"  周期: 1分钟")
    print(f"  时间: 2023-01-01 ~ 2023-06-30")
    print(f"  资金: $100,000")
    
    # 添加策略
    print("\n2. 添加EMA+ADX策略...")
    strategy_setting = {
        "fast_window": 10,      # 快速EMA周期
        "slow_window": 20,      # 慢速EMA周期
        "adx_window": 14,       # ADX周期
        "adx_threshold": 25.0,  # ADX阈值
        "fixed_size": 100       # 固定交易数量
    }
    
    engine.add_strategy(EmaAdxStrategy, strategy_setting)
    print(f"策略参数: {strategy_setting}")
    
    # 加载数据
    print("\n3. 加载历史数据...")
    try:
        engine.load_data()
        print("历史数据加载完成")
    except Exception as e:
        print(f"数据加载失败: {e}")
        print("提示: 请确保网络连接正常，或配置本地数据源")
        return
    
    # 运行回测
    print("\n4. 运行回测...")
    try:
        engine.run_backtesting()
        print("回测运行完成")
    except Exception as e:
        print(f"回测运行失败: {e}")
        return
    
    # 计算结果
    print("\n5. 计算回测结果...")
    try:
        # 获取交易记录
        df = engine.calculate_result()
        print(f"交易记录数量: {len(df)}")
        
        # 计算统计指标
        statistics = engine.calculate_statistics()
        
        # 显示关键指标
        print("\n" + "=" * 40)
        print("回测结果统计")
        print("=" * 40)
        print(f"总收益率: {statistics.get('total_return', 0):.2%}")
        print(f"年化收益率: {statistics.get('annual_return', 0):.2%}")
        print(f"最大回撤: {statistics.get('max_drawdown', 0):.2%}")
        print(f"夏普比率: {statistics.get('sharpe_ratio', 0):.4f}")
        print(f"总交易次数: {statistics.get('total_trades', 0)}")
        print(f"胜率: {statistics.get('win_rate', 0):.2%}")
        
        # 显示前几笔交易
        if len(df) > 0:
            print("\n前5笔交易记录:")
            print(df.head().to_string())
            
    except Exception as e:
        print(f"结果计算失败: {e}")
        
    print("\n" + "=" * 60)
    print("快速回测演示完成")
    print("=" * 60)


def strategy_comparison_demo():
    """
    策略对比演示
    
    展示如何对比不同策略的表现
    """
    print("\n" + "=" * 60)
    print("策略对比演示")
    print("=" * 60)
    
    strategies = [
        ("EMA+ADX策略", EmaAdxStrategy, {
            "fast_window": 10,
            "slow_window": 20,
            "adx_window": 14,
            "adx_threshold": 25.0,
            "fixed_size": 100
        }),
        ("Z-Score策略", ZScoreStrategy, {
            "window": 20,
            "entry_threshold": 2.0,
            "exit_threshold": 0.5,
            "fixed_size": 100
        }),
        ("自定义比率策略", CustomRatioStrategy, {
            "short_period": 5,
            "long_period": 20,
            "ratio_upper": 1.02,
            "ratio_lower": 0.98,
            "exit_ratio": 1.00,
            "fixed_size": 100
        })
    ]
    
    results = []
    
    for strategy_name, strategy_class, setting in strategies:
        print(f"\n测试策略: {strategy_name}")
        
        try:
            # 创建新的回测引擎
            engine = BacktestingEngine()
            
            # 设置相同的回测参数
            engine.set_parameters(
                vt_symbol="AAPL.NASDAQ",
                interval=Interval.MINUTE,
                start=datetime(2023, 1, 1),
                end=datetime(2023, 3, 31),  # 缩短时间以加快演示
                capital=100000,
                commission=0.0003,
                slippage=0.0001,
                size=1,
                pricetick=0.01
            )
            
            # 添加策略
            engine.add_strategy(strategy_class, setting)
            
            # 运行回测
            engine.load_data()
            engine.run_backtesting()
            
            # 计算结果
            df = engine.calculate_result()
            statistics = engine.calculate_statistics()
            
            results.append({
                "name": strategy_name,
                "total_return": statistics.get('total_return', 0),
                "sharpe_ratio": statistics.get('sharpe_ratio', 0),
                "max_drawdown": statistics.get('max_drawdown', 0),
                "win_rate": statistics.get('win_rate', 0),
                "total_trades": statistics.get('total_trades', 0)
            })
            
            print(f"  ✓ 完成")
            
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            results.append({
                "name": strategy_name,
                "total_return": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "total_trades": 0
            })
    
    # 显示对比结果
    print("\n" + "=" * 80)
    print("策略对比结果")
    print("=" * 80)
    print(f"{'策略名称':<15} {'总收益率':<10} {'夏普比率':<10} {'最大回撤':<10} {'胜率':<8} {'交易次数':<8}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['name']:<15} "
              f"{result['total_return']:>9.2%} "
              f"{result['sharpe_ratio']:>9.4f} "
              f"{result['max_drawdown']:>9.2%} "
              f"{result['win_rate']:>7.2%} "
              f"{result['total_trades']:>7d}")
    
    print("\n" + "=" * 60)
    print("策略对比演示完成")
    print("=" * 60)


def live_trading_setup_demo():
    """
    实盘交易设置演示
    
    展示如何配置实盘交易（不实际连接）
    """
    print("\n" + "=" * 60)
    print("实盘交易设置演示")
    print("=" * 60)
    
    print("\n实盘交易设置步骤:")
    print("\n1. 配置交易接口")
    print("   编辑 config/live_trading_config.json:")
    print("   {")
    print('     "gateways": {')
    print('       "alpaca": {')
    print('         "enabled": true,')
    print('         "paper_trading": true,')
    print('         "key_id": "YOUR_ALPACA_KEY_ID",')
    print('         "secret_key": "YOUR_ALPACA_SECRET_KEY"')
    print('       }')
    print('     }')
    print("   }")
    
    print("\n2. 配置策略参数")
    print("   在配置文件中添加策略设置:")
    print("   {")
    print('     "strategies": {')
    print('       "EmaAdxStrategy_AAPL": {')
    print('         "class_name": "EmaAdxStrategy",')
    print('         "vt_symbol": "AAPL.NASDAQ",')
    print('         "setting": {')
    print('           "fast_window": 10,')
    print('           "slow_window": 20,')
    print('           "fixed_size": 100')
    print('         }')
    print('       }')
    print('     }')
    print("   }")
    
    print("\n3. 设置风险控制")
    print("   配置风险管理参数:")
    print("   - 最大日内亏损限制")
    print("   - 单笔订单大小限制")
    print("   - 允许交易的品种")
    print("   - 交易时间限制")
    
    print("\n4. 启动实盘交易")
    print("   模拟交易: python scripts/run_live_trading.py --paper")
    print("   实盘交易: python scripts/run_live_trading.py --live")
    print("   图形界面: python scripts/run_live_trading.py --paper --gui")
    
    print("\n⚠️  重要提醒:")
    print("   - 实盘交易前请充分测试策略")
    print("   - 建议先使用模拟交易验证")
    print("   - 确保风险控制参数设置合理")
    print("   - 监控系统运行状态")
    
    print("\n" + "=" * 60)
    print("实盘交易设置演示完成")
    print("=" * 60)


def main():
    """
    主函数
    """
    print("欢迎使用 VN.py Trading Framework!")
    print("\n这个快速开始脚本将演示框架的主要功能:")
    print("1. 策略回测")
    print("2. 策略对比")
    print("3. 实盘交易设置")
    
    try:
        # 检查依赖
        print("\n检查依赖包...")
        import vnpy
        import vnpy_ctastrategy
        print(f"✓ vnpy版本: {vnpy.__version__}")
        print("✓ 依赖包检查通过")
        
    except ImportError as e:
        print(f"✗ 依赖包缺失: {e}")
        print("\n请先安装依赖包:")
        print("pip install -r requirements_vnpy.txt")
        return
    
    # 运行演示
    try:
        # 1. 快速回测演示
        quick_backtest_demo()
        
        # 询问是否继续
        response = input("\n是否继续策略对比演示? (y/n): ")
        if response.lower() == 'y':
            strategy_comparison_demo()
        
        # 3. 实盘交易设置演示
        live_trading_setup_demo()
        
    except KeyboardInterrupt:
        print("\n\n演示被用户中断")
    except Exception as e:
        print(f"\n演示过程中出现错误: {e}")
        print("\n可能的原因:")
        print("- 网络连接问题（无法获取数据）")
        print("- 依赖包版本不兼容")
        print("- 系统配置问题")
        print("\n请检查错误信息并参考文档解决")
    
    print("\n感谢使用 VN.py Trading Framework!")
    print("\n更多信息请参考:")
    print("- 项目文档: README.md")
    print("- 策略开发: strategies/ 目录")
    print("- 配置文件: config/ 目录")
    print("- 运行脚本: scripts/ 目录")


if __name__ == "__main__":
    main()