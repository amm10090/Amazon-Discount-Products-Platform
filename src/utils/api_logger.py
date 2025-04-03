"""
API日志记录模块，提供API调用的详细日志记录功能。
集成了Loguru日志系统，支持请求/响应记录、性能监控和错误追踪。
"""

import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from functools import wraps
import re
from loguru import logger
from .log_config import get_logger, LogContext

class APILogger:
    """API日志记录器，用于记录API请求和响应的详细信息。"""
    
    def __init__(
        self,
        name: str,
        sensitive_fields: Optional[list[str]] = None,
        max_body_length: int = 1000
    ):
        """
        初始化API日志记录器
        
        Args:
            name: 日志记录器名称
            sensitive_fields: 需要在日志中遮蔽的敏感字段列表
            max_body_length: 响应体最大记录长度
        """
        self.logger = get_logger(name)
        self.sensitive_fields = sensitive_fields or [
            "access_key",
            "secret_key",
            "api_key",
            "password",
            "token",
            "authorization"  # 添加 authorization 字段
        ]
        self.max_body_length = max_body_length
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        遮蔽数据中的敏感信息
        
        Args:
            data: 原始数据
            
        Returns:
            Dict[str, Any]: 遮蔽后的数据
        """
        if not isinstance(data, dict):
            return data
            
        masked_data = data.copy()
        for key, value in masked_data.items():
            if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                masked_data[key] = "******"
            elif isinstance(value, dict):
                masked_data[key] = self._mask_sensitive_data(value)
            elif isinstance(value, list):
                masked_data[key] = [
                    self._mask_sensitive_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str) and any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                masked_data[key] = "******"
        return masked_data
    
    def _truncate_response(self, response_data: Any) -> Any:
        """
        截断过长的响应数据
        
        Args:
            response_data: 原始响应数据
            
        Returns:
            Any: 截断后的响应数据
        """
        if isinstance(response_data, dict):
            return {
                k: self._truncate_response(v)
                for k, v in response_data.items()
            }
        elif isinstance(response_data, list):
            if len(response_data) > 10:
                return [
                    self._truncate_response(response_data[0]),
                    "...",
                    f"[还有 {len(response_data)-2} 项]",
                    self._truncate_response(response_data[-1])
                ]
            return [self._truncate_response(item) for item in response_data]
        elif isinstance(response_data, str):
            if len(response_data) > self.max_body_length:
                return f"{response_data[:self.max_body_length]}... [截断，完整长度: {len(response_data)}]"
        return response_data
    
    def log_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        **extra_kwargs
    ) -> None:
        """
        记录API请求信息
        
        Args:
            method: 请求方法
            url: 请求URL
            headers: 请求头
            params: URL参数
            data: 请求体数据
            **extra_kwargs: 其他请求相关信息
        """
        # 深拷贝并遮蔽敏感数据
        headers_copy = self._mask_sensitive_data(headers or {})
        data_copy = self._mask_sensitive_data(data or {}) if data else None
        
        request_info = {
            "method": method,
            "url": url,
            "headers": headers_copy,
            "params": params,
            "data": data_copy
        }
        
        # 将请求信息转换为字符串
        request_str = "API请求: " + json.dumps(request_info, ensure_ascii=False)
        
        # 直接写入日志，不传递额外参数
        with self.logger.catch(message="记录API请求时发生错误"):
            self.logger.opt(raw=True).info(request_str + "\n")
    
    def log_response(
        self,
        status_code: int,
        response_data: Any,
        elapsed: float,
        **extra_kwargs
    ) -> None:
        """
        记录API响应信息
        
        Args:
            status_code: 响应状态码
            response_data: 响应数据
            elapsed: 请求耗时（秒）
            **extra_kwargs: 其他响应相关信息
        """
        response_info = {
            "status_code": status_code,
            "elapsed": f"{elapsed:.3f}s",
            "response": self._truncate_response(response_data)
        }
        
        # 将响应信息转换为字符串
        response_str = "API响应: " + json.dumps(response_info, ensure_ascii=False)
        
        # 选择日志级别
        log_level = "INFO" if 200 <= status_code < 400 else "ERROR"
        
        # 直接写入日志，不传递额外参数
        with self.logger.catch(message="记录API响应时发生错误"):
            if log_level == "INFO":
                self.logger.opt(raw=True).info(response_str + "\n")
            else:
                self.logger.opt(raw=True).error(response_str + "\n")
    
    def log_error(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        **extra_kwargs
    ) -> None:
        """
        记录API错误信息
        
        Args:
            error: 异常对象
            context: 错误上下文信息
            **extra_kwargs: 其他错误相关信息
        """
        error_info = {
            "type": error.__class__.__name__,
            "message": str(error),
            "context": context or {}
        }
        
        # 将错误信息转换为字符串
        error_str = "API错误: " + json.dumps(error_info, ensure_ascii=False)
        
        # 直接写入日志，不传递额外参数
        with self.logger.catch(message="记录API错误时发生错误"):
            self.logger.opt(raw=True).error(error_str + "\n")

def with_api_logging(api_name: str):
    """
    API日志记录装饰器
    
    Args:
        api_name: API名称，用于日志标识
        
    Returns:
        Callable: 装饰器函数
    """
    api_logger = APILogger(api_name)
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = datetime.now()
            request_id = kwargs.get("request_id", str(start_time.timestamp()))
            
            with LogContext(api_name=api_name, request_id=request_id):
                try:
                    # 记录请求信息 - 提取参数，使用默认值
                    api_logger.log_request(
                        method=kwargs.get("method", "UNKNOWN"),
                        url=kwargs.get("url", "UNKNOWN"),
                        headers=kwargs.get("headers", {}),
                        params=kwargs.get("params", {}),
                        data=kwargs.get("data", {})
                    )
                    
                    # 执行API调用
                    response = await func(*args, **kwargs)
                    
                    # 计算耗时
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    # 记录响应信息
                    api_logger.log_response(
                        status_code=getattr(response, "status_code", 200),
                        response_data=response,
                        elapsed=elapsed
                    )
                    
                    return response
                    
                except Exception as e:
                    # 记录错误信息
                    api_logger.log_error(
                        error=e,
                        context={
                            "args": str(args),
                            "kwargs": str(kwargs)
                        }
                    )
                    raise
                    
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = datetime.now()
            request_id = kwargs.get("request_id", str(start_time.timestamp()))
            
            with LogContext(api_name=api_name, request_id=request_id):
                try:
                    # 记录请求信息 - 提取参数，使用默认值
                    api_logger.log_request(
                        method=kwargs.get("method", "UNKNOWN"),
                        url=kwargs.get("url", "UNKNOWN"),
                        headers=kwargs.get("headers", {}),
                        params=kwargs.get("params", {}),
                        data=kwargs.get("data", {})
                    )
                    
                    # 执行API调用
                    response = func(*args, **kwargs)
                    
                    # 计算耗时
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    # 记录响应信息
                    api_logger.log_response(
                        status_code=getattr(response, "status_code", 200),
                        response_data=response,
                        elapsed=elapsed
                    )
                    
                    return response
                    
                except Exception as e:
                    # 记录错误信息
                    api_logger.log_error(
                        error=e,
                        context={
                            "args": str(args),
                            "kwargs": str(kwargs)
                        }
                    )
                    raise
                    
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator 