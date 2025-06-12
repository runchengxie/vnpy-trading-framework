# websocket_handler.py
import asyncio
import logging
import json
import websockets
from typing import Dict, Callable, Optional, List
from datetime import datetime
import threading
from alpaca_trade_api.stream import Stream
from alpaca_trade_api.common import URL
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class WebSocketDataHandler:
    """
    WebSocket实时数据处理器，支持Alpaca实时数据流
    """
    
    def __init__(self, api_key: str = None, secret_key: str = None, base_url: str = None):
        load_dotenv()
        
        self.api_key = api_key or os.getenv('APCA_API_KEY_ID')
        self.secret_key = secret_key or os.getenv('APCA_API_SECRET_KEY')
        self.base_url = base_url or os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Missing Alpaca API credentials")
        
        # 初始化Alpaca Stream
        self.stream = Stream(
            key_id=self.api_key,
            secret_key=self.secret_key,
            base_url=URL(self.base_url),
            data_feed='iex'  # 使用IEX数据源
        )
        
        # 回调函数存储
        self.quote_callbacks: Dict[str, List[Callable]] = {}
        self.trade_callbacks: Dict[str, List[Callable]] = {}
        self.bar_callbacks: Dict[str, List[Callable]] = {}
        
        # 连接状态
        self.is_connected = False
        self.subscribed_symbols = set()
        
        # 数据缓存
        self.latest_quotes: Dict[str, Dict] = {}
        self.latest_trades: Dict[str, Dict] = {}
        self.latest_bars: Dict[str, Dict] = {}
        
        logger.info("WebSocket数据处理器初始化完成")
    
    async def connect(self):
        """
        建立WebSocket连接
        """
        try:
            logger.info("正在连接到Alpaca WebSocket...")
            
            # 设置通用处理器
            @self.stream.on_quote
            async def quote_handler(quote):
                await self._handle_quote(quote)
            
            @self.stream.on_trade
            async def trade_handler(trade):
                await self._handle_trade(trade)
            
            @self.stream.on_bar
            async def bar_handler(bar):
                await self._handle_bar(bar)
            
            # 启动连接
            await self.stream._run_forever()
            self.is_connected = True
            logger.info("WebSocket连接建立成功")
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """
        断开WebSocket连接
        """
        try:
            if self.stream:
                await self.stream.close()
            self.is_connected = False
            logger.info("WebSocket连接已断开")
        except Exception as e:
            logger.error(f"断开WebSocket连接时出错: {e}")
    
    def subscribe_quotes(self, symbols: List[str], callback: Callable = None):
        """
        订阅实时报价数据
        
        Args:
            symbols: 股票代码列表
            callback: 数据回调函数
        """
        for symbol in symbols:
            if symbol not in self.quote_callbacks:
                self.quote_callbacks[symbol] = []
            
            if callback:
                self.quote_callbacks[symbol].append(callback)
            
            self.subscribed_symbols.add(symbol)
        
        # 订阅Alpaca数据流
        self.stream.subscribe_quotes(*symbols)
        logger.info(f"已订阅报价数据: {symbols}")
    
    def subscribe_trades(self, symbols: List[str], callback: Callable = None):
        """
        订阅实时交易数据
        
        Args:
            symbols: 股票代码列表
            callback: 数据回调函数
        """
        for symbol in symbols:
            if symbol not in self.trade_callbacks:
                self.trade_callbacks[symbol] = []
            
            if callback:
                self.trade_callbacks[symbol].append(callback)
            
            self.subscribed_symbols.add(symbol)
        
        # 订阅Alpaca数据流
        self.stream.subscribe_trades(*symbols)
        logger.info(f"已订阅交易数据: {symbols}")
    
    def subscribe_bars(self, symbols: List[str], callback: Callable = None):
        """
        订阅实时K线数据
        
        Args:
            symbols: 股票代码列表
            callback: 数据回调函数
        """
        for symbol in symbols:
            if symbol not in self.bar_callbacks:
                self.bar_callbacks[symbol] = []
            
            if callback:
                self.bar_callbacks[symbol].append(callback)
            
            self.subscribed_symbols.add(symbol)
        
        # 订阅Alpaca数据流
        self.stream.subscribe_bars(*symbols)
        logger.info(f"已订阅K线数据: {symbols}")
    
    async def _handle_quote(self, quote):
        """
        处理实时报价数据
        """
        symbol = quote.symbol
        
        # 构造标准化数据格式
        quote_data = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'bid_price': float(quote.bid_price) if quote.bid_price else None,
            'ask_price': float(quote.ask_price) if quote.ask_price else None,
            'bid_size': int(quote.bid_size) if quote.bid_size else None,
            'ask_size': int(quote.ask_size) if quote.ask_size else None,
            'spread': None
        }
        
        # 计算买卖价差
        if quote_data['bid_price'] and quote_data['ask_price']:
            quote_data['spread'] = quote_data['ask_price'] - quote_data['bid_price']
            quote_data['spread_percentage'] = quote_data['spread'] / quote_data['ask_price']
        
        # 更新缓存
        self.latest_quotes[symbol] = quote_data
        
        # 调用回调函数
        if symbol in self.quote_callbacks:
            for callback in self.quote_callbacks[symbol]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(quote_data)
                    else:
                        callback(quote_data)
                except Exception as e:
                    logger.error(f"报价回调函数执行错误: {e}")
        
        logger.debug(f"处理报价数据: {symbol} Bid={quote_data['bid_price']} Ask={quote_data['ask_price']}")
    
    async def _handle_trade(self, trade):
        """
        处理实时交易数据
        """
        symbol = trade.symbol
        
        # 构造标准化数据格式
        trade_data = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'price': float(trade.price),
            'size': int(trade.size),
            'conditions': getattr(trade, 'conditions', []),
            'exchange': getattr(trade, 'exchange', None)
        }
        
        # 更新缓存
        self.latest_trades[symbol] = trade_data
        
        # 调用回调函数
        if symbol in self.trade_callbacks:
            for callback in self.trade_callbacks[symbol]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(trade_data)
                    else:
                        callback(trade_data)
                except Exception as e:
                    logger.error(f"交易回调函数执行错误: {e}")
        
        logger.debug(f"处理交易数据: {symbol} Price={trade_data['price']} Size={trade_data['size']}")
    
    async def _handle_bar(self, bar):
        """
        处理实时K线数据
        """
        symbol = bar.symbol
        
        # 构造标准化数据格式
        bar_data = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': int(bar.volume),
            'trade_count': getattr(bar, 'trade_count', None),
            'vwap': getattr(bar, 'vwap', None)
        }
        
        # 更新缓存
        self.latest_bars[symbol] = bar_data
        
        # 调用回调函数
        if symbol in self.bar_callbacks:
            for callback in self.bar_callbacks[symbol]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(bar_data)
                    else:
                        callback(bar_data)
                except Exception as e:
                    logger.error(f"K线回调函数执行错误: {e}")
        
        logger.debug(f"处理K线数据: {symbol} OHLCV={bar_data['open']}/{bar_data['high']}/{bar_data['low']}/{bar_data['close']}/{bar_data['volume']}")
    
    def get_latest_quote(self, symbol: str) -> Optional[Dict]:
        """
        获取最新报价数据
        """
        return self.latest_quotes.get(symbol)
    
    def get_latest_trade(self, symbol: str) -> Optional[Dict]:
        """
        获取最新交易数据
        """
        return self.latest_trades.get(symbol)
    
    def get_latest_bar(self, symbol: str) -> Optional[Dict]:
        """
        获取最新K线数据
        """
        return self.latest_bars.get(symbol)
    
    def get_market_summary(self, symbol: str) -> Dict:
        """
        获取市场数据摘要
        """
        summary = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'quote': self.get_latest_quote(symbol),
            'trade': self.get_latest_trade(symbol),
            'bar': self.get_latest_bar(symbol),
            'is_subscribed': symbol in self.subscribed_symbols
        }
        
        # 计算衍生指标
        if summary['quote'] and summary['trade']:
            quote = summary['quote']
            trade = summary['trade']
            
            summary['derived_metrics'] = {
                'mid_price': (quote['bid_price'] + quote['ask_price']) / 2 if quote['bid_price'] and quote['ask_price'] else None,
                'last_vs_mid': trade['price'] - ((quote['bid_price'] + quote['ask_price']) / 2) if quote['bid_price'] and quote['ask_price'] else None,
                'spread_bps': (quote['spread'] / quote['ask_price'] * 10000) if quote.get('spread') and quote['ask_price'] else None
            }
        
        return summary
    
    def start_background_connection(self):
        """
        在后台线程中启动WebSocket连接
        """
        def run_connection():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.connect())
            except Exception as e:
                logger.error(f"后台WebSocket连接错误: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_connection, daemon=True)
        thread.start()
        logger.info("WebSocket连接已在后台启动")
        return thread
    
    def unsubscribe(self, symbols: List[str]):
        """
        取消订阅
        """
        for symbol in symbols:
            self.subscribed_symbols.discard(symbol)
            
            # 清理回调函数
            if symbol in self.quote_callbacks:
                del self.quote_callbacks[symbol]
            if symbol in self.trade_callbacks:
                del self.trade_callbacks[symbol]
            if symbol in self.bar_callbacks:
                del self.bar_callbacks[symbol]
            
            # 清理缓存
            self.latest_quotes.pop(symbol, None)
            self.latest_trades.pop(symbol, None)
            self.latest_bars.pop(symbol, None)
        
        # 取消Alpaca订阅
        try:
            self.stream.unsubscribe_quotes(*symbols)
            self.stream.unsubscribe_trades(*symbols)
            self.stream.unsubscribe_bars(*symbols)
        except Exception as e:
            logger.warning(f"取消订阅时出错: {e}")
        
        logger.info(f"已取消订阅: {symbols}")
    
    def get_connection_status(self) -> Dict:
        """
        获取连接状态信息
        """
        return {
            'is_connected': self.is_connected,
            'subscribed_symbols': list(self.subscribed_symbols),
            'active_quotes': len(self.latest_quotes),
            'active_trades': len(self.latest_trades),
            'active_bars': len(self.latest_bars),
            'total_callbacks': {
                'quotes': sum(len(callbacks) for callbacks in self.quote_callbacks.values()),
                'trades': sum(len(callbacks) for callbacks in self.trade_callbacks.values()),
                'bars': sum(len(callbacks) for callbacks in self.bar_callbacks.values())
            }
        }


class MarketDataAggregator:
    """
    市场数据聚合器，整合多源数据并提供统一接口
    """
    
    def __init__(self, websocket_handler: WebSocketDataHandler):
        self.ws_handler = websocket_handler
        self.data_quality_checks = True
        self.aggregated_data = {}
        
        logger.info("市场数据聚合器初始化完成")
    
    def enable_data_quality_checks(self, enabled: bool = True):
        """
        启用/禁用数据质量检查
        """
        self.data_quality_checks = enabled
        logger.info(f"数据质量检查: {'启用' if enabled else '禁用'}")
    
    def get_consolidated_market_data(self, symbol: str) -> Dict:
        """
        获取整合的市场数据
        """
        quote = self.ws_handler.get_latest_quote(symbol)
        trade = self.ws_handler.get_latest_trade(symbol)
        bar = self.ws_handler.get_latest_bar(symbol)
        
        consolidated = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'best_bid': quote['bid_price'] if quote else None,
            'best_ask': quote['ask_price'] if quote else None,
            'last_price': trade['price'] if trade else None,
            'last_size': trade['size'] if trade else None,
            'volume': bar['volume'] if bar else None,
            'data_quality': 'GOOD'
        }
        
        # 数据质量检查
        if self.data_quality_checks:
            quality_issues = []
            
            # 检查数据时效性
            if quote and (datetime.now() - quote['timestamp']).seconds > 60:
                quality_issues.append('报价数据过时')
            
            if trade and (datetime.now() - trade['timestamp']).seconds > 60:
                quality_issues.append('交易数据过时')
            
            # 检查价格合理性
            if quote and quote['bid_price'] and quote['ask_price']:
                if quote['bid_price'] >= quote['ask_price']:
                    quality_issues.append('买卖价格倒挂')
                
                spread_pct = (quote['ask_price'] - quote['bid_price']) / quote['ask_price']
                if spread_pct > 0.05:  # 5%
                    quality_issues.append('买卖价差过大')
            
            if quality_issues:
                consolidated['data_quality'] = 'POOR'
                consolidated['quality_issues'] = quality_issues
        
        return consolidated