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
import asyncio
import aiofiles
import os

# 初始化colorama
colorama.init()

# 日志级别常量
LOG_LEVEL_ERROR = 0
LOG_LEVEL_WARNING = 1
LOG_LEVEL_INFO = 2
LOG_LEVEL_DEBUG = 3

# 从环境变量获取日志级别，默认为 INFO
DEBUG_LEVEL = int(os.getenv('DEBUG_LEVEL', LOG_LEVEL_INFO))

# 日志格式常量
LOG_INFO = f"{Fore.GREEN}[INFO]{Style.RESET_ALL}"
LOG_DEBUG = f"{Fore.BLUE}[DEBUG]{Style.RESET_ALL}"
LOG_WARNING = f"{Fore.YELLOW}[WARN]{Style.RESET_ALL}"
LOG_ERROR = f"{Fore.RED}[ERROR]{Style.RESET_ALL}"
LOG_SUCCESS = f"{Fore.GREEN}[✓]{Style.RESET_ALL}"

def should_log(level: int) -> bool:
    """检查是否应该输出指定级别的日志"""
    return DEBUG_LEVEL >= level

def log_info(message: str) -> None:
    """输出信息日志"""
    if should_log(LOG_LEVEL_INFO):
        print(f"{LOG_INFO} {message}")

def log_debug(message: str) -> None:
    """输出调试日志"""
    if should_log(LOG_LEVEL_DEBUG):
        print(f"{LOG_DEBUG} {message}")

def log_warning(message: str) -> None:
    """输出警告日志"""
    if should_log(LOG_LEVEL_WARNING):
        print(f"{LOG_WARNING} {message}")

def log_error(message: str) -> None:
    """输出错误日志"""
    if should_log(LOG_LEVEL_ERROR):
        print(f"{LOG_ERROR} {message}")

def log_success(message: str) -> None:
    """输出成功日志"""
    if should_log(LOG_LEVEL_INFO):
        print(f"{LOG_SUCCESS} {message}")

def log_progress(current: int, total: int, prefix: str = '') -> None:
    """输出进度信息"""
    if should_log(LOG_LEVEL_INFO):
        percentage = (current / total) * 100
        bar_length = 30
        filled_length = int(bar_length * current / total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        print(f"\r{prefix}进度: [{bar}] {current}/{total} ({percentage:.1f}%)", end='', flush=True)

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
        Dict: 包含优惠券类型和值的字典，如果没有优惠券则返回None
    """
    try:
        # 首先检查卡片是否包含优惠券标记
        coupon_badge = card_element.find_element(By.CSS_SELECTOR, 'span[class*="CouponExperienceBadge-module__label"]')
        if not coupon_badge:
            return None
            
        log_debug("发现优惠券卡片")
        
        # 获取优惠券文本
        coupon_text = coupon_badge.text.strip()
        if not coupon_text:
            return None
            
        log_success(f"成功找到优惠券: {coupon_text}")
        
        # 提取优惠券值和类型
        # 处理百分比优惠券 (例如: "节省 20%")
        if "%" in coupon_text:
            match = re.search(r'(\d+)%', coupon_text)
            if match:
                value = float(match.group(1))
                return {
                    "type": "percentage",
                    "value": value
                }
        # 处理固定金额优惠券 (例如: "节省 US$30")
        elif "US$" in coupon_text:
            match = re.search(r'US\$(\d+)', coupon_text)
            if match:
                value = float(match.group(1))
                return {
                    "type": "fixed",
                    "value": value
                }
            
        log_warning(f"无法解析优惠券格式: {coupon_text}")
        return None
        
    except Exception as e:
        log_error(f"提取优惠券信息时出错: {str(e)}")
        log_error(f"原始文本: {coupon_text if 'coupon_text' in locals() else 'N/A'}")
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

def check_no_results(driver) -> bool:
    """
    检查页面是否显示"没有找到匹配商品"的提示
    
    Args:
        driver: Selenium WebDriver对象
        
    Returns:
        bool: 如果页面显示无结果则返回True，否则返回False
    """
    try:
        # 检查是否存在无结果提示 - 使用多个选择器
        selectors = [
            "//div[contains(text(), \"We couldn't find a match\")]",
            "//div[contains(text(), '没有找到匹配')]",
            "//div[contains(@class, 'EmptyGrid-module')]",
            "//div[contains(@class, 'empty-grid')]"
        ]
        
        for selector in selectors:
            elements = driver.find_elements(By.XPATH, selector)
            if elements and any(elem.is_displayed() for elem in elements):
                log_warning(f"检测到无结果提示: {selector}")
                return True
        
        # 检查是否存在商品网格
        grid_selectors = [
            'div[data-testid="virtuoso-item-list"]',
            'div[class*="Grid-module"]',
            'div[class*="gridItemPad"]'
        ]
        
        for selector in grid_selectors:
            grid_container = driver.find_elements(By.CSS_SELECTOR, selector)
            if grid_container and any(elem.is_displayed() for elem in grid_container):
                # 检查网格内是否有商品
                items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid^="B"]')
                if not items:
                    log_warning("商品网格存在但没有商品项")
                    return True
                return False
        
        log_warning("未找到商品展示区域")
        return True
        
    except Exception as e:
        log_error(f"检查页面结果时出错: {str(e)}")
        # 出错时不要直接返回True，继续检查其他可能的情况
        try:
            # 使用更简单的方法再次检查
            no_results = driver.find_element(By.CSS_SELECTOR, '.a-section-empty')
            if no_results and no_results.is_displayed():
                log_warning("检测到空结果提示")
                return True
        except:
            pass
        
        # 如果所有检查都失败，返回False以允许程序继续
        return False

async def crawl_coupon_deals(
    max_items: int,
    timeout: int,
    headless: bool
) -> List[Dict]:
    """爬取优惠券商品数据"""
    try:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始爬取优惠券商品...")
        print(f"目标数量: {max_items} 个商品")
        print(f"超时时间: {timeout} 秒")
        print(f"无头模式: {'是' if headless else '否'}\n")
        
        driver = setup_driver(headless)
        products = []
        last_products_count = 0
        no_new_items_time = 0
        
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在访问Amazon Deals页面...")
            driver.get('https://www.amazon.com/deals?bubble-id=deals-collection-coupons')
            
            # 等待页面加载
            time.sleep(5)
            
            # 检查页面是否有商品
            if check_no_results(driver):
                log_warning("当前页面没有可用的优惠券商品，退出爬取")
                return []
                
            try:
                viewport = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR, 
                        'div[data-testid="virtuoso-item-list"]'
                    ))
                )
                log_success("成功找到viewport容器")
            except TimeoutException:
                log_warning("无法找到商品展示区域，退出爬取")
                return []
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取商品信息...")
            scroll_count = 0
            
            while len(products) < max_items:
                scroll_count += 1
                
                # 获取当前页面商品
                new_products = process_visible_products(driver)
                if new_products:
                    products.extend(new_products)
                    log_progress(len(products), max_items)
                
                # 检查是否有新商品
                if len(products) == last_products_count:
                    no_new_items_time += 1
                    if no_new_items_time >= 3:  # 连续3次没有新商品，等待更长时间
                        log_warning(f"连续{no_new_items_time}次未发现新商品，等待加载...")
                        time.sleep(2)  # 增加等待时间
                        
                        # 尝试触发更多加载
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 100);")
                        
                        if no_new_items_time >= timeout:  # 超时退出
                            log_warning(f"超过{timeout}秒未发现新商品，结束爬取")
                            break
                else:
                    no_new_items_time = 0  # 重置计数器
                    
                last_products_count = len(products)
                
                # 滚动页面
                if not scroll_page(driver, scroll_count):
                    log_error("滚动页面失败")
                    break
                    
                # 处理可能的连接问题
                if handle_connection_problem(driver):
                    continue
                    
                # 等待新内容加载
                time.sleep(1)
            
            print(f"\n\n[{datetime.now().strftime('%H:%M:%S')}] 商品获取完成")
            print(f"共获取 {len(products)} 个商品\n")
            
            return products[:max_items]
            
        finally:
            driver.quit()
            
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 错误: {str(e)}")
        return []

def process_visible_products(driver) -> List[Dict]:
    """处理当前可见的商品信息"""
    products = []
    cards = driver.find_elements(
        By.CSS_SELECTOR,
        'div[data-testid^="B"][class*="GridItem-module__container"]'
    )
    
    for card in cards:
        try:
            product = extract_product_info(card)
            if product:
                products.append(product)
        except Exception as e:
            continue
            
    return products

def extract_product_info(card) -> Optional[Dict]:
    """提取商品信息"""
    try:
        # 获取商品链接和ASIN
        link_element = card.find_element(By.CSS_SELECTOR, 'a[href*="/dp/"]')
        url = link_element.get_attribute('href')
        asin = card.get_attribute('data-testid')
        
        # 获取优惠券信息
        coupon = extract_coupon_info(card)
        if not coupon:
            return None
            
        return {
            'asin': asin,
            'url': url,
            'coupon': coupon
        }
        
    except Exception:
        return None

async def save_coupon_results(results: List[Dict], filename: str, format: str = 'json') -> None:
    """异步保存优惠券商品结果
    
    Args:
        results: 优惠券商品结果列表
        filename: 文件名
        format: 输出格式 (json/csv/txt)
    """
    # 确保基础目录存在
    base_dir = Path("data/coupon_deals")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"coupon_deals_{timestamp}.{format}"
    output_path = base_dir / filename
    
    if format == 'json':
        data = {
            'metadata': {
                'total_count': len(results),
                'timestamp': datetime.now().isoformat(),
                'source': 'amazon_coupon_deals'
            },
            'items': results
        }
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            
    elif format == 'csv':
        async with aiofiles.open(output_path, 'w', newline='', encoding='utf-8') as f:
            await f.write('ASIN,Coupon Type,Coupon Value,Timestamp\n')
            for item in results:
                coupon = item['coupon']
                await f.write(f"{item['asin']},{coupon['type']},{coupon['value']},{item['timestamp']}\n")
                
    elif format == 'txt':
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            for item in results:
                coupon = item['coupon']
                await f.write(f"{item['asin']}\t{coupon['type']}\t{coupon['value']}\n")
                
    log_success(f"结果已保存到: {output_path} ({format.upper()}格式)")

async def main():
    """异步主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Amazon优惠券商品爬虫')
    parser.add_argument('--max-items', type=int, default=100, help='要爬取的商品数量')
    parser.add_argument('--format', type=str, choices=['txt', 'csv', 'json'], default='json', help='输出文件格式')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--timeout', type=int, default=30, help='无新商品超时时间(秒)')
    args = parser.parse_args()
    
    # 开始爬取
    log_info("开始爬取Amazon优惠券商品...")
    results = await crawl_coupon_deals(
        max_items=args.max_items,
        timeout=args.timeout,
        headless=not args.no_headless
    )
    
    if results:
        # 保存结果
        await save_coupon_results(results, "coupon_deals", args.format)
        log_success(f"\n任务完成！共抓取 {len(results)} 个优惠券商品")
    else:
        log_warning("未获取到任何优惠券商品数据")

if __name__ == "__main__":
    asyncio.run(main()) 