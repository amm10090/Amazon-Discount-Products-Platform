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
from typing import Dict, List, Optional, TypedDict
from datetime import datetime, UTC
import asyncio
import aiofiles
import os
import logging
import psutil
import sys
from dataclasses import dataclass

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
except ImportError:
    from ..utils.webdriver_manager import WebDriverConfig
    from ..utils.logger_manager import (
        log_info, log_debug, log_warning, 
        log_error, log_success, log_progress,
        log_section, set_log_config
    )
    from ..utils.config_loader import config_loader

@dataclass
class CrawlStats:
    """爬虫统计信息"""
    start_time: datetime
    total_seen: int = 0          # 总共看到的商品数
    unique_count: int = 0        # 唯一商品数
    duplicate_count: int = 0     # 重复商品数
    coupon_stats: dict = None    # 优惠券统计
    last_index: int = -1         # 最后处理的商品索引
    
    def __post_init__(self):
        # 确保start_time包含时区信息
        if self.start_time.tzinfo is None:
            self.start_time = self.start_time.replace(tzinfo=UTC)
            
        self.coupon_stats = {
            'percentage': {'count': 0, 'avg_value': 0.0},
            'fixed': {'count': 0, 'avg_value': 0.0}
        }
    
    @property
    def duplicate_rate(self) -> float:
        """计算重复率"""
        return (self.duplicate_count / self.total_seen * 100) if self.total_seen > 0 else 0
    
    def update_coupon_stats(self, coupon_type: str, value: float):
        """更新优惠券统计信息"""
        stats = self.coupon_stats[coupon_type]
        current_count = stats['count']
        current_avg = stats['avg_value']
        
        # 更新平均值
        stats['count'] += 1
        stats['avg_value'] = (current_avg * current_count + value) / (current_count + 1)

# 配置WebDriver Manager的日志
logging.getLogger('WDM').setLevel(logging.INFO)

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    crawler_config = config_loader.get_component_config('crawler')
    if crawler_config:
        set_log_config(
            log_to_file=True,
            log_dir=os.path.dirname(crawler_config.get('file', 'logs/crawler.log')),
            max_file_size=10 * 1024 * 1024,  # 10MB
            backup_count=5
        )
        
# 调用初始化
init_logger()

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='Amazon优惠券商品爬虫')
    parser.add_argument('--max-items', type=int, default=100, help='要爬取的商品数量')
    parser.add_argument('--format', type=str, choices=['txt', 'csv', 'json'], default='json', help='输出文件格式')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--timeout', type=int, default=30, help='无新商品超时时间(秒)')
    return parser.parse_args()

def setup_driver(headless=True):
    """设置Chrome浏览器选项"""
    try:
        return WebDriverConfig.create_chrome_driver(headless=headless)
    except Exception as e:
        log_error(f"ChromeDriver初始化失败: {str(e)}")
        raise

def scroll_page(driver, scroll_count: int, last_index: int) -> bool:
    """智能滚动页面，基于商品索引优化滚动
    
    Args:
        driver: Selenium WebDriver对象
        scroll_count: 当前滚动次数
        last_index: 最后处理的商品索引
        
    Returns:
        bool: 滚动是否成功
    """
    try:
        # 获取页面信息
        window_height = driver.execute_script("return window.innerHeight;")
        total_height = driver.execute_script("return document.body.scrollHeight;")
        current_position = driver.execute_script("return window.pageYOffset;")
        
        log_info(f"滚动 #{scroll_count} - 窗口高度: {window_height}px, 总高度: {total_height}px, 当前位置: {current_position}px")
        
        # 尝试找到下一个未处理的商品卡片
        try:
            next_card = driver.find_element(
                By.CSS_SELECTOR,
                f'div[data-test-index="{last_index + 1}"]'
            )
            if next_card:
                # 滚动到下一个商品的位置
                driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                    next_card
                )
                time.sleep(1)
                return True
        except:
            pass
        
        # 如果找不到下一个商品，使用默认滚动逻辑
        overlap = int(window_height * 0.2)  # 20%的重叠
        scroll_distance = window_height - overlap
        next_position = min(current_position + scroll_distance, total_height - window_height)
        
        # 检查是否接近底部
        if total_height - (current_position + window_height) < window_height:
            # 尝试触发加载更多
            load_more_button = driver.find_elements(
                By.CSS_SELECTOR,
                'button[data-testid="load-more-view-more-button"]'
            )
            if load_more_button and load_more_button[0].is_displayed():
                log_warning("检测到加载更多按钮，尝试点击...")
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", load_more_button[0])
                time.sleep(1)
                load_more_button[0].click()
                time.sleep(2)
                return True
            
            # 平滑滚动到底部
            driver.execute_script(f"window.scrollTo({{top: {total_height}, behavior: 'smooth'}})")
            time.sleep(1)
            
            # 检查是否有新内容加载
            new_height = driver.execute_script("return document.body.scrollHeight;")
            if new_height > total_height:
                log_debug("检测到新内容加载")
                time.sleep(1)
                return True
                
            return False
            
        # 执行平滑滚动
        driver.execute_script(f"window.scrollTo({{top: {next_position}, behavior: 'smooth'}})")
        time.sleep(0.5)
        
        # 等待内容加载
        time.sleep(1)
        
        # 检查是否有新内容
        new_height = driver.execute_script("return document.body.scrollHeight;")
        if new_height > total_height:
            log_debug("检测到新内容加载")
            time.sleep(1)
            
        return True
        
    except Exception as e:
        log_error(f"滚动页面时出错: {str(e)}")
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

def process_visible_products(
    driver, 
    seen_asins: set,
    stats: CrawlStats
) -> List[Dict]:
    """处理当前可见的商品信息，并更新统计数据"""
    products = []
    processed_in_view = set()
    
    try:
        # 等待商品卡片加载
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                'div[data-testid^="B"][class*="GridItem-module__container"]'
            ))
        )
        
        # 获取当前视图中的所有商品卡片
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            'div[data-testid^="B"][class*="GridItem-module__container"]'
        )
        
        # 按data-test-index排序处理商品
        indexed_cards = []
        for card in cards:
            if not card.is_displayed():
                continue
                
            try:
                index = int(card.get_attribute('data-test-index') or -1)
                if index > stats.last_index:  # 只处理未处理过的索引
                    indexed_cards.append((index, card))
            except ValueError:
                continue
        
        # 按索引排序
        indexed_cards.sort(key=lambda x: x[0])
        
        # 更新总处理数
        stats.total_seen += len(indexed_cards)
        
        for index, card in indexed_cards:
            try:
                # 获取ASIN
                asin = card.get_attribute('data-testid')
                if not asin or asin in processed_in_view:
                    continue
                    
                processed_in_view.add(asin)
                
                # 检查是否是重复的ASIN
                if asin in seen_asins:
                    stats.duplicate_count += 1
                    log_debug(f"跳过重复商品: {asin}")
                    continue
                
                # 确保元素在视图中完全可见
                if not is_element_fully_visible(driver, card):
                    log_debug(f"商品不完全可见，跳过: {asin}")
                    continue
                
                # 提取商品信息
                product = extract_product_info(card)
                if product:
                    seen_asins.add(asin)
                    stats.unique_count += 1
                    stats.last_index = index
                    
                    # 添加索引信息到商品数据
                    product['index'] = index
                    
                    # 更新优惠券统计
                    coupon_info = product['coupon']
                    stats.update_coupon_stats(
                        coupon_info['type'],
                        coupon_info['value']
                    )
                    
                    products.append(product)
                    log_debug(f"成功处理商品: {asin} (索引: {index})")
                    
            except Exception as e:
                log_error(f"处理商品卡片时出错: {str(e)}")
                continue
                
    except Exception as e:
        log_error(f"处理可见商品时出错: {str(e)}")
        
    return products

def is_element_fully_visible(driver, element) -> bool:
    """检查元素是否完全在视图中可见
    
    Args:
        driver: WebDriver实例
        element: 要检查的元素
        
    Returns:
        bool: 元素是否完全可见
    """
    try:
        # 获取元素和视窗的位置信息
        viewport_height = driver.execute_script("return window.innerHeight")
        element_top = element.location['y']
        element_bottom = element_top + element.size['height']
        current_scroll = driver.execute_script("return window.pageYOffset")
        
        # 检查元素是否完全在视图中
        is_visible = (
            element_top >= current_scroll and 
            element_bottom <= current_scroll + viewport_height
        )
        
        return is_visible
    except Exception:
        return False

def extract_coupon_info(card_element) -> Optional[Dict]:
    """
    从商品卡片中提取优惠券信息，支持多语言格式
    
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
        # 处理百分比优惠券 (例如: "节省 20%" 或 "Save 20%")
        percentage_match = re.search(r'(\d+)%', coupon_text)
        if percentage_match:
            value = float(percentage_match.group(1))
            return {
                "type": "percentage",
                "value": value
            }
            
        # 处理固定金额优惠券 (例如: "节省 $30" 或 "Save $30" 或 "Save US$30")
        # 移除所有空格，以便更好地匹配
        normalized_text = coupon_text.replace(" ", "")
        amount_match = re.search(r'(?:US)?\$(\d+(?:\.\d{2})?)', normalized_text)
        if amount_match:
            value = float(amount_match.group(1))
            return {
                "type": "fixed",
                "value": value
            }
            
        # 尝试匹配纯数字（针对某些特殊格式）
        number_match = re.search(r'(?:Save|节省)\s*(\d+(?:\.\d{2})?)', coupon_text)
        if number_match:
            value = float(number_match.group(1))
            # 如果文本中包含%，则认为是百分比优惠券
            if "%" in coupon_text:
                return {
                    "type": "percentage",
                    "value": value
                }
            else:
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

class CouponInfo(TypedDict):
    type: str
    value: float

class ProductInfo(TypedDict):
    asin: str
    url: str
    coupon: CouponInfo

async def save_coupon_results(
    results: List[ProductInfo],
    stats: CrawlStats,
    filename: str,
    format: str = 'json'
) -> None:
    """异步保存优惠券商品结果"""
    base_dir = Path("data/coupon_deals")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"coupon_deals_{timestamp}.{format}"
    output_path = base_dir / filename
    
    log_progress(f"正在保存结果到: {output_path}")
    
    try:
        if format == 'json':
            data = {
                'metadata': {
                    'timestamp': datetime.now(UTC).isoformat(),
                    'source': 'amazon_coupon_deals',
                    'stats': {
                        'total_processed': stats.total_seen,
                        'unique_items': stats.unique_count,
                        'duplicate_items': stats.duplicate_count,
                        'duplicate_rate': f"{stats.duplicate_rate:.1f}%",
                        'duration_seconds': (datetime.now(UTC) - stats.start_time).total_seconds(),
                        'coupon_stats': stats.coupon_stats
                    }
                },
                'items': results
            }
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                
        elif format == 'csv':
            async with aiofiles.open(output_path, 'w', newline='', encoding='utf-8') as f:
                await f.write('ASIN,URL,Coupon Type,Coupon Value\n')
                for item in results:
                    coupon_info = item['coupon']
                    line = f"{item['asin']},{item['url']},{coupon_info['type']},{coupon_info['value']}\n"
                    await f.write(line)
                    
        elif format == 'txt':
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                for item in results:
                    coupon_info = item['coupon']
                    line = f"{item['asin']}\t{item['url']}\t{coupon_info['type']}\t{coupon_info['value']}\n"
                    await f.write(line)
                    
        log_success(f"成功保存 {len(results)} 个商品数据")
        log_debug(f"文件路径: {output_path}")
        
    except Exception as e:
        log_error(f"保存结果时出错: {str(e)}")
        raise

async def crawl_coupon_deals(
    max_items: int,
    timeout: int,
    headless: bool
) -> tuple[List[Dict], CrawlStats]:
    """爬取优惠券商品数据"""
    try:
        log_section("启动优惠券商品爬虫")
        stats = CrawlStats(start_time=datetime.now())
        
        log_info("任务配置:")
        log_info(f"  • 目标数量: {max_items} 个商品")
        log_info(f"  • 超时时间: {timeout} 秒")
        log_info(f"  • 无头模式: {'是' if headless else '否'}")
        
        driver = setup_driver(headless)
        products = []
        seen_asins = set()
        last_products_count = 0
        no_new_items_count = 0
        consecutive_empty_scrolls = 0
        
        try:
            log_progress("正在访问Amazon Deals页面...")
            driver.get('https://www.amazon.com/deals?bubble-id=deals-collection-coupons')
            
            # 等待页面初始加载
            time.sleep(5)
            
            if check_no_results(driver):
                log_warning("当前页面没有可用的优惠券商品")
                return [], stats
            
            try:
                viewport = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR, 
                        'div[data-testid="virtuoso-item-list"]'
                    ))
                )
                log_success("成功找到商品展示区域")
            except TimeoutException:
                log_warning("无法找到商品展示区域")
                return [], stats
            
            log_section("开始采集商品数据")
            scroll_count = 0
            last_scroll_position = -1
            
            while len(products) < max_items:
                scroll_count += 1
                log_debug(f"执行第 {scroll_count} 次页面滚动")
                
                # 获取当前滚动位置
                current_position = driver.execute_script("return window.pageYOffset;")
                
                # 检查是否真的滚动了
                if current_position == last_scroll_position:
                    consecutive_empty_scrolls += 1
                    if consecutive_empty_scrolls >= 3:
                        log_warning("连续3次未能滚动，可能已到达页面底部")
                        break
                else:
                    consecutive_empty_scrolls = 0
                    last_scroll_position = current_position
                
                # 处理当前可见商品
                new_products = process_visible_products(driver, seen_asins, stats)
                if new_products:
                    remaining = max_items - len(products)
                    products.extend(new_products[:remaining])
                    
                    # 输出进度信息
                    log_progress(f"已采集 {len(products)}/{max_items} 个商品 ({len(products)/max_items*100:.1f}%)")
                    log_success(f"本次滚动新增 {len(new_products)} 个商品")
                    log_debug(
                        f"采集状态:\n"
                        f"  • 唯一商品数: {stats.unique_count}\n"
                        f"  • 重复率: {stats.duplicate_rate:.1f}%\n"
                        f"  • 当前索引: {stats.last_index}"
                    )
                    
                    if len(products) >= max_items:
                        break
                        
                    last_products_count = len(products)
                    no_new_items_count = 0
                else:
                    no_new_items_count += 1
                    if no_new_items_count >= 3:
                        log_warning(
                            f"连续 {no_new_items_count} 次未发现新商品\n"
                            f"  • 当前进度: {len(products)}/{max_items}\n"
                            f"  • 重复率: {stats.duplicate_rate:.1f}%\n"
                            f"  • 当前索引: {stats.last_index}"
                        )
                        
                        if no_new_items_count >= timeout:
                            log_warning(f"{timeout}秒内未发现新商品，结束爬取")
                            break
                
                # 滚动页面
                if not scroll_page(driver, scroll_count, stats.last_index):
                    log_warning("已到达页面底部，结束爬取")
                    break
                    
                # 处理可能的连接问题
                if handle_connection_problem(driver):
                    continue
                    
                # 动态调整等待时间
                if stats.duplicate_rate > 30:
                    time.sleep(1.5)  # 重复率高时，增加等待时间
                else:
                    time.sleep(0.5)
            
            # 输出最终统计信息
            log_section("爬取任务完成")
            duration = (datetime.now(UTC) - stats.start_time).total_seconds()
            
            log_success(f"任务统计:")
            log_success(f"  • 总耗时: {duration:.1f} 秒")
            log_success(f"  • 总处理商品: {stats.total_seen} 个")
            log_success(f"  • 成功采集: {stats.unique_count} 个")
            log_success(f"  • 重复商品: {stats.duplicate_count} 个")
            log_success(f"  • 重复率: {stats.duplicate_rate:.1f}%")
            log_success(f"  • 处理速度: {stats.total_seen/duration:.1f} 个/秒")
            
            # 输出优惠券统计
            log_section("优惠券统计")
            log_success(f"百分比优惠券:")
            log_success(f"  • 数量: {stats.coupon_stats['percentage']['count']} 个")
            log_success(f"  • 平均折扣: {stats.coupon_stats['percentage']['avg_value']:.1f}%")
            log_success(f"固定金额优惠券:")
            log_success(f"  • 数量: {stats.coupon_stats['fixed']['count']} 个")
            log_success(f"  • 平均优惠: ${stats.coupon_stats['fixed']['avg_value']:.2f}")
            
            return products[:max_items], stats
            
        finally:
            driver.quit()
            log_debug("浏览器资源已释放")
            
    except Exception as e:
        log_error(f"爬取过程中发生错误: {str(e)}")
        return [], stats

async def main():
    """异步主函数"""
    args = parse_arguments()
    
    log_section("启动Amazon优惠券爬虫")
    results, stats = await crawl_coupon_deals(
        max_items=args.max_items,
        timeout=args.timeout,
        headless=not args.no_headless
    )
    
    if results:
        await save_coupon_results(
            results,
            stats,
            "coupon_deals",
            args.format
        )
    else:
        log_warning("未获取到任何优惠券商品数据")

if __name__ == "__main__":
    asyncio.run(main()) 