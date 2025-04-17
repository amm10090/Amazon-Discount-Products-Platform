"""
优惠券信息多线程抓取模块
该模块负责从亚马逊商品页面抓取优惠券信息，使用多线程提高处理速度。

主要功能：
1. 按创建时间顺序抓取商品优惠券信息
2. 更新数据库记录
3. 只处理source为'coupon'的商品
4. 多线程并行处理提高效率
"""

import os
import sys
from datetime import datetime, UTC
from typing import Optional, Dict, Tuple, List
import time
import random
import argparse
import threading
import queue
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from tqdm import tqdm
import concurrent.futures
from dateutil import parser as date_parser

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, Offer, CouponHistory, get_db
from src.utils.webdriver_manager import WebDriverConfig
# 导入Loguru相关模块
from src.utils.log_config import get_logger, LogContext, track_performance, LogConfig

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='亚马逊商品优惠券信息多线程抓取工具')
    parser.add_argument('--batch-size', type=int, default=50, help='每批处理的商品数量')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--min-delay', type=float, default=2.0, help='最小请求延迟(秒)')
    parser.add_argument('--max-delay', type=float, default=4.0, help='最大请求延迟(秒)')
    parser.add_argument('--asin', type=str, help='要处理的单个商品ASIN')
    parser.add_argument('--asin-list', type=str, help='要处理的多个商品ASIN列表，用逗号分隔')
    parser.add_argument('--debug', action='store_true', help='启用调试模式，显示更详细的日志')
    parser.add_argument('--verbose', action='store_true', help='输出更多详细信息')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default=None, help='设置日志级别')
    parser.add_argument('--log-to-console', action='store_true', help='同时将日志输出到控制台')
    parser.add_argument('--threads', type=int, default=4, help='抓取线程数量')
    parser.add_argument('--update-interval', type=int, default=72, help='优惠券信息更新间隔(小时)，默认72小时')
    parser.add_argument('--force-update', action='store_true', help='强制更新所有商品，忽略更新间隔')
    return parser.parse_args()

# 初始化Loguru日志配置
def init_logger(log_level=None, log_to_console=False):
    """初始化Loguru日志配置
    
    Args:
        log_level: 日志级别，可以是 DEBUG, INFO, WARNING, ERROR
        log_to_console: 是否同时输出到控制台
        
    Returns:
        logger: 配置好的logger实例
    """
    # 使用项目根目录下的logs目录
    log_dir = Path(project_root) / os.getenv("APP_LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置日志级别
    if log_level:
        level = log_level.upper()
    else:
        level = "INFO"
    
    # 配置Loguru
    config = {
        "LOG_LEVEL": level,
        "JSON_LOGS": False,
        "LOG_PATH": str(log_dir),
        "LOG_FILE": "coupon_scraper_mt.log",
        "CONSOLE_LOGS": log_to_console,
        "ASYNC_LOGS": True,  # 启用异步日志记录提高性能
        "ROTATION": "10 MB",
        "RETENTION": "5 days"
    }
    
    # 应用配置
    LogConfig(config)
    
    # 返回当前模块的logger
    logger = get_logger("CouponScraperMT")
    logger.debug(f"日志已初始化: 级别={level}, 控制台输出={log_to_console}")
    return logger

# 全局日志记录器
logger = None  # 将在main函数中初始化

# 创建线程安全的统计数据类
class ThreadSafeStats:
    """线程安全的统计数据类"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._stats = {
            'start_time': time.time(),
            'end_time': None,
            'processed_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'updated_fields': {
                'coupon_type': 0,
                'coupon_value': 0,
            },
            'coupon_history': {
                'created': 0,
                'updated': 0
            }
        }
    
    def increment(self, key, subkey=None, amount=1):
        """增加计数并记录日志"""
        with self._lock:
            if subkey:
                self._stats[key][subkey] += amount
                logger.debug("统计计数增加: {}.{} += {}", key, subkey, amount)
            else:
                self._stats[key] += amount
                logger.debug("统计计数增加: {} += {}", key, amount)
    
    def set(self, key, value):
        """设置值"""
        with self._lock:
            self._stats[key] = value
            logger.debug("统计数据设置: {} = {}", key, value)
    
    def get(self, key=None):
        """获取统计数据"""
        with self._lock:
            if key:
                return self._stats.get(key)
            else:
                return self._stats.copy()

class CouponScraperWorker:
    """优惠券信息抓取工作线程类"""
    
    def __init__(self, worker_id: int, task_queue: queue.Queue, stats: ThreadSafeStats, 
                 headless: bool = True, min_delay: float = 2.0, max_delay: float = 4.0, 
                 debug: bool = False, verbose: bool = False):
        """
        初始化工作线程
        
        Args:
            worker_id: 工作线程ID
            task_queue: 任务队列
            stats: 线程安全的统计数据
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            debug: 是否启用调试模式
            verbose: 是否输出更多详细信息
        """
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.stats = stats
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.debug = debug
        self.verbose = verbose
        self.driver = None
        self.db_session = None
        
        # 已处理的商品集合，避免重复处理
        self._processed_asins = set()
         
    def _init_worker(self):
        """初始化工作线程环境"""
        # 为每个线程创建独立的数据库会话
        try:
            self.db_session = next(get_db())
            logger.debug("数据库会话初始化成功")
        except Exception as e:
            logger.exception("数据库会话初始化失败: {}", e)
            raise
        
        # 初始化WebDriver
        self._init_driver()
    
    def _init_driver(self):
        """初始化WebDriver"""
        if not self.driver:
            try:
                config = WebDriverConfig()
                self.driver = config.create_chrome_driver(headless=self.headless)
                
                # 设置全局超时参数
                self.driver.set_page_load_timeout(60)  # 页面加载超时
                self.driver.set_script_timeout(30)     # 脚本执行超时
                
                if self.debug:
                    logger.debug("WebDriver设置详情:")
                    logger.debug("  • 无头模式: {}", self.headless)
                    logger.debug("  • 页面加载超时: 60秒")
                    logger.debug("  • 脚本执行超时: 30秒")
                
                # 预热浏览器，访问简单页面确保WebDriver正常工作
                self.driver.get("about:blank")
                logger.info("WebDriver初始化完成")
            except Exception as e:
                logger.exception("WebDriver初始化异常: {}", e)
                # 尝试重新创建
                try:
                    if self.driver:
                        self.driver.quit()
                except:
                    pass
                config = WebDriverConfig()
                self.driver = config.create_chrome_driver(headless=self.headless)
                self.driver.set_page_load_timeout(60)
                self.driver.set_script_timeout(30)
                logger.info("WebDriver重新初始化完成")
            
    def _close_driver(self):
        """关闭WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning("关闭WebDriver异常: {}", e)
            finally:
                self.driver = None
                logger.info("WebDriver已关闭")
    
    def _extract_coupon_info(self) -> Tuple[Optional[str], Optional[float], Optional[datetime], Optional[str]]:
        """
        从页面提取优惠券信息
        
        Returns:
            Tuple[Optional[str], Optional[float], Optional[datetime], Optional[str]]: 
            (优惠券类型, 优惠券值, 有效期, 条款)
        """
        try:
            if self.debug:
                logger.debug("开始提取优惠券信息...")
            
            # 确保在函数顶部导入re模块
            import re
            
            # 增强的正则表达式模式，用于从文本中提取金额
            dollar_pattern = r'\$\s*(\d+(?:\.\d+)?)'
            percentage_pattern = r'(\d+)%'
            # 增强的正则表达式，匹配更多格式
            fixed_amount_pattern = r'(?:[\$\£\€])?(\d+(?:\.\d{1,2})?)\s*(?:off|discount|save|coupon)'
            percentage_amount_pattern = r'(?:save|get|take)?\s*(\d+(?:\.\d{1,2})?)\s*(?:%|percent|percentage)'
            
            # 用于匹配有效期的正则表达式
            date_patterns = [
                r'Coupon\s+Expiry\s+Date\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # Coupon Expiry Date: April 21, 2025
                r'(?:coupon|offer)\s+expires\s+(?:on)?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # coupon expires on April 21, 2025
                r'Valid\s+through\s+(\w+\s+\d{1,2},?\s+\d{4})',  # Valid through May 31, 2024
                r'Promotion\s+(?:ends|expires)\s+(?:on)?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # Promotion ends on April 21, 2025
                r'(?:coupon|offer)\s+expires\s+(?:on)?\s*(\d{1,2}/\d{1,2}/\d{2,4})'  # coupon expires on 4/21/25
            ]
            
            # 初始化结果
            coupon_type = None
            coupon_value = None
            expiration_date = None
            terms = None
            
            # 保存页面源代码以便调试
            if self.debug or self.verbose:
                page_source = self.driver.page_source
                # 检查页面源代码中是否包含关键词
                if 'Apply $' in page_source and 'coupon' in page_source:
                    logger.debug("页面源代码中检测到'Apply $ coupon'字样")
                    # 使用正则表达式在页面源码中查找优惠券金额
                    coupon_matches = re.findall(r'Apply\s+\$(\d+)\s+coupon', page_source)
                    if coupon_matches:
                        logger.debug("在页面源码中发现优惠券金额: ${}", coupon_matches[0])
                
                # 添加对百分比优惠券的检查
                if 'Apply' in page_source and '%' in page_source and 'coupon' in page_source:
                    logger.debug("页面源代码中检测到'Apply X% coupon'字样")
                    # 匹配百分比优惠券
                    percent_matches = re.findall(r'Apply\s+(\d+)%\s+coupon', page_source)
                    if percent_matches:
                        logger.debug("在页面源码中发现百分比优惠券: {}%", percent_matches[0])
                        # 设置百分比优惠券信息
                        coupon_type = "percentage"
                        coupon_value = float(percent_matches[0])
            
            # 尝试提取优惠券值和类型
            # 使用PHP代码中的XPath路径集合
            xpath_paths = [
                "//div[@id='promoPriceBlockMessage_feature_div']//span[@class='a-size-base a-color-success']",
                "//div[@id='promoPriceBlockMessage_feature_div']//div[@class='a-box a-alert-inline a-alert-inline-success a-text-bold']//div[@class='a-alert-content']",
                "//div[contains(@id, 'coupon')]//span[contains(@class, 'a-color-success')]",
                "//div[contains(@id, 'promotion')]//span[contains(@class, 'promotion-message')]",
                "//div[@id='buybox']//span[contains(text(), 'coupon')]",
                "//div[@id='promoPriceBlockMessage']//span[contains(@class, 'promotion')]",
                "//div[contains(@class, 'coupon-text')]",
                "//div[contains(@id, 'dealPrice')]//span[contains(text(), '%') or contains(text(), 'off')]",
                "//*[contains(text(), 'Apply $') and contains(text(), 'coupon')]",
                "//*[contains(text(), 'Apply') and contains(text(), '%') and contains(text(), 'coupon')]",
                "//span[contains(@class, 'couponBadge')]",
                "//div[contains(@class, 'promotions')]//span[contains(text(), 'coupon')]",
                "//div[contains(@class, 'applyPromotions')]",
                "//div[@id='corePrice_desktop']//span[contains(text(), 'coupon')]"
            ]
            
            # 尝试从所有XPath路径中提取优惠券信息
            for xpath in xpath_paths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    
                    for element in elements:
                        text = element.text.strip()
                        if not text:
                            continue
                            
                        if self.debug:
                            logger.debug("发现优惠券元素: '{}'，通过XPath: '{}'", text, xpath)
                        
                        # 尝试匹配固定金额优惠券
                        fixed_match = re.search(fixed_amount_pattern, text, re.IGNORECASE)
                        if fixed_match:
                            amount = float(fixed_match.group(1))
                            logger.debug("提取到固定金额优惠券: ${}", amount)
                            coupon_type = "fixed"
                            coupon_value = amount
                        
                        # 尝试匹配百分比优惠券
                        percent_match = re.search(percentage_amount_pattern, text, re.IGNORECASE)
                        if percent_match:
                            percentage = float(percent_match.group(1))
                            logger.debug("提取到百分比优惠券: {}%", percentage)
                            coupon_type = "percentage"
                            coupon_value = percentage
                        
                        # 尝试基本美元金额模式匹配
                        dollar_match = re.search(dollar_pattern, text)
                        if dollar_match and ('coupon' in text.lower() or 'off' in text.lower() or 'save' in text.lower()):
                            amount = float(dollar_match.group(1))
                            logger.debug("通过美元符号模式提取到优惠券金额: ${}", amount)
                            coupon_type = "fixed"
                            coupon_value = amount
                        
                        # 尝试基本百分比模式匹配
                        percent_basic_match = re.search(percentage_pattern, text)
                        if percent_basic_match and ('coupon' in text.lower() or 'off' in text.lower() or 'save' in text.lower()):
                            percentage = float(percent_basic_match.group(1))
                            logger.debug("通过百分比符号模式提取到优惠券百分比: {}%", percentage)
                            coupon_type = "percentage"
                            coupon_value = percentage
                except Exception as e:
                    if self.debug:
                        logger.debug("XPath '{}' 提取失败: {}", xpath, e)
            
            # 如果找到了优惠券信息，尝试点击Terms链接获取更多信息
            if coupon_type and coupon_value:
                try:
                    logger.debug("尝试查找Terms链接...")
                    
                    # 尝试查找Terms链接
                    terms_links = []
                    
                    # 方法1：使用文本内容查找
                    terms_xpath1 = "//a[contains(text(), 'Terms') or text()='Terms']"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath1))
                    
                    # 方法2：使用data-selector属性查找
                    terms_xpath2 = "//a[@data-selector='cxcwPopoverLink']"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath2))
                    
                    # 方法3：使用更通用的方式查找
                    terms_xpath3 = "//span[contains(@class, 'a-declarative') and contains(@data-a-modal, 'Terms')]//a"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath3))
                    
                    # 方法4：使用最通用的方式查找
                    terms_xpath4 = "//*[contains(@data-immersive-translate-walked, '4d8e3776')]//a"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath4))
                    
                    # 如果找到了Terms链接，点击打开模态框
                    for terms_link in terms_links:
                        if terms_link.is_displayed() and terms_link.is_enabled():
                            logger.info("找到并点击Terms链接")
                            
                            try:
                                # 使用JavaScript点击
                                self.driver.execute_script("arguments[0].click();", terms_link)
                                
                                # 等待模态框出现
                                time.sleep(2)
                                
                                # 尝试查找模态框内容
                                modal_content_xpath = "//div[contains(@class, 'a-modal-content') or @id='a-popover-content-1']"
                                modal_elements = self.driver.find_elements(By.XPATH, modal_content_xpath)
                                
                                if modal_elements:
                                    modal_content = modal_elements[0].text.strip()
                                    logger.debug("成功提取模态框内容: {}", modal_content[:50] + "..." if len(modal_content) > 50 else modal_content)
                                    
                                    # 保存完整条款
                                    terms = modal_content
                                    
                                    # 尝试提取有效期
                                    for pattern in date_patterns:
                                        date_match = re.search(pattern, modal_content, re.IGNORECASE)
                                        if date_match:
                                            date_str = date_match.group(1)
                                            try:
                                                expiration_date = date_parser.parse(date_str)
                                                logger.debug("从模态框提取到优惠券有效期: {}", expiration_date)
                                                break
                                            except Exception as e:
                                                logger.debug("解析日期失败: {} - {}", date_str, e)
                                
                                # 点击关闭按钮或按ESC关闭模态框
                                try:
                                    # 尝试查找关闭按钮
                                    close_buttons = self.driver.find_elements(By.XPATH, "//button[@data-action='a-popover-close']")
                                    if close_buttons:
                                        self.driver.execute_script("arguments[0].click();", close_buttons[0])
                                    else:
                                        # 如果找不到关闭按钮，尝试按ESC键
                                        from selenium.webdriver.common.keys import Keys
                                        from selenium.webdriver.common.action_chains import ActionChains
                                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                except Exception as e:
                                    logger.debug("关闭模态框失败，但继续处理: {}", e)
                                
                                break  # 成功处理了Terms链接，退出循环
                            except Exception as e:
                                logger.warning("点击Terms链接或提取模态框内容失败: {}", e)
                
                except Exception as e:
                    logger.warning("处理Terms链接时发生错误: {}", e)
            
            # 如果我们已经找到了优惠券信息，返回所有提取的数据
            if coupon_type and coupon_value is not None:
                logger.debug("返回提取的优惠券信息: 类型={}, 值={}, 有效期={}, 条款长度={}", 
                            coupon_type, coupon_value, 
                            expiration_date, len(terms) if terms else 0)
                return coupon_type, coupon_value, expiration_date, terms
            
            # 如果未能提取到优惠券信息，尝试其他方法
            # 检查优惠券特定元素 (保留原代码的方法)
            coupon_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-section .couponBadge")
            for element in coupon_elements:
                text = element.text.strip().lower()
                if self.debug:
                    logger.debug("发现优惠券徽章: '{}'", text)
                if "% off" in text or ("coupon" in text and "%" in text):
                    try:
                        # 提取百分比，处理格式如"40% off coupon"
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            logger.debug("从优惠券徽章提取到百分比优惠券: {}%", percentage)
                            return "percentage", percentage, expiration_date, terms
                    except (ValueError, IndexError) as e:
                        logger.warning("无法从优惠券徽章提取百分比: {}, 错误: {}", text, e)
                        
            # 检查a-color-success元素 (保留原代码的方法)
            success_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-color-success")
            for element in success_elements:
                text = element.text.strip()
                if self.debug:
                    logger.debug("发现a-color-success元素: '{}'", text)
                
                # 检查优惠券文本 - 添加对百分比优惠券的支持
                if "coupon" in text.lower():
                    # 检查是否有"apply $X coupon"文本
                    dollar_match = re.search(dollar_pattern, text)
                    if dollar_match:
                        amount = float(dollar_match.group(1))
                        logger.debug("从a-color-success元素提取到优惠券金额: ${}", amount)
                        return "fixed", amount, expiration_date, terms
                    
                    # 检查是否有"apply X% coupon"文本
                    percent_match = re.search(percentage_pattern, text)
                    if percent_match:
                        percentage = float(percent_match.group(1))
                        logger.debug("从a-color-success元素提取到优惠券百分比: {}%", percentage)
                        return "percentage", percentage, expiration_date, terms
            
            # 检查所有元素是否包含coupon关键词
            try:
                all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'coupon')]")
                for element in all_elements:
                    text = element.text.strip()
                    if not text:
                        continue
                        
                    if self.debug:
                        logger.debug("发现包含'coupon'的元素: '{}'", text)
                    
                    # 尝试所有匹配模式
                    fixed_match = re.search(fixed_amount_pattern, text, re.IGNORECASE)
                    if fixed_match:
                        amount = float(fixed_match.group(1))
                        logger.debug("从通用元素提取到固定金额优惠券: ${}", amount)
                        return "fixed", amount, expiration_date, terms
                    
                    percent_match = re.search(percentage_amount_pattern, text, re.IGNORECASE)
                    if percent_match:
                        percentage = float(percent_match.group(1))
                        logger.debug("从通用元素提取到百分比优惠券: {}%", percentage)
                        return "percentage", percentage, expiration_date, terms
                    
                    # 手动检查格式如"Apply 15% coupon"
                    if "apply" in text.lower() and "%" in text and "coupon" in text.lower():
                        try:
                            # 提取百分比数值
                            parts = text.split("%")[0].strip().split()
                            percentage_text = parts[-1]  # 取分割后最后一个元素作为百分比数值
                            if percentage_text.isdigit():
                                percentage = float(percentage_text)
                                logger.debug("从'Apply X% coupon'格式手动提取百分比: {}%", percentage)
                                return "percentage", percentage, expiration_date, terms
                        except Exception as e:
                            logger.debug("手动提取百分比失败: {}", e)
            except Exception as e:
                if self.debug:
                    logger.debug("通用元素搜索失败: {}", e)
                    
        except Exception as e:
            logger.warning("提取优惠券信息失败: {}", e)
            if self.debug:
                logger.exception("优惠券提取异常堆栈")
        
        if self.debug:
            logger.debug("未能提取到任何优惠券信息")
        return None, None, None, None
    
    def _update_product_coupon(self, product: Product, coupon_type: str, coupon_value: float, 
                              expiration_date: Optional[datetime] = None, terms: Optional[str] = None):
        """更新商品优惠券信息"""
        logger.info("更新商品 {} 的优惠券信息", product.asin)
        
        # 如果没有优惠券信息，删除商品记录（而不是跳过）
        if coupon_type is None:
            logger.info("商品 {} 没有优惠券信息，将从数据库中删除", product.asin)
            try:
                # 删除关联的优惠信息
                if product.offers:
                    for offer in product.offers:
                        self.db_session.delete(offer)
                    
                # 删除商品记录
                self.db_session.delete(product)
                self.db_session.commit()
                logger.info("成功从数据库删除商品: {}", product.asin)
            except Exception as e:
                self.db_session.rollback()
                logger.exception("删除商品记录失败: {}", e)
            return
            
        # 如果没有优惠信息记录，创建一个新的
        if not product.offers:
            offer = Offer(product_id=product.asin)
            product.offers.append(offer)
            logger.info("创建新的优惠信息记录")
        
        # 获取当前的offer
        offer = product.offers[0]
        updated_fields = []
        
        # 更新coupon_type
        if offer.coupon_type != coupon_type and (coupon_type is not None or offer.coupon_type is not None):
            updated_fields.append(f"优惠券类型: {offer.coupon_type} -> {coupon_type}")
            offer.coupon_type = coupon_type
            self.stats.increment('updated_fields', 'coupon_type')
        
        # 更新coupon_value
        if offer.coupon_value != coupon_value and (coupon_value is not None or offer.coupon_value is not None):
            updated_fields.append(f"优惠券金额: {offer.coupon_value} -> {coupon_value}")
            offer.coupon_value = coupon_value
            self.stats.increment('updated_fields', 'coupon_value')
        
        # 更新deal_type为Coupon
        if offer.coupon_type and offer.deal_type != "Coupon":
            offer.deal_type = "Coupon"
            product.deal_type = "Coupon"
            updated_fields.append(f"优惠类型: {offer.deal_type} -> Coupon")
        elif not offer.coupon_type and offer.deal_type == "Coupon":
            offer.deal_type = "None"
            product.deal_type = "None"
            updated_fields.append(f"优惠类型: Coupon -> None")
        
        # 更新时间戳
        offer.updated_at = datetime.now(UTC)
        product.updated_at = datetime.now(UTC)
        product.discount_updated_at = datetime.now(UTC)
        
        # 更新或创建coupon_history记录
        if coupon_type and coupon_value:
            # 查找最近的优惠券历史记录
            latest_history = self.db_session.query(CouponHistory).filter(
                CouponHistory.product_id == product.asin
            ).order_by(CouponHistory.created_at.desc()).first()
            
            if not latest_history or latest_history.coupon_type != coupon_type or latest_history.coupon_value != coupon_value:
                # 如果没有历史记录或者优惠券信息发生变化，创建新记录
                coupon_history = CouponHistory(
                    product_id=product.asin,
                    coupon_type=coupon_type,
                    coupon_value=coupon_value,
                    expiration_date=expiration_date,
                    terms=terms,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC)
                )
                self.db_session.add(coupon_history)
                logger.info("创建新的优惠券历史记录: 类型={}, 值={}, 有效期={}, 条款长度={}", 
                          coupon_type, coupon_value, 
                          expiration_date.strftime('%Y-%m-%d') if expiration_date else "无", 
                          len(terms) if terms else 0)
                self.stats.increment('coupon_history', 'created')
            else:
                # 即使优惠券类型和金额没变，也要更新有效期和条款
                if (expiration_date and latest_history.expiration_date != expiration_date) or (terms and latest_history.terms != terms):
                    if expiration_date:
                        latest_history.expiration_date = expiration_date
                    if terms:
                        latest_history.terms = terms
                    logger.info("更新优惠券历史记录的有效期和条款: 有效期={}, 条款长度={}", 
                              expiration_date.strftime('%Y-%m-%d') if expiration_date else "无", 
                              len(terms) if terms else 0)
                
                # 更新时间戳
                latest_history.updated_at = datetime.now(UTC)
                logger.debug("更新优惠券历史记录时间戳")
                self.stats.increment('coupon_history', 'updated')
        
        # 如果有字段更新，记录详情
        if updated_fields:
            logger.info("优惠券信息更新: {}", '; '.join(updated_fields))
        else:
            logger.debug("商品优惠券信息无变化")
        
    @track_performance  # 使用装饰器记录函数执行时间
    def process_product(self, product: Product) -> bool:
        """
        处理单个商品的优惠券信息
        
        Args:
            product: 商品对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            url = f"https://www.amazon.com/dp/{product.asin}?th=1"
            logger.info("开始处理商品: {}", url)
            
            # 添加页面加载超时处理
            try:
                self.driver.set_page_load_timeout(60)
                self.driver.set_script_timeout(30)
                
                try:
                    self.driver.get(url)
                except TimeoutException:
                    logger.warning("页面加载超时，尝试停止加载并继续处理")
                    try:
                        self.driver.execute_script("window.stop();")
                    except Exception as e:
                        logger.error("停止页面加载失败: {}", e)
                        return False
            except Exception as e:
                logger.error("访问页面时出错: {}", e)
                
                try:
                    self.driver.execute_script("return navigator.userAgent;")
                    logger.info("WebDriver仍然响应，继续处理")
                except:
                    logger.error("WebDriver无响应，放弃处理该商品")
                    return False
            
            # 随机等待1-3秒，模拟人类行为
            wait_time = random.uniform(1, 3)
            logger.debug("等待页面加载: {:.1f}秒", wait_time)
            time.sleep(wait_time)
            
            # 提取优惠券信息
            logger.debug("提取优惠券信息...")
            coupon_type, coupon_value, expiration_date, terms = self._extract_coupon_info()
            
            # 记录提取到的信息
            coupon_value_str = str(coupon_value) if coupon_value is not None else "无"
            exp_date_str = expiration_date.strftime('%Y-%m-%d') if expiration_date else "无"
            terms_str = f"长度: {len(terms)} 字符" if terms else "无"
            logger.info("优惠券信息提取结果", extra={
                "coupon_type": coupon_type, 
                "coupon_value": coupon_value_str,
                "expiration_date": exp_date_str,
                "terms": terms_str
            })
            
            # 更新数据库
            logger.debug("更新数据库...")
            self._update_product_coupon(product, coupon_type, coupon_value, expiration_date, terms)
            
            self.db_session.commit()
            logger.info("商品优惠券信息更新成功")
            return True
            
        except Exception as e:
            self.db_session.rollback()
            logger.exception("处理商品失败")
            return False
            
    def process_asin(self, asin: str) -> bool:
        """
        处理单个商品ASIN的优惠券信息
        
        Args:
            asin: 商品ASIN
            
        Returns:
            bool: 处理是否成功
        """
        # 检查是否已经处理过此商品
        if asin in self._processed_asins:
            logger.debug("商品已处理过: {}", asin)
            return True
        
        # 尝试从数据库获取商品
        logger.info("查询数据库中的商品信息")
        product = self.db_session.query(Product).filter(Product.asin == asin).first()
        
        # 如果数据库中不存在该商品，则创建一个新的记录
        if not product:
            logger.info("数据库中不存在商品，创建新记录 (source='coupon')")
            product = Product(asin=asin, created_at=datetime.now(UTC), source='coupon')
            self.db_session.add(product)
            try:
                logger.debug("刷新数据库以获取ID")
                self.db_session.flush()  # 刷新以获取ID，但不提交
            except Exception as e:
                logger.error("创建商品记录失败: {}", e)
                self.db_session.rollback()
                return False
        # 验证商品是否为'coupon'来源
        elif product.source != 'coupon':
            logger.warning("跳过非'coupon'来源的商品: {} (source={})", asin, product.source)
            return False
        
        # 处理商品优惠券信息
        success = self.process_product(product)
        
        # 如果处理成功，将商品ASIN添加到已处理集合中
        if success:
            self._processed_asins.add(asin)
            
        return success
    
    def run(self):
        """启动工作线程处理任务"""
        # 使用Loguru上下文管理
        with LogContext(worker_id=self.worker_id, component="WorkerThread"):
            # 初始化工作线程
            try:
                self._init_worker()
                logger.info("工作线程启动成功")
            except Exception as e:
                logger.exception("工作线程初始化失败")
                return
            
            try:
                while True:
                    # 从队列获取任务，如果队列为空则返回None
                    try:
                        asin = self.task_queue.get(block=False)
                    except queue.Empty:
                        logger.info("任务队列为空，退出")
                        break
                    
                    if asin is None:  # 接收到结束信号
                        logger.info("收到结束信号，退出")
                        self.task_queue.task_done()
                        break
                    
                    # 处理商品
                    logger.info("处理商品 ASIN: {}", asin)
                    
                    # 使用当前线程的会话处理ASIN
                    self.stats.increment('processed_count')
                    success = self.process_asin(asin)
                    
                    if success:
                        self.stats.increment('success_count')
                        logger.info("商品处理成功")
                        # 成功后等待随机时间
                        delay = random.uniform(self.min_delay, self.max_delay)
                        logger.debug("等待 {:.1f} 秒...", delay)
                        time.sleep(delay)
                    else:
                        self.stats.increment('failure_count')
                        logger.warning("商品处理失败")
                        # 失败后等待较长时间
                        delay = random.uniform(5, 10)
                        logger.debug("失败后等待 {:.1f} 秒...", delay)
                        time.sleep(delay)
                    
                    # 标记任务完成
                    self.task_queue.task_done()
            
            except Exception as e:
                logger.exception("工作线程发生异常")
            
            finally:
                # 关闭资源
                self._close_driver()
                if self.db_session:
                    self.db_session.close()
                logger.info("工作线程已关闭")

class CouponScraperMT:
    """多线程优惠券信息抓取器主类"""
    
    def __init__(self, num_threads: int = 4, batch_size: int = 50, headless: bool = True,
                 min_delay: float = 2.0, max_delay: float = 4.0, specific_asins: list = None,
                 debug: bool = False, verbose: bool = False, update_interval: int = 24,
                 force_update: bool = False, log_to_console: bool = False):
        """
        初始化多线程抓取器
        
        Args:
            num_threads: 线程数
            batch_size: 每批处理的商品数量
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            specific_asins: 指定要处理的商品ASIN列表
            debug: 是否启用调试模式
            verbose: 是否输出更多详细信息
            update_interval: 优惠券信息更新间隔(小时)，默认24小时
            force_update: 强制更新所有商品，忽略更新间隔
            log_to_console: 是否将日志输出到控制台
        """
        # 确保logger已初始化
        global logger
        if logger is None:
            logger = init_logger(
                log_level="DEBUG" if debug else "INFO",
                log_to_console=log_to_console
            )
            logger.info("在CouponScraperMT实例化过程中初始化了logger")
            
        self.num_threads = max(1, min(num_threads, 32))  # 限制线程数在1-32之间
        self.batch_size = batch_size
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.specific_asins = specific_asins
        self.debug = debug
        self.verbose = verbose
        self.update_interval = update_interval
        self.force_update = force_update
        
        # 初始化数据库会话
        from models.database import get_db
        self.db = next(get_db())
        
        # 初始化任务队列
        import queue
        self.task_queue = queue.Queue()
        
        # 初始化线程安全统计数据
        self.stats = ThreadSafeStats()
        
        # 工作线程列表
        self.workers = []
        
        # 添加完整的配置日志
        logger.info(
            "CouponScraperMT配置详情: 线程数={}, 批大小={}, 无头模式={}, 最小延迟={}, 最大延迟={}, "
            "调试模式={}, 详细模式={}, 更新间隔={}小时, 强制更新={}, 日志到控制台={}",
            self.num_threads, self.batch_size, self.headless, self.min_delay, self.max_delay,
            self.debug, self.verbose, self.update_interval, self.force_update, log_to_console
        )
    
    @track_performance
    def _populate_queue(self):
        """填充任务队列，使用智能更新策略"""
        # 处理特定的ASIN列表或从数据库获取商品
        if self.specific_asins:
            logger.info("将处理指定的 {} 个商品ASIN", len(self.specific_asins))
            asins_to_process = self.specific_asins
        else:
            logger.info("从数据库获取待处理商品列表，使用智能更新策略...")
            
            # 计算更新间隔的时间点
            from datetime import timedelta
            update_threshold = datetime.now(UTC) - timedelta(hours=self.update_interval)
            current_time = datetime.now(UTC)
            
            # 增加关于force_update的日志
            if self.force_update:
                logger.info("强制更新模式已启用 - 将忽略更新间隔检查")
            else:
                logger.info("智能更新模式 - 更新间隔设置为 {} 小时，更新阈值时间: {}", 
                          self.update_interval, update_threshold.strftime("%Y-%m-%d %H:%M:%S"))
            
            with LogContext(operation="db_query", component="QueuePopulation"):
                if self.force_update:
                    # 强制更新模式 - 忽略时间间隔限制
                    logger.info("强制更新模式 - 获取所有source为'coupon'的商品")
                    products = self.db.query(Product).filter(
                        Product.source == 'coupon'
                    ).order_by(Product.created_at).limit(self.batch_size).all()
                    logger.info("强制更新模式 - 获取到 {} 个商品", len(products))
                else:
                    # 智能更新模式 - 使用SQL查询根据优惠券历史记录筛选需要更新的商品
                    logger.info("智能更新模式 - 过滤需要更新的商品 (更新间隔: {}小时)", self.update_interval)
                    
                    # 查询符合以下条件之一的商品:
                    # 1. 从未抓取过优惠券信息的商品 (不在 CouponHistory 表中)
                    # 2. 最后更新时间超过了更新间隔
                    # 3. 优惠券已过期
                    
                    # 首先获取所有存在于coupon_history的商品ASIN
                    history_asins = self.db.query(CouponHistory.product_id).distinct().all()
                    history_asins = [asin[0] for asin in history_asins]
                    
                    # 获取没有历史记录的商品
                    new_products = self.db.query(Product).filter(
                        Product.source == 'coupon',
                        ~Product.asin.in_(history_asins) if history_asins else True
                    ).order_by(Product.created_at).limit(self.batch_size).all()
                    
                    # 如果新商品不足batch_size，再查询需要更新的商品
                    if len(new_products) < self.batch_size:
                        # 计算还需要多少商品
                        remaining = self.batch_size - len(new_products)
                        
                        # 获取有历史记录但需要更新的商品
                        # 子查询：获取每个商品最新的优惠券历史记录
                        from sqlalchemy import func
                        
                        # 查询每个商品最新的历史记录ID
                        latest_history_subq = self.db.query(
                            CouponHistory.product_id,
                            func.max(CouponHistory.id).label('latest_id')
                        ).group_by(CouponHistory.product_id).subquery()
                        
                        # 关联查询获取最新历史记录的详细信息
                        latest_histories = self.db.query(
                            CouponHistory
                        ).join(
                            latest_history_subq,
                            (CouponHistory.product_id == latest_history_subq.c.product_id) &
                            (CouponHistory.id == latest_history_subq.c.latest_id)
                        ).all()
                        
                        # 筛选需要更新的商品ASIN
                        update_asins = []
                        
                        for history in latest_histories:
                            # 需要更新的条件:
                            # 1. 最后更新时间超过了更新间隔
                            # 2. 优惠券已过期（如果有设置过期时间）
                            need_update = False
                            
                            # 检查最后更新时间
                            if history.updated_at:
                                # 为了解决时区问题，确保比较时两者都具有时区信息
                                if history.updated_at.tzinfo is None:
                                    # 如果数据库中的时间没有时区信息，假定为UTC
                                    history_updated_at = history.updated_at.replace(tzinfo=UTC)
                                else:
                                    history_updated_at = history.updated_at
                                
                                if history_updated_at < update_threshold:
                                    need_update = True
                                    logger.debug("商品 {} 需要更新：最后更新时间 {} 超过了更新间隔",
                                               history.product_id, history_updated_at)
                            
                            # 检查优惠券是否已过期
                            if history.expiration_date:
                                # 同样处理有效期的时区问题
                                if history.expiration_date.tzinfo is None:
                                    history_expiration_date = history.expiration_date.replace(tzinfo=UTC)
                                else:
                                    history_expiration_date = history.expiration_date
                                
                                if history_expiration_date < current_time:
                                    need_update = True
                                    logger.debug("商品 {} 需要更新：优惠券已于 {} 过期",
                                               history.product_id, history_expiration_date)
                            
                            if need_update:
                                update_asins.append(history.product_id)
                                
                                # 如果已收集足够的ASIN，提前退出循环
                                if len(update_asins) >= remaining:
                                    break
                        
                        # 查询这些需要更新的商品的完整信息
                        if update_asins:
                            update_products = self.db.query(Product).filter(
                                Product.asin.in_(update_asins),
                                Product.source == 'coupon'  # 确保只处理coupon来源的商品
                            ).all()
                            # 合并结果
                            products = new_products + update_products
                        else:
                            products = new_products
                    else:
                        # 如果新商品足够，直接使用
                        products = new_products
            
            asins_to_process = [p.asin for p in products]
            logger.info("获取到 {} 个待处理商品 (其中新商品: {})",
                       len(asins_to_process),
                       len(new_products) if 'new_products' in locals() else "全部")
        
        # 填充队列
        for asin in asins_to_process:
            self.task_queue.put(asin)
        
        logger.info("任务队列填充完成，共 {} 个任务", self.task_queue.qsize())
        return len(asins_to_process)
    
    def run(self):
        """运行抓取器"""
        self.stats.set('start_time', time.time())
        task_count = 0
        
        with LogContext(
            threads=self.num_threads,
            batch_size=self.batch_size,
            headless=self.headless,
            component="MainScraper"
        ):
            try:
                logger.info("=====================================================")
                logger.info("             开始多线程优惠券信息抓取任务")
                logger.info("=====================================================")
                logger.info("配置信息:")
                logger.info("- 线程数: {}", self.num_threads)
                logger.info("- 批处理大小: {}", self.batch_size)
                logger.info("- 更新间隔: {}小时", self.update_interval)
                logger.info("- 强制更新模式: {}", "启用" if self.force_update else "禁用")
                logger.info("- 无头模式: {}", "启用" if self.headless else "禁用")
                logger.info("- 调试模式: {}", "启用" if self.debug else "禁用")
                logger.info("=====================================================")
                
                # 填充任务队列
                task_count = self._populate_queue()
                if task_count == 0:
                    logger.warning("没有找到需要处理的商品，任务结束")
                    return
                
                # 创建并启动工作线程
                logger.info("启动 {} 个工作线程", self.num_threads)
                for i in range(self.num_threads):
                    worker = CouponScraperWorker(
                        worker_id=i+1,
                        task_queue=self.task_queue,
                        stats=self.stats,
                        headless=self.headless,
                        min_delay=self.min_delay,
                        max_delay=self.max_delay,
                        debug=self.debug,
                        verbose=self.verbose
                    )
                    
                    # 使用线程池启动工作线程
                    threading.Thread(
                        target=worker.run,
                        name=f"Worker-{i+1}",
                        daemon=True
                    ).start()
                
                # 等待所有任务完成
                logger.info("等待所有任务完成...")
                self.task_queue.join()
                logger.info("所有任务已完成")
                
            except KeyboardInterrupt:
                logger.info("收到中断信号，正在停止爬虫...")
            except Exception as e:
                logger.exception("抓取过程发生错误")
            
            finally:
                # 设置结束时间
                self.stats.set('end_time', time.time())
                
                # 输出任务统计信息
                stats = self.stats.get()
                duration = stats['end_time'] - stats['start_time']
                
                logger.info("=====================================================")
                logger.info("                  任务完成")
                logger.info("=====================================================")
                
                # 将统计信息作为消息内容直接打印，而不是使用extra参数
                logger.info(f"任务统计:")
                logger.info(f"线程数: {self.num_threads}")
                logger.info(f"总耗时: {duration:.1f}秒")
                logger.info(f"处理商品数: {stats['processed_count']}")
                logger.info(f"成功数: {stats['success_count']}")
                logger.info(f"失败数: {stats['failure_count']}")
                logger.info(f"成功率: {(stats['success_count']/stats['processed_count']*100) if stats['processed_count'] > 0 else 0:.1f}%")
                logger.info(f"平均速度: {stats['processed_count']/duration:.2f}个/秒" if duration > 0 else "平均速度: N/A")
                logger.info(f"更新的优惠券类型数量: {stats['updated_fields']['coupon_type']}")
                logger.info(f"更新的优惠券值数量: {stats['updated_fields']['coupon_value']}")
                logger.info(f"新建的优惠券历史记录数: {stats['coupon_history']['created']}")
                logger.info(f"更新的优惠券历史记录数: {stats['coupon_history']['updated']}")
                logger.info("=====================================================")
                
                # 关闭数据库连接
                self.db.close()

def main():
    """主函数"""
    args = parse_arguments()

    # 初始化日志
    global logger
    logger = init_logger(
        log_level=args.log_level or ('DEBUG' if args.debug else 'INFO'),
        log_to_console=args.log_to_console
    )
    
    # 处理命令行参数中的ASIN
    specific_asins = None
    if args.asin:
        specific_asins = [args.asin]
    elif args.asin_list:
        specific_asins = [asin.strip() for asin in args.asin_list.split(',')]

    # 初始化爬虫
    with LogContext(component="Startup"):
        logger.info("初始化多线程优惠券抓取器")
        scraper = CouponScraperMT(
            num_threads=args.threads,
            batch_size=args.batch_size,
            headless=not args.no_headless,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            specific_asins=specific_asins,
            debug=args.debug,
            verbose=args.verbose,
            update_interval=args.update_interval,
            force_update=args.force_update
        )
    
    try:
        # 输出调试信息
        if args.debug:
            logger.debug("===== 启动参数 =====", extra={
                "threads": args.threads,
                "batch_size": args.batch_size,
                "headless": not args.no_headless,
                "min_delay": args.min_delay,
                "max_delay": args.max_delay,
                "specific_asins": specific_asins,
                "debug": args.debug,
                "verbose": args.verbose,
                "log_level": args.log_level or ('DEBUG' if args.debug else 'INFO'),
                "update_interval": args.update_interval,
                "force_update": args.force_update
            })
        
        # 运行爬虫
        scraper.run()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止爬虫...")

if __name__ == "__main__":
    main() 