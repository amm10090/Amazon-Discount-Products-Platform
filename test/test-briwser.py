from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver(headless=False):  # 将默认值改为 False
    """设置Chrome浏览器选项"""
    options = webdriver.ChromeOptions()
    
    # 基本配置
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # 添加更多选项来模拟真实浏览器
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-infobars')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    options.add_argument('--ignore-certificate-errors')
    
    # 禁用图片加载以提高性能
    prefs = {
        'profile.managed_default_content_settings.images': 2,
        'permissions.default.stylesheet': 2,
        'javascript.enabled': True
    }
    options.add_experimental_option('prefs', prefs)
    
    # 设置user agent
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36')
    
    # 添加实验性选项
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 使用 ChromeDriverManager 自动下载和管理驱动
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    return driver

# 使用示例
try:
    # 创建浏览器实例
    driver = setup_driver(headless=False)
    
    # 访问网页
    driver.get('https://www.amazon.com/deals?bubble-id=deals-collection-coupons')
    
    # 等待用户手动关闭浏览器
    input("按回车键关闭浏览器...")
    
except Exception as e:
    print(f"发生错误: {e}")
finally:
    # 确保浏览器正确关闭
    if 'driver' in locals():
        driver.quit()