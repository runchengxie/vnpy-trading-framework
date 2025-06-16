#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VN.py框架历史数据下载脚本

这个脚本用于从各种数据源下载历史数据并保存到VN.py的数据库中，支持：
1. Alpaca API数据下载
2. Yahoo Finance数据下载
3. 多种时间周期和数据格式
4. 批量下载和增量更新
5. 数据验证和清洗

运行方法：
python scripts/download_data.py --symbol SPY --days 365
python scripts/download_data.py --symbol AAPL --start 2023-01-01 --end 2023-12-31
python scripts/download_data.py --batch --config config/download_config.json
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from vnpy.trader.database import get_database
    from vnpy.trader.object import BarData, Interval, Exchange
    from vnpy.trader.constant import Exchange as ExchangeConstant
    from vnpy.trader.utility import ZoneInfo
except ImportError as e:
    print(f"❌ VN.py导入失败: {e}")
    print("请确保已正确安装VN.py框架")
    sys.exit(1)

try:
    import yfinance as yf
except ImportError:
    print("⚠️  yfinance未安装，将无法使用Yahoo Finance数据源")
    yf = None

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    print("⚠️  alpaca-trade-api未安装，将无法使用Alpaca数据源")
    tradeapi = None


class DataDownloader:
    """
    历史数据下载器
    """
    
    def __init__(self):
        self.database = get_database()
        self.timezone = ZoneInfo("America/New_York")  # 美股时区
        
        # 交易所映射
        self.exchange_mapping = {
            "NASDAQ": Exchange.NASDAQ,
            "NYSE": Exchange.NYSE,
            "AMEX": Exchange.AMEX,
            "ARCA": Exchange.ARCA,
        }
        
    def download_from_yahoo(self, symbol: str, start_date: datetime, 
                          end_date: datetime, interval: str = "1d") -> List[BarData]:
        """
        从Yahoo Finance下载数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 时间间隔 (1m, 5m, 15m, 30m, 1h, 1d)
            
        Returns:
            BarData列表
        """
        if yf is None:
            raise ImportError("yfinance未安装，无法使用Yahoo Finance数据源")
            
        print(f"从Yahoo Finance下载 {symbol} 数据...")
        
        try:
            # 下载数据
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=interval,
                auto_adjust=True,
                prepost=True
            )
            
            if df.empty:
                print(f"⚠️  {symbol} 没有找到数据")
                return []
                
            # 转换为BarData
            bars = []
            exchange = self._get_exchange_from_symbol(symbol)
            vt_symbol = f"{symbol}.{exchange.value}"
            
            # 确定时间间隔
            vnpy_interval = self._convert_interval(interval)
            
            for index, row in df.iterrows():
                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=index.to_pydatetime().replace(tzinfo=self.timezone),
                    interval=vnpy_interval,
                    volume=row['Volume'],
                    turnover=0,  # Yahoo Finance不提供成交额
                    open_price=row['Open'],
                    high_price=row['High'],
                    low_price=row['Low'],
                    close_price=row['Close'],
                    gateway_name="YF"
                )
                bars.append(bar)
                
            print(f"✅ 成功下载 {len(bars)} 条 {symbol} 数据")
            return bars
            
        except Exception as e:
            print(f"❌ Yahoo Finance下载失败: {e}")
            return []
            
    def download_from_alpaca(self, symbol: str, start_date: datetime,
                           end_date: datetime, timeframe: str = "1Day") -> List[BarData]:
        """
        从Alpaca API下载数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            timeframe: 时间框架 (1Min, 5Min, 15Min, 30Min, 1Hour, 1Day)
            
        Returns:
            BarData列表
        """
        if tradeapi is None:
            raise ImportError("alpaca-trade-api未安装，无法使用Alpaca数据源")
            
        print(f"从Alpaca下载 {symbol} 数据...")
        
        try:
            # 从配置文件读取API密钥
            config_path = project_root / "config" / "live_trading_config.json"
            if not config_path.exists():
                raise FileNotFoundError("找不到Alpaca配置文件")
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            alpaca_config = config.get("gateways", {}).get("alpaca", {})
            if not alpaca_config:
                raise ValueError("配置文件中未找到Alpaca设置")
                
            # 初始化Alpaca API
            api = tradeapi.REST(
                alpaca_config.get("key_id"),
                alpaca_config.get("secret_key"),
                base_url="https://paper-api.alpaca.markets" if alpaca_config.get("paper", True) else "https://api.alpaca.markets",
                api_version='v2'
            )
            
            # 下载数据
            bars_df = api.get_bars(
                symbol,
                timeframe,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                adjustment='raw'
            ).df
            
            if bars_df.empty:
                print(f"⚠️  {symbol} 没有找到数据")
                return []
                
            # 转换为BarData
            bars = []
            exchange = self._get_exchange_from_symbol(symbol)
            vnpy_interval = self._convert_alpaca_timeframe(timeframe)
            
            for index, row in bars_df.iterrows():
                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=index.to_pydatetime().replace(tzinfo=self.timezone),
                    interval=vnpy_interval,
                    volume=row['volume'],
                    turnover=row['volume'] * row['vwap'] if 'vwap' in row else 0,
                    open_price=row['open'],
                    high_price=row['high'],
                    low_price=row['low'],
                    close_price=row['close'],
                    gateway_name="ALPACA"
                )
                bars.append(bar)
                
            print(f"✅ 成功下载 {len(bars)} 条 {symbol} 数据")
            return bars
            
        except Exception as e:
            print(f"❌ Alpaca下载失败: {e}")
            return []
            
    def save_bars_to_database(self, bars: List[BarData]) -> bool:
        """
        保存K线数据到数据库
        
        Args:
            bars: BarData列表
            
        Returns:
            是否成功
        """
        if not bars:
            print("⚠️  没有数据需要保存")
            return False
            
        try:
            # 保存到数据库
            self.database.save_bar_data(bars)
            print(f"✅ 成功保存 {len(bars)} 条数据到数据库")
            return True
            
        except Exception as e:
            print(f"❌ 数据库保存失败: {e}")
            return False
            
    def download_and_save(self, symbol: str, start_date: datetime,
                         end_date: datetime, source: str = "yahoo",
                         interval: str = "1d") -> bool:
        """
        下载并保存数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            source: 数据源 (yahoo, alpaca)
            interval: 时间间隔
            
        Returns:
            是否成功
        """
        print(f"\n{'='*60}")
        print(f"下载 {symbol} 数据")
        print(f"时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
        print(f"数据源: {source.upper()}")
        print(f"时间间隔: {interval}")
        print(f"{'='*60}")
        
        # 根据数据源下载
        if source.lower() == "yahoo":
            bars = self.download_from_yahoo(symbol, start_date, end_date, interval)
        elif source.lower() == "alpaca":
            # 转换时间间隔格式
            alpaca_timeframe = self._convert_to_alpaca_timeframe(interval)
            bars = self.download_from_alpaca(symbol, start_date, end_date, alpaca_timeframe)
        else:
            print(f"❌ 不支持的数据源: {source}")
            return False
            
        # 保存数据
        if bars:
            return self.save_bars_to_database(bars)
        else:
            return False
            
    def batch_download(self, config_file: str) -> None:
        """
        批量下载数据
        
        Args:
            config_file: 配置文件路径
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            symbols = config.get("symbols", [])
            start_date = datetime.strptime(config.get("start_date", "2023-01-01"), "%Y-%m-%d")
            end_date = datetime.strptime(config.get("end_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
            source = config.get("source", "yahoo")
            interval = config.get("interval", "1d")
            
            print(f"\n开始批量下载 {len(symbols)} 个股票的数据...")
            
            success_count = 0
            for symbol in symbols:
                if self.download_and_save(symbol, start_date, end_date, source, interval):
                    success_count += 1
                    
            print(f"\n批量下载完成: {success_count}/{len(symbols)} 成功")
            
        except Exception as e:
            print(f"❌ 批量下载失败: {e}")
            
    def _get_exchange_from_symbol(self, symbol: str) -> Exchange:
        """
        根据股票代码推断交易所
        """
        # 简单的交易所推断逻辑
        # 实际应用中可能需要更复杂的逻辑或查询表
        return Exchange.NASDAQ  # 默认使用NASDAQ
        
    def _convert_interval(self, interval: str) -> Interval:
        """
        转换时间间隔格式
        """
        mapping = {
            "1m": Interval.MINUTE,
            "5m": Interval.MINUTE,
            "15m": Interval.MINUTE,
            "30m": Interval.MINUTE,
            "1h": Interval.HOUR,
            "1d": Interval.DAILY,
            "1wk": Interval.WEEKLY,
        }
        return mapping.get(interval, Interval.DAILY)
        
    def _convert_alpaca_timeframe(self, timeframe: str) -> Interval:
        """
        转换Alpaca时间框架到VN.py间隔
        """
        mapping = {
            "1Min": Interval.MINUTE,
            "5Min": Interval.MINUTE,
            "15Min": Interval.MINUTE,
            "30Min": Interval.MINUTE,
            "1Hour": Interval.HOUR,
            "1Day": Interval.DAILY,
        }
        return mapping.get(timeframe, Interval.DAILY)
        
    def _convert_to_alpaca_timeframe(self, interval: str) -> str:
        """
        转换时间间隔到Alpaca格式
        """
        mapping = {
            "1m": "1Min",
            "5m": "5Min",
            "15m": "15Min",
            "30m": "30Min",
            "1h": "1Hour",
            "1d": "1Day",
        }
        return mapping.get(interval, "1Day")
        
    def get_data_overview(self) -> None:
        """
        显示数据库中的数据概览
        """
        try:
            overview = self.database.get_bar_overview()
            
            if not overview:
                print("数据库中没有数据")
                return
                
            print("\n数据库数据概览:")
            print(f"{'='*80}")
            print(f"{'股票代码':<15} {'交易所':<10} {'间隔':<10} {'开始日期':<12} {'结束日期':<12} {'数据量':<10}")
            print(f"{'-'*80}")
            
            for item in overview:
                print(f"{item.symbol:<15} {item.exchange.value:<10} {item.interval.value:<10} "
                      f"{item.start.strftime('%Y-%m-%d'):<12} {item.end.strftime('%Y-%m-%d'):<12} {item.count:<10}")
                      
            print(f"{'='*80}")
            
        except Exception as e:
            print(f"❌ 获取数据概览失败: {e}")


def create_sample_config():
    """
    创建示例配置文件
    """
    config = {
        "symbols": ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"],
        "start_date": "2023-01-01",
        "end_date": datetime.now().strftime("%Y-%m-%d"),
        "source": "yahoo",
        "interval": "1d",
        "description": "主要ETF和科技股的日线数据"
    }
    
    config_path = project_root / "config" / "download_config.json"
    config_path.parent.mkdir(exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    print(f"✅ 创建示例配置文件: {config_path}")


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description="VN.py历史数据下载工具")
    
    # 基本参数
    parser.add_argument("--symbol", type=str, help="股票代码 (如: SPY, AAPL)")
    parser.add_argument("--start", type=str, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="下载最近N天的数据")
    parser.add_argument("--source", type=str, choices=["yahoo", "alpaca"], 
                       default="yahoo", help="数据源")
    parser.add_argument("--interval", type=str, default="1d",
                       help="时间间隔 (1m, 5m, 15m, 30m, 1h, 1d)")
    
    # 批量操作
    parser.add_argument("--batch", action="store_true", help="批量下载")
    parser.add_argument("--config", type=str, 
                       default="config/download_config.json", 
                       help="批量下载配置文件")
    
    # 工具功能
    parser.add_argument("--overview", action="store_true", help="显示数据概览")
    parser.add_argument("--create-config", action="store_true", 
                       help="创建示例配置文件")
    
    args = parser.parse_args()
    
    # 创建下载器
    downloader = DataDownloader()
    
    try:
        # 创建示例配置
        if args.create_config:
            create_sample_config()
            return
            
        # 显示数据概览
        if args.overview:
            downloader.get_data_overview()
            return
            
        # 批量下载
        if args.batch:
            config_path = project_root / args.config
            if not config_path.exists():
                print(f"❌ 配置文件不存在: {config_path}")
                print("使用 --create-config 创建示例配置文件")
                return
            downloader.batch_download(str(config_path))
            return
            
        # 单个股票下载
        if not args.symbol:
            print("❌ 请指定股票代码 (--symbol)")
            parser.print_help()
            return
            
        # 确定时间范围
        if args.days:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=args.days)
        elif args.start and args.end:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
        else:
            # 默认下载最近一年的数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
        # 下载数据
        success = downloader.download_and_save(
            args.symbol, start_date, end_date, args.source, args.interval
        )
        
        if success:
            print(f"\n🎉 {args.symbol} 数据下载完成！")
            print("\n下一步:")
            print(f"1. 查看数据概览: python scripts/download_data.py --overview")
            print(f"2. 运行回测: python scripts/run_backtest.py --strategy EmaAdxStrategy --symbol {args.symbol}")
        else:
            print(f"\n❌ {args.symbol} 数据下载失败")
            
    except KeyboardInterrupt:
        print("\n\n下载被用户中断")
    except Exception as e:
        print(f"\n❌ 下载过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()