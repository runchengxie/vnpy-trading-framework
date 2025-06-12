# exception_handler.py
import logging
import time
import traceback
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import threading
from functools import wraps
import json

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"          # 轻微错误，可以继续运行
    MEDIUM = "medium"    # 中等错误，需要重试或调整
    HIGH = "high"        # 严重错误，需要人工干预
    CRITICAL = "critical" # 致命错误，必须停止交易

class ErrorCategory(Enum):
    """错误类别"""
    NETWORK = "network"              # 网络连接错误
    API = "api"                      # API调用错误
    ORDER_EXECUTION = "order_execution" # 订单执行错误
    DATA_QUALITY = "data_quality"    # 数据质量问题
    RISK_MANAGEMENT = "risk_management" # 风险管理错误
    SYSTEM = "system"                # 系统错误
    STRATEGY = "strategy"            # 策略逻辑错误

@dataclass
class ErrorRecord:
    """错误记录"""
    timestamp: datetime
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    traceback_info: str
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    resolved: bool = False
    resolution_action: Optional[str] = None
    resolution_timestamp: Optional[datetime] = None

class RetryConfig:
    """重试配置"""
    def __init__(self, 
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_backoff: bool = True,
                 jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        if self.exponential_backoff:
            delay = self.base_delay * (2 ** attempt)
        else:
            delay = self.base_delay
        
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # 添加50%的随机抖动
        
        return delay

class CircuitBreaker:
    """熔断器模式实现"""
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs):
        """通过熔断器调用函数"""
        with self._lock:
            if self.state == 'OPEN':
                if self._should_attempt_reset():
                    self.state = 'HALF_OPEN'
                else:
                    raise Exception(f"熔断器开启状态，拒绝调用 {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置熔断器"""
        return (self.last_failure_time and 
                time.time() - self.last_failure_time >= self.recovery_timeout)
    
    def _on_success(self):
        """成功时的处理"""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def _on_failure(self):
        """失败时的处理"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"熔断器开启，失败次数: {self.failure_count}")

class ExceptionHandler:
    """综合异常处理器"""
    
    def __init__(self):
        self.error_records: List[ErrorRecord] = []
        self.retry_configs: Dict[ErrorCategory, RetryConfig] = self._init_retry_configs()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.error_callbacks: Dict[ErrorCategory, List[Callable]] = {}
        self.emergency_stop_triggered = False
        self._lock = threading.Lock()
        
        logger.info("异常处理器初始化完成")
    
    def _init_retry_configs(self) -> Dict[ErrorCategory, RetryConfig]:
        """初始化重试配置"""
        return {
            ErrorCategory.NETWORK: RetryConfig(max_retries=5, base_delay=2.0, max_delay=30.0),
            ErrorCategory.API: RetryConfig(max_retries=3, base_delay=1.0, max_delay=10.0),
            ErrorCategory.ORDER_EXECUTION: RetryConfig(max_retries=2, base_delay=0.5, max_delay=5.0),
            ErrorCategory.DATA_QUALITY: RetryConfig(max_retries=3, base_delay=1.0, max_delay=15.0),
            ErrorCategory.RISK_MANAGEMENT: RetryConfig(max_retries=1, base_delay=0.1, max_delay=1.0),
            ErrorCategory.SYSTEM: RetryConfig(max_retries=2, base_delay=5.0, max_delay=60.0),
            ErrorCategory.STRATEGY: RetryConfig(max_retries=1, base_delay=1.0, max_delay=5.0)
        }
    
    def register_circuit_breaker(self, name: str, circuit_breaker: CircuitBreaker):
        """注册熔断器"""
        self.circuit_breakers[name] = circuit_breaker
        logger.info(f"熔断器已注册: {name}")
    
    def register_error_callback(self, category: ErrorCategory, callback: Callable):
        """注册错误回调函数"""
        if category not in self.error_callbacks:
            self.error_callbacks[category] = []
        self.error_callbacks[category].append(callback)
        logger.info(f"错误回调已注册: {category.value}")
    
    def handle_exception(self, 
                        exception: Exception,
                        category: ErrorCategory,
                        severity: ErrorSeverity,
                        context: Dict[str, Any] = None) -> ErrorRecord:
        """处理异常"""
        error_record = ErrorRecord(
            timestamp=datetime.now(),
            error_type=type(exception).__name__,
            category=category,
            severity=severity,
            message=str(exception),
            traceback_info=traceback.format_exc(),
            context=context or {}
        )
        
        with self._lock:
            self.error_records.append(error_record)
        
        logger.error(f"异常处理: {category.value} - {severity.value} - {error_record.message}")
        
        # 执行错误回调
        self._execute_error_callbacks(category, error_record)
        
        # 检查是否需要紧急停止
        if severity == ErrorSeverity.CRITICAL:
            self._trigger_emergency_stop(error_record)
        
        return error_record
    
    def _execute_error_callbacks(self, category: ErrorCategory, error_record: ErrorRecord):
        """执行错误回调函数"""
        if category in self.error_callbacks:
            for callback in self.error_callbacks[category]:
                try:
                    callback(error_record)
                except Exception as e:
                    logger.error(f"错误回调执行失败: {e}")
    
    def _trigger_emergency_stop(self, error_record: ErrorRecord):
        """触发紧急停止"""
        self.emergency_stop_triggered = True
        logger.critical(f"触发紧急停止: {error_record.message}")
        
        # 这里可以添加紧急停止的具体逻辑
        # 例如：关闭所有持仓、停止策略执行等
    
    def retry_with_backoff(self, 
                          func: Callable,
                          category: ErrorCategory,
                          *args, **kwargs) -> Any:
        """带退避策略的重试机制"""
        retry_config = self.retry_configs.get(category, RetryConfig())
        last_exception = None
        
        for attempt in range(retry_config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < retry_config.max_retries:
                    delay = retry_config.get_delay(attempt)
                    logger.warning(f"重试 {attempt + 1}/{retry_config.max_retries}, 延迟 {delay:.2f}秒: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"重试失败，已达到最大重试次数: {e}")
        
        # 记录最终失败
        severity = ErrorSeverity.HIGH if category in [ErrorCategory.ORDER_EXECUTION, ErrorCategory.RISK_MANAGEMENT] else ErrorSeverity.MEDIUM
        self.handle_exception(last_exception, category, severity, {'retry_attempts': retry_config.max_retries})
        raise last_exception
    
    def with_circuit_breaker(self, circuit_breaker_name: str):
        """装饰器：使用熔断器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if circuit_breaker_name in self.circuit_breakers:
                    circuit_breaker = self.circuit_breakers[circuit_breaker_name]
                    return circuit_breaker.call(func, *args, **kwargs)
                else:
                    return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def safe_execute(self, 
                    func: Callable,
                    category: ErrorCategory,
                    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                    context: Dict[str, Any] = None,
                    default_return: Any = None) -> Any:
        """安全执行函数，捕获并处理异常"""
        try:
            return func()
        except Exception as e:
            self.handle_exception(e, category, severity, context)
            return default_return
    
    def get_error_statistics(self, hours: int = 24) -> Dict:
        """获取错误统计信息"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [err for err in self.error_records if err.timestamp >= cutoff_time]
        
        # 按类别统计
        category_stats = {}
        for category in ErrorCategory:
            category_errors = [err for err in recent_errors if err.category == category]
            category_stats[category.value] = {
                'count': len(category_errors),
                'severity_breakdown': {
                    severity.value: len([err for err in category_errors if err.severity == severity])
                    for severity in ErrorSeverity
                }
            }
        
        # 按严重程度统计
        severity_stats = {}
        for severity in ErrorSeverity:
            severity_errors = [err for err in recent_errors if err.severity == severity]
            severity_stats[severity.value] = len(severity_errors)
        
        # 最常见错误
        error_types = {}
        for error in recent_errors:
            error_type = error.error_type
            if error_type not in error_types:
                error_types[error_type] = 0
            error_types[error_type] += 1
        
        most_common_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'analysis_period_hours': hours,
            'total_errors': len(recent_errors),
            'category_breakdown': category_stats,
            'severity_breakdown': severity_stats,
            'most_common_errors': most_common_errors,
            'emergency_stop_status': self.emergency_stop_triggered,
            'circuit_breaker_status': {
                name: cb.state for name, cb in self.circuit_breakers.items()
            }
        }
    
    def resolve_error(self, error_index: int, resolution_action: str):
        """标记错误为已解决"""
        if 0 <= error_index < len(self.error_records):
            error_record = self.error_records[error_index]
            error_record.resolved = True
            error_record.resolution_action = resolution_action
            error_record.resolution_timestamp = datetime.now()
            
            logger.info(f"错误已解决: {error_record.error_type} - {resolution_action}")
        else:
            logger.warning(f"无效的错误索引: {error_index}")
    
    def reset_emergency_stop(self):
        """重置紧急停止状态"""
        self.emergency_stop_triggered = False
        logger.info("紧急停止状态已重置")
    
    def export_error_log(self, file_path: str):
        """导出错误日志"""
        error_data = []
        for error in self.error_records:
            error_data.append({
                'timestamp': error.timestamp.isoformat(),
                'error_type': error.error_type,
                'category': error.category.value,
                'severity': error.severity.value,
                'message': error.message,
                'context': error.context,
                'retry_count': error.retry_count,
                'resolved': error.resolved,
                'resolution_action': error.resolution_action,
                'resolution_timestamp': error.resolution_timestamp.isoformat() if error.resolution_timestamp else None
            })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"错误日志已导出到: {file_path}")

# 装饰器函数
def handle_exceptions(category: ErrorCategory, 
                     severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                     retry: bool = False,
                     default_return: Any = None):
    """异常处理装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 假设第一个参数是包含exception_handler的对象
            if args and hasattr(args[0], 'exception_handler'):
                handler = args[0].exception_handler
                
                if retry:
                    return handler.retry_with_backoff(func, category, *args, **kwargs)
                else:
                    return handler.safe_execute(
                        lambda: func(*args, **kwargs),
                        category,
                        severity,
                        {'function': func.__name__},
                        default_return
                    )
            else:
                # 如果没有exception_handler，直接执行
                return func(*args, **kwargs)
        return wrapper
    return decorator

# 示例使用
if __name__ == "__main__":
    # 创建异常处理器
    handler = ExceptionHandler()
    
    # 注册熔断器
    api_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    handler.register_circuit_breaker("api_calls", api_circuit_breaker)
    
    # 注册错误回调
    def on_network_error(error_record: ErrorRecord):
        print(f"网络错误回调: {error_record.message}")
    
    handler.register_error_callback(ErrorCategory.NETWORK, on_network_error)
    
    # 测试异常处理
    try:
        raise ConnectionError("网络连接失败")
    except Exception as e:
        handler.handle_exception(e, ErrorCategory.NETWORK, ErrorSeverity.MEDIUM)
    
    # 打印统计信息
    stats = handler.get_error_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))