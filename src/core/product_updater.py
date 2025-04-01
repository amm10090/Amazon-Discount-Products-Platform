"""
商品更新管理模块

该模块提供对商品数据的定期更新功能，包括：
1. 删除价格为0的商品
2. 检查商品在CJ平台的可用性
3. 更新商品的CJ推广链接
4. 获取商品最新价格、库存和优惠信息
5. 更新数据库中的商品记录

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
from tqdm import tqdm  # 添加tqdm库支持进度条

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
        
        # API请求限制相关变量
        self.last_pa_api_request_time = None
        self.pa_api_request_interval = 1.0  # 每秒允许的请求数量的倒数（秒）
        self.last_cj_api_request_time = None
        self.cj_api_request_interval = 0.5  # 每秒允许的请求数量的倒数（秒）
        
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
        
        # 创建文件处理器 - 记录所有级别日志
        file_handler = RotatingFileHandler(
            product_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # 创建控制台处理器 - 只显示INFO及以上级别
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 设置格式化器 - 只保留一种格式，避免重复输出
        log_formatter = logging.Formatter(
            '[%(levelname)s] [%(task_id)s] %(message)s'
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
        
        # 创建LoggerAdapter来添加task_id
        self.logger = TaskLoggerAdapter(logger, {'task_id': 'SYSTEM'})
        
        self.logger.info(f"商品更新日志系统初始化完成，日志级别: {log_level_str}")
        
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
        
        # 添加兼容层，确保API调用正常工作
        log_debug("添加PAAPI兼容层...")
        # 如果amazon_api没有get_items方法，但有get_products_by_asins方法
        if not hasattr(self.amazon_api, "get_items") and hasattr(self.amazon_api, "get_products_by_asins"):
            # 添加对get_items的兼容支持，调用get_products_by_asins
            self.amazon_api.get_items = self.amazon_api.get_products_by_asins
            log_debug("已添加get_items兼容方法，映射到get_products_by_asins")
        
        # 初始化CJ客户端
        log_progress("正在初始化CJ API客户端...")
        self.cj_client = CJAPIClient()
        
        log_success("API客户端初始化完成")
        
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
    
    async def delete_zero_price_products(self, db: Session) -> int:
        """删除所有价格为0或null的商品"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'DELETE_BATCH'})
        
        # 查询价格为0或null的商品
        zero_price_products = db.query(Product).filter(
            (Product.current_price == 0) | (Product.current_price == None)
        ).all()
        
        if not zero_price_products:
            log_info.debug("未找到价格为0或为null的商品")
            return 0
            
        log_info.info(f"开始删除价格为0或null的商品，共 {len(zero_price_products)} 个")
        
        deleted_count = 0
        for product in tqdm(zero_price_products, desc="删除价格异常商品"):
            try:
                price_str = "0" if product.current_price == 0 else "null"
                db.delete(product)
                deleted_count += 1
                log_info.debug(f"已删除价格为{price_str}的商品: {product.asin}")
            except Exception as e:
                log_info.error(f"删除商品失败 {product.asin}: {str(e)}")
                
        try:
            db.commit()
            log_info.info(f"价格异常商品删除完成，共删除 {deleted_count} 个商品")
        except Exception as e:
            log_info.error(f"提交删除操作失败: {str(e)}")
            db.rollback()
            return 0
            
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
        task_id = f"DELETE:{product.asin}"
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': task_id})
        
        try:
            db.delete(product)
            db.commit()
            log_info.info(f"已删除商品: ASIN={product.asin}, 原因={reason}")
            return True
        except Exception as e:
            log_info.error(f"删除商品失败 {product.asin}: {str(e)}")
            db.rollback()
            return False

    async def get_products_to_update(self, db: Session, limit: int = 100) -> List[Product]:
        """获取需要更新的商品列表"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'QUERY'})
        
        # 首先删除所有价格为0的商品
        deleted_count = await self.delete_zero_price_products(db)
        if deleted_count > 0:
            log_info.info(f"已删除 {deleted_count} 个价格异常的商品")
        
        # 获取需要更新的常规商品
        regular_products = []
        
        # 按照上次更新时间升序排序，优先更新最久未更新的商品
        products = db.query(Product).filter(
            Product.current_price != 0
        ).order_by(
            Product.updated_at.asc().nulls_first()
        ).all()
        
        log_info.info(f"数据库中共找到 {len(products)} 个商品")
        
        # 筛选需要更新的商品
        log_info.info(f"正在筛选需要更新的商品...")
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
                        log_info.debug(
                            f"选中商品更新: ASIN={product.asin}, "
                            f"最后更新时间={last_update}, "
                            f"优先级={priority.value}, "
                            f"API来源={product.api_provider or 'unknown'}"
                        )
                        regular_products.append(product)
                        selection_count += 1
                        # 显示选择进度
                        if selection_count % 100 == 0:
                            log_info.debug(f"已选择 {selection_count} 个商品...")
            except Exception as e:
                log_info.debug(f"商品 {product.asin} 检查更新状态时出错: {str(e)}，已跳过")
                continue
        
        # 只在INFO级别记录汇总信息
        cj_count = sum(1 for p in regular_products if p.api_provider == 'cj-api')
        pa_count = sum(1 for p in regular_products if p.api_provider == 'pa-api')
        log_info.info(
            f"找到 {len(regular_products)} 个商品需要更新 (CJ商品: {cj_count}, PA商品: {pa_count}), "
            f"数据库中还有 {total_need_update - len(regular_products)} 个商品等待更新"
        )
        return regular_products
        
    async def process_product_update(self, product: Product, db: Session) -> bool:
        """处理单个商品的更新"""
        task_id = f"UPDATE:{product.asin}"
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': task_id})
        
        try:
            # 1. 检查CJ平台可用性
            log_info.debug("检查CJ平台可用性")
            cj_availability = await self.cj_client.check_products_availability([product.asin])
            is_cj_available = cj_availability.get(product.asin, False)
            
            # 2. 如果CJ平台可用，获取推广链接
            if is_cj_available:
                log_info.debug("商品在CJ平台可用，获取推广链接")
                try:
                    cj_url = await self.cj_client.generate_product_link(product.asin)
                    product.cj_url = cj_url
                    product.api_provider = "cj-api"
                    log_info.debug("成功获取CJ推广链接")
                except Exception as e:
                    log_info.error(f"获取CJ推广链接失败: {str(e)}")
                    product.cj_url = None
                    product.api_provider = "pa-api"
            else:
                log_info.debug("商品在CJ平台不可用")
                product.cj_url = None
                product.api_provider = "pa-api"
            
            # 3. 使用PAAPI获取商品详细信息
            log_info.debug("从PAAPI获取商品信息")
            try:
                pa_products = await self.amazon_api.get_products_by_asins([product.asin])
                if not pa_products:
                    log_info.error("无法从PAAPI获取商品信息，商品可能已下架或缺货")
                    # 删除不可用的商品
                    return await self.delete_product(product, db, "商品不可用，无法从PAAPI获取信息")
                
                pa_info = pa_products[0]
                # 更新商品信息
                product.current_price = pa_info.offers[0].price if pa_info.offers else 0
                product.stock = "in_stock" if pa_info.offers and pa_info.offers[0].availability == "Available" else "out_of_stock"
                # 更新商品的时间戳
                product.timestamp = datetime.now(UTC)
                # 更新商品的updated_at字段
                product.updated_at = datetime.now(UTC)
                
                db.commit()
                log_info.debug(f"商品信息更新成功: 价格={product.current_price}, 库存={product.stock}")
                return True
                
            except Exception as e:
                log_info.error(f"PAAPI获取商品信息失败: {str(e)}")
                # 删除无法获取信息的商品
                return await self.delete_product(product, db, f"PAAPI获取商品信息失败: {str(e)}")
            
        except Exception as e:
            log_info.error(f"更新商品信息失败: {str(e)}")
            db.rollback()
            return False

    async def process_batch_cj_availability(self, asins: List[str]) -> Dict[str, bool]:
        """批量检查CJ平台商品可用性"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'CJ-CHECK'})
        batch_size = 10
        results = {}
        
        log_info.info(f"开始检查 {len(asins)} 个商品的CJ平台可用性")
        
        # 使用tqdm添加进度条
        batch_count = (len(asins) + batch_size - 1) // batch_size  # 计算批次数
        with tqdm(total=batch_count, desc="检查CJ平台可用性") as pbar:
            for i in range(0, len(asins), batch_size):
                batch_asins = asins[i:i + batch_size]
                try:
                    log_info.debug(f"检查CJ平台可用性: ASINs={batch_asins}")
                    
                    # 应用请求频率限制
                    await self._rate_limit_cj_api()
                    
                    batch_results = await self.cj_client.check_products_availability(batch_asins)
                    results.update(batch_results)
                    
                    # 记录可用和不可用的商品数量(DEBUG级别)
                    available_count = sum(1 for asin, available in batch_results.items() if available)
                    log_info.debug(f"批次检查结果: 总数={len(batch_results)}, 可用={available_count}, 不可用={len(batch_results) - available_count}")
                    
                except Exception as e:
                    log_info.error(
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
        log_info.info(f"CJ平台检查完成: 总数={len(results)}, 可用={available_count}, 不可用={len(results) - available_count}")
        return results
        
    async def process_batch_cj_links(self, available_asins: List[str]) -> Dict[str, str]:
        """批量获取CJ推广链接"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'CJ-LINKS'})
        batch_size = 10
        results = {}
        
        if not available_asins:
            log_info.info("没有可用的CJ商品，跳过获取推广链接")
            return results
            
        log_info.info(f"开始获取 {len(available_asins)} 个商品的CJ推广链接")
        
        # 使用tqdm添加进度条
        with tqdm(total=len(available_asins), desc="获取CJ推广链接") as pbar:
            for i in range(0, len(available_asins), batch_size):
                batch_asins = available_asins[i:i + batch_size]
                log_info.debug(f"获取CJ推广链接: ASINs={batch_asins}")
                
                for asin in batch_asins:
                    try:
                        # 每个链接请求都应用请求频率限制
                        await self._rate_limit_cj_api()
                        
                        link = await self.cj_client.generate_product_link(asin)
                        results[asin] = link
                        log_info.debug(f"成功获取CJ推广链接: ASIN={asin}")
                        
                    except Exception as e:
                        log_info.error(
                            f"获取商品 {asin} 的CJ推广链接失败: "
                            f"错误类型={type(e).__name__}, "
                            f"错误信息={str(e)}"
                        )
                        results[asin] = None
                    
                    # 更新进度条
                    pbar.update(1)
                    
        # 输出最终结果
        success_count = sum(1 for link in results.values() if link)
        log_info.info(f"CJ推广链接获取完成: 总数={len(results)}, 成功={success_count}, 失败={len(results) - success_count}")
        return results
        
    async def process_batch_pa_api(self, products: List[Product]) -> Dict[str, Dict]:
        """批量获取PA API商品信息"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'PAAPI'})
        results = {}
        
        # 只在INFO级别输出开始和结束信息
        log_info.info(f"开始获取 {len(products)} 个商品的PAAPI信息")
        
        # 按10个商品一组进行批处理
        batch_count = (len(products) + 9) // 10  # 计算批次数
        with tqdm(total=batch_count, desc="获取PAAPI信息") as pbar:
            for i in range(0, len(products), 10):
                batch = products[i:i+10]
                asins = [p.asin for p in batch]
                try:
                    log_info.debug(f"开始获取PAAPI信息: ASINs={asins}")
                    
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
                        
                        results[product.asin] = {
                            'price': price,
                            'stock': in_stock,
                            'title': product.title if hasattr(product, 'title') else '',
                            'availability_status': product.offers[0].availability if product.offers else 'Unavailable'
                        }
                        
                        log_info.debug(
                            f"成功获取商品信息: ASIN={product.asin}, "
                            f"价格={price}, "
                            f"库存={in_stock}, "
                            f"状态={product.offers[0].availability if product.offers else 'Unavailable'}"
                        )
                    
                    # 记录未返回结果的ASIN
                    for asin in asins:
                        if asin not in results and not any(p.asin == asin for p in pa_products if p):
                            log_info.error(
                                f"商品 {asin} 无法获取PAAPI信息: "
                                f"原因=商品不存在或无访问权限"
                            )
                            results[asin] = None
                        
                except Exception as e:
                    # 检查是否是请求过多错误(429)
                    if hasattr(e, 'status') and e.status == 429:
                        log_info.error(
                            f"API请求过多(429 Too Many Requests): "
                            f"ASINs={asins}, "
                            f"错误信息={str(e)}"
                        )
                        # 添加更长的等待时间，然后重试
                        log_info.info(f"等待5秒后重试...")
                        await asyncio.sleep(5)  # 等待5秒
                        try:
                            log_info.debug(f"重试获取PAAPI信息: ASINs={asins}")
                            
                            # 重试时再次应用请求频率限制
                            await self._rate_limit_pa_api()
                            
                            pa_products = await self.amazon_api.get_products_by_asins(asins)
                            
                            # 处理返回的产品信息
                            for product in pa_products:
                                if not product:
                                    continue
                                    
                                price = product.offers[0].price if product.offers else 0
                                in_stock = "Available" == product.offers[0].availability if product.offers else False
                                
                                results[product.asin] = {
                                    'price': price,
                                    'stock': in_stock,
                                    'title': product.title if hasattr(product, 'title') else '',
                                    'availability_status': product.offers[0].availability if product.offers else 'Unavailable'
                                }
                                
                                log_info.debug(
                                    f"重试成功获取商品信息: ASIN={product.asin}, "
                                    f"价格={price}, "
                                    f"库存={in_stock}"
                                )
                            
                            for asin in asins:
                                if asin not in results and not any(p.asin == asin for p in pa_products if p):
                                    results[asin] = None
                        except Exception as retry_e:
                            log_info.error(
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
                        log_info.error(
                            f"批量获取PAAPI信息失败: "
                            f"ASINs={asins}, "
                            f"错误类型={type(e).__name__}, "
                            f"错误信息={str(e)}"
                        )
                        # 添加详细的API错误记录
                        if hasattr(e, 'response') and hasattr(e.response, 'json'):
                            try:
                                error_detail = e.response.json()
                                log_info.error(f"API错误响应: {error_detail}")
                                
                                # 检查是否有ItemNotAccessible错误
                                if 'Errors' in error_detail:
                                    for error in error_detail['Errors']:
                                        if error.get('Code') == 'ItemNotAccessible':
                                            asin = error.get('Message', '').split(' ')[2] if len(error.get('Message', '').split(' ')) > 2 else 'unknown'
                                            log_info.error(f"商品 {asin} 通过API无法访问，可能已下架或限制访问")
                            except:
                                log_info.error("无法解析API错误响应")
                        
                        for asin in asins:
                            if asin not in results:
                                results[asin] = None
                
                # 更新进度条
                pbar.update(1)
                        
        # 输出总结信息
        success_count = sum(1 for result in results.values() if result and result.get('price'))
        log_info.info(f"PAAPI信息获取完成: 总数={len(results)}, 成功={success_count}, 失败={len(results) - success_count}")
        return results

    async def update_batch(self, db: Session, limit: int = 100) -> Tuple[int, int, int]:
        """批量更新商品信息"""
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': 'BATCH'})
        log_info.info("开始批量更新商品信息")
        
        success_count = 0
        failed_count = 0
        deleted_count = 0
        cj_success_count = 0  # CJ商品更新成功数量
        pa_success_count = 0  # PA商品更新成功数量
        
        # 获取需要更新的商品
        products = await self.get_products_to_update(db, limit)
        
        if not products:
            log_info.info("没有需要更新的商品")
            return success_count, failed_count, deleted_count
            
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
        log_info.info(f"开始更新 {len(products)} 个商品信息到数据库")
        
        # 使用tqdm添加进度条
        with tqdm(total=len(asin_to_product), desc="更新商品信息") as pbar:
            for asin, product in asin_to_product.items():
                try:
                    # 更新CJ相关信息
                    if asin in available_asins and cj_links.get(asin):
                        product.cj_url = cj_links[asin]
                        product.api_provider = "cj-api"
                    else:
                        product.cj_url = None
                        product.api_provider = "pa-api"
                    
                    # 更新PAAPI信息
                    pa_product = pa_info.get(asin)
                    if pa_product and pa_product.get('price'):
                        product.current_price = pa_product['price']
                        product.stock = "in_stock" if pa_product['stock'] else "out_of_stock"
                        # 更新商品的时间戳
                        product.timestamp = datetime.now(UTC)
                        # 更新商品的updated_at字段
                        product.updated_at = datetime.now(UTC)
                        success_count += 1
                        
                        # 根据api_provider统计更新成功的商品数量
                        if product.api_provider == "cj-api":
                            cj_success_count += 1
                        else:
                            pa_success_count += 1
                        
                        # 记录详细的更新信息(DEBUG级别)
                        log_info.debug(
                            f"成功更新商品: ASIN={asin}, "
                            f"API来源={product.api_provider}, "
                            f"价格={product.current_price}, "
                            f"库存={product.stock}"
                        )
                    else:
                        # 无法获取价格信息，删除商品
                        reason = "无法获取价格信息" if pa_product else "获取PAAPI信息失败"
                        log_info.debug(f"商品 {asin} 更新失败: {reason}，将删除该商品")
                        if await self.delete_product(product, db, reason):
                            deleted_count += 1
                        else:
                            failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
                    log_info.error(f"更新商品 {asin} 失败: 错误类型={type(e).__name__}, 错误信息={str(e)}")
                
                # 更新进度条    
                pbar.update(1)
                
        # 提交所有更改
        try:
            db.commit()
            # 输出总结信息
            log_info.info(
                f"批量更新完成: 成功={success_count} (CJ商品={cj_success_count}, PA商品={pa_success_count}), "
                f"失败={failed_count}, 删除={deleted_count}"
            )
        except Exception as e:
            db.rollback()
            log_info.error(f"提交数据库更改失败: 错误类型={type(e).__name__}, 错误信息={str(e)}")
            return 0, len(products), deleted_count
            
        return success_count, failed_count, deleted_count
    
    async def run_scheduled_update(self, batch_size: Optional[int] = None) -> Tuple[int, int, int]:
        """执行计划更新任务"""
        schedule_logger = TaskLoggerAdapter(self.logger.logger, {'task_id': 'SCHEDULE'})
        schedule_logger.info("开始执行计划更新任务")
        
        try:
            with SessionLocal() as db:
                success_count, failed_count, deleted_count = await self.update_batch(db, batch_size or 100)
                
                # 计算剩余需要更新的商品数量
                try:
                    # 获取所有非零价格的商品
                    products = db.query(Product).filter(
                        Product.current_price != 0
                    ).all()
                    
                    # 计算需要更新的商品总数
                    remaining_products_count = 0
                    
                    # 使用进度条显示统计进度
                    schedule_logger.info(f"正在统计剩余需要更新的商品数量，共 {len(products)} 个商品...")
                    
                    # 分批处理，避免处理大量商品时耗时过长
                    batch_size = 1000
                    for i in range(0, len(products), batch_size):
                        batch = products[i:i+batch_size]
                        for product in batch:
                            try:
                                if self._should_update(product):
                                    remaining_products_count += 1
                            except Exception as product_e:
                                # 单个商品处理错误不影响整体计数
                                schedule_logger.debug(f"计算更新状态时单个商品出错，已忽略: {str(product_e)}")
                                continue
                        # 显示进度
                        schedule_logger.debug(f"已检查 {min(i+batch_size, len(products))}/{len(products)} 个商品...")
                    
                    # 添加剩余需要更新的商品数量到总结信息
                    schedule_logger.info(
                        f"计划更新完成: 成功={success_count}, 失败={failed_count}, 删除={deleted_count}, "
                        f"剩余需要更新的商品数量={remaining_products_count}"
                    )
                except Exception as count_e:
                    # 计算剩余商品出错不影响主要功能
                    schedule_logger.warning(f"计算剩余需要更新的商品数量时出错: {str(count_e)}")
                    schedule_logger.info(
                        f"计划更新完成: 成功={success_count}, 失败={failed_count}, 删除={deleted_count}"
                    )
                
                return success_count, failed_count, deleted_count
                
        except Exception as e:
            schedule_logger.error(f"计划更新任务失败: {str(e)}")
            return 0, 0, 0

    async def update_single_asin(self, db: Session, asin: str) -> bool:
        """更新单个ASIN商品信息
        
        Args:
            db: 数据库会话
            asin: 要更新的商品ASIN
            
        Returns:
            bool: 更新是否成功
        """
        task_id = f"SINGLE:{asin}"
        log_info = TaskLoggerAdapter(self.logger.logger, {'task_id': task_id})
        
        # 查询数据库中是否存在该ASIN
        product = db.query(Product).filter(Product.asin == asin).first()
        
        if not product:
            log_info.error(f"数据库中不存在ASIN为{asin}的商品")
            return False
            
        log_info.info(f"开始更新单个商品: ASIN={asin}")
        
        try:
            # 1. 检查CJ平台可用性
            log_info.debug("检查CJ平台可用性")
            cj_availability = await self.cj_client.check_products_availability([asin])
            is_cj_available = cj_availability.get(asin, False)
            
            # 2. 如果CJ平台可用，获取推广链接
            if is_cj_available:
                log_info.debug("商品在CJ平台可用，获取推广链接")
                try:
                    await self._rate_limit_cj_api()
                    cj_url = await self.cj_client.generate_product_link(asin)
                    product.cj_url = cj_url
                    product.api_provider = "cj-api"
                    log_info.info("成功获取CJ推广链接")
                except Exception as e:
                    log_info.error(f"获取CJ推广链接失败: {str(e)}")
                    product.cj_url = None
                    product.api_provider = "pa-api"
            else:
                log_info.info("商品在CJ平台不可用")
                product.cj_url = None
                product.api_provider = "pa-api"
            
            # 3. 使用PAAPI获取商品详细信息
            log_info.debug("从PAAPI获取商品信息")
            try:
                await self._rate_limit_pa_api()
                pa_products = await self.amazon_api.get_products_by_asins([asin])
                if not pa_products:
                    log_info.error("无法从PAAPI获取商品信息，商品可能已下架或缺货")
                    # 删除不可用的商品
                    return await self.delete_product(product, db, "商品不可用，无法从PAAPI获取信息")
                
                pa_info = pa_products[0]
                # 更新商品信息
                old_price = product.current_price
                product.current_price = pa_info.offers[0].price if pa_info.offers else 0
                product.stock = "in_stock" if pa_info.offers and pa_info.offers[0].availability == "Available" else "out_of_stock"
                # 更新商品的时间戳
                product.timestamp = datetime.now(UTC)
                # 更新商品的updated_at字段
                product.updated_at = datetime.now(UTC)
                
                db.commit()
                log_info.info(f"商品更新成功: ASIN={asin}, 旧价格={old_price}, 新价格={product.current_price}, 库存={product.stock}")
                return True
                
            except Exception as e:
                log_info.error(f"PAAPI获取商品信息失败: {str(e)}")
                # 如果是价格为0，删除商品
                if product.current_price == 0:
                    return await self.delete_product(product, db, f"PAAPI获取商品信息失败: {str(e)}")
                db.rollback()
                return False
            
        except Exception as e:
            log_info.error(f"更新商品信息失败: {str(e)}")
            db.rollback()
            return False

# 用于CLI运行
if __name__ == "__main__":
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="商品更新程序")
    parser.add_argument("--scheduled", action="store_true", help="执行计划更新任务")
    parser.add_argument("--batch-size", type=int, default=100, help="每批次更新的商品数量")
    parser.add_argument("--log-level", type=str, default=None, help="日志级别 (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument("--asin", type=str, help="更新单个ASIN商品")
    args = parser.parse_args()
    
    # 从命令行参数或环境变量获取日志级别
    log_level_str = args.log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # 设置基本日志配置
    logging.basicConfig(level=log_level)
    
    async def main():
        try:
            updater = ProductUpdater()
            await updater.initialize_clients()
            
            if args.asin:
                # 处理单个ASIN更新
                with SessionLocal() as db:
                    success = await updater.update_single_asin(db, args.asin)
                    if success:
                        log_success(f"ASIN {args.asin} 更新成功")
                    else:
                        log_error(f"ASIN {args.asin} 更新失败")
            elif args.scheduled:
                success, failed, deleted = await updater.run_scheduled_update(args.batch_size)
                log_section("计划更新任务完成")
                log_info(f"成功更新: {success}/{success + failed}")
                if deleted > 0:
                    log_info(f"删除价格为0的商品: {deleted}")
            else:
                print("请使用 --scheduled 参数来执行计划更新任务")
                print("或使用 --asin 参数来更新单个商品")
                print("例如: python product_updater.py --scheduled --batch-size 100")
                print("      python product_updater.py --asin B07XYZABC")
        except Exception as e:
            log_error(f"主程序运行异常: {str(e)}")
            import traceback
            log_error(traceback.format_exc())
            sys.exit(1)
    
    asyncio.run(main()) 