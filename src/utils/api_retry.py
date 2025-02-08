import asyncio
import logging
from typing import TypeVar, Callable, Any, Optional
from functools import wraps
import aiohttp

T = TypeVar('T')

class APIRetryHandler:
    """API 重试处理器，用于处理请求限制和重试逻辑"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0
    ):
        """
        初始化重试处理器
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间(秒)
            max_delay: 最大延迟时间(秒)
            exponential_base: 指数退避的基数
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        
    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟时间
        
        Args:
            attempt: 当前重试次数
            
        Returns:
            float: 延迟时间(秒)
        """
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        return delay
        
    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args,
        **kwargs
    ) -> Any:
        """
        使用重试机制执行异步函数
        
        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            Any: 函数执行结果
            
        Raises:
            Exception: 如果所有重试都失败则抛出最后一个异常
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except aiohttp.ClientResponseError as e:
                if e.status == 429:  # Too Many Requests
                    logging.error(
                        f"请求受限 (429)，API请求次数超出限制。"
                        f"建议：降低请求频率或增加请求间隔时间。"
                    )
                    raise  # 直接抛出429错误，不进行重试
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:  # 只有在不是最后一次尝试时才重试
                    delay = self.calculate_delay(attempt)
                    logging.warning(
                        f"请求失败，第 {attempt + 1}/{self.max_retries} 次重试，"
                        f"等待 {delay:.2f} 秒... 错误: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                
        if last_exception:
            raise last_exception

def with_retry(
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[float] = None
):
    """
    重试装饰器，用于为异步函数添加重试功能
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间(秒)
        max_delay: 最大延迟时间(秒)
        exponential_base: 指数退避的基数
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            retry_handler = APIRetryHandler(
                max_retries=max_retries or 3,
                base_delay=base_delay or 1.0,
                max_delay=max_delay or 30.0,
                exponential_base=exponential_base or 2.0
            )
            return await retry_handler.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator 