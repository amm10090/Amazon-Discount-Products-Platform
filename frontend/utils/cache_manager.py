import streamlit as st
from typing import Any, Callable, Optional, TypeVar, Dict
from datetime import datetime, timedelta
import functools
import json
import os
from pathlib import Path

T = TypeVar('T')

class CacheManager:
    """缓存管理器，用于统一管理应用的缓存策略和监控"""
    
    def __init__(self):
        self.cache_stats: Dict[str, Any] = {
            'hits': 0,
            'misses': 0,
            'total_calls': 0,
            'last_cleanup': None
        }
        
        # 确保缓存目录存在
        self.cache_dir = Path('.streamlit/cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载缓存统计信息
        self._load_stats()
    
    def _load_stats(self):
        """加载缓存统计信息"""
        stats_file = self.cache_dir / 'cache_stats.json'
        if stats_file.exists():
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    self.cache_stats = json.load(f)
            except Exception as e:
                st.error(f"加载缓存统计信息失败: {str(e)}")
    
    def _save_stats(self):
        """保存缓存统计信息"""
        stats_file = self.cache_dir / 'cache_stats.json'
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"保存缓存统计信息失败: {str(e)}")
    
    def data_cache(
        self,
        ttl: Optional[int] = 300,
        max_entries: Optional[int] = 1000,
        show_spinner: bool = True
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        数据缓存装饰器，用于缓存数据加载和处理结果
        
        Args:
            ttl: 缓存过期时间（秒）
            max_entries: 最大缓存条目数
            show_spinner: 是否显示加载提示
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @st.cache_data(
                ttl=timedelta(seconds=ttl) if ttl else None,
                max_entries=max_entries,
                show_spinner=show_spinner
            )
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                self.cache_stats['total_calls'] += 1
                try:
                    result = func(*args, **kwargs)
                    self.cache_stats['hits'] += 1
                    return result
                except Exception as e:
                    self.cache_stats['misses'] += 1
                    raise e
                finally:
                    self._save_stats()
            return wrapper
        return decorator
    
    def resource_cache(
        self,
        show_spinner: bool = True
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        资源缓存装饰器，用于缓存数据库连接等资源
        
        Args:
            show_spinner: 是否显示加载提示
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @st.cache_resource(show_spinner=show_spinner)
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                self.cache_stats['total_calls'] += 1
                try:
                    result = func(*args, **kwargs)
                    self.cache_stats['hits'] += 1
                    return result
                except Exception as e:
                    self.cache_stats['misses'] += 1
                    raise e
                finally:
                    self._save_stats()
            return wrapper
        return decorator
    
    def clear_cache(self):
        """清理所有缓存"""
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
            self.cache_stats['last_cleanup'] = datetime.now().isoformat()
            self._save_stats()
            return True
        except Exception as e:
            st.error(f"清理缓存失败: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'hits': self.cache_stats['hits'],
            'misses': self.cache_stats['misses'],
            'total_calls': self.cache_stats['total_calls'],
            'hit_rate': (
                self.cache_stats['hits'] / self.cache_stats['total_calls'] * 100
                if self.cache_stats['total_calls'] > 0 else 0
            ),
            'last_cleanup': self.cache_stats['last_cleanup']
        }

# 创建全局缓存管理器实例
cache_manager = CacheManager()
