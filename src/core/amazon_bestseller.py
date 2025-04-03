from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import random
import json
import re
import argparse
from pathlib import Path
import csv
import asyncio
from typing import List, Set
import aiofiles
import logging
import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from src.utils.webdriver_manager import WebDriverConfig
    from src.utils.logger_manager import (
        log_info, log_debug, log_warning, 
        log_error, log_success, log_progress,
        log_section, set_log_config
    )
    from src.utils.config_loader import config_loader
except ImportError as e:
    logging.error(f"导入错误: {str(e)}")
    raise

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    crawler_config = config_loader.get_component_config('crawler')
    if crawler_config:
        log_file = crawler_config.get('file', 'logs/crawler.log')
        set_log_config(
            log_level=crawler_config.get('level', 'INFO'),
            log_file=log_file,
            max_file_size=10 * 1024 * 1024,  # 10MB
            backup_count=5,
            use_colors=True
        )
        
        # 设置环境变量来控制日志级别
        os.environ['DEBUG_LEVEL'] = crawler_config.get('level', 'INFO')

# 调用初始化
init_logger()

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
    try:
        # 确保输出目录存在
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        log_debug(f"开始保存结果到文件: {filename} (格式: {format})")
        
        if format == 'txt':
            with open(filename, 'w', encoding='utf-8') as f:
                for asin in asins:
                    f.write(f"{asin}\n")
            log_success(f"结果已保存到: {filename} (TXT格式)")
        
        elif format == 'csv':
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['ASIN', 'Index'])
                for idx, asin in enumerate(asins, 1):
                    writer.writerow([asin, idx])
            log_success(f"结果已保存到: {filename} (CSV格式)")
        
        elif format == 'json':
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'metadata': {
                        'total_count': len(asins),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'source': 'amazon_deals'
                    },
                    'asins': list(asins)
                }, f, indent=2, ensure_ascii=False)
            log_success(f"结果已保存到: {filename} (JSON格式)")
            
        log_debug(f"保存完成，共写入 {len(asins)} 条记录")
        
    except Exception as e:
        log_error(f"保存结果时出错: {str(e)}")
        raise

def setup_driver(headless=True):
    """设置Chrome浏览器选项"""
    try:
        log_section("初始化Chrome浏览器")
        
        # 获取基础配置的options
        options = WebDriverConfig.setup_chrome_options(headless=headless)
        log_debug("Chrome基础选项配置完成")
        
        # 添加bestseller特有的配置
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'permissions.default.stylesheet': 2,
            'javascript.enabled': True
        }
        options.add_experimental_option('prefs', prefs)
        log_debug("Chrome特有选项配置完成")
        
        # 创建driver实例
        driver = WebDriverConfig.create_chrome_driver(headless=headless, custom_options=options)
        log_success("ChromeDriver创建成功")
        
        # 执行CDP命令
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
        })
        log_debug("User-Agent设置完成")
        
        return driver
        
    except Exception as e:
        log_error(f"ChromeDriver初始化失败: {str(e)}")
        WebDriverConfig.cleanup_chrome_processes()
        raise

def extract_asin_from_url(url):
    """从URL中提取ASIN"""
    try:
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if asin_match:
            log_debug(f"从URL提取ASIN成功: {asin_match.group(1)}")
            return asin_match.group(1)
        log_warning(f"无法从URL提取ASIN: {url}")
        return None
    except Exception as e:
        log_error(f"提取ASIN时出错: {str(e)}")
        return None

def handle_connection_problem(driver):
    """处理连接问题，点击Try again按钮"""
    try:
        retry_button = driver.find_element(By.CSS_SELECTOR, 'input[data-testid="connection-problem-retry-button"]')
        if retry_button and retry_button.is_displayed():
            log_warning("检测到连接问题，尝试重新加载...")
            retry_button.click()
            time.sleep(3)
            return True
    except Exception:
        # 静默处理异常，因为这是预期中可能发生的情况
        pass
    return False

def scroll_page(driver, scroll_count):
    """智能滚动页面"""
    try:
        # 获取页面信息
        window_height = driver.execute_script("return window.innerHeight;")
        total_height = driver.execute_script("return document.body.scrollHeight;")
        current_position = driver.execute_script("return window.pageYOffset;")
        
        log_debug(f"滚动状态 - 窗口高度: {window_height}px, 总高度: {total_height}px, 当前位置: {current_position}px")
        
        next_position = min(current_position + window_height, total_height - window_height)
        
        if total_height - (current_position + window_height) < window_height:
            log_debug("接近页面底部，执行特殊滚动")
            driver.execute_script(f"window.scrollTo({{top: {total_height}, behavior: 'smooth'}})")
            time.sleep(0.5)
            driver.execute_script(f"window.scrollTo({{top: {total_height - 200}, behavior: 'smooth'}})")
            time.sleep(0.5)
            driver.execute_script(f"window.scrollTo({{top: {total_height}, behavior: 'smooth'}})")
        else:
            log_debug(f"执行常规滚动到位置: {next_position}")
            driver.execute_script(f"window.scrollTo({{top: {next_position}, behavior: 'smooth'}})")
            time.sleep(0.5)
            driver.execute_script(f"window.scrollTo({{top: {next_position - 100}, behavior: 'smooth'}})")
            
        # 等待页面加载
        time.sleep(1)
        
        # 检查是否有新内容加载
        new_height = driver.execute_script("return document.body.scrollHeight;")
        if new_height > total_height:
            log_debug("检测到新内容加载")
            time.sleep(1)  # 额外等待新内容完全加载
            return True
            
        return True
    except Exception as e:
        log_error(f"滚动页面时出错: {str(e)}")
        return False

def check_view_more_button(driver):
    """检查并处理"View more deals"按钮"""
    try:
        view_more_button = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-testid="load-more-view-more-button"]'))
        )
        if view_more_button and view_more_button.is_displayed():
            log_info("发现'View more deals'按钮，正在点击...")
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", view_more_button)
            time.sleep(0.5)
            view_more_button.click()
            time.sleep(2)  # 等待按钮点击后的内容加载
            return True
    except Exception:
        pass  # 静默处理按钮未找到的情况
    return False

async def crawl_deals(max_items: int = 100, timeout: int = 30, headless: bool = True) -> List[str]:
    """
    异步爬取Amazon Deals页面的商品ASIN
    """
    start_time = time.time()
    driver = None
    try:
        log_section("开始Amazon Deals爬取任务")
        log_info(f"配置信息:")
        log_info(f"  • 目标数量: {max_items} 个商品")
        log_info(f"  • 超时时间: {timeout} 秒")
        log_info(f"  • 无头模式: {'是' if headless else '否'}")
        
        driver = setup_driver(headless=headless)
        all_asins = []
        seen_asins = set()
        no_new_items_count = 0
        connection_retry_count = 0
        
        log_progress("正在访问Amazon Deals页面...")
        driver.get('https://www.amazon.com/deals')
        time.sleep(3)
        
        log_progress("初始化页面...")
        wait = WebDriverWait(driver, 5)
        try:
            viewport_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-viewport-type="window"]'))
            )
            log_success("成功找到viewport容器")
        except TimeoutException:
            log_warning("未找到viewport容器，请检查页面结构")
            return all_asins
        
        scroll_count = 0
        last_success_time = time.time()
        
        while True:
            scroll_count += 1
            log_debug(f"执行第 {scroll_count} 次页面滚动")
            
            if time.time() - last_success_time > timeout:
                log_warning(f"{timeout}秒内未发现新商品，结束爬取")
                break
            
            if handle_connection_problem(driver):
                connection_retry_count += 1
                log_warning(f"网络连接问题，第 {connection_retry_count} 次重试")
                if connection_retry_count >= 5:
                    log_error("连接问题持续存在，终止爬取")
                    break
                continue
            else:
                connection_retry_count = 0
            
            if not scroll_page(driver, scroll_count):
                log_warning("页面滚动失败，尝试继续...")
                time.sleep(1)
                continue
            
            previous_count = len(all_asins)
            try:
                product_cards = viewport_container.find_elements(
                    By.CSS_SELECTOR, 
                    'div[data-testid^="B"][class*="GridItem-module__container"]'
                )
                log_debug(f"本次滚动找到 {len(product_cards)} 个商品卡片")
                
                for card in product_cards:
                    if len(all_asins) >= max_items:
                        log_success(f"已达到目标数量: {max_items} 个商品")
                        return all_asins
                    
                    try:
                        main_asin = card.get_attribute('data-testid')
                        if main_asin and main_asin not in seen_asins:
                            seen_asins.add(main_asin)
                            all_asins.append(main_asin)
                            if len(all_asins) % 10 == 0:
                                log_progress(f"已采集 {len(all_asins)}/{max_items} 个商品 ({(len(all_asins)/max_items*100):.1f}%)")
                    except Exception as e:
                        log_error(f"获取商品ASIN失败: {str(e)}")
                        continue
            except Exception as e:
                log_error(f"获取商品元素失败: {str(e)}")
                continue
            
            new_items = len(all_asins) - previous_count
            if new_items > 0:
                log_success(f"本次滚动新增 {new_items} 个商品")
                last_success_time = time.time()
                no_new_items_count = 0
            else:
                no_new_items_count += 1
                if check_view_more_button(driver):
                    log_success("发现并点击了'加载更多'按钮")
                    no_new_items_count = 0
                    continue
                    
                if no_new_items_count >= 3:
                    log_warning("连续3次未发现新商品，可能已到达页面底部")
                    break
            
            time.sleep(random.uniform(0.3, 0.5))
            
    except Exception as e:
        log_error(f"爬取过程中发生严重错误: {str(e)}")
    finally:
        if driver:
            driver.quit()
            log_debug("浏览器资源已释放")
        
        end_time = time.time()
        duration = end_time - start_time
        
        log_section("爬取任务完成")
        log_success(f"任务统计:")
        log_success(f"  • 总耗时: {duration:.1f} 秒")
        log_success(f"  • 成功获取: {len(all_asins)} 个商品")
        log_success(f"  • 平均速度: {len(all_asins)/duration:.1f} 个/秒")
    
    return all_asins

async def main():
    """异步主函数"""
    args = parse_arguments()
    
    log_section("启动Amazon Deals爬虫")
    asins = await crawl_deals(
        max_items=args.max_items,
        timeout=args.timeout,
        headless=not args.no_headless
    )
    
    output_file = args.output
    if not output_file.endswith(f'.{args.format}'):
        output_file = f"{output_file.rsplit('.', 1)[0]}.{args.format}"
    
    log_progress(f"正在保存结果到: {output_file}")
    save_results(asins, output_file, args.format)
    
    log_section("任务结束")
    log_success(f"成功采集 {len(asins)} 个唯一ASIN")

if __name__ == "__main__":
    asyncio.run(main())