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
    parser.add_argument('--check-details', action='store_true', help='检查并抓取优惠券的到期日期和条款信息检查并抓取优惠券的到期日期和条款信息')
    return parser.parse_args()

# 初始化Loguru日志配置
def init_logger(log_level=None, log_to_console=False, file_use_colors=False):
    """初始化Loguru日志配置
    
    Args:
        log_level: 日志级别，可以是 DEBUG, INFO, WARNING, ERROR
        log_to_console: 是否同时输出到控制台
        file_use_colors: 是否在文件日志中使用颜色，默认False
        
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
    
    # 检查环境变量，判断是否应该禁用颜色
    force_no_color = False
    if (os.getenv("COLORTERM") == "0" or 
        os.getenv("DISCOUNT_SCRAPER_LOG_COLOR_OUTPUT") == "false" or
        os.getenv("LOG_COLORS") == "false" or
        os.getenv("FORCE_COLOR") == "0" or
        os.getenv("TERM") == "dumb"):
        force_no_color = True
        print("检测到环境变量设置，强制禁用日志颜色")
        file_use_colors = False  # 确保文件不使用颜色
    
    # 配置Loguru
    config = {
        "LOG_LEVEL": level,
        "JSON_LOGS": False,
        "LOG_PATH": str(log_dir),
        "LOG_FILE": f"coupon_scraper_mt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        "CONSOLE_LOGS": log_to_console,
        "ASYNC_LOGS": True,  # 启用异步日志记录提高性能
        "ROTATION": "10 MB",
        "RETENTION": "5 days",
        # 控制台日志格式（彩色）
        "CONSOLE_LOG_FORMAT": (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[name]}</cyan> | "
            "<level>{message}</level>"
        ),
        # 文件日志格式（无颜色）
        "FILE_LOG_FORMAT": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[name]} | "
            "{message}"
        ),
        "COLORIZE_CONSOLE": not force_no_color,   # 根据环境变量决定是否使用颜色
        "COLORIZE_FILE": file_use_colors      # 文件日志是否使用颜色，默认False
    }
    
    # 应用配置
    LogConfig(config)
    
    # 返回当前模块的logger
    logger = get_logger("CouponScraperMT")
    logger.debug(f"日志已初始化: 级别={level}, 控制台输出={log_to_console}, 文件日志颜色={file_use_colors}, 强制禁用颜色={force_no_color}")
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
            'captcha_count': 0,        # 遇到验证码的次数
            'refresh_success_count': 0, # 通过刷新成功解决验证码的次数
            'retry_count': 0,          # 重试的次数
            'delayed_count': 0,        # 因等待期而被延迟处理的次数
            'max_retry_exceeded': 0,   # 超过最大重试次数的任务数
            'updated_fields': {
                'coupon_type': 0,
                'coupon_value': 0,
            },
            'coupon_history': {
                'created': 0,
                'updated': 0,
                'updated_with_details': 0  # 添加新的子键，用于跟踪更新了有效期或条款的记录数
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
        
        # 重试计数器和时间戳，用于跟踪每个ASIN的重试次数和下次可处理的时间点
        self._retry_counter = {}
        # 最大重试次数
        self.max_retries = 3
         
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
                logger.debug("WebDriver已关闭")
            except Exception as e:
                logger.warning("关闭WebDriver时出错: {}", e)
            self.driver = None
            
    def _safe_refresh_page(self) -> bool:
        """
        安全地刷新当前页面
        
        Returns:
            bool: 刷新是否成功
        """
        try:
            logger.debug("尝试刷新页面...")
            self.driver.refresh()
            
            # 等待页面加载完成
            wait_time = random.uniform(3, 5)
            logger.debug("等待页面加载: {:.1f}秒", wait_time)
            time.sleep(wait_time)
            
            # 检查浏览器是否仍然响应
            try:
                self.driver.execute_script("return document.readyState")
                logger.debug("页面刷新成功")
                return True
            except Exception as e:
                logger.warning("检查页面状态失败: {}", e)
                return False
                
        except Exception as e:
            logger.warning("刷新页面时出错: {}", e)
            return False
            
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
            
            # 用于匹配有效期的正则表达式，增加更多模式
            date_patterns = [
                r'Coupon\s+Expiry\s+Date\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # Coupon Expiry Date: April 21, 2025
                r'Coupon\s+Expiry\s+Date\s+(\w+\s+\d{1,2},?\s+\d{4})',  # Coupon Expiry Date April 21, 2025
                r'(?:coupon|offer)\s+expires\s+(?:on)?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # coupon expires on April 21, 2025
                r'Valid\s+through\s+(\w+\s+\d{1,2},?\s+\d{4})',  # Valid through May 31, 2024
                r'Promotion\s+(?:ends|expires)\s+(?:on)?\s*(\w+\s+\d{1,2},?\s+\d{4})',  # Promotion ends on April 21, 2025
                r'(?:coupon|offer)\s+expires\s+(?:on)?\s*(\d{1,2}/\d{1,2}/\d{2,4})',  # coupon expires on 4/21/25
                r'Expir(?:y|ation)\s+Date\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})'  # Expiration Date: April 28, 2025
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
                    
                    # 方法4：查找coupon页面上的Terms链接
                    terms_xpath4 = "//span[contains(@class, 'a-truncate-full')]//a[contains(text(), 'Terms')]"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath4))
                    
                    # 方法5：查找任何可见的Terms链接
                    terms_xpath5 = "//a[contains(@class, 'a-link-normal') and (contains(text(), 'Terms') or contains(text(), 'terms'))]"
                    terms_links.extend(self.driver.find_elements(By.XPATH, terms_xpath5))
                    
                    # 如果找到了Terms链接，点击打开模态框
                    for terms_link in terms_links:
                        if terms_link.is_displayed() and terms_link.is_enabled():
                            logger.info("找到并点击Terms链接")
                            
                            try:
                                # 使用JavaScript点击
                                self.driver.execute_script("arguments[0].click();", terms_link)
                                
                                # 等待模态框出现 - 增加等待时间确保完全加载
                                time.sleep(2)
                                
                                # 尝试查找模态框内容 - 增加更多选择器以适应不同的弹窗结构
                                modal_selectors = [
                                    "//div[contains(@class, 'a-popover-content')]",
                                    "//div[@id='a-popover-content-1']",
                                    "//div[@id='a-popover-content-2']",
                                    "//div[@id='a-popover-content-3']",
                                    "//div[@id='a-popover-content-4']",
                                    "//div[contains(@id, 'promo_tncPage_')]",
                                    "//div[contains(@id, 'promo_tnc_popup_container_')]"
                                ]
                                
                                for selector in modal_selectors:
                                    modal_elements = self.driver.find_elements(By.XPATH, selector)
                                    if modal_elements and modal_elements[0].is_displayed():
                                        modal_content = modal_elements[0].text.strip()
                                        if modal_content:
                                            logger.debug("成功提取模态框内容，长度: {}", len(modal_content))
                                            if self.debug and len(modal_content) > 0:
                                                logger.debug("内容预览: {}", modal_content[:100] + "..." if len(modal_content) > 100 else modal_content)
                                            
                                            # 保存完整条款
                                            terms = modal_content
                                            
                                            # 尝试直接从弹窗中提取到期日期
                                            # 1. 寻找特定的到期日期元素
                                            expiry_elements = self.driver.find_elements(By.XPATH, 
                                                "//div[contains(@class, 'expiration') or contains(@id, 'expiration')]")
                                            
                                            if expiry_elements:
                                                for expiry_elem in expiry_elements:
                                                    expiry_text = expiry_elem.text.strip()
                                                    if expiry_text:
                                                        logger.debug("找到到期日期元素: {}", expiry_text)
                                                        # 尝试从文本中提取日期
                                                        for pattern in date_patterns:
                                                            date_match = re.search(pattern, expiry_text, re.IGNORECASE)
                                                            if date_match:
                                                                date_str = date_match.group(1)
                                                                try:
                                                                    expiration_date = date_parser.parse(date_str)
                                                                    logger.info("成功提取到期日期: {}", expiration_date.strftime('%Y-%m-%d'))
                                                                    break
                                                                except Exception as e:
                                                                    logger.debug("解析日期失败: {} - {}", date_str, e)
                                            
                                            # 2. 如果没有找到特定元素，从整个弹窗内容中提取日期
                                            if not expiration_date:
                                                for pattern in date_patterns:
                                                    date_match = re.search(pattern, modal_content, re.IGNORECASE)
                                                    if date_match:
                                                        date_str = date_match.group(1)
                                                        try:
                                                            expiration_date = date_parser.parse(date_str)
                                                            logger.info("从模态框内容提取到到期日期: {}", expiration_date.strftime('%Y-%m-%d'))
                                                            break
                                                        except Exception as e:
                                                            logger.debug("解析日期失败: {} - {}", date_str, e)
                                            
                                            # 成功提取内容，可以退出循环
                                            break
                                
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
                            expiration_date.strftime('%Y-%m-%d') if expiration_date else "None", 
                            len(terms) if terms else 0)
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
            
            create_new_record = False
            update_existing = False
            
            # 决定是创建新记录还是更新现有记录
            if not latest_history:
                # 如果没有历史记录，创建新记录
                create_new_record = True
                logger.info("没有现有的优惠券历史记录，将创建新记录")
            elif latest_history.coupon_type != coupon_type or latest_history.coupon_value != coupon_value:
                # 如果优惠券类型或金额有变化，创建新记录
                create_new_record = True
                logger.info("优惠券类型或金额有变化，将创建新记录")
            else:
                # 即使优惠券类型和金额没变，如果有新的到期日期或条款，也更新
                update_existing = True
                logger.info("优惠券类型和金额没变，检查是否需要更新到期日期和条款")
            
            # 创建新记录
            if create_new_record:
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
            # 更新现有记录
            elif update_existing:
                # 即使没有新的到期日期或条款，也强制更新字段
                has_updates = False
                
                # 当提取到到期日期时总是更新，即使为None也更新
                if expiration_date != latest_history.expiration_date:
                    latest_history.expiration_date = expiration_date
                    has_updates = True
                    updated_fields.append(f"优惠券有效期: {latest_history.expiration_date} -> {expiration_date}")
                    logger.info("更新优惠券历史记录的有效期: {}", 
                               expiration_date.strftime('%Y-%m-%d') if expiration_date else "无")
                
                # 当提取到条款时总是更新，即使为None也更新
                if terms != latest_history.terms:
                    latest_history.terms = terms
                    has_updates = True
                    logger.info("更新优惠券历史记录的条款，长度: {}", len(terms) if terms else 0)
                
                # 更新时间戳
                latest_history.updated_at = datetime.now(UTC)
                
                if has_updates:
                    logger.info("优惠券历史记录已更新")
                    self.stats.increment('coupon_history', 'updated_with_details')
                else:
                    logger.debug("优惠券历史记录时间戳已更新，但没有实质性变化")
                    self.stats.increment('coupon_history', 'updated')
        
        # 如果有字段更新，记录详情
        if updated_fields:
            logger.info("优惠券信息更新: {}", '; '.join(updated_fields))
        else:
            logger.debug("商品优惠券信息无变化")
        
        # 尝试提交更改
        try:
            self.db_session.commit()
            logger.debug("数据库更改已提交")
        except Exception as e:
            self.db_session.rollback()
            logger.exception("提交数据库更改失败: {}", e)
            raise
    
    def _is_captcha_page(self) -> bool:
        """
        检测当前页面是否为验证码人机验证页面
        
        Returns:
            bool: 如果是验证码页面返回True，否则返回False
        """
        try:
            # 检查页面源码中的特定特征
            page_source = self.driver.page_source.lower()
            
            # 检查典型的验证码页面文本
            captcha_texts = [
                "enter the characters you see below",
                "type the characters you see in this image",
                "sorry, we just need to make sure you're not a robot",
                "captcha",
                "bot check"
            ]
            
            # 如果页面源码中包含任何验证码特征文本，则认为是验证码页面
            for text in captcha_texts:
                if text in page_source:
                    logger.warning("检测到验证码页面 - 包含文本: '{}'", text)
                    return True
            
            # 检查是否存在验证码输入框
            captcha_inputs = self.driver.find_elements(By.ID, "captchacharacters")
            if captcha_inputs:
                logger.warning("检测到验证码页面 - 存在ID为'captchacharacters'的输入框")
                return True
            
            # 检查是否存在验证码图片
            captcha_images = self.driver.find_elements(By.XPATH, "//img[contains(@src, 'captcha')]")
            if captcha_images:
                logger.warning("检测到验证码页面 - 存在包含'captcha'的图片URL")
                return True
            
            # 检查页面标题
            title = self.driver.title.lower()
            if "robot" in title or "captcha" in title or "bot check" in title:
                logger.warning("检测到验证码页面 - 页面标题包含验证相关词汇")
                return True
                
            return False
            
        except Exception as e:
            logger.warning("检测验证码页面时出错: {}", e)
            # 发生错误时保守处理，返回False
            return False

    def _try_different_image(self) -> bool:
        """
        尝试在验证码页面点击"Try different image"链接
        
        Returns:
            bool: 是否成功点击了链接
        """
        try:
            logger.info("尝试点击'Try different image'链接...")
            
            # 尝试查找"Try different image"链接的多种方式
            selectors = [
                "//a[contains(text(), 'Try different image')]", 
                "//div[contains(@class, 'a-column') and contains(@class, 'a-span6')]//a[contains(text(), 'Try different image')]",
                "//div[contains(@class, 'a-column') and contains(@class, 'a-span6') and contains(@class, 'a-span-last')]//a",
                "//a[contains(@onclick, 'window.location.reload()')]"
            ]
            
            for selector in selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        logger.info("找到'Try different image'链接，尝试点击")
                        
                        try:
                            # 尝试使用JavaScript点击
                            self.driver.execute_script("arguments[0].click();", element)
                            
                            # 等待一段时间让页面重新加载验证码图片
                            wait_time = random.uniform(2, 4)
                            logger.debug("等待页面加载新验证码图片: {:.1f}秒", wait_time)
                            time.sleep(wait_time)
                            
                            logger.info("成功点击'Try different image'链接")
                            return True
                        except Exception as e:
                            logger.warning("点击'Try different image'链接时出错: {}", e)
            
            logger.warning("未找到'Try different image'链接或点击失败")
            return False
                
        except Exception as e:
            logger.warning("尝试点击'Try different image'链接时出错: {}", e)
            return False
    
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
            
            # 检查是否是验证码页面
            if self._is_captcha_page():
                # 首先尝试点击"Try different image"链接
                logger.warning("检测到验证码页面，尝试点击'Try different image'链接...")
                try_different_success = self._try_different_image()
                
                # 如果点击"Try different image"失败，再尝试刷新页面
                if not try_different_success:
                    logger.warning("点击'Try different image'链接失败，等待10秒后尝试刷新页面...")
                    time.sleep(10)  # 等待10秒
                    
                    # 尝试刷新页面
                    refresh_success = self._safe_refresh_page()
                    
                    if not refresh_success:
                        logger.warning("刷新页面失败，将商品 {} 放回队列尾部", product.asin)
                        self.stats.increment('captcha_count')
                        self.stats.increment('retry_count')
                        self.task_queue.put(product.asin)
                        return True
                
                # 再次检查是否还是验证码页面
                if self._is_captcha_page():
                    # 刷新后仍是验证码页面，更新验证码统计
                    self.stats.increment('captcha_count')
                    logger.warning("尝试后仍然是验证码页面，商品 {} 将放回队列尾部稍后重试", product.asin)
                    
                    # 获取当前ASIN的重试信息
                    retry_info = self._retry_counter.get(product.asin, (0, 0))
                    # 如果是旧格式（整数），则转换为元组格式
                    if isinstance(retry_info, int):
                        retry_count = retry_info + 1
                    else:
                        # 如果已经是元组格式，取出重试次数并增加
                        retry_count = retry_info[0] + 1
                    
                    # 如果重试次数超过最大值，则放弃
                    if retry_count > self.max_retries:
                        logger.error("商品 {} 已达到最大重试次数 {}，放弃处理", product.asin, self.max_retries)
                        self.stats.increment('max_retry_exceeded')
                        return False
                    
                    # 更新重试次数统计
                    self.stats.increment('retry_count')
                    
                    # 计算下次处理时间（当前时间 + 延迟）
                    delay = random.uniform(50, 70)  # 等待50-70秒
                    next_process_time = time.time() + delay
                    
                    # 创建一个包含时间戳的元组 (retry_count, next_process_time)
                    self._retry_counter[product.asin] = (retry_count, next_process_time)
                    
                    logger.info("商品 {} 将在 {:.0f} 秒后可再次处理", product.asin, delay)
                    
                    # 将任务重新加入队列，但不等待
                    self.task_queue.put(product.asin)
                    return True  # 返回True表示任务已重新加入队列
                else:
                    # 操作成功解决了验证码问题
                    logger.info("操作成功，验证码已消失，继续处理")
                    self.stats.increment('refresh_success_count')
            
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
            
            # 清除该ASIN的重试计数
            if product.asin in self._retry_counter:
                del self._retry_counter[product.asin]
                
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
        # 检查商品是否在等待重试的状态
        if asin in self._retry_counter:
            retry_info = self._retry_counter[asin]
            # 如果是元组格式 (retry_count, next_process_time)
            if isinstance(retry_info, tuple) and len(retry_info) == 2:
                retry_count, next_process_time = retry_info
                current_time = time.time()
                # 如果当前时间未到允许处理的时间点
                if current_time < next_process_time:
                    remaining_time = next_process_time - current_time
                    logger.info("商品 {} 尚在等待期，还需等待 {:.1f} 秒，重新放回队列", 
                              asin, remaining_time)
                    # 更新延迟处理的计数
                    self.stats.increment('delayed_count')
                    # 重新放回队列并跳过处理
                    self.task_queue.put(asin)
                    return True
        
        # 检查是否是首次处理此ASIN
        is_first_attempt = asin not in self._processed_asins
        
        # 将ASIN加入已处理集合，无论是否成功
        self._processed_asins.add(asin)
        
        # 仅在首次处理时增加processed_count计数
        if is_first_attempt:
            self.stats.increment('processed_count')
        
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
                    # 注意：processed_count统计已移至process_asin方法中
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
    """
    多线程优惠券信息抓取器主类
    
    本类专门用于处理数据库中source='coupon'来源的商品，抓取其优惠券详情。
    注意：非'coupon'来源的商品将被跳过处理。
    """
    
    def __init__(self, num_threads: int = 4, batch_size: int = 50, headless: bool = True,
                 min_delay: float = 2.0, max_delay: float = 4.0, specific_asins: list = None,
                 debug: bool = False, verbose: bool = False, update_interval: int = 24,
                 force_update: bool = False, log_to_console: bool = False, file_use_colors: bool = False):
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
            file_use_colors: 是否在文件日志中使用颜色，默认False
        """
        # 检查环境变量，判断是否应该禁用颜色
        force_no_color = False
        if (os.getenv("COLORTERM") == "0" or 
            os.getenv("DISCOUNT_SCRAPER_LOG_COLOR_OUTPUT") == "false" or
            os.getenv("LOG_COLORS") == "false" or
            os.getenv("FORCE_COLOR") == "0" or
            os.getenv("TERM") == "dumb"):
            force_no_color = True
            file_use_colors = False  # 确保文件不使用颜色
            # 只打印一次，避免重复输出
            
        # 确保logger已初始化
        global logger
        if logger is None:
            print("检测到环境变量设置，强制禁用日志颜色") if force_no_color else None
            log_level = "DEBUG" if debug else "INFO"
            # 创建配置字典
            log_config = {
                "LOG_LEVEL": log_level,
                "JSON_LOGS": False,
                "LOG_PATH": str(Path(project_root) / os.getenv("APP_LOG_DIR", "logs")),
                "LOG_FILE": f"coupon_scraper_mt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                "CONSOLE_LOGS": log_to_console,
                "ASYNC_LOGS": True,
                "ROTATION": "10 MB",
                "RETENTION": "5 days",
                "CONSOLE_LOG_FORMAT": (
                    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                    "<level>{level: <8}</level> | "
                    "<cyan>{extra[name]}</cyan> | "
                    "<level>{message}</level>"
                ),
                "FILE_LOG_FORMAT": (
                    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                    "{level: <8} | "
                    "{extra[name]} | "
                    "{message}"
                ),
                "COLORIZE_CONSOLE": not force_no_color,   # 根据环境变量决定是否使用颜色
                "COLORIZE_FILE": file_use_colors  # 文件日志是否使用颜色，默认False
            }
            
            # 应用配置
            LogConfig(log_config)
            logger = get_logger("CouponScraperMT")
            logger.info("在CouponScraperMT实例化过程中初始化了logger，级别: {}，控制台输出: {}，文件日志颜色: {}，强制禁用颜色: {}", 
                       log_level, log_to_console, file_use_colors, force_no_color)
            
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
            "调试模式={}, 详细模式={}, 更新间隔={}小时, 强制更新={}, 日志到控制台={}, 文件日志颜色={}",
            self.num_threads, self.batch_size, self.headless, self.min_delay, self.max_delay,
            self.debug, self.verbose, self.update_interval, self.force_update, log_to_console, file_use_colors
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
            one_day_future = current_time + timedelta(days=1)  # 一天后的时间点
            
            # 增加关于force_update的日志
            if self.force_update:
                logger.info("强制更新模式已启用 - 将忽略更新间隔检查")
            else:
                logger.info("智能更新模式 - 更新间隔设置为 {} 小时，更新阈值时间: {}", 
                          self.update_interval, update_threshold.strftime("%Y-%m-%d %H:%M:%S"))
            
            with LogContext(operation="db_query", component="QueuePopulation"):
                # 优先处理的商品列表
                priority_products = []
                
                # 高优先级条件1: 查找优惠券没有有效期或条款的商品
                # 获取所有至少有一个优惠券历史记录的商品ASIN
                history_asins_query = self.db.query(CouponHistory.product_id).distinct()
                history_asins = [asin[0] for asin in history_asins_query.all()]
                
                # 查找在products表中存在，但在最新的优惠券记录中没有expiration_date或terms的商品
                logger.info("查找优惠券缺失有效期或条款的商品")
                missing_info_products = []
                for asin in history_asins:
                    # 获取该商品最新的优惠券记录
                    latest_coupon = self.db.query(CouponHistory).filter(
                        CouponHistory.product_id == asin
                    ).order_by(CouponHistory.created_at.desc()).first()
                    
                    if latest_coupon and (latest_coupon.expiration_date is None or latest_coupon.terms is None):
                        # 查找对应的产品
                        product = self.db.query(Product).filter(Product.asin == asin).first()
                        if product:
                            missing_info_products.append(product)
                
                logger.info("找到 {} 个优惠券缺失有效期或条款的商品", len(missing_info_products))
                priority_products.extend(missing_info_products)
                
                # 高优先级条件2: 查找优惠券即将到期（一天内）或已过期的商品
                logger.info("查找优惠券即将到期或已过期的商品")
                expiring_products_query = self.db.query(Product).join(
                    CouponHistory, Product.asin == CouponHistory.product_id
                ).filter(
                    # 有效期不为空
                    CouponHistory.expiration_date.isnot(None),
                    # 已过期或一天内到期
                    or_(
                        CouponHistory.expiration_date <= current_time,  # 已过期
                        CouponHistory.expiration_date <= one_day_future  # 一天内到期
                    )
                ).distinct()
                
                expiring_products = expiring_products_query.all()
                logger.info("找到 {} 个优惠券即将到期或已过期的商品", len(expiring_products))
                
                # 添加到优先队列，避免重复
                for product in expiring_products:
                    if product.asin not in [p.asin for p in priority_products]:
                        priority_products.append(product)
                
                # 正常的产品选择逻辑，如果优先队列不足批处理大小
                remaining_slots = self.batch_size - len(priority_products)
                regular_products = []
                
                if remaining_slots > 0:
                    if self.force_update:
                        # 强制更新模式 - 获取所有source为'coupon'的商品
                        logger.info("强制更新模式 - 获取所有source为'coupon'的商品")
                        products_query = self.db.query(Product).filter(
                            Product.source == 'coupon'  # 重要：仅处理coupon来源的商品
                        ).order_by(Product.created_at)
                        
                        # 排除已在优先队列中的商品
                        priority_asins = [p.asin for p in priority_products]
                        products_query = products_query.filter(~Product.asin.in_(priority_asins))
                        
                        regular_products = products_query.limit(remaining_slots).all()
                        logger.info("强制更新模式 - 获取到 {} 个常规商品", len(regular_products))
                    else:
                        # 智能更新模式 - 使用改进的查询逻辑
                        logger.info("智能更新模式 - 过滤需要更新的商品 (更新间隔: {}小时)", self.update_interval)
                        
                        # 修改查询逻辑: 查询所有source='coupon'的商品
                        all_coupon_products = self.db.query(Product).filter(
                            Product.source == 'coupon'
                        ).all()
                        
                        # 筛选需要更新的商品
                        products_to_update = []
                        
                        # 排除已在优先队列中的商品
                        priority_asins = [p.asin for p in priority_products]
                        
                        # 处理没有历史记录的商品（直接添加）
                        new_products = [p for p in all_coupon_products if p.asin not in history_asins and p.asin not in priority_asins]
                        logger.info("找到 {} 个没有历史记录的新商品", len(new_products))
                        products_to_update.extend(new_products)
                        
                        # 如果新商品数量不足剩余槽位，再处理有历史记录但需要更新的商品
                        if len(products_to_update) < remaining_slots and history_asins:
                            # 使用updated_at或discount_updated_at字段查询需要更新的商品（满足任一条件）
                            from sqlalchemy import or_
                            products_need_update = self.db.query(Product).filter(
                                Product.source == 'coupon',
                                Product.asin.in_(history_asins),
                                ~Product.asin.in_(priority_asins),  # 排除优先队列中的商品
                                or_(
                                    Product.updated_at < update_threshold,
                                    Product.discount_updated_at < update_threshold
                                )
                            ).order_by(Product.updated_at).limit(remaining_slots - len(products_to_update)).all()
                            
                            logger.info("找到 {} 个需要更新的已有历史记录的商品", len(products_need_update))
                            products_to_update.extend(products_need_update)
                        
                        # 使用最终筛选出的商品列表
                        regular_products = products_to_update
                        
                        # 根据创建时间排序
                        regular_products.sort(key=lambda p: p.created_at if p.created_at else datetime.min)
                        
                        # 限制数量
                        regular_products = regular_products[:remaining_slots]
                
                # 合并优先和常规商品列表
                products = priority_products + regular_products
                
                # 限制总数量
                products = products[:self.batch_size]
                
                logger.info("最终选择商品数量: 总计 {}, 其中优先商品 {}, 常规商品 {}", 
                          len(products), len(priority_products), len(regular_products))
            
                asins_to_process = [p.asin for p in products]
            
            logger.info("获取到 {} 个待处理商品 (其中优先商品: {})",
                       len(asins_to_process),
                       len(priority_products))
        
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
                # 如果处理过程中存在重试，添加独立商品数的计数说明
                if stats['retry_count'] > 0:
                    logger.info(f"不重复商品数: {len(self.specific_asins) if self.specific_asins else self.batch_size}")
                logger.info(f"成功数: {stats['success_count']}")
                logger.info(f"失败数: {stats['failure_count']}")
                logger.info(f"成功率: {(stats['success_count']/stats['processed_count']*100) if stats['processed_count'] > 0 else 0:.1f}%")
                logger.info(f"平均速度: {stats['processed_count']/duration:.2f}个/秒" if duration > 0 else "平均速度: N/A")
                logger.info(f"更新的优惠券类型数量: {stats['updated_fields']['coupon_type']}")
                logger.info(f"更新的优惠券值数量: {stats['updated_fields']['coupon_value']}")
                logger.info(f"新建的优惠券历史记录数: {stats['coupon_history']['created']}")
                logger.info(f"更新的优惠券历史记录数: {stats['coupon_history']['updated']}")
                
                # 添加验证码统计信息
                logger.info(f"遇到验证码次数: {stats['captcha_count']}")
                logger.info(f"刷新成功解决验证码次数: {stats['refresh_success_count']}")
                logger.info(f"任务重试次数: {stats['retry_count']}")
                logger.info(f"等待期延迟处理次数: {stats['delayed_count']}")
                logger.info(f"超过最大重试次数的任务: {stats['max_retry_exceeded']}")
                
                logger.info("=====================================================")
                
                # 关闭数据库连接
                self.db.close()

def check_and_scrape_coupon_details(asins=None, batch_size=50, num_threads=2, headless=True, 
                                    min_delay=2.0, max_delay=4.0, debug=False):
    """
    检查并抓取优惠券商品详情
    
    注意：此函数仅处理来源(source)为'coupon'的商品，其他来源的商品将被跳过。
    如果提供了asins参数，会检查每个ASIN对应的商品来源，并跳过非'coupon'来源的商品。
    
    Args:
        asins: 指定的ASIN列表，如果为None则从数据库中获取
        batch_size: 每批处理的商品数量
        num_threads: 并发线程数
        headless: 是否使用无头浏览器
        min_delay: 最小延迟时间
        max_delay: 最大延迟时间
        debug: 是否开启调试模式
        
    Returns:
        tuple: (处理商品数量, 更新商品数量)
    """
    # 初始化日志
    logger = init_logger()
    logger.info(f"开始执行优惠券详情抓取任务，批次大小: {batch_size}, 线程数: {num_threads}")
    
    # 初始化数据库会话
    from models.database import SessionLocal
    db = SessionLocal()
    
    try:
        # 获取需要处理的商品列表
        if asins is None:
            from models.database import Product
            from sqlalchemy import or_, func, desc, and_
            from datetime import datetime, timedelta
            
            # 优化查询策略：采用多种策略选择商品
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=24)  # 24小时前
            
            # 创建基础查询
            from models.database import Offer
            
            # 检查输入的商品类型
            logger.info("仅选择source='coupon'来源的商品进行处理")
            
            # 两种策略：直接筛选有优惠券的商品和有折扣的商品
            coupon_products_query = db.query(Product).join(Offer).filter(
                Offer.coupon_type.isnot(None),
                Product.source == 'coupon'  # 重要：仅处理coupon来源的商品
            ).distinct()
            
            discount_products_query = db.query(Product).filter(
                or_(
                    Product.deal_type == "Coupon",
                    Product.savings_percentage > 0
                ),
                Product.source == 'coupon'  # 重要：仅处理coupon来源的商品
            )
            
            # 合并两个查询
            coupon_products = coupon_products_query.all()
            discount_products = discount_products_query.all()
            
            # 合并去重
            all_products = {}
            for product in coupon_products + discount_products:
                all_products[product.asin] = product
            
            base_products = list(all_products.values())
            logger.info(f"找到 {len(base_products)} 个有优惠券或折扣的商品")
            
            # 如果没有找到任何符合条件的商品，直接返回
            if not base_products:
                logger.info("没有找到任何有优惠券或折扣的商品")
                return 0, 0
            
            # 将所有找到的商品按照更新时间进行排序
            sorted_products = sorted(base_products, key=lambda p: p.updated_at or datetime.min)
            
            # 策略1: 选取30%最早更新的商品
            earliest_count = int(batch_size * 0.3)
            earliest_products = sorted_products[:earliest_count]
            
            # 策略2: 随机选择40%的商品
            import random
            remaining_products = sorted_products[earliest_count:]
            random_count = int(batch_size * 0.4)
            if len(remaining_products) > random_count:
                random_products = random.sample(remaining_products, random_count)
            else:
                random_products = remaining_products
            
            # 策略3: 选择30%最近添加的商品（可能是新商品）
            sorted_by_creation = sorted(base_products, key=lambda p: p.created_at or datetime.min, reverse=True)
            newest_count = batch_size - len(earliest_products) - len(random_products)
            newest_products = sorted_by_creation[:newest_count]
            
            # 合并所有选择的商品
            selected_products = {}
            for product in earliest_products + random_products + newest_products:
                selected_products[product.asin] = product
            
            # 获取最终的商品列表
            products = list(selected_products.values())[:batch_size]
            
            # 获取ASIN列表
            asins = [product.asin for product in products]
            logger.info(f"从数据库获取了 {len(asins)} 个商品进行优惠券详情抓取")
            
            # 打印选择的商品类型分布
            logger.info(f"商品选择分布: 最早更新 {len(earliest_products)}, 随机选择 {len(random_products)}, 最新添加 {len(newest_products)}")
            
            # 如果没有符合条件的商品，记录并返回
            if not asins:
                logger.info("没有找到需要抓取优惠券详情的商品")
                return 0, 0
        else:
            # 使用指定的ASIN列表
            logger.info(f"使用指定的 {len(asins)} 个ASIN进行优惠券详情抓取")
        
        # 如果批次大小大于实际商品数量，调整批次大小
        if batch_size > len(asins):
            batch_size = len(asins)
            logger.info(f"调整批次大小为实际商品数量: {batch_size}")
        
        # 创建爬虫实例
        stats = ThreadSafeStats()
        scraper = CouponScraperMT(
            num_threads=num_threads,
            batch_size=batch_size,
            specific_asins=asins[:batch_size],  # 限制处理数量
            headless=headless,
            min_delay=min_delay,
            max_delay=max_delay,
            debug=debug
        )
        
        # 运行爬虫
        scraper.run()
        
        # 获取统计数据
        stats_data = scraper.stats.get()
        processed_count = stats_data.get('processed_count', 0)
        updated_count = stats_data.get('success_count', 0)
        
        logger.success(f"优惠券详情抓取完成，处理: {processed_count}，更新: {updated_count}")
        return processed_count, updated_count
        
    except Exception as e:
        logger.error(f"优惠券详情抓取失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 0, 0
    finally:
        db.close()

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

    # 根据参数决定执行模式
    if args.check_details:
        # 执行优惠券详情检查和抓取
        logger.info("启动优惠券详情检查和抓取功能")
        processed_count, updated_count = check_and_scrape_coupon_details(
            asins=specific_asins,
            batch_size=args.batch_size,
            num_threads=args.threads,
            headless=not args.no_headless,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            debug=args.debug
        )
        logger.info(f"完成优惠券详情抓取，处理了{processed_count}个商品，成功更新{updated_count}个")
    else:
        # 初始化常规优惠券抓取
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