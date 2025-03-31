"""
WebDriver池管理模块
该模块负责管理多个WebDriver实例，支持并行爬取操作。

主要功能：
1. 创建和管理WebDriver实例池
2. 提供线程安全的获取和释放WebDriver方法
3. 支持动态扩展和收缩池大小
4. 监控资源使用情况
"""

import os
import sys
import time
import threading
import logging
import random
import psutil
from typing import Optional, List, Dict
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.utils.webdriver_manager import WebDriverConfig
from selenium import webdriver


class WebDriverPool:
    """WebDriver池管理类
    
    负责创建和管理多个WebDriver实例，提供线程安全的获取和释放方法。
    支持动态调整池大小，监控资源使用，以及智能分配WebDriver。
    """
    
    def __init__(self, size: int = 5, headless: bool = True, 
                 min_idle: int = 1, max_wait_time: int = 30,
                 check_interval: int = 5):
        """
        初始化WebDriver池
        
        Args:
            size: 池中WebDriver的最大数量
            headless: 是否使用无头模式
            min_idle: 保持的最小空闲WebDriver数量
            max_wait_time: 获取WebDriver的最大等待时间（秒）
            check_interval: 资源检查间隔（秒）
        """
        self.size = size
        self.headless = headless
        self.min_idle = min_idle
        self.max_wait_time = max_wait_time
        self.check_interval = check_interval
        
        # 初始化池和使用状态
        self._pool: List[webdriver.Chrome] = []
        self._used: Dict[webdriver.Chrome, datetime] = {}
        self._lock = threading.Lock()
        self._config = WebDriverConfig()
        
        # 线程本地存储
        self._thread_local = threading.local()
        
        # 启动资源监控线程
        self._stop_monitor = False
        self._monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self._monitor_thread.start()
        
        # 初始化日志
        self.logger = logging.getLogger("WebDriverPool")
        
        # 预创建部分WebDriver
        self._prefill_pool()
        
    def _prefill_pool(self):
        """预先填充池，创建最小数量的WebDriver"""
        with self._lock:
            for _ in range(self.min_idle):
                if len(self._pool) < self.size:
                    try:
                        driver = self._create_driver()
                        self._pool.append(driver)
                        self.logger.info(f"预创建WebDriver成功，当前池大小: {len(self._pool)}")
                    except Exception as e:
                        self.logger.error(f"预创建WebDriver失败: {str(e)}")
        
    def get_driver(self) -> Optional[webdriver.Chrome]:
        """
        获取可用的WebDriver实例
        
        Returns:
            webdriver.Chrome: 可用的WebDriver实例，如果没有可用实例则返回None
        """
        start_time = time.time()
        
        while time.time() - start_time < self.max_wait_time:
            with self._lock:
                # 首先检查当前线程是否已经持有WebDriver
                if hasattr(self._thread_local, 'driver'):
                    driver = self._thread_local.driver
                    if driver in self._pool and driver not in self._used:
                        self._used[driver] = datetime.now()
                        return driver
                
                # 尝试从空闲池中获取
                available = [d for d in self._pool if d not in self._used]
                if available:
                    driver = random.choice(available)  # 随机选择，避免总是使用同一个
                    self._used[driver] = datetime.now()
                    self._thread_local.driver = driver
                    self.logger.debug(f"获取到现有WebDriver，当前使用: {len(self._used)}/{len(self._pool)}")
                    return driver
                
                # 如果没有可用的driver并且池还没满，创建新的
                if len(self._pool) < self.size:
                    try:
                        driver = self._create_driver()
                        self._pool.append(driver)
                        self._used[driver] = datetime.now()
                        self._thread_local.driver = driver
                        self.logger.info(f"创建新WebDriver成功，当前池大小: {len(self._pool)}")
                        return driver
                    except Exception as e:
                        self.logger.error(f"创建新WebDriver失败: {str(e)}")
            
            # 如果所有WebDriver都在使用，等待一段时间后重试
            time.sleep(0.5)
        
        self.logger.warning(f"获取WebDriver超时，已等待{self.max_wait_time}秒")
        return None
    
    def _create_driver(self) -> webdriver.Chrome:
        """创建新的WebDriver实例"""
        driver = self._config.create_chrome_driver(headless=self.headless)
        # 设置页面加载超时
        driver.set_page_load_timeout(30)
        # 设置脚本执行超时
        driver.set_script_timeout(30)
        return driver
    
    def release_driver(self, driver: Optional[webdriver.Chrome] = None):
        """
        释放WebDriver实例
        
        Args:
            driver: 要释放的WebDriver实例，如果为None则释放当前线程持有的WebDriver
        """
        if driver is None:
            # 如果没有指定driver，尝试获取当前线程持有的driver
            if hasattr(self._thread_local, 'driver'):
                driver = self._thread_local.driver
            else:
                return
            
        with self._lock:
            if driver in self._used:
                del self._used[driver]
                self.logger.debug(f"释放WebDriver成功，当前使用: {len(self._used)}/{len(self._pool)}")
                
                # 清除线程本地存储
                if hasattr(self._thread_local, 'driver') and self._thread_local.driver == driver:
                    delattr(self._thread_local, 'driver')
    
    def _monitor_resources(self):
        """监控系统资源使用情况，动态调整池大小"""
        while not self._stop_monitor:
            try:
                # 获取系统内存使用率
                mem_usage = psutil.virtual_memory().percent
                # 获取CPU使用率
                cpu_usage = psutil.cpu_percent(interval=1)
                
                # 如果资源使用率过高，考虑减少池大小
                if mem_usage > 85 or cpu_usage > 85:
                    with self._lock:
                        # 计算可以释放的WebDriver数量
                        idle_drivers = [d for d in self._pool if d not in self._used]
                        release_count = max(0, len(idle_drivers) - self.min_idle)
                        
                        if release_count > 0:
                            self.logger.warning(
                                f"系统资源使用率高(内存:{mem_usage}%, CPU:{cpu_usage}%)，"
                                f"释放{release_count}个空闲WebDriver"
                            )
                            
                            # 释放多余的空闲WebDriver
                            for _ in range(release_count):
                                if idle_drivers:
                                    driver = idle_drivers.pop()
                                    self._pool.remove(driver)
                                    try:
                                        driver.quit()
                                    except Exception as e:
                                        self.logger.error(f"关闭WebDriver时出错: {str(e)}")
                
                # 检查WebDriver健康状态
                with self._lock:
                    for driver in list(self._pool):
                        if driver not in self._used:
                            try:
                                # 简单测试WebDriver是否正常工作
                                driver.current_url
                            except Exception as e:
                                self.logger.warning(f"检测到异常WebDriver，将其移除: {str(e)}")
                                self._pool.remove(driver)
                                try:
                                    driver.quit()
                                except:
                                    pass
                                
                                # 创建新的替代
                                if len(self._pool) < self.min_idle:
                                    try:
                                        new_driver = self._create_driver()
                                        self._pool.append(new_driver)
                                        self.logger.info("创建替代WebDriver成功")
                                    except Exception as e:
                                        self.logger.error(f"创建替代WebDriver失败: {str(e)}")
                
            except Exception as e:
                self.logger.error(f"资源监控线程出错: {str(e)}")
                
            # 等待下一个检查周期
            time.sleep(self.check_interval)
    
    def close_all(self):
        """关闭所有WebDriver实例并清理资源"""
        self._stop_monitor = True
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)
            
        with self._lock:
            for driver in self._pool:
                try:
                    driver.quit()
                except Exception as e:
                    self.logger.error(f"关闭WebDriver时出错: {str(e)}")
                    
            self._pool = []
            self._used = {}
            self.logger.info("已关闭所有WebDriver实例") 