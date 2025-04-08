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
from tqdm import tqdm
import re
import asyncio
import math
from dataclasses import dataclass
from queue import PriorityQueue
import heapq
from sqlalchemy import func, desc

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, CouponHistory, Offer, get_db
from src.utils.webdriver_manager import WebDriverConfig
from src.utils.config_loader import config_loader
from src.core.discount_scheduler import DiscountUpdateScheduler, TaskLoggerAdapter  # 更新导入

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    # 使用项目根目录下的logs目录
    log_dir = Path(project_root) / os.getenv("APP_LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置优惠抓取专用日志
    scraper_log_file = log_dir / "discount_scraper.log"
    
    # 创建日志记录器
    logger = logging.getLogger("DiscountScraper")
    logger.setLevel(logging.INFO)
    
    # 移除现有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建文件处理器
    file_handler = RotatingFileHandler(
        scraper_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # 设置格式化器
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    
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
    parser.add_argument('--force-update', action='store_true', help='强制更新所有商品，忽略时间间隔检查')
    return parser.parse_args()

class DiscountScraper:
    """优惠信息抓取器类"""
    
    def __init__(self, db: Session, batch_size: int = 50, headless: bool = True,
                 min_delay: float = 2.0, max_delay: float = 4.0, specific_asins: list = None,
                 use_scheduler: bool = True, scheduler: DiscountUpdateScheduler = None,
                 retry_count: int = 2, retry_delay: float = 5.0):  # 添加重试参数
        """
        初始化抓取器
        
        Args:
            db: 数据库会话
            batch_size: 每批处理的商品数量
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            specific_asins: 指定要处理的商品ASIN列表
            use_scheduler: 是否使用调度器
            scheduler: 调度器实例
            retry_count: 失败重试次数
            retry_delay: 重试间隔(秒)
        """
        self.db = db
        self.batch_size = batch_size
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.specific_asins = specific_asins
        self.driver = None
        self.logger = TaskLoggerAdapter(logger, {'task_id': 'SYSTEM'})
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # 初始化调度器
        self.use_scheduler = use_scheduler
        self.scheduler = scheduler if use_scheduler else None
        
        # 添加字段更新统计
        self.stats = {
            'start_time': None,
            'end_time': None,
            'processed_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'retry_count': 0,  # 添加重试计数
            'updated_fields': {
                'current_price': 0,
                'original_price': 0,
                'savings_amount': 0,
                'savings_percentage': 0,
                'coupon_type': 0,
                'coupon_value': 0,
                'deal_type': 0,
                'deal_badge': 0
            }
        }
        
        # 已处理的商品集合，避免重复处理
        self._processed_asins = set()
        
    def _init_driver(self):
        """初始化WebDriver"""
        if not self.driver:
            config = WebDriverConfig()
            self.driver = config.create_chrome_driver(headless=self.headless)
            
            # 设置全局超时参数
            self.driver.set_page_load_timeout(60)  # 页面加载超时
            self.driver.set_script_timeout(30)     # 脚本执行超时
            
            # 添加错误处理
            try:
                # 预热浏览器，访问简单页面确保WebDriver正常工作
                self.driver.get("about:blank")
                self.logger.info("WebDriver初始化完成")
            except Exception as e:
                self.logger.error(f"WebDriver初始化异常: {str(e)}")
                # 尝试重新创建
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = config.create_chrome_driver(headless=self.headless)
                self.driver.set_page_load_timeout(60)
                self.driver.set_script_timeout(30)
                self.logger.info("WebDriver重新初始化完成")
            
    def _close_driver(self):
        """关闭WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logger.info("WebDriver已关闭")
            
    def _extract_discount_info(self, product: Product) -> Tuple[Optional[float], Optional[int], Optional[float]]:
        """提取商品折扣信息"""
        task_log = TaskLoggerAdapter(self.logger, {'task_id': f'EXTRACT:{product.asin}'})
        
        savings = None
        savings_percentage = None
        actual_current_price = None
        
        try:
            # 添加页面稳定性检查
            try:
                # 等待页面主体加载完成
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                )
                
                # 通过执行简单脚本确认页面响应正常
                self.driver.execute_script("return document.readyState")
            except Exception as e:
                task_log.warning(f"页面状态检查失败: {str(e)}，尝试继续处理")
                
            # 尝试获取当前价格
            try:
                # 首先尝试使用精确的选择器提取价格
                price_elements = self.driver.find_elements(By.CSS_SELECTOR, '#corePrice_feature_div .a-offscreen')
                if price_elements:
                    price_text = price_elements[0].get_attribute('textContent')
                    cleaned_price = float(price_text.replace('$', '').replace(',', '').strip())
                    task_log.debug(f"从页面精确提取到当前实际价格: ${cleaned_price}")
                    actual_current_price = cleaned_price
                else:
                    # 如果精确选择器失败，尝试更一般的选择器
                    price_elements = self.driver.find_elements(By.CSS_SELECTOR, '.a-price .a-offscreen')
                    if price_elements:
                        price_text = price_elements[0].get_attribute('textContent')
                        cleaned_price = float(price_text.replace('$', '').replace(',', '').strip())
                        task_log.debug(f"从页面选择器 .a-price .a-offscreen 提取到当前实际价格: ${cleaned_price}")
                        actual_current_price = cleaned_price
            except (ValueError, IndexError) as e:
                task_log.debug(f"提取当前价格出错: {str(e)}")
            
            # 首先尝试获取标准List Price原价信息
            try:
                # 寻找显示原价的元素
                list_price_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                    '.a-text-price .a-offscreen, #listPrice, #priceblock_ourprice_lbl + span'
                )
                
                if list_price_elements:
                    # 提取List Price文本并转换为数字
                    list_price_text = list_price_elements[0].get_attribute('textContent')
                    list_price = float(list_price_text.replace('$', '').replace(',', '').strip())
                    task_log.debug(f"从页面提取到List Price原价: ${list_price}")
                    
                    # 检查原价字段是否为空，更新商品原价
                    if not product.original_price or product.original_price == 0:
                        product.original_price = list_price
                        task_log.debug(f"使用页面提取的List Price ${list_price} 更新商品原价")
                    
                    # 设置了原价和当前价格，计算折扣信息
                    if actual_current_price and actual_current_price < list_price:
                        # 计算折扣百分比
                        discount_percentage = int(round((1 - actual_current_price / list_price) * 100))
                        task_log.debug(f"根据页面原价${list_price}和当前价格${actual_current_price}计算折扣百分比: {discount_percentage}%")
                        
                        # 计算节省金额
                        savings_amount = list_price - actual_current_price
                        task_log.debug(f"使用页面原价${list_price}和折扣{discount_percentage}%，计算节省金额${savings_amount:.2f}")
                        
                        savings = savings_amount
                        savings_percentage = discount_percentage
            except (ValueError, IndexError) as e:
                task_log.debug(f"提取List Price原价出错: {str(e)}")
            
            # 如果上面的方法未能提取到折扣信息，检查可能的"Save X%" 文本
            if not savings_percentage:
                try:
                    # 寻找包含"Save"的元素
                    save_elements = self.driver.find_elements(By.XPATH, 
                        '//*[contains(text(), "Save") and contains(text(), "%")]'
                    )
                    
                    if save_elements:
                        # 提取Save文本
                        save_text = save_elements[0].text
                        # 使用正则表达式提取百分比
                        percentage_match = re.search(r'Save\s+(\d+)%', save_text)
                        if percentage_match:
                            savings_percentage = int(percentage_match.group(1))
                            task_log.debug(f"从'Save'文本提取到折扣百分比: {savings_percentage}%")
                                
                            # 根据百分比和当前价格反推原价
                            if actual_current_price and savings_percentage:
                                calculated_original = actual_current_price / (1 - savings_percentage/100)
                                calculated_savings = calculated_original - actual_current_price
                                
                                # 更新商品原价（如果未设置）
                                if not product.original_price or product.original_price == 0:
                                    product.original_price = calculated_original
                                    task_log.debug(f"根据当前价格${actual_current_price}和折扣{savings_percentage}%反推原价: ${calculated_original:.2f}")
                                
                                savings = calculated_savings
                                task_log.debug(f"根据当前价格和折扣百分比计算节省金额: ${calculated_savings:.2f}")
                except Exception as e:
                    task_log.debug(f"提取Save文本折扣出错: {str(e)}")
            
            # 尝试提取优惠券信息
            coupon_type, coupon_value = self._extract_coupon_info()
            
            return savings, savings_percentage, actual_current_price
            
        except Exception as e:
            task_log.error(f"提取折扣信息时出错: {str(e)}")
            return None, None, None
        
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
                            self.logger.debug(f"从优惠券徽章提取到百分比优惠券: {percentage}%")
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
                        self.logger.debug(f"从'Apply coupon'元素提取到优惠券金额: ${amount}")
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
                                self.logger.debug(f"从'coupon applied'元素提取到优惠券金额: ${amount}")
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
                                self.logger.debug(f"从文本中提取到百分比优惠券: {percentage}%")
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
                        self.logger.debug(f"从标签元素提取到优惠券金额: ${amount}")
                        return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从标签文本中提取金额: {text}, 错误: {str(e)}")
                elif "%" in text and "coupon" in text:
                    try:
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            self.logger.debug(f"从标签元素提取到百分比优惠券: {percentage}%")
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
                                self.logger.debug(f"从success元素提取到优惠券金额: ${amount}")
                                return "fixed", amount
                    except (IndexError, ValueError) as e:
                        self.logger.warning(f"无法从success元素提取金额: {text}, 错误: {str(e)}")
                elif "%" in text and ("coupon" in text or "off" in text):
                    try:
                        percentage_text = ''.join(c for c in text.split("%")[0] if c.isdigit())
                        if percentage_text:
                            percentage = float(percentage_text)
                            self.logger.debug(f"从success元素提取到百分比优惠券: {percentage}%")
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
            
    def _update_product_discount(self, product: Product, savings: float, savings_percentage: int,
                          coupon_type: str, coupon_value: float, deal_badge: str,
                          actual_current_price: float = None):
        """更新商品折扣信息"""
        task_log = TaskLoggerAdapter(self.logger, {'task_id': f'UPDATE:{product.asin}'})
        
        # 检查是否没有任何优惠信息
        has_no_discount = (savings is None or savings <= 0) and (savings_percentage is None or savings_percentage <= 0)
        has_no_coupon = coupon_type is None or coupon_value is None or coupon_value <= 0
        has_no_deal = deal_badge is None
        
        if has_no_discount and has_no_coupon and has_no_deal:
            # 商品没有任何优惠信息，从数据库中删除
            task_log.info(f"商品{product.asin}没有任何优惠信息，将从数据库中删除")
            
            try:
                # 记录商品ASIN用于后续删除
                asin_to_delete = product.asin
                
                # 不直接删除对象，而是通过ASIN查询并删除，避免会话冲突
                # 使用本方法中的会话(self.db)执行删除操作
                offers_to_delete = self.db.query(Offer).filter(Offer.product_id == asin_to_delete).all()
                for offer in offers_to_delete:
                    self.db.delete(offer)
                
                # 获取当前会话中的商品对象
                product_to_delete = self.db.query(Product).filter(Product.asin == asin_to_delete).first()
                if product_to_delete:
                    self.db.delete(product_to_delete)
                    task_log.debug(f"商品{asin_to_delete}及其关联记录已标记为删除")
                else:
                    task_log.warning(f"无法在当前会话中找到要删除的商品: {asin_to_delete}")
                
                # 立即提交删除操作
                self.db.commit()
                task_log.info(f"成功从数据库删除商品: {asin_to_delete}")
            except Exception as e:
                self.db.rollback()
                task_log.error(f"删除商品时出错: {str(e)}")
                import traceback
                task_log.debug(f"删除异常堆栈: {traceback.format_exc()}")
            
            # 提前返回，不再执行后续更新
            return
        
        # 如果没有优惠信息记录，创建一个新的
        if not product.offers:
            offer = Offer(product_id=product.asin)
            product.offers.append(offer)
            task_log.info(f"创建新的优惠信息记录")
        
        # 获取当前的offer以便与新值比较
        offer = product.offers[0]
        updated_fields = []
        
        # 记录原始值用于比较
        original_price_before = product.original_price
        
        # 比较并更新优惠信息字段
        # 1. 更新savings
        if offer.savings != savings and (savings is not None or offer.savings is not None):
            updated_fields.append(f"节省金额: {offer.savings} -> {savings}")
            offer.savings = savings
            product.savings_amount = savings
            self.stats['updated_fields']['savings_amount'] += 1
        
        # 2. 更新savings_percentage
        if offer.savings_percentage != savings_percentage and (savings_percentage is not None or offer.savings_percentage is not None):
            updated_fields.append(f"折扣比例: {offer.savings_percentage}% -> {savings_percentage}%")
            offer.savings_percentage = savings_percentage
            product.savings_percentage = savings_percentage
            self.stats['updated_fields']['savings_percentage'] += 1
        
        # 3. 更新coupon_type
        if offer.coupon_type != coupon_type and (coupon_type is not None or offer.coupon_type is not None):
            updated_fields.append(f"优惠券类型: {offer.coupon_type} -> {coupon_type}")
            offer.coupon_type = coupon_type
            self.stats['updated_fields']['coupon_type'] += 1
        
        # 4. 更新coupon_value
        if offer.coupon_value != coupon_value and (coupon_value is not None or offer.coupon_value is not None):
            updated_fields.append(f"优惠券金额: {offer.coupon_value} -> {coupon_value}")
            offer.coupon_value = coupon_value
            self.stats['updated_fields']['coupon_value'] += 1
        
        # 5. 更新deal_badge
        if offer.deal_badge != deal_badge and (deal_badge is not None or offer.deal_badge is not None):
            updated_fields.append(f"促销标签: {offer.deal_badge} -> {deal_badge}")
            offer.deal_badge = deal_badge
            self.stats['updated_fields']['deal_badge'] += 1
        
        # 6. 更新deal_type
        deal_type = self._determine_deal_type(bool(savings), bool(coupon_type), deal_badge)
        if offer.deal_type != deal_type and (deal_type is not None or offer.deal_type is not None):
            updated_fields.append(f"优惠类型: {offer.deal_type} -> {deal_type}")
            offer.deal_type = deal_type
            product.deal_type = deal_type
            self.stats['updated_fields']['deal_type'] += 1
        else:
            offer.deal_type = deal_type
            product.deal_type = deal_type
        
        # 7. 更新actual_current_price
        if actual_current_price and product.current_price != actual_current_price:
            updated_fields.append(f"当前价格: ${product.current_price} -> ${actual_current_price}")
            product.current_price = actual_current_price
            self.stats['updated_fields']['current_price'] += 1
        
        # 8. 更新original_price（如果从页面中获取到了新值）
        if product.original_price != original_price_before and original_price_before is not None:
            updated_fields.append(f"原价: ${original_price_before} -> ${product.original_price}")
            self.stats['updated_fields']['original_price'] += 1
        
        # 对于只有优惠券没有折扣的情况，将当前价格同时作为原价
        if (not product.original_price or product.original_price == 0 or 
            (coupon_type and not savings and not savings_percentage)) and actual_current_price:
            product.original_price = actual_current_price
            if original_price_before != actual_current_price:
                updated_fields.append(f"设置原价等于当前价格: ${actual_current_price}")
                self.stats['updated_fields']['original_price'] += 1
                task_log.debug(f"只有优惠券没有折扣，使用当前价格 ${actual_current_price} 同时作为原价")
        
        # 更新时间戳
        offer.updated_at = datetime.now(UTC)
        product.updated_at = datetime.now(UTC)
        product.discount_updated_at = datetime.now(UTC)
        
        # 如果有字段更新，记录详情
        if updated_fields:
            task_log.info(f"优惠信息更新: {'; '.join(updated_fields)}")
        else:
            task_log.debug(f"商品信息无变化")
        
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
            
            # 添加页面加载超时处理
            try:
                # 增加命令超时时间和页面加载超时时间
                self.driver.set_page_load_timeout(60)  # 提高页面加载超时时间至60秒
                self.driver.set_script_timeout(30)     # 设置脚本执行超时为30秒
                
                # 使用try-except包装get请求，确保能够捕获所有超时类型
                try:
                    self.driver.get(url)
                except TimeoutException:
                    task_log.warning(f"页面加载超时，尝试停止加载并继续处理")
                    try:
                        # 尝试停止页面加载
                        self.driver.execute_script("window.stop();")
                    except Exception as e:
                        task_log.error(f"停止页面加载失败: {str(e)}")
                        return False
            except Exception as e:
                # 捕获包括连接错误、浏览器崩溃等所有异常
                task_log.error(f"访问页面时出错: {str(e)}")
                
                # 尝试刷新WebDriver状态
                try:
                    self.driver.execute_script("return navigator.userAgent;")
                    task_log.info("WebDriver仍然响应，继续处理")
                except:
                    task_log.error("WebDriver无响应，放弃处理该商品")
                    return False
            
            # 随机等待1-3秒，模拟人类行为
            wait_time = random.uniform(1, 3)
            task_log.debug(f"等待页面加载: {wait_time:.1f}秒")
            time.sleep(wait_time)
            
            # 提取折扣和优惠券信息
            task_log.debug("提取折扣信息...")
            # _extract_discount_info内部已经调用了_extract_coupon_info
            savings, savings_percentage, actual_current_price = self._extract_discount_info(product)
            
            # 提取优惠券信息 - 如果_extract_discount_info已经调用过，则重用结果
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
        
        # 检查是否已经处理过此商品并成功
        if asin in self._processed_asins:
            task_log.debug(f"商品已处理过，但允许重试: {asin}")
            # 不阻止处理，允许重试
        
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
        success = self.process_product(product)
        
        # 如果处理成功，将商品ASIN添加到已处理集合中
        if success:
            self._processed_asins.add(asin)
            
        return success

    def run(self):
        """运行抓取器"""
        main_log = TaskLoggerAdapter(logger, {'task_id': 'MAIN'})
        self.stats['start_time'] = time.time()
        processed_count = 0
        success_count = 0
        
        try:
            main_log.info("初始化WebDriver...")
            self._init_driver()
            
            main_log.info("=====================================================")
            main_log.info("              开始优惠信息抓取任务")
            main_log.info("=====================================================")
            
            # 处理特定的ASIN列表或从调度器获取商品
            if self.specific_asins:
                main_log.info(f"将处理指定的 {len(self.specific_asins)} 个商品ASIN")
                asins_to_process = self.specific_asins
            elif self.use_scheduler:
                main_log.info("使用调度器获取待处理商品...")
                # 更新调度器任务队列
                self.scheduler.update_task_queue()
                # 获取下一批要处理的商品
                asins_to_process = self.scheduler.get_next_batch()
                main_log.info(f"调度器返回 {len(asins_to_process)} 个待处理商品")
            else:
                # 获取按创建时间排序的商品
                main_log.info("从数据库获取待处理商品列表...")
                products = self.db.query(Product).order_by(
                    Product.created_at
                ).limit(self.batch_size).all()
                asins_to_process = [p.asin for p in products]
                main_log.info(f"获取到 {len(asins_to_process)} 个待处理商品")
            
            # 使用tqdm添加进度条
            for idx, asin in enumerate(tqdm(asins_to_process, desc="处理商品"), 1):
                task_log = TaskLoggerAdapter(logger, {'task_id': f'BATCH:{idx}/{len(asins_to_process)}'})
                task_log.info(f"处理商品 ASIN: {asin}")
                
                # 记录处理开始时间
                task_start_time = time.time()
                
                # 处理商品
                success = self.process_asin(asin)
                processed_count += 1
                self.stats['processed_count'] += 1
                
                # 计算处理时间
                processing_time = time.time() - task_start_time
                
                # 如果使用调度器，记录任务结果
                if self.use_scheduler:
                    self.scheduler.record_task_result(asin, success, processing_time)
                
                if success:
                    success_count += 1
                    self.stats['success_count'] += 1
                    task_log.info(f"商品处理成功")
                    # 成功后等待随机时间
                    delay = random.uniform(self.min_delay, self.max_delay)
                    task_log.debug(f"等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                else:
                    self.stats['failure_count'] += 1
                    task_log.warning(f"商品处理失败")
                    # 失败后等待较长时间
                    delay = random.uniform(5, 10)
                    task_log.debug(f"失败后等待 {delay:.1f} 秒...")
                    time.sleep(delay)
            
            # 处理失败的商品进行重试
            if self.stats['failure_count'] > 0 and self.retry_count > 0:
                # 收集失败的商品ASIN进行重试
                failed_asins = [asin for asin in asins_to_process if asin not in self._processed_asins]
                
                # 重试失败的商品
                retry_count = 0
                while failed_asins and retry_count < self.retry_count:
                    retry_count += 1
                    main_log.info(f"第{retry_count}次重试，处理{len(failed_asins)}个失败商品")
                    
                    # 清除已处理列表，允许重试
                    self._processed_asins.clear()
                    
                    # 等待一段时间后重试
                    time.sleep(self.retry_delay)
                    
                    # 记录当前成功和失败数量
                    before_success = self.stats['success_count']
                    before_failure = self.stats['failure_count']
                    
                    # 使用进度条进行重试
                    for idx, asin in enumerate(tqdm(failed_asins, desc=f"重试 #{retry_count}"), 1):
                        task_log = TaskLoggerAdapter(logger, {'task_id': f'RETRY-{retry_count}:{idx}/{len(failed_asins)}'})
                        task_log.info(f"重试商品 ASIN: {asin}")
                        
                        # 处理商品
                        success = self.process_asin(asin)
                        self.stats['retry_count'] += 1
                        
                        if success:
                            # 更新统计数据
                            self.stats['success_count'] += 1
                            self.stats['failure_count'] -= 1
                            task_log.info(f"重试成功: {asin}")
                        else:
                            task_log.warning(f"重试失败: {asin}")
                        
                        # 重试后等待随机时间
                        delay = random.uniform(self.min_delay, self.max_delay)
                        time.sleep(delay)
                    
                    # 更新失败列表
                    failed_asins = [asin for asin in failed_asins if asin not in self._processed_asins]
                    
                    # 输出重试结果
                    success_diff = self.stats['success_count'] - before_success
                    failure_diff = before_failure - self.stats['failure_count']
                    main_log.info(f"第{retry_count}次重试完成，成功恢复: {success_diff}个，剩余失败: {len(failed_asins)}个")
                    
                    # 如果没有商品恢复成功，退出重试循环
                    if success_diff == 0:
                        main_log.warning("重试没有成功恢复任何商品，停止重试")
                        break
            
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
            self.stats['end_time'] = time.time()
            end_time = time.time()
            duration = end_time - self.stats['start_time']
            
            main_log.info("=====================================================")
            main_log.info("                  任务完成")
            main_log.info("=====================================================")
            main_log.info(f"任务统计:")
            main_log.info(f"  • 总耗时: {duration:.1f} 秒")
            main_log.info(f"  • 处理商品: {self.stats['processed_count']} 个")
            main_log.info(f"  • 成功更新: {self.stats['success_count']} 个")
            main_log.info(f"  • 失败数量: {self.stats['failure_count']} 个")
            main_log.info(f"  • 重试次数: {self.stats['retry_count']} 次")
            success_rate = (self.stats['success_count']/self.stats['processed_count']*100) if self.stats['processed_count'] > 0 else 0
            main_log.info(f"  • 成功率: {success_rate:.1f}%")
            main_log.info(f"  • 平均速度: {self.stats['processed_count']/duration:.2f} 个/秒" if duration > 0 else "N/A")
            
            # 添加字段更新统计信息
            main_log.info("\n字段更新统计:")
            main_log.info(f"  • 更新商品当前价格: {self.stats['updated_fields']['current_price']} 个")
            main_log.info(f"  • 更新商品标价: {self.stats['updated_fields']['original_price']} 个")
            main_log.info(f"  • 更新节省金额: {self.stats['updated_fields']['savings_amount']} 个")
            main_log.info(f"  • 更新折扣比例: {self.stats['updated_fields']['savings_percentage']} 个")
            main_log.info(f"  • 更新优惠券类型: {self.stats['updated_fields']['coupon_type']} 个")
            main_log.info(f"  • 更新优惠券值: {self.stats['updated_fields']['coupon_value']} 个")
            main_log.info(f"  • 更新优惠类型: {self.stats['updated_fields']['deal_type']} 个")
            main_log.info(f"  • 更新促销标签: {self.stats['updated_fields']['deal_badge']} 个")
            
            # 如果使用调度器，输出调度器统计信息
            if self.use_scheduler:
                scheduler_stats = self.scheduler.get_statistics()
                main_log.info("\n调度器统计:")
                main_log.info(f"  • 总任务数: {scheduler_stats['total_tasks']}")
                main_log.info(f"  • 完成任务: {scheduler_stats['completed_tasks']}")
                main_log.info(f"  • 失败任务: {scheduler_stats['failed_tasks']}")
                main_log.info(f"  • 成功率: {scheduler_stats['success_rate']:.1f}%")
                main_log.info(f"  • 平均处理时间: {scheduler_stats['avg_processing_time']:.2f} 秒")
                main_log.info(f"  • 剩余任务数: {scheduler_stats['queue_size']}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='亚马逊商品优惠信息爬虫')
    parser.add_argument('--batch-size', type=int, default=50, help='批处理大小')
    parser.add_argument('--no-headless', action='store_true', help='不使用无头模式')
    parser.add_argument('--force-update', action='store_true', help='强制更新所有商品，忽略时间间隔检查')
    args = parser.parse_args()

    # 初始化数据库会话
    db = next(get_db())
    
    # 初始化调度器
    scheduler = DiscountUpdateScheduler(
        db=db, 
        batch_size=args.batch_size,
        force_update=args.force_update
    )
    
    # 初始化爬虫
    scraper = DiscountScraper(
        db=db,
        scheduler=scheduler,
        headless=not args.no_headless
    )
    
    try:
        # 运行爬虫
        scraper.run()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止爬虫...")
    finally:
        # 关闭数据库连接
        db.close()

if __name__ == "__main__":
    main() 