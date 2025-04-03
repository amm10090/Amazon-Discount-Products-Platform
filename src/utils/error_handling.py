"""
错误处理模块，提供统一的异常处理和错误追踪机制。
集成了Loguru日志系统，支持详细的错误信息记录和分析。
"""

import sys
import enum
import traceback
from typing import Dict, Any, Optional, Type, List, Callable
from datetime import datetime, UTC
from functools import wraps

from loguru import logger
from .log_config import get_logger

class ErrorCode(enum.Enum):
    """系统错误码枚举。"""
    
    # 系统错误 (1000-1999)
    SYSTEM_ERROR = 1000
    CONFIG_ERROR = 1001
    RESOURCE_ERROR = 1002
    INITIALIZATION_ERROR = 1003
    
    # 业务错误 (2000-2999)
    VALIDATION_ERROR = 2000
    BUSINESS_RULE_ERROR = 2001
    INVALID_OPERATION = 2002
    STATE_ERROR = 2003
    
    # 外部服务错误 (3000-3999)
    API_ERROR = 3000
    NETWORK_ERROR = 3001
    TIMEOUT_ERROR = 3002
    EXTERNAL_SERVICE_ERROR = 3003
    
    # 数据错误 (4000-4999)
    DATA_ERROR = 4000
    DATABASE_ERROR = 4001
    SERIALIZATION_ERROR = 4002
    DATA_NOT_FOUND = 4003
    
    # 权限错误 (5000-5999)
    AUTHENTICATION_ERROR = 5000
    AUTHORIZATION_ERROR = 5001
    PERMISSION_DENIED = 5002
    TOKEN_ERROR = 5003

class ErrorLevel(enum.Enum):
    """错误级别枚举。"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class CustomException(Exception):
    """
    自定义异常基类，所有业务异常都应继承此类。
    
    属性:
        error_code: 错误码
        message: 错误消息
        details: 详细错误信息
        context: 错误发生时的上下文信息
        level: 错误级别
    """
    
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        level: ErrorLevel = ErrorLevel.ERROR
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.context = context or {}
        self.level = level
        self.timestamp = datetime.now(UTC)
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """将异常信息转换为字典格式。"""
        return {
            "error_code": self.error_code.value,
            "error_name": self.error_code.name,
            "message": self.message,
            "details": self.details,
            "context": self.context,
            "level": self.level.value,
            "timestamp": self.timestamp.isoformat(),
            "traceback": traceback.format_exc()
        }

class ErrorHandler:
    """
    全局错误处理器，负责捕获、格式化和记录异常。
    
    支持错误过滤、自定义处理器和错误统计。
    """
    
    def __init__(self):
        self._error_filters: List[Callable[[Exception], bool]] = []
        self._error_handlers: Dict[Type[Exception], Callable] = {}
        self._metrics = ErrorMetrics()
        self._logger = get_logger("error_handler")
        self._async_exception_handler = None
    
    def add_filter(self, filter_func: Callable[[Exception], bool]) -> None:
        """添加错误过滤器。"""
        self._error_filters.append(filter_func)
    
    def add_handler(
        self,
        exception_type: Type[Exception],
        handler: Callable[[Exception], None]
    ) -> None:
        """为特定异常类型添加处理器。"""
        self._error_handlers[exception_type] = handler
    
    def setup_async_handler(self, loop=None):
        """
        将异步异常处理器绑定到事件循环。
        
        Args:
            loop: 要绑定的事件循环，如果为None则尝试获取当前事件循环
        """
        if not self._async_exception_handler:
            return
            
        try:
            import asyncio
            # 尝试获取当前事件循环，如果提供了loop则使用提供的
            target_loop = loop or asyncio.get_event_loop()
            target_loop.set_exception_handler(self._async_exception_handler)
        except (ImportError, RuntimeError):
            # 忽略异步相关错误
            pass
    
    def handle(self, exc: Exception) -> None:
        """
        处理异常。
        
        Args:
            exc: 要处理的异常
        """
        # 检查是否应该过滤此错误
        if any(f(exc) for f in self._error_filters):
            return
        
        # 获取异常信息
        error_info = self._get_error_info(exc)
        
        # 更新错误统计
        self._metrics.record_error(exc)
        
        # 使用合适的日志级别记录错误
        log_level = (
            error_info.get("level", "ERROR")
            if isinstance(exc, CustomException)
            else "ERROR"
        )
        
        # 记录错误
        self._logger.log(
            log_level,
            "错误发生",
            error=error_info
        )
        
        # 调用自定义处理器
        for exc_type, handler in self._error_handlers.items():
            if isinstance(exc, exc_type):
                handler(exc)
                break
    
    def _get_error_info(self, exc: Exception) -> Dict[str, Any]:
        """获取异常的详细信息。"""
        if isinstance(exc, CustomException):
            return exc.to_dict()
        
        return {
            "error_code": ErrorCode.SYSTEM_ERROR.value,
            "error_name": ErrorCode.SYSTEM_ERROR.name,
            "message": str(exc),
            "details": {},
            "context": {},
            "level": "ERROR",
            "timestamp": datetime.now(UTC).isoformat(),
            "traceback": traceback.format_exc()
        }

class ErrorMetrics:
    """
    错误统计指标收集器。
    
    跟踪错误发生次数、频率和分布等统计信息。
    """
    
    def __init__(self):
        self._error_counts: Dict[Type[Exception], int] = {}
        self._error_codes_count: Dict[ErrorCode, int] = {}
        self._last_errors: List[Dict[str, Any]] = []
        self._max_last_errors = 100
    
    def record_error(self, exc: Exception) -> None:
        """记录一个错误。"""
        # 更新错误类型计数
        exc_type = type(exc)
        self._error_counts[exc_type] = self._error_counts.get(exc_type, 0) + 1
        
        # 如果是自定义异常，更新错误码计数
        if isinstance(exc, CustomException):
            self._error_codes_count[exc.error_code] = (
                self._error_codes_count.get(exc.error_code, 0) + 1
            )
        
        # 保存最近的错误
        error_info = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": exc.__class__.__name__,
            "message": str(exc)
        }
        
        self._last_errors.append(error_info)
        if len(self._last_errors) > self._max_last_errors:
            self._last_errors.pop(0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取错误统计指标。"""
        return {
            "error_counts": {
                exc_type.__name__: count
                for exc_type, count in self._error_counts.items()
            },
            "error_codes_count": {
                code.name: count
                for code, count in self._error_codes_count.items()
            },
            "last_errors": self._last_errors
        }

def error_handler(error_code: ErrorCode, level: ErrorLevel = ErrorLevel.ERROR):
    """
    异常处理装饰器，用于自动捕获和处理函数执行期间的异常。
    
    Args:
        error_code: 发生异常时使用的错误码
        level: 错误级别
        
    示例：
        @error_handler(ErrorCode.API_ERROR)
        def call_external_api():
            # 可能抛出异常的代码
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, CustomException):
                    raise
                
                raise CustomException(
                    error_code=error_code,
                    message=f"执行 {func.__name__} 时发生错误: {str(e)}",
                    details={"args": args, "kwargs": kwargs},
                    level=level
                ) from e
        return wrapper
    return decorator

# 创建全局错误处理器实例
global_error_handler = ErrorHandler()

def setup_error_handling():
    """
    设置全局异常处理。
    
    此函数应在应用启动时调用，用于配置全局异常处理器。
    """
    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        """处理未捕获的异常。"""
        if issubclass(exc_type, KeyboardInterrupt):
            # 对于键盘中断，使用系统默认处理
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # 使用全局错误处理器处理异常
        global_error_handler.handle(exc_value)
    
    # 设置全局异常处理器
    sys.excepthook = handle_uncaught_exception
    
    # 配置异步异常处理函数
    try:
        import asyncio
        
        def handle_async_exception(loop, context):
            """处理异步代码中的异常。"""
            exc = context.get("exception")
            if exc:
                global_error_handler.handle(exc)
            else:
                logger.error(f"异步错误: {context['message']}")
        
        # 设置全局异常处理器的异步处理函数
        global_error_handler._async_exception_handler = handle_async_exception
        
    except ImportError:
        # 如果不需要异步支持，可以忽略
        pass 