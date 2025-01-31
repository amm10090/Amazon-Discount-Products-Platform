"""
Amazon PA-API缓存管理模块

该模块提供了一个通用的缓存管理实现，支持：
1. 基于文件系统的缓存存储
2. 可配置的缓存过期时间
3. 自动清理过期缓存
4. 压缩存储
5. 分类存储不同类型的数据
"""

import os
import json
import time
import gzip
import shutil
import yaml
from typing import Any, Dict, Optional, Union
from datetime import datetime
from pathlib import Path
import threading
import logging
from functools import wraps

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器类"""
    
    def __init__(self, config_path: str = "config/cache_config.yaml"):
        """
        初始化缓存管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.base_dir = Path(self.config["cache"]["base_dir"])
        self._ensure_cache_dirs()
        self._cleanup_thread = None
        self._start_cleanup_thread()
        
    def _load_config(self, config_path: str) -> Dict:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Dict: 配置信息
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            # 使用默认配置
            return {
                "cache": {
                    "base_dir": "cache",
                    "ttl": {
                        "offers": 3600,
                        "browse_nodes": 3600,
                        "others": 86400
                    },
                    "options": {
                        "max_size": 1000,
                        "cleanup_interval": 3600
                    },
                    "serialization": {
                        "format": "json",
                        "compress": True
                    },
                    "file_structure": {
                        "offers": "offers",
                        "browse_nodes": "browse_nodes",
                        "products": "products",
                        "images": "images"
                    }
                }
            }
            
    def _ensure_cache_dirs(self):
        """确保缓存目录存在"""
        self.base_dir.mkdir(exist_ok=True)
        for dir_name in self.config["cache"]["file_structure"].values():
            (self.base_dir / dir_name).mkdir(exist_ok=True)
            
    def _get_cache_path(self, key: str, cache_type: str = "products") -> Path:
        """
        获取缓存文件路径
        
        Args:
            key: 缓存键
            cache_type: 缓存类型
            
        Returns:
            Path: 缓存文件路径
        """
        dir_name = self.config["cache"]["file_structure"].get(cache_type, "products")
        return self.base_dir / dir_name / f"{key}.{'gz' if self.config['cache']['serialization']['compress'] else 'json'}"
        
    def _serialize(self, data: Any) -> bytes:
        """
        序列化数据
        
        Args:
            data: 要序列化的数据
            
        Returns:
            bytes: 序列化后的数据
        """
        json_str = json.dumps(data)
        if self.config["cache"]["serialization"]["compress"]:
            return gzip.compress(json_str.encode('utf-8'))
        return json_str.encode('utf-8')
        
    def _deserialize(self, data: bytes) -> Any:
        """
        反序列化数据
        
        Args:
            data: 要反序列化的数据
            
        Returns:
            Any: 反序列化后的数据
        """
        if self.config["cache"]["serialization"]["compress"]:
            data = gzip.decompress(data)
        return json.loads(data.decode('utf-8'))
        
    def get(self, key: str, cache_type: str = "products") -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key: 缓存键
            cache_type: 缓存类型
            
        Returns:
            Optional[Any]: 缓存的数据，如果不存在或已过期则返回None
        """
        try:
            cache_path = self._get_cache_path(key, cache_type)
            if not cache_path.exists():
                return None
                
            # 检查是否过期
            mtime = cache_path.stat().st_mtime
            ttl = self.config["cache"]["ttl"].get(cache_type, self.config["cache"]["ttl"]["others"])
            if time.time() - mtime > ttl:
                self.delete(key, cache_type)
                return None
                
            with open(cache_path, 'rb') as f:
                return self._deserialize(f.read())
        except Exception as e:
            logger.error(f"读取缓存失败: {str(e)}")
            return None
            
    def set(self, key: str, value: Any, cache_type: str = "products"):
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            value: 要缓存的数据
            cache_type: 缓存类型
        """
        try:
            cache_path = self._get_cache_path(key, cache_type)
            with open(cache_path, 'wb') as f:
                f.write(self._serialize(value))
        except Exception as e:
            logger.error(f"写入缓存失败: {str(e)}")
            
    def delete(self, key: str, cache_type: str = "products"):
        """
        删除缓存数据
        
        Args:
            key: 缓存键
            cache_type: 缓存类型
        """
        try:
            cache_path = self._get_cache_path(key, cache_type)
            if cache_path.exists():
                cache_path.unlink()
        except Exception as e:
            logger.error(f"删除缓存失败: {str(e)}")
            
    def clear_all(self):
        """清空所有缓存"""
        try:
            shutil.rmtree(self.base_dir)
            self._ensure_cache_dirs()
        except Exception as e:
            logger.error(f"清空缓存失败: {str(e)}")
            
    def _cleanup_expired(self):
        """清理过期缓存"""
        try:
            for cache_type, dir_name in self.config["cache"]["file_structure"].items():
                cache_dir = self.base_dir / dir_name
                ttl = self.config["cache"]["ttl"].get(cache_type, self.config["cache"]["ttl"]["others"])
                
                for cache_file in cache_dir.glob("*"):
                    if time.time() - cache_file.stat().st_mtime > ttl:
                        cache_file.unlink()
        except Exception as e:
            logger.error(f"清理过期缓存失败: {str(e)}")
            
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_task():
            while True:
                self._cleanup_expired()
                time.sleep(self.config["cache"]["options"]["cleanup_interval"])
                
        self._cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        self._cleanup_thread.start()
        
    def get_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 缓存统计信息
        """
        stats = {
            "total_size": 0,
            "total_files": 0,
            "by_type": {}
        }
        
        try:
            for cache_type, dir_name in self.config["cache"]["file_structure"].items():
                cache_dir = self.base_dir / dir_name
                type_size = sum(f.stat().st_size for f in cache_dir.glob("*"))
                type_count = len(list(cache_dir.glob("*")))
                
                stats["by_type"][cache_type] = {
                    "size": type_size,
                    "count": type_count
                }
                
                stats["total_size"] += type_size
                stats["total_files"] += type_count
                
            stats["last_cleanup"] = datetime.fromtimestamp(
                self.base_dir.stat().st_mtime
            ).isoformat()
            
        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {str(e)}")
            
        return stats

def cache_decorator(cache_type: str = "products", ttl: Optional[int] = None):
    """
    缓存装饰器
    
    用于方便地为函数添加缓存功能
    
    Args:
        cache_type: 缓存类型
        ttl: 过期时间（秒）
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}_{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            cached_result = self.cache_manager.get(cache_key, cache_type)
            if cached_result is not None:
                return cached_result
                
            # 执行原函数
            result = await func(self, *args, **kwargs)
            
            # 缓存结果
            self.cache_manager.set(cache_key, result, cache_type)
            
            return result
        return wrapper
    return decorator 