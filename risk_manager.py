# risk_manager.py
import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime, timedelta
import warnings

logger = logging.getLogger(__name__)

class RiskManager:
    """
    综合风险管理模块，包含VaR计算、流动性检查、市场数据验证等功能
    """
    
    def __init__(self, var_window: int = 252, var_confidence: float = 0.05):
        self.var_window = var_window
        self.var_confidence = var_confidence
        self.price_history = deque(maxlen=var_window)
        self.volume_history = deque(maxlen=var_window)
        self.returns_history = deque(maxlen=var_window)
        
        # 异常检测阈值
        self.price_jump_threshold = 0.05  # 5%价格跳跃阈值
        self.volume_spike_threshold = 3.0  # 3倍成交量异常阈值
        self.min_liquidity_volume = 1000  # 最小流动性要求
        
        logger.info(f"风险管理器初始化: VaR窗口={var_window}, 置信度={1-var_confidence:.1%}")
    
    def update_market_data(self, price: float, volume: float, timestamp: datetime = None):
        """
        更新市场数据并进行实时风险检查
        
        Args:
            price: 当前价格
            volume: 当前成交量
            timestamp: 时间戳
        
        Returns:
            dict: 风险检查结果
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        # 计算收益率
        if len(self.price_history) > 0:
            return_rate = (price - self.price_history[-1]) / self.price_history[-1]
            self.returns_history.append(return_rate)
        
        # 更新历史数据
        self.price_history.append(price)
        self.volume_history.append(volume)
        
        # 执行风险检查
        risk_alerts = self._perform_risk_checks(price, volume, timestamp)
        
        return risk_alerts
    
    def _perform_risk_checks(self, price: float, volume: float, timestamp: datetime) -> Dict:
        """
        执行综合风险检查
        """
        alerts = {
            'timestamp': timestamp,
            'price_jump_alert': False,
            'volume_spike_alert': False,
            'liquidity_alert': False,
            'data_quality_alert': False,
            'messages': []
        }
        
        # 1. 价格跳跃检测
        if len(self.returns_history) > 0:
            latest_return = abs(self.returns_history[-1])
            if latest_return > self.price_jump_threshold:
                alerts['price_jump_alert'] = True
                alerts['messages'].append(f"价格异常跳跃: {latest_return:.2%}")
                logger.warning(f"检测到价格异常跳跃: {latest_return:.2%}")
        
        # 2. 成交量异常检测
        if len(self.volume_history) >= 10:
            avg_volume = np.mean(list(self.volume_history)[:-1])  # 排除当前值
            if volume > avg_volume * self.volume_spike_threshold:
                alerts['volume_spike_alert'] = True
                alerts['messages'].append(f"成交量异常放大: {volume/avg_volume:.1f}倍")
                logger.warning(f"检测到成交量异常: {volume/avg_volume:.1f}倍于平均值")
        
        # 3. 流动性检查
        if volume < self.min_liquidity_volume:
            alerts['liquidity_alert'] = True
            alerts['messages'].append(f"流动性不足: 成交量{volume} < 最小要求{self.min_liquidity_volume}")
            logger.warning(f"流动性不足警告: 成交量{volume}")
        
        # 4. 数据质量检查
        if price <= 0 or volume < 0:
            alerts['data_quality_alert'] = True
            alerts['messages'].append(f"数据质量异常: 价格={price}, 成交量={volume}")
            logger.error(f"数据质量异常: 价格={price}, 成交量={volume}")
        
        return alerts
    
    def calculate_var(self, portfolio_value: float, method: str = 'historical') -> Dict:
        """
        计算风险价值(VaR)
        
        Args:
            portfolio_value: 组合价值
            method: 计算方法 ('historical', 'parametric')
        
        Returns:
            dict: VaR计算结果
        """
        if len(self.returns_history) < 30:
            logger.warning("历史数据不足，无法计算可靠的VaR")
            return {'var': None, 'method': method, 'confidence': 1-self.var_confidence}
        
        returns_array = np.array(self.returns_history)
        
        if method == 'historical':
            var_return = np.percentile(returns_array, self.var_confidence * 100)
            var_amount = abs(var_return * portfolio_value)
        
        elif method == 'parametric':
            mean_return = np.mean(returns_array)
            std_return = np.std(returns_array)
            # 使用正态分布假设
            from scipy.stats import norm
            var_return = norm.ppf(self.var_confidence, mean_return, std_return)
            var_amount = abs(var_return * portfolio_value)
        
        else:
            raise ValueError(f"不支持的VaR计算方法: {method}")
        
        # 计算滚动VaR
        rolling_var = self._calculate_rolling_var(portfolio_value, method)
        
        result = {
            'var': var_amount,
            'var_percentage': abs(var_return),
            'method': method,
            'confidence': 1-self.var_confidence,
            'portfolio_value': portfolio_value,
            'rolling_var': rolling_var,
            'data_points': len(returns_array)
        }
        
        logger.info(f"VaR计算完成: {var_amount:.2f} ({abs(var_return):.2%})")
        return result
    
    def _calculate_rolling_var(self, portfolio_value: float, method: str, window: int = 30) -> List[float]:
        """
        计算滚动VaR
        """
        if len(self.returns_history) < window:
            return []
        
        rolling_vars = []
        returns_array = np.array(self.returns_history)
        
        for i in range(window, len(returns_array) + 1):
            window_returns = returns_array[i-window:i]
            
            if method == 'historical':
                var_return = np.percentile(window_returns, self.var_confidence * 100)
            elif method == 'parametric':
                mean_return = np.mean(window_returns)
                std_return = np.std(window_returns)
                from scipy.stats import norm
                var_return = norm.ppf(self.var_confidence, mean_return, std_return)
            
            var_amount = abs(var_return * portfolio_value)
            rolling_vars.append(var_amount)
        
        return rolling_vars
    
    def check_liquidity_risk(self, symbol: str, order_size: float, current_volume: float, 
                           bid_ask_spread: float = None) -> Dict:
        """
        流动性风险评估
        
        Args:
            symbol: 交易品种
            order_size: 订单大小
            current_volume: 当前成交量
            bid_ask_spread: 买卖价差
        
        Returns:
            dict: 流动性风险评估结果
        """
        assessment = {
            'symbol': symbol,
            'liquidity_score': 'UNKNOWN',
            'market_impact_estimate': 0.0,
            'recommended_max_order': 0.0,
            'warnings': []
        }
        
        # 计算订单占成交量比例
        if current_volume > 0:
            volume_ratio = abs(order_size) / current_volume
            
            # 流动性评分
            if volume_ratio < 0.01:  # 小于1%
                assessment['liquidity_score'] = 'HIGH'
                assessment['market_impact_estimate'] = volume_ratio * 0.1  # 估算市场冲击
            elif volume_ratio < 0.05:  # 1-5%
                assessment['liquidity_score'] = 'MEDIUM'
                assessment['market_impact_estimate'] = volume_ratio * 0.2
                assessment['warnings'].append("中等流动性风险")
            else:  # 大于5%
                assessment['liquidity_score'] = 'LOW'
                assessment['market_impact_estimate'] = volume_ratio * 0.5
                assessment['warnings'].append("高流动性风险，建议分批交易")
            
            # 推荐最大订单大小（不超过成交量的2%）
            assessment['recommended_max_order'] = current_volume * 0.02
        
        # 买卖价差检查
        if bid_ask_spread is not None:
            if bid_ask_spread > 0.01:  # 大于1%
                assessment['warnings'].append(f"买卖价差较大: {bid_ask_spread:.2%}")
        
        logger.info(f"流动性评估 {symbol}: {assessment['liquidity_score']}, 市场冲击估算: {assessment['market_impact_estimate']:.2%}")
        return assessment
    
    def validate_market_data(self, price: float, volume: float, 
                           previous_price: float = None, 
                           futures_price: float = None) -> Dict:
        """
        市场数据验证
        
        Args:
            price: 当前价格
            volume: 成交量
            previous_price: 前一价格
            futures_price: 期货价格（如果适用）
        
        Returns:
            dict: 数据验证结果
        """
        validation = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # 基本数据检查
        if price <= 0:
            validation['is_valid'] = False
            validation['errors'].append(f"价格无效: {price}")
        
        if volume < 0:
            validation['is_valid'] = False
            validation['errors'].append(f"成交量无效: {volume}")
        
        # 价格合理性检查
        if previous_price is not None and previous_price > 0:
            price_change = abs(price - previous_price) / previous_price
            if price_change > 0.2:  # 20%变化阈值
                validation['warnings'].append(f"价格变化异常: {price_change:.2%}")
        
        # 期货vs现货价格检查
        if futures_price is not None and futures_price > 0:
            price_diff = abs(futures_price - price) / price
            if price_diff > 0.05:  # 5%差异阈值
                validation['warnings'].append(f"期货现货价差异常: {price_diff:.2%}")
        
        # 成交量异常检查
        if len(self.volume_history) >= 5:
            avg_volume = np.mean(list(self.volume_history)[-5:])
            if volume > avg_volume * 10:  # 10倍异常
                validation['warnings'].append(f"成交量异常放大: {volume/avg_volume:.1f}倍")
        
        return validation
    
    def get_risk_summary(self, portfolio_value: float) -> Dict:
        """
        获取风险摘要报告
        """
        summary = {
            'timestamp': datetime.now(),
            'portfolio_value': portfolio_value,
            'data_points': len(self.returns_history),
            'var_analysis': None,
            'recent_alerts': [],
            'risk_metrics': {}
        }
        
        # VaR分析
        if len(self.returns_history) >= 30:
            summary['var_analysis'] = self.calculate_var(portfolio_value)
        
        # 风险指标
        if len(self.returns_history) > 0:
            returns_array = np.array(self.returns_history)
            summary['risk_metrics'] = {
                'volatility': np.std(returns_array),
                'max_drawdown': self._calculate_max_drawdown(),
                'sharpe_ratio': self._calculate_sharpe_ratio(returns_array),
                'skewness': self._calculate_skewness(returns_array),
                'kurtosis': self._calculate_kurtosis(returns_array)
            }
        
        return summary
    
    def _calculate_max_drawdown(self) -> float:
        """
        计算最大回撤
        """
        if len(self.price_history) < 2:
            return 0.0
        
        prices = np.array(self.price_history)
        cumulative = np.cumprod(1 + np.diff(prices) / prices[:-1])
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        return abs(np.min(drawdown))
    
    def _calculate_sharpe_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """
        计算夏普比率
        """
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252  # 日化无风险利率
        if np.std(excess_returns) == 0:
            return 0.0
        
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
    
    def _calculate_skewness(self, returns: np.ndarray) -> float:
        """
        计算偏度
        """
        if len(returns) < 3:
            return 0.0
        
        from scipy.stats import skew
        return skew(returns)
    
    def _calculate_kurtosis(self, returns: np.ndarray) -> float:
        """
        计算峰度
        """
        if len(returns) < 4:
            return 0.0
        
        from scipy.stats import kurtosis
        return kurtosis(returns)