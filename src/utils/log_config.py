"""
日志配置模块，使用Loguru实现高级日志处理功能。
提供统一的日志配置、格式化和处理机制。
"""

import sys
import os
import json
import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, TypeVar, Callable, AsyncContextManager
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from loguru import logger
from loguru._logger import Logger

# 计算项目根目录
# 假设当前文件在 src/utils/log_config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认配置
DEFAULT_CONFIG = {
    "LOG_LEVEL": "INFO",
    "JSON_LOGS": False,
    "LOG_PATH": "logs",  # 这将是相对于项目根目录的路径
    "MAX_LOG_SIZE": "100 MB",
    "LOG_RETENTION": "30 days",
    "CONSOLE_LOG_FORMAT": (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[name]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    "FILE_LOG_FORMAT": (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{extra[name]} | "
        "process:{process} | thread:{thread} | "
        "{name}:{function}:{line} | {message}"
    )
}

# 上下文变量
_context_stack: ContextVar[List[Dict[str, Any]]] = ContextVar('_context_stack', default=[])
T = TypeVar('T')

class LogContext:
    """
    日志上下文管理器，支持同步和异步操作。
    提供性能监控和上下文数据管理功能。
    
    示例：
        # 同步使用
        with LogContext(task_id='123', module='user_service'):
            logger.info('处理用户请求')
            
        # 异步使用
        async with LogContext(task_id='456', module='auth_service'):
            logger.info('验证用户token')
            
        # 性能监控
        with LogContext(task_id='789', track_performance=True):
            # 执行耗时操作
            time.sleep(1)
    """
    
    def __init__(self, **kwargs):
        self.context_data = kwargs
        self.track_performance = kwargs.pop('track_performance', False) if 'track_performance' in kwargs else False
        self.start_time = None
        self._token = None
        
    def __enter__(self):
        # 获取当前上下文栈
        stack = _context_stack.get()
        # 创建新的上下文数据，继承父上下文的数据
        new_context = {}
        if stack:
            # 复制父上下文的数据
            new_context.update(stack[-1])
        # 更新新的上下文数据
        new_context.update(self.context_data)
        
        # 保存新的上下文栈
        new_stack = stack + [new_context]
        self._token = _context_stack.set(new_stack)
        
        # 更新logger的extra数据
        logger.configure(extra=new_context)
        
        if self.track_performance:
            self.start_time = time.perf_counter()
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.track_performance and self.start_time is not None:
            duration = time.perf_counter() - self.start_time
            # 确保在记录性能统计信息时绑定name属性
            logger.bind(name="PerformanceTracker").info(f"性能统计 - 执行时间: {duration:.3f}秒")
            
        # 恢复之前的上下文栈
        if self._token is not None:
            _context_stack.reset(self._token)
            
        # 获取当前栈
        stack = _context_stack.get()
        
        # 恢复到上一个上下文的extra数据
        if stack:
            logger.configure(extra=stack[-1])
        else:
            logger.configure(extra={"name": "DefaultLogger"})
            
    async def __aenter__(self):
        return self.__enter__()
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
        
    def _get_merged_context(self) -> Dict[str, Any]:
        """合并所有活动的上下文数据。"""
        stack = _context_stack.get()
        if not stack:
            return {}
        return stack[-1].copy()

def get_current_context() -> Dict[str, Any]:
    """
    获取当前活动的上下文数据。
    
    Returns:
        包含所有活动上下文数据的字典
    """
    stack = _context_stack.get()
    if not stack:
        return {}
    return stack[-1].copy()

def with_context(**context_kwargs):
    """
    用于函数级别的上下文管理的装饰器。
    
    Args:
        **context_kwargs: 要添加到上下文的键值对
        
    示例：
        @with_context(module='user_service')
        def process_user(user_id):
            logger.info(f'处理用户 {user_id}')
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                async with LogContext(**context_kwargs):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with LogContext(**context_kwargs):
                    return func(*args, **kwargs)
            return sync_wrapper
    return decorator

def track_performance(func: Callable[..., T]) -> Callable[..., T]:
    """
    用于跟踪函数执行性能的装饰器。
    
    Args:
        func: 要跟踪的函数
        
    示例：
        @track_performance
        def expensive_operation():
            time.sleep(1)
    """
    context_kwargs = {'track_performance': True}
    return with_context(**context_kwargs)(func)

async def bind_context(task: asyncio.Task, **context_kwargs):
    """
    将上下文绑定到异步任务。
    
    Args:
        task: 要绑定上下文的异步任务
        **context_kwargs: 要绑定的上下文数据
        
    示例：
        task = asyncio.create_task(some_coroutine())
        await bind_context(task, task_id='123')
    """
    current_context = get_current_context()
    current_context.update(context_kwargs)
    
    # 创建一个新的上下文管理器
    ctx = LogContext(**current_context)
    
    # 包装任务以使用上下文
    async def wrapped_task():
        async with ctx:
            return await task
            
    # 替换原始任务
    new_task = asyncio.create_task(wrapped_task())
    return new_task

class LogConfig:
    """
    Loguru日志配置类，提供统一的日志配置管理。
    """
    
    _instance = None
    _handler_ids = []  # 类变量，存储所有处理器ID
    
    def __new__(cls, config: Optional[Dict[str, Any]] = None):
        """
        实现单例模式，确保只有一个LogConfig实例。
        
        Args:
            config: 自定义配置字典，用于覆盖默认配置
            
        Returns:
            LogConfig实例
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化日志配置。
        
        Args:
            config: 自定义配置字典，用于覆盖默认配置
        """
        # 即使已初始化，也更新配置
        self.config = DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)
        
        # 移除现有的处理器
        logger.remove()
        LogConfig._handler_ids.clear()
        
        # 创建日志目录 - 使用项目根目录
        self.log_path = (PROJECT_ROOT / self.config["LOG_PATH"]).resolve()
        os.makedirs(self.log_path, exist_ok=True)
        
        # 配置日志处理器
        self._configure_handlers()
        self._initialized = True
    
    @classmethod
    def reset(cls):
        """
        重置LogConfig实例和所有处理器。
        用于测试环境中清理日志配置。
        """
        if cls._instance is not None:
            # 移除所有处理器
            for handler_id in cls._handler_ids:
                logger.remove(handler_id)
            cls._handler_ids.clear()
            
            # 重置实例
            cls._instance = None
    
    def _configure_handlers(self) -> None:
        """配置日志处理器，包括控制台和文件输出。"""
        # 添加控制台处理器
        handler_id = logger.add(
            sys.stderr,
            format=self.config["CONSOLE_LOG_FORMAT"],
            level=self.config["LOG_LEVEL"],
            colorize=True,
            backtrace=True,
            diagnose=True,
            catch=True
        )
        LogConfig._handler_ids.append(handler_id)
        
        # 添加主日志文件处理器
        log_file = self.log_path / "app.{time:YYYY-MM-DD}.log"
        if self.config.get("JSON_LOGS", False):
            handler_id = logger.add(
                str(log_file),
                serialize=True,  # 启用JSON序列化
                level=self.config["LOG_LEVEL"],
                rotation="00:00",  # 每天午夜轮转
                retention=self.config["LOG_RETENTION"],
                compression="zip",
                encoding="utf-8",
                backtrace=True,
                diagnose=True,
                catch=True
            )
        else:
            handler_id = logger.add(
                str(log_file),
                format=self.config["FILE_LOG_FORMAT"],
                level=self.config["LOG_LEVEL"],
                rotation="00:00",  # 每天午夜轮转
                retention=self.config["LOG_RETENTION"],
                compression="zip",
                encoding="utf-8",
                backtrace=True,
                diagnose=True,
                catch=True
            )
        LogConfig._handler_ids.append(handler_id)
        
        # 添加错误日志专用处理器
        error_log = self.log_path / "error.{time:YYYY-MM-DD}.log"
        handler_id = logger.add(
            str(error_log),
            format=self.config["FILE_LOG_FORMAT"],
            rotation="00:00",  # 每天午夜轮转
            retention=self.config["LOG_RETENTION"],
            level="ERROR",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
            catch=True,
            filter=lambda record: record["level"].name == "ERROR"
        )
        LogConfig._handler_ids.append(handler_id)
    
    @classmethod
    def set_log_level(cls, level: Union[str, int]) -> None:
        """
        动态设置日志级别。
        
        Args:
            level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）或对应的数字
        """
        # 如果是数字，转换为对应的级别名称
        if isinstance(level, int):
            level_map = {
                10: "DEBUG",
                20: "INFO",
                30: "WARNING",
                40: "ERROR",
                50: "CRITICAL"
            }
            level = level_map.get(level, "INFO")
        
        # 更新所有处理器的日志级别
        for handler_id in cls._handler_ids:
            logger.remove(handler_id)
        
        # 重新创建配置实例，使用新的日志级别
        config = cls._instance.config.copy()
        config["LOG_LEVEL"] = level
        cls._instance = None  # 重置单例
        LogConfig(config)  # 创建新实例
    
    @staticmethod
    def add_context(**kwargs) -> None:
        """
        添加上下文信息到日志记录。
        
        Args:
            **kwargs: 键值对形式的上下文信息
        """
        logger.configure(extra=kwargs)

# 创建默认日志配置实例
default_config = LogConfig()

# 导出logger实例供其他模块使用
log = logger.bind(context="global")

def get_logger(name: str = "DefaultLogger", **kwargs) -> Logger:
    """
    获取带有上下文的logger实例。
    
    Args:
        name: 日志记录器名称
        **kwargs: 额外的上下文信息
        
    Returns:
        配置好的logger实例
    """
    context = {"name": name}
    context.update(kwargs)
    return logger.bind(**context)

# 设置常用的日志装饰器
def log_function_call(func):
    """
    记录函数调用的装饰器。
    
    Args:
        func: 被装饰的函数
        
    Returns:
        装饰后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger_instance = get_logger(name=func.__name__)
        logger_instance.debug(f"调用函数 {func.__name__} - 参数: {args}, 关键字参数: {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger_instance.debug(f"函数 {func.__name__} 执行成功")
            return result
        except Exception as e:
            logger_instance.exception(f"函数 {func.__name__} 执行失败")
            raise
    return wrapper 