"""
日志兼容层模块

此模块创建了一个兼容层，允许使用标准logging库接口的代码无缝迁移到Loguru。
提供了与标准logging库API兼容的接口，但在底层使用Loguru进行实际的日志记录。
"""

import sys
import logging
from typing import Optional, Dict, Any, Union, Callable

from loguru import logger
from .log_config import get_logger, LogConfig

# 拦截标准库的日志记录
class InterceptHandler(logging.Handler):
    """
    拦截标准库logging的处理器，将日志转发到Loguru
    
    用于捕获第三方库通过logging模块发出的日志，并将其重定向到Loguru
    """
    
    def emit(self, record):
        # 获取对应的Loguru级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        # 使用Loguru记录日志
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

class LoggingCompatLayer:
    """
    标准logging库的兼容层，将调用转发到Loguru
    
    提供与标准logging库兼容的接口，但底层使用Loguru进行实际日志记录
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialize()
            self._initialized = True
    
    def _initialize(self):
        """初始化兼容层，设置日志级别映射和默认记录器"""
        # 级别映射
        self.level_mapping = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO", 
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
            # 自定义级别支持
            logging.INFO + 1: "SUCCESS",
            logging.INFO + 2: "PROGRESS",
            logging.INFO + 3: "SECTION"
        }
        
        # 获取默认记录器
        self.default_logger = get_logger("compat")
        
        # 记录器缓存
        self._loggers = {}
    
    def setup(self):
        """
        设置日志兼容层，拦截标准库日志
        
        - 移除标准库已有的处理器
        - 添加拦截处理器，将日志转发到Loguru
        - 设置标准库日志级别为NOTSET，确保所有消息都转发
        """
        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.handlers = [InterceptHandler()]
        root_logger.setLevel(logging.NOTSET)
        
        # 禁用标准库的内置处理
        logging.basicConfig(handlers=[InterceptHandler()], level=logging.NOTSET)
        
        # 拦截常见的库日志
        for name in logging.root.manager.loggerDict.keys():
            logging.getLogger(name).handlers = [InterceptHandler()]
            logging.getLogger(name).propagate = False
    
    def get_logger(self, name: Optional[str] = None) -> 'CompatLogger':
        """
        获取兼容的日志记录器实例
        
        Args:
            name: 记录器名称，可选
            
        Returns:
            兼容日志记录器实例
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger_instance = CompatLogger(name)
        self._loggers[name] = logger_instance
        return logger_instance

class CompatLogger:
    """
    兼容的日志记录器类，提供与标准logging.Logger相同的接口
    """
    
    def __init__(self, name: Optional[str] = None):
        """
        初始化兼容日志记录器
        
        Args:
            name: 记录器名称
        """
        self.name = name
        self._loguru_logger = get_logger(name) if name else logger
        
        # 添加自定义日志级别
        if not hasattr(logging, 'SUCCESS'):
            logging.addLevelName(logging.INFO + 1, 'SUCCESS')
        if not hasattr(logging, 'PROGRESS'):
            logging.addLevelName(logging.INFO + 2, 'PROGRESS')
        if not hasattr(logging, 'SECTION'):
            logging.addLevelName(logging.INFO + 3, 'SECTION')
    
    def _get_loguru_level(self, level: Union[int, str]) -> str:
        """转换日志级别到Loguru格式"""
        compat = LoggingCompatLayer()
        
        if isinstance(level, int):
            return compat.level_mapping.get(level, "INFO")
        return level
    
    def setLevel(self, level: Union[int, str]) -> None:
        """设置日志级别"""
        # Loguru不支持每个记录器单独设置级别
        # 这里我们忽略这个调用
        pass
    
    def debug(self, msg: str, *args, **kwargs) -> None:
        """记录DEBUG级别日志"""
        self._loguru_logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs) -> None:
        """记录INFO级别日志"""
        self._loguru_logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs) -> None:
        """记录WARNING级别日志"""
        self._loguru_logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs) -> None:
        """记录ERROR级别日志"""
        self._loguru_logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs) -> None:
        """记录CRITICAL级别日志"""
        self._loguru_logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs) -> None:
        """记录异常信息"""
        self._loguru_logger.exception(msg, *args, **kwargs)
    
    def log(self, level: Union[int, str], msg: str, *args, **kwargs) -> None:
        """
        用指定级别记录日志
        
        Args:
            level: 日志级别
            msg: 日志消息
            *args: 位置参数
            **kwargs: 关键字参数
        """
        loguru_level = self._get_loguru_level(level)
        self._loguru_logger.log(loguru_level, msg, *args, **kwargs)
    
    def addHandler(self, handler: logging.Handler) -> None:
        """添加处理器（兼容性方法，不执行实际操作）"""
        pass
    
    def removeHandler(self, handler: logging.Handler) -> None:
        """移除处理器（兼容性方法，不执行实际操作）"""
        pass

# 添加对老版本LoggerManager的兼容支持
class LegacyLoggerManager:
    """
    兼容旧版LoggerManager的接口，但底层使用Loguru
    
    用于支持之前的logger.success()等自定义方法
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.logger = get_logger("legacy")
            self._initialized = True
    
    def setup(self,
             log_level: str = 'INFO',
             log_file: Optional[str] = None,
             use_colors: bool = True,
             max_file_size: int = 10 * 1024 * 1024,
             backup_count: int = 5):
        """设置日志配置（兼容旧接口，但使用LogConfig）"""
        config = {
            "LOG_LEVEL": log_level,
            "JSON_LOGS": False,
            "LOG_PATH": "logs",
            "MAX_LOG_SIZE": f"{max_file_size // (1024*1024)} MB",
            "LOG_RETENTION": f"{backup_count * 30} days"
        }
        
        if log_file:
            config["LOG_FILE"] = log_file
        
        LogConfig(config)
    
    def debug(self, message: str):
        """输出调试信息"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """输出普通信息"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """输出警告信息"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """输出错误信息"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """输出严重错误信息"""
        self.logger.critical(message)
    
    def success(self, message: str):
        """输出成功信息"""
        self.logger.success(message)
    
    def progress(self, message: str):
        """输出进度信息"""
        self.logger.info(f"→ {message}")
    
    def section(self, message: str):
        """输出分节信息"""
        separator = "=" * 50
        self.logger.info(f"\n{separator}\n{message}\n{separator}\n")

# 创建单例实例
compat_layer = LoggingCompatLayer()
legacy_logger = LegacyLoggerManager()

# 暴露兼容函数作为替代
def getLogger(name: Optional[str] = None) -> CompatLogger:
    """获取兼容的日志记录器"""
    return compat_layer.get_logger(name)

# 替换标准logging的getLogger函数
logging.getLogger = getLogger

# 暴露旧版接口函数
log_debug = legacy_logger.debug
log_info = legacy_logger.info
log_warning = legacy_logger.warning
log_error = legacy_logger.error
log_critical = legacy_logger.critical
log_success = legacy_logger.success
log_progress = legacy_logger.progress
log_section = legacy_logger.section

def set_log_config(**kwargs):
    """设置日志配置的便捷函数"""
    legacy_logger.setup(**kwargs)

def setup_logging_compat():
    """设置日志兼容层"""
    compat_layer.setup() 