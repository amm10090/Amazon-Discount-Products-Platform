from typing import Dict, Any, Optional
import json
import time
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，用于处理datetime对象"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = None):
        """初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录路径，如果为None则使用环境变量CACHE_DIR
        """
        # 从环境变量读取配置
        self.enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_dir = Path(cache_dir or os.getenv('CACHE_DIR', 'cache'))
        
        # 从环境变量读取TTL配置（秒）
        self.CACHE_TTL = {
            'Offers': int(os.getenv('CACHE_TTL_OFFERS', 3600)),  # 1小时
            'BrowseNodeInfo': int(os.getenv('CACHE_TTL_BROWSE_NODE', 3600)),  # 1小时
            'default': int(os.getenv('CACHE_TTL_DEFAULT', 86400))  # 1天
        }
        
        # 如果缓存启用，创建缓存目录
        if self.enabled:
            self.cache_dir.mkdir(exist_ok=True)
            print(f"缓存已启用，目录: {self.cache_dir}")
        else:
            print("缓存已禁用")
        
    def _get_cache_file(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.json"
        
    def get(self, key: str) -> Optional[Dict]:
        """获取缓存数据
        
        Args:
            key: 缓存键名（通常是ASIN）
            
        Returns:
            Optional[Dict]: 缓存的数据，如果不存在或已过期则返回None
        """
        # 如果缓存被禁用，直接返回None
        if not self.enabled:
            return None
            
        cache_file = self._get_cache_file(key)
        if not cache_file.exists():
            return None
            
        try:
            with cache_file.open('r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # 检查各个资源的过期时间
            current_time = time.time()
            is_expired = False
            
            for resource_type, ttl in self.CACHE_TTL.items():
                if resource_type in cache_data:
                    if current_time - cache_data['timestamp'] > ttl:
                        is_expired = True
                        break
                        
            if is_expired:
                return None
                
            return cache_data['data']
            
        except Exception as e:
            print(f"读取缓存出错: {str(e)}")
            return None
            
    def set(self, key: str, data: Dict):
        """设置缓存数据
        
        Args:
            key: 缓存键名（通常是ASIN）
            data: 要缓存的数据
        """
        # 如果缓存被禁用，直接返回
        if not self.enabled:
            return
            
        try:
            cache_file = self._get_cache_file(key)
            cache_data = {
                'timestamp': time.time(),
                'data': data
            }
            
            with cache_file.open('w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, cls=DateTimeEncoder)
                
        except Exception as e:
            print(f"写入缓存出错: {str(e)}")
            
    def clear_expired(self):
        """清理过期的缓存文件"""
        # 如果缓存被禁用，直接返回
        if not self.enabled:
            return
            
        try:
            current_time = time.time()
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with cache_file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    # 使用最长的TTL作为过期判断
                    if current_time - cache_data['timestamp'] > self.CACHE_TTL['default']:
                        cache_file.unlink()
                        print(f"已删除过期缓存: {cache_file}")
                        
                except Exception:
                    # 如果文件损坏，直接删除
                    cache_file.unlink()
                    print(f"已删除损坏的缓存文件: {cache_file}")
                    
        except Exception as e:
            print(f"清理缓存出错: {str(e)}")
            
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        if not self.enabled:
            return {
                "enabled": False,
                "status": "Cache is disabled"
            }
            
        try:
            total_files = 0
            total_size = 0
            expired_files = 0
            current_time = time.time()
            
            for cache_file in self.cache_dir.glob("*.json"):
                total_files += 1
                total_size += cache_file.stat().st_size
                
                try:
                    with cache_file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    if current_time - cache_data['timestamp'] > self.CACHE_TTL['default']:
                        expired_files += 1
                except:
                    expired_files += 1
                    
            return {
                "enabled": True,
                "cache_dir": str(self.cache_dir),
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "expired_files": expired_files,
                "ttl_config": self.CACHE_TTL
            }
            
        except Exception as e:
            return {
                "enabled": True,
                "status": f"Error getting cache stats: {str(e)}"
            } 