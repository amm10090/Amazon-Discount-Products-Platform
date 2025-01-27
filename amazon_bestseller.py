from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import json
import re
import argparse
from pathlib import Path
import csv

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='Amazon Deals ASIN爬虫')
    parser.add_argument('--max-items', type=int, default=50, help='要爬取的商品数量')
    parser.add_argument('--output', type=str, default='asin_list.txt', help='输出文件路径')
    parser.add_argument('--format', type=str, choices=['txt', 'csv', 'json'], default='txt', help='输出文件格式')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--timeout', type=int, default=30, help='无新商品超时时间(秒)')
    return parser.parse_args()

def save_results(asins, filename, format='txt'):
    """保存结果到文件，支持多种格式"""
    # 确保输出目录存在
    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == 'txt':
        with open(filename, 'w', encoding='utf-8') as f:
            for asin in asins:  # 直接使用列表顺序
                f.write(f"{asin}\n")
        print(f"结果已保存到: {filename} (TXT格式)")
    
    elif format == 'csv':
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ASIN', 'Index'])  # 写入表头
            for idx, asin in enumerate(asins, 1):  # 保持原始顺序
                writer.writerow([asin, idx])
        print(f"结果已保存到: {filename} (CSV格式)")
    
    elif format == 'json':
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'metadata': {
                    'total_count': len(asins),
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'amazon_deals'
                },
                'asins': list(asins)  # 保持原始顺序
            }, f, indent=2, ensure_ascii=False)
        print(f"结果已保存到: {filename} (JSON格式)")

def setup_driver(headless=True):
    """设置Chrome浏览器选项"""
    options = webdriver.ChromeOptions()
    
    # 基本配置
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    if headless:
        options.add_argument('--headless=new')
    
    # 添加更多选项来模拟真实浏览器
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-infobars')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    options.add_argument('--ignore-certificate-errors')
    
    # 禁用图片加载
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
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # 执行CDP命令来修改webdriver状态
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
    })
    
    # 设置页面加载策略
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    
    return driver

def extract_asin_from_url(url):
    """从URL中提取ASIN"""
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if asin_match:
        return asin_match.group(1)
    return None

def handle_connection_problem(driver):
    """处理连接问题，点击Try again按钮"""
    try:
        # 查找Try again按钮
        retry_button = driver.find_element(By.CSS_SELECTOR, 'input[data-testid="connection-problem-retry-button"]')
        if retry_button and retry_button.is_displayed():
            print(f"[{time.strftime('%H:%M:%S')}] 检测到连接问题，尝试重新加载...")
            retry_button.click()
            time.sleep(3)  # 等待重新加载
            return True
    except Exception:
        pass
    return False

def scroll_page(driver, scroll_count):
    """智能滚动页面"""
    try:
        # 获取当前窗口高度和页面总高度
        window_height = driver.execute_script("return window.innerHeight;")
        total_height = driver.execute_script("return document.body.scrollHeight;")
        current_position = driver.execute_script("return window.pageYOffset;")
        
        print(f"[{time.strftime('%H:%M:%S')}] 窗口高度: {window_height}px, 总高度: {total_height}px, 当前位置: {current_position}px")
        
        # 计算下一个滚动位置（每次滚动一个窗口高度）
        next_position = min(current_position + window_height, total_height - window_height)
        
        # 如果已经接近底部，尝试触发加载更多
        if total_height - (current_position + window_height) < window_height:
            # 来回滚动以触发加载
            driver.execute_script(f"window.scrollTo({{top: {total_height}, behavior: 'smooth'}})")
            time.sleep(0.5)
            driver.execute_script(f"window.scrollTo({{top: {total_height - 200}, behavior: 'smooth'}})")
            time.sleep(0.5)
            driver.execute_script(f"window.scrollTo({{top: {total_height}, behavior: 'smooth'}})")
        else:
            # 正常滚动到下一个位置
            driver.execute_script(f"window.scrollTo({{top: {next_position}, behavior: 'smooth'}})")
            time.sleep(0.5)
            # 略微回滚以触发可能的加载
            driver.execute_script(f"window.scrollTo({{top: {next_position - 100}, behavior: 'smooth'}})")
            
        return True
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 滚动出错: {str(e)}")
        return False

def crawl_deals(max_items=100, timeout=30, headless=False):
    driver = setup_driver(headless=headless)
    all_asins = []  # 改用列表存储，保持顺序
    seen_asins = set()  # 用于去重检查
    page_height = 0
    no_new_items_count = 0
    connection_retry_count = 0
    start_time = time.time()
    
    try:
        print("\n" + "="*50)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始爬取任务")
        print(f"目标数量: {max_items} 个商品")
        print(f"超时时间: {timeout} 秒")
        print(f"无头模式: {'是' if headless else '否'}")
        print("="*50 + "\n")
        
        # 访问页面
        print(f"[{time.strftime('%H:%M:%S')}] 正在访问Amazon Deals页面...")
        driver.get('https://www.amazon.com/deals')
        time.sleep(3)
        
        # 初始化页面 - 定位viewport容器
        print(f"[{time.strftime('%H:%M:%S')}] 初始化页面...")
        wait = WebDriverWait(driver, 5)
        try:
            viewport_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-viewport-type="window"]'))
            )
            print(f"[{time.strftime('%H:%M:%S')}] 成功找到viewport容器")
        except TimeoutException:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 未找到viewport容器，请检查页面结构")
            return all_asins
        
        scroll_count = 0
        last_success_time = time.time()
        
        while True:
            scroll_count += 1
            print(f"\n[{time.strftime('%H:%M:%S')}] === 第 {scroll_count} 次滚动 ===")
            
            # 检查是否长时间没有新商品
            if time.time() - last_success_time > timeout:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ {timeout}秒内没有新商品，结束爬取")
                break
            
            # 检查连接问题
            if handle_connection_problem(driver):
                connection_retry_count += 1
                print(f"[{time.strftime('%H:%M:%S')}] 第 {connection_retry_count} 次重试连接")
                if connection_retry_count >= 5:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 连接问题持续存在，退出爬取")
                    break
                continue
            else:
                connection_retry_count = 0
            
            # 检查并点击"View more deals"按钮
            try:
                view_more_button = viewport_container.find_element(By.CSS_SELECTOR, 'button[data-testid="load-more-view-more-button"]')
                if view_more_button and view_more_button.is_displayed():
                    print(f"[{time.strftime('%H:%M:%S')}] 发现'View more deals'按钮，正在点击...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", view_more_button)
                    time.sleep(0.5)
                    view_more_button.click()
                    print(f"[{time.strftime('%H:%M:%S')}] 按钮点击成功，等待新内容加载...")
                    time.sleep(2)
                    continue
            except Exception:
                pass
            
            # 执行智能滚动
            if not scroll_page(driver, scroll_count):
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 滚动失败，尝试继续...")
                time.sleep(1)
                continue
            
            # 获取商品ASIN - 只从viewport容器内获取
            previous_count = len(all_asins)
            try:
                # 首先找到所有产品卡片容器，按照页面顺序
                product_cards = viewport_container.find_elements(
                    By.CSS_SELECTOR, 
                    'div[data-testid^="B"][class*="GridItem-module__container"]'
                )
                
                for card in product_cards:
                    if len(all_asins) >= max_items:
                        print(f"\n[{time.strftime('%H:%M:%S')}] ✓ 已达到目标数量: {max_items}")
                        return all_asins
                    
                    try:
                        # 获取产品卡片的data-testid属性（主ASIN）
                        main_asin = card.get_attribute('data-testid')
                        if main_asin and main_asin not in seen_asins:  # 使用seen_asins进行去重检查
                            seen_asins.add(main_asin)  # 添加到去重集合
                            all_asins.append(main_asin)  # 按顺序添加到列表
                            if len(all_asins) % 10 == 0:
                                print(f"[{time.strftime('%H:%M:%S')}] 进度: {len(all_asins)}/{max_items} ({(len(all_asins)/max_items*100):.1f}%)")
                    except Exception as e:
                        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 获取ASIN失败: {str(e)}")
                        continue
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 获取商品元素失败: {str(e)}")
                continue
            
            new_items = len(all_asins) - previous_count
            if new_items > 0:
                print(f"[{time.strftime('%H:%M:%S')}] 本次滚动新增: {new_items} 个商品")
                last_success_time = time.time()
            
            time.sleep(random.uniform(0.5, 1))
            
    except Exception as e:
        print(f"\n[{time.strftime('%H:%M:%S')}] ❌ 发生错误: {str(e)}")
    finally:
        driver.quit()
        
    # 统计信息
    end_time = time.time()
    duration = end_time - start_time
    print("\n" + "="*50)
    print("爬取任务统计信息:")
    print(f"总耗时: {duration:.1f} 秒")
    print(f"成功获取: {len(all_asins)} 个商品")
    print(f"平均速度: {len(all_asins)/duration:.1f} 个/秒")
    print("="*50)
    
    return all_asins

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    # 开始爬取
    print(f"开始爬取Amazon Deals页面...")
    asins = crawl_deals(
        max_items=args.max_items,
        timeout=args.timeout,
        headless=not args.no_headless  # 反转no-headless参数
    )
    
    # 确保输出文件扩展名与格式匹配
    output_file = args.output
    if not output_file.endswith(f'.{args.format}'):
        output_file = f"{output_file.rsplit('.', 1)[0]}.{args.format}"
    
    # 保存结果
    save_results(asins, output_file, args.format)
    
    print(f"\n任务完成！共找到 {len(asins)} 个唯一ASIN")