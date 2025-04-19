"""
日志管理模块

提供统一的日志管理功能，包括：
1. 控制台彩色输出
2. 文件日志记录
3. 日志级别控制
4. 日志格式化
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional
import colorama
from colorama import Fore, Style

# 初始化colorama
colorama.init()

# 日志级别映射
LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# 颜色映射
COLOR_MAP = {
    'DEBUG': Fore.CYAN,
    'INFO': Fore.GREEN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.RED + Style.BRIGHT,
    'SUCCESS': Fore.GREEN + Style.BRIGHT,
    'PROGRESS': Fore.BLUE + Style.BRIGHT,
    'SECTION': Fore.MAGENTA + Style.BRIGHT
}

class ColoredFormatter(logging.Formatter):
    """自定义的彩色日志格式化器"""
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record):
        # 创建一个干净的时间戳
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # 获取日志级别的颜色
        level_color = COLOR_MAP.get(record.levelname, '') if self.use_colors else ''
        reset_color = Style.RESET_ALL if self.use_colors else ''
        
        # 根据日志级别使用不同的格式
        if record.levelname in ['ERROR', 'CRITICAL']:
            # 错误信息使用更突出的格式
            format_str = f"[{timestamp}] {level_color}[{record.levelname}]{reset_color} {record.message}"
        elif record.levelname == 'SUCCESS':
            # 成功信息使用简洁的格式
            format_str = f"[{timestamp}] {level_color}✓ {record.message}{reset_color}"
        elif record.levelname == 'PROGRESS':
            # 进度信息使用特殊格式
            format_str = f"[{timestamp}] {level_color}→ {record.message}{reset_color}"
        elif record.levelname == 'SECTION':
            # 分节信息使用分隔线
            format_str = f"\n{level_color}{'='*50}\n{record.message}\n{'='*50}{reset_color}\n"
        else:
            # 普通信息使用标准格式
            format_str = f"[{timestamp}] {record.message}"
            
        # 如果是调试信息，添加文件和行号
        if record.levelname == 'DEBUG':
            format_str = f"[{timestamp}] {level_color}[DEBUG]{reset_color} [{record.filename}:{record.lineno}] {record.message}"
            
        return format_str

class LoggerManager:
    """日志管理器"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger('amazon_collector')
            self.logger.setLevel(logging.INFO)
            self._initialized = True
            
    def setup(self,
             log_level: str = 'INFO',
             log_file: Optional[str] = None,
             use_colors: bool = True,
             file_use_colors: bool = False,  # 新增参数，默认文件不使用颜色
             max_file_size: int = 10 * 1024 * 1024,  # 10MB
             backup_count: int = 5):
        """
        设置日志配置
        
        Args:
            log_level: 日志级别
            log_file: 日志文件路径
            use_colors: 控制台是否使用彩色输出
            file_use_colors: 文件日志是否使用彩色输出，默认为False
            max_file_size: 单个日志文件最大大小
            backup_count: 保留的日志文件数量
        """
        # 清除现有的处理器
        self.logger.handlers.clear()
        
        # 设置日志级别
        self.logger.setLevel(LEVEL_MAP.get(log_level.upper(), logging.INFO))
        
        # 添加控制台处理器（使用颜色）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter(use_colors=use_colors))
        self.logger.addHandler(console_handler)
        
        # 如果指定了日志文件，添加文件处理器（禁用颜色）
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
            # 为文件处理器使用无颜色的格式化器
            if file_use_colors:
                # 如果明确要求文件使用颜色，则使用带颜色的格式化器
                file_handler.setFormatter(ColoredFormatter(use_colors=file_use_colors))
            else:
                # 默认文件使用无颜色的简单格式
                file_format = '[%(asctime)s] [%(levelname)s] %(message)s'
                file_handler.setFormatter(logging.Formatter(
                    file_format,
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
            self.logger.addHandler(file_handler)
    
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
        self.logger.log(logging.INFO + 1, message)
    
    def progress(self, message: str):
        """输出进度信息"""
        self.logger.log(logging.INFO + 2, message)
    
    def section(self, message: str):
        """输出分节信息"""
        self.logger.log(logging.INFO + 3, message)

# 创建全局日志管理器实例
logger = LoggerManager()

# 添加自定义日志级别
logging.addLevelName(logging.INFO + 1, 'SUCCESS')
logging.addLevelName(logging.INFO + 2, 'PROGRESS')
logging.addLevelName(logging.INFO + 3, 'SECTION')

# 导出便捷函数
log_debug = logger.debug
log_info = logger.info
log_warning = logger.warning
log_error = logger.error
log_critical = logger.critical
log_success = logger.success
log_progress = logger.progress
log_section = logger.section

def set_log_config(**kwargs):
    """设置日志配置的便捷函数"""
    logger.setup(**kwargs) 