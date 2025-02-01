from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging
import os
import psutil
import tempfile
from typing import Optional

# 配置WebDriver Manager的日志
logging.getLogger('WDM').setLevel(logging.INFO)

class WebDriverConfig:
    """Chrome WebDriver配置管理类"""
    
    @staticmethod
    def setup_chrome_options(headless: bool = True) -> webdriver.ChromeOptions:
        """
        设置Chrome浏览器选项
        
        Args:
            headless: 是否使用无头模式，默认为True
            
        Returns:
            webdriver.ChromeOptions: 配置好的Chrome选项对象
        """
        try:
            # 检查系统资源
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                raise Exception(f"系统内存使用率过高: {memory.percent}%")
                
            options = webdriver.ChromeOptions()
            
            # Linux环境特定配置
            options.add_argument('--no-sandbox')  # 在root用户下运行必需
            options.add_argument('--disable-dev-shm-usage')  # 避免Linux下的内存问题
            
            # 设置共享内存目录
            if os.path.exists('/dev/shm'):
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--shm-size=2gb')
            
            # 设置临时目录
            options.add_argument(f'--user-data-dir={tempfile.gettempdir()}/chrome_temp')
            
            # 无头模式配置
            if headless:
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')
                
            # 浏览器性能优化
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-dev-tools')
            options.add_argument('--disable-logging')
            options.add_argument('--log-level=3')
            options.add_argument('--silent')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 设置窗口大小和其他选项
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--disable-notifications')
            
            # 设置user agent
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
            options.add_argument(f'user-agent={user_agent}')
            
            # 添加实验性选项
            options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
            options.add_experimental_option('useAutomationExtension', False)
            
            return options
            
        except Exception as e:
            logging.error(f"Chrome选项配置失败: {str(e)}")
            raise

    @staticmethod
    def create_chrome_driver(
        headless: bool = True,
        custom_options: Optional[webdriver.ChromeOptions] = None
    ) -> webdriver.Chrome:
        """
        创建并配置Chrome WebDriver实例
        
        Args:
            headless: 是否使用无头模式，默认为True
            custom_options: 可选的自定义Chrome选项
            
        Returns:
            webdriver.Chrome: 配置好的Chrome WebDriver实例
            
        Raises:
            Exception: 当初始化失败时抛出异常
        """
        try:
            # 设置ChromeDriver的日志级别
            logging.getLogger('selenium').setLevel(logging.WARNING)
            logging.getLogger('urllib3').setLevel(logging.WARNING)
            
            # 使用提供的选项或创建新的选项
            options = custom_options if custom_options else WebDriverConfig.setup_chrome_options(headless)
            
            # 配置ChromeDriver服务
            service = Service(ChromeDriverManager().install())
            service.log_path = os.devnull
            service.service_args = ['--verbose', '--log-path=/dev/null', '--disable-dev-shm-usage']
            
            # 创建driver实例并设置超时
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)
            driver.set_script_timeout(30)
            driver.implicitly_wait(10)
            
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
            try:
                os.system('pkill -f chrome')
                os.system('pkill -f chromedriver')
            except:
                pass
            raise

    @staticmethod
    def cleanup_chrome_processes():
        """清理Chrome相关进程"""
        try:
            os.system('pkill -f chrome')
            os.system('pkill -f chromedriver')
            logging.info("Chrome进程清理完成")
        except Exception as e:
            logging.error(f"Chrome进程清理失败: {str(e)}") 