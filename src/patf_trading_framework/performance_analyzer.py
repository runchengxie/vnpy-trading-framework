# performance_analyzer.py
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TradeRecord:
    """
    交易记录数据结构
    """
    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    price: float
    commission: float
    order_id: str
    execution_time: float = 0.0  # 执行时间（秒）
    slippage: float = 0.0  # 滑点
    market_impact: float = 0.0  # 市场冲击

class PerformanceAnalyzer:
    """
    专业的算法交易性能分析器
    包含换手率、交易成本、风险调整收益等专业指标
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.trades: List[TradeRecord] = []
        self.portfolio_values: List[Tuple[datetime, float]] = []
        self.positions: Dict[str, float] = {}  # symbol -> quantity
        self.cash = initial_capital
        
        logger.info(f"性能分析器初始化，初始资金: {initial_capital:,.2f}")
    
    def add_trade(self, trade: TradeRecord):
        """
        添加交易记录
        """
        self.trades.append(trade)
        
        # 更新持仓
        if trade.symbol not in self.positions:
            self.positions[trade.symbol] = 0.0
        
        if trade.side == 'buy':
            self.positions[trade.symbol] += trade.quantity
            self.cash -= (trade.quantity * trade.price + trade.commission)
        else:  # sell
            self.positions[trade.symbol] -= trade.quantity
            self.cash += (trade.quantity * trade.price - trade.commission)
        
        logger.debug(f"添加交易记录: {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
    
    def update_portfolio_value(self, timestamp: datetime, market_prices: Dict[str, float]):
        """
        更新组合价值
        
        Args:
            timestamp: 时间戳
            market_prices: 市场价格字典 {symbol: price}
        """
        portfolio_value = self.cash
        
        for symbol, quantity in self.positions.items():
            if symbol in market_prices and quantity != 0:
                portfolio_value += quantity * market_prices[symbol]
        
        self.portfolio_values.append((timestamp, portfolio_value))
        logger.debug(f"组合价值更新: {portfolio_value:,.2f}")
    
    def calculate_returns(self) -> pd.Series:
        """
        计算收益率序列
        """
        if len(self.portfolio_values) < 2:
            return pd.Series()
        
        df = pd.DataFrame(self.portfolio_values, columns=['timestamp', 'value'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        returns = df['value'].pct_change().dropna()
        return returns
    
    def calculate_turnover_rate(self, period_days: int = 30) -> Dict:
        """
        计算换手率
        
        Args:
            period_days: 计算周期（天）
        
        Returns:
            dict: 换手率分析结果
        """
        if not self.trades:
            return {'turnover_rate': 0.0, 'analysis_period': period_days}
        
        # 获取指定期间的交易
        end_date = max(trade.timestamp for trade in self.trades)
        start_date = end_date - timedelta(days=period_days)
        
        period_trades = [t for t in self.trades if start_date <= t.timestamp <= end_date]
        
        if not period_trades:
            return {'turnover_rate': 0.0, 'analysis_period': period_days}
        
        # 计算交易总金额
        total_traded_value = sum(trade.quantity * trade.price for trade in period_trades)
        
        # 计算平均组合价值
        period_portfolio_values = [
            value for timestamp, value in self.portfolio_values 
            if start_date <= timestamp <= end_date
        ]
        
        if not period_portfolio_values:
            avg_portfolio_value = self.initial_capital
        else:
            avg_portfolio_value = np.mean(period_portfolio_values)
        
        # 换手率 = 交易总金额 / 平均组合价值
        turnover_rate = total_traded_value / avg_portfolio_value if avg_portfolio_value > 0 else 0.0
        
        # 年化换手率
        annualized_turnover = turnover_rate * (365 / period_days)
        
        result = {
            'turnover_rate': turnover_rate,
            'annualized_turnover': annualized_turnover,
            'total_traded_value': total_traded_value,
            'avg_portfolio_value': avg_portfolio_value,
            'analysis_period': period_days,
            'trade_count': len(period_trades)
        }
        
        logger.info(f"换手率分析: {turnover_rate:.2%} ({period_days}天), 年化: {annualized_turnover:.2%}")
        return result
    
    def calculate_trading_costs(self) -> Dict:
        """
        计算详细的交易成本分析
        """
        if not self.trades:
            return {}
        
        # 佣金成本
        total_commission = sum(trade.commission for trade in self.trades)
        
        # 滑点成本
        total_slippage = sum(abs(trade.slippage) * trade.quantity for trade in self.trades)
        
        # 市场冲击成本
        total_market_impact = sum(abs(trade.market_impact) * trade.quantity for trade in self.trades)
        
        # 总交易金额
        total_traded_value = sum(trade.quantity * trade.price for trade in self.trades)
        
        # 成本比率
        commission_rate = total_commission / total_traded_value if total_traded_value > 0 else 0.0
        slippage_rate = total_slippage / total_traded_value if total_traded_value > 0 else 0.0
        market_impact_rate = total_market_impact / total_traded_value if total_traded_value > 0 else 0.0
        
        total_cost = total_commission + total_slippage + total_market_impact
        total_cost_rate = total_cost / total_traded_value if total_traded_value > 0 else 0.0
        
        # 按品种分析
        cost_by_symbol = {}
        for symbol in set(trade.symbol for trade in self.trades):
            symbol_trades = [t for t in self.trades if t.symbol == symbol]
            symbol_commission = sum(t.commission for t in symbol_trades)
            symbol_slippage = sum(abs(t.slippage) * t.quantity for t in symbol_trades)
            symbol_market_impact = sum(abs(t.market_impact) * t.quantity for t in symbol_trades)
            symbol_value = sum(t.quantity * t.price for t in symbol_trades)
            
            cost_by_symbol[symbol] = {
                'commission': symbol_commission,
                'slippage': symbol_slippage,
                'market_impact': symbol_market_impact,
                'total_cost': symbol_commission + symbol_slippage + symbol_market_impact,
                'traded_value': symbol_value,
                'cost_rate': (symbol_commission + symbol_slippage + symbol_market_impact) / symbol_value if symbol_value > 0 else 0.0
            }
        
        result = {
            'total_commission': total_commission,
            'total_slippage': total_slippage,
            'total_market_impact': total_market_impact,
            'total_cost': total_cost,
            'total_traded_value': total_traded_value,
            'commission_rate': commission_rate,
            'slippage_rate': slippage_rate,
            'market_impact_rate': market_impact_rate,
            'total_cost_rate': total_cost_rate,
            'cost_by_symbol': cost_by_symbol,
            'trade_count': len(self.trades)
        }
        
        logger.info(f"交易成本分析: 总成本率 {total_cost_rate:.4%}, 佣金 {commission_rate:.4%}, 滑点 {slippage_rate:.4%}")
        return result
    
    def calculate_risk_metrics(self) -> Dict:
        """
        计算风险调整收益指标
        """
        returns = self.calculate_returns()
        
        if len(returns) < 2:
            return {}
        
        # 基础统计
        total_return = (self.portfolio_values[-1][1] / self.initial_capital - 1) if self.portfolio_values else 0.0
        annualized_return = (1 + total_return) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0.0
        volatility = returns.std() * np.sqrt(252)
        
        # 夏普比率
        risk_free_rate = 0.02  # 假设2%无风险利率
        excess_returns = returns - risk_free_rate / 252
        sharpe_ratio = excess_returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0.0
        
        # 最大回撤
        portfolio_df = pd.DataFrame(self.portfolio_values, columns=['timestamp', 'value'])
        portfolio_df.set_index('timestamp', inplace=True)
        cumulative_returns = portfolio_df['value'] / self.initial_capital
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Calmar比率
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
        
        # Sortino比率
        downside_returns = returns[returns < 0]
        downside_deviation = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0.0
        sortino_ratio = (annualized_return - risk_free_rate) / downside_deviation if downside_deviation > 0 else 0.0
        
        # VaR和CVaR
        var_95 = np.percentile(returns, 5)
        cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else 0.0
        
        # 胜率和盈亏比
        if self.trades:
            profitable_trades = []
            losing_trades = []
            
            # 按配对交易计算盈亏
            positions_tracker = {}
            for trade in self.trades:
                symbol = trade.symbol
                if symbol not in positions_tracker:
                    positions_tracker[symbol] = {'quantity': 0.0, 'cost_basis': 0.0}
                
                if trade.side == 'buy':
                    old_quantity = positions_tracker[symbol]['quantity']
                    old_cost = positions_tracker[symbol]['cost_basis'] * old_quantity
                    new_cost = trade.quantity * trade.price + trade.commission
                    
                    positions_tracker[symbol]['quantity'] += trade.quantity
                    if positions_tracker[symbol]['quantity'] > 0:
                        positions_tracker[symbol]['cost_basis'] = (old_cost + new_cost) / positions_tracker[symbol]['quantity']
                
                else:  # sell
                    if positions_tracker[symbol]['quantity'] > 0:
                        cost_basis = positions_tracker[symbol]['cost_basis']
                        pnl = (trade.price - cost_basis) * trade.quantity - trade.commission
                        
                        if pnl > 0:
                            profitable_trades.append(pnl)
                        else:
                            losing_trades.append(abs(pnl))
                        
                        positions_tracker[symbol]['quantity'] -= trade.quantity
            
            win_rate = len(profitable_trades) / (len(profitable_trades) + len(losing_trades)) if (len(profitable_trades) + len(losing_trades)) > 0 else 0.0
            avg_win = np.mean(profitable_trades) if profitable_trades else 0.0
            avg_loss = np.mean(losing_trades) if losing_trades else 0.0
            profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')
        else:
            win_rate = 0.0
            profit_factor = 0.0
        
        result = {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio,
            'sortino_ratio': sortino_ratio,
            'var_95': var_95,
            'cvar_95': cvar_95,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(self.trades),
            'analysis_period_days': (max(trade.timestamp for trade in self.trades) - min(trade.timestamp for trade in self.trades)).days if self.trades else 0
        }
        
        logger.info(f"风险指标: 夏普比率 {sharpe_ratio:.2f}, 最大回撤 {max_drawdown:.2%}, 胜率 {win_rate:.2%}")
        return result
    
    def calculate_concentration_risk(self) -> Dict:
        """
        计算集中度风险
        """
        if not self.portfolio_values:
            return {}
        
        current_portfolio_value = self.portfolio_values[-1][1]
        
        # 计算各品种权重
        weights = {}
        total_position_value = 0.0
        
        # 需要当前市场价格来计算，这里假设使用最后交易价格
        symbol_prices = {}
        for trade in reversed(self.trades):
            if trade.symbol not in symbol_prices:
                symbol_prices[trade.symbol] = trade.price
        
        for symbol, quantity in self.positions.items():
            if quantity != 0 and symbol in symbol_prices:
                position_value = abs(quantity * symbol_prices[symbol])
                weights[symbol] = position_value / current_portfolio_value
                total_position_value += position_value
        
        # 计算集中度指标
        if weights:
            # 赫芬达尔指数
            herfindahl_index = sum(w**2 for w in weights.values())
            
            # 最大权重
            max_weight = max(weights.values())
            
            # 前三大持仓权重
            top3_weights = sorted(weights.values(), reverse=True)[:3]
            top3_concentration = sum(top3_weights)
            
            # 有效品种数量
            effective_positions = 1 / herfindahl_index if herfindahl_index > 0 else 0
        else:
            herfindahl_index = 0.0
            max_weight = 0.0
            top3_concentration = 0.0
            effective_positions = 0
        
        result = {
            'position_weights': weights,
            'herfindahl_index': herfindahl_index,
            'max_weight': max_weight,
            'top3_concentration': top3_concentration,
            'effective_positions': effective_positions,
            'cash_weight': self.cash / current_portfolio_value,
            'total_positions': len([w for w in weights.values() if w > 0.001])  # 权重大于0.1%的持仓
        }
        
        logger.info(f"集中度风险: 最大权重 {max_weight:.2%}, 前三大 {top3_concentration:.2%}, 有效持仓数 {effective_positions:.1f}")
        return result
    
    def generate_performance_report(self) -> Dict:
        """
        生成综合性能报告
        """
        logger.info("生成综合性能报告...")
        
        report = {
            'report_timestamp': datetime.now(),
            'initial_capital': self.initial_capital,
            'current_value': self.portfolio_values[-1][1] if self.portfolio_values else self.initial_capital,
            'cash_position': self.cash,
            'active_positions': {k: v for k, v in self.positions.items() if abs(v) > 1e-6},
            'returns_analysis': self.calculate_risk_metrics(),
            'trading_costs': self.calculate_trading_costs(),
            'turnover_analysis': self.calculate_turnover_rate(),
            'concentration_risk': self.calculate_concentration_risk()
        }
        
        # 添加摘要指标
        if report['returns_analysis']:
            report['summary'] = {
                'total_return': report['returns_analysis'].get('total_return', 0.0),
                'sharpe_ratio': report['returns_analysis'].get('sharpe_ratio', 0.0),
                'max_drawdown': report['returns_analysis'].get('max_drawdown', 0.0),
                'win_rate': report['returns_analysis'].get('win_rate', 0.0),
                'total_cost_rate': report['trading_costs'].get('total_cost_rate', 0.0),
                'turnover_rate': report['turnover_analysis'].get('annualized_turnover', 0.0),
                'max_concentration': report['concentration_risk'].get('max_weight', 0.0)
            }
        
        logger.info("性能报告生成完成")
        return report
    
    def plot_performance_charts(self, save_path: str = None):
        """
        绘制性能图表
        
        Args:
            save_path: 保存路径，如果为None则显示图表
        """
        if not self.portfolio_values:
            logger.warning("没有组合价值数据，无法绘制图表")
            return
        
        # 创建子图
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('算法交易性能分析', fontsize=16)
        
        # 1. 组合价值曲线
        portfolio_df = pd.DataFrame(self.portfolio_values, columns=['timestamp', 'value'])
        portfolio_df.set_index('timestamp', inplace=True)
        
        axes[0, 0].plot(portfolio_df.index, portfolio_df['value'])
        axes[0, 0].axhline(y=self.initial_capital, color='r', linestyle='--', alpha=0.7, label='初始资金')
        axes[0, 0].set_title('组合价值变化')
        axes[0, 0].set_ylabel('价值')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # 2. 回撤曲线
        cumulative_returns = portfolio_df['value'] / self.initial_capital
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        
        axes[0, 1].fill_between(drawdown.index, drawdown, 0, alpha=0.3, color='red')
        axes[0, 1].plot(drawdown.index, drawdown, color='red')
        axes[0, 1].set_title('回撤曲线')
        axes[0, 1].set_ylabel('回撤比例')
        axes[0, 1].grid(True, alpha=0.3)
        
        # 3. 收益率分布
        returns = self.calculate_returns()
        if len(returns) > 0:
            axes[1, 0].hist(returns, bins=50, alpha=0.7, edgecolor='black')
            axes[1, 0].axvline(returns.mean(), color='red', linestyle='--', label=f'均值: {returns.mean():.4f}')
            axes[1, 0].set_title('收益率分布')
            axes[1, 0].set_xlabel('日收益率')
            axes[1, 0].set_ylabel('频次')
            axes[1, 0].legend()
            axes[1, 0].grid(True, alpha=0.3)
        
        # 4. 滚动夏普比率
        if len(returns) >= 30:
            rolling_sharpe = returns.rolling(window=30).mean() / returns.rolling(window=30).std() * np.sqrt(252)
            axes[1, 1].plot(rolling_sharpe.index, rolling_sharpe)
            axes[1, 1].axhline(y=0, color='black', linestyle='-', alpha=0.3)
            axes[1, 1].axhline(y=1, color='green', linestyle='--', alpha=0.7, label='夏普比率=1')
            axes[1, 1].set_title('滚动夏普比率 (30天)')
            axes[1, 1].set_ylabel('夏普比率')
            axes[1, 1].legend()
            axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"性能图表已保存到: {save_path}")
        else:
            plt.show()
        
        plt.close()