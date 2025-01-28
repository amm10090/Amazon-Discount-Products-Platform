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
from typing import Dict, List, Optional, Union
from datetime import datetime
import colorama
from colorama import Fore, Back, Style

# 初始化colorama
colorama.init()

# 日志格式常量
LOG_INFO = f"{Fore.GREEN}[INFO]{Style.RESET_ALL}"
LOG_DEBUG = f"{Fore.BLUE}[DEBUG]{Style.RESET_ALL}"
LOG_WARNING = f"{Fore.YELLOW}[WARN]{Style.RESET_ALL}"
LOG_ERROR = f"{Fore.RED}[ERROR]{Style.RESET_ALL}"
LOG_SUCCESS = f"{Fore.GREEN}[✓]{Style.RESET_ALL}"

def log_info(message: str) -> None:
    """输出信息日志"""
    print(f"{LOG_INFO} {message}")

def log_debug(message: str) -> None:
    """输出调试日志"""
    print(f"{LOG_DEBUG} {message}")

def log_warning(message: str) -> None:
    """输出警告日志"""
    print(f"{LOG_WARNING} {message}")

def log_error(message: str) -> None:
    """输出错误日志"""
    print(f"{LOG_ERROR} {message}")

def log_success(message: str) -> None:
    """输出成功日志"""
    print(f"{LOG_SUCCESS} {message}")

def format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """生成进度条
    
    Args:
        current: 当前进度
        total: 总数
        width: 进度条宽度
        
    Returns:
        str: 格式化的进度条字符串
    """
    percentage = current / total
    filled = int(width * percentage)
    bar = '█' * filled + '░' * (width - filled)
    return f"{Fore.CYAN}[{bar}] {current}/{total} ({percentage*100:.1f}%){Style.RESET_ALL}"

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='Amazon优惠券商品爬虫')
    parser.add_argument('--max-items', type=int, default=100, help='要爬取的商品数量')
    parser.add_argument('--output', type=str, default='coupon_deals.json', help='输出文件路径')
    parser.add_argument('--format', type=str, choices=['txt', 'csv', 'json'], default='json', help='输出文件格式')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--timeout', type=int, default=30, help='无新商品超时时间(秒)')
    return parser.parse_args()

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
    
    # 执行CDP命令来修改webdriver状态
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
    })
    
    # 设置页面加载策略
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    
    return driver

def extract_coupon_info(card_element) -> Optional[Dict]:
    """
    从商品卡片中提取优惠券信息
    
    Args:
        card_element: Selenium WebElement对象，表示商品卡片元素
        
    Returns:
        Dict 包含优惠券类型、值和原始文本的字典，如果没有优惠券则返回None
    """
    try:
        # 首先检查卡片是否包含优惠券标记
        coupon_badge = card_element.find_element(By.CSS_SELECTOR, 'span[class*="CouponExperienceBadge-module__label"]')
        if not coupon_badge:
            return None
            
        log_info("调试 - 发现优惠券卡片")
        
        # 获取优惠券文本
        coupon_text = coupon_badge.text.strip()
        if not coupon_text:
            return None
            
        log_success("成功找到优惠券: " + coupon_text)
        
        # 获取完整的优惠券文本
        full_text = coupon_badge.find_element(By.XPATH, "./parent::div").text.strip()
        
        # 移除"节省"字样并清理文本
        clean_text = coupon_text.replace("节省", "").strip()
        
        # 解析优惠券类型和值
        if "%" in clean_text:
            coupon_type = "percentage"
            value = float(clean_text.replace("%", "").strip())
        else:
            coupon_type = "fixed"
            # 处理美元金额，移除"US$"或"$"
            value = float(clean_text.replace("US$", "").replace("$", "").strip())
            
        return {
            "type": coupon_type,
            "value": value,
            "raw_text": full_text,
            "discount_text": coupon_text
        }
                    
    except Exception as e:
        log_error("提取优惠券信息时出错: " + str(e))
        log_error("原始文本: " + (coupon_text if 'coupon_text' in locals() else 'N/A'))
    return None

def scroll_page(driver, scroll_count: int) -> bool:
    """
    智能滚动页面
    
    Args:
        driver: Selenium WebDriver对象
        scroll_count: 当前滚动次数
        
    Returns:
        bool: 滚动是否成功
    """
    try:
        # 获取当前窗口高度和页面总高度
        window_height = driver.execute_script("return window.innerHeight;")
        total_height = driver.execute_script("return document.body.scrollHeight;")
        current_position = driver.execute_script("return window.pageYOffset;")
        
        log_info("滚动 #" + str(scroll_count) + " - 窗口高度: " + str(window_height) + "px, 总高度: " + str(total_height) + "px, 当前位置: " + str(current_position) + "px")
        
        # 计算下一个滚动位置
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
        log_error("滚动出错: " + str(e))
        return False

def handle_connection_problem(driver) -> bool:
    """
    处理连接问题，尝试点击重试按钮
    
    Args:
        driver: Selenium WebDriver对象
        
    Returns:
        bool: 是否检测到并处理了连接问题
    """
    try:
        retry_button = driver.find_element(
            By.CSS_SELECTOR, 
            'input[data-testid="connection-problem-retry-button"]'
        )
        if retry_button and retry_button.is_displayed():
            log_warning("检测到连接问题，尝试重新加载...")
            retry_button.click()
            time.sleep(3)
            return True
    except Exception:
        pass
    return False

def crawl_coupon_deals(max_items: int = 100, timeout: int = 30, headless: bool = True) -> List[Dict]:
    """
    抓取带优惠券的商品信息
    
    Args:
        max_items: 最大抓取商品数量
        timeout: 无新商品超时时间（秒）
        headless: 是否使用无头模式
        
    Returns:
        List[Dict]: 包含商品ASIN和优惠券信息的列表
    """
    driver = setup_driver(headless=headless)
    results = []
    seen_asins = set()
    connection_retry_count = 0
    start_time = time.time()
    
    try:
        log_info("\n" + "="*50)
        log_info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取优惠券商品")
        log_info(f"目标数量: {max_items} 个商品")
        log_info(f"超时时间: {timeout} 秒")
        log_info(f"无头模式: {'是' if headless else '否'}")
        log_info("="*50 + "\n")
        
        # 访问优惠券商品页面
        driver.get('https://www.amazon.com/deals?bubble-id=deals-collection-coupons')
        time.sleep(5)  # 增加等待时间，确保页面完全加载
        
        # 初始化页面 - 定位viewport容器
        wait = WebDriverWait(driver, 10)
        try:
            viewport_container = wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    'div[data-testid="virtuoso-item-list"]'
                ))
            )
            log_success("成功找到viewport容器")
        except TimeoutException:
            log_warning("未找到viewport容器，尝试继续...")
            viewport_container = driver
        
        # 等待商品卡片加载
        try:
            wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'div[data-testid^="B"][class*="GridItem-module__container"]'
                ))
            )
            log_success("成功找到商品卡片")
        except TimeoutException:
            log_warning("未找到商品卡片，请检查选择器")
        
        scroll_count = 0
        last_success_time = time.time()
        no_new_items_count = 0
        
        while len(results) < max_items:
            scroll_count += 1
            log_info("\n" + "="*50)
            log_info(f"[{time.strftime('%H:%M:%S')}] === 第 {scroll_count} 次滚动 ===")
            
            # 检查是否长时间没有新商品
            if time.time() - last_success_time > timeout:
                log_warning(f"{timeout}秒内没有新商品，结束抓取")
                break
            
            # 检查连接问题
            if handle_connection_problem(driver):
                connection_retry_count += 1
                if connection_retry_count >= 5:
                    log_warning("连接问题持续存在，退出抓取")
                    break
                continue
            
            # 获取商品卡片
            try:
                product_cards = viewport_container.find_elements(
                    By.CSS_SELECTOR,
                    'div[data-testid^="B"][class*="GridItem-module__container"]'
                )
                
                log_info("找到 " + str(len(product_cards)) + " 个商品卡片")
                
                if not product_cards:
                    no_new_items_count += 1
                    if no_new_items_count >= 5:
                        log_warning("连续5次未找到商品卡片，退出抓取")
                        break
                    continue
                else:
                    no_new_items_count = 0
                
                previous_count = len(results)
                
                for card in product_cards:
                    if len(results) >= max_items:
                        break
                        
                    try:
                        # 获取ASIN
                        asin = card.get_attribute('data-testid')
                        
                        # 如果已经处理过该ASIN，跳过
                        if not asin or asin in seen_asins:
                            continue
                            
                        # 获取优惠券信息
                        coupon_info = extract_coupon_info(card)
                        
                        if coupon_info:
                            seen_asins.add(asin)
                            results.append({
                                "asin": asin,
                                "coupon": coupon_info,
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            if len(results) % 5 == 0:  # 每5个商品显示一次进度
                                log_info(format_progress_bar(len(results), max_items))
                                
                    except Exception as e:
                        log_error("处理商品卡片时出错: " + str(e))
                        continue
                
                new_items = len(results) - previous_count
                if new_items > 0:
                    log_info("本次滚动新增: " + str(new_items) + " 个商品")
                    last_success_time = time.time()
                
            except Exception as e:
                log_error("获取商品元素失败: " + str(e))
                continue
            
            # 滚动页面加载更多
            if not scroll_page(driver, scroll_count):
                time.sleep(1)
                continue
                
            time.sleep(random.uniform(1.5, 2.5))  # 增加随机等待时间
            
    except Exception as e:
        log_error("❌ 抓取过程出错: " + str(e))
    finally:
        driver.quit()
        
    # 统计信息
    end_time = time.time()
    duration = end_time - start_time
    log_info("\n" + "="*50)
    log_info("抓取任务统计信息:")
    log_info(f"总耗时: {duration:.1f} 秒")
    log_info(f"成功获取: {len(results)} 个商品")
    log_info(f"平均速度: {len(results)/duration:.1f} 个/秒")
    log_info("="*50)
        
    return results

def save_coupon_results(results: List[Dict], filename: str, format: str = 'json') -> None:
    """
    保存优惠券商品结果
    
    Args:
        results: 抓取结果列表
        filename: 输出文件名
        format: 输出格式（json/csv/txt）
    """
    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == 'json':
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'metadata': {
                    'total_count': len(results),
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'amazon_coupon_deals'
                },
                'items': results
            }, f, indent=2, ensure_ascii=False)
            
    elif format == 'csv':
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ASIN', 'Coupon Type', 'Coupon Value', 'Coupon Text', 'Timestamp'])
            for item in results:
                writer.writerow([
                    item['asin'],
                    item['coupon']['type'],
                    item['coupon']['value'],
                    item['coupon']['raw_text'],
                    item['timestamp']
                ])
                
    elif format == 'txt':
        with open(filename, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(f"{item['asin']}\t{item['coupon']['raw_text']}\n")
                
    log_success("结果已保存到: " + filename + " (" + format.upper() + "格式)")

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    # 开始抓取
    log_info("开始抓取Amazon优惠券商品...")
    results = crawl_coupon_deals(
        max_items=args.max_items,
        timeout=args.timeout,
        headless=not args.no_headless
    )
    
    # 确保输出文件扩展名与格式匹配
    output_file = args.output
    if not output_file.endswith(f'.{args.format}'):
        output_file = f"{output_file.rsplit('.', 1)[0]}.{args.format}"
    
    # 保存结果
    save_coupon_results(results, output_file, args.format)
    
    log_success("\n任务完成！共抓取 " + str(len(results)) + " 个优惠券商品") 