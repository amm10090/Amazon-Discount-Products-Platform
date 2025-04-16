"""
优惠券信息抓取模块
该模块负责从亚马逊商品页面抓取优惠券信息。

主要功能：
1. 按创建时间顺序抓取商品优惠券信息
2. 更新数据库记录
3. 只处理source为'coupon'的商品
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from tqdm import tqdm

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, Offer, get_db
from src.utils.webdriver_manager import WebDriverConfig

def parse_arguments():
    """添加命令行参数支持"""
    parser = argparse.ArgumentParser(description='亚马逊商品优惠券信息抓取工具')
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
    return parser.parse_args()

# 初始化组件日志配置
def init_logger(log_level=None, log_to_console=False):
    """初始化日志配置

    Args:
        log_level: 日志级别，可以是 DEBUG, INFO, WARNING, ERROR
        log_to_console: 是否同时输出到控制台
    """
    # 使用项目根目录下的logs目录
    log_dir = Path(project_root) / os.getenv("APP_LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置优惠抓取专用日志
    scraper_log_file = log_dir / "coupon_scraper.log"
    
    # 创建日志记录器
    logger = logging.getLogger("CouponScraper")
    
    # 设置日志级别
    if log_level:
        level = getattr(logging, log_level.upper())
        logger.setLevel(level)
    else:
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
    logger.addHandler(file_handler)
    
    # 如果需要，添加控制台处理器
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

# 全局日志记录器
logger = None  # 将在main函数中初始化

class CouponScraper:
    """优惠券信息抓取器类"""
    
    def __init__(self, db: Session, batch_size: int = 50, headless: bool = True,
                 min_delay: float = 2.0, max_delay: float = 4.0, specific_asins: list = None,
                 debug: bool = False, verbose: bool = False):
        """
        初始化抓取器
        
        Args:
            db: 数据库会话
            batch_size: 每批处理的商品数量
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            specific_asins: 指定要处理的商品ASIN列表
            debug: 是否启用调试模式
            verbose: 是否输出更多详细信息
        """
        self.db = db
        self.batch_size = batch_size
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.specific_asins = specific_asins
        self.driver = None
        self.logger = logger
        self.debug = debug
        self.verbose = verbose
        
        # 添加字段更新统计
        self.stats = {
            'start_time': None,
            'end_time': None,
            'processed_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'updated_fields': {
                'coupon_type': 0,
                'coupon_value': 0,
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
            
            if self.debug:
                self.logger.debug("WebDriver设置详情:")
                self.logger.debug(f"  • 无头模式: {self.headless}")
                self.logger.debug(f"  • 页面加载超时: 60秒")
                self.logger.debug(f"  • 脚本执行超时: 30秒")
            
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
        
    def _extract_coupon_info(self) -> Tuple[Optional[str], Optional[float]]:
        """
        从页面提取优惠券信息
        
        Returns:
            Tuple[Optional[str], Optional[float]]: (优惠券类型, 优惠券值)
        """
        try:
            if self.debug:
                self.logger.debug("开始提取优惠券信息...")
            
            # 增强的正则表达式模式，用于从文本中提取美元金额
            dollar_pattern = r'\$\s*(\d+(?:\.\d+)?)'
            percentage_pattern = r'(\d+)%'
            
            # 保存页面源代码以便调试
            if self.debug or self.verbose:
                page_source = self.driver.page_source
                # 检查页面源代码中是否包含关键词
                if 'Apply $' in page_source and 'coupon' in page_source:
                    self.logger.debug("页面源代码中检测到'Apply $ coupon'字样")
                    import re
                    # 使用正则表达式在页面源码中查找优惠券金额
                    coupon_matches = re.findall(r'Apply\s+\$(\d+)\s+coupon', page_source)
                    if coupon_matches:
                        self.logger.debug(f"在页面源码中发现优惠券金额: ${coupon_matches[0]}")
            
            # 方法0: 使用更广泛的XPath查询检查包含"Apply $X coupon"的任何元素
            try:
                apply_coupon_xpath = "//*[contains(text(), 'Apply $') and contains(text(), 'coupon')]"
                apply_coupon_elements = self.driver.find_elements(By.XPATH, apply_coupon_xpath)
                
                for element in apply_coupon_elements:
                    text = element.text.strip()
                    self.logger.debug(f"发现Apply coupon元素: '{text}'")
                    
                    # 提取美元金额
                    import re
                    match = re.search(dollar_pattern, text)
                    if match:
                        amount = float(match.group(1))
                        self.logger.debug(f"从XPath提取到优惠券金额: ${amount}")
                        return "fixed", amount
            except Exception as e:
                self.logger.debug(f"XPath方法提取优惠券失败: {str(e)}")
            
            # 检查优惠券特定元素
            coupon_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-section .couponBadge")
            for element in coupon_elements:
                text = element.text.strip().lower()
                if self.debug:
                    self.logger.debug(f"发现优惠券徽章: '{text}'")
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
                        
            # 方法1: 检查a-color-success元素，这是您提供的HTML中使用的类
            success_elements = self.driver.find_elements(By.CSS_SELECTOR, ".a-color-success")
            for element in success_elements:
                text = element.text.strip()
                if self.debug:
                    self.logger.debug(f"发现a-color-success元素: '{text}'")
                
                # 检查是否有"apply $X coupon"文本
                if ("Apply $" in text or "apply $" in text) and "coupon" in text:
                    try:
                        # 提取优惠券金额
                        import re
                        match = re.search(dollar_pattern, text)
                        if match:
                            amount = float(match.group(1))
                            self.logger.debug(f"从a-color-success元素提取到优惠券金额: ${amount}")
                            return "fixed", amount
                    except Exception as e:
                        self.logger.warning(f"无法从a-color-success元素提取金额: {text}, 错误: {str(e)}")
            
            # 方法2: 检查包含"Apply $X coupon"的促销价格信息元素
            promo_elements = self.driver.find_elements(By.CSS_SELECTOR, ".promoPriceBlockMessage")
            for element in promo_elements:
                text = element.text.strip().lower()
                if self.debug:
                    self.logger.debug(f"发现促销价格元素: '{text}'")
                
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
            
            # 方法3: 检查checkbox和label中的优惠券信息
            try:
                coupon_labels = self.driver.find_elements(By.CSS_SELECTOR, "label[for^='checkbox']")
                for label in coupon_labels:
                    text = label.text.strip()
                    if self.debug:
                        self.logger.debug(f"发现label元素: '{text}'")
                    
                    if ("Apply $" in text or "apply $" in text) and "coupon" in text:
                        try:
                            # 使用正则表达式提取金额
                            import re
                            match = re.search(dollar_pattern, text)
                            if match:
                                amount = float(match.group(1))
                                self.logger.debug(f"从label元素提取到优惠券金额: ${amount}")
                                return "fixed", amount
                        except Exception as e:
                            self.logger.warning(f"无法从label文本中提取金额: {text}, 错误: {str(e)}")
                    elif "%" in text and "coupon" in text:
                        try:
                            # 使用正则表达式提取百分比
                            import re
                            match = re.search(percentage_pattern, text)
                            if match:
                                percentage = float(match.group(1))
                                self.logger.debug(f"从label元素提取到百分比优惠券: {percentage}%")
                                return "percentage", percentage
                        except Exception as e:
                            self.logger.warning(f"无法从label文本中提取百分比: {text}, 错误: {str(e)}")
            except Exception as e:
                self.logger.debug(f"检查label元素失败: {str(e)}")
            
            # 方法4: 检查span元素中的优惠券信息（针对您提供的HTML格式）
            try:
                span_elements = self.driver.find_elements(By.CSS_SELECTOR, "span.a-color-success")
                for span in span_elements:
                    text = span.text.strip()
                    if self.debug:
                        self.logger.debug(f"发现span.a-color-success元素: '{text}'")
                    
                    if "Apply $" in text and "coupon" in text:
                        # 使用正则表达式提取金额
                        import re
                        match = re.search(dollar_pattern, text)
                        if match:
                            amount = float(match.group(1))
                            self.logger.debug(f"从span元素提取到优惠券金额: ${amount}")
                            return "fixed", amount
            except Exception as e:
                self.logger.debug(f"检查span元素失败: {str(e)}")
            
            # 方法5: 更通用的方法，尝试在整个页面中查找包含"coupon"的元素
            try:
                coupon_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'coupon')]")
                for element in coupon_elements:
                    text = element.text.strip()
                    if not text:  # 跳过空文本
                        continue
                        
                    if self.debug and ("$" in text or "%" in text):
                        self.logger.debug(f"发现包含'coupon'的元素: '{text}'")
                    
                    # 检查美元金额
                    if "$" in text:
                        # 使用正则表达式提取金额
                        import re
                        match = re.search(dollar_pattern, text)
                        if match and "coupon" in text.lower():
                            amount = float(match.group(1))
                            self.logger.debug(f"从通用元素提取到优惠券金额: ${amount}")
                            return "fixed", amount
                    
                    # 检查百分比
                    if "%" in text:
                        # 使用正则表达式提取百分比
                        import re
                        match = re.search(percentage_pattern, text)
                        if match and "coupon" in text.lower():
                            percentage = float(match.group(1))
                            self.logger.debug(f"从通用元素提取到百分比优惠券: {percentage}%")
                            return "percentage", percentage
            except Exception as e:
                self.logger.debug(f"通用元素搜索失败: {str(e)}")
            
            # 如果在调试模式下，打印所有潜在的优惠券元素的HTML
            if self.debug and self.verbose:
                self.logger.debug("未找到优惠券信息，尝试分析页面结构...")
                try:
                    # 搜索任何可能包含优惠券信息的元素
                    potential_elements = self.driver.find_elements(By.XPATH, 
                        "//*[contains(text(), 'coupon') or contains(text(), 'Coupon') or contains(text(), 'COUPON')]")
                    
                    if potential_elements:
                        self.logger.debug(f"找到{len(potential_elements)}个可能包含优惠券信息的元素:")
                        for i, elem in enumerate(potential_elements[:5]):  # 只记录前5个避免日志过大
                            self.logger.debug(f"潜在元素 {i+1}: 文本='{elem.text}', 标签='{elem.tag_name}'")
                    else:
                        self.logger.debug("未找到包含'coupon'关键词的元素")
                except Exception as e:
                    self.logger.debug(f"分析页面结构失败: {str(e)}")
                
        except Exception as e:
            self.logger.warning(f"提取优惠券信息失败: {str(e)}")
            if self.debug:
                import traceback
                self.logger.debug(f"优惠券提取异常堆栈: {traceback.format_exc()}")
        
        if self.debug:
            self.logger.debug("未能提取到任何优惠券信息")
        return None, None
    
    def _update_product_coupon(self, product: Product, coupon_type: str, coupon_value: float):
        """更新商品优惠券信息"""
        self.logger.info(f"更新商品 {product.asin} 的优惠券信息")
        
        # 如果没有优惠券信息，删除商品记录（而不是跳过）
        if coupon_type is None:
            self.logger.info(f"商品 {product.asin} 没有优惠券信息，将从数据库中删除")
            try:
                # 删除关联的优惠信息
                if product.offers:
                    for offer in product.offers:
                        self.db.delete(offer)
                    
                # 删除商品记录
                self.db.delete(product)
                self.db.commit()
                self.logger.info(f"成功从数据库删除商品: {product.asin}")
            except Exception as e:
                self.db.rollback()
                self.logger.error(f"删除商品记录失败: {str(e)}")
                import traceback
                self.logger.debug(f"删除异常堆栈: {traceback.format_exc()}")
            return
            
        # 如果没有优惠信息记录，创建一个新的
        if not product.offers:
            offer = Offer(product_id=product.asin)
            product.offers.append(offer)
            self.logger.info(f"创建新的优惠信息记录")
        
        # 获取当前的offer
        offer = product.offers[0]
        updated_fields = []
        
        # 更新coupon_type
        if offer.coupon_type != coupon_type and (coupon_type is not None or offer.coupon_type is not None):
            updated_fields.append(f"优惠券类型: {offer.coupon_type} -> {coupon_type}")
            offer.coupon_type = coupon_type
            self.stats['updated_fields']['coupon_type'] += 1
        
        # 更新coupon_value
        if offer.coupon_value != coupon_value and (coupon_value is not None or offer.coupon_value is not None):
            updated_fields.append(f"优惠券金额: {offer.coupon_value} -> {coupon_value}")
            offer.coupon_value = coupon_value
            self.stats['updated_fields']['coupon_value'] += 1
        
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
        
        # 如果有字段更新，记录详情
        if updated_fields:
            self.logger.info(f"优惠券信息更新: {'; '.join(updated_fields)}")
        else:
            self.logger.debug(f"商品优惠券信息无变化")
        
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
            self.logger.info(f"开始处理商品: {url}")
            
            # 添加页面加载超时处理
            try:
                self.driver.set_page_load_timeout(60)
                self.driver.set_script_timeout(30)
                
                try:
                    self.driver.get(url)
                except TimeoutException:
                    self.logger.warning(f"页面加载超时，尝试停止加载并继续处理")
                    try:
                        self.driver.execute_script("window.stop();")
                    except Exception as e:
                        self.logger.error(f"停止页面加载失败: {str(e)}")
                        return False
            except Exception as e:
                self.logger.error(f"访问页面时出错: {str(e)}")
                
                try:
                    self.driver.execute_script("return navigator.userAgent;")
                    self.logger.info("WebDriver仍然响应，继续处理")
                except:
                    self.logger.error("WebDriver无响应，放弃处理该商品")
                    return False
            
            # 随机等待1-3秒，模拟人类行为
            wait_time = random.uniform(1, 3)
            self.logger.debug(f"等待页面加载: {wait_time:.1f}秒")
            time.sleep(wait_time)
            
            # 提取优惠券信息
            self.logger.debug("提取优惠券信息...")
            coupon_type, coupon_value = self._extract_coupon_info()
            
            # 记录提取到的信息
            coupon_value_str = str(coupon_value) if coupon_value is not None else "无"
            self.logger.info(f"优惠券信息提取结果: 类型={coupon_type}, 值={coupon_value_str}")
            
            # 更新数据库
            self.logger.debug("更新数据库...")
            self._update_product_coupon(product, coupon_type, coupon_value)
            
            self.db.commit()
            self.logger.info(f"商品优惠券信息更新成功")
            return True
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"处理失败: {str(e)}")
            # 记录详细的异常堆栈信息
            import traceback
            self.logger.debug(f"异常堆栈: {traceback.format_exc()}")
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
            self.logger.debug(f"商品已处理过: {asin}")
            return True
        
        # 尝试从数据库获取商品
        self.logger.info(f"查询数据库中的商品信息")
        product = self.db.query(Product).filter(Product.asin == asin).first()
        
        # 如果数据库中不存在该商品，则创建一个新的记录
        if not product:
            self.logger.info(f"数据库中不存在商品，创建新记录 (source='coupon')")
            product = Product(asin=asin, created_at=datetime.now(UTC), source='coupon')
            self.db.add(product)
            try:
                self.logger.debug(f"刷新数据库以获取ID")
                self.db.flush()  # 刷新以获取ID，但不提交
            except Exception as e:
                self.logger.error(f"创建商品记录失败: {str(e)}")
                self.db.rollback()
                return False
        # 验证商品是否为'coupon'来源
        elif product.source != 'coupon':
            self.logger.warning(f"跳过非'coupon'来源的商品: {asin} (source={product.source})")
            return False
        
        # 处理商品优惠券信息
        success = self.process_product(product)
        
        # 如果处理成功，将商品ASIN添加到已处理集合中
        if success:
            self._processed_asins.add(asin)
            
        return success

    def run(self):
        """运行抓取器"""
        self.stats['start_time'] = time.time()
        
        try:
            self.logger.info("初始化WebDriver...")
            self._init_driver()
            
            self.logger.info("=====================================================")
            self.logger.info("              开始优惠券信息抓取任务")
            self.logger.info("=====================================================")
            
            # 处理特定的ASIN列表或从数据库获取商品
            if self.specific_asins:
                self.logger.info(f"将处理指定的 {len(self.specific_asins)} 个商品ASIN")
                asins_to_process = self.specific_asins
            else:
                # 获取商品，仅处理source为'coupon'的商品
                self.logger.info("从数据库获取待处理商品列表 (仅source='coupon')...")
                products = self.db.query(Product).filter(
                    Product.source == 'coupon'
                ).order_by(
                    Product.created_at
                ).limit(self.batch_size).all()
                
                asins_to_process = [p.asin for p in products]
                self.logger.info(f"获取到 {len(asins_to_process)} 个待处理商品")
            
            # 使用tqdm添加进度条
            for idx, asin in enumerate(tqdm(asins_to_process, desc="处理商品"), 1):
                self.logger.info(f"处理商品 ASIN: {asin} ({idx}/{len(asins_to_process)})")
                
                # 验证商品是否为'coupon'来源（如果是特定ASIN列表）
                if self.specific_asins:
                    product = self.db.query(Product).filter(Product.asin == asin).first()
                    if product and product.source != 'coupon':
                        self.logger.warning(f"跳过非'coupon'来源的商品: {asin} (source={product.source})")
                        continue
                
                # 处理商品
                success = self.process_asin(asin)
                self.stats['processed_count'] += 1
                
                if success:
                    self.stats['success_count'] += 1
                    self.logger.info(f"商品处理成功")
                    # 成功后等待随机时间
                    delay = random.uniform(self.min_delay, self.max_delay)
                    self.logger.debug(f"等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                else:
                    self.stats['failure_count'] += 1
                    self.logger.warning(f"商品处理失败")
                    # 失败后等待较长时间
                    delay = random.uniform(5, 10)
                    self.logger.debug(f"失败后等待 {delay:.1f} 秒...")
                    time.sleep(delay)
            
        except Exception as e:
            self.logger.error(f"抓取过程发生错误: {str(e)}")
            # 记录详细的异常堆栈信息
            import traceback
            self.logger.debug(f"异常堆栈: {traceback.format_exc()}")
            raise
            
        finally:
            self.logger.info("关闭WebDriver...")
            self._close_driver()
            
            # 输出任务统计信息
            self.stats['end_time'] = time.time()
            duration = self.stats['end_time'] - self.stats['start_time']
            
            self.logger.info("=====================================================")
            self.logger.info("                  任务完成")
            self.logger.info("=====================================================")
            self.logger.info(f"任务统计:")
            self.logger.info(f"  • 总耗时: {duration:.1f} 秒")
            self.logger.info(f"  • 处理商品: {self.stats['processed_count']} 个")
            self.logger.info(f"  • 成功更新: {self.stats['success_count']} 个")
            self.logger.info(f"  • 失败数量: {self.stats['failure_count']} 个")
            success_rate = (self.stats['success_count']/self.stats['processed_count']*100) if self.stats['processed_count'] > 0 else 0
            self.logger.info(f"  • 成功率: {success_rate:.1f}%")
            self.logger.info(f"  • 平均速度: {self.stats['processed_count']/duration:.2f} 个/秒" if duration > 0 else "N/A")
            
            # 添加字段更新统计信息
            self.logger.info("\n字段更新统计:")
            self.logger.info(f"  • 更新优惠券类型: {self.stats['updated_fields']['coupon_type']} 个")
            self.logger.info(f"  • 更新优惠券值: {self.stats['updated_fields']['coupon_value']} 个")

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

    # 初始化数据库会话
    db = next(get_db())
    
    # 初始化爬虫
    scraper = CouponScraper(
        db=db,
        batch_size=args.batch_size,
        headless=not args.no_headless,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        specific_asins=specific_asins,
        debug=args.debug,
        verbose=args.verbose
    )
    
    try:
        # 输出调试信息
        if args.debug:
            logger.debug("===== 启动参数 =====")
            logger.debug(f"批处理大小: {args.batch_size}")
            logger.debug(f"无头模式: {not args.no_headless}")
            logger.debug(f"最小延迟: {args.min_delay}秒")
            logger.debug(f"最大延迟: {args.max_delay}秒")
            logger.debug(f"指定ASIN: {specific_asins}")
            logger.debug(f"调试模式: {args.debug}")
            logger.debug(f"详细输出: {args.verbose}")
            logger.debug(f"日志级别: {args.log_level or ('DEBUG' if args.debug else 'INFO')}")
            logger.debug("===================")
        
        # 运行爬虫
        scraper.run()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止爬虫...")
    finally:
        # 关闭数据库连接
        db.close()

if __name__ == "__main__":
    main() 