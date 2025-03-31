"""
优惠信息更新调度器
该模块负责管理商品优惠信息的更新优先级和调度策略。

主要功能：
1. 计算商品更新优先级
2. 控制更新频率
3. 分配更新任务
4. 监控任务执行
5. 收集统计信息
"""

import math
import time
import random  # 添加random模块引入
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass
from queue import PriorityQueue
import heapq
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text

from models.database import Product, Offer

# 初始化日志记录器
logger = logging.getLogger("DiscountScheduler")

class TaskLoggerAdapter(logging.LoggerAdapter):
    """为日志添加任务ID的适配器"""
    def process(self, msg, kwargs):
        kwargs.setdefault('extra', {}).setdefault('task_id', self.extra.get('task_id', 'SYSTEM'))
        return msg, kwargs

@dataclass
class UpdateTask:
    """更新任务数据类"""
    asin: str
    priority: float = 0.0
    next_update_time: datetime = None
    created_at: datetime = None
    price: float = 0.0
    popularity_score: float = 0.0
    last_discount_update: datetime = None  # 改为使用折扣更新时间
    has_discount: bool = False
    
    def __lt__(self, other):
        """优先级比较，用于优先级队列排序"""
        return self.priority > other.priority  # 高优先级在前

class DiscountUpdateScheduler:
    """优惠信息更新调度器"""
    
    def __init__(self, db: Session, 
                 base_interval: int = 24*60*60,  # 基础更新间隔（秒）
                 min_interval: int = 4*60*60,    # 最小更新间隔（秒）
                 max_interval: int = 7*24*60*60, # 最大更新间隔（秒）
                 batch_size: int = 50,
                 max_load_products: int = 1000,   # 每次最多加载的商品数量
                 force_update: bool = False):    # 添加强制更新参数
        """
        初始化调度器
        
        Args:
            db: 数据库会话
            base_interval: 基础更新间隔（秒）
            min_interval: 最小更新间隔（秒）
            max_interval: 最大更新间隔（秒）
            batch_size: 批处理大小
            max_load_products: 每次最多加载的商品数量
            force_update: 是否强制更新，忽略时间间隔检查
        """
        self.db = db
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.batch_size = batch_size
        self.max_load_products = max_load_products
        self.force_update = force_update  # 添加force_update属性
        
        # 优先级计算权重
        self.weights = {
            'price': 0.25,      # 价格权重
            'time': 0.20,       # 时间权重
            'popularity': 0.25,  # 热度权重
            'discount': 0.20,    # 优惠权重
            'random': 0.10      # 随机因子权重
        }
        
        # 任务队列
        self.task_queue = PriorityQueue()
        
        # 统计信息
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'avg_processing_time': 0.0,
            'last_stats_reset': datetime.now(UTC)
        }
        
        self.logger = TaskLoggerAdapter(logger, {'task_id': 'SCHEDULER'})
        
    def calculate_price_factor(self, price: float) -> float:
        """
        计算价格因子
        价格越高，优先级越高
        使用对数函数平滑价格差异
        """
        if price <= 0:
            return 0.0
        return min(1.0, math.log(1 + price/100) / 5)  # 归一化到0-1范围
        
    def calculate_time_decay(self, last_discount_update: Optional[datetime]) -> float:
        """
        计算时间衰减因子
        
        Args:
            last_discount_update: 最后折扣更新时间
            
        Returns:
            float: 时间衰减因子 (0.0-1.0)
        """
        if not last_discount_update:
            return 1.0  # 从未更新过的商品获得最高优先级
        
        # 处理时区问题：确保last_discount_update是带时区的
        now = datetime.now(UTC)
        if last_discount_update.tzinfo is None:
            # 如果last_discount_update没有时区信息，假定它是UTC时间
            # 将其转换为带UTC时区信息的日期时间
            last_discount_update = last_discount_update.replace(tzinfo=UTC)
            
        hours_since_update = (now - last_discount_update).total_seconds() / 3600
        
        # 修改时间衰减公式，使更长时间未更新的商品获得更高优先级
        # 使用线性函数替代指数函数，避免在相近时间点的商品衰减值过于接近
        decay = min(1.0, hours_since_update / (24 * 7))  # 一周为满分
        return decay
        
    def calculate_popularity_score(self, product: Product) -> float:
        """
        计算商品热度分数
        基于浏览量、销量等指标
        """
        # TODO: 实现实际的热度计算逻辑
        # 当前使用简单的示例实现
        base_score = 0.5
        
        # 如果有优惠，提高热度分数
        if product.offers and product.offers[0].deal_type != "None":
            base_score += 0.2
            
        # 如果是高价值商品，提高热度分数
        if product.current_price and product.current_price > 100:
            base_score += 0.3
            
        return min(1.0, base_score)
        
    def calculate_discount_factor(self, product: Product) -> float:
        """
        计算优惠因子
        有优惠的商品获得更高的优先级
        """
        if not product.offers:
            return 0.5  # 默认中等优先级
            
        offer = product.offers[0]
        
        # 基础分数
        score = 0.5
        
        # 如果有优惠券，提高优先级
        if offer.coupon_type and offer.coupon_value:
            score += 0.3
            
        # 如果有折扣，提高优先级
        if offer.savings_percentage:
            score += 0.2 * (offer.savings_percentage / 100)
            
        # 如果有特殊促销，提高优先级
        if offer.deal_badge:
            score += 0.2
            
        return min(1.0, score)
        
    def calculate_priority(self, product: Product) -> float:
        """
        计算商品的更新优先级
        
        Args:
            product: 商品对象
            
        Returns:
            float: 优先级分数 (0-1)
        """
        # 计算各个因子
        price_factor = self.calculate_price_factor(product.current_price or 0)
        time_decay = self.calculate_time_decay(product.discount_updated_at)
        popularity_score = self.calculate_popularity_score(product)
        discount_factor = self.calculate_discount_factor(product)
        
        # 添加随机因子，打破相同时间更新的商品的排序
        random_factor = random.random()
        
        # 加权计算最终优先级
        priority = (
            self.weights['price'] * price_factor +
            self.weights['time'] * time_decay +
            self.weights['popularity'] * popularity_score +
            self.weights['discount'] * discount_factor +
            self.weights['random'] * random_factor
        )
        
        return min(1.0, priority)
        
    def calculate_next_update_time(self, product: Product, priority: float) -> datetime:
        """
        计算下次更新时间
        优先级越高，更新间隔越短
        
        Args:
            product: 商品对象
            priority: 优先级分数
            
        Returns:
            datetime: 下次更新时间
        """
        # 基于优先级调整更新间隔
        interval = self.base_interval * (1 - priority)
        
        # 确保在最小和最大间隔范围内
        interval = max(self.min_interval, min(self.max_interval, interval))
        
        # 如果商品有优惠，缩短更新间隔
        if product.offers and product.offers[0].deal_type != "None":
            interval *= 0.5
            
        return datetime.now(UTC) + timedelta(seconds=interval)
        
    def create_update_task(self, product: Product) -> UpdateTask:
        """
        创建更新任务
        
        Args:
            product: 商品数据库记录
            
        Returns:
            UpdateTask: 更新任务对象
        """
        # 计算基础优先级
        priority = self.calculate_priority(product)
        
        # 计算下次更新时间
        next_update_time = self.calculate_next_update_time(product, priority)
        
        return UpdateTask(
            asin=product.asin,
            priority=priority,
            next_update_time=next_update_time,
            created_at=datetime.now(UTC),
            price=product.current_price or 0.0,
            popularity_score=self.calculate_popularity_score(product),
            last_discount_update=product.discount_updated_at,  # 使用折扣更新时间
            has_discount=bool(product.offers and product.offers[0].deal_type != "None")
        )
        
    def update_task_queue(self):
        """更新任务队列，采用分批加载商品数据的策略"""
        self.logger.info("开始更新任务队列...")
        
        # 清空现有队列
        while not self.task_queue.empty():
            self.task_queue.get()
            
        try:
            # 获取数据库中商品总数
            total_products = self.db.query(func.count(Product.id)).scalar()
            self.logger.info(f"数据库中共有 {total_products} 个商品")
            
            # 分批加载和处理商品
            offset = 0
            batch_size = self.max_load_products
            total_loaded = 0
            
            while offset < total_products:
                # 按照不同的策略批量加载商品
                # 1. 优先加载有折扣的商品
                products_with_discount = self.db.query(Product)\
                    .join(Offer, Product.id == Offer.product_id)\
                    .filter(Offer.deal_type != "None")\
                    .limit(batch_size // 3)\
                    .all()
                
                # 2. 加载高价值商品
                high_value_products = self.db.query(Product)\
                    .filter(Product.current_price > 1000)\
                    .order_by(Product.current_price.desc())\
                    .offset(offset)\
                    .limit(batch_size // 3)\
                    .all()
                
                # 3. 加载长时间未更新的商品
                old_updated_products = self.db.query(Product)\
                    .order_by(Product.discount_updated_at.asc().nullsfirst())\
                    .offset(offset)\
                    .limit(batch_size // 3)\
                    .all()
                
                # 4. 如果前面的商品数量不足批次大小，则随机抽取一些商品补足
                products_count = len(products_with_discount) + len(high_value_products) + len(old_updated_products)
                random_products = []
                
                if products_count < batch_size:
                    # 使用 SQL 随机抽取商品
                    random_products = self.db.query(Product)\
                        .order_by(func.random())\
                        .limit(batch_size - products_count)\
                        .all()
                
                # 合并所有获取的商品，去重
                all_products = []
                product_asins = set()
                
                for product_list in [products_with_discount, high_value_products, old_updated_products, random_products]:
                    for product in product_list:
                        if product.asin not in product_asins:
                            all_products.append(product)
                            product_asins.add(product.asin)
                
                self.logger.info(f"已加载 {len(all_products)} 个商品进行处理")
                total_loaded += len(all_products)
                
                # 为每个商品创建任务并加入队列
                for product in all_products:
                    task = self.create_update_task(product)
                    self.task_queue.put(task)
                
                # 更新偏移量
                offset += batch_size
                
                # 如果任务队列已经足够大，则不再继续加载
                if self.task_queue.qsize() >= self.max_load_products * 2:
                    break
            
            self.logger.info(f"任务队列更新完成，共加载 {total_loaded} 个商品，队列大小 {self.task_queue.qsize()}")
            
        except Exception as e:
            self.logger.error(f"更新任务队列时发生错误: {str(e)}")
            # 如果出错，至少添加一些随机商品以确保系统可以继续运行
            try:
                random_products = self.db.query(Product).order_by(func.random()).limit(self.batch_size * 2).all()
                for product in random_products:
                    task = self.create_update_task(product)
                    self.task_queue.put(task)
                self.logger.info(f"已添加 {len(random_products)} 个随机商品到队列作为备用")
            except Exception as fallback_error:
                self.logger.error(f"添加备用商品时也发生错误: {str(fallback_error)}")
        
    def get_next_batch(self) -> List[str]:
        """
        获取下一批要更新的商品ASIN
        
        Returns:
            List[str]: ASIN列表
        """
        current_time = datetime.now(UTC)
        batch = []
        temp_tasks = []  # 临时存储不需要立即处理的任务
        
        while len(batch) < self.batch_size and not self.task_queue.empty():
            task = self.task_queue.get()
            
            # 如果是强制更新或者到达更新时间，则添加到批次中
            if self.force_update or task.next_update_time <= current_time:
                batch.append(task.asin)
                self.stats['total_tasks'] += 1
            else:
                # 如果还没到更新时间，保存到临时列表
                temp_tasks.append(task)
                
        # 将未处理的任务放回队列
        for task in temp_tasks:
            self.task_queue.put(task)
                
        return batch
        
    def record_task_result(self, asin: str, success: bool, processing_time: float):
        """
        记录任务执行结果
        
        Args:
            asin: 商品ASIN
            success: 是否成功
            processing_time: 处理时间（秒）
        """
        if success:
            self.stats['completed_tasks'] += 1
        else:
            self.stats['failed_tasks'] += 1
            
        # 更新平均处理时间
        n = self.stats['completed_tasks'] + self.stats['failed_tasks']
        self.stats['avg_processing_time'] = (
            (self.stats['avg_processing_time'] * (n-1) + processing_time) / n
        )
        
    def get_statistics(self) -> Dict:
        """
        获取任务统计信息
        
        Returns:
            Dict: 统计信息字典
        """
        stats = self.stats.copy()
        stats['success_rate'] = (
            self.stats['completed_tasks'] / self.stats['total_tasks'] * 100
            if self.stats['total_tasks'] > 0 else 0
        )
        stats['queue_size'] = self.task_queue.qsize()
        return stats
        
    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'avg_processing_time': 0.0,
            'last_stats_reset': datetime.now(UTC)
        }
        
    def adjust_weights(self):
        """
        动态调整优先级权重
        基于任务执行结果和性能指标
        """
        # TODO: 实现动态权重调整逻辑
        pass 