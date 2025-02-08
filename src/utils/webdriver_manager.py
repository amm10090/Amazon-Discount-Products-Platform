from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import logging
import os
import psutil
import tempfile
from typing import Optional
from pathlib import Path
import subprocess
import time
import shutil

# 配置日志级别
logging.getLogger('selenium').setLevel(logging.WARNING)

class WebDriverConfig:
    """Chrome WebDriver配置管理类"""
    
    @staticmethod
    def get_chrome_path() -> Optional[str]:
        """获取Chrome浏览器路径"""
        try:
            # 在WSL环境下优先检查Windows的Chrome
            wsl_chrome_paths = [
                '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
                '/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe'
            ]
            
            # Linux环境的Chrome路径
            linux_chrome_paths = [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium'
            ]
            
            # 首先检查WSL路径
            for path in wsl_chrome_paths:
                if os.path.exists(path):
                    logging.info(f"在WSL中找到Chrome: {path}")
                    return path
                    
            # 然后检查Linux路径
            for path in linux_chrome_paths:
                if os.path.exists(path):
                    logging.info(f"在Linux中找到Chrome: {path}")
                    return path
                    
            # 尝试使用which命令
            try:
                chrome_path = subprocess.check_output(['which', 'google-chrome'], 
                                                   stderr=subprocess.STDOUT).decode().strip()
                if os.path.exists(chrome_path):
                    logging.info(f"通过which命令找到Chrome: {chrome_path}")
                    return chrome_path
            except:
                pass
                
            logging.warning("未找到Chrome浏览器")
            return None
            
        except Exception as e:
            logging.error(f"查找Chrome路径时出错: {str(e)}")
            return None
    
    @staticmethod
    def setup_chrome_options(headless: bool = True) -> webdriver.ChromeOptions:
        """设置Chrome浏览器选项"""
        try:
            # 检查系统资源
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                raise Exception(f"系统内存使用率过高: {memory.percent}%")
                
            options = webdriver.ChromeOptions()
            
            # 设置Chrome二进制文件路径
            chrome_path = WebDriverConfig.get_chrome_path()
            if chrome_path:
                options.binary_location = chrome_path
                logging.info(f"设置Chrome路径: {chrome_path}")
            
            # Linux环境特定配置
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # 设置共享内存目录
            if os.path.exists('/dev/shm'):
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--shm-size=2gb')
            
            # 设置临时目录（使用时间戳确保唯一性）
            timestamp = str(int(time.time()))
            temp_dir = Path(tempfile.gettempdir()) / f'chrome_temp_{timestamp}'
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
            options.add_argument(f'--user-data-dir={temp_dir}')
            logging.info(f"创建新的用户数据目录: {temp_dir}")
            
            # 无头模式配置
            if headless:
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')
            
            # 网络优化
            options.add_argument('--disable-web-security')  # 禁用同源策略
            options.add_argument('--ignore-certificate-errors')  # 忽略证书错误
            options.add_argument('--allow-running-insecure-content')  # 允许不安全内容
            options.add_argument('--disable-client-side-phishing-detection')  # 禁用钓鱼检测

            
            # 性能优化
            options.add_argument('--disable-extensions')  # 禁用扩展
            options.add_argument('--disable-default-apps')  # 禁用默认应用
            options.add_argument('--disable-sync')  # 禁用同步
            options.add_argument('--disable-background-networking')  # 禁用后台网络
            options.add_argument('--disable-background-timer-throttling')  # 禁用后台定时器限制
            options.add_argument('--disable-backgrounding-occluded-windows')  # 禁用后台窗口限制
            options.add_argument('--disable-renderer-backgrounding')  # 禁用渲染器后台处理
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-dev-tools')
            options.add_argument('--disable-logging')
            options.add_argument('--log-level=3')
            options.add_argument('--silent')
            
            # 内存优化
            options.add_argument('--disable-dev-shm-usage')  # 禁用/dev/shm使用
            options.add_argument('--disable-features=TranslateUI')  # 禁用翻译
            options.add_argument('--disable-features=site-per-process')  # 禁用站点隔离
            options.add_argument('--disable-hang-monitor')  # 禁用挂起监视器
            
            # 自动化相关
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
            options.add_experimental_option('useAutomationExtension', False)
            
            # 设置窗口大小和其他选项
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-notifications')
            
            # 设置user agent
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
            options.add_argument(f'user-agent={user_agent}')
            
            # 禁用密码管理器弹窗和其他弹窗
            prefs = {
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False,
                'profile.default_content_setting_values.notifications': 2,
                'profile.default_content_setting_values.media_stream_mic': 2,
                'profile.default_content_setting_values.media_stream_camera': 2,
                'profile.default_content_setting_values.geolocation': 2,
                'profile.managed_default_content_settings.images': 2,  # 1允许加载图片，2禁止加载图片
            }
            options.add_experimental_option('prefs', prefs)
            
            return options
            
        except Exception as e:
            logging.error(f"Chrome选项配置失败: {str(e)}")
            raise
            
    @staticmethod
    def create_chrome_driver(
        headless: bool = True,
        custom_options: Optional[webdriver.ChromeOptions] = None
    ) -> webdriver.Chrome:
        """创建并配置Chrome WebDriver实例
        
        使用Selenium Manager自动管理驱动程序
        """
        try:
            # 设置ChromeDriver的日志级别
            logging.getLogger('selenium').setLevel(logging.WARNING)
            
            # 设置环境变量以禁用Selenium Manager的遥测数据收集
            os.environ['SE_SKIP_ANALYTICS'] = 'true'
            
            # 删除可能存在的不兼容的chromedriver
            if os.path.exists('/usr/bin/chromedriver'):
                try:
                    os.remove('/usr/bin/chromedriver')
                    logging.info("已删除可能不兼容的chromedriver")
                except:
                    logging.warning("无法删除旧的chromedriver，可能需要sudo权限")
            
            # 使用提供的选项或创建新的选项
            options = custom_options if custom_options else WebDriverConfig.setup_chrome_options(headless)
            
            # 使用Selenium Manager自动管理驱动程序
            driver = webdriver.Chrome(options=options)
            
            # 设置超时时间（增加超时时间）
            driver.set_page_load_timeout(60)  # 页面加载超时时间
            driver.set_script_timeout(60)  # 脚本执行超时时间
            driver.implicitly_wait(20)  # 元素查找超时时间
            
            # 验证driver是否正常工作
            try:
                driver.execute_script('return navigator.userAgent')
                logging.info("ChromeDriver初始化成功并验证正常")
                return driver
            except Exception as e:
                logging.error(f"ChromeDriver验证失败: {str(e)}")
                if driver:
                    driver.quit()
                raise
                
        except Exception as e:
            logging.error(f"ChromeDriver初始化失败: {str(e)}")
            # 清理可能存在的Chrome进程
            WebDriverConfig.cleanup_chrome_processes()
            raise
            
    @staticmethod
    def cleanup_chrome_processes():
        """清理Chrome相关进程"""
        try:
            if os.name == 'posix':  # Linux/Unix
                os.system('pkill -f chrome')
                os.system('pkill -f chromedriver')
            elif os.name == 'nt':  # Windows
                os.system('taskkill /f /im chrome.exe')
                os.system('taskkill /f /im chromedriver.exe')
                
            # 清理临时目录
            temp_base = Path(tempfile.gettempdir())
            for item in temp_base.glob('chrome_temp_*'):
                if item.is_dir():
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                        logging.info(f"清理临时目录: {item}")
                    except:
                        pass
                        
            logging.info("Chrome进程和临时目录清理完成")
        except Exception as e:
            logging.error(f"Chrome进程清理失败: {str(e)}") 