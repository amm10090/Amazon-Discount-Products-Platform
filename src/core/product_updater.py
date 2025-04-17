"""
商品更新管理模块

该模块提供对商品数据的定期更新功能，包括：
1. 删除价格为0的商品
2. 检查商品在CJ平台的可用性
3. 更新商品的CJ推广链接
4. 获取商品最新价格、库存和优惠信息
5. 更新数据库中的商品记录
6. 检查优惠券信息（针对Coupon来源的商品）

主要组件：
- ProductUpdater: 商品更新管理类，提供单个和批量商品更新方法
- 优先级调度: 基于商品热度和更新时间的优先级计算

更新策略：
1. 首先删除所有价格为0的商品
2. 对剩余商品检查CJ平台可用性
3. 对于CJ平台有的商品，获取CJ推广链接和详情
4. 使用PAAPI获取最新的商品数据
5. 集成来自不同来源的数据
6. 更新数据库记录
"""

import os
import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta, UTC
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from enum import Enum
import random
from tqdm import tqdm  # 添加tqdm库支持进度条
import time

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.core.amazon_product_api import AmazonProductAPI
from src.core.cj_api_client import CJAPIClient
from models.database import SessionLocal, Product, Offer
from models.product import ProductInfo, ProductOffer
from models.product_service import ProductService
from src.utils.log_config import get_logger, LogContext, track_performance
from src.utils.api_retry import with_retry
from src.utils.config_loader import config_loader
from src.core.discount_scraper_mt import CouponScraperMT
from src.core.discount_scraper import CouponScraper

class TaskLogContext:
    """
    任务日志上下文管理器
    
    提供任务级别的日志上下文管理，自动添加任务ID和其他上下文信息到日志记录。
    支持同步和异步操作。
    
    示例:
        with TaskLogContext(task_id="task123", operation="update") as task_log:
            task_log.info("开始处理任务")
            # ... 执行任务 ...
            task_log.success("任务完成")
    """
    
    def __init__(self, task_id: str = "SYSTEM", **kwargs):
        """
        初始化任务日志上下文
        
        Args:
            task_id: 任务ID，默认为"SYSTEM"
            **kwargs: 其他上下文信息
        """
        self.context_data = {"task_id": task_id, "name": "ProductUpdater"}
        self.context_data.update(kwargs)
        
        # 使用环境变量中的日志目录
        log_dir = Path(os.getenv("APP_LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        self._logger = get_logger(name="ProductUpdater")
        self._log_context = LogContext(**self.context_data)
        self._bound_logger = None
        
    def __enter__(self):
        """进入上下文，设置日志上下文"""
        self._log_context.__enter__()
        self._bound_logger = self._logger.bind(**self.context_data)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，清理日志上下文"""
        try:
            if exc_type is not None:
                # 如果发生异常，记录错误信息
                self.error(f"任务执行出错: {str(exc_val)}")
        finally:
            self._log_context.__exit__(exc_type, exc_val, exc_tb)
            self._bound_logger = None
    
    async def __aenter__(self):
        """异步进入上下文"""
        await self._log_context.__aenter__()
        self._bound_logger = self._logger.bind(**self.context_data)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步退出上下文"""
        try:
            if exc_type is not None:
                # 如果发生异常，记录错误信息
                self.error(f"任务执行出错: {str(exc_val)}")
        finally:
            await self._log_context.__aexit__(exc_type, exc_val, exc_tb)
            self._bound_logger = None
        
    def info(self, message: str):
        """记录INFO级别日志"""
        if self._bound_logger:
            self._bound_logger.info(message)
        else:
            self._logger.bind(**self.context_data).info(message)
        
    def debug(self, message: str):
        """记录DEBUG级别日志"""
        if self._bound_logger:
            self._bound_logger.debug(message)
        else:
            self._logger.bind(**self.context_data).debug(message)
        
    def warning(self, message: str):
        """记录WARNING级别日志"""
        if self._bound_logger:
            self._bound_logger.warning(message)
        else:
            self._logger.bind(**self.context_data).warning(message)
        
    def error(self, message: str):
        """记录ERROR级别日志"""
        if self._bound_logger:
            self._bound_logger.error(message)
        else:
            self._logger.bind(**self.context_data).error(message)
        
    def success(self, message: str):
        """记录SUCCESS级别日志"""
        if self._bound_logger:
            self._bound_logger.success(message)
        else:
            self._logger.bind(**self.context_data).success(message)

# 在时间维度上，如何调度不同商品的更新频率
class UpdatePriority(Enum):
    """商品更新优先级枚举"""
    URGENT = "urgent"    # 紧急优先级，立即更新（价格为0的商品）
    HIGH = "high"       # 高优先级，每天更新多次
    MEDIUM = "medium"   # 中优先级，每天更新1次
    LOW = "low"         # 低优先级，每3天更新1次
    VERY_LOW = "very_low"  # 非常低优先级，每周更新1次

class UpdateConfiguration:
    """更新配置类"""
    def __init__(self, 
                 urgent_priority_hours: int = 1,        # 紧急优先级商品更新间隔（小时）
                 high_priority_hours: int = 6,        # 高优先级商品更新间隔（小时）
                 medium_priority_hours: int = 24,     # 中优先级商品更新间隔（小时）
                 low_priority_hours: int = 72,        # 低优先级商品更新间隔（小时）
                 very_low_priority_hours: int = 168,  # 非常低优先级商品更新间隔（小时）
                 batch_size: int = 500,                # 每批处理的商品数量
                 max_retries: int = 3,                # 最大重试次数
                 retry_delay: float = 2.0,            # 重试延迟时间（秒）
                 update_category_info: bool = False,  # 是否更新品类信息（不常变化）
                 force_cj_check: bool = False,        # 是否强制检查CJ平台
                 parallel_requests: int = 5,          # 并行请求数量
                 ):
        self.priority_hours = {
            UpdatePriority.URGENT: urgent_priority_hours,
            UpdatePriority.HIGH: high_priority_hours,
            UpdatePriority.MEDIUM: medium_priority_hours,
            UpdatePriority.LOW: low_priority_hours,
            UpdatePriority.VERY_LOW: very_low_priority_hours
        }
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.update_category_info = update_category_info
        self.force_cj_check = force_cj_check
        self.parallel_requests = parallel_requests

    @classmethod
    def from_config(cls, config_path: str = "config/update_config.yaml") -> "UpdateConfiguration":
        """从配置文件加载配置"""
        try:
            config = config_loader.load_yaml_config(config_path)
            if not config:
                logger = get_logger("ProductUpdater")
                logger.warning(f"无法加载配置文件: {config_path}，使用默认配置")
                return cls()
                
            return cls(
                urgent_priority_hours=config.get('priority_hours', {}).get('urgent', 1),
                high_priority_hours=config.get('priority_hours', {}).get('high', 6),
                medium_priority_hours=config.get('priority_hours', {}).get('medium', 24),
                low_priority_hours=config.get('priority_hours', {}).get('low', 72),
                very_low_priority_hours=config.get('priority_hours', {}).get('very_low', 168),
                batch_size=config.get('batch_size', 10),
                max_retries=config.get('max_retries', 3),
                retry_delay=config.get('retry_delay', 2.0),
                update_category_info=config.get('update_category_info', False),
                force_cj_check=config.get('force_cj_check', False),
                parallel_requests=config.get('parallel_requests', 5)
            )
        except Exception as e:
            logger = get_logger("ProductUpdater")
            logger.error(f"加载配置文件出错: {str(e)}")
            return cls()
            
class ProductUpdater:
    """商品更新管理类"""
    
    def __init__(self, config: Optional[UpdateConfiguration] = None):
        """
        初始化商品更新管理器
        
        Args:
            config: 更新配置，如果为None则使用默认配置
        """
        self.config = config or UpdateConfiguration()
        self.amazon_api = None
        self.cj_client = None
        self.logger = get_logger("ProductUpdater")
        
        # API请求限制相关变量
        self.last_pa_api_request_time = None
        self.pa_api_request_interval = 2.0  # 增加到2秒以避免429错误
        self.last_cj_api_request_time = None
        self.cj_api_request_interval = 0.5
        
        # 优惠券检查相关配置
        self.coupon_check_retry_count = 2
        self.coupon_check_retry_delay = 5
        self.coupon_scraper = None
        
    async def initialize_clients(self):
        """初始化API客户端"""
        # 获取环境变量
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            self.logger.error("缺少必要的Amazon PA-API凭证")
            raise ValueError("请检查环境变量设置: AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG")
        
        # 初始化PA-API客户端
        self.logger.info("正在初始化Amazon Product API客户端...")
        self.amazon_api = AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        
        # 添加兼容层，确保API调用正常工作
        self.logger.debug("添加PAAPI兼容层...")
        # 如果amazon_api没有get_items方法，但有get_products_by_asins方法
        if not hasattr(self.amazon_api, "get_items") and hasattr(self.amazon_api, "get_products_by_asins"):
            # 添加对get_items的兼容支持，调用get_products_by_asins
            self.amazon_api.get_items = self.amazon_api.get_products_by_asins
            self.logger.debug("已添加get_items兼容方法，映射到get_products_by_asins")
        
        # 初始化CJ客户端
        self.logger.info("正在初始化CJ API客户端...")
        self.cj_client = CJAPIClient()
        
        self.logger.success("API客户端初始化完成")
        
    async def _rate_limit_pa_api(self):
        """限制PA API请求频率，避免429错误"""
        now = datetime.now(UTC)
        if self.last_pa_api_request_time:
            # 确保last_pa_api_request_time有时区信息
            last_time = self.last_pa_api_request_time
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=UTC)
                
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.pa_api_request_interval:
                wait_time = self.pa_api_request_interval - elapsed
                await asyncio.sleep(wait_time)
        self.last_pa_api_request_time = now
        
    async def _rate_limit_cj_api(self):
        """限制CJ API请求频率"""
        now = datetime.now(UTC)
        if self.last_cj_api_request_time:
            # 确保last_cj_api_request_time有时区信息
            last_time = self.last_cj_api_request_time
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=UTC)
                
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.cj_api_request_interval:
                wait_time = self.cj_api_request_interval - elapsed
                await asyncio.sleep(wait_time)
        self.last_cj_api_request_time = now
        
    def _calculate_priority(self, product: Product) -> UpdatePriority:
        """
        计算商品的更新优先级
        
        优先级计算基于：
        1. 创建时间（越早创建优先级越高）
        2. 上次更新时间（越久未更新优先级越高）
        3. CJ平台状态（CJ平台商品优先级更高）
        4. 随机因素（防止所有同类商品在同一时间更新）
        
        Args:
            product: 商品数据库记录
            
        Returns:
            UpdatePriority: 商品更新优先级
        """
        # 基础得分
        score = 0
        
        now = datetime.now(UTC)
        
        # 1. 基于创建时间计算得分
        if product.created_at:
            # 确保created_at有时区信息
            created_at = product.created_at.replace(tzinfo=UTC) if product.created_at.tzinfo is None else product.created_at
            days_since_creation = (now - created_at).days
            # 每30天增加5分，最多25分
            creation_score = min(days_since_creation // 30 * 5, 25)
            score += creation_score
            
        # 2. 基于更新时间计算得分
        if product.updated_at:
            # 确保updated_at有时区信息
            updated_at = product.updated_at.replace(tzinfo=UTC) if product.updated_at.tzinfo is None else product.updated_at
            hours_since_update = (now - updated_at).total_seconds() / 3600
            # 每24小时增加10分，最多30分
            update_score = min(hours_since_update / 24 * 10, 30)
            score += update_score
        else:
            # 如果从未更新过，给予最高更新时间得分
            score += 30
            
        # 3. CJ商品优先级加分
        if product.api_provider == 'cj-api' or product.cj_url:
            score += 20
            
        # 4. 添加随机因素（-5到5分）防止更新扎堆
        score += random.randint(-5, 5)
        
        # 根据最终得分确定优先级
        if score >= 60:  # 创建很久 + 更新很久 + CJ平台
            return UpdatePriority.HIGH
        elif score >= 40:  # 创建较久或更新较久 + CJ平台
            return UpdatePriority.MEDIUM
        elif score >= 20:  # 创建较久或更新较久
            return UpdatePriority.LOW
        else:
            return UpdatePriority.VERY_LOW
            
    def _should_update(self, product: Product) -> bool:
        """判断商品是否需要更新
        
        基于上次更新时间和商品优先级决定是否需要更新
        对于价格为0的商品，忽略更新间隔，直接返回True
        
        Args:
            product: 商品数据库记录
            
        Returns:
            bool: 是否需要更新
        """
        # 如果价格为0，立即更新
        if product.current_price == 0:
            return True
        
        # 如果没有更新时间，则需要更新
        if not product.updated_at:
            return True
        
        # 计算商品优先级
        priority = self._calculate_priority(product)
        
        # 获取当前时间
        now = datetime.now(UTC)
        
        # 确保updated_at有时区信息
        updated_at = product.updated_at.replace(tzinfo=UTC) if product.updated_at.tzinfo is None else product.updated_at
        
        # 获取该优先级的更新间隔时间
        hours = self.config.priority_hours[priority]
        
        # 计算上次更新到现在的时间间隔
        time_since_update = now - updated_at
        
        # 基础判断：如果时间间隔大于更新间隔，则需要更新
        if time_since_update > timedelta(hours=hours):
            return True
            
        # 添加智能调度策略：负载均衡
        # 对于接近更新时间的商品，根据当前系统负载随机选择一部分更新
        # 这样可以避免所有商品都在同一时间点需要更新
        if time_since_update > timedelta(hours=hours * 0.9):
            # 创建一个基于ASIN的确定性随机数，确保同一商品在短时间内得到一致的结果
            try:
                # 使用ASIN的哈希值作为种子，更安全且适用于所有ASIN格式
                seed = hash(product.asin) % 10000
                random.seed(seed + int(now.timestamp() / 3600))  # 每小时变化一次
                
                # 高优先级的商品有更高概率被提前更新
                chance = {
                    UpdatePriority.HIGH: 0.4,      # 高优先级有40%概率被提前更新
                    UpdatePriority.MEDIUM: 0.2,    # 中优先级有20%概率被提前更新
                    UpdatePriority.LOW: 0.1,       # 低优先级有10%概率被提前更新
                    UpdatePriority.VERY_LOW: 0.05  # 非常低优先级有5%概率被提前更新
                }.get(priority, 0)
                
                return random.random() < chance
            except Exception as e:
                # 如果计算随机概率时出错，默认不更新
                return False
            
        return False
    
    @track_performance
    async def delete_zero_price_products(self, db: Session) -> int:
        """删除所有价格为0或null的商品"""
        deleted_count = 0
        
        with TaskLogContext(task_id='DELETE_BATCH'):
            self.logger.info("开始删除价格为0或null的商品")
            
            try:
                # 查询价格为0或null的商品
                products = db.query(Product).filter(
                    (Product.current_price == 0) | (Product.current_price == None)
                ).all()
                
                if not products:
                    self.logger.info("没有找到价格为0或null的商品")
                    return 0
                    
                self.logger.info(f"找到{len(products)}个价格为0或null的商品")
                
                # 使用进度条显示删除进度
                for product in tqdm(products, desc="删除价格为0的商品"):
                    with TaskLogContext(task_id=f"DELETE:{product.asin}"):
                        if await self.delete_product(product, db, "价格为0或null"):
                            deleted_count += 1
                
                self.logger.success(f"成功删除了{deleted_count}个价格为0或null的商品")
                return deleted_count
                
            except Exception as e:
                self.logger.error(f"删除价格为0的商品时出错: {str(e)}")
                return deleted_count
        
    async def delete_product(self, product: Product, db: Session, reason: str) -> bool:
        """删除单个商品
        
        Args:
            product: 要删除的商品
            db: 数据库会话
            reason: 删除原因
            
        Returns:
            bool: 删除是否成功
        """
        with TaskLogContext(task_id=f"DELETE:{product.asin}"):
            try:
                db.delete(product)
                db.commit()
                self.logger.info(f"已删除商品: ASIN={product.asin}, 原因={reason}")
                return True
            except Exception as e:
                self.logger.error(f"删除商品失败 {product.asin}: {str(e)}")
                db.rollback()
                return False

    async def get_products_to_update(self, db: Session, limit: int = 100) -> List[Product]:
        """获取需要更新的商品列表"""
        with TaskLogContext(task_id='QUERY'):
            # 首先删除所有价格为0的商品
            deleted_count = await self.delete_zero_price_products(db)
            if deleted_count > 0:
                self.logger.info(f"已删除 {deleted_count} 个价格异常的商品")
            
            # 获取需要更新的常规商品
            regular_products = []
            
            # 按照上次更新时间升序排序，优先更新最久未更新的商品
            products = db.query(Product).filter(
                Product.current_price != 0
            ).order_by(
                Product.updated_at.asc().nulls_first()
            ).all()
            
            self.logger.info(f"数据库中共找到 {len(products)} 个商品")
            
            # 筛选需要更新的商品
            self.logger.info(f"正在筛选需要更新的商品...")
            selection_count = 0
            total_need_update = 0
            
            for product in products:
                try:
                    if self._should_update(product):
                        total_need_update += 1
                        # 如果未达到limit限制，添加到更新列表
                        if len(regular_products) < limit:
                            # 记录每个选中商品的详细信息（降级为DEBUG）
                            priority = self._calculate_priority(product)
                            last_update = product.updated_at.strftime('%Y-%m-%d %H:%M:%S') if product.updated_at else "从未更新"
                            self.logger.debug(
                                f"选中商品更新: ASIN={product.asin}, "
                                f"最后更新时间={last_update}, "
                                f"优先级={priority.value}, "
                                f"API来源={product.api_provider or 'unknown'}"
                            )
                            regular_products.append(product)
                            selection_count += 1
                            # 显示选择进度
                            if selection_count % 100 == 0:
                                self.logger.debug(f"已选择 {selection_count} 个商品...")
                except Exception as e:
                    self.logger.debug(f"商品 {product.asin} 检查更新状态时出错: {str(e)}，已跳过")
                    continue
            
            # 只在INFO级别记录汇总信息
            cj_count = sum(1 for p in regular_products if p.api_provider == 'cj-api')
            pa_count = sum(1 for p in regular_products if p.api_provider == 'pa-api')
            self.logger.info(
                f"找到 {len(regular_products)} 个商品需要更新 (CJ商品: {cj_count}, PA商品: {pa_count}), "
                f"数据库中还有 {total_need_update - len(regular_products)} 个商品等待更新"
            )
            return regular_products
        
    @track_performance
    async def process_product_update(self, product: Product, db: Session) -> bool:
        """处理单个商品的更新"""
        with TaskLogContext(task_id=f"UPDATE:{product.asin}"):
            try:
                # 1. 检查CJ平台可用性
                self.logger.debug("检查CJ平台可用性")
                cj_availability = await self.cj_client.check_products_availability([product.asin])
                is_cj_available = cj_availability.get(product.asin, False)
                
                # 2. 如果CJ平台可用，获取推广链接
                if is_cj_available:
                    self.logger.debug("商品在CJ平台可用，获取推广链接")
                    try:
                        cj_url = await self.cj_client.generate_product_link(product.asin)
                        product.cj_url = cj_url
                        product.api_provider = "cj-api"
                        self.logger.debug("成功获取CJ推广链接")
                    except Exception as e:
                        self.logger.warning(f"获取CJ推广链接失败: {str(e)}")
                        product.cj_url = None
                        product.api_provider = "pa-api"
                else:
                    self.logger.debug("商品在CJ平台不可用，使用PA-API")
                    product.cj_url = None
                    product.api_provider = "pa-api"
                
                # 3. 使用PAAPI获取商品详细信息
                self.logger.debug("从PAAPI获取商品信息")
                try:
                    pa_products = await self.amazon_api.get_products_by_asins([product.asin])
                    if not pa_products:
                        self.logger.error("无法从PAAPI获取商品信息，商品可能已下架或缺货")
                        return await self.delete_product(product, db, "商品不可用，无法从PAAPI获取信息")
                    
                    pa_info = pa_products[0]
                    
                    # 检查是否需要获取优惠券信息
                    if product.source and product.source.lower() in ['coupon', '/coupon']:
                        self.logger.info(f"检测到Coupon商品，开始检查优惠券信息")
                        coupon_type, coupon_value = await self.check_coupon_info(product, db)
                        
                        # 更新优惠券信息
                        if not product.offers:
                            offer = Offer(product_id=product.asin)
                            product.offers.append(offer)
                        else:
                            offer = product.offers[0]
                        
                        # 无论是否有优惠券信息都更新字段
                        offer.coupon_type = coupon_type
                        offer.coupon_value = coupon_value
                        offer.updated_at = datetime.now(UTC)
                        self.logger.info(
                            f"已更新优惠券信息: "
                            f"类型={coupon_type or '无'}, "
                            f"金额={coupon_value or '无'}"
                        )
                    
                    # 更新商品信息
                    if pa_info.offers:
                        product.current_price = pa_info.offers[0].price
                        product.stock = "in_stock" if pa_info.offers[0].availability == "Available" else "out_of_stock"
                        
                        # 更新折扣信息
                        savings = pa_info.offers[0].savings if hasattr(pa_info.offers[0], 'savings') else None
                        savings_percentage = pa_info.offers[0].savings_percentage if hasattr(pa_info.offers[0], 'savings_percentage') else None
                        
                        # 更新products表中的折扣信息
                        product.savings_amount = savings
                        product.savings_percentage = savings_percentage
                        
                        # 更新或创建offers表中的记录
                        if not product.offers:
                            offer = Offer(
                                product_id=product.asin,
                                savings=savings,
                                savings_percentage=savings_percentage,
                                updated_at=datetime.now(UTC)
                            )
                            product.offers.append(offer)
                        else:
                            offer = product.offers[0]
                            offer.savings = savings
                            offer.savings_percentage = savings_percentage
                            offer.updated_at = datetime.now(UTC)
                        
                        # 如果没有折扣，设置为None
                        if not savings and not savings_percentage:
                            product.original_price = product.current_price
                        else:
                            # 如果有折扣，计算原价
                            if savings:
                                product.original_price = product.current_price + savings
                            elif savings_percentage:
                                product.original_price = product.current_price / (1 - savings_percentage/100)
                    else:
                        product.current_price = 0
                        product.stock = "out_of_stock"
                        product.savings_amount = None
                        product.savings_percentage = None
                        product.original_price = None
                        
                        # 更新offers表
                        if product.offers:
                            offer = product.offers[0]
                            offer.savings = None
                            offer.savings_percentage = None
                            offer.updated_at = datetime.now(UTC)
                    
                    # 如果价格为0，删除商品
                    if product.current_price == 0:
                        self.logger.warning(f"商品价格为0，将删除商品: {product.asin}")
                        return await self.delete_product(product, db, "商品价格为0")
                    
                    # 更新商品的时间戳
                    product.timestamp = datetime.now(UTC)
                    # 更新商品的updated_at字段
                    product.updated_at = datetime.now(UTC)
                    
                    db.commit()
                    self.logger.debug(
                        f"商品信息更新成功: "
                        f"价格={product.current_price}, "
                        f"原价={product.original_price}, "
                        f"节省={product.savings_amount}, "
                        f"折扣比例={product.savings_percentage}%, "
                        f"库存={product.stock}"
                    )
                    return True
                    
                except Exception as e:
                    self.logger.error(f"PAAPI获取商品信息失败: {str(e)}")
                    db.rollback()
                    return False
                
            except Exception as e:
                self.logger.error(f"更新商品信息失败: {str(e)}")
                db.rollback()
                return False

    async def check_coupon_info(self, product: Product, db: Session) -> Tuple[str, float]:
        """
        检查商品的优惠券信息
        
        Args:
            product: 商品对象
            db: 数据库会话
            
        Returns:
            Tuple[str, float]: (优惠券类型, 优惠券金额)
        """
        task_id = f"COUPON:{product.asin}"
        with TaskLogContext(task_id=task_id):
            try:
                # 创建一个临时的CouponScraperMT实例，只处理单个商品
                temp_scraper = CouponScraperMT(
                    num_threads=1,         # 只使用1个线程
                    batch_size=1,          # 只处理1个商品
                    headless=True,         # 使用无头模式
                    min_delay=1.0,         # 最小延迟
                    max_delay=2.0,         # 最大延迟
                    specific_asins=[product.asin], # 只处理这个ASIN
                    debug=False,           # 不开启调试
                    verbose=False          # 不输出详细信息
                )
                
                # 运行爬虫处理商品
                temp_scraper.run()
                
                # 获取处理结果
                stats = temp_scraper.stats.get()
                
                # 如果成功处理了商品，从数据库中获取最新的优惠券信息
                if stats['success_count'] > 0:
                    # 刷新数据库中的商品信息
                    db.refresh(product)
                    
                    # 获取优惠券信息
                    if product.offers and len(product.offers) > 0:
                        offer = product.offers[0]
                        coupon_type = offer.coupon_type
                        coupon_value = offer.coupon_value
                        
                        self.logger.info(
                            f"优惠券检查结果: "
                            f"类型={coupon_type or '无'}, "
                            f"金额={coupon_value or '无'}"
                        )
                        
                        return coupon_type, coupon_value
                
                # 如果无法获取优惠券信息，返回None
                self.logger.info(f"商品 {product.asin} 没有优惠券信息")
                return None, None
                    
            except Exception as e:
                self.logger.error(f"检查优惠券信息时出错: {str(e)}")
                return None, None
                
    async def close_coupon_scraper(self):
        """关闭优惠券检查器（现在使用CouponScraperMT，不需要特别关闭资源）"""
        # CouponScraperMT会在run方法执行完毕后自动关闭资源
        self.coupon_scraper = None

    async def process_batch_cj_availability(self, asins: List[str]) -> Dict[str, bool]:
        """批量检查CJ平台商品可用性"""
        with TaskLogContext(task_id='CJ-CHECK') as log_ctx:
            batch_size = 10
            results = {}
            
            self.logger.info(f"开始检查 {len(asins)} 个商品的CJ平台可用性")
            
            # 使用tqdm添加进度条
            batch_count = (len(asins) + batch_size - 1) // batch_size  # 计算批次数
            with tqdm(total=batch_count, desc="检查CJ平台可用性") as pbar:
                for i in range(0, len(asins), batch_size):
                    batch_asins = asins[i:i + batch_size]
                    try:
                        self.logger.debug(f"检查CJ平台可用性: ASINs={batch_asins}")
                        
                        # 应用请求频率限制
                        await self._rate_limit_cj_api()
                        
                        batch_results = await self.cj_client.check_products_availability(batch_asins)
                        results.update(batch_results)
                        
                        # 记录可用和不可用的商品数量(DEBUG级别)
                        available_count = sum(1 for asin, available in batch_results.items() if available)
                        self.logger.debug(f"批次检查结果: 总数={len(batch_results)}, 可用={available_count}, 不可用={len(batch_results) - available_count}")
                        
                    except Exception as e:
                        self.logger.error(
                            f"批量检查CJ平台可用性失败: "
                            f"ASINs={batch_asins}, "
                            f"错误类型={type(e).__name__}, "
                            f"错误信息={str(e)}"
                        )
                        # 如果批处理失败，将该批次的所有商品标记为不可用
                        for asin in batch_asins:
                            results[asin] = False
                    
                    # 更新进度条
                    pbar.update(1)
                        
            # 输出最终结果
            available_count = sum(1 for asin, available in results.items() if available)
            self.logger.info(f"CJ平台检查完成: 总数={len(results)}, 可用={available_count}, 不可用={len(results) - available_count}")
            return results
            
    async def process_batch_cj_links(self, available_asins: List[str]) -> Dict[str, str]:
        """批量获取CJ推广链接"""
        with TaskLogContext(task_id='CJ-LINKS'):
            batch_size = 10
            results = {}
            
            if not available_asins:
                self.logger.info("没有可用的CJ商品，跳过获取推广链接")
                return results
                
            self.logger.info(f"开始获取 {len(available_asins)} 个商品的CJ推广链接")
            
            # 使用tqdm添加进度条
            with tqdm(total=len(available_asins), desc="获取CJ推广链接") as pbar:
                for i in range(0, len(available_asins), batch_size):
                    batch_asins = available_asins[i:i + batch_size]
                    self.logger.debug(f"获取CJ推广链接: ASINs={batch_asins}")
                    
                    for asin in batch_asins:
                        try:
                            # 每个链接请求都应用请求频率限制
                            await self._rate_limit_cj_api()
                            
                            link = await self.cj_client.generate_product_link(asin)
                            results[asin] = link
                            self.logger.debug(f"成功获取CJ推广链接: ASIN={asin}")
                            
                        except Exception as e:
                            self.logger.error(
                                f"获取商品 {asin} 的CJ推广链接失败: "
                                f"错误类型={type(e).__name__}, "
                                f"错误信息={str(e)}"
                            )
                            results[asin] = None
                        
                        # 更新进度条
                        pbar.update(1)
                        
            # 输出最终结果
            success_count = sum(1 for link in results.values() if link)
            self.logger.info(f"CJ推广链接获取完成: 总数={len(results)}, 成功={success_count}, 失败={len(results) - success_count}")
            return results
        
    async def process_batch_pa_api(self, products: List[Product]) -> Dict[str, Dict]:
        """批量获取PA API商品信息"""
        with TaskLogContext(task_id='PAAPI'):
            results = {}
            
            # 只在INFO级别输出开始和结束信息
            self.logger.info(f"开始获取 {len(products)} 个商品的PAAPI信息")
            
            # 按10个商品一组进行批处理
            batch_count = (len(products) + 9) // 10  # 计算批次数
            with tqdm(total=batch_count, desc="获取PAAPI信息") as pbar:
                for i in range(0, len(products), 10):
                    batch = products[i:i+10]
                    asins = [p.asin for p in batch]
                    try:
                        self.logger.debug(f"开始获取PAAPI信息: ASINs={asins}")
                        
                        # 应用请求频率限制
                        await self._rate_limit_pa_api()
                        
                        # 使用正确的方法名 get_products_by_asins 替代 get_items
                        pa_products = await self.amazon_api.get_products_by_asins(asins)
                        
                        # 处理返回的产品信息
                        for product in pa_products:
                            if not product:
                                continue
                                
                            # 记录成功获取的商品信息(DEBUG级别)
                            price = product.offers[0].price if product.offers else 0
                            in_stock = "Available" == product.offers[0].availability if product.offers else False
                            
                            # 获取折扣信息
                            savings = product.offers[0].savings if product.offers and hasattr(product.offers[0], 'savings') else None
                            savings_percentage = product.offers[0].savings_percentage if product.offers and hasattr(product.offers[0], 'savings_percentage') else None
                            
                            results[product.asin] = {
                                'price': price,
                                'stock': in_stock,
                                'title': product.title if hasattr(product, 'title') else '',
                                'availability_status': product.offers[0].availability if product.offers else 'Unavailable',
                                'savings': savings,
                                'savings_percentage': savings_percentage
                            }
                            
                            self.logger.debug(
                                f"成功获取商品信息: ASIN={product.asin}, "
                                f"价格={price}, "
                                f"节省={savings}, "
                                f"折扣比例={savings_percentage}%, "
                                f"库存={in_stock}, "
                                f"状态={product.offers[0].availability if product.offers else 'Unavailable'}"
                            )
                        
                            # 记录未返回结果的ASIN
                            for asin in asins:
                                if asin not in results and not any(p.asin == asin for p in pa_products if p):
                                    self.logger.error(
                                        f"商品 {asin} 无法获取PAAPI信息: "
                                        f"原因=商品不存在或无访问权限"
                                    )
                                    results[asin] = None
                            
                    except Exception as e:
                        # 检查是否是请求过多错误(429)
                        if hasattr(e, 'status') and e.status == 429:
                            self.logger.error(
                                f"API请求过多(429 Too Many Requests): "
                                f"ASINs={asins}, "
                                f"错误信息={str(e)}"
                            )
                            # 添加更长的等待时间，然后重试
                            self.logger.info(f"等待5秒后重试...")
                            await asyncio.sleep(5)  # 等待5秒
                            try:
                                self.logger.debug(f"重试获取PAAPI信息: ASINs={asins}")
                                
                                # 重试时再次应用请求频率限制
                                await self._rate_limit_pa_api()
                                
                                pa_products = await self.amazon_api.get_products_by_asins(asins)
                                
                                # 处理返回的产品信息
                                for product in pa_products:
                                    if not product:
                                        continue
                                        
                                    price = product.offers[0].price if product.offers else 0
                                    in_stock = "Available" == product.offers[0].availability if product.offers else False
                                    
                                    # 获取折扣信息
                                    savings = product.offers[0].savings if product.offers and hasattr(product.offers[0], 'savings') else None
                                    savings_percentage = product.offers[0].savings_percentage if product.offers and hasattr(product.offers[0], 'savings_percentage') else None
                                    
                                    results[product.asin] = {
                                        'price': price,
                                        'stock': in_stock,
                                        'title': product.title if hasattr(product, 'title') else '',
                                        'availability_status': product.offers[0].availability if product.offers else 'Unavailable',
                                        'savings': savings,
                                        'savings_percentage': savings_percentage
                                    }
                                    
                                    self.logger.debug(
                                        f"重试成功获取商品信息: ASIN={product.asin}, "
                                        f"价格={price}, "
                                        f"节省={savings}, "
                                        f"折扣比例={savings_percentage}%, "
                                        f"库存={in_stock}"
                                    )
                                
                                for asin in asins:
                                    if asin not in results and not any(p.asin == asin for p in pa_products if p):
                                        results[asin] = None
                            except Exception as retry_e:
                                self.logger.error(
                                    f"重试失败: "
                                    f"ASINs={asins}, "
                                    f"错误类型={type(retry_e).__name__}, "
                                    f"错误信息={str(retry_e)}"
                                )
                                # 所有重试失败的商品标记为None
                                for asin in asins:
                                    if asin not in results:
                                        results[asin] = None
                        else:
                            # 非429错误的处理
                            self.logger.error(
                                f"批量获取PAAPI信息失败: "
                                f"ASINs={asins}, "
                                f"错误类型={type(e).__name__}, "
                                f"错误信息={str(e)}"
                            )
                            # 添加详细的API错误记录
                            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                                try:
                                    error_detail = e.response.json()
                                    self.logger.error(f"API错误响应: {error_detail}")
                                    
                                    # 检查是否有ItemNotAccessible错误
                                    if 'Errors' in error_detail:
                                        for error in error_detail['Errors']:
                                            if error.get('Code') == 'ItemNotAccessible':
                                                asin = error.get('Message', '').split(' ')[2] if len(error.get('Message', '').split(' ')) > 2 else 'unknown'
                                                self.logger.error(f"商品 {asin} 通过API无法访问，可能已下架或限制访问")
                                except:
                                    self.logger.error("无法解析API错误响应")
                            
                            for asin in asins:
                                if asin not in results:
                                    results[asin] = None
                    
                    # 更新进度条
                    pbar.update(1)
                            
            # 输出总结信息
            success_count = sum(1 for result in results.values() if result and result.get('price'))
            self.logger.info(f"PAAPI信息获取完成: 总数={len(results)}, 成功={success_count}, 失败={len(results) - success_count}")
            return results

    @track_performance
    async def update_batch(self, db: Session, limit: int = 100) -> Tuple[int, int, int]:
        """批量更新商品信息"""
        with TaskLogContext(task_id='BATCH'):
            self.logger.info("开始批量更新商品信息")
            
            try:
                # 获取需要更新的商品
                products = await self.get_products_to_update(db, limit)
                
                if not products:
                    self.logger.info("没有需要更新的商品")
                    return 0, 0, 0
                    
                self.logger.info(f"找到{len(products)}个需要更新的商品")
                
                # 分类商品
                regular_products = []
                coupon_products = []
                for product in products:
                    if product.source and product.source.lower() in ['coupon', '/coupon']:
                        coupon_products.append(product)
                    else:
                        regular_products.append(product)
                        
                self.logger.info(f"商品分类: 常规商品={len(regular_products)}, Coupon商品={len(coupon_products)}")
                
                # 获取所有ASIN
                asins = [product.asin for product in products]
                asin_to_product = {product.asin: product for product in products}
                
                # 1. 批量检查CJ平台可用性
                cj_availability = await self.process_batch_cj_availability(asins)
                
                # 获取CJ平台可用的ASIN列表
                available_asins = [asin for asin, available in cj_availability.items() if available]
                
                # 2. 为可用商品批量获取CJ推广链接
                cj_links = await self.process_batch_cj_links(available_asins)
                
                # 3. 批量获取PAAPI商品信息
                pa_info = await self.process_batch_pa_api(products)
                
                # 4. 更新商品信息
                self.logger.info(f"开始更新 {len(products)} 个商品信息到数据库")
                
                success_count = 0
                fail_count = 0
                delete_count = 0
                
                # 使用进度条显示更新进度
                with tqdm(total=len(asin_to_product), desc="更新商品信息") as pbar:
                    # 先处理常规商品
                    for product in regular_products:
                        try:
                            result = await self.process_product_update(product, db)
                            if result:
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e:
                            fail_count += 1
                            self.logger.error(f"更新商品 {product.asin} 失败: {str(e)}")
                        pbar.update(1)
                    
                    # 再处理Coupon商品
                    if coupon_products:
                        self.logger.info(f"开始处理 {len(coupon_products)} 个Coupon商品")
                        for product in coupon_products:
                            try:
                                result = await self.process_product_update(product, db)
                                if result:
                                    success_count += 1
                                else:
                                    fail_count += 1
                            except Exception as e:
                                fail_count += 1
                                self.logger.error(f"更新Coupon商品 {product.asin} 失败: {str(e)}")
                            pbar.update(1)
                
                # 关闭优惠券检查器
                await self.close_coupon_scraper()
                
                # 提交所有更改
                try:
                    db.commit()
                    self.logger.success(
                        f"批量更新完成: 成功={success_count}, 失败={fail_count}, 删除={delete_count}"
                    )
                except Exception as e:
                    db.rollback()
                    self.logger.error(f"提交数据库更改失败: {str(e)}")
                    return 0, len(products), 0
                
                return success_count, fail_count, delete_count
                
            except Exception as e:
                self.logger.error(f"批量更新过程中出错: {str(e)}")
                return 0, 0, 0
                
    @track_performance
    async def run_scheduled_update(self, batch_size: Optional[int] = None) -> Tuple[int, int, int]:
        """执行计划更新任务"""
        with TaskLogContext(task_id='SCHEDULE'):
            self.logger.info("开始执行计划更新任务")
            
            try:
                # 初始化API客户端
                await self.initialize_clients()
                if not self.amazon_api or not self.cj_client:
                    self.logger.error("API客户端初始化失败")
                    return 0, 0, 0
                    
                # 使用配置的batch_size或传入的参数
                actual_batch_size = batch_size or self.config.batch_size
                self.logger.info(f"使用批量大小: {actual_batch_size}")
                
                # 创建数据库会话
                db = SessionLocal()
                try:
                    # 首先删除价格为0的商品
                    deleted_count = await self.delete_zero_price_products(db)
                    self.logger.info(f"已删除{deleted_count}个价格为0的商品")
                    
                    # 执行批量更新
                    success_count, fail_count, delete_count = await self.update_batch(
                        db, actual_batch_size
                    )
                    
                    self.logger.success(
                        f"计划更新任务完成: "
                        f"成功={success_count}, "
                        f"失败={fail_count}, "
                        f"删除={delete_count + deleted_count}"
                    )
                    
                    return success_count, fail_count, delete_count + deleted_count
                    
                finally:
                    db.close()
                    
            except Exception as e:
                self.logger.error(f"执行计划更新任务时出错: {str(e)}")
                return 0, 0, 0

    @track_performance
    async def update_single_asin(self, db: Session, asin: str) -> bool:
        """更新单个ASIN的商品信息"""
        with TaskLogContext(task_id=f"SINGLE:{asin}"):
            try:
                self.logger.info(f"开始更新商品: {asin}")
                
                # 查询数据库中是否存在该ASIN
                product = db.query(Product).filter(Product.asin == asin).first()
                
                if not product:
                    self.logger.warning(f"数据库中不存在商品: {asin}")
                    return False
                    
                # 初始化API客户端（如果尚未初始化）
                if not self.amazon_api or not self.cj_client:
                    await self.initialize_clients()
                    if not self.amazon_api or not self.cj_client:
                        self.logger.error("API客户端初始化失败")
                        return False
                        
                # 处理商品更新
                result = await self.process_product_update(product, db)
                
                if result:
                    self.logger.success(f"商品 {asin} 更新成功")
                else:
                    self.logger.warning(f"商品 {asin} 更新失败或已删除")
                    
                return result
                
            except Exception as e:
                self.logger.error(f"更新商品 {asin} 时出错: {str(e)}")
                return False

    @classmethod
    async def main(cls):
        """主函数"""
        import argparse
        import os
        from pathlib import Path
        from loguru import logger
        
        # 创建命令行参数解析器
        parser = argparse.ArgumentParser(description="商品更新管理工具")
        parser.add_argument("--scheduled", action="store_true", help="执行计划更新任务")
        parser.add_argument("--batch-size", type=int, help="批量处理的商品数量")
        parser.add_argument("--asin", type=str, help="要更新的单个商品的ASIN")
        parser.add_argument("--log-level", type=str, default="INFO", help="日志级别")
        parser.add_argument("--debug", action="store_true", help="启用调试模式")
        parser.add_argument("--json-logs", action="store_true", help="使用JSON格式记录日志")
        parser.add_argument("--log-dir", type=str, default="logs", help="日志文件目录")
        
        args = parser.parse_args()
        
        # 创建模块特定的日志目录
        log_dir = Path(args.log_dir) / "product_updater"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志级别
        log_level = "DEBUG" if args.debug else args.log_level
        
        # 配置日志格式
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "process:{process} | thread:{thread} | "
            "{name}:{function}:{line} | {message}"
        )
        
        # 移除默认处理器
        logger.remove()
        
        # 添加控制台处理器
        logger.add(
            sys.stderr,
            format=console_format,
            level=log_level,
            colorize=True
        )
        
        # 添加主日志文件处理器
        logger.add(
            str(log_dir / "info.log"),
            format=file_format,
            level=log_level,
            rotation="00:00",  # 每天午夜轮转
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            serialize=args.json_logs,
            filter=lambda record: record["level"].name != "ERROR"  # 非错误日志
        )
        
        # 添加错误日志文件处理器
        logger.add(
            str(log_dir / "error.log"),
            format=file_format,
            level="ERROR",
            rotation="00:00",  # 每天午夜轮转
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            filter=lambda record: record["level"].name == "ERROR",
            serialize=args.json_logs
        )
        
        # 获取带有名称的 logger
        product_logger = get_logger("ProductUpdater")
        
        if not args.scheduled and not args.asin:
            product_logger.warning(
                "请使用以下参数之一运行程序：\n"
                "1. --scheduled 执行计划更新任务\n"
                "2. --asin ASIN 更新单个商品\n"
                "例如：\n"
                "python product_updater.py --scheduled --batch-size 100\n"
                "python product_updater.py --asin B07XYZABC"
            )
            return
            
        try:
            product_logger.info("初始化商品更新管理器...")
            updater = cls()
            
            if args.scheduled:
                product_logger.info(f"开始执行计划更新任务，批量大小: {args.batch_size or '默认'}")
                await updater.run_scheduled_update(args.batch_size)
            elif args.asin:
                product_logger.info(f"开始更新单个商品: {args.asin}")
                db = SessionLocal()
                try:
                    await updater.update_single_asin(db, args.asin)
                finally:
                    db.close()
                    
        except Exception as e:
            product_logger.error(f"程序执行出错: {str(e)}")
            sys.exit(1)
        finally:
            # 确保所有日志都被写入
            product_logger.info("程序执行完成")

if __name__ == "__main__":
    import asyncio
    asyncio.run(ProductUpdater.main()) 