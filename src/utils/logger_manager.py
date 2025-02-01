import colorama
from colorama import Fore, Back, Style
import os
import sys
from typing import Optional, Dict, List, Union
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import json
from pathlib import Path
import atexit
from queue import Queue
from threading import Lock, Thread
import time

from .config_loader import config_loader

# 初始化colorama
colorama.init()

# 日志级别常量
LOG_LEVEL_ERROR = 0
LOG_LEVEL_WARNING = 1
LOG_LEVEL_INFO = 2
LOG_LEVEL_DEBUG = 3

# 日志级别映射
LOG_LEVEL_MAP = {
    'ERROR': LOG_LEVEL_ERROR,
    'WARNING': LOG_LEVEL_WARNING,
    'INFO': LOG_LEVEL_INFO,
    'DEBUG': LOG_LEVEL_DEBUG
}

# 日志颜色配置
LOG_COLORS = {
    'ERROR': Fore.RED,
    'WARNING': Fore.YELLOW,
    'INFO': Fore.GREEN,
    'DEBUG': Fore.BLUE,
    'SUCCESS': Fore.GREEN
}

class LogConfig:
    """日志配置类"""
    def __init__(self):
        try:
            # 加载配置
            config_loader.load_config()
            log_config = config_loader.get_logging_config()
            
            if not isinstance(log_config, dict):
                log_config = {}
            
            # 基础配置
            file_config = log_config.get('file', {})
            if not isinstance(file_config, dict):
                file_config = {}
                
            console_config = log_config.get('console', {})
            if not isinstance(console_config, dict):
                console_config = {}
                
            buffer_config = log_config.get('buffer', {})
            if not isinstance(buffer_config, dict):
                buffer_config = {}
            
            # 文件配置
            self.log_dir = Path(str(file_config.get('path', 'logs')))
            self.max_file_size = int(file_config.get('max_size', 10 * 1024 * 1024))
            self.backup_count = int(file_config.get('backup_count', 5))
            self.file_log_format = str(file_config.get('format', "[%(asctime)s] %(name)s - %(levelname)s: %(message)s"))
            self.log_filename = str(file_config.get('filename', 'service.log'))
            
            # 控制台配置
            self.console_log_format = str(console_config.get('format', "%(message)s"))
            self.date_format = str(file_config.get('date_format', "%Y-%m-%d %H:%M:%S"))
            
            # 缓冲配置
            self.buffer_size = int(buffer_config.get('size', 1000))
            self.flush_interval = int(buffer_config.get('flush_interval', 5))
            
            # 输出配置
            self.use_colors = bool(log_config.get('use_colors', True))
            self.log_to_file = bool(file_config.get('enabled', True))
            self.log_to_console = bool(console_config.get('enabled', True))
            
            # 创建日志目录
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
        except Exception as e:
            # 如果出现任何错误，使用默认配置
            self.log_dir = Path('logs')
            self.max_file_size = 10 * 1024 * 1024  # 10MB
            self.backup_count = 5
            self.file_log_format = "[%(asctime)s] %(name)s - %(levelname)s: %(message)s"
            self.log_filename = 'service.log'
            self.console_log_format = "%(message)s"
            self.date_format = "%Y-%m-%d %H:%M:%S"
            self.buffer_size = 1000
            self.flush_interval = 5
            self.use_colors = True
            self.log_to_file = True
            self.log_to_console = True
            self.log_dir.mkdir(parents=True, exist_ok=True)
            print(f"警告: 使用默认日志配置，原因: {str(e)}")

class LogBuffer:
    """日志缓冲区类"""
    def __init__(self, config: LogConfig):
        self.buffer: List[str] = []
        self.lock = Lock()
        self.config = config
        self.file_handler = None
        self.setup_file_handler()
        
        # 启动异步写入线程
        self.running = True
        self.flush_thread = Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
        
        # 注册程序退出时的清理函数
        atexit.register(self.cleanup)
    
    def setup_file_handler(self):
        """设置文件处理器"""
        if not self.config.log_to_file:
            return
            
        log_file = self.config.log_dir / self.config.log_filename
        self.file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.config.max_file_size,
            backupCount=self.config.backup_count,
            encoding='utf-8'
        )
        formatter = logging.Formatter(
            self.config.file_log_format,
            datefmt=self.config.date_format
        )
        self.file_handler.setFormatter(formatter)
    
    def add(self, message: str):
        """添加日志到缓冲区"""
        with self.lock:
            self.buffer.append(message)
            if len(self.buffer) >= self.config.buffer_size:
                self.flush()
    
    def flush(self):
        """将缓冲区的日志写入文件"""
        if not self.config.log_to_file or not self.file_handler:
            return
            
        with self.lock:
            if not self.buffer:
                return
            for message in self.buffer:
                self.file_handler.emit(
                    logging.LogRecord(
                        name="",
                        level=logging.INFO,
                        pathname="",
                        lineno=0,
                        msg=message,
                        args=(),
                        exc_info=None
                    )
                )
            self.buffer.clear()
    
    def _flush_loop(self):
        """定期刷新缓冲区"""
        while self.running:
            time.sleep(self.config.flush_interval)
            self.flush()
    
    def cleanup(self):
        """清理资源"""
        self.running = False
        self.flush()
        if self.file_handler:
            self.file_handler.close()

# 创建全局配置和缓冲区实例
config = LogConfig()
buffer = LogBuffer(config)

# 从环境变量获取日志级别，默认为 INFO
def get_log_level():
    level = os.getenv('DEBUG_LEVEL', 'INFO').upper()
    return LOG_LEVEL_MAP.get(level, LOG_LEVEL_INFO)

DEBUG_LEVEL = get_log_level()

def format_log_message(level: str, message: str, timestamp: bool = True) -> str:
    """格式化日志消息"""
    time_prefix = f"[{datetime.now().strftime('%H:%M:%S')}] " if timestamp else ""
    if config.use_colors:
        color = LOG_COLORS.get(level, '')
        return f"{time_prefix}{color}[{level}]{Style.RESET_ALL} {message}"
    return f"{time_prefix}[{level}] {message}"

def should_log(level: int) -> bool:
    """检查是否应该输出指定级别的日志"""
    return DEBUG_LEVEL >= level

def log_message(level: str, message: str, timestamp: bool = True):
    """通用日志输出函数"""
    formatted_message = format_log_message(level, message, timestamp)
    print(formatted_message, flush=True)
    if config.log_to_file:
        buffer.add(formatted_message)

def log_info(message: str, timestamp: bool = True) -> None:
    """输出信息日志"""
    if should_log(LOG_LEVEL_INFO):
        log_message('INFO', message, timestamp)

def log_debug(message: str, timestamp: bool = True) -> None:
    """输出调试日志"""
    if should_log(LOG_LEVEL_DEBUG):
        log_message('DEBUG', message, timestamp)

def log_warning(message: str, timestamp: bool = True) -> None:
    """输出警告日志"""
    if should_log(LOG_LEVEL_WARNING):
        log_message('WARNING', message, timestamp)

def log_error(message: str, timestamp: bool = True) -> None:
    """输出错误日志"""
    if should_log(LOG_LEVEL_ERROR):
        log_message('ERROR', message, timestamp)

def log_success(message: str, timestamp: bool = True) -> None:
    """输出成功日志"""
    if should_log(LOG_LEVEL_INFO):
        log_message('SUCCESS', message, timestamp)

def log_progress(current: int, total: int, prefix: str = '', show_percentage: bool = True) -> None:
    """
    输出进度信息
    
    Args:
        current: 当前进度
        total: 总数
        prefix: 进度条前缀
        show_percentage: 是否显示百分比
    """
    if should_log(LOG_LEVEL_INFO):
        percentage = (current / total) * 100 if show_percentage else 0
        bar_length = 30
        filled_length = int(bar_length * current / total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        message = f"\r{prefix}进度: [{bar}] {current}/{total}"
        if show_percentage:
            message += f" ({percentage:.1f}%)"
        
        print(message, end='', flush=True)
        if current == total:
            print()  # 完成时换行

def log_section(title: str, char: str = '=', length: int = 50) -> None:
    """
    输出分节标题
    
    Args:
        title: 标题文本
        char: 分隔符字符
        length: 分隔线长度
    """
    if should_log(LOG_LEVEL_INFO):
        separator = char * length
        message = f"\n{separator}\n{title}\n{separator}\n"
        print(message, flush=True)
        if config.log_to_file:
            buffer.add(message)

def set_log_config(
    log_to_file: bool = True,
    use_colors: bool = True,
    log_dir: str = "logs",
    max_file_size: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    buffer_size: int = 1000,
    flush_interval: int = 5
) -> None:
    """
    配置日志系统
    
    Args:
        log_to_file: 是否记录到文件
        use_colors: 是否使用彩色输出
        log_dir: 日志文件目录
        max_file_size: 单个日志文件最大大小（字节）
        backup_count: 保留的日志文件数量
        buffer_size: 缓冲区大小
        flush_interval: 刷新间隔（秒）
    """
    global config, buffer
    
    # 更新配置
    config.log_to_file = log_to_file
    config.use_colors = use_colors
    config.log_dir = Path(log_dir)
    config.max_file_size = max_file_size
    config.backup_count = backup_count
    config.buffer_size = buffer_size
    config.flush_interval = flush_interval
    
    # 重新创建缓冲区
    if buffer:
        buffer.cleanup()
    buffer = LogBuffer(config)

# 初始化默认配置
set_log_config() 