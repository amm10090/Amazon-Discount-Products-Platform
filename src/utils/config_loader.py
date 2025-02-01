import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import os

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.env = os.getenv('ENV', 'development')
        # 在初始化时就加载配置
        self.load_config()
        
    def load_config(self, config_dir: str = "config") -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_dir: 配置文件目录
            
        Returns:
            Dict[str, Any]: 合并后的配置
        """
        try:
            # 基础配置文件路径
            base_config_path = Path(config_dir) / "app.yaml"
            
            # 环境特定配置文件路径
            env_config_path = Path(config_dir) / f"{self.env}.yaml"
            
            # 加载基础配置
            if base_config_path.exists():
                with open(base_config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}
            
            # 加载环境特定配置并合并
            if env_config_path.exists():
                with open(env_config_path, 'r', encoding='utf-8') as f:
                    env_config = yaml.safe_load(f) or {}
                    self._merge_config(self.config, env_config)
                    
            return self.config
            
        except Exception as e:
            print(f"Error loading config: {str(e)}")
            return {}
    
    def _merge_config(self, base: Dict, override: Dict) -> None:
        """递归合并配置字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {})
    
    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.get_logging_config().get('level', 'INFO')
    
    @property
    def use_colors(self) -> bool:
        """是否使用颜色输出"""
        return self.get_logging_config().get('use_colors', True)
    
    @property
    def console_config(self) -> Dict[str, Any]:
        """获取控制台输出配置"""
        return self.get_logging_config().get('console', {})
    
    @property
    def file_config(self) -> Dict[str, Any]:
        """获取文件输出配置"""
        return self.get_logging_config().get('file', {})
    
    @property
    def buffer_config(self) -> Dict[str, Any]:
        """获取缓冲配置"""
        return self.get_logging_config().get('buffer', {})
    
    def get_component_config(self, component: str) -> Optional[Dict[str, Any]]:
        """获取特定组件的日志配置"""
        components = self.get_logging_config().get('components', {})
        return components.get(component)

# 创建全局配置加载器实例
config_loader = ConfigLoader() 