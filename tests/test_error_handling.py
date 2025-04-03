"""
测试错误处理模块的功能。
"""

import sys
import pytest
import asyncio
from datetime import datetime, UTC
from src.utils.error_handling import (
    ErrorCode,
    ErrorLevel,
    CustomException,
    ErrorHandler,
    ErrorMetrics,
    error_handler,
    global_error_handler,
    setup_error_handling
)

def test_custom_exception():
    """测试自定义异常类。"""
    # 创建一个自定义异常
    exc = CustomException(
        error_code=ErrorCode.API_ERROR,
        message="API调用失败",
        details={"url": "http://api.example.com"},
        level=ErrorLevel.ERROR
    )
    
    # 验证异常属性
    assert exc.error_code == ErrorCode.API_ERROR
    assert exc.message == "API调用失败"
    assert exc.details == {"url": "http://api.example.com"}
    assert exc.level == ErrorLevel.ERROR
    assert isinstance(exc.timestamp, datetime)
    
    # 验证字典转换
    error_dict = exc.to_dict()
    assert error_dict["error_code"] == ErrorCode.API_ERROR.value
    assert error_dict["error_name"] == "API_ERROR"
    assert error_dict["message"] == "API调用失败"
    assert error_dict["details"] == {"url": "http://api.example.com"}
    assert error_dict["level"] == "ERROR"
    assert "timestamp" in error_dict
    assert "traceback" in error_dict

def test_error_handler():
    """测试错误处理器。"""
    handler = ErrorHandler()
    
    # 测试错误过滤器
    def filter_debug_errors(exc):
        return (
            isinstance(exc, CustomException) and
            exc.level == ErrorLevel.DEBUG
        )
    
    handler.add_filter(filter_debug_errors)
    
    # 创建一个DEBUG级别的错误（应该被过滤）
    debug_exc = CustomException(
        error_code=ErrorCode.SYSTEM_ERROR,
        message="调试信息",
        level=ErrorLevel.DEBUG
    )
    
    # 处理DEBUG错误（应该被过滤，不会抛出异常）
    handler.handle(debug_exc)
    
    # 测试自定义错误处理器
    handled_exceptions = []
    
    def custom_handler(exc):
        handled_exceptions.append(exc)
    
    handler.add_handler(CustomException, custom_handler)
    
    # 创建一个ERROR级别的错误（不应该被过滤）
    error_exc = CustomException(
        error_code=ErrorCode.API_ERROR,
        message="API错误",
        level=ErrorLevel.ERROR
    )
    
    # 处理ERROR错误
    handler.handle(error_exc)
    
    # 验证错误被正确处理
    assert len(handled_exceptions) == 1
    assert handled_exceptions[0] == error_exc

def test_error_metrics():
    """测试错误统计指标。"""
    metrics = ErrorMetrics()
    
    # 记录一些错误
    exc1 = CustomException(
        error_code=ErrorCode.API_ERROR,
        message="API错误1"
    )
    exc2 = CustomException(
        error_code=ErrorCode.API_ERROR,
        message="API错误2"
    )
    exc3 = CustomException(
        error_code=ErrorCode.DATABASE_ERROR,
        message="数据库错误"
    )
    exc4 = ValueError("普通Python异常")
    
    metrics.record_error(exc1)
    metrics.record_error(exc2)
    metrics.record_error(exc3)
    metrics.record_error(exc4)
    
    # 获取统计信息
    stats = metrics.get_metrics()
    
    # 验证错误计数
    assert stats["error_counts"]["CustomException"] == 3
    assert stats["error_counts"]["ValueError"] == 1
    
    # 验证错误码计数
    assert stats["error_codes_count"]["API_ERROR"] == 2
    assert stats["error_codes_count"]["DATABASE_ERROR"] == 1
    
    # 验证最近错误列表
    assert len(stats["last_errors"]) == 4
    assert stats["last_errors"][-1]["type"] == "ValueError"

def test_error_handler_decorator():
    """测试错误处理装饰器。"""
    
    @error_handler(ErrorCode.API_ERROR)
    def api_call():
        raise ValueError("API调用失败")
    
    # 测试装饰器是否正确包装异常
    with pytest.raises(CustomException) as exc_info:
        api_call()
    
    assert exc_info.value.error_code == ErrorCode.API_ERROR
    assert "API调用失败" in str(exc_info.value)
    
    # 测试装饰器是否保留原始异常信息
    assert exc_info.value.__cause__.__class__ == ValueError

def test_global_error_handler():
    """测试全局错误处理器。"""
    # 记录处理的错误
    handled_errors = []
    
    def test_handler(exc):
        handled_errors.append(exc)
    
    # 添加测试处理器
    global_error_handler.add_handler(Exception, test_handler)
    
    # 创建一个测试异常
    test_exc = CustomException(
        error_code=ErrorCode.SYSTEM_ERROR,
        message="测试错误"
    )
    
    # 使用全局处理器处理异常
    global_error_handler.handle(test_exc)
    
    # 验证错误被正确处理
    assert len(handled_errors) == 1
    assert handled_errors[0] == test_exc

def test_setup_error_handling():
    """测试错误处理设置。"""
    # 设置全局错误处理
    setup_error_handling()
    
    # 验证sys.excepthook被正确设置
    assert sys.excepthook != sys.__excepthook__
    
    # 测试异常处理
    handled_errors = []
    
    def test_handler(exc):
        handled_errors.append(exc)
    
    global_error_handler.add_handler(Exception, test_handler)
    
    # 触发一个未捕获的异常
    try:
        sys.excepthook(ValueError, ValueError("测试错误"), None)
    except:
        pass
    
    # 验证错误被正确处理
    assert len(handled_errors) == 1
    assert isinstance(handled_errors[0], ValueError)

@pytest.mark.asyncio
async def test_async_error_handling():
    """测试异步错误处理。"""
    # 记录处理的错误
    handled_errors = []
    
    def test_handler(exc):
        handled_errors.append(exc)
    
    # 使用直接的错误处理方法
    handler = ErrorHandler()
    handler.add_handler(Exception, test_handler)
    
    # 创建一个测试异常
    test_exc = CustomException(
        error_code=ErrorCode.API_ERROR,
        message="异步错误"
    )
    
    # 部分1：测试同步错误处理
    handler.handle(test_exc)
    
    # 验证错误被正确处理
    assert len(handled_errors) == 1
    assert isinstance(handled_errors[0], CustomException)
    assert handled_errors[0].error_code == ErrorCode.API_ERROR
    
    # 清空处理的错误
    handled_errors.clear()
    
    # 部分2：测试集成到异步环境中
    loop = asyncio.get_event_loop()
    
    # 设置异步错误处理器
    def async_exception_handler(loop, context):
        exc = context.get('exception')
        if exc:
            handler.handle(exc)
    
    handler._async_exception_handler = async_exception_handler
    handler.setup_async_handler(loop)
    
    # 测试通过异步方式处理异常
    async def async_function():
        # 模拟异步错误
        await asyncio.sleep(0.01)
        # 创建一个模拟异常上下文
        loop.call_exception_handler({
            'message': '异步测试错误',
            'exception': test_exc
        })
        return True
    
    # 执行异步函数
    result = await async_function()
    assert result is True
    
    # 等待异步处理完成
    await asyncio.sleep(0.01)
    
    # 验证错误被正确处理
    assert len(handled_errors) == 1
    assert isinstance(handled_errors[0], CustomException)
    assert handled_errors[0].error_code == ErrorCode.API_ERROR 