#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VN.py Trading Framework 安装脚本

这个脚本帮助用户快速设置VN.py交易框架环境，包括：
1. 检查Python版本
2. 安装依赖包
3. 创建必要的目录
4. 初始化配置文件
5. 验证安装

运行方法：
python install.py
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime


class FrameworkInstaller:
    """
    框架安装器
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.python_executable = sys.executable
        
    def check_python_version(self):
        """
        检查Python版本
        """
        print("检查Python版本...")
        
        version = sys.version_info
        print(f"当前Python版本: {version.major}.{version.minor}.{version.micro}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print("❌ Python版本过低，需要Python 3.8或更高版本")
            return False
            
        print("✅ Python版本符合要求")
        return True
        
    def install_dependencies(self):
        """
        安装依赖包
        """
        print("\n安装依赖包...")
        
        requirements_file = self.project_root / "requirements_vnpy.txt"
        
        if not requirements_file.exists():
            print("❌ requirements_vnpy.txt 文件不存在")
            return False
            
        try:
            # 升级pip
            print("升级pip...")
            subprocess.run([
                self.python_executable, "-m", "pip", "install", "--upgrade", "pip"
            ], check=True)
            
            # 安装依赖
            print("安装VN.py框架依赖...")
            subprocess.run([
                self.python_executable, "-m", "pip", "install", "-r", str(requirements_file)
            ], check=True)
            
            print("✅ 依赖包安装完成")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 依赖包安装失败: {e}")
            print("\n请尝试手动安装:")
            print(f"pip install -r {requirements_file}")
            return False
            
    def create_directories(self):
        """
        创建必要的目录
        """
        print("\n创建必要的目录...")
        
        directories = [
            "logs",
            "results",
            "data",
            "docs"
        ]
        
        for dir_name in directories:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"✅ 创建目录: {dir_name}/")
            else:
                print(f"📁 目录已存在: {dir_name}/")
                
        return True
        
    def create_gitignore(self):
        """
        创建.gitignore文件
        """
        print("\n创建.gitignore文件...")
        
        gitignore_content = """
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
PIPFILE.lock

# Virtual Environment
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# VN.py specific
logs/
results/
data/
*.db
*.sqlite

# Trading specific
*.key
*.secret
api_keys.json
trade_records/

# OS
.DS_Store
Thumbs.db

# Jupyter Notebook
.ipynb_checkpoints

# pytest
.pytest_cache/
.coverage
htmlcov/

# mypy
.mypy_cache/
.dmypy.json
dmypy.json
"""
        
        gitignore_path = self.project_root / ".gitignore"
        
        if not gitignore_path.exists():
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(gitignore_content.strip())
            print("✅ 创建.gitignore文件")
        else:
            print("📄 .gitignore文件已存在")
            
        return True
        
    def verify_installation(self):
        """
        验证安装
        """
        print("\n验证安装...")
        
        try:
            # 测试核心包导入
            import vnpy
            print(f"✅ VN.py核心包 (版本: {vnpy.__version__})")
            
            import vnpy_ctastrategy
            print("✅ CTA策略模块")
            
            # 测试策略导入
            sys.path.insert(0, str(self.project_root))
            
            from strategies.cta_ema_adx_strategy import EmaAdxStrategy
            print("✅ EMA ADX策略")
            
            from strategies.cta_zscore_strategy import ZScoreStrategy
            print("✅ Z-Score策略")
            
            from strategies.cta_custom_ratio_strategy import CustomRatioStrategy
            print("✅ 自定义比率策略")
            
            print("✅ 安装验证通过")
            return True
            
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 验证失败: {e}")
            return False
            
    def show_next_steps(self):
        """
        显示后续步骤
        """
        print("\n" + "="*80)
        print("🎉 VN.py Trading Framework 安装完成！")
        print("="*80)
        
        print("\n📋 后续步骤:")
        print("\n1. 测试框架:")
        print("   python scripts/test_framework.py")
        
        print("\n2. 快速开始:")
        print("   python scripts/quick_start.py")
        
        print("\n3. 下载历史数据:")
        print("   python scripts/download_data.py --symbol SPY --days 365")
        
        print("\n4. 配置交易接口:")
        print("   编辑 config/live_trading_config.json")
        print("   添加你的API密钥和交易参数")
        
        print("\n5. 运行回测:")
        print("   python scripts/run_backtest.py --strategy EmaAdxStrategy")
        
        print("\n6. 启动实盘交易:")
        print("   python scripts/run_live_trading.py --mode paper")
        
        print("\n📚 文档和帮助:")
        print("   - 查看 README.md 了解详细使用说明")
        print("   - 访问 https://www.vnpy.com 获取官方文档")
        print("   - 策略开发指南在 strategies/ 目录中")
        
        print("\n⚠️  重要提醒:")
        print("   - 实盘交易前请充分测试策略")
        print("   - 妥善保管API密钥，不要提交到版本控制")
        print("   - 设置合理的风险控制参数")
        
        print("\n" + "="*80)
        
    def run_installation(self):
        """
        运行完整安装流程
        """
        print("VN.py Trading Framework 安装程序")
        print(f"安装时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"项目路径: {self.project_root}")
        print("="*80)
        
        steps = [
            ("检查Python版本", self.check_python_version),
            ("安装依赖包", self.install_dependencies),
            ("创建目录结构", self.create_directories),
            ("创建.gitignore", self.create_gitignore),
            ("验证安装", self.verify_installation),
        ]
        
        failed_steps = []
        
        for step_name, step_func in steps:
            print(f"\n{'='*60}")
            print(f"步骤: {step_name}")
            print(f"{'='*60}")
            
            try:
                if not step_func():
                    failed_steps.append(step_name)
                    print(f"❌ {step_name} 失败")
                else:
                    print(f"✅ {step_name} 完成")
            except Exception as e:
                failed_steps.append(step_name)
                print(f"❌ {step_name} 异常: {e}")
                
        # 显示安装结果
        print("\n" + "="*80)
        print("安装结果")
        print("="*80)
        
        if failed_steps:
            print(f"❌ 安装未完全成功，失败步骤: {', '.join(failed_steps)}")
            print("\n请检查错误信息并手动解决问题，然后重新运行安装程序。")
            
            print("\n常见问题解决方案:")
            print("1. 网络问题: 使用国内镜像源")
            print("   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements_vnpy.txt")
            print("2. 权限问题: 使用管理员权限运行")
            print("3. 版本冲突: 创建虚拟环境")
            print("   python -m venv vnpy_env")
            print("   vnpy_env\\Scripts\\activate  # Windows")
            print("   source vnpy_env/bin/activate  # Linux/Mac")
            
        else:
            print("✅ 安装完全成功！")
            self.show_next_steps()
            

def main():
    """
    主函数
    """
    installer = FrameworkInstaller()
    
    try:
        installer.run_installation()
    except KeyboardInterrupt:
        print("\n\n安装被用户中断")
    except Exception as e:
        print(f"\n安装过程中出现未预期的错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()