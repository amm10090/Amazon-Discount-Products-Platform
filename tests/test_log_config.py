"""
测试日志配置模块的功能。
"""

import os
import shutil
import asyncio
import time
from pathlib import Path
import pytest
from src.utils.log_config import (
    LogConfig, get_logger, log_function_call,
    LogContext, with_context, track_performance,
    get_current_context, bind_context
)

@pytest.fixture(scope="function")
def temp_log_dir(tmp_path):
    """创建临时日志目录。"""
    # 确保每次测试前重置LogConfig
    LogConfig.reset()
    
    log_dir = tmp_path / "test_logs"
    yield log_dir
    # 清理测试日志文件
    if log_dir.exists():
        shutil.rmtree(log_dir)

def test_log_config_initialization(temp_log_dir):
    """测试日志配置初始化。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    
    # 验证日志目录创建
    assert temp_log_dir.exists()
    assert temp_log_dir.is_dir()

@log_function_call
def sample_function(x, y):
    """用于测试的示例函数。"""
    return x + y

def test_log_function_decorator(temp_log_dir, capsys):
    """测试函数调用日志装饰器。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    
    # 调用被装饰的函数
    result = sample_function(1, 2)
    assert result == 3
    
    # 检查控制台输出中是否包含函数调用日志
    captured = capsys.readouterr()
    assert "调用函数 sample_function" in captured.err
    assert "函数 sample_function 执行成功" in captured.err

def test_logger_with_context(temp_log_dir, capsys):
    """测试带上下文的日志记录。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    
    # 创建带上下文的logger
    logger = get_logger("test_module", task_id="123")
    logger.info("测试消息")
    
    # 检查日志输出
    captured = capsys.readouterr()
    assert "test_module" in captured.err
    
def test_error_logging(temp_log_dir):
    """测试错误日志记录。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    logger = get_logger("error_test")
    
    # 记录一个错误
    try:
        raise ValueError("测试错误")
    except Exception as e:
        logger.error("发生错误: {}", str(e))
    
    # 验证错误日志文件存在
    error_logs = list(temp_log_dir.glob("error_*.log"))
    assert len(error_logs) > 0

def test_log_level_change(temp_log_dir, capsys):
    """测试动态修改日志级别。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "INFO"
    }
    log_config = LogConfig(config)
    logger = get_logger("level_test")
    
    # 记录DEBUG级别的消息（不应该显示）
    logger.debug("DEBUG消息")
    captured = capsys.readouterr()
    assert "DEBUG消息" not in captured.err
    
    # 修改日志级别到DEBUG
    LogConfig.set_log_level("DEBUG")
    
    # 再次记录DEBUG级别的消息（应该显示）
    logger.debug("DEBUG消息")
    captured = capsys.readouterr()
    assert "DEBUG消息" in captured.err

def test_json_logging(temp_log_dir):
    """测试JSON格式日志输出。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG",
        "JSON_LOGS": True
    }
    log_config = LogConfig(config)
    logger = get_logger("json_test")
    
    # 记录一条消息
    logger.info("JSON测试消息")
    
    # 验证日志文件存在并包含JSON格式的内容
    log_files = list(temp_log_dir.glob("app_*.log"))
    assert len(log_files) > 0
    with open(log_files[0], 'r', encoding='utf-8') as f:
        content = f.read()
        assert '"message": "JSON测试消息"' in content.replace("'", '"')

def test_log_context_manager(temp_log_dir, capsys):
    """测试日志上下文管理器。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    logger = get_logger()
    
    with LogContext(task_id="123", module="test"):
        logger.info("测试消息")
        
        # 嵌套上下文
        with LogContext(sub_task="subtask"):
            logger.info("子任务消息")
            
            # 验证当前上下文
            context = get_current_context()
            assert context["task_id"] == "123"
            assert context["module"] == "test"
            assert context["sub_task"] == "subtask"
    
    # 验证上下文已清理
    assert not get_current_context()
    
    # 检查日志输出
    captured = capsys.readouterr()
    assert "task_id" in captured.err
    assert "module" in captured.err
    assert "sub_task" in captured.err

def test_performance_tracking(temp_log_dir, capsys):
    """测试性能跟踪功能。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    
    @track_performance
    def slow_function():
        time.sleep(0.1)
        return True
    
    result = slow_function()
    assert result is True
    
    # 检查性能日志
    captured = capsys.readouterr()
    assert "性能统计" in captured.err
    assert "执行时间" in captured.err

@pytest.mark.asyncio
async def test_async_context(temp_log_dir, capsys):
    """测试异步上下文管理。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    logger = get_logger()
    
    async def async_task():
        await asyncio.sleep(0.1)
        logger.info("异步任务执行")
        return True
    
    async with LogContext(task_type="async", task_id="456"):
        task = asyncio.create_task(async_task())
        task = await bind_context(task, sub_task_id="789")
        result = await task
        assert result is True
    
    # 检查日志输出
    captured = capsys.readouterr()
    assert "task_type" in captured.err
    assert "task_id" in captured.err
    assert "sub_task_id" in captured.err

def test_context_decorator(temp_log_dir, capsys):
    """测试上下文装饰器。"""
    config = {
        "LOG_PATH": str(temp_log_dir),
        "LOG_LEVEL": "DEBUG"
    }
    log_config = LogConfig(config)
    logger = get_logger()
    
    @with_context(module="test_module")
    def decorated_function():
        logger.info("装饰器测试")
        context = get_current_context()
        assert context["module"] == "test_module"
    
    decorated_function()
    
    # 检查日志输出
    captured = capsys.readouterr()
    assert "module" in captured.err
    assert "test_module" in captured.err 