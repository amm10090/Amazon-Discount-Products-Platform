"""
测试API日志记录模块的功能。
"""

import pytest
import json
import asyncio
import os
from datetime import datetime
from src.utils.api_logger import APILogger, with_api_logging
from loguru import logger

@pytest.fixture
def api_logger():
    """创建API日志记录器实例。"""
    return APILogger("test_api")

@pytest.fixture(autouse=True)
def setup_logger():
    """设置测试用的日志记录器。"""
    # 保存原始处理器
    original_handlers = logger._core.handlers.copy()
    
    # 清除所有处理器
    logger.remove()
    
    # 添加测试处理器
    logger.add(
        "test_logs.log",
        format="{message}",
        level="DEBUG"
    )
    
    yield
    
    # 恢复原始处理器
    logger._core.handlers = original_handlers

def test_mask_sensitive_data(api_logger):
    """测试敏感数据遮蔽功能。"""
    test_data = {
        "access_key": "secret123",
        "name": "test",
        "config": {
            "api_key": "key123",
            "url": "http://api.example.com"
        },
        "items": [
            {"token": "token123", "id": 1},
            {"password": "pass123", "id": 2}
        ]
    }
    
    masked_data = api_logger._mask_sensitive_data(test_data)
    
    # 验证顶层敏感字段被遮蔽
    assert masked_data["access_key"] == "******"
    assert masked_data["name"] == "test"  # 非敏感字段保持不变
    
    # 验证嵌套字典中的敏感字段被遮蔽
    assert masked_data["config"]["api_key"] == "******"
    assert masked_data["config"]["url"] == "http://api.example.com"
    
    # 验证列表中字典的敏感字段被遮蔽
    assert masked_data["items"][0]["token"] == "******"
    assert masked_data["items"][0]["id"] == 1
    assert masked_data["items"][1]["password"] == "******"
    assert masked_data["items"][1]["id"] == 2

def test_truncate_response(api_logger):
    """测试响应数据截断功能。"""
    # 测试字符串截断
    long_string = "a" * 2000
    truncated = api_logger._truncate_response(long_string)
    assert len(truncated) < len(long_string)
    assert "截断" in truncated
    assert str(len(long_string)) in truncated
    
    # 测试列表截断
    long_list = list(range(20))
    truncated = api_logger._truncate_response(long_list)
    assert len(truncated) == 4  # [first, "...", count_message, last]
    assert truncated[0] == 0
    assert truncated[1] == "..."
    assert "还有" in truncated[2]
    assert truncated[3] == 19
    
    # 测试嵌套数据结构
    nested_data = {
        "string": "a" * 2000,
        "list": list(range(20)),
        "dict": {"key": "a" * 2000}
    }
    truncated = api_logger._truncate_response(nested_data)
    assert len(truncated["string"]) < 2000
    assert len(truncated["list"]) == 4
    assert len(truncated["dict"]["key"]) < 2000

def test_log_request(api_logger, tmp_path):
    """测试请求日志记录功能。"""
    log_file = tmp_path / "test_logs.log"
    
    # 添加临时日志处理器
    logger.remove()
    logger.add(
        str(log_file),
        format="{message}",
        level="DEBUG"
    )
    
    test_request = {
        "method": "POST",
        "url": "http://api.example.com/test",
        "headers": {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json"
        },
        "params": {"id": 123},
        "data": {"name": "test", "api_key": "secret123"}
    }
    
    api_logger.log_request(**test_request)
    
    # 读取日志文件内容
    log_content = log_file.read_text()
    
    # 验证日志内容
    assert "API请求" in log_content
    assert "http://api.example.com/test" in log_content
    assert "token123" not in log_content  # 敏感数据应被遮蔽
    assert "secret123" not in log_content  # 敏感数据应被遮蔽

def test_log_response(api_logger, tmp_path):
    """测试响应日志记录功能。"""
    log_file = tmp_path / "test_logs.log"
    
    # 添加临时日志处理器
    logger.remove()
    logger.add(
        str(log_file),
        format="{message}",
        level="DEBUG"
    )
    
    api_logger.log_response(
        status_code=200,
        response_data={"result": "success", "data": "a" * 2000},
        elapsed=1.234
    )
    
    # 读取日志文件内容
    log_content = log_file.read_text()
    
    # 验证日志内容
    assert "API响应" in log_content
    assert "200" in log_content
    assert "1.234" in log_content
    assert "截断" in log_content

def test_log_error(api_logger, tmp_path):
    """测试错误日志记录功能。"""
    log_file = tmp_path / "test_logs.log"
    
    # 添加临时日志处理器
    logger.remove()
    logger.add(
        str(log_file),
        format="{message}",
        level="DEBUG"
    )
    
    try:
        raise ValueError("测试错误")
    except Exception as e:
        api_logger.log_error(
            error=e,
            context={"task": "test_task"}
        )
    
    # 读取日志文件内容
    log_content = log_file.read_text()
    
    # 验证日志内容
    assert "API错误" in log_content
    assert "ValueError" in log_content
    assert "测试错误" in log_content
    assert "test_task" in log_content

def create_logger_for_test(tmp_path, logger_name="test_logger"):
    """创建测试用的日志记录器。"""
    log_file = tmp_path / f"{logger_name}.log"
    if os.path.exists(log_file):
        os.remove(log_file)
        
    # 创建新的处理器
    logger.remove()
    handler_id = logger.add(
        str(log_file),
        format="{message}",
        level="DEBUG"
    )
    
    return log_file, handler_id

@pytest.mark.asyncio
async def test_async_api_logging_decorator(tmp_path):
    """测试异步API日志记录装饰器。"""
    log_file, handler_id = create_logger_for_test(tmp_path, "async_test")
    
    try:
        # 自定义测试函数，明确提供method和url参数
        @with_api_logging("test_async_api")
        async def test_async_function(success: bool = True):
            if not success:
                raise ValueError("测试错误")
            return {"status": "success"}
        
        # 测试成功情况
        response = await test_async_function()
        assert response["status"] == "success"
        
        # 读取日志文件内容
        log_content = log_file.read_text()
        
        # 验证日志内容
        assert "API请求" in log_content
        assert "API响应" in log_content
        assert "success" in log_content
        
        # 清空日志文件
        with open(log_file, 'w') as f:
            f.write("")
        
        # 测试失败情况
        with pytest.raises(ValueError):
            await test_async_function(success=False)
        
        # 读取日志文件内容
        log_content = log_file.read_text()
        
        # 验证日志内容
        assert "API请求" in log_content
        assert "API错误" in log_content
        assert "测试错误" in log_content
    finally:
        # 清理
        logger.remove(handler_id)

def test_sync_api_logging_decorator(tmp_path):
    """测试同步API日志记录装饰器。"""
    log_file, handler_id = create_logger_for_test(tmp_path, "sync_test")
    
    try:
        # 自定义测试函数，明确提供method和url参数
        @with_api_logging("test_sync_api")
        def test_sync_function(success: bool = True):
            if not success:
                raise ValueError("测试错误")
            return {"status": "success"}
        
        # 测试成功情况
        response = test_sync_function()
        assert response["status"] == "success"
        
        # 读取日志文件内容
        log_content = log_file.read_text()
        
        # 验证日志内容
        assert "API请求" in log_content
        assert "API响应" in log_content
        assert "success" in log_content
        
        # 清空日志文件
        with open(log_file, 'w') as f:
            f.write("")
        
        # 测试失败情况
        with pytest.raises(ValueError):
            test_sync_function(success=False)
        
        # 读取日志文件内容
        log_content = log_file.read_text()
        
        # 验证日志内容
        assert "API请求" in log_content
        assert "API错误" in log_content
        assert "测试错误" in log_content
    finally:
        # 清理
        logger.remove(handler_id) 