#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CJ商品爬虫模块

从CJ平台获取商品数据并保存到数据库
处理变体关系和优惠券信息
"""

import os
import sys
import json
import asyncio
import re
import heapq
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, UTC, timedelta
from pathlib import Path
import argparse
import random

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.database import Product, ProductVariant, Offer, CouponHistory
from models.product import ProductInfo, ProductOffer
from models.product_service import ProductService
from src.core.cj_api_client import CJAPIClient
from src.utils.log_config import get_logger, log_function_call, LogContext

class CJProductsCrawler:
    """CJ商品爬虫类，负责从CJ API获取商品并保存到数据库"""
    
    def __init__(self):
        """初始化CJ商品爬虫"""
        self.api_client = CJAPIClient()
        self.logger = get_logger("CJProductsCrawler")
        
        # 确保日志目录存在
        log_dir = Path(project_root) / "logs"
        log_dir.mkdir(exist_ok=True)
        
        self.logger.debug("CJ商品爬虫初始化完成")
        
        # 添加游标持久化相关的属性
        self.cursor_file_path = Path(__file__).parent.parent.parent / "data" / "cursors" / "cj_cursors.json"
        self.cursor_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_history = {}
        self.last_full_scan = None
        self.cursor_expiry_days = 7  # 单个游标过期时间（天）
        self.full_scan_expiry_days = 30  # 全局扫描过期时间（天）
        
        # 游标优先级队列
        self.cursor_priority_queue = []
        
        # 加载历史游标
        self._load_cursor_history()
    
    def _load_cursor_history(self) -> None:
        """从文件加载游标历史记录"""
        try:
            if self.cursor_file_path.exists():
                with open(self.cursor_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 加载上次全局扫描时间
                    if 'last_full_scan' in data and data['last_full_scan']:
                        self.last_full_scan = datetime.fromisoformat(data['last_full_scan'])
                    
                    # 加载游标历史
                    if 'cursors' in data and isinstance(data['cursors'], list):
                        for cursor_data in data['cursors']:
                            if 'cursor' in cursor_data and cursor_data['cursor']:
                                cursor = cursor_data['cursor']
                                self.cursor_history[cursor] = {
                                    'asins': cursor_data.get('asins', []),
                                    'last_used': datetime.fromisoformat(cursor_data.get('last_used', datetime.now().isoformat())),
                                    'success_count': cursor_data.get('success_count', 0),
                                    'scan_count': cursor_data.get('scan_count', 1),
                                    'success_rate': cursor_data.get('success_count', 0) / max(1, cursor_data.get('scan_count', 1))
                                }
                
                self.logger.info(f"已加载 {len(self.cursor_history)} 条游标历史记录")
                if self.last_full_scan:
                    self.logger.info(f"上次全局扫描时间: {self.last_full_scan.isoformat()}")
                
                # 初始化游标优先级队列
                self._initialize_cursor_priority_queue()
        except Exception as e:
            self.logger.error(f"加载游标历史记录失败: {str(e)}")
            # 如果加载失败，使用空的游标历史
            self.cursor_history = {}
            self.last_full_scan = None
    
    def _initialize_cursor_priority_queue(self) -> None:
        """初始化游标优先级队列"""
        self.cursor_priority_queue = []
        
        for cursor, data in self.cursor_history.items():
            # 计算优先级评分
            score = self._calculate_cursor_score(cursor, data)
            heapq.heappush(self.cursor_priority_queue, (-score, cursor))  # 负分数使高分优先
            
        self.logger.debug(f"游标优先级队列已初始化，共 {len(self.cursor_priority_queue)} 个游标")
    
    def _calculate_cursor_score(self, cursor: str, data: Dict) -> float:
        """计算游标优先级分数"""
        if not data:
            return 0.0
        
        # 基础因素
        last_used = data.get('last_used', datetime.now())
        if isinstance(last_used, str):
            last_used = datetime.fromisoformat(last_used)
        
        success_rate = data.get('success_rate', 0)
        if not success_rate and 'success_count' in data and 'scan_count' in data:
            scan_count = max(1, data.get('scan_count', 1))
            success_rate = data.get('success_count', 0) / scan_count
            
        product_count = len(data.get('asins', []))
        scan_count = data.get('scan_count', 1)
        
        # 时间衰减因子（越久没扫描优先级越高）
        time_diff = (datetime.now() - last_used).total_seconds()
        time_factor = min(10, time_diff / (24 * 3600))
        
        # 成功率因子（成功率高的优先级较高）
        success_factor = success_rate * 2
        
        # 产品密度因子（产品密度高的区域优先级较高）
        density_factor = min(5, product_count / max(1, scan_count))
        
        # 合并评分
        score = time_factor * 0.5 + success_factor * 0.3 + density_factor * 0.2
        
        self.logger.debug(f"游标 {cursor[:20]}... 评分: {score:.2f} (时间:{time_factor:.2f}, 成功率:{success_factor:.2f}, 密度:{density_factor:.2f})")
        return score
    
    def _save_cursor_history(self) -> None:
        """保存游标历史记录到文件"""
        try:
            # 准备要保存的数据
            data = {
                'last_full_scan': self.last_full_scan.isoformat() if self.last_full_scan else None,
                'cursors': []
            }
            
            # 转换游标历史为可序列化格式
            for cursor, info in self.cursor_history.items():
                success_count = info.get('success_count', 0)
                scan_count = info.get('scan_count', 1)
                success_rate = success_count / max(1, scan_count)
                
                data['cursors'].append({
                    'cursor': cursor,
                    'asins': info.get('asins', []),
                    'last_used': info.get('last_used', datetime.now()).isoformat(),
                    'success_count': success_count,
                    'scan_count': scan_count,
                    'success_rate': success_rate
                })
            
            # 写入文件
            with open(self.cursor_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"已保存 {len(self.cursor_history)} 条游标历史记录")
        except Exception as e:
            self.logger.error(f"保存游标历史记录失败: {str(e)}")
    
    def _is_cursor_expired(self, cursor: str) -> bool:
        """判断游标是否已过期需要重新扫描
        
        Args:
            cursor: 要检查的游标
            
        Returns:
            bool: 如果游标已过期，返回True，否则返回False
        """
        if cursor not in self.cursor_history:
            return True
            
        data = self.cursor_history[cursor]
        
        # 获取最后扫描时间
        last_used = data.get('last_used')
        if isinstance(last_used, str):
            try:
                last_used = datetime.fromisoformat(last_used)
            except ValueError:
                return True
                
        if not last_used:
            return True
        
        # 计算成功率
        scan_count = data.get('scan_count', 0)
        success_count = data.get('success_count', 0)
        success_rate = success_count / max(1, scan_count)
        
        # 基础过期时间（24小时）
        base_expiry = timedelta(hours=24)
        
        # 成功率高的游标更频繁地扫描
        if success_rate > 0.8:
            expiry_time = base_expiry * 0.5  # 12小时
        elif success_rate > 0.5:
            expiry_time = base_expiry  # 24小时
        elif success_rate > 0.2:
            expiry_time = base_expiry * 2  # 48小时
        else:
            expiry_time = base_expiry * 4  # 96小时
        
        # 随机波动±20%，避免同时过期
        random_factor = random.uniform(0.8, 1.2)
        expiry_time = expiry_time * random_factor
        
        # 当前时间减去最后扫描时间 > 过期时间则过期
        return (datetime.now() - last_used) > expiry_time
    
    def _is_full_scan_expired(self) -> bool:
        """检查是否需要执行全局扫描
        
        Returns:
            bool: 如果需要执行全局扫描，返回True，否则返回False
        """
        if not self.last_full_scan:
            return True
            
        # 计算上次全局扫描是否超过过期时间
        expiry_date = datetime.now() - timedelta(days=self.full_scan_expiry_days)
        return self.last_full_scan < expiry_date
    
    def _select_cursor(self) -> str:
        """智能选择下一个要扫描的游标
        
        Returns:
            str: 选择的游标，如果需要重新扫描，返回空字符串
        """
        # 检查是否需要全局扫描
        if self._is_full_scan_expired():
            self.logger.info(f"上次全局扫描已过期，需要执行全局扫描")
            # 更新全局扫描时间
            self.last_full_scan = datetime.now()
            self._save_cursor_history()
            return ""
        
        # 20%概率完全随机选择（探索新区域）
        if random.random() < 0.2:
            random_cursor = self._get_random_cursor(self.cursor_history)
            self.logger.info(f"随机探索策略选择游标: {random_cursor[:30] if random_cursor else '无'}")
            return random_cursor
            
        # 初始化优先级队列（如果尚未初始化）
        if not self.cursor_priority_queue:
            self._initialize_cursor_priority_queue()
            
        # 80%概率使用优先级队列
        temp_queue = self.cursor_priority_queue.copy()
        
        while temp_queue:
            _, cursor = heapq.heappop(temp_queue)
            
            # 检查是否还需要扫描该游标
            if not self._is_cursor_expired(cursor):
                # 将游标重新放回主队列，但调整优先级
                if cursor in self.cursor_history:
                    new_score = self._calculate_cursor_score(cursor, self.cursor_history.get(cursor, {})) * 0.8
                    for i, (score, c) in enumerate(self.cursor_priority_queue):
                        if c == cursor:
                            # 更新分数
                            self.cursor_priority_queue[i] = (-new_score, cursor)
                            # 重建堆
                            heapq.heapify(self.cursor_priority_queue)
                            break
                            
                self.logger.debug(f"游标 {cursor[:30]}... 未过期，跳过")
                continue
                
            self.logger.info(f"优先级队列选择游标: {cursor[:30] if cursor else '无'}")
            return cursor
        
        # 如果队列为空或所有游标都未过期，从头开始
        self.logger.info("没有可用的游标，使用空游标从头开始")
        return ""
    
    def _update_cursor_history(self, cursor: str, asins: List[str], success_count: int) -> None:
        """更新游标历史信息
        
        Args:
            cursor: 游标
            asins: 该游标获取到的商品ASIN列表
            success_count: 成功获取商品数量
        """
        now = datetime.now()
        
        if cursor not in self.cursor_history:
            self.cursor_history[cursor] = {
                'asins': [],
                'last_used': now,
                'success_count': 0,
                'scan_count': 0,
                'success_rate': 0.0
            }
        
        # 更新游标信息
        existing_asins = set(self.cursor_history[cursor].get('asins', []))
        new_asins = [asin for asin in asins if asin not in existing_asins]
        
        # 合并ASIN列表（去重）
        updated_asins = list(existing_asins.union(new_asins))
        
        # 更新字段
        self.cursor_history[cursor]['asins'] = updated_asins
        self.cursor_history[cursor]['last_used'] = now
        self.cursor_history[cursor]['success_count'] += success_count
        
        # 增加扫描计数
        scan_count = self.cursor_history[cursor].get('scan_count', 0) + 1
        self.cursor_history[cursor]['scan_count'] = scan_count
        
        # 计算成功率
        total_success = self.cursor_history[cursor]['success_count']
        self.cursor_history[cursor]['success_rate'] = total_success / max(1, scan_count)
        
        # 保存更新后的历史
        self._save_cursor_history()
        
        # 更新优先级队列
        score = self._calculate_cursor_score(cursor, self.cursor_history[cursor])
        
        # 在队列中查找并更新现有项，或添加新项
        cursor_in_queue = False
        for i, (_, c) in enumerate(self.cursor_priority_queue):
            if c == cursor:
                self.cursor_priority_queue[i] = (-score, cursor)
                cursor_in_queue = True
                # 重建堆
                heapq.heapify(self.cursor_priority_queue)
                break
                
        if not cursor_in_queue:
            heapq.heappush(self.cursor_priority_queue, (-score, cursor))
    
    @log_function_call
    async def _generate_and_set_promo_link(self, product_info: ProductInfo) -> None:
        """
        为商品生成CJ推广链接并设置到product_info对象
        
        Args:
            product_info: 商品信息对象
            
        Returns:
            None
        """
        try:
            # 调用CJ API生成推广链接
            promo_link = await self.api_client.generate_product_link(asin=product_info.asin)
            
            # 设置到商品信息对象
            product_info.cj_url = promo_link
            
            self.logger.debug(f"成功生成商品 {product_info.asin} 的推广链接")
            
        except Exception as e:
            self.logger.warning(f"生成商品 {product_info.asin} 的推广链接失败: {str(e)}")
            # 设置为None，确保后续处理不会出错
            product_info.cj_url = None
    
    @log_function_call
    async def _batch_generate_promo_links(self, product_infos: List[ProductInfo]) -> None:
        """
        批量生成商品推广链接并设置到对应的product_info对象
        
        Args:
            product_infos: 商品信息对象列表
            
        Returns:
            None
        """
        if not product_infos:
            return
        
        # 收集所有ASIN
        asins = [p.asin for p in product_infos]
        asin_to_product_info = {p.asin: p for p in product_infos}
        
        try:
            # 批量请求推广链接，每批最多10个
            for i in range(0, len(asins), 10):
                batch_asins = asins[i:i+10]
                self.logger.debug(f"处理批次 {i//10+1}，ASIN数量: {len(batch_asins)}")
                
                try:
                    # 调用API批量生成推广链接
                    result = await self.api_client.batch_generate_product_links(batch_asins)
                    
                    # 将链接设置到对应的商品信息对象
                    for asin, link in result.items():
                        if asin in asin_to_product_info:
                            asin_to_product_info[asin].cj_url = link
                            self.logger.debug(f"成功设置商品 {asin} 的推广链接: {link[:30]}...")
                    
                    # 设置未返回链接的商品为None
                    for asin in batch_asins:
                        if asin not in result and asin in asin_to_product_info:
                            asin_to_product_info[asin].cj_url = None
                            self.logger.warning(f"商品 {asin} 未获取到推广链接，将尝试使用默认构造方式")
                            # 尝试构造一个默认的推广链接 (Amazon + ASIN)
                            default_link = f"https://www.amazon.com/dp/{asin}?tag=default"
                            asin_to_product_info[asin].cj_url = default_link
                            self.logger.debug(f"为商品 {asin} 设置了默认推广链接")
                    
                except Exception as e:
                    self.logger.error(f"批量生成推广链接失败: {str(e)}")
                    # 将这批商品的链接设置为默认构造的链接
                    for asin in batch_asins:
                        if asin in asin_to_product_info:
                            default_link = f"https://www.amazon.com/dp/{asin}?tag=default"
                            asin_to_product_info[asin].cj_url = default_link
                            self.logger.debug(f"由于API异常，为商品 {asin} 设置了默认推广链接")
                
                # 避免API限流
                if i + 10 < len(asins):
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            self.logger.error(f"批量生成推广链接过程中发生错误: {str(e)}")
            # 确保所有商品都有cj_url值，使用默认构造的链接
            for p in product_infos:
                if not p.cj_url:  # 真正检查cj_url是否为None或空
                    default_link = f"https://www.amazon.com/dp/{p.asin}?tag=default"
                    p.cj_url = default_link
                    self.logger.debug(f"由于整体流程异常，为商品 {p.asin} 设置了默认推广链接")
    
    def _convert_cj_product_to_model(self, product_data: Dict) -> ProductInfo:
        """
        将CJ API返回的商品数据转换为ProductInfo模型
        
        Args:
            product_data: CJ API返回的单个商品数据
            
        Returns:
            ProductInfo: 转换后的商品信息对象
        """
        # 解析价格（去掉货币符号）
        def parse_price(price_str):
            if not price_str:
                return 0.0
            # 从价格字符串中提取数字部分
            match = re.search(r'[\d,.]+', price_str)
            if match:
                # 替换逗号，然后转换为浮点数
                return float(match.group().replace(',', ''))
            return 0.0
        
        # 解析优惠券
        def parse_coupon(coupon_str):
            if not coupon_str:
                return None, None
            
            # 解析优惠券类型和值
            if coupon_str.startswith('$'):
                return 'fixed', parse_price(coupon_str)
            elif '%' in coupon_str:
                return 'percentage', float(coupon_str.replace('%', '').strip())
            return None, None
        
        # 处理折扣百分比
        def parse_discount(discount_str):
            if not discount_str or discount_str == '0%':
                return 0
            return int(discount_str.replace('%', '').strip())
        
        # 解析价格
        original_price = parse_price(product_data.get('original_price', '0'))
        current_price = parse_price(product_data.get('discount_price', '0'))
        discount_percentage = parse_discount(product_data.get('discount', '0%'))
        
        # 计算节省金额
        savings = round(original_price - current_price, 2) if original_price > current_price else 0
        
        # 解析优惠券
        coupon_type, coupon_value = parse_coupon(product_data.get('coupon'))
        
        # 构建categories列表
        categories = []
        if product_data.get('category'):
            categories.append(product_data['category'])
        if product_data.get('subcategory') and product_data.get('subcategory') != product_data.get('category'):
            categories.append(product_data['subcategory'])
        
        # 构建offer
        offer = ProductOffer(
            condition="New",  # CJ API没有提供condition字段，默认为新品
            price=current_price,
            currency="USD",  # CJ API价格格式为$xx.xx，因此默认为USD
            savings=savings,
            savings_percentage=discount_percentage,
            is_prime=False,  # CJ API没有提供Prime信息
            is_amazon_fulfilled=False,
            is_free_shipping_eligible=False,
            availability=product_data.get('availability', 'Unknown'),
            merchant_name=product_data.get('brand_name', 'Unknown'),
            is_buybox_winner=False,
            coupon_type=coupon_type,
            coupon_value=coupon_value,
            commission=product_data.get('commission')
        )
        
        # 构建商品信息
        product_info = ProductInfo(
            asin=product_data.get('asin', ''),
            title=product_data.get('product_name', ''),
            url=product_data.get('url', ''),
            brand=product_data.get('brand_name', ''),
            main_image=product_data.get('image', ''),
            offers=[offer],
            timestamp=datetime.now(UTC),
            categories=categories,
            api_provider="cj-api",  # 明确标记API提供者
            raw_data=product_data,  # 保存原始数据
            cj_url=None,  # 初始化为None，稍后会生成
            coupon_info={  # 添加优惠券信息
                'type': coupon_type,
                'value': coupon_value
            } if coupon_type and coupon_value else None
        )
        
        return product_info
    
    def _process_offers(self, db: Session, product: Product, product_info: ProductInfo) -> None:
        """处理商品优惠信息"""
        # 删除旧的优惠信息
        db.query(Offer).filter(Offer.product_id == product.asin).delete()
        
        # 添加新的优惠信息
        for offer_data in product_info.offers:
            offer = Offer(
                product_id=product.asin,
                price=offer_data.price,
                currency=offer_data.currency,
                savings=offer_data.savings,
                savings_percentage=offer_data.savings_percentage,
                coupon_type=offer_data.coupon_type,
                coupon_value=offer_data.coupon_value,
                commission=offer_data.commission,
                condition=offer_data.condition,
                availability=offer_data.availability,
                merchant_name=offer_data.merchant_name,
                is_buybox_winner=offer_data.is_buybox_winner,
                is_prime=offer_data.is_prime,
                is_amazon_fulfilled=offer_data.is_amazon_fulfilled,
                is_free_shipping_eligible=offer_data.is_free_shipping_eligible,
                deal_type=offer_data.deal_type,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            db.add(offer)
            
            # 检查是否有优惠券信息，如果有则保存到coupon_history表
            if offer_data.coupon_type and offer_data.coupon_value:
                self.logger.debug(f"发现商品 {product.asin} 的优惠券: 类型={offer_data.coupon_type}, 值={offer_data.coupon_value}")
                
                # 检查是否已存在相同的优惠券记录
                existing_coupon = db.query(CouponHistory).filter(
                    CouponHistory.product_id == product.asin,
                    CouponHistory.coupon_type == offer_data.coupon_type,
                    CouponHistory.coupon_value == offer_data.coupon_value
                ).first()
                
                if not existing_coupon:
                    # 创建新的优惠券历史记录
                    coupon_history = CouponHistory(
                        product_id=product.asin,
                        coupon_type=offer_data.coupon_type,
                        coupon_value=offer_data.coupon_value,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC)
                    )
                    db.add(coupon_history)
                    self.logger.debug(f"为商品 {product.asin} 添加了新的优惠券历史记录")
                else:
                    # 更新现有优惠券记录的更新时间
                    existing_coupon.updated_at = datetime.now(UTC)
                    self.logger.debug(f"商品 {product.asin} 的优惠券记录已存在，更新时间戳")
        
        # 提交更改
        db.commit()
        
        # 记录优惠券历史记录的数量，用于验证
        coupon_history_count = db.query(CouponHistory).filter(CouponHistory.product_id == product.asin).count()
        self.logger.debug(f"商品 {product.asin} 的优惠券历史记录数量: {coupon_history_count}")
    
    def _process_variants(self, db: Session, product_data: Dict, product: Product) -> int:
        """
        处理商品变体关系
        
        Args:
            db: 数据库会话
            product_data: CJ API返回的商品数据
            product: 保存的商品对象
            
        Returns:
            int: 处理的变体数量
        """
        variant_count = 0
        variant_asins = product_data.get('variant_asin', '').split(',')
        parent_asin = product_data.get('parent_asin')
        
        if parent_asin and variant_asins:
            # 删除旧的变体关系
            db.query(ProductVariant).filter(
                ProductVariant.variant_asin == product.asin
            ).delete()
            
            # 添加新的变体关系
            db_variant = ProductVariant(
                parent_asin=parent_asin,
                variant_asin=product.asin,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            db.add(db_variant)
            variant_count += 1
            
            # 如果商品本身是父ASIN，还需要处理其子变体
            if product.asin == parent_asin and variant_asins and variant_asins[0]:
                for variant_asin in variant_asins:
                    if variant_asin and variant_asin != product.asin:
                        # 检查变体关系是否已存在
                        existing = db.query(ProductVariant).filter(
                            ProductVariant.parent_asin == parent_asin,
                            ProductVariant.variant_asin == variant_asin
                        ).first()
                        
                        if not existing:
                            db_variant = ProductVariant(
                                parent_asin=parent_asin,
                                variant_asin=variant_asin,
                                created_at=datetime.now(UTC),
                                updated_at=datetime.now(UTC)
                            )
                            db.add(db_variant)
                            variant_count += 1
            
            db.commit()
            
        return variant_count
    
    @log_function_call
    def _filter_existing_products(self, db: Session, asins: List[str]) -> List[str]:
        """
        过滤数据库中已存在的商品ASIN
        
        Args:
            db: 数据库会话
            asins: 待检查的ASIN列表
            
        Returns:
            List[str]: 数据库中不存在的ASIN列表
        """
        if not asins:
            return []
            
        # 查询数据库中已存在的ASIN
        existing_asins = db.query(Product.asin).filter(Product.asin.in_(asins)).all()
        existing_asins = [asin[0] for asin in existing_asins]
        
        # 过滤出不存在的ASIN
        new_asins = [asin for asin in asins if asin not in existing_asins]
        
        if existing_asins:
            self.logger.info(f"过滤掉 {len(existing_asins)}/{len(asins)} 个已存在的商品")
            
        return new_asins
    
    @log_function_call
    def _filter_similar_variants(self, products: List[Dict]) -> List[Dict]:
        """
        过滤掉变体中优惠相同的商品（例如仅颜色不同但价格和优惠相同的变体）
        
        两阶段过滤策略：
        1. 先按折扣价格(discount_price)过滤，每个价格点只保留一个变体
        2. 再按完整优惠组合(原价+折扣价+折扣率+优惠券)过滤
        
        Args:
            products: 商品数据列表
            
        Returns:
            List[Dict]: 过滤后的商品数据列表
        """
        if not products:
            return []
            
        # 如果没有变体信息的商品，直接返回原列表
        if not any(p.get('variant_asin') for p in products):
            return products
            
        self.logger.info(f"开始过滤变体中优惠相同的商品，原始商品数: {len(products)}")
        
        # 按parent_asin对商品进行分组
        variants_by_parent = {}
        for product in products:
            parent_asin = product.get('parent_asin')
            if parent_asin:
                if parent_asin not in variants_by_parent:
                    variants_by_parent[parent_asin] = []
                variants_by_parent[parent_asin].append(product)
            
        # 不在变体组中的商品
        standalone_products = [p for p in products if p.get('parent_asin') not in variants_by_parent]
        
        filtered_products = standalone_products.copy()  # 先加入非变体商品
        total_price_filtered = 0
        total_offer_filtered = 0
        
        # 处理每组变体
        for parent_asin, variant_group in variants_by_parent.items():
            self.logger.debug(f"处理变体组 {parent_asin}，包含 {len(variant_group)} 个变体")
            
            # 第一阶段：按折扣价格过滤
            price_filtered_variants = []
            unique_prices = set()  # 保存已处理的折扣价格
            price_filtered_out = 0  # 记录因价格重复而过滤掉的商品数量
            
            for variant in variant_group:
                discount_price = variant.get('discount_price', '0')
                
                # 如果这个价格还没有处理过，保留这个变体
                if discount_price not in unique_prices:
                    unique_prices.add(discount_price)
                    price_filtered_variants.append(variant)
                    self.logger.debug(f"保留变体 {variant.get('asin')}，价格: {discount_price}")
                else:
                    price_filtered_out += 1
                    self.logger.debug(f"过滤掉变体 {variant.get('asin')}，价格相同: {discount_price}")
            
            total_price_filtered += price_filtered_out
            if price_filtered_out > 0:
                self.logger.info(f"变体组 {parent_asin}: 按价格过滤掉 {price_filtered_out} 个变体，剩余 {len(price_filtered_variants)} 个")
            
            # 第二阶段：对价格过滤后的变体，按优惠指纹过滤
            unique_offers = set()
            kept_variants = []
            offer_filtered_out = 0
            
            for variant in price_filtered_variants:
                # 构建优惠信息指纹：价格+折扣+优惠券
                original_price = variant.get('original_price', '0')
                discount_price = variant.get('discount_price', '0')
                discount_percentage = variant.get('discount', '0%')
                coupon = variant.get('coupon', '')
                
                # 创建优惠信息指纹
                offer_fingerprint = f"{original_price}|{discount_price}|{discount_percentage}|{coupon}"
                
                # 如果是新的优惠组合，保留此变体
                if offer_fingerprint not in unique_offers:
                    unique_offers.add(offer_fingerprint)
                    kept_variants.append(variant)
                    self.logger.debug(f"保留变体 {variant.get('asin')}，优惠组合: {offer_fingerprint}")
                else:
                    offer_filtered_out += 1
                    self.logger.debug(f"过滤掉变体 {variant.get('asin')}，优惠组合已存在: {offer_fingerprint}")
            
            total_offer_filtered += offer_filtered_out
            if offer_filtered_out > 0:
                self.logger.info(f"变体组 {parent_asin}: 按优惠组合过滤掉 {offer_filtered_out} 个变体，最终剩余 {len(kept_variants)} 个")
            
            # 将保留的变体添加到结果中
            filtered_products.extend(kept_variants)
            
            # 记录此变体组的过滤情况
            if len(kept_variants) < len(variant_group):
                total_filtered = len(variant_group) - len(kept_variants)
                self.logger.info(f"变体组 {parent_asin} 过滤总结: 原有 {len(variant_group)} 个变体，过滤掉 {total_filtered} 个，最终保留 {len(kept_variants)} 个")
        
        total_filtered = total_price_filtered + total_offer_filtered
        self.logger.info(f"变体过滤完成，原始商品数: {len(products)}，按价格过滤: {total_price_filtered}，按优惠过滤: {total_offer_filtered}，最终保留: {len(filtered_products)}")
        return filtered_products
    
    @log_function_call
    def _filter_products_without_discount_or_coupon(self, products: List[Dict]) -> List[Dict]:
        """
        过滤掉没有优惠或折扣的商品
        
        过滤条件:
        - 商品必须有折扣(discount不为0%)或者优惠券(coupon不为空)
        
        Args:
            products: 商品数据列表
            
        Returns:
            List[Dict]: 过滤后的商品数据列表
        """
        if not products:
            return []
        
        self.logger.info(f"开始过滤没有优惠或折扣的商品，原始商品数: {len(products)}")
        
        # 过滤没有优惠的商品
        filtered_products = []
        filtered_count = 0
        
        for product in products:
            asin = product.get('asin', '未知')
            discount = product.get('discount', '0%')
            coupon = product.get('coupon')
            
            # 检查是否有折扣
            has_discount = discount and discount != '0%'
            # 检查是否有优惠券
            has_coupon = coupon is not None and coupon != ''
            
            if has_discount or has_coupon:
                filtered_products.append(product)
                if has_discount and has_coupon:
                    self.logger.debug(f"保留商品 {asin}，同时具有折扣({discount})和优惠券({coupon})")
                elif has_discount:
                    self.logger.debug(f"保留商品 {asin}，具有折扣({discount})")
                else:
                    self.logger.debug(f"保留商品 {asin}，具有优惠券({coupon})")
            else:
                filtered_count += 1
                self.logger.debug(f"过滤掉商品 {asin}，没有优惠或折扣")
        
        self.logger.info(f"优惠过滤完成，原始商品数: {len(products)}，过滤掉无优惠商品: {filtered_count}，最终保留: {len(filtered_products)}")
        return filtered_products
    
    def _get_random_cursor(self, cursor_history: Dict[str, List[str]], skip_recent: int = 3) -> str:
        """
        从历史游标中随机选择一个，避免最近使用过的游标
        
        Args:
            cursor_history: 游标历史记录，key为游标，value为该游标获取到的ASIN列表
            skip_recent: 跳过最近使用的几个游标
            
        Returns:
            str: 选择的游标
        """
        if not cursor_history or len(cursor_history) <= skip_recent:
            return ""  # 如果历史记录不足，则从头开始
            
        # 按照新发现的商品数量对游标进行排序
        sorted_cursors = sorted(
            cursor_history.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )
        
        # 排除最近使用的几个游标
        recent_cursors = [c[0] for c in sorted_cursors[:skip_recent]]
        available_cursors = [c[0] for c in sorted_cursors[skip_recent:]]
        
        if not available_cursors:
            return ""
        
        # 随机选择一个游标
        return random.choice(available_cursors)
    
    @log_function_call
    async def fetch_and_save_products(
        self,
        db: Session,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        cursor: str = "",
        limit: int = 50,
        country_code: str = "US",
        brand_id: int = 0,
        is_featured_product: int = 2,
        is_amazon_choice: int = 2,
        have_coupon: int = 2,
        discount_min: int = 0,
        save_variants: bool = False,
        skip_existing: bool = True,
        filter_similar_variants: bool = True
    ) -> Tuple[int, int, int, int, int, str, List[str]]:
        """
        从CJ API获取并保存商品数据
        
        Args:
            db: 数据库会话
            category: 商品类别
            subcategory: 商品子类别
            cursor: 分页游标
            limit: 每页数量，最大50
            country_code: 国家代码
            brand_id: 品牌ID
            is_featured_product: 是否精选商品(0:否, 1:是, 2:全部)
            is_amazon_choice: 是否亚马逊之选(0:否, 1:是, 2:全部)
            have_coupon: 是否有优惠券(0:否, 1:是, 2:全部)
            discount_min: 最低折扣率
            save_variants: 是否保存变体关系
            skip_existing: 是否跳过已存在的商品
            filter_similar_variants: 是否过滤优惠相同的变体
            
        Returns:
            Tuple: (成功数, 失败数, 变体数, 优惠券商品数, 折扣商品数, 下一页游标, 所有获取的ASIN列表)
            
        Note:
            此函数会自动过滤没有优惠或折扣的商品，只保留至少满足以下一个条件的商品:
            1. 有折扣(discount字段不为0%)
            2. 有优惠券(coupon字段不为空)
        """
        with LogContext(category=category, have_coupon=have_coupon):
            self.logger.info(f"开始获取CJ平台商品: 类别={category or '全部'}, 子类别={subcategory or '全部'}, 优惠券筛选={have_coupon}, 游标={cursor[:10] if cursor else '无'}...")
            
            # 详细记录当前游标信息
            if cursor:
                self.logger.info(f"当前使用的游标参数: [{cursor[:50]}{'...' if len(cursor) > 50 else ''}]")
            else:
                self.logger.info("当前未使用游标，从第一页开始获取")
            
            # 从CJ API获取商品数据
            try:
                response = await self.api_client.get_products(
                    category=category,
                    subcategory=subcategory,
                    cursor=cursor,
                    limit=limit,
                    country_code=country_code,
                    brand_id=brand_id,
                    is_featured_product=is_featured_product,
                    is_amazon_choice=is_amazon_choice,
                    have_coupon=have_coupon,
                    discount_min=discount_min
                )
            except Exception as e:
                self.logger.error(f"获取CJ商品数据失败: {str(e)}")
                return 0, 0, 0, 0, 0, "", []
            
            if response.get("code") != 0:
                self.logger.error(f"CJ API返回错误: {response.get('message', '未知错误')}")
                return 0, 0, 0, 0, 0, "", []
                
            # 获取商品列表和下一页游标
            products = response.get("data", {}).get("list", [])
            next_cursor = response.get("data", {}).get("cursor", "")
            
            # 记录获取到的下一页游标信息
            if next_cursor:
                self.logger.info(f"API返回的下一页游标: [{next_cursor[:50]}{'...' if len(next_cursor) > 50 else ''}]")
            else:
                self.logger.info("API返回的下一页游标为空，表示已到达最后一页")
            
            if not products:
                self.logger.warning("API返回的商品列表为空")
                return 0, 0, 0, 0, 0, next_cursor, []
                
            self.logger.info(f"获取到 {len(products)} 个CJ商品数据")
            
            # 提取所有商品的ASIN
            all_asins = [p.get("asin") for p in products if p.get("asin")]
            
            # 过滤掉没有优惠或折扣的商品
            products = self._filter_products_without_discount_or_coupon(products)
            if not products:
                self.logger.warning("所有商品都没有优惠或折扣，跳过处理")
                return 0, 0, 0, 0, 0, next_cursor, all_asins
            
            # 过滤掉变体中优惠相同的商品
            if filter_similar_variants:
                products = self._filter_similar_variants(products)
                self.logger.info(f"变体优惠过滤后剩余 {len(products)} 个商品")
            
            # 如果需要跳过已存在的商品，过滤ASIN列表
            if skip_existing:
                filtered_asins = self._filter_existing_products(db, [p.get("asin") for p in products if p.get("asin")])
                if not filtered_asins:
                    self.logger.info("所有商品已存在于数据库中，跳过处理")
                    return 0, 0, 0, 0, 0, next_cursor, all_asins
                    
                # 过滤产品列表，只保留新的商品
                products = [p for p in products if p.get("asin") in filtered_asins]
                self.logger.info(f"过滤后剩余 {len(products)} 个新商品需要处理")
            
            # 初始化计数器
            success_count = 0
            fail_count = 0
            variant_count = 0
            coupon_count = 0
            discount_count = 0
            
            # 将API商品数据转换为ProductInfo对象
            product_infos = []
            for product_data in products:
                try:
                    product_info = self._convert_cj_product_to_model(product_data)
                    product_infos.append((product_info, product_data))
                except Exception as e:
                    fail_count += 1
                    asin = product_data.get("asin", "未知")
                    self.logger.error(f"处理商品 {asin} 数据转换失败: {str(e)}")
            
            # 如果没有有效的商品数据，直接返回
            if not product_infos:
                self.logger.warning("没有有效的商品数据需要处理")
                return 0, fail_count, 0, 0, 0, next_cursor, all_asins
            
            # 批量异步生成推广链接
            try:
                self.logger.debug(f"开始为 {len(product_infos)} 个商品生成推广链接")
                await self._batch_generate_promo_links([p[0] for p in product_infos])
                
                # 检查推广链接生成情况
                success_links = sum(1 for p in product_infos if p[0].cj_url is not None)
                self.logger.debug(f"推广链接生成情况: 成功 {success_links}/{len(product_infos)}")
                
                # 记录缺失推广链接的商品
                missing_links = [p[0].asin for p in product_infos if p[0].cj_url is None]
                if missing_links:
                    self.logger.warning(f"以下商品未能生成推广链接: {missing_links}")
            except Exception as e:
                self.logger.error(f"批量生成推广链接失败: {str(e)}")
                # 继续处理，不中断流程
            
            # 处理每个商品：保存到数据库、处理优惠信息和变体关系
            for product_info, product_data in product_infos:
                try:
                    # 确保有推广链接，即使是默认构造的
                    if not product_info.cj_url:
                        default_link = f"https://www.amazon.com/dp/{product_info.asin}?tag=default"
                        product_info.cj_url = default_link
                        self.logger.debug(f"为商品 {product_info.asin} 设置默认推广链接: {default_link}")
                    
                    # 根据优惠券状态确定商品来源
                    source = "coupon" if (product_info.offers and product_info.offers[0].coupon_type and product_info.offers[0].coupon_value) else "discount"
                    
                    # 确保api_provider字段一定设置为cj-api
                    product_info.api_provider = "cj-api"
                    
                    # 保存或更新商品信息，显式传递source
                    product = ProductService.create_or_update_product(db, product_info, source)
                    
                    # 检查推广链接是否正确保存到数据库
                    if not product.cj_url:
                        self.logger.warning(f"商品 {product.asin} 的推广链接未正确保存到数据库，尝试直接更新")
                        product.cj_url = product_info.cj_url
                        db.commit()
                        
                    # 处理优惠信息
                    self._process_offers(db, product, product_info)
                    
                    # 处理变体关系
                    if save_variants:
                        variant_count += self._process_variants(db, product_data, product)
                    
                    # 确保api_provider字段设置为cj-api (直接设置数据库对象字段)
                    if product.api_provider != "cj-api":
                        product.api_provider = "cj-api"
                        db.commit()
                    
                    # 更新计数器
                    success_count += 1
                    if product_data.get("coupon"):
                        coupon_count += 1
                    else:
                        discount_count += 1
                        
                    if success_count % 10 == 0:
                        self.logger.debug(f"已处理 {success_count} 个商品")
                        
                except Exception as e:
                    fail_count += 1
                    asin = product_data.get("asin", "未知")
                    self.logger.error(f"处理商品 {asin} 失败: {str(e)}")
            
            # 记录推广链接状态
            saved_with_links = db.query(Product).filter(
                Product.asin.in_([p[0].asin for p in product_infos]),
                Product.cj_url.isnot(None)
            ).count()
            
            self.logger.debug(f"数据库中成功保存推广链接的商品数: {saved_with_links}/{success_count}")
            
            # 记录优惠券信息的处理情况
            if coupon_count > 0:
                # 获取所有带优惠券的商品ASIN
                coupon_asins = [p[0].asin for p in product_infos if p[0].offers and p[0].offers[0].coupon_type and p[0].offers[0].coupon_value]
                
                # 查询这些商品在优惠券历史表中的记录数
                coupon_history_count = db.query(CouponHistory).filter(
                    CouponHistory.product_id.in_(coupon_asins)
                ).count()
                
                # 查询这些商品在Offer表中的优惠券记录数
                offer_coupon_count = db.query(Offer).filter(
                    Offer.product_id.in_(coupon_asins),
                    Offer.coupon_type.isnot(None),
                    Offer.coupon_value.isnot(None)
                ).count()
                
                self.logger.info(f"优惠券信息统计: 带优惠券商品={coupon_count}, Offer表中记录={offer_coupon_count}, CouponHistory表中记录={coupon_history_count}")
                
                # 检查是否有优惠券信息没有被正确保存
                if coupon_history_count < coupon_count:
                    self.logger.warning(f"发现 {coupon_count - coupon_history_count} 个商品的优惠券信息未保存到CouponHistory表")
                    
                    # 列出未保存优惠券历史的商品
                    saved_coupon_history_asins = [ch[0] for ch in db.query(CouponHistory.product_id).filter(
                        CouponHistory.product_id.in_(coupon_asins)
                    ).all()]
                    
                    missing_asins = [asin for asin in coupon_asins if asin not in saved_coupon_history_asins]
                    if missing_asins:
                        self.logger.warning(f"未保存优惠券历史的商品: {missing_asins[:10]}{' 等' if len(missing_asins) > 10 else ''}")
            
            self.logger.success(f"批次完成，成功: {success_count}，失败: {fail_count}，优惠券: {coupon_count}，折扣: {discount_count}，变体: {variant_count}")
            return success_count, fail_count, variant_count, coupon_count, discount_count, next_cursor, all_asins
    
    @log_function_call
    async def fetch_all_products(
        self,
        db: Session,
        max_items: int = 1000,
        use_random_cursor: bool = False,  # 默认不使用随机游标
        skip_existing: bool = True,
        use_persistent_cursor: bool = True,  # 默认使用持久化游标
        filter_similar_variants: bool = True,  # 是否过滤优惠相同的变体
        **kwargs
    ) -> Tuple[int, int, int, int, int]:
        """
        分页获取所有商品数据直到达到最大数量
        
        Args:
            db: 数据库会话
            max_items: 最大获取商品数量
            use_random_cursor: 是否使用随机游标策略
            skip_existing: 是否跳过已存在的商品
            use_persistent_cursor: 是否使用持久化游标
            filter_similar_variants: 是否过滤优惠相同的变体
            **kwargs: 传递给fetch_and_save_products的参数
            
        Returns:
            Tuple: (成功数, 失败数, 变体数, 优惠券商品数, 折扣商品数)
        """
        with LogContext(max_items=max_items):
            self.logger.info(f"开始批量获取商品，最大数量: {max_items}，使用随机游标: {use_random_cursor}，使用持久化游标: {use_persistent_cursor}，跳过已存在: {skip_existing}，过滤相似变体: {filter_similar_variants}，参数: {kwargs}")
            
            limit = min(kwargs.pop("limit", 50), 50)  # 单次获取数量，最大50
            
            # 初始化计数器和游标
            total_success = 0
            total_fail = 0
            total_variants = 0
            total_coupon = 0
            total_discount = 0
            
            # 根据设置决定游标策略
            if use_persistent_cursor:
                # 使用持久化游标策略
                cursor = self._select_cursor()
                self.logger.info(f"使用持久化游标策略，初始游标: {cursor[:30] if cursor else '空'}")
            else:
                # 使用旧的随机游标策略或空游标
                cursor = ""
            
            # 临时存储本次执行的游标历史，用于随机游标策略
            temp_cursor_history = {}
            empty_count = 0  # 连续获取不到新商品的次数
            
            # 分页获取所有商品
            while total_success + total_fail < max_items:
                # 使用随机游标策略（仅当启用且非持久化模式时）
                if use_random_cursor and not use_persistent_cursor and temp_cursor_history and empty_count > 0:
                    cursor = self._get_random_cursor(temp_cursor_history)
                    self.logger.debug(f"使用临时随机游标: {cursor[:10] if cursor else '无'}...")
                
                # 计算单次获取数量
                remaining = max_items - (total_success + total_fail)
                batch_limit = min(limit, remaining)
                
                # 获取一批商品
                success, fail, variants, coupon, discount, next_cursor, asins = await self.fetch_and_save_products(
                    db=db,
                    cursor=cursor,
                    limit=batch_limit,
                    skip_existing=skip_existing,
                    filter_similar_variants=filter_similar_variants,
                    **kwargs
                )
                
                # 记录当前游标获取到的ASIN
                if cursor not in temp_cursor_history:
                    temp_cursor_history[cursor] = []
                temp_cursor_history[cursor].extend(asins)
                
                # 更新计数器
                total_success += success
                total_fail += fail
                total_variants += variants
                total_coupon += coupon
                total_discount += discount
                
                # 如果使用持久化游标，更新游标历史
                if use_persistent_cursor:
                    self._update_cursor_history(cursor, asins, success)
                
                self.logger.info(f"当前进度: 已获取 {total_success + total_fail}/{max_items} 个商品")
                
                # 检查是否获取到新商品
                if success == 0:
                    empty_count += 1
                    self.logger.warning(f"连续 {empty_count} 次未获取到新商品")
                    
                    # 检查游标是否相同，如果相同则可能存在循环问题
                    if cursor == next_cursor:
                        self.logger.warning("当前游标与下一页游标相同，退出循环以避免无限循环!")
                        break
                        
                    # 只有在没有next_cursor时才考虑结束爬取
                    if not next_cursor:
                        self.logger.info("没有下一页游标，爬取完成")
                        break
                    else:
                        # 有next_cursor，继续使用它向下翻页
                        self.logger.info(f"虽然没有新商品，但继续使用API返回的next_cursor: {next_cursor[:10] if next_cursor else '无'}...")
                else:
                    empty_count = 0  # 获取到新商品，重置计数器
                
                # 详细记录分页参数
                self.logger.info(f"进入下一页分页 - 当前游标: [{cursor[:30]}{'...' if len(cursor) > 30 else ''}], 下一页游标: [{next_cursor[:30]}{'...' if len(next_cursor) > 30 else ''}]")
                if cursor == next_cursor:
                    self.logger.warning("警告: 当前游标与下一页游标相同，可能会导致重复数据!")
                
                # 更新游标
                cursor = next_cursor
                
                # 等待一段时间，避免API限流
                await asyncio.sleep(0.5)
                
            self.logger.success(f"批量获取完成，成功: {total_success}，失败: {total_fail}，优惠券: {total_coupon}，折扣: {total_discount}，变体: {total_variants}")
            return total_success, total_fail, total_variants, total_coupon, total_discount

    @log_function_call
    async def fetch_all_products_parallel(
        self,
        db: Session,
        max_items: int = 1000,
        max_workers: int = 3,  # 并行工作数
        skip_existing: bool = True,
        filter_similar_variants: bool = True,
        **kwargs
    ) -> Tuple[int, int, int, int, int]:
        """并行抓取商品数据
        
        Args:
            db: 数据库会话
            max_items: 最大获取商品数量
            max_workers: 并行工作进程数量
            skip_existing: 是否跳过已存在的商品
            filter_similar_variants: 是否过滤优惠相同的变体
            **kwargs: 传递给fetch_all_products的参数
            
        Returns:
            Tuple: (成功数, 失败数, 变体数, 优惠券商品数, 折扣商品数)
        """
        with LogContext(max_items=max_items, max_workers=max_workers):
            self.logger.info(f"开始并行抓取商品，最大数量: {max_items}，工作进程数: {max_workers}")
            
            # 创建共享计数器
            total_success = 0
            total_fail = 0
            total_variants = 0
            total_coupon = 0
            total_discount = 0
            
            # 共享计数器锁
            success_counter_lock = asyncio.Lock()
            
            # 每个工作进程处理的商品数
            items_per_worker = max(10, max_items // max_workers)
            
            # 定义工作进程函数
            async def worker(worker_id):
                nonlocal total_success, total_fail, total_variants, total_coupon, total_discount
                
                # 为这个工作进程选择游标
                cursor = self._select_cursor()
                self.logger.info(f"工作进程 {worker_id} 使用游标: {cursor[:30] if cursor else '空'}")
                
                # 为这个工作进程设置单独的数据库会话
                from models.database import SessionLocal
                worker_db = SessionLocal()
                
                try:
                    # 调用现有的抓取方法
                    success, fail, variants, coupon, discount = await self.fetch_all_products(
                        db=worker_db,
                        max_items=items_per_worker,
                        cursor=cursor,
                        skip_existing=skip_existing,
                        filter_similar_variants=filter_similar_variants,
                        **kwargs
                    )
                    
                    # 获取锁，更新共享计数器
                    async with success_counter_lock:
                        total_success += success
                        total_fail += fail
                        total_variants += variants
                        total_coupon += coupon
                        total_discount += discount
                        
                    self.logger.success(f"工作进程 {worker_id} 完成，成功: {success}，失败: {fail}")
                    
                except Exception as e:
                    self.logger.error(f"工作进程 {worker_id} 出错: {str(e)}")
                finally:
                    # 关闭工作进程的数据库会话
                    worker_db.close()
            
            # 创建并运行所有工作进程
            tasks = [worker(i) for i in range(max_workers)]
            await asyncio.gather(*tasks)
            
            self.logger.success(f"并行抓取完成，总计: 成功={total_success}，失败={total_fail}，" 
                              f"优惠券={total_coupon}，折扣={total_discount}，变体={total_variants}")
                              
            return total_success, total_fail, total_variants, total_coupon, total_discount

    def _partition_cursors(self) -> Dict[str, List[str]]:
        """将游标按类别分区
        
        Returns:
            Dict[str, List[str]]: 按类别分组的游标字典
        """
        cursor_history = self.cursor_history
        partitions = {}
        
        for cursor in cursor_history:
            # 提取类别标识（假设游标格式包含类别信息）
            category = self._extract_category_from_cursor(cursor)
            if category not in partitions:
                partitions[category] = []
            
            partitions[category].append(cursor)
        
        # 记录分区情况
        for category, cursors in partitions.items():
            self.logger.debug(f"游标分区 '{category}': {len(cursors)} 个游标")
            
        return partitions
    
    def _extract_category_from_cursor(self, cursor: str) -> str:
        """从游标中提取类别信息
        
        Args:
            cursor: 游标字符串
            
        Returns:
            str: 提取的类别标识符
        """
        # 示例实现，实际根据游标格式调整
        # 尝试提取可能的类别标识
        if not cursor:
            return "default"
            
        # 尝试使用 "=" 分割提取参数
        if "=" in cursor:
            # 检查是否包含category参数
            parts = cursor.split("&")
            for part in parts:
                if part.startswith("category="):
                    category = part.split("=")[1]
                    return category
                if part.startswith("subcategory="):
                    subcategory = part.split("=")[1]
                    return subcategory
        
        # 尝试将游标按"-"分割
        parts = cursor.split("-")
        if len(parts) > 1:
            return parts[0]
            
        # 退化情况：直接使用游标的前10个字符作为标识
        if len(cursor) > 10:
            return cursor[:10]
            
        return "default"

@log_function_call
async def main():
    """命令行入口函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='CJ商品爬虫')
    parser.add_argument('--category', type=str, help='商品类别')
    parser.add_argument('--subcategory', type=str, help='商品子类别')
    parser.add_argument('--limit', type=int, default=100, help='最大获取数量')
    parser.add_argument('--have-coupon', type=int, choices=[0, 1, 2], default=2, 
                       help='是否有优惠券(0:无 1:有 2:全部)')
    parser.add_argument('--min-discount', type=int, default=0, help='最低折扣率')
    parser.add_argument('--save-variants', action='store_true', help='是否保存变体关系')
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--random-cursor', action='store_true', help='使用随机游标策略')
    parser.add_argument('--no-skip-existing', action='store_true', help='不跳过已存在的商品')
    parser.add_argument('--no-filter-variants', action='store_true', help='不过滤优惠相同的变体商品')
    parser.add_argument('--parallel', action='store_true', help='启用并行抓取')
    parser.add_argument('--workers', type=int, default=3, help='并行工作进程数量')
    
    args = parser.parse_args()
    
    # 创建日志记录器
    logger = get_logger("CJProductsCrawler")
    
    with LogContext(
        category=args.category, 
        subcategory=args.subcategory, 
        limit=args.limit, 
        have_coupon=args.have_coupon,
        debug=args.debug,
        random_cursor=args.random_cursor,
        skip_existing=not args.no_skip_existing,
        filter_variants=not args.no_filter_variants,
        parallel=args.parallel,
        workers=args.workers
    ):
        logger.info(f"启动CJ商品爬虫: 类别={args.category or '全部'}, 子类别={args.subcategory or '全部'}, "
                   f"最大数量={args.limit}, 优惠券筛选={args.have_coupon}, 最低折扣={args.min_discount}, "
                   f"随机游标={args.random_cursor}, 跳过已存在={not args.no_skip_existing}, "
                   f"过滤相似变体={not args.no_filter_variants}, 并行抓取={args.parallel}, "
                   f"工作进程数={args.workers if args.parallel else 1}")
        
        # 创建爬虫实例
        crawler = CJProductsCrawler()
        
        # 创建数据库会话
        from models.database import SessionLocal
        db = SessionLocal()
        
        try:
            if args.parallel:
                # 使用并行抓取
                success, fail, variants, coupon, discount = await crawler.fetch_all_products_parallel(
                    db=db,
                    max_items=args.limit,
                    max_workers=args.workers,
                    category=args.category,
                    subcategory=args.subcategory,
                    have_coupon=args.have_coupon,
                    discount_min=args.min_discount,
                    save_variants=args.save_variants,
                    skip_existing=not args.no_skip_existing,
                    filter_similar_variants=not args.no_filter_variants
                )
            else:
                # 使用常规抓取
                success, fail, variants, coupon, discount = await crawler.fetch_all_products(
                    db=db,
                    max_items=args.limit,
                    category=args.category,
                    subcategory=args.subcategory,
                    have_coupon=args.have_coupon,
                    discount_min=args.min_discount,
                    save_variants=args.save_variants,
                    use_random_cursor=args.random_cursor,
                    skip_existing=not args.no_skip_existing,
                    use_persistent_cursor=True,
                    filter_similar_variants=not args.no_filter_variants
                )
            
            # 输出结果
            result_msg = f"爬取完成，成功: {success}, 失败: {fail}, 优惠券: {coupon}, 折扣: {discount}, 变体关系: {variants}"
            logger.success(result_msg)
            print(result_msg)
            
            # 验证优惠券信息是否正确保存
            if coupon > 0:
                # 查询优惠券历史记录数
                coupon_history_count = db.query(CouponHistory).count()
                
                # 如果使用了--have-coupon=1，则验证是否所有商品都有优惠券历史记录
                if args.have_coupon == 1:
                    # 获取最近添加的商品
                    recent_products = db.query(Product).order_by(desc(Product.created_at)).limit(success).all()
                    recent_asins = [p.asin for p in recent_products]
                    
                    # 查询这些商品在优惠券历史表中的记录数
                    recent_coupon_history_count = db.query(CouponHistory).filter(
                        CouponHistory.product_id.in_(recent_asins)
                    ).count()
                    
                    logger.info(f"优惠券历史记录验证: 总记录数={coupon_history_count}, 最近添加商品的记录数={recent_coupon_history_count}/{success}")
                    
                    # 如果优惠券历史记录数少于优惠券商品数，输出警告
                    if recent_coupon_history_count < coupon:
                        # 查找哪些商品没有优惠券历史记录
                        saved_coupon_history_asins = [ch[0] for ch in db.query(CouponHistory.product_id).filter(
                            CouponHistory.product_id.in_(recent_asins)
                        ).all()]
                        
                        missing_asins = [asin for asin in recent_asins if asin not in saved_coupon_history_asins]
                        if missing_asins:
                            logger.warning(f"以下商品未保存优惠券历史记录: {missing_asins[:10]}{' 等' if len(missing_asins) > 10 else ''}")
                            
                            # 尝试补充添加优惠券历史记录
                            for asin in missing_asins:
                                try:
                                    # 获取商品的优惠信息
                                    offer = db.query(Offer).filter(
                                        Offer.product_id == asin,
                                        Offer.coupon_type.isnot(None),
                                        Offer.coupon_value.isnot(None)
                                    ).first()
                                    
                                    if offer:
                                        # 添加优惠券历史记录
                                        coupon_history = CouponHistory(
                                            product_id=asin,
                                            coupon_type=offer.coupon_type,
                                            coupon_value=offer.coupon_value,
                                            created_at=datetime.now(UTC),
                                            updated_at=datetime.now(UTC)
                                        )
                                        db.add(coupon_history)
                                        logger.debug(f"为商品 {asin} 补充添加了优惠券历史记录")
                                except Exception as e:
                                    logger.error(f"补充添加优惠券历史记录失败: {str(e)}")
                            
                            # 提交更改
                            db.commit()
                            
                            # 再次验证
                            fixed_coupon_history_count = db.query(CouponHistory).filter(
                                CouponHistory.product_id.in_(recent_asins)
                            ).count()
                            
                            logger.info(f"补充后的优惠券历史记录数: {fixed_coupon_history_count}/{coupon}")
                    else:
                        logger.info("所有优惠券商品都已正确保存优惠券历史记录")
                else:
                    logger.info(f"数据库中共有 {coupon_history_count} 条优惠券历史记录")
            
            # 如果指定了输出文件，则保存ASIN列表
            if args.output:
                # 获取所有商品的ASIN
                products = db.query(Product).order_by(desc(Product.created_at)).limit(args.limit).all()
                asins = [p.asin for p in products]
                
                # 写入文件
                with open(args.output, 'w') as f:
                    f.write('\n'.join(asins))
                    
                logger.info(f"ASIN列表已保存到: {args.output}")
                print(f"ASIN列表已保存到: {args.output}")
                
        except Exception as e:
            logger.error(f"爬虫执行失败: {str(e)}")
            print(f"爬虫执行失败: {str(e)}")
            
        finally:
            db.close()

if __name__ == "__main__":
    asyncio.run(main()) 