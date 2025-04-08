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
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, UTC
from pathlib import Path
import argparse
import random

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.database import Product, ProductVariant, Offer
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
                            self.logger.debug(f"成功设置商品 {asin} 的推广链接")
                    
                    # 设置未返回链接的商品为None
                    for asin in batch_asins:
                        if asin not in result and asin in asin_to_product_info:
                            asin_to_product_info[asin].cj_url = None
                            self.logger.warning(f"商品 {asin} 未获取到推广链接")
                    
                except Exception as e:
                    self.logger.error(f"批量生成推广链接失败: {str(e)}")
                    # 将这批商品的链接设置为None
                    for asin in batch_asins:
                        if asin in asin_to_product_info:
                            asin_to_product_info[asin].cj_url = None
                
                # 避免API限流
                if i + 10 < len(asins):
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            self.logger.error(f"批量生成推广链接过程中发生错误: {str(e)}")
            # 确保所有商品都有cj_url值，即使是None
            for p in product_infos:
                if p.cj_url is None:
                    p.cj_url = None
    
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
            cj_url=None  # 初始化为None，稍后会生成
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
        
        db.commit()
    
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
        skip_existing: bool = True
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
            
        Returns:
            Tuple: (成功数, 失败数, 变体数, 优惠券商品数, 折扣商品数, 下一页游标, 所有获取的ASIN列表)
        """
        with LogContext(category=category, have_coupon=have_coupon):
            self.logger.info(f"开始获取CJ平台商品: 类别={category or '全部'}, 子类别={subcategory or '全部'}, 优惠券筛选={have_coupon}, 游标={cursor[:10] if cursor else '无'}...")
            
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
            
            if not products:
                self.logger.warning("API返回的商品列表为空")
                return 0, 0, 0, 0, 0, next_cursor, []
                
            self.logger.info(f"获取到 {len(products)} 个CJ商品数据")
            
            # 提取所有商品的ASIN
            all_asins = [p.get("asin") for p in products if p.get("asin")]
            
            # 如果需要跳过已存在的商品，过滤ASIN列表
            if skip_existing:
                filtered_asins = self._filter_existing_products(db, all_asins)
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
                await self._batch_generate_promo_links([p[0] for p in product_infos])
            except Exception as e:
                self.logger.error(f"批量生成推广链接失败: {str(e)}")
                # 继续处理，不中断流程
            
            # 处理每个商品：保存到数据库、处理优惠信息和变体关系
            for product_info, product_data in product_infos:
                try:
                    # 根据优惠券状态确定商品来源
                    source = "coupon" if product_data.get("coupon") else "discount"
                    
                    # 保存或更新商品信息
                    product = ProductService.create_or_update_product(db, product_info, source)
                    
                    # 处理优惠信息
                    self._process_offers(db, product, product_info)
                    
                    # 处理变体关系
                    if save_variants:
                        variant_count += self._process_variants(db, product_data, product)
                    
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
            
            self.logger.success(f"批次完成，成功: {success_count}，失败: {fail_count}，优惠券: {coupon_count}，折扣: {discount_count}，变体: {variant_count}")
            return success_count, fail_count, variant_count, coupon_count, discount_count, next_cursor, all_asins
    
    @log_function_call
    async def fetch_all_products(
        self,
        db: Session,
        max_items: int = 1000,
        use_random_cursor: bool = True,
        skip_existing: bool = True,
        **kwargs
    ) -> Tuple[int, int, int, int, int]:
        """
        分页获取所有商品数据直到达到最大数量
        
        Args:
            db: 数据库会话
            max_items: 最大获取商品数量
            use_random_cursor: 是否使用随机游标策略
            skip_existing: 是否跳过已存在的商品
            **kwargs: 传递给fetch_and_save_products的参数
            
        Returns:
            Tuple: (成功数, 失败数, 变体数, 优惠券商品数, 折扣商品数)
        """
        with LogContext(max_items=max_items):
            self.logger.info(f"开始批量获取商品，最大数量: {max_items}，使用随机游标: {use_random_cursor}，跳过已存在: {skip_existing}，参数: {kwargs}")
            
            limit = min(kwargs.pop("limit", 50), 50)  # 单次获取数量，最大50
            
            # 初始化计数器和游标
            total_success = 0
            total_fail = 0
            total_variants = 0
            total_coupon = 0
            total_discount = 0
            cursor = ""
            
            # 保存游标历史记录，key为游标，value为该游标获取到的ASIN列表
            cursor_history = {}
            empty_count = 0  # 连续获取不到新商品的次数
            
            # 分页获取所有商品
            while total_success + total_fail < max_items:
                # 如果启用随机游标，且已经有一些历史记录，从历史中选择一个游标
                if use_random_cursor and cursor_history and empty_count > 0:
                    cursor = self._get_random_cursor(cursor_history)
                    self.logger.debug(f"使用随机游标: {cursor[:10] if cursor else '无'}...")
                
                # 计算单次获取数量
                remaining = max_items - (total_success + total_fail)
                batch_limit = min(limit, remaining)
                
                # 获取一批商品
                success, fail, variants, coupon, discount, next_cursor, asins = await self.fetch_and_save_products(
                    db=db,
                    cursor=cursor,
                    limit=batch_limit,
                    skip_existing=skip_existing,
                    **kwargs
                )
                
                # 记录当前游标获取到的ASIN
                if cursor not in cursor_history:
                    cursor_history[cursor] = []
                cursor_history[cursor].extend(asins)
                
                # 更新计数器
                total_success += success
                total_fail += fail
                total_variants += variants
                total_coupon += coupon
                total_discount += discount
                
                self.logger.info(f"当前进度: 已获取 {total_success + total_fail}/{max_items} 个商品")
                
                # 检查是否获取到新商品
                if success == 0:
                    empty_count += 1
                    self.logger.warning(f"连续 {empty_count} 次未获取到新商品")
                    
                    # 如果连续多次未获取到新商品，考虑使用随机游标或重置游标
                    if empty_count >= 3:
                        if use_random_cursor and len(cursor_history) > 5:
                            cursor = self._get_random_cursor(cursor_history, skip_recent=5)
                            self.logger.info(f"多次未获取到新商品，使用随机游标: {cursor[:10] if cursor else '无'}...")
                        else:
                            cursor = ""  # 重置游标，从头开始
                            self.logger.info("多次未获取到新商品，重置游标从头开始")
                        
                        empty_count = 0  # 重置计数器
                        continue
                else:
                    empty_count = 0  # 获取到新商品，重置计数器
                
                # 如果没有下一页或者没有获取到任何商品，且已经尝试过随机游标，则退出循环
                if not next_cursor or (success == 0 and fail == 0 and empty_count >= 5):
                    break
                    
                # 更新游标
                cursor = next_cursor
                
                # 等待一段时间，避免API限流
                await asyncio.sleep(0.5)
                
            self.logger.success(f"批量获取完成，成功: {total_success}，失败: {total_fail}，优惠券: {total_coupon}，折扣: {total_discount}，变体: {total_variants}")
            return total_success, total_fail, total_variants, total_coupon, total_discount

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
        skip_existing=not args.no_skip_existing
    ):
        logger.info(f"启动CJ商品爬虫: 类别={args.category or '全部'}, 子类别={args.subcategory or '全部'}, "
                   f"最大数量={args.limit}, 优惠券筛选={args.have_coupon}, 最低折扣={args.min_discount}, "
                   f"随机游标={args.random_cursor}, 跳过已存在={not args.no_skip_existing}")
        
        # 创建爬虫实例
        crawler = CJProductsCrawler()
        
        # 创建数据库会话
        from models.database import SessionLocal
        db = SessionLocal()
        
        try:
            # 获取所有商品
            success, fail, variants, coupon, discount = await crawler.fetch_all_products(
                db=db,
                max_items=args.limit,
                category=args.category,
                subcategory=args.subcategory,
                have_coupon=args.have_coupon,
                discount_min=args.min_discount,
                save_variants=args.save_variants,
                use_random_cursor=args.random_cursor,
                skip_existing=not args.no_skip_existing
            )
            
            # 输出结果
            result_msg = f"爬取完成，成功: {success}, 失败: {fail}, 优惠券: {coupon}, 折扣: {discount}, 变体关系: {variants}"
            logger.success(result_msg)
            print(result_msg)
            
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