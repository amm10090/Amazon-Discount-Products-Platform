"""
优惠信息抓取模块
该模块负责从亚马逊商品页面抓取优惠券和折扣信息，并更新数据库。

主要功能：
1. 按创建时间顺序抓取商品优惠信息
2. 处理优惠券和折扣信息
3. 更新数据库记录
4. 维护优惠券历史记录
"""

import os
import sys
from datetime import datetime, UTC
from typing import Optional, Dict, Tuple
import logging
import time
import random
import argparse
from pathlib import Path
from logging.handlers import RotatingFileHandler
from sqlalchemy.orm import Session
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from tqdm import tqdm  # 添加tqdm库支持进度条
import re

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, CouponHistory, Offer, get_db
from src.utils.webdriver_manager import WebDriverConfig
from src.utils.logger_manager import (
    log_info, log_debug, log_warning, 
    log_error, log_success, log_progress,
    log_section, set_log_config
)
from src.utils.config_loader import config_loader

class TaskLoggerAdapter(logging.LoggerAdapter):
    """为日志添加任务ID的适配器"""
    def process(self, msg, kwargs):
        kwargs.setdefault('extra', {}).setdefault('task_id', self.extra.get('task_id', 'SYSTEM'))
        return msg, kwargs

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 配置优惠抓取专用日志
    scraper_log_file = log_dir / "discount_scraper.log"
    
    # 创建日志记录器
    logger = logging.getLogger("DiscountScraper")
    
    # 移除现有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建文件处理器 - 记录所有级别日志
    file_handler = RotatingFileHandler(
        scraper_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # 创建控制台处理器 - 只显示INFO及以上级别
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 设置格式化器
    log_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(task_id)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)
    
    # 配置日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 从环境变量获取日志级别，默认为INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # 设置日志级别
    logger.setLevel(log_level)
    
    return logger

# 全局日志记录器
logger = init_logger()

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='Amazon商品优惠信息抓取工具')
    parser.add_argument('--batch-size', type=int, default=50, help='每批处理的商品数量')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--min-delay', type=float, default=2.0, help='最小请求延迟(秒)')
    parser.add_argument('--max-delay', type=float, default=4.0, help='最大请求延迟(秒)')
    parser.add_argument('--asin', type=str, help='要处理的单个商品ASIN')
    parser.add_argument('--asin-list', type=str, help='要处理的多个商品ASIN列表，用逗号分隔')
    parser.add_argument('--asin-file', type=str, help='包含多个商品ASIN的文件路径，每行一个ASIN')
    parser.add_argument('--log-level', type=str, default=None, help='日志级别 (DEBUG, INFO, WARNING, ERROR)')
    return parser.parse_args()

class DiscountScraper:
    """优惠信息抓取器类"""
    
    def __init__(self, db: Session, batch_size: int = 50, headless: bool = True,
                 min_delay: float = 2.0, max_delay: float = 4.0, specific_asins: list = None):
        """
        初始化抓取器
        
        Args:
            db: 数据库会话
            batch_size: 每批处理的商品数量
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            specific_asins: 指定要处理的商品ASIN列表
        """
        self.db = db
        self.batch_size = batch_size
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.specific_asins = specific_asins
        self.driver = None
        self.logger = TaskLoggerAdapter(logger, {'task_id': 'SYSTEM'})
        
    def _init_driver(self):
        """初始化WebDriver"""
        if not self.driver:
            config = WebDriverConfig()
            self.driver = config.create_chrome_driver(headless=self.headless)
            self.logger.info("WebDriver初始化完成")
            
    def _close_driver(self):
        """关闭WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logger.info("WebDriver已关闭")
            
    def _extract_discount_info(self, product: Product) -> Tuple[Optional[float], Optional[int], Optional[float]]:
        """
        从页面提取折扣信息，使用数据库中的原价计算节省金额
        
        Args:
            product: 商品对象，包含数据库中的原价信息
            
        Returns:
            Tuple[Optional[float], Optional[int], Optional[float]]: (折扣金额, 折扣百分比, 实际当前价格)
        """
        actual_current_price = None
        try:
            # 首先尝试从页面获取当前实际价格 - 使用更精确的选择器
            try:
                # 尝试方法1：获取整数和小数部分并组合
                try:
                    whole_part = self.driver.find_element(By.CSS_SELECTOR, ".priceToPay .a-price-whole")
                    fraction_part = self.driver.find_element(By.CSS_SELECTOR, ".priceToPay .a-price-fraction")
                    
                    whole_text = whole_part.text.strip().replace(",", "")  # 移除逗号
                    fraction_text = fraction_part.text.strip()
                    
                    actual_current_price = float(f"{whole_text}.{fraction_text}")
                    self.logger.info(f"从页面精确提取到当前实际价格: ${actual_current_price}")
                except (NoSuchElementException, ValueError) as e:
                    self.logger.debug(f"无法通过精确选择器提取价格: {str(e)}")
                
                # 尝试方法2：使用隐藏的价格元素（如果方法1失败）
                if actual_current_price is None:
                    offscreen_price = self.driver.find_element(By.CSS_SELECTOR, ".priceToPay .a-offscreen")
                    price_text = offscreen_price.get_attribute("textContent").replace("$", "").strip()
                    actual_current_price = float(price_text)
                    self.logger.info(f"从隐藏元素提取到当前实际价格: ${actual_current_price}")
                
                # 尝试方法3：使用原始选择器作为备选
                if actual_current_price is None:
                    price_element = self.driver.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                    price_text = price_element.get_attribute("textContent").replace("$", "").strip()
                    actual_current_price = float(price_text)
                    self.logger.info(f"从通用选择器提取到当前实际价格: ${actual_current_price}")
            except (NoSuchElementException, ValueError) as e:
                self.logger.warning(f"无法从页面提取当前实际价格: {str(e)}")

            # 同时尝试获取List Price作为原价
            try:
                list_price_element = self.driver.find_element(By.CSS_SELECTOR, ".a-price.a-text-price[data-a-strike='true'] .a-offscreen")
                list_price_text = list_price_element.get_attribute("textContent").replace("$", "").strip()
                list_price = float(list_price_text)
                self.logger.info(f"从页面提取到List Price: ${list_price}")
                
                # 如果数据库没有原价或原价为0，使用List Price更新
                if not product.original_price or product.original_price == 0:
                    product.original_price = list_price
                    self.logger.info(f"使用List Price ${list_price} 更新商品原价")
            except (NoSuchElementException, ValueError) as e:
                self.logger.debug(f"无法从页面提取List Price: {str(e)}")

            # 方法1: 直接从折扣元素中提取百分比 
            discount_selectors = [
                ".savingPriceOverride", 
                ".savingsPercentage",
                ".a-color-price.a-size-large.aok-align-center.reinventPriceSavingsPercentageMargin", 
                ".a-color-base.a-text-bold",
                "[id*='savings']",
                ".dealBadgeSavingsPercentage"
            ]
            
            # 寻找百分比折扣标记
            percentage = None
            for selector in discount_selectors:
                discount_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for discount_element in discount_elements:
                    text = discount_element.text.strip()
                    if "%" in text:
                        # 提取百分比数字，处理格式如"-34%"或"Save 34%"
                        percentage_text = ''.join(c for c in text.replace("-", "").replace("%", "") if c.isdigit())
                        if percentage_text:
                            percentage = int(percentage_text)
                            self.logger.info(f"直接从页面提取到折扣百分比: {percentage}%")
                            break
                if percentage:
                    break
            
            # 如果找到了折扣百分比，计算节省金额
            if percentage and product.original_price:
                # 使用数据库中的原价计算节省金额
                savings = product.original_price * (percentage / 100)
                self.logger.info(f"使用数据库原价${product.original_price}和折扣{percentage}%，计算节省金额${savings:.2f}")
                
                # 如果我们提取到了实际当前价格，记录一下计算价格与实际价格的差异
                if actual_current_price:
                    calculated_price = product.original_price - savings
                    diff = abs(calculated_price - actual_current_price)
                    self.logger.info(f"计算价格(${calculated_price:.2f})与实际价格(${actual_current_price:.2f})差异: ${diff:.2f}")
                
                return savings, percentage, actual_current_price
            elif percentage and product.current_price and (not product.original_price or product.original_price == 0):
                # 如果数据库中没有original_price但有current_price，直接使用current_price作为original_price
                # 将current_price设为original_price
                product.original_price = product.current_price
                # 计算节省金额
                savings = product.current_price * (percentage / 100)
                self.logger.info(f"数据库中无原价但有当前价格${product.current_price}，直接使用当前价格作为原价，计算节省金额${savings:.2f}")
                return savings, percentage, actual_current_price
            elif percentage:
                # 如果数据库中没有原价，也没有获取到实际当前价格，尝试从页面获取当前价格
                try:
                    if not actual_current_price:
                        # 再次尝试获取当前价格（以防之前的代码改变）
                        price_element = self.driver.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                        actual_current_price = float(price_element.get_attribute("textContent").replace("$", "").strip())
                        self.logger.info(f"提取到当前价格: ${actual_current_price}")
                    
                    # 直接使用当前价格作为原价
                    product.original_price = actual_current_price
                    # 计算节省金额
                    savings = actual_current_price * (percentage / 100)
                    self.logger.info(f"数据库中无原价，使用页面当前价格${actual_current_price}作为原价，计算节省金额${savings:.2f}")
                    return savings, percentage, actual_current_price
                except (NoSuchElementException, ValueError) as e:
                    self.logger.warning(f"无法提取当前价格且数据库无原价: {str(e)}")
                    return None, percentage, actual_current_price
            
        except NoSuchElementException:
            self.logger.warning("找不到折扣元素")
        except Exception as e:
            self.logger.warning(f"提取折扣信息失败: {str(e)}")
            
        return None, None, actual_current_price
        
    def _extract_deal_badge_info(self) -> Optional[str]:
        """
        提取商品页面的Deal Badge信息
        
        Returns:
            Optional[str]: Deal类型，例如"Prime Spring Deal"
        """
        try:
            deal_badge = self.driver.find_element(By.CSS_SELECTOR, "#dealBadge_feature_div .dealBadgeTextColor")
            if deal_badge:
                return deal_badge.text.strip()
        except NoSuchElementException:
            pass
            
        return None
        
    def _extract_coupon_info(self) -> Tuple[Optional[str], Optional[float]]:
        """
        从页面提取优惠券信息
        
        Returns:
            Tuple[Optional[str], Optional[float]]: (优惠券类型, 优惠券值)
        """
        try:
            # 新增: 检查优惠券特定元素
            coupon_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-section .couponBadge")
            for element in coupon_elements:
                text = element.text.strip().lower()
                if "% off" in text or ("coupon" in text and "%" in text):
                    try:
                        # 提取百分比，处理格式如"40% off coupon"
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            self.logger.info(f"从优惠券徽章提取到百分比优惠券: {percentage}%")
                            return "percentage", percentage
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"无法从优惠券徽章提取百分比: {text}, 错误: {str(e)}")
                        
            # 方法1: 检查包含"Apply $X coupon"的促销价格信息元素
            promo_elements = self.driver.find_elements(By.CSS_SELECTOR, ".promoPriceBlockMessage")
            for element in promo_elements:
                text = element.text.strip().lower()
                
                # 检查是否有"apply $X coupon"文本
                if "apply $" in text and "coupon" in text:
                    try:
                        # 提取优惠券金额
                        amount_text = text.split("apply $")[1].split("coupon")[0].strip()
                        amount = float(''.join(c for c in amount_text if c.isdigit() or c == '.'))
                        self.logger.info(f"从'Apply coupon'元素提取到优惠券金额: ${amount}")
                        return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从'Apply coupon'文本中提取金额: {text}, 错误: {str(e)}")
                
                # 检查是否有"$X off coupon applied"文本
                if "coupon applied" in text:
                    try:
                        # 寻找$金额
                        if "$" in text:
                            amount_parts = text.split("$")
                            if len(amount_parts) > 1:
                                amount_text = amount_parts[1].split(" ")[0].strip()
                                amount = float(''.join(c for c in amount_text if c.isdigit() or c == '.'))
                                self.logger.info(f"从'coupon applied'元素提取到优惠券金额: ${amount}")
                                return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从'coupon applied'文本中提取金额: {text}, 错误: {str(e)}")
                
                # 检查是否有"X% off coupon"或类似的百分比优惠券
                if "%" in text and "coupon" in text:
                    try:
                        percentage_parts = text.split("%")
                        if len(percentage_parts) > 0:
                            # 提取百分比前面的数字
                            percentage_text = ''.join(c for c in percentage_parts[0] if c.isdigit() or c == '.')
                            if percentage_text:
                                percentage = float(percentage_text)
                                self.logger.info(f"从文本中提取到百分比优惠券: {percentage}%")
                                return "percentage", percentage
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"无法从文本中提取百分比: {text}, 错误: {str(e)}")
            
            # 方法2: 检查checkbox和label中的优惠券信息
            coupon_labels = self.driver.find_elements(By.CSS_SELECTOR, "label[for^='checkbox']")
            for label in coupon_labels:
                text = label.text.strip().lower()
                if "apply $" in text and "coupon" in text:
                    try:
                        amount_text = text.split("apply $")[1].split("coupon")[0].strip()
                        amount = float(''.join(c for c in amount_text if c.isdigit() or c == '.'))
                        self.logger.info(f"从标签元素提取到优惠券金额: ${amount}")
                        return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从标签文本中提取金额: {text}, 错误: {str(e)}")
                elif "%" in text and "coupon" in text:
                    try:
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            self.logger.info(f"从标签元素提取到百分比优惠券: {percentage}%")
                            return "percentage", percentage
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"无法从标签文本中提取百分比: {text}, 错误: {str(e)}")
            
            # 方法3: 检查.a-color-success元素，可能包含优惠券信息
            success_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-color-success")
            for element in success_elements:
                text = element.text.strip().lower()
                if "$" in text and ("coupon" in text or "off" in text):
                    # 尝试提取金额
                    try:
                        amount_parts = text.split("$")
                        if len(amount_parts) > 1:
                            amount_text = ''.join(c for c in amount_parts[1].split(" ")[0] if c.isdigit() or c == '.')
                            if amount_text:
                                amount = float(amount_text)
                                self.logger.info(f"从success元素提取到优惠券金额: ${amount}")
                                return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从success元素提取金额: {text}, 错误: {str(e)}")
                elif "%" in text and ("coupon" in text or "off" in text):
                    try:
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            self.logger.info(f"从success元素提取到百分比优惠券: {percentage}%")
                            return "percentage", percentage
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"无法从success元素提取百分比: {text}, 错误: {str(e)}")
            
            # 方法4: 使用常规选择器检查
            coupon_selectors = [
                "#couponBadgeRegularVpc", 
                ".promoPriceBlockMessage",
                ".vpcButton",
                "#vpcButton",
                ".dealBadge",
                ".newCouponBadge",
                "#donepctch"
            ]
            
            for selector in coupon_selectors:
                coupon_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in coupon_elements:
                    text = element.text.strip().lower()
                    
                    # 处理百分比优惠券
                    if "% off" in text:
                        percentage = float(''.join(c for c in text.split("%")[0] if c.isdigit() or c == '.'))
                        return "percentage", percentage
                        
                    # 处理固定金额优惠券
                    elif "$" in text and "off" in text:
                        amount = float(''.join(c for c in text.split("$")[1].split(" ")[0] if c.isdigit() or c == '.'))
                        return "fixed", amount
                        
                    # 处理优惠券文本中包含"coupon"的情况
                    elif "coupon" in text:
                        if "%" in text:
                            percentage = float(''.join(c for c in text.split("%")[0] if c.isdigit() or c == '.'))
                            return "percentage", percentage
                        elif "$" in text:
                            amount = float(''.join(c for c in text.split("$")[1].split(" ")[0] if c.isdigit() or c == '.'))
                            return "fixed", amount
                    
        except Exception as e:
            self.logger.warning(f"提取优惠券信息失败: {str(e)}")
            
        return None, None
        
    def _determine_deal_type(self, 
                           has_discount: bool, 
                           has_coupon: bool,
                           deal_badge: Optional[str] = None) -> str:
        """
        根据优惠情况确定deal_type
        
        Args:
            has_discount: 是否有折扣
            has_coupon: 是否有优惠券
            deal_badge: 是否有特殊促销标签
            
        Returns:
            str: 优惠类型
        """
        if deal_badge:
            if "Prime" in deal_badge:
                return "PrimeDeal"
            return "SpecialDeal"
        elif has_discount and has_coupon:
            # 如果同时有折扣和优惠券，优先返回Coupon作为deal_type
            # 这符合用户期望的行为
            return "Coupon"
        elif has_discount:
            return "Discount"
        elif has_coupon:
            return "Coupon"
        else:
            return "None"
            
    def _update_product_discount(self, 
                               product: Product,
                               savings: Optional[float],
                               savings_percentage: Optional[int],
                               coupon_type: Optional[str],
                               coupon_value: Optional[float],
                               deal_badge: Optional[str] = None,
                               actual_current_price: Optional[float] = None) -> None:
        """
        更新商品优惠信息
        
        Args:
            product: 商品对象
            savings: 节省金额
            savings_percentage: 折扣百分比
            coupon_type: 优惠券类型
            coupon_value: 优惠券值
            deal_badge: 特殊促销标签
            actual_current_price: 从网页直接抓取的当前价格
        """
        task_log = TaskLoggerAdapter(logger, {'task_id': f'UPDATE:{product.asin}'})
        
        # 如果存在旧的优惠券信息，保存到历史记录
        if product.offers and (product.offers[0].coupon_type or product.offers[0].coupon_value):
            old_coupon = CouponHistory(
                product_id=product.asin,
                coupon_type=product.offers[0].coupon_type,
                coupon_value=product.offers[0].coupon_value,
                created_at=datetime.now(UTC)
            )
            self.db.add(old_coupon)
            task_log.info(f"保存旧优惠券信息: 类型={product.offers[0].coupon_type}, 值={product.offers[0].coupon_value}")
            
        # 更新商品优惠信息
        if not product.offers:
            offer = Offer(product_id=product.asin)
            product.offers.append(offer)
            task_log.info(f"创建新的优惠信息记录")
            
        # 更新Offer表中的优惠信息
        product.offers[0].savings = savings
        product.offers[0].savings_percentage = savings_percentage
        product.offers[0].coupon_type = coupon_type
        product.offers[0].coupon_value = coupon_value
        product.offers[0].deal_badge = deal_badge
        product.offers[0].deal_type = self._determine_deal_type(
            bool(savings), bool(coupon_type), deal_badge
        )
        product.offers[0].updated_at = datetime.now(UTC)
        
        # 同步更新Product表中的优惠信息
        product.savings_amount = savings
        product.savings_percentage = savings_percentage
        product.deal_type = product.offers[0].deal_type
        product.updated_at = datetime.now(UTC)
        
        # 安全处理可能为None的数值
        savings_str = f"${savings:.2f}" if savings is not None else "无"
        percentage_str = f"{savings_percentage}%" if savings_percentage is not None else "无"
        
        task_log.info(
            f"优惠信息更新: 折扣={percentage_str}, 节省={savings_str}, "
            f"优惠券={coupon_type}({coupon_value}), 促销={deal_badge}, 类型={product.deal_type}"
        )
        
        # 更新商品当前价格
        if actual_current_price:
            # 优先使用从网页抓取的实际价格作为当前显示价格
            product.current_price = actual_current_price
            
            # 如果之前没有设置原价，也使用当前价格作为原价
            if not product.original_price or product.original_price == 0:
                product.original_price = actual_current_price
                
            task_log.info(f"使用从网页抓取的实际当前价格: ${actual_current_price:.2f}")
        elif savings and product.original_price:
            # 如果有折扣金额且有原价，计算折扣后的价格
            product.current_price = product.original_price - savings
            task_log.info(f"通过计算得出当前价格: ${product.current_price:.2f} (原价${product.original_price:.2f} - 节省${savings:.2f})")
        
        # 记录优惠券信息，但不再改变当前价格
        # 注意：优惠券只是记录用，不会从当前价格中减去
        if coupon_type and coupon_value:
            coupon_discount_str = ""
            if coupon_type == "percentage":
                if product.current_price:
                    coupon_discount = product.current_price * (coupon_value / 100)
                    coupon_discount_str = f"${coupon_discount:.2f}"
                task_log.info(f"记录百分比优惠券: {coupon_value}% (约合{coupon_discount_str})")
            elif coupon_type == "fixed":
                task_log.info(f"记录固定金额优惠券: ${coupon_value}")
            
            # 添加注释说明不再从当前价格中减去优惠券金额
            task_log.info(f"优惠券信息仅供记录，不会从当前价格中减去")
        
    def process_product(self, product: Product) -> bool:
        """
        处理单个商品的优惠信息
        
        Args:
            product: 商品对象
            
        Returns:
            bool: 处理是否成功
        """
        task_log = TaskLoggerAdapter(logger, {'task_id': f'PROCESS:{product.asin}'})
        
        try:
            url = f"https://www.amazon.com/dp/{product.asin}?th=1"
            task_log.info(f"开始处理商品: {url}")
            self.driver.get(url)
            
            # 随机等待1-3秒，模拟人类行为
            wait_time = random.uniform(1, 3)
            task_log.debug(f"等待页面加载: {wait_time:.1f}秒")
            time.sleep(wait_time)
            
            # 提取折扣和优惠券信息
            task_log.debug("提取折扣信息...")
            savings, savings_percentage, actual_current_price = self._extract_discount_info(product)
            
            task_log.debug("提取优惠券信息...")
            coupon_type, coupon_value = self._extract_coupon_info()
            
            task_log.debug("提取促销标签信息...")
            deal_badge = self._extract_deal_badge_info()
            
            # 安全处理可能为None的数值，避免格式化错误
            savings_str = f"${savings:.2f}" if savings is not None else "无"
            percentage_str = f"{savings_percentage}%" if savings_percentage is not None else "无"
            coupon_value_str = str(coupon_value) if coupon_value is not None else "无"
            actual_price_str = f"${actual_current_price:.2f}" if actual_current_price is not None else "无"
            
            # 记录提取到的信息
            task_log.info(
                f"优惠信息提取结果: 折扣={percentage_str}, 节省={savings_str}, "
                f"实际当前价格={actual_price_str}, 优惠券={coupon_type}({coupon_value_str}), 促销={deal_badge}"
            )
            
            # 更新数据库
            task_log.debug("更新数据库...")
            self._update_product_discount(
                product, savings, savings_percentage,
                coupon_type, coupon_value, deal_badge, actual_current_price
            )
            
            self.db.commit()
            task_log.info(f"商品优惠信息更新成功")
            return True
            
        except Exception as e:
            self.db.rollback()
            task_log.error(f"处理失败: {str(e)}")
            # 记录详细的异常堆栈信息
            import traceback
            task_log.debug(f"异常堆栈: {traceback.format_exc()}")
            return False
            
    def process_asin(self, asin: str) -> bool:
        """
        处理单个商品ASIN的优惠信息
        
        Args:
            asin: 商品ASIN
            
        Returns:
            bool: 处理是否成功
        """
        task_log = TaskLoggerAdapter(logger, {'task_id': f'ASIN:{asin}'})
        
        # 尝试从数据库获取商品
        task_log.info(f"查询数据库中的商品信息")
        product = self.db.query(Product).filter(Product.asin == asin).first()
        
        # 如果数据库中不存在该商品，则创建一个新的记录
        if not product:
            task_log.info(f"数据库中不存在商品，创建新记录")
            product = Product(asin=asin, created_at=datetime.now(UTC))
            self.db.add(product)
            try:
                task_log.debug(f"刷新数据库以获取ID")
                self.db.flush()  # 刷新以获取ID，但不提交
            except Exception as e:
                task_log.error(f"创建商品记录失败: {str(e)}")
                self.db.rollback()
                return False
        
        # 处理商品优惠信息
        return self.process_product(product)

    def run(self):
        """运行抓取器"""
        main_log = TaskLoggerAdapter(logger, {'task_id': 'MAIN'})
        start_time = time.time()
        processed_count = 0
        success_count = 0
        
        try:
            main_log.info("初始化WebDriver...")
            self._init_driver()
            
            main_log.info("=====================================================")
            main_log.info("              开始优惠信息抓取任务")
            main_log.info("=====================================================")
            
            # 处理特定的ASIN列表或从数据库获取商品
            if self.specific_asins:
                main_log.info(f"将处理指定的 {len(self.specific_asins)} 个商品ASIN")
                
                # 使用tqdm添加进度条
                for idx, asin in enumerate(tqdm(self.specific_asins, desc="处理商品"), 1):
                    task_log = TaskLoggerAdapter(logger, {'task_id': f'BATCH:{idx}/{len(self.specific_asins)}'})
                    task_log.info(f"处理商品 ASIN: {asin}")
                    
                    # 处理商品
                    success = self.process_asin(asin)
                    processed_count += 1
                    
                    if success:
                        success_count += 1
                        task_log.info(f"商品处理成功")
                        # 成功后等待随机时间
                        delay = random.uniform(self.min_delay, self.max_delay)
                        task_log.debug(f"等待 {delay:.1f} 秒...")
                        time.sleep(delay)
                    else:
                        task_log.warning(f"商品处理失败")
                        # 失败后等待较长时间
                        delay = random.uniform(5, 10)
                        task_log.debug(f"失败后等待 {delay:.1f} 秒...")
                        time.sleep(delay)
            else:
                # 获取按创建时间排序的商品
                main_log.info("从数据库获取待处理商品列表...")
                products = self.db.query(Product).order_by(
                    Product.created_at
                ).limit(self.batch_size).all()
                
                total_products = len(products)
                main_log.info(f"本次任务将处理 {total_products} 个商品")
                
                # 使用tqdm添加进度条
                for idx, product in enumerate(tqdm(products, desc="处理商品"), 1):
                    task_log = TaskLoggerAdapter(logger, {'task_id': f'BATCH:{idx}/{total_products}'})
                    task_log.info(f"处理商品 ASIN: {product.asin}")
                    
                    # 处理每个商品
                    success = self.process_product(product)
                    processed_count += 1
                    
                    if success:
                        success_count += 1
                        task_log.info(f"商品处理成功")
                        # 成功后等待随机时间
                        delay = random.uniform(self.min_delay, self.max_delay)
                        task_log.debug(f"等待 {delay:.1f} 秒...")
                        time.sleep(delay)
                    else:
                        task_log.warning(f"商品处理失败")
                        # 失败后等待较长时间
                        delay = random.uniform(5, 10)
                        task_log.debug(f"失败后等待 {delay:.1f} 秒...")
                        time.sleep(delay)
                    
        except Exception as e:
            main_log.error(f"抓取过程发生错误: {str(e)}")
            # 记录详细的异常堆栈信息
            import traceback
            main_log.debug(f"异常堆栈: {traceback.format_exc()}")
            raise
            
        finally:
            main_log.info("关闭WebDriver...")
            self._close_driver()
            
            # 输出任务统计信息
            end_time = time.time()
            duration = end_time - start_time
            
            main_log.info("=====================================================")
            main_log.info("                  任务完成")
            main_log.info("=====================================================")
            main_log.info(f"任务统计:")
            main_log.info(f"  • 总耗时: {duration:.1f} 秒")
            main_log.info(f"  • 处理商品: {processed_count} 个")
            main_log.info(f"  • 成功更新: {success_count} 个")
            main_log.info(f"  • 失败数量: {processed_count - success_count} 个")
            main_log.info(f"  • 成功率: {(success_count/processed_count*100):.1f}%" if processed_count > 0 else "0%")
            main_log.info(f"  • 平均速度: {processed_count/duration:.2f} 个/秒" if duration > 0 else "N/A")

async def main():
    """异步主函数"""
    args = parse_arguments()
    
    # 设置日志级别
    if args.log_level:
        log_level = getattr(logging, args.log_level.upper(), logging.INFO)
        logger.setLevel(log_level)
    
    main_log = TaskLoggerAdapter(logger, {'task_id': 'MAIN'})
    main_log.info("=====================================================")
    main_log.info("           启动优惠信息抓取任务")
    main_log.info("=====================================================")
    
    # 处理ASIN参数
    specific_asins = []
    
    if args.asin:
        main_log.info(f"  • 指定单个ASIN: {args.asin}")
        specific_asins.append(args.asin)
        
    if args.asin_list:
        asin_list = [asin.strip() for asin in args.asin_list.split(',') if asin.strip()]
        main_log.info(f"  • 指定ASIN列表: {len(asin_list)}个")
        specific_asins.extend(asin_list)
        
    if args.asin_file:
        try:
            with open(args.asin_file, 'r') as f:
                file_asins = [line.strip() for line in f if line.strip()]
                main_log.info(f"  • 从文件加载ASIN: {len(file_asins)}个 (文件: {args.asin_file})")
                specific_asins.extend(file_asins)
        except Exception as e:
            main_log.error(f"读取ASIN文件失败: {str(e)}")
            sys.exit(1)
    
    # 去重
    if specific_asins:
        specific_asins = list(dict.fromkeys(specific_asins))
        main_log.info(f"  • 总计处理ASIN: {len(specific_asins)}个 (去重后)")
    
    # 当有指定ASIN时，调整批量大小为实际处理的ASIN数量
    actual_batch_size = len(specific_asins) if specific_asins else args.batch_size
    
    main_log.info(f"配置信息:")
    main_log.info(f"  • 批量大小: {actual_batch_size} 个商品")
    main_log.info(f"  • 无头模式: {'否' if args.no_headless else '是'}")
    main_log.info(f"  • 延迟范围: {args.min_delay}-{args.max_delay} 秒")
    main_log.info(f"  • 日志级别: {logger.level}")
    
    try:
        # 获取数据库会话
        main_log.info("连接数据库...")
        db = next(get_db())
        
        # 创建抓取器实例
        main_log.info("创建优惠抓取器实例...")
        scraper = DiscountScraper(
            db=db,
            batch_size=actual_batch_size,
            headless=not args.no_headless,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            specific_asins=specific_asins if specific_asins else None
        )
        
        # 运行抓取任务
        main_log.info("开始运行抓取任务...")
        scraper.run()
        
    except Exception as e:
        main_log.error(f"任务执行失败: {str(e)}")
        # 记录详细的异常堆栈信息
        import traceback
        main_log.debug(f"异常堆栈: {traceback.format_exc()}")
        sys.exit(1)
        
    finally:
        main_log.info("关闭数据库连接...")
        db.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 