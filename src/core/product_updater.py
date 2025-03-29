"""
商品更新管理模块

该模块提供对商品数据的定期更新功能，包括：
1. 检查商品在CJ平台的可用性
2. 更新商品的CJ推广链接
3. 获取商品最新价格、库存和优惠信息
4. 更新数据库中的商品记录

主要组件：
- ProductUpdater: 商品更新管理类，提供单个和批量商品更新方法
- 优先级调度: 基于商品热度和更新时间的优先级计算

更新策略：
1. 先检查CJ平台可用性
2. 对于CJ平台有的商品，获取CJ推广链接和详情
3. 使用PAAPI获取最新的商品数据
4. 集成来自不同来源的数据
5. 更新数据库记录
"""

import os
import asyncio
import logging
import json
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta, UTC
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from enum import Enum
import random
from logging.handlers import RotatingFileHandler

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.core.amazon_product_api import AmazonProductAPI
from src.core.cj_api_client import CJAPIClient
from models.database import SessionLocal, Product
from models.product import ProductInfo, ProductOffer
from models.product_service import ProductService
from src.utils.logger_manager import (
    log_info, log_debug, log_warning, 
    log_error, log_success, log_progress,
    log_section, set_log_config
)
from src.utils.api_retry import with_retry
from src.utils.config_loader import config_loader

class TaskLoggerAdapter(logging.LoggerAdapter):
    """为日志添加任务ID的适配器"""
    def process(self, msg, kwargs):
        kwargs.setdefault('extra', {}).setdefault('task_id', self.extra.get('task_id', 'SYSTEM'))
        return msg, kwargs

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
                log_warning(f"无法加载配置文件: {config_path}，使用默认配置")
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
            log_error(f"加载配置文件出错: {str(e)}")
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
        self._initialize_logger()
        
    def _initialize_logger(self):
        """初始化日志配置"""
        # 创建日志目录
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 配置商品更新专用日志
        product_log_file = log_dir / "product_updater.log"
        
        # 移除现有的处理器
        logger = logging.getLogger("ProductUpdater")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # 创建文件处理器
        file_handler = RotatingFileHandler(
            product_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # 设置格式化器 - 使用更结构化的格式
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] [%(task_id)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # 配置日志记录器
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
        
        # 创建LoggerAdapter来添加task_id
        class TaskLoggerAdapter(logging.LoggerAdapter):
            def process(self, msg, kwargs):
                kwargs.setdefault('extra', {}).setdefault('task_id', self.extra.get('task_id', 'SYSTEM'))
                return msg, kwargs
        
        # 保存日志记录器引用
        self.logger = TaskLoggerAdapter(logger, {'task_id': 'SYSTEM'})
        
        self.logger.info("商品更新日志系统初始化完成")
        
    async def initialize_clients(self):
        """初始化API客户端"""
        # 获取环境变量
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            log_error("缺少必要的Amazon PA-API凭证")
            raise ValueError("请检查环境变量设置: AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG")
        
        # 初始化PA-API客户端
        log_progress("正在初始化Amazon Product API客户端...")
        self.amazon_api = AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        
        # 初始化CJ客户端
        log_progress("正在初始化CJ API客户端...")
        self.cj_client = CJAPIClient()
        
        log_success("API客户端初始化完成")
        
    def _calculate_priority(self, product: Product) -> UpdatePriority:
        """
        计算商品的更新优先级
        
        优先级计算基于：
        1. 价格状态（价格为0的商品最优先）
        2. 创建时间（越早创建优先级越高）
        3. 上次更新时间（越久未更新优先级越高）
        4. CJ平台状态（CJ平台商品优先级更高）
        5. 随机因素（防止所有同类商品在同一时间更新）
        
        Args:
            product: 商品数据库记录
            
        Returns:
            UpdatePriority: 商品更新优先级
        """
        # 检查价格是否为0
        if product.current_price == 0:
            return UpdatePriority.URGENT
            
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
        """
        判断商品是否需要更新
        
        基于上次更新时间和商品优先级决定是否需要更新
        
        Args:
            product: 商品数据库记录
            
        Returns:
            bool: 是否需要更新
        """
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
        
        # 如果时间间隔大于更新间隔，则需要更新
        return time_since_update > timedelta(hours=hours)
    
    def get_products_to_update(self, db: Session, limit: int = 100) -> List[Product]:
        """获取需要更新的商品列表"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'QUERY'})
        
        # 首先获取所有价格为0的商品
        urgent_products = db.query(Product).filter(Product.current_price == 0).all()
        urgent_count = len(urgent_products)
        
        # 记录价格为0的商品信息
        if urgent_count > 0:
            log_info.info(f"发现 {urgent_count} 个价格为0的商品需要紧急更新")
            log_info.info("价格为0的商品ASIN列表:")
            for product in urgent_products:
                log_info.info(f"- {product.asin} | 标题: {product.title[:50]}...")
        
        # 如果有紧急商品，直接返回所有紧急商品，不考虑limit限制
        if urgent_count > 0:
            log_info.info(f"返回所有需要紧急更新的商品 ({urgent_count}个)")
            return urgent_products
        
        # 如果没有紧急商品，查询常规需要更新的商品
        regular_products = []
        products = db.query(Product).filter(Product.current_price != 0).all()
        
        # 筛选需要更新的商品
        for product in products:
            if self._should_update(product):
                regular_products.append(product)
                if len(regular_products) >= limit:
                    break
        
        log_info.info(f"找到 {len(regular_products)} 个常规商品需要更新")
        return regular_products
        
    async def process_product_update(
        self,
        product: Product,
        force_update: bool = False
    ) -> bool:
        """处理单个商品更新"""
        # 确保API客户端已初始化
        if not self.amazon_api or not self.cj_client:
            await self.initialize_clients()
        
        asin = product.asin
        # 为每个商品更新任务创建带有task_id的logger
        task_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': f'ASIN:{asin}'})
        
        task_logger.info("开始更新流程")
        
        # 检查是否需要更新
        if not force_update and not self._should_update(product):
            task_logger.info("无需更新 - 未达到更新间隔")
            return False
        
        try:
            # 检查CJ平台可用性
            cj_available = False
            cj_product_data = None
            try:
                task_logger.info("检查CJ平台可用性")
                cj_availability = await self.cj_client.check_products_availability([asin])
                cj_available = cj_availability.get(asin, False)
                task_logger.info(f"CJ平台状态: {'可用' if cj_available else '不可用'}")
            except Exception as e:
                task_logger.warning(f"CJ平台检查失败: {str(e)}")
            
            # 获取PA-API数据
            product_info = None
            pa_api_data = None
            try:
                task_logger.info("获取PA-API数据")
                products = await self.amazon_api.get_products_by_asins([asin])
                if products and len(products) > 0:
                    product_info = products[0]
                    if hasattr(products[0], '_raw_response'):
                        pa_api_data = products[0]._raw_response
                    task_logger.info("PA-API数据获取成功")
            except Exception as e:
                task_logger.warning(f"PA-API数据获取失败: {str(e)}")
            
            # 如果商品在CJ平台可用，获取CJ数据
            cj_url = None
            if cj_available:
                try:
                    task_logger.info("获取CJ商品数据")
                    
                    # 获取CJ商品详情
                    cj_product = await self.cj_client.get_product_details(asin)
                    if cj_product:
                        cj_product_data = cj_product
                    
                    # 生成CJ推广链接
                    cj_url = await self.cj_client.generate_product_link(asin)
                    task_logger.info("CJ数据获取成功")
                    
                    # 更新商品信息
                    if cj_product and isinstance(cj_product, dict):
                        task_logger.info("更新CJ相关数据")
                        # 确保有offers
                        if not product_info.offers:
                            product_info.offers = [ProductOffer(
                                condition="New",
                                price=0.0,
                                currency="USD",
                                availability="Available",
                                merchant_name="Amazon"
                            )]
                        
                        if product_info.offers and len(product_info.offers) > 0:
                            main_offer = product_info.offers[0]
                            
                            # 添加佣金信息
                            commission = cj_product.get('commission')
                            if isinstance(commission, str):
                                main_offer.commission = commission.rstrip('%')
                            elif isinstance(commission, (int, float)):
                                main_offer.commission = str(commission)
                            
                            # 添加优惠券信息
                            coupon_data = cj_product.get('coupon', {})
                            if isinstance(coupon_data, dict):
                                main_offer.coupon_type = coupon_data.get('type')
                                coupon_value = coupon_data.get('value')
                                if coupon_value is not None:
                                    main_offer.coupon_value = float(coupon_value)
                            
                            # 添加折扣信息
                            discount = cj_product.get('discount')
                            if isinstance(discount, str):
                                try:
                                    discount_value = float(discount.strip('%'))
                                    main_offer.savings_percentage = int(discount_value)
                                    if main_offer.price:
                                        main_offer.savings = (main_offer.price * discount_value) / 100
                                except (ValueError, TypeError):
                                    pass
                    
                except Exception as e:
                    task_logger.error(f"CJ数据处理失败: {str(e)}")
            
            # 如果没有获取到任何数据，返回失败
            if not product_info:
                task_logger.warning("无法获取任何更新数据")
                return False
            
            # 更新数据库
            with SessionLocal() as db:
                from models.product_service import ProductService
                
                # 设置API提供者
                product_info.api_provider = "cj-api" if cj_available else "pa-api"
                
                # 更新产品
                try:
                    task_logger.info("正在更新数据库记录")
                    updated_product = ProductService.update_product(
                        db,
                        product_info
                    )
                    
                    if updated_product:
                        task_logger.info("数据库更新成功")
                        task_logger.info("=" * 50)  # 添加分隔线
                        return True
                    else:
                        task_logger.warning("数据库更新失败")
                        task_logger.info("=" * 50)  # 添加分隔线
                        return False
                except Exception as e:
                    task_logger.error(f"数据库更新错误: {str(e)}")
                    task_logger.info("=" * 50)  # 添加分隔线
                    return False
                
        except Exception as e:
            task_logger.error(f"更新流程失败: {str(e)}")
            task_logger.info("=" * 50)  # 添加分隔线
            return False
    
    async def process_batch_pa_api(self, asins: List[str]) -> Dict[str, ProductInfo]:
        """批量处理PA-API请求
        
        将ASIN列表分批处理，每批最多10个ASIN，减少API请求次数
        
        Args:
            asins: ASIN列表
            
        Returns:
            Dict[str, ProductInfo]: ASIN到商品信息的映射
        """
        batch_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': f'PA-API-BATCH'})
        results = {}
        
        # 将ASIN列表分成每组10个的批次
        batch_size = 10
        for i in range(0, len(asins), batch_size):
            batch_asins = asins[i:i + batch_size]
            batch_logger.info(f"处理PA-API批次 {i//batch_size + 1}, ASINs: {', '.join(batch_asins)}")
            
            try:
                products = await self.amazon_api.get_products_by_asins(batch_asins)
                if products:
                    for product in products:
                        results[product.asin] = product
                    batch_logger.info(f"批次处理成功，获取到 {len(products)} 个商品信息")
            except Exception as e:
                batch_logger.error(f"批次处理失败: {str(e)}")
                # 如果批处理失败，尝试单个处理
                batch_logger.info("尝试单个处理失败的ASINs")
                for asin in batch_asins:
                    try:
                        products = await self.amazon_api.get_products_by_asins([asin])
                        if products and len(products) > 0:
                            results[asin] = products[0]
                            batch_logger.info(f"单个处理成功: {asin}")
                    except Exception as e:
                        batch_logger.error(f"单个处理失败 {asin}: {str(e)}")
            
            # 添加短暂延迟，避免请求过于频繁
            await asyncio.sleep(0.5)
        
        return results

    async def update_batch(
        self,
        asins: List[str],
        force_update: bool = False
    ) -> Tuple[int, int]:
        """批量更新商品"""
        # 确保API客户端已初始化
        if not self.amazon_api or not self.cj_client:
            await self.initialize_clients()
        
        batch_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': f'BATCH:{len(asins)}'})
        batch_logger.info(f"开始批量更新 {len(asins)} 个商品")
        batch_logger.info("=" * 50)
        
        # 获取商品记录
        with SessionLocal() as db:
            products = db.query(Product).filter(Product.asin.in_(asins)).all()
            asin_to_product = {product.asin: product for product in products}
            
            # 找出不存在的ASIN
            missing_asins = [asin for asin in asins if asin not in asin_to_product]
            if missing_asins:
                batch_logger.warning(f"数据库中不存在的ASIN: {', '.join(missing_asins)}")
        
        # 首先批量检查CJ平台可用性
        try:
            batch_logger.info("批量检查CJ平台可用性")
            cj_availability = await self.cj_client.check_products_availability(asins)
            batch_logger.info(f"CJ平台检查完成，{sum(cj_availability.values())}个商品可用")
        except Exception as e:
            batch_logger.error(f"CJ平台批量检查失败: {str(e)}")
            cj_availability = {asin: False for asin in asins}
        
        # 批量获取PA-API数据
        batch_logger.info("开始批量获取PA-API数据")
        pa_api_results = await self.process_batch_pa_api(asins)
        batch_logger.info(f"PA-API数据获取完成，成功获取{len(pa_api_results)}个商品信息")
        
        # 处理每个商品
        success_count = 0
        total = len(products)
        
        for product in products:
            asin = product.asin
            task_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': f'ASIN:{asin}'})
            
            try:
                # 检查是否需要更新
                if not force_update and not self._should_update(product):
                    task_logger.info("无需更新 - 未达到更新间隔")
                    continue
                
                # 获取PA-API数据
                product_info = pa_api_results.get(asin)
                if not product_info:
                    task_logger.warning("无法获取PA-API数据")
                    continue
                
                # 处理CJ平台数据
                cj_available = cj_availability.get(asin, False)
                if cj_available:
                    try:
                        task_logger.info("获取CJ商品数据")
                        cj_product = await self.cj_client.get_product_details(asin)
                        cj_url = await self.cj_client.generate_product_link(asin)
                        
                        if cj_product and isinstance(cj_product, dict):
                            task_logger.info("更新CJ相关数据")
                            product_info.api_provider = "cj-api"
                            product_info.cj_url = cj_url
                            # ... 现有的CJ数据处理代码 ...
                    except Exception as e:
                        task_logger.error(f"CJ数据处理失败: {str(e)}")
                
                # 更新数据库
                with SessionLocal() as db:
                    try:
                        task_logger.info("更新数据库记录")
                        updated_product = ProductService.update_product(db, product_info)
                        if updated_product:
                            success_count += 1
                            task_logger.info("数据库更新成功")
                        else:
                            task_logger.warning("数据库更新失败")
                    except Exception as e:
                        task_logger.error(f"数据库更新错误: {str(e)}")
                
            except Exception as e:
                task_logger.error(f"处理失败: {str(e)}")
            
            task_logger.info("=" * 50)
        
        batch_logger.info(f"批量更新完成: 成功 {success_count}/{total}")
        
        # 检查剩余的紧急更新商品
        with SessionLocal() as db:
            remaining_urgent = db.query(Product).filter(Product.current_price == 0).count()
            if remaining_urgent > 0:
                batch_logger.warning(f"注意：系统中还有 {remaining_urgent} 个商品价格为0，需要紧急更新")
            else:
                batch_logger.info("当前没有需要紧急更新的商品")
        
        batch_logger.info("=" * 50)
        return success_count, total
    
    async def run_scheduled_update(self, batch_size: Optional[int] = None) -> Tuple[int, int]:
        """运行计划更新任务"""
        batch_size = batch_size or self.config.batch_size
        
        schedule_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': 'SCHEDULE'})
        
        schedule_logger.info(f"开始计划更新任务 (批量大小: {batch_size})")
        schedule_logger.info("=" * 50)  # 添加分隔线
        
        # 确保API客户端已初始化
        if not self.amazon_api or not self.cj_client:
            await self.initialize_clients()
        
        # 查询需要更新的商品
        with SessionLocal() as db:
            products_to_update = self.get_products_to_update(db, limit=batch_size)
            
            if not products_to_update:
                schedule_logger.info("没有需要更新的商品")
                schedule_logger.info("=" * 50)  # 添加分隔线
                return 0, 0
            
            schedule_logger.info(f"找到 {len(products_to_update)} 个需要更新的商品")
            
            # 提取ASIN列表
            asins = [product.asin for product in products_to_update]
        
        # 执行批量更新
        success_count, total = await self.update_batch(asins)
        
        # 检查剩余的紧急更新商品
        with SessionLocal() as db:
            remaining_urgent = db.query(Product).filter(Product.current_price == 0).count()
            if remaining_urgent > 0:
                schedule_logger.warning(f"计划更新完成后，系统中还有 {remaining_urgent} 个商品价格为0，需要紧急更新")
                schedule_logger.warning("建议增加更新频率或批量大小")
            else:
                schedule_logger.info("系统中没有需要紧急更新的商品")
        
        schedule_logger.info("=" * 50)
        return success_count, total

# 用于CLI运行
async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="商品数据更新工具")
    
    parser.add_argument(
        "--asin",
        type=str,
        help="要更新的ASIN，用逗号分隔多个ASIN"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="批处理大小"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制更新，忽略更新间隔"
    )
    
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="运行计划更新任务"
    )
    
    args = parser.parse_args()
    
    # 创建更新器
    updater = ProductUpdater()
    await updater.initialize_clients()
    
    if args.scheduled:
        # 运行计划更新任务
        success, total = await updater.run_scheduled_update(args.batch_size)
        log_section("计划更新任务完成")
        log_info(f"成功更新: {success}/{total}")
    elif args.asin:
        # 更新指定的ASIN
        asins = [asin.strip() for asin in args.asin.split(",")]
        success, total = await updater.update_batch(asins, args.force)
        log_section("指定ASIN更新任务完成")
        log_info(f"成功更新: {success}/{total}")
    else:
        log_error("请指定--asin或--scheduled参数")

if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    
    # 运行异步任务
    asyncio.run(main()) 