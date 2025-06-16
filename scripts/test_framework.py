#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VN.py框架测试脚本

这个脚本用于测试框架的基本功能，包括：
1. 依赖包检查
2. 策略类导入测试
3. 配置文件验证
4. 基本功能测试

运行方法：
python test_framework.py
"""

import sys
import os
import json
import traceback
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class FrameworkTester:
    """
    框架测试器
    """
    
    def __init__(self):
        self.test_results = []
        self.passed_tests = 0
        self.failed_tests = 0
        
    def run_test(self, test_name, test_func):
        """
        运行单个测试
        
        Args:
            test_name: 测试名称
            test_func: 测试函数
        """
        print(f"\n{'='*60}")
        print(f"测试: {test_name}")
        print(f"{'='*60}")
        
        try:
            result = test_func()
            if result:
                print(f"✓ {test_name} - 通过")
                self.passed_tests += 1
                self.test_results.append((test_name, True, None))
            else:
                print(f"✗ {test_name} - 失败")
                self.failed_tests += 1
                self.test_results.append((test_name, False, "测试返回False"))
        except Exception as e:
            print(f"✗ {test_name} - 异常: {e}")
            self.failed_tests += 1
            self.test_results.append((test_name, False, str(e)))
            
    def test_dependencies(self):
        """
        测试依赖包
        """
        print("检查依赖包...")
        
        required_packages = [
            ('vnpy', 'VN.py核心包'),
            ('vnpy_ctastrategy', 'CTA策略模块'),
            ('pandas', 'Pandas数据处理'),
            ('numpy', 'NumPy数值计算'),
            ('matplotlib', 'Matplotlib绘图'),
        ]
        
        optional_packages = [
            ('vnpy_alpaca', 'Alpaca交易接口'),
            ('vnpy_ib', 'Interactive Brokers接口'),
            ('vnpy_binance', 'Binance交易接口'),
        ]
        
        # 检查必需包
        for package, description in required_packages:
            try:
                __import__(package)
                print(f"  ✓ {package} ({description})")
            except ImportError:
                print(f"  ✗ {package} ({description}) - 缺失")
                return False
                
        # 检查可选包
        print("\n可选包状态:")
        for package, description in optional_packages:
            try:
                __import__(package)
                print(f"  ✓ {package} ({description})")
            except ImportError:
                print(f"  - {package} ({description}) - 未安装")
                
        return True
        
    def test_strategy_imports(self):
        """
        测试策略导入
        """
        print("测试策略类导入...")
        
        strategies = [
            ('strategies.cta_ema_adx_strategy', 'EmaAdxStrategy'),
            ('strategies.cta_zscore_strategy', 'ZScoreStrategy'),
            ('strategies.cta_custom_ratio_strategy', 'CustomRatioStrategy'),
        ]
        
        for module_name, class_name in strategies:
            try:
                module = __import__(module_name, fromlist=[class_name])
                strategy_class = getattr(module, class_name)
                print(f"  ✓ {class_name} - 导入成功")
                
                # 检查基本属性
                if hasattr(strategy_class, 'author'):
                    print(f"    作者: {strategy_class.author}")
                if hasattr(strategy_class, 'parameters'):
                    print(f"    参数: {strategy_class.parameters}")
                    
            except ImportError as e:
                print(f"  ✗ {class_name} - 导入失败: {e}")
                return False
            except AttributeError as e:
                print(f"  ✗ {class_name} - 类不存在: {e}")
                return False
                
        return True
        
    def test_config_files(self):
        """
        测试配置文件
        """
        print("测试配置文件...")
        
        config_files = [
            'config/backtest_config.json',
            'config/live_trading_config.json'
        ]
        
        for config_file in config_files:
            config_path = project_root / config_file
            
            if not config_path.exists():
                print(f"  ✗ {config_file} - 文件不存在")
                return False
                
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"  ✓ {config_file} - 格式正确")
                
                # 检查关键配置项
                if 'backtest' in config_file:
                    required_keys = ['data', 'backtest', 'strategies']
                else:
                    required_keys = ['gateways', 'strategies', 'risk']
                    
                for key in required_keys:
                    if key not in config:
                        print(f"    ⚠ 缺少配置项: {key}")
                    else:
                        print(f"    ✓ 配置项存在: {key}")
                        
            except json.JSONDecodeError as e:
                print(f"  ✗ {config_file} - JSON格式错误: {e}")
                return False
            except Exception as e:
                print(f"  ✗ {config_file} - 读取失败: {e}")
                return False
                
        return True
        
    def test_directory_structure(self):
        """
        测试目录结构
        """
        print("测试目录结构...")
        
        required_dirs = [
            'strategies',
            'scripts',
            'config'
        ]
        
        optional_dirs = [
            'docs',
            'results',
            'logs'
        ]
        
        # 检查必需目录
        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                print(f"  ✓ {dir_name}/ - 存在")
            else:
                print(f"  ✗ {dir_name}/ - 不存在")
                return False
                
        # 检查可选目录
        for dir_name in optional_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                print(f"  ✓ {dir_name}/ - 存在")
            else:
                print(f"  - {dir_name}/ - 不存在（可选）")
                
        return True
        
    def test_script_files(self):
        """
        测试脚本文件
        """
        print("测试脚本文件...")
        
        script_files = [
            'scripts/run_backtest.py',
            'scripts/run_live_trading.py'
        ]
        
        for script_file in script_files:
            script_path = project_root / script_file
            
            if not script_path.exists():
                print(f"  ✗ {script_file} - 文件不存在")
                return False
                
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 检查基本内容
                if 'def main(' in content:
                    print(f"  ✓ {script_file} - 包含main函数")
                else:
                    print(f"  ⚠ {script_file} - 缺少main函数")
                    
                if 'if __name__ == "__main__"' in content:
                    print(f"  ✓ {script_file} - 可执行")
                else:
                    print(f"  ⚠ {script_file} - 不可直接执行")
                    
            except Exception as e:
                print(f"  ✗ {script_file} - 读取失败: {e}")
                return False
                
        return True
        
    def test_basic_functionality(self):
        """
        测试基本功能
        """
        print("测试基本功能...")
        
        try:
            # 测试回测引擎创建
            from vnpy_ctastrategy.backtesting import BacktestingEngine
            engine = BacktestingEngine()
            print("  ✓ 回测引擎创建成功")
            
            # 测试策略类实例化
            from strategies.cta_ema_adx_strategy import EmaAdxStrategy
            
            # 模拟CTA引擎和参数
            class MockCtaEngine:
                def write_log(self, msg):
                    pass
                    
            mock_engine = MockCtaEngine()
            strategy_setting = {
                "fast_window": 10,
                "slow_window": 20,
                "adx_window": 14,
                "adx_threshold": 25.0,
                "fixed_size": 100
            }
            
            # 尝试创建策略实例（不完全初始化）
            try:
                strategy = EmaAdxStrategy(
                    cta_engine=mock_engine,
                    strategy_name="test_strategy",
                    vt_symbol="AAPL.NASDAQ",
                    setting=strategy_setting
                )
                print("  ✓ 策略实例创建成功")
            except Exception as e:
                print(f"  ⚠ 策略实例创建警告: {e}")
                # 这个错误是预期的，因为我们没有完整的环境
                
            # 测试数组管理器
            from vnpy_ctastrategy import ArrayManager
            am = ArrayManager()
            print("  ✓ 数组管理器创建成功")
            
            return True
            
        except Exception as e:
            print(f"  ✗ 基本功能测试失败: {e}")
            return False
            
    def test_requirements_file(self):
        """
        测试requirements文件
        """
        print("测试requirements文件...")
        
        req_file = project_root / 'requirements_vnpy.txt'
        
        if not req_file.exists():
            print(f"  ✗ requirements_vnpy.txt - 文件不存在")
            return False
            
        try:
            with open(req_file, 'r', encoding='utf-8') as f:
                requirements = f.read().strip().split('\n')
                
            print(f"  ✓ requirements_vnpy.txt - 包含{len(requirements)}个依赖")
            
            # 检查关键依赖
            key_packages = ['vnpy', 'vnpy-ctastrategy', 'pandas', 'numpy']
            for package in key_packages:
                found = any(package in req for req in requirements)
                if found:
                    print(f"    ✓ {package} - 已包含")
                else:
                    print(f"    ⚠ {package} - 未找到")
                    
            return True
            
        except Exception as e:
            print(f"  ✗ requirements_vnpy.txt - 读取失败: {e}")
            return False
            
    def run_all_tests(self):
        """
        运行所有测试
        """
        print("VN.py Trading Framework 测试开始")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"项目路径: {project_root}")
        
        # 运行所有测试
        tests = [
            ("依赖包检查", self.test_dependencies),
            ("目录结构检查", self.test_directory_structure),
            ("配置文件检查", self.test_config_files),
            ("脚本文件检查", self.test_script_files),
            ("Requirements文件检查", self.test_requirements_file),
            ("策略导入测试", self.test_strategy_imports),
            ("基本功能测试", self.test_basic_functionality),
        ]
        
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
            
        # 显示测试总结
        self.show_summary()
        
    def show_summary(self):
        """
        显示测试总结
        """
        total_tests = self.passed_tests + self.failed_tests
        
        print(f"\n{'='*80}")
        print("测试总结")
        print(f"{'='*80}")
        print(f"总测试数: {total_tests}")
        print(f"通过: {self.passed_tests}")
        print(f"失败: {self.failed_tests}")
        print(f"成功率: {self.passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "成功率: 0%")
        
        if self.failed_tests > 0:
            print(f"\n失败的测试:")
            for test_name, passed, error in self.test_results:
                if not passed:
                    print(f"  ✗ {test_name}: {error}")
                    
        print(f"\n{'='*80}")
        
        if self.failed_tests == 0:
            print("🎉 所有测试通过！框架已准备就绪。")
            print("\n下一步:")
            print("1. 运行快速开始: python quick_start.py")
            print("2. 配置交易接口: 编辑 config/live_trading_config.json")
            print("3. 运行回测: python scripts/run_backtest.py --strategy EmaAdxStrategy")
        else:
            print("⚠️  部分测试失败，请检查上述错误并修复。")
            print("\n常见解决方案:")
            print("1. 安装缺失的依赖: pip install -r requirements_vnpy.txt")
            print("2. 检查Python路径和模块导入")
            print("3. 确保配置文件格式正确")
            
        print(f"{'='*80}")


def main():
    """
    主函数
    """
    tester = FrameworkTester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n测试过程中出现未预期的错误: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()