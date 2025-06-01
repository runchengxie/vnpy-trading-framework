# enhanced_trading_example.py
"""
增强交易系统示例
展示如何使用新增的风险管理、WebSocket数据流、性能分析、异常处理和一致性验证功能
"""

import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
import numpy as np

# 导入核心模块
from risk_manager import RiskManager
from websocket_handler import WebSocketDataHandler, MarketDataAggregator
from performance_analyzer import PerformanceAnalyzer, TradeRecord
from exception_handler import ExceptionHandler, ErrorCategory, ErrorSeverity, handle_exceptions
from consistency_validator import ConsistencyValidator
from broker_handler import BrokerAPIHandler
from live_trader import LiveMeanReversionStrategy, TradingState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedTradingSystem:
    """
    增强交易系统
    集成所有新增功能的完整交易系统
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # 初始化核心组件
        self.risk_manager = RiskManager(
            initial_capital=config.get('initial_capital', 100000)
        )
        
        self.performance_analyzer = PerformanceAnalyzer(
            initial_capital=config.get('initial_capital', 100000)
        )
        
        self.exception_handler = ExceptionHandler()
        self.consistency_validator = ConsistencyValidator()
        
        # 初始化交易组件
        self.broker_handler = None
        self.websocket_handler = None
        self.market_aggregator = None
        self.trading_strategy = None
        self.trading_state = TradingState()
        
        # 数据存储
        self.market_data_buffer = []
        self.trade_history = []
        self.signal_history = []
        
        logger.info("增强交易系统初始化完成")
    
    @handle_exceptions(ErrorCategory.SYSTEM, ErrorSeverity.HIGH)
    def initialize_components(self):
        """
        初始化所有组件
        """
        logger.info("开始初始化交易组件...")
        
        try:
            # 初始化Broker API
            self.broker_handler = BrokerAPIHandler()
            
            # 初始化WebSocket数据流
            self.websocket_handler = WebSocketDataHandler(
                api_key=self.config.get('alpaca_api_key'),
                secret_key=self.config.get('alpaca_secret_key'),
                base_url=self.config.get('alpaca_base_url')
            )
            
            # 初始化市场数据聚合器
            self.market_aggregator = MarketDataAggregator()
            
            # 初始化交易策略
            strategy_config = self.config.get('strategy', {})
            self.trading_strategy = LiveMeanReversionStrategy(
                symbol=strategy_config.get('symbol', 'AAPL'),
                lookback_period=strategy_config.get('lookback_period', 20),
                z_threshold=strategy_config.get('z_threshold', 2.0),
                position_size=strategy_config.get('position_size', 100)
            )
            
            # 注册异常处理回调
            self._register_error_callbacks()
            
            logger.info("所有组件初始化成功")
            
        except Exception as e:
            logger.error(f"组件初始化失败: {e}")
            raise
    
    def _register_error_callbacks(self):
        """
        注册错误处理回调
        """
        def on_network_error(error_record):
            logger.warning(f"网络错误处理: {error_record.message}")
            # 可以在这里添加网络重连逻辑
        
        def on_api_error(error_record):
            logger.warning(f"API错误处理: {error_record.message}")
            # 可以在这里添加API重试逻辑
        
        def on_order_error(error_record):
            logger.error(f"订单错误处理: {error_record.message}")
            # 可以在这里添加订单恢复逻辑
        
        self.exception_handler.register_error_callback(ErrorCategory.NETWORK, on_network_error)
        self.exception_handler.register_error_callback(ErrorCategory.API, on_api_error)
        self.exception_handler.register_error_callback(ErrorCategory.ORDER_EXECUTION, on_order_error)
    
    @handle_exceptions(ErrorCategory.DATA_QUALITY, ErrorSeverity.MEDIUM)
    def process_market_data(self, market_data: Dict):
        """
        处理市场数据
        """
        try:
            # 数据质量检查
            if not self.market_aggregator.validate_data_quality(market_data):
                logger.warning("市场数据质量检查失败")
                return
            
            # 添加到缓冲区
            self.market_data_buffer.append(market_data)
            
            # 保持缓冲区大小
            if len(self.market_data_buffer) > 1000:
                self.market_data_buffer = self.market_data_buffer[-1000:]
            
            # 生成交易信号
            signal = self.trading_strategy.generate_signal(market_data)
            
            if signal != 'hold':
                signal_record = {
                    'timestamp': datetime.now(),
                    'symbol': market_data.get('symbol'),
                    'signal': 1.0 if signal == 'buy' else -1.0 if signal == 'sell' else 0.0,
                    'price': market_data.get('price'),
                    'confidence': self.trading_strategy.get_signal_confidence()
                }
                
                self.signal_history.append(signal_record)
                
                # 风险检查
                if self._risk_check(signal_record):
                    self._execute_trade(signal, market_data)
                else:
                    logger.warning(f"风险检查未通过，跳过交易信号: {signal}")
            
            # 更新性能分析
            self._update_performance_metrics(market_data)
            
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.DATA_QUALITY, ErrorSeverity.MEDIUM,
                {'market_data': market_data}
            )
    
    def _risk_check(self, signal_record: Dict) -> bool:
        """
        执行风险检查
        """
        try:
            # 流动性检查
            symbol = signal_record['symbol']
            if not self.risk_manager.check_liquidity_risk(symbol, 100):
                return False
            
            # 集中度检查
            current_positions = self.trading_state.get_positions()
            if not self.risk_manager.check_concentration_risk(current_positions, symbol, 100):
                return False
            
            # VaR检查
            portfolio_values = [(datetime.now(), self.trading_state.get_portfolio_value())]
            risk_metrics = self.risk_manager.calculate_portfolio_risk(
                portfolio_values, current_positions
            )
            
            if risk_metrics.get('var_95', 0) > self.config.get('max_var', 0.05):
                logger.warning(f"VaR超过限制: {risk_metrics['var_95']:.4f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return False
    
    @handle_exceptions(ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH)
    def _execute_trade(self, signal: str, market_data: Dict):
        """
        执行交易
        """
        try:
            symbol = market_data['symbol']
            price = market_data['price']
            quantity = self.trading_strategy.position_size
            
            if signal == 'buy':
                order_result = self.broker_handler.place_order(
                    symbol=symbol,
                    qty=quantity,
                    side='buy',
                    type='limit',
                    limit_price=price * 1.001  # 稍微高于市价
                )
            elif signal == 'sell':
                order_result = self.broker_handler.place_order(
                    symbol=symbol,
                    qty=quantity,
                    side='sell',
                    type='limit',
                    limit_price=price * 0.999  # 稍微低于市价
                )
            else:
                return
            
            if order_result and 'id' in order_result:
                # 记录交易
                trade_record = TradeRecord(
                    timestamp=datetime.now(),
                    symbol=symbol,
                    side=signal,
                    quantity=quantity,
                    price=price,
                    commission=0.005 * quantity * price,  # 假设0.5%手续费
                    order_id=order_result['id']
                )
                
                self.performance_analyzer.add_trade(trade_record)
                self.trade_history.append(trade_record)
                
                # 更新交易状态
                self.trading_state.update_position(symbol, quantity if signal == 'buy' else -quantity)
                
                logger.info(f"交易执行成功: {signal} {quantity} {symbol} @ {price}")
            else:
                logger.error(f"交易执行失败: {order_result}")
                
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.ORDER_EXECUTION, ErrorSeverity.HIGH,
                {'signal': signal, 'market_data': market_data}
            )
    
    def _update_performance_metrics(self, market_data: Dict):
        """
        更新性能指标
        """
        try:
            # 更新组合价值
            current_positions = self.trading_state.get_positions()
            market_prices = {market_data['symbol']: market_data['price']}
            
            self.performance_analyzer.update_portfolio_value(
                datetime.now(), market_prices
            )
            
        except Exception as e:
            logger.warning(f"性能指标更新失败: {e}")
    
    async def start_live_trading(self):
        """
        启动实时交易
        """
        logger.info("启动实时交易系统...")
        
        try:
            # 初始化组件
            self.initialize_components()
            
            # 订阅市场数据
            symbols = [self.config.get('strategy', {}).get('symbol', 'AAPL')]
            
            # 启动WebSocket数据流
            await self.websocket_handler.start_data_stream(
                symbols=symbols,
                data_callback=self.process_market_data
            )
            
        except Exception as e:
            self.exception_handler.handle_exception(
                e, ErrorCategory.SYSTEM, ErrorSeverity.CRITICAL
            )
            raise
    
    def run_consistency_validation(self, backtest_data: Dict) -> Dict:
        """
        运行一致性验证
        """
        logger.info("开始一致性验证...")
        
        # 准备实盘数据
        live_data = {
            'signals': self.signal_history,
            'trades': [{
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'side': trade.side,
                'quantity': trade.quantity,
                'price': trade.price
            } for trade in self.trade_history],
            'performance': self.performance_analyzer.calculate_risk_metrics()
        }
        
        # 执行验证
        validation_results = self.consistency_validator.validate_consistency(
            backtest_data, live_data
        )
        
        # 生成报告
        validation_report = self.consistency_validator.generate_validation_report(
            validation_results
        )
        
        logger.info(f"一致性验证完成，总体状态: {validation_report['overall_status']}")
        return validation_report
    
    def generate_comprehensive_report(self) -> Dict:
        """
        生成综合报告
        """
        logger.info("生成综合交易报告...")
        
        try:
            # 性能报告
            performance_report = self.performance_analyzer.generate_performance_report()
            
            # 风险报告
            portfolio_values = [(datetime.now(), self.trading_state.get_portfolio_value())]
            current_positions = self.trading_state.get_positions()
            risk_metrics = self.risk_manager.calculate_portfolio_risk(
                portfolio_values, current_positions
            )
            
            # 异常统计
            error_statistics = self.exception_handler.get_error_statistics()
            
            # 交易统计
            trading_stats = {
                'total_trades': len(self.trade_history),
                'total_signals': len(self.signal_history),
                'signal_to_trade_ratio': len(self.trade_history) / len(self.signal_history) if self.signal_history else 0,
                'current_positions': current_positions,
                'portfolio_value': self.trading_state.get_portfolio_value()
            }
            
            comprehensive_report = {
                'timestamp': datetime.now(),
                'performance_analysis': performance_report,
                'risk_analysis': risk_metrics,
                'trading_statistics': trading_stats,
                'error_statistics': error_statistics,
                'system_status': {
                    'emergency_stop': self.exception_handler.emergency_stop_triggered,
                    'active_positions': len(current_positions),
                    'data_buffer_size': len(self.market_data_buffer)
                }
            }
            
            logger.info("综合报告生成完成")
            return comprehensive_report
            
        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return {'error': str(e)}
    
    def stop_trading(self):
        """
        停止交易
        """
        logger.info("停止交易系统...")
        
        try:
            # 停止WebSocket连接
            if self.websocket_handler:
                asyncio.create_task(self.websocket_handler.stop_data_stream())
            
            # 平仓所有持仓（可选）
            current_positions = self.trading_state.get_positions()
            for symbol, quantity in current_positions.items():
                if quantity != 0:
                    logger.info(f"平仓: {symbol} {quantity}")
                    # 这里可以添加平仓逻辑
            
            # 生成最终报告
            final_report = self.generate_comprehensive_report()
            
            # 导出报告
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.performance_analyzer.plot_performance_charts(
                f'performance_chart_{timestamp}.png'
            )
            
            self.exception_handler.export_error_log(
                f'error_log_{timestamp}.json'
            )
            
            logger.info("交易系统已停止")
            return final_report
            
        except Exception as e:
            logger.error(f"停止交易系统时发生错误: {e}")

# 示例配置
EXAMPLE_CONFIG = {
    'initial_capital': 100000,
    'alpaca_api_key': 'your_api_key',
    'alpaca_secret_key': 'your_secret_key',
    'alpaca_base_url': 'https://paper-api.alpaca.markets',
    'strategy': {
        'symbol': 'AAPL',
        'lookback_period': 20,
        'z_threshold': 2.0,
        'position_size': 100
    },
    'risk_limits': {
        'max_var': 0.05,
        'max_concentration': 0.3,
        'min_liquidity': 1000000
    }
}

# 示例使用
async def main():
    """
    主函数示例
    """
    # 创建交易系统
    trading_system = EnhancedTradingSystem(EXAMPLE_CONFIG)
    
    try:
        # 启动实时交易（这里只是示例，实际使用时需要配置真实的API密钥）
        # await trading_system.start_live_trading()
        
        # 模拟运行一段时间
        logger.info("模拟交易运行中...")
        
        # 模拟一些市场数据
        for i in range(10):
            market_data = {
                'symbol': 'AAPL',
                'price': 150.0 + np.random.normal(0, 1),
                'volume': 1000000,
                'timestamp': datetime.now()
            }
            
            trading_system.process_market_data(market_data)
            time.sleep(1)
        
        # 生成报告
        report = trading_system.generate_comprehensive_report()
        logger.info(f"交易报告: {report}")
        
        # 停止交易
        final_report = trading_system.stop_trading()
        
    except Exception as e:
        logger.error(f"交易系统运行错误: {e}")
        trading_system.stop_trading()

if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())