from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import logging
import os
from typing import Optional
import random

# 配置日志级别
logging.getLogger('selenium').setLevel(logging.WARNING)

class WebDriverConfig:
    """Chrome WebDriver配置管理类"""
    
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ]
    
    # 美国各州及其邮政编码范围
    US_LOCATIONS = [
        {'state': 'NY', 'zip': '10001'},  # 纽约
        {'state': 'CA', 'zip': '90001'},  # 洛杉矶
        {'state': 'IL', 'zip': '60601'},  # 芝加哥
        {'state': 'TX', 'zip': '75001'},  # 达拉斯
        {'state': 'FL', 'zip': '33101'},  # 迈阿密
    ]
    
    @staticmethod
    def setup_chrome_options(headless: bool = True) -> webdriver.ChromeOptions:
        """设置Chrome浏览器选项"""
        try:
            options = webdriver.ChromeOptions()
            
            # 基本安全配置
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # 无头模式配置
            if headless:
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')
            
            # 反爬虫配置
            # 1. 使用随机User-Agent
            options.add_argument(f'user-agent={random.choice(WebDriverConfig.USER_AGENTS)}')
            
            # 2. 禁用自动化标志
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            # 3. 模拟真实浏览器特征
            options.add_argument('--window-size=1920,1080')  # 设置正常窗口大小
            options.add_argument('--start-maximized')  # 最大化窗口
            
            # 4. 设置美国地区和英语语言
            options.add_argument('--lang=en-US')  # 设置语言为美式英语
            random_location = random.choice(WebDriverConfig.US_LOCATIONS)
            
            # 5. 性能和隐私设置
            prefs = {
                # 禁用图片加载
                'profile.managed_default_content_settings.images': 2,
                # 禁用JavaScript JIT
                'webkit.webprefs.javascript_jit': False,
                # 禁用WebRTC以防止IP泄露
                'webrtc.ip_handling_policy': 'disable_non_proxied_udp',
                # 禁用密码保存弹窗
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False,
                # 设置美国地区
                'profile.default_content_setting_values.geolocation': 1,  # 启用地理位置
                'profile.default_content_settings.geolocation': 1,
                'profile.content_settings.exceptions.geolocation[*]': 1,
                # 设置语言
                'intl.accept_languages': 'en-US,en',
                # 禁用通知
                'profile.default_content_setting_values.notifications': 2
            }
            options.add_experimental_option('prefs', prefs)
            
            # 6. 添加美国地区的请求头
            options.add_argument(f'--accept-language=en-US,en;q=0.9')
            
            return options
            
        except Exception as e:
            logging.error(f"Chrome选项配置失败: {str(e)}")
            raise
            
    @staticmethod
    def create_chrome_driver(
        headless: bool = True,
        custom_options: Optional[webdriver.ChromeOptions] = None
    ) -> webdriver.Chrome:
        """创建并配置Chrome WebDriver实例"""
        try:
            options = custom_options if custom_options else WebDriverConfig.setup_chrome_options(headless)
            driver = webdriver.Chrome(options=options)
            
            # 设置页面加载策略
            driver.set_page_load_timeout(30)  # 页面加载超时时间
            
            # 执行反爬虫JavaScript代码
            random_location = random.choice(WebDriverConfig.US_LOCATIONS)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': f'''
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined
                    }});
                    Object.defineProperty(navigator, 'plugins', {{
                        get: () => [1, 2, 3, 4, 5]
                    }});
                    window.chrome = {{
                        runtime: {{}}
                    }};
                    // 模拟美国地区
                    Object.defineProperty(navigator, 'language', {{
                        get: () => 'en-US'
                    }});
                    Object.defineProperty(navigator, 'languages', {{
                        get: () => ['en-US', 'en']
                    }});
                    // 模拟时区
                    Object.defineProperty(Intl, 'DateTimeFormat', {{
                        get: () => function() {{
                            return {{ resolvedOptions: () => {{ return {{ timeZone: 'America/New_York' }} }} }}
                        }}
                    }});
                '''
            })
            
            # 设置地理位置为美国
            params = {
                "latitude": 40.7128,  # 纽约市的经纬度（可以根据random_location动态调整）
                "longitude": -74.0060,
                "accuracy": 100
            }
            driver.execute_cdp_cmd("Emulation.setGeolocationOverride", params)
            
            return driver
                
        except Exception as e:
            logging.error(f"ChromeDriver初始化失败: {str(e)}")
            raise 