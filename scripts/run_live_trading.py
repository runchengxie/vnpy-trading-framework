#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vn.py框架实盘交易脚本

这个脚本提供了完整的实盘/模拟交易功能，支持：
1. 多种交易接口（Alpaca、IB、CTP等）
2. 策略实例管理
3. 风险控制
4. 实时监控
5. 异常处理和恢复

使用方法：
1. 模拟交易：python run_live_trading.py --paper
2. 实盘交易：python run_live_trading.py --live
3. 指定策略：python run_live_trading.py --strategy EmaAdxStrategy --paper
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
import time
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading
from queue import Queue

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# vnpy相关导入
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy.trader.setting import SETTINGS
from vnpy_ctastrategy import CtaStrategyApp
from vnpy_ctastrategy.engine import CtaEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway

# 交易接口导入（根据需要启用）
try:
    from vnpy_alpaca import AlpacaGateway
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("警告: Alpaca接口不可用，请安装 vnpy_alpaca")

try:
    from vnpy_ib import IbGateway
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    print("警告: IB接口不可用，请安装 vnpy_ib")

# 策略导入
from strategies.cta_ema_adx_strategy import EmaAdxStrategy
from strategies.cta_zscore_strategy import ZScoreStrategy
from strategies.cta_custom_ratio_strategy import CustomRatioStrategy


class LiveTradingManager:
    """
    实盘交易管理器
    
    负责管理实盘交易的整个生命周期，包括：
    - 交易接口连接
    - 策略实例管理
    - 风险控制
    - 异常处理
    - 状态监控
    """
    
    def __init__(self, config_path: str = None, use_gui: bool = False):
        """
        初始化交易管理器
        
        Args:
            config_path: 配置文件路径
            use_gui: 是否使用图形界面
        """
        self.config_path = config_path or "config/live_trading_config.json"
        self.config = self._load_config()
        self.use_gui = use_gui
        
        # 初始化事件引擎和主引擎
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        
        # 添加CTA策略应用
        self.main_engine.add_app(CtaStrategyApp)
        self.cta_engine = self.main_engine.get_app("CtaStrategy")
        
        # 策略映射
        self.strategy_classes = {
            "EmaAdxStrategy": EmaAdxStrategy,
            "ZScoreStrategy": ZScoreStrategy,
            "CustomRatioStrategy": CustomRatioStrategy
        }
        
        # 运行状态
        self.is_running = False
        self.connected_gateways = set()
        self.active_strategies = {}
        
        # 风险控制
        self.risk_manager = RiskManager(self.config.get("risk", {}))
        
        # 性能监控
        self.performance_monitor = PerformanceMonitor()
        
        # 异常处理
        self.exception_handler = ExceptionHandler()
        
        # GUI相关
        self.main_window = None
        self.qapp = None
        
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
        """
        default_config = {
            "gateways": {
                "alpaca": {
                    "enabled": True,
                    "paper_trading": True,
                    "key_id": "YOUR_ALPACA_KEY_ID",
                    "secret_key": "YOUR_ALPACA_SECRET_KEY",
                    "server": "PAPER"  # PAPER or LIVE
                },
                "ib": {
                    "enabled": False,
                    "host": "127.0.0.1",
                    "port": 7497,
                    "client_id": 1
                }
            },
            "strategies": {
                "EmaAdxStrategy_AAPL": {
                    "class_name": "EmaAdxStrategy",
                    "vt_symbol": "AAPL.NASDAQ",
                    "setting": {
                        "fast_window": 10,
                        "slow_window": 20,
                        "adx_window": 14,
                        "adx_threshold": 25.0,
                        "fixed_size": 100
                    }
                },
                "ZScoreStrategy_TSLA": {
                    "class_name": "ZScoreStrategy",
                    "vt_symbol": "TSLA.NASDAQ",
                    "setting": {
                        "window": 20,
                        "entry_threshold": 2.0,
                        "exit_threshold": 0.5,
                        "fixed_size": 50
                    }
                }
            },
            "risk": {
                "max_daily_loss": 5000.0,
                "max_position_size": 1000,
                "max_order_size": 500,
                "allowed_symbols": ["AAPL.NASDAQ", "TSLA.NASDAQ", "MSFT.NASDAQ"],
                "trading_hours": {
                    "start": "09:30",
                    "end": "16:00",
                    "timezone": "US/Eastern"
                }
            },
            "monitoring": {
                "log_level": "INFO",
                "save_trades": True,
                "performance_update_interval": 60,
                "health_check_interval": 30
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
                print("请修改配置文件中的API密钥等信息后重新运行")
                return default_config
        except Exception as e:
            print(f"配置文件加载失败: {e}，使用默认配置")
            return default_config
            
    def connect_gateways(self):
        """
        连接交易接口
        """
        gateway_config = self.config["gateways"]
        
        # 连接Alpaca
        if gateway_config.get("alpaca", {}).get("enabled") and ALPACA_AVAILABLE:
            self._connect_alpaca(gateway_config["alpaca"])
            
        # 连接IB
        if gateway_config.get("ib", {}).get("enabled") and IB_AVAILABLE:
            self._connect_ib(gateway_config["ib"])
            
        if not self.connected_gateways:
            raise RuntimeError("没有可用的交易接口连接")
            
        print(f"已连接交易接口: {', '.join(self.connected_gateways)}")
        
    def _connect_alpaca(self, alpaca_config: Dict[str, Any]):
        """
        连接Alpaca接口
        
        Args:
            alpaca_config: Alpaca配置
        """
        try:
            # 添加Alpaca接口
            self.main_engine.add_gateway(AlpacaGateway)
            
            # 连接参数
            connect_setting = {
                "key": alpaca_config["key_id"],
                "secret": alpaca_config["secret_key"],
                "server": alpaca_config["server"]
            }
            
            # 连接
            self.main_engine.connect(connect_setting, "ALPACA")
            
            # 等待连接
            time.sleep(3)
            
            self.connected_gateways.add("ALPACA")
            trading_mode = "模拟" if alpaca_config["paper_trading"] else "实盘"
            print(f"Alpaca接口连接成功 ({trading_mode})")
            
        except Exception as e:
            print(f"Alpaca接口连接失败: {e}")
            
    def _connect_ib(self, ib_config: Dict[str, Any]):
        """
        连接IB接口
        
        Args:
            ib_config: IB配置
        """
        try:
            # 添加IB接口
            self.main_engine.add_gateway(IbGateway)
            
            # 连接参数
            connect_setting = {
                "host": ib_config["host"],
                "port": ib_config["port"],
                "clientid": ib_config["client_id"]
            }
            
            # 连接
            self.main_engine.connect(connect_setting, "IB")
            
            # 等待连接
            time.sleep(5)
            
            self.connected_gateways.add("IB")
            print(f"IB接口连接成功")
            
        except Exception as e:
            print(f"IB接口连接失败: {e}")
            
    def start_strategies(self, strategy_names: List[str] = None):
        """
        启动策略
        
        Args:
            strategy_names: 策略名称列表，None表示启动所有配置的策略
        """
        strategies_config = self.config["strategies"]
        
        if strategy_names is None:
            strategy_names = list(strategies_config.keys())
            
        for strategy_name in strategy_names:
            if strategy_name not in strategies_config:
                print(f"警告: 策略配置不存在: {strategy_name}")
                continue
                
            try:
                self._start_single_strategy(strategy_name, strategies_config[strategy_name])
            except Exception as e:
                print(f"策略 {strategy_name} 启动失败: {e}")
                self.exception_handler.handle_exception(e, f"策略启动: {strategy_name}")
                
        print(f"已启动策略数量: {len(self.active_strategies)}")
        
    def _start_single_strategy(self, strategy_name: str, strategy_config: Dict[str, Any]):
        """
        启动单个策略
        
        Args:
            strategy_name: 策略名称
            strategy_config: 策略配置
        """
        class_name = strategy_config["class_name"]
        vt_symbol = strategy_config["vt_symbol"]
        setting = strategy_config["setting"]
        
        if class_name not in self.strategy_classes:
            raise ValueError(f"未知策略类: {class_name}")
            
        strategy_class = self.strategy_classes[class_name]
        
        # 风险检查
        if not self.risk_manager.check_strategy_risk(strategy_name, vt_symbol, setting):
            raise RuntimeError(f"策略 {strategy_name} 未通过风险检查")
            
        # 添加策略
        self.cta_engine.add_strategy(
            class_name=class_name,
            strategy_name=strategy_name,
            vt_symbol=vt_symbol,
            setting=setting
        )
        
        # 初始化策略
        self.cta_engine.init_strategy(strategy_name)
        
        # 等待初始化完成
        time.sleep(2)
        
        # 启动策略
        self.cta_engine.start_strategy(strategy_name)
        
        # 记录活跃策略
        self.active_strategies[strategy_name] = {
            "class_name": class_name,
            "vt_symbol": vt_symbol,
            "setting": setting,
            "start_time": datetime.now()
        }
        
        print(f"策略启动成功: {strategy_name} ({class_name} - {vt_symbol})")
        
    def start_gui(self):
        """
        启动图形界面
        """
        if not self.use_gui:
            return
            
        try:
            # 创建Qt应用
            self.qapp = create_qapp()
            
            # 创建主窗口
            self.main_window = MainWindow(self.main_engine, self.event_engine)
            self.main_window.showMaximized()
            
            print("图形界面启动成功")
            
        except Exception as e:
            print(f"图形界面启动失败: {e}")
            self.use_gui = False
            
    def run(self):
        """
        运行交易系统
        """
        try:
            print("正在启动实盘交易系统...")
            
            # 连接交易接口
            self.connect_gateways()
            
            # 启动策略
            self.start_strategies()
            
            # 启动监控
            self.start_monitoring()
            
            # 启动图形界面
            if self.use_gui:
                self.start_gui()
                
            self.is_running = True
            print("实盘交易系统启动完成")
            
            # 主循环
            if self.use_gui and self.qapp:
                # GUI模式
                self.qapp.exec_()
            else:
                # 命令行模式
                self._run_console_mode()
                
        except KeyboardInterrupt:
            print("\n收到中断信号，正在关闭系统...")
        except Exception as e:
            print(f"系统运行异常: {e}")
            self.exception_handler.handle_exception(e, "系统运行")
        finally:
            self.shutdown()
            
    def _run_console_mode(self):
        """
        命令行模式运行
        """
        print("\n交易系统运行中... (按 Ctrl+C 退出)")
        print("可用命令:")
        print("  status - 显示系统状态")
        print("  strategies - 显示策略状态")
        print("  positions - 显示持仓")
        print("  orders - 显示委托")
        print("  stop <strategy_name> - 停止策略")
        print("  quit - 退出系统")
        
        while self.is_running:
            try:
                command = input("\n> ").strip().lower()
                
                if command == "quit":
                    break
                elif command == "status":
                    self._show_system_status()
                elif command == "strategies":
                    self._show_strategies_status()
                elif command == "positions":
                    self._show_positions()
                elif command == "orders":
                    self._show_orders()
                elif command.startswith("stop "):
                    strategy_name = command.split(" ", 1)[1]
                    self._stop_strategy(strategy_name)
                elif command == "":
                    continue
                else:
                    print(f"未知命令: {command}")
                    
            except EOFError:
                break
            except Exception as e:
                print(f"命令执行错误: {e}")
                
    def start_monitoring(self):
        """
        启动监控线程
        """
        # 性能监控线程
        performance_thread = threading.Thread(
            target=self._performance_monitoring_loop,
            daemon=True
        )
        performance_thread.start()
        
        # 健康检查线程
        health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )
        health_thread.start()
        
        print("监控线程启动完成")
        
    def _performance_monitoring_loop(self):
        """
        性能监控循环
        """
        interval = self.config["monitoring"]["performance_update_interval"]
        
        while self.is_running:
            try:
                self.performance_monitor.update_performance(self.main_engine)
                time.sleep(interval)
            except Exception as e:
                self.exception_handler.handle_exception(e, "性能监控")
                time.sleep(interval)
                
    def _health_check_loop(self):
        """
        健康检查循环
        """
        interval = self.config["monitoring"]["health_check_interval"]
        
        while self.is_running:
            try:
                self._perform_health_check()
                time.sleep(interval)
            except Exception as e:
                self.exception_handler.handle_exception(e, "健康检查")
                time.sleep(interval)
                
    def _perform_health_check(self):
        """
        执行健康检查
        """
        # 检查连接状态
        for gateway_name in self.connected_gateways:
            # 这里可以添加具体的连接检查逻辑
            pass
            
        # 检查策略状态
        for strategy_name in self.active_strategies:
            # 这里可以添加策略健康检查逻辑
            pass
            
        # 检查风险控制
        self.risk_manager.check_daily_risk()
        
    def _show_system_status(self):
        """
        显示系统状态
        """
        print(f"\n系统状态:")
        print(f"  运行状态: {'运行中' if self.is_running else '已停止'}")
        print(f"  连接接口: {', '.join(self.connected_gateways)}")
        print(f"  活跃策略: {len(self.active_strategies)}")
        print(f"  当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    def _show_strategies_status(self):
        """
        显示策略状态
        """
        print(f"\n策略状态:")
        for name, info in self.active_strategies.items():
            print(f"  {name}: {info['class_name']} - {info['vt_symbol']}")
            print(f"    启动时间: {info['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            
    def _show_positions(self):
        """
        显示持仓
        """
        positions = self.main_engine.get_all_positions()
        print(f"\n当前持仓 (共{len(positions)}个):")
        for pos in positions:
            print(f"  {pos.vt_symbol}: {pos.volume} @ {pos.price:.2f}")
            
    def _show_orders(self):
        """
        显示委托
        """
        orders = self.main_engine.get_all_active_orders()
        print(f"\n活跃委托 (共{len(orders)}个):")
        for order in orders:
            print(f"  {order.vt_orderid}: {order.direction.value} {order.volume} @ {order.price:.2f}")
            
    def _stop_strategy(self, strategy_name: str):
        """
        停止策略
        
        Args:
            strategy_name: 策略名称
        """
        if strategy_name in self.active_strategies:
            self.cta_engine.stop_strategy(strategy_name)
            del self.active_strategies[strategy_name]
            print(f"策略 {strategy_name} 已停止")
        else:
            print(f"策略 {strategy_name} 不存在或未运行")
            
    def shutdown(self):
        """
        关闭交易系统
        """
        print("正在关闭交易系统...")
        
        self.is_running = False
        
        # 停止所有策略
        for strategy_name in list(self.active_strategies.keys()):
            try:
                self.cta_engine.stop_strategy(strategy_name)
                print(f"策略 {strategy_name} 已停止")
            except Exception as e:
                print(f"停止策略 {strategy_name} 失败: {e}")
                
        # 断开连接
        for gateway_name in self.connected_gateways:
            try:
                self.main_engine.disconnect(gateway_name)
                print(f"接口 {gateway_name} 已断开")
            except Exception as e:
                print(f"断开接口 {gateway_name} 失败: {e}")
                
        # 关闭引擎
        self.main_engine.close()
        
        print("交易系统已关闭")
        

class RiskManager:
    """
    风险管理器
    """
    
    def __init__(self, risk_config: Dict[str, Any]):
        self.config = risk_config
        self.daily_loss = 0.0
        self.daily_trades = 0
        
    def check_strategy_risk(self, strategy_name: str, vt_symbol: str, setting: Dict[str, Any]) -> bool:
        """
        检查策略风险
        """
        # 检查允许的交易品种
        allowed_symbols = self.config.get("allowed_symbols", [])
        if allowed_symbols and vt_symbol not in allowed_symbols:
            print(f"风险控制: 不允许交易 {vt_symbol}")
            return False
            
        # 检查仓位大小
        max_position = self.config.get("max_position_size", float('inf'))
        position_size = setting.get("fixed_size", 0)
        if position_size > max_position:
            print(f"风险控制: 仓位大小 {position_size} 超过限制 {max_position}")
            return False
            
        return True
        
    def check_daily_risk(self):
        """
        检查日内风险
        """
        max_daily_loss = self.config.get("max_daily_loss", float('inf'))
        if self.daily_loss > max_daily_loss:
            print(f"风险警告: 日内亏损 {self.daily_loss} 超过限制 {max_daily_loss}")
            

class PerformanceMonitor:
    """
    性能监控器
    """
    
    def __init__(self):
        self.last_update = datetime.now()
        
    def update_performance(self, main_engine):
        """
        更新性能数据
        """
        # 这里可以添加性能统计逻辑
        self.last_update = datetime.now()
        

class ExceptionHandler:
    """
    异常处理器
    """
    
    def __init__(self):
        self.exception_count = 0
        
    def handle_exception(self, exception: Exception, context: str):
        """
        处理异常
        """
        self.exception_count += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] 异常 #{self.exception_count} in {context}: {exception}")
        
        # 这里可以添加异常处理逻辑，如发送邮件、记录日志等
        

def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description="vn.py框架实盘交易脚本")
    parser.add_argument("--paper", action="store_true", help="模拟交易模式")
    parser.add_argument("--live", action="store_true", help="实盘交易模式")
    parser.add_argument("--gui", action="store_true", help="启用图形界面")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--strategy", type=str, help="指定启动的策略名称")
    
    args = parser.parse_args()
    
    if not args.paper and not args.live:
        print("请指定交易模式: --paper (模拟) 或 --live (实盘)")
        return
        
    if args.paper and args.live:
        print("不能同时指定模拟和实盘模式")
        return
        
    # 创建交易管理器
    manager = LiveTradingManager(args.config, args.gui)
    
    # 设置交易模式
    if args.paper:
        print("启动模拟交易模式")
        # 确保配置为模拟交易
        if "alpaca" in manager.config["gateways"]:
            manager.config["gateways"]["alpaca"]["paper_trading"] = True
            manager.config["gateways"]["alpaca"]["server"] = "PAPER"
    else:
        print("启动实盘交易模式")
        print("警告: 这是实盘交易，请确保配置正确！")
        confirm = input("确认启动实盘交易? (yes/no): ")
        if confirm.lower() != "yes":
            print("已取消")
            return
            
    # 设置信号处理
    def signal_handler(signum, frame):
        print("\n收到退出信号，正在关闭系统...")
        manager.shutdown()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 运行交易系统
        manager.run()
    except Exception as e:
        print(f"系统启动失败: {e}")
        import traceback
        traceback.print_exc()
        

if __name__ == "__main__":
    main()