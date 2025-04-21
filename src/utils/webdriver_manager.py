"""
WebDriver管理器模块
该模块提供了Chrome WebDriver的配置和管理功能，主要用于反爬虫和模拟美国用户访问。
包含了各种浏览器配置选项，如User-Agent设置、地理位置模拟、语言设置等。

主要功能：
1. 配置Chrome浏览器选项
2. 创建和管理WebDriver实例
3. 实现反爬虫机制
4. 模拟美国用户的浏览行为
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import logging
import os
from typing import Optional
import random

# 配置Selenium日志级别为WARNING，减少不必要的日志输出
logging.getLogger('selenium').setLevel(logging.WARNING)

class WebDriverConfig:
    """Chrome WebDriver配置管理类
    
    该类负责管理和配置Chrome WebDriver的所有设置，包括：
    - 浏览器启动参数配置
    - 反爬虫策略实现
    - 地理位置和语言设置
    - 性能和隐私相关配置
    """
    
    # 预定义的User-Agent列表，用于随机切换，增加真实性
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ]
    
    # 美国主要城市的位置信息，用于地理位置模拟
    US_LOCATIONS = [
        {'state': 'NY', 'zip': '10001'},  # 纽约
        {'state': 'CA', 'zip': '90001'},  # 洛杉矶
        {'state': 'IL', 'zip': '60601'},  # 芝加哥
        {'state': 'TX', 'zip': '75001'},  # 达拉斯
        {'state': 'FL', 'zip': '33101'},  # 迈阿密
    ]
    
    @staticmethod
    def setup_chrome_options(headless: bool = True) -> webdriver.ChromeOptions:
        """配置Chrome浏览器选项
        
        Args:
            headless: 是否使用无头模式，默认为True
            
        Returns:
            配置好的ChromeOptions对象
            
        功能说明：
        1. 设置基础安全配置
        2. 配置无头模式
        3. 实现反爬虫策略
        4. 设置美国地区和语言
        5. 配置性能和隐私选项
        """
        try:
            options = webdriver.ChromeOptions()
            
            # 基本安全配置：禁用沙箱和共享内存使用
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # 无头模式配置：不显示浏览器界面，减少资源占用
            if headless:
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')
            
            # 反爬虫配置部分
            # 1. 随机选择User-Agent，模拟不同的浏览器特征
            options.add_argument(f'user-agent={random.choice(WebDriverConfig.USER_AGENTS)}')
            
            # 2. 禁用自动化标志，避免被检测为自动化工具
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            # 3. 模拟真实浏览器特征：设置窗口大小
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            
            # 4. 设置美国地区和英语语言
            options.add_argument('--lang=en-US')
            random_location = random.choice(WebDriverConfig.US_LOCATIONS)
            
            # 5. 性能和隐私设置：配置浏览器性能和隐私相关选项
            prefs = {
                # 禁用图片加载，提高性能
                'profile.managed_default_content_settings.images': 2,
                # 禁用JavaScript JIT，降低特征识别
                'webkit.webprefs.javascript_jit': False,
                # 禁用WebRTC，防止IP地址泄露
                'webrtc.ip_handling_policy': 'disable_non_proxied_udp',
                # 禁用密码管理弹窗
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False,
                # 设置美国地区位置服务
                'profile.default_content_setting_values.geolocation': 1,
                'profile.default_content_settings.geolocation': 1,
                'profile.content_settings.exceptions.geolocation[*]': 1,
                # 设置浏览器语言为英语
                'intl.accept_languages': 'en-US,en',
                # 禁用通知弹窗
                'profile.default_content_setting_values.notifications': 2
            }
            options.add_experimental_option('prefs', prefs)
            
            # 6. 添加美国地区的语言请求头
            options.add_argument(f'--accept-language=en-US,en;q=0.9')
            
            # 内存优化参数
            options.add_argument('--disable-extensions')  # 禁用扩展
            options.add_argument('--disable-popup-blocking')  # 禁用弹窗
            options.add_argument('--disable-infobars')  # 禁用信息栏
            options.add_argument('--js-flags=--expose-gc')  # 允许JavaScript垃圾回收
            options.add_argument('--disable-web-security')  # 禁用网页安全功能（谨慎使用）
            options.add_argument('--single-process')  # 单进程模式（大幅减少内存占用）
            options.add_argument('--disable-application-cache')  # 禁用应用缓存
            options.add_argument('--disable-default-apps')  # 禁用默认应用
            options.add_argument('--process-per-site')  # 每个站点一个进程
            options.add_argument('--aggressive-cache-discard')  # 积极丢弃缓存
            options.add_argument('--disable-component-extensions-with-background-pages')  # 禁用带后台页面的组件扩展
            options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')  # 禁用特定功能
            options.add_argument('--disable-site-isolation-trials')  # 禁用站点隔离试验
            
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
        
        Args:
            headless: 是否使用无头模式
            custom_options: 可选的自定义Chrome选项
            
        Returns:
            配置好的Chrome WebDriver实例
            
        功能说明：
        1. 创建WebDriver实例
        2. 注入反爬虫JavaScript代码
        3. 设置地理位置信息
        4. 配置页面加载超时
        """
        try:
            # 使用自定义选项或创建新的选项
            options = custom_options if custom_options else WebDriverConfig.setup_chrome_options(headless)
            driver = webdriver.Chrome(options=options)
            
            # 设置页面加载超时时间
            driver.set_page_load_timeout(30)
            
            # 注入反爬虫JavaScript代码：修改navigator和window对象，隐藏自动化特征
            random_location = random.choice(WebDriverConfig.US_LOCATIONS)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': f'''
                    // 隐藏Selenium WebDriver特征
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined
                    }});
                    // 模拟浏览器插件
                    Object.defineProperty(navigator, 'plugins', {{
                        get: () => [1, 2, 3, 4, 5]
                    }});
                    // 模拟Chrome浏览器环境
                    window.chrome = {{
                        runtime: {{}}
                    }};
                    // 设置美国英语语言环境
                    Object.defineProperty(navigator, 'language', {{
                        get: () => 'en-US'
                    }});
                    Object.defineProperty(navigator, 'languages', {{
                        get: () => ['en-US', 'en']
                    }});
                    // 设置美国东部时区
                    Object.defineProperty(Intl, 'DateTimeFormat', {{
                        get: () => function() {{
                            return {{ resolvedOptions: () => {{ return {{ timeZone: 'America/New_York' }} }} }}
                        }}
                    }});
                '''
            })
            
            # 设置地理位置为美国（默认纽约）
            params = {
                "latitude": 40.7128,  # 纽约市纬度
                "longitude": -74.0060,  # 纽约市经度
                "accuracy": 100  # 精确度（米）
            }
            driver.execute_cdp_cmd("Emulation.setGeolocationOverride", params)
            
            return driver
                
        except Exception as e:
            logging.error(f"ChromeDriver初始化失败: {str(e)}")
            raise 