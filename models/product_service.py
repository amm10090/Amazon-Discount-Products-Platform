from typing import List, Optional, Dict, Any, Tuple, Union
import logging
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey, or_, cast, and_
import json

# 配置logger
logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from datetime import datetime, timedelta, timezone # 导入 timezone
from .database import Product, Offer, CouponHistory
from .product import ProductInfo, ProductOffer
from functools import lru_cache

class ProductService:
    """
    商品服务类
    提供商品的增删改查等数据库操作方法
    """
    
    @staticmethod
    def create_product(db: Session, product_info: ProductInfo, source: str = "pa-api") -> Product:
        """创建新商品记录"""
        # 获取第一个优惠（通常是最佳优惠）
        best_offer = product_info.offers[0] if product_info.offers else None
        
        # 创建产品记录
        db_product = Product(
            asin=product_info.asin,
            title=product_info.title,
            url=product_info.url,
            brand=product_info.brand,
            main_image=product_info.main_image,
            
            # CJ特有信息
            cj_url=product_info.cj_url if hasattr(product_info, 'cj_url') else None,
            
            # 价格信息
            current_price=best_offer.price if best_offer else None,
            original_price=best_offer.price + best_offer.savings if best_offer and best_offer.savings else None,
            currency=best_offer.currency if best_offer else None,
            savings_amount=best_offer.savings if best_offer else None,
            savings_percentage=best_offer.savings_percentage if best_offer else None,
            
            # Prime信息
            is_prime=best_offer.is_prime if best_offer else None,
            is_prime_exclusive=False,  # 需要从API响应中提取
            
            # 商品状态
            condition=best_offer.condition if best_offer else None,
            availability=best_offer.availability if best_offer else None,
            merchant_name=best_offer.merchant_name if best_offer else None,
            is_buybox_winner=best_offer.is_buybox_winner if best_offer else None,
            
            # 其他信息
            deal_type=best_offer.deal_type if best_offer else None,
            features=json.dumps([]) if not product_info.features else json.dumps(product_info.features),
            
            # 分类信息
            categories=json.dumps(product_info.categories) if product_info.categories else json.dumps([]),
            browse_nodes=json.dumps(product_info.browse_nodes) if product_info.browse_nodes else json.dumps([]),
            binding=product_info.binding,
            product_group=product_info.product_group,
            
            # 元数据
            source=source,
            api_provider=product_info.api_provider if hasattr(product_info, 'api_provider') else "pa-api",
            raw_data=json.dumps(product_info.dict())
        )
        
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def manual_create_product(db: Session, product_info: ProductInfo) -> ProductInfo:
        """
        手动创建新商品记录
        
        Args:
            db: 数据库会话
            product_info: 用户提供的完整商品信息
            
        Returns:
            ProductInfo: 创建成功的商品信息
            
        Raises:
            ValueError: 如果ASIN已存在或缺少必要信息
            Exception: 如果数据库操作失败
        """
        # 检查ASIN是否已存在
        existing_product = db.query(Product).filter(Product.asin == product_info.asin).first()
        if existing_product:
            raise ValueError(f"ASIN {product_info.asin} 已存在，无法手动创建。")
            
        # 检查是否有offers信息
        if not product_info.offers:
            raise ValueError("必须至少提供一个商品优惠信息 (offer)。")
            
        try:
            current_time = datetime.now(timezone.utc) # 使用 timezone.utc
            best_offer = product_info.offers[0] # 取第一个offer作为主要信息来源

            # 序列化列表和字典类型的字段
            features = json.dumps(product_info.features or [])
            categories = json.dumps(product_info.categories or [])
            browse_nodes = json.dumps(product_info.browse_nodes or [])
            # raw_data可以由用户提供，或基于输入信息生成
            raw_data = json.dumps(product_info.raw_data or product_info.dict(exclude={'raw_data'})) # 优先用用户提供的

            # 创建 Product 对象
            db_product = Product(
                asin=product_info.asin,
                title=product_info.title,
                url=product_info.url,
                brand=product_info.brand,
                main_image=product_info.main_image,
                
                cj_url=product_info.cj_url,
                
                # 使用第一个offer的信息填充主要价格字段
                current_price=best_offer.price,
                original_price=best_offer.original_price, # 使用offer中的原始价格
                currency=best_offer.currency,
                savings_amount=best_offer.savings,
                savings_percentage=best_offer.savings_percentage,
                
                is_prime=best_offer.is_prime,
                is_prime_exclusive=False, # 手动添加时默认为False，或允许用户在ProductInfo中指定？(模型暂无)

                condition=best_offer.condition,
                availability=best_offer.availability,
                merchant_name=best_offer.merchant_name,
                is_buybox_winner=best_offer.is_buybox_winner,
                
                binding=product_info.binding,
                product_group=product_info.product_group,
                categories=categories,
                browse_nodes=browse_nodes,
                
                deal_type=best_offer.deal_type,
                features=features,
                
                # 时间戳 - timestamp由用户提供，created/updated自动生成
                created_at=current_time,
                updated_at=current_time,
                discount_updated_at=current_time, # 折扣更新时间设为当前
                timestamp=product_info.timestamp or current_time, # 优先使用用户提供的时间戳
                
                source=product_info.source or "manual", # 默认为 manual
                api_provider=product_info.api_provider or "manual", # 默认为 manual
                raw_data=raw_data
            )
            
            db.add(db_product)
            
            # 创建 Offer 对象
            for offer_info in product_info.offers:
                offer = Offer(
                    product_id=db_product.asin,
                    condition=offer_info.condition,
                    price=offer_info.price,
                    currency=offer_info.currency,
                    savings=offer_info.savings,
                    savings_percentage=offer_info.savings_percentage,
                    is_prime=offer_info.is_prime,
                    is_amazon_fulfilled=offer_info.is_amazon_fulfilled,
                    is_free_shipping_eligible=offer_info.is_free_shipping_eligible,
                    availability=offer_info.availability,
                    merchant_name=offer_info.merchant_name,
                    is_buybox_winner=offer_info.is_buybox_winner,
                    deal_type=offer_info.deal_type,
                    coupon_type=offer_info.coupon_type,
                    coupon_value=offer_info.coupon_value,
                    commission=offer_info.commission,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(offer)

            # 创建 CouponHistory 记录 (如果提供了相关信息)
            # 使用第一个offer的优惠券信息以及ProductInfo中的过期时间和条款
            if offer_info := next((o for o in product_info.offers if o.coupon_type and o.coupon_value), None):
                 if product_info.coupon_expiration_date or product_info.coupon_terms or offer_info:
                    coupon_history = CouponHistory(
                        product_id=db_product.asin,
                        coupon_type=offer_info.coupon_type,
                        coupon_value=offer_info.coupon_value,
                        expiration_date=product_info.coupon_expiration_date,
                        terms=product_info.coupon_terms,
                        created_at=current_time,
                        updated_at=current_time
                    )
                    db.add(coupon_history)
            elif product_info.coupon_expiration_date or product_info.coupon_terms:
                 # 即使offer没有优惠券，但productInfo有日期或条款，也记录
                 coupon_history = CouponHistory(
                     product_id=db_product.asin,
                     coupon_type=None, # 未知类型
                     coupon_value=None, # 未知值
                     expiration_date=product_info.coupon_expiration_date,
                     terms=product_info.coupon_terms,
                     created_at=current_time,
                     updated_at=current_time
                 )
                 db.add(coupon_history)

            db.commit()
            db.refresh(db_product)
            
            # 从数据库重新加载并返回完整的ProductInfo
            # 使用现有的get_product_details_by_asin获取完整信息
            created_product_info = ProductService.get_product_details_by_asin(db, product_info.asin)
            if not created_product_info:
                 # 如果查询失败，构造一个基本的 ProductInfo 返回
                 # 这不应该发生，但作为后备
                 logger.warning(f"手动创建商品 {product_info.asin} 后未能从数据库重新检索，返回原始输入。")
                 return product_info
                 
            return created_product_info

        except ValueError as ve:
            db.rollback()
            logger.error(f"手动创建商品 {product_info.asin} 失败 (验证错误): {str(ve)}")
            raise ve
        except Exception as e:
            db.rollback()
            logger.error(f"手动创建商品 {product_info.asin} 数据库操作失败: {str(e)}")
            raise Exception(f"数据库操作失败: {str(e)}")
    
    @staticmethod
    def manual_update_product(db: Session, product_info: ProductInfo) -> ProductInfo:
        """
        手动更新商品记录
        
        Args:
            db: 数据库会话
            product_info: 用户提供的完整商品信息
            
        Returns:
            ProductInfo: 更新成功的商品信息
            
        Raises:
            ValueError: 如果商品不存在或数据验证失败
            Exception: 如果数据库操作失败
        """
        # 检查商品是否存在
        existing_product = db.query(Product).filter(Product.asin == product_info.asin).first()
        if not existing_product:
            raise ValueError(f"ASIN {product_info.asin} 不存在，无法更新。")
            
        # 检查是否有offers信息
        if not product_info.offers:
            raise ValueError("必须至少提供一个商品优惠信息 (offer)。")
            
        try:
            current_time = datetime.now(timezone.utc)
            best_offer = product_info.offers[0]  # 取第一个offer作为主要信息来源
            
            # 更新商品基本信息
            existing_product.title = product_info.title
            existing_product.url = product_info.url
            existing_product.brand = product_info.brand
            existing_product.main_image = product_info.main_image
            existing_product.cj_url = product_info.cj_url
            
            # 更新价格信息（使用第一个offer的信息）
            existing_product.current_price = best_offer.price
            existing_product.original_price = best_offer.original_price
            existing_product.currency = best_offer.currency
            existing_product.savings_amount = best_offer.savings
            existing_product.savings_percentage = best_offer.savings_percentage
            
            # 更新Prime信息
            existing_product.is_prime = best_offer.is_prime
            
            # 更新商品状态
            existing_product.condition = best_offer.condition
            existing_product.availability = best_offer.availability
            existing_product.merchant_name = best_offer.merchant_name
            existing_product.is_buybox_winner = best_offer.is_buybox_winner
            existing_product.deal_type = best_offer.deal_type
            
            # 更新分类信息
            existing_product.binding = product_info.binding
            existing_product.product_group = product_info.product_group
            existing_product.categories = json.dumps(product_info.categories or [])
            existing_product.browse_nodes = json.dumps(product_info.browse_nodes or [])
            existing_product.features = json.dumps(product_info.features or [])
            
            # 更新时间戳和元数据
            existing_product.updated_at = current_time
            existing_product.discount_updated_at = current_time
            # 如果用户提供了timestamp，使用用户的；否则使用当前时间
            existing_product.timestamp = product_info.timestamp or current_time
            
            # 更新API提供者和来源（如果提供）
            if product_info.api_provider:
                existing_product.api_provider = product_info.api_provider
            if product_info.source:
                existing_product.source = product_info.source
                
            # 更新原始数据
            existing_product.raw_data = json.dumps(product_info.dict(exclude={'raw_data'}) if not product_info.raw_data else product_info.raw_data)
            
            # 删除现有的offer记录
            db.query(Offer).filter(Offer.product_id == existing_product.asin).delete()
            
            # 创建新的Offer记录
            for offer_info in product_info.offers:
                offer = Offer(
                    product_id=existing_product.asin,
                    condition=offer_info.condition,
                    price=offer_info.price,
                    currency=offer_info.currency,
                    savings=offer_info.savings,
                    savings_percentage=offer_info.savings_percentage,
                    is_prime=offer_info.is_prime,
                    is_amazon_fulfilled=offer_info.is_amazon_fulfilled,
                    is_free_shipping_eligible=offer_info.is_free_shipping_eligible,
                    availability=offer_info.availability,
                    merchant_name=offer_info.merchant_name,
                    is_buybox_winner=offer_info.is_buybox_winner,
                    deal_type=offer_info.deal_type,
                    coupon_type=offer_info.coupon_type,
                    coupon_value=offer_info.coupon_value,
                    commission=offer_info.commission,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(offer)
            
            # 更新优惠券历史记录（如果提供了相关信息）
            if offer_info := next((o for o in product_info.offers if o.coupon_type and o.coupon_value), None):
                if product_info.coupon_expiration_date or product_info.coupon_terms or offer_info:
                    # 查找是否已有优惠券历史记录
                    existing_coupon = db.query(CouponHistory).filter(
                        CouponHistory.product_id == existing_product.asin
                    ).order_by(CouponHistory.updated_at.desc()).first()
                    
                    # 判断优惠券信息是否有变化
                    coupon_changed = True
                    if existing_coupon:
                        coupon_changed = (
                            existing_coupon.coupon_type != offer_info.coupon_type or
                            existing_coupon.coupon_value != offer_info.coupon_value or
                            existing_coupon.expiration_date != product_info.coupon_expiration_date or
                            existing_coupon.terms != product_info.coupon_terms
                        )
                    
                    # 如果有变化或是新的优惠券，创建新记录
                    if coupon_changed:
                        coupon_history = CouponHistory(
                            product_id=existing_product.asin,
                            coupon_type=offer_info.coupon_type,
                            coupon_value=offer_info.coupon_value,
                            expiration_date=product_info.coupon_expiration_date,
                            terms=product_info.coupon_terms,
                            created_at=current_time,
                            updated_at=current_time
                        )
                        db.add(coupon_history)
            
            db.commit()
            db.refresh(existing_product)
            
            # 从数据库重新加载并返回完整的ProductInfo
            updated_product_info = ProductService.get_product_details_by_asin(db, product_info.asin)
            if not updated_product_info:
                # 如果查询失败，构造一个基本的 ProductInfo 返回
                logger.warning(f"更新商品 {product_info.asin} 后未能从数据库重新检索，返回原始输入。")
                return product_info
                
            return updated_product_info
            
        except ValueError as ve:
            db.rollback()
            logger.error(f"更新商品 {product_info.asin} 失败 (验证错误): {str(ve)}")
            raise ve
        except Exception as e:
            db.rollback()
            logger.error(f"更新商品 {product_info.asin} 数据库操作失败: {str(e)}")
            raise Exception(f"数据库操作失败: {str(e)}")
    
    @staticmethod
    def update_product(db: Session, product_info: ProductInfo, source: str = "update") -> Optional[Product]:
        """
        更新商品信息
        
        Args:
            db: 数据库会话
            product_info: 商品信息对象
            source: 数据来源（已弃用，保留参数是为了兼容性）
            
        Returns:
            Optional[Product]: 更新后的商品对象，如果失败则返回None
        """
        try:
            # 查找现有商品
            product = db.query(Product).filter(Product.asin == product_info.asin).first()
            if not product:
                return None
                
            # 更新商品基本信息
            product.title = product_info.title
            product.url = product_info.url
            product.brand = product_info.brand
            product.main_image = product_info.main_image
            
            # 更新CJ相关信息
            if hasattr(product_info, 'cj_url') and product_info.cj_url is not None:
                product.cj_url = product_info.cj_url
                # 添加日志，跟踪cj_url的更新
                logging.getLogger("ProductService").info(f"更新商品 {product.asin} 的推广链接: {product_info.cj_url[:30] if product_info.cj_url else 'None'}...")
            
            # 更新价格信息
            if product_info.offers:
                main_offer = product_info.offers[0]
                product.current_price = main_offer.price
                product.original_price = main_offer.price + (main_offer.savings or 0)
                product.currency = main_offer.currency
                
                # 更新Prime信息
                product.is_prime = main_offer.is_prime
                
                # 更新商品状态
                product.condition = main_offer.condition
                product.availability = main_offer.availability
                product.merchant_name = main_offer.merchant_name
                product.is_buybox_winner = main_offer.is_buybox_winner
                
                # 更新优惠类型
                product.deal_type = main_offer.deal_type
            
            # 更新分类信息
            if product_info.categories:
                product.categories = json.dumps(product_info.categories)
            if product_info.browse_nodes:
                product.browse_nodes = json.dumps(product_info.browse_nodes)
            if product_info.features:
                product.features = json.dumps(product_info.features)
            
            # 更新API提供者和原始数据
            product.api_provider = product_info.api_provider
            product.raw_data = json.dumps(product_info.dict())
            
            # 只更新时间戳，不更新source
            product.updated_at = datetime.now()
            
            # 提交更改
            db.commit()
            db.refresh(product)
            
            return product
            
        except Exception as e:
            db.rollback()
            raise Exception(f"更新商品失败: {str(e)}")
    
    @staticmethod
    def get_product_by_asin(db: Session, asin: str) -> Optional[ProductInfo]:
        """根据ASIN获取商品信息"""
        try:
            product = db.query(Product).filter(Product.asin == asin).first()
            
            if not product:
                return None
            
            # 解析JSON字符串
            categories = json.loads(product.categories) if product.categories else []
            browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
            features = json.loads(product.features) if product.features else []
            
            # 确保解析后的数据是列表类型
            if not isinstance(categories, list):
                categories = []
            if not isinstance(browse_nodes, list):
                browse_nodes = []
            if not isinstance(features, list):
                features = []
            
            # 获取商品的所有优惠信息
            offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
            
            # 获取最新的优惠券历史记录，改用updated_at排序
            latest_coupon = db.query(CouponHistory).filter(
                CouponHistory.product_id == product.asin
            ).order_by(CouponHistory.updated_at.desc()).first()
            
            # 转换优惠券对象为字典
            coupon_history = None
            if latest_coupon:
                coupon_history = {
                    "id": latest_coupon.id,
                    "product_id": latest_coupon.product_id,
                    "coupon_type": latest_coupon.coupon_type,
                    "coupon_value": latest_coupon.coupon_value,
                    "expiration_date": latest_coupon.expiration_date.isoformat() if latest_coupon.expiration_date else None,
                    "terms": latest_coupon.terms,
                    "updated_at": latest_coupon.updated_at.isoformat() if latest_coupon.updated_at else None
                }
                
            return ProductInfo(
                asin=product.asin,
                title=product.title,
                url=product.url,
                brand=product.brand,
                main_image=product.main_image,
                timestamp=product.timestamp or datetime.utcnow(),
                binding=product.binding,
                product_group=product.product_group,
                categories=categories,
                browse_nodes=browse_nodes,
                features=features,
                cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                api_provider=product.api_provider,
                source=product.source,  # 添加数据来源字段
                offers=[
                    ProductOffer(
                        condition=o.condition or "New",  # 提供默认值
                        price=o.price or 0.0,  # 提供默认值
                        original_price=product.original_price,  # 添加原始价格
                        currency=o.currency or "USD",  # 提供默认值
                        savings=o.savings,
                        savings_percentage=o.savings_percentage,
                        is_prime=o.is_prime or False,
                        availability=o.availability or "Available",  # 提供默认值
                        merchant_name=o.merchant_name or "Amazon",  # 提供默认值
                        is_buybox_winner=o.is_buybox_winner or False,
                        deal_type=o.deal_type,
                        coupon_type=getattr(o, 'coupon_type', None),
                        coupon_value=getattr(o, 'coupon_value', None),
                        commission=o.commission if product.api_provider == "cj-api" else None
                    ) for o in offers
                ],
                # 添加优惠券过期日期和条款
                coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                coupon_terms=latest_coupon.terms if latest_coupon else None,
                # 添加完整的优惠券历史信息
                coupon_history=coupon_history
            )
        except Exception as e:
            logger.error(f"获取商品 {asin} 详情时出错: {str(e)}")
            raise e
    
    @staticmethod
    def get_product_details_by_asin(
        db: Session, 
        asins: Union[str, List[str]], 
        include_metadata: bool = False,
        include_browse_nodes: Optional[List[str]] = None
    ) -> Union[Optional[ProductInfo], List[Optional[ProductInfo]]]:
        """根据ASIN获取商品详细信息，支持单个或批量查询
        
        Args:
            db: 数据库会话
            asins: 单个ASIN字符串或ASIN列表
            include_metadata: 是否包含元数据
            include_browse_nodes: 要包含的浏览节点ID列表
            
        Returns:
            单个ASIN时返回单个ProductInfo对象或None
            ASIN列表时返回ProductInfo对象列表，未找到的项为None
        """
        try:
            # 处理单个ASIN的情况
            if isinstance(asins, str):
                return ProductService._get_single_product_details(
                    db, asins, include_metadata, include_browse_nodes
                )
            
            # 处理ASIN列表的情况
            products = db.query(Product).filter(Product.asin.in_(asins)).all()
            product_dict = {p.asin: p for p in products}
            
            # 获取所有相关的优惠信息
            offers = db.query(Offer).filter(Offer.product_id.in_(asins)).all()
            offers_dict = {}
            for offer in offers:
                if offer.product_id not in offers_dict:
                    offers_dict[offer.product_id] = []
                offers_dict[offer.product_id].append(offer)
            
            # 获取所有相关的优惠券历史记录
            # 使用子查询获取每个商品的最新优惠券历史记录
            latest_coupon_subquery = db.query(
                CouponHistory.product_id,
                func.max(CouponHistory.updated_at).label('max_updated_at')
            ).filter(
                CouponHistory.product_id.in_(asins)
            ).group_by(CouponHistory.product_id).subquery()
            
            latest_coupons = db.query(CouponHistory).join(
                latest_coupon_subquery,
                and_(
                    CouponHistory.product_id == latest_coupon_subquery.c.product_id,
                    CouponHistory.updated_at == latest_coupon_subquery.c.max_updated_at
                )
            ).all()
            
            coupon_dict = {}
            for coupon in latest_coupons:
                coupon_dict[coupon.product_id] = {
                    "id": coupon.id,
                    "product_id": coupon.product_id,
                    "coupon_type": coupon.coupon_type,
                    "coupon_value": coupon.coupon_value,
                    "expiration_date": coupon.expiration_date.isoformat() if coupon.expiration_date else None,
                    "terms": coupon.terms,
                    "updated_at": coupon.updated_at.isoformat() if coupon.updated_at else None
                }
            
            # 构建结果列表
            results = []
            for asin in asins:
                product = product_dict.get(asin)
                if not product:
                    results.append(None)
                    continue
                
                try:
                    # 解析JSON字符串
                    categories = json.loads(product.categories) if product.categories else []
                    browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                    features = json.loads(product.features) if product.features else []
                    
                    # 确保解析后的数据是列表类型
                    if not isinstance(categories, list):
                        categories = []
                    if not isinstance(browse_nodes, list):
                        browse_nodes = []
                    if not isinstance(features, list):
                        features = []
                    
                    # 如果提供了include_browse_nodes参数，进行筛选
                    if include_browse_nodes and include_browse_nodes != ["string"]:  # 忽略默认的无效值
                        filtered_nodes = [
                            node for node in browse_nodes 
                            if node.get('id') in include_browse_nodes
                        ]
                        # 只有在找到匹配项时才使用筛选结果
                        if filtered_nodes:
                            browse_nodes = filtered_nodes
                    
                    # 获取商品的优惠信息
                    product_offers = offers_dict.get(asin, [])
                    
                    # 获取优惠券历史记录
                    coupon_history = coupon_dict.get(asin)
                    
                    # 构建商品信息对象
                    product_info = ProductInfo(
                        asin=product.asin,
                        title=product.title,
                        url=product.url,
                        brand=product.brand,
                        main_image=product.main_image,
                        timestamp=product.timestamp or datetime.utcnow(),
                        binding=product.binding,
                        product_group=product.product_group,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        features=features,
                        cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                        api_provider=product.api_provider,
                        source=product.source,  # 添加数据来源字段
                        offers=[
                            ProductOffer(
                                condition=o.condition or "New",
                                price=o.price or 0.0,
                                original_price=product.original_price,
                                currency=o.currency or "USD",
                                savings=o.savings,
                                savings_percentage=o.savings_percentage,
                                is_prime=o.is_prime or False,
                                availability=o.availability or "Available",
                                merchant_name=o.merchant_name or "Amazon",
                                is_buybox_winner=o.is_buybox_winner or False,
                                deal_type=o.deal_type,
                                coupon_type=getattr(o, 'coupon_type', None),
                                coupon_value=getattr(o, 'coupon_value', None),
                                commission=o.commission if product.api_provider == "cj-api" else None
                            ) for o in product_offers
                        ],
                        # 添加优惠券过期日期、条款和历史记录
                        coupon_expiration_date=coupon_history["expiration_date"] if coupon_history else None,
                        coupon_terms=coupon_history["terms"] if coupon_history else None,
                        coupon_history=coupon_history
                    )
                    
                    # 添加元数据（如果需要）
                    if include_metadata and product.raw_data:
                        try:
                            raw_data = json.loads(product.raw_data)
                            product_info.raw_data = raw_data
                        except:
                            pass
                        
                    results.append(product_info)
                    
                except Exception as e:
                    logger.error(f"处理商品 {asin} 时出错: {str(e)}")
                    results.append(None)
                    continue
                
            return results
            
        except Exception as e:
            logger.error(f"获取商品详情时出错: {str(e)}")
            raise e

    @staticmethod
    def _get_single_product_details(
        db: Session, 
        asin: str,
        include_metadata: bool = False,
        include_browse_nodes: Optional[List[str]] = None
    ) -> Optional[ProductInfo]:
        """获取单个商品的详细信息(内部方法)"""
        try:
            product = db.query(Product).filter(Product.asin == asin).first()
            if not product:
                return None
            
            # 解析JSON字符串
            categories = json.loads(product.categories) if product.categories else []
            browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
            features = json.loads(product.features) if product.features else []
            
            # 确保解析后的数据是列表类型
            if not isinstance(categories, list):
                categories = []
            if not isinstance(browse_nodes, list):
                browse_nodes = []
            if not isinstance(features, list):
                features = []
            
            # 如果提供了include_browse_nodes参数，进行筛选
            if include_browse_nodes and include_browse_nodes != ["string"]:  # 忽略默认的无效值
                filtered_nodes = [
                    node for node in browse_nodes 
                    if node.get('id') in include_browse_nodes
                ]
                # 只有在找到匹配项时才使用筛选结果
                if filtered_nodes:
                    browse_nodes = filtered_nodes
            
            # 获取商品的优惠信息
            offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
            
            # 获取最新的优惠券历史记录，改用updated_at排序
            latest_coupon = db.query(CouponHistory).filter(
                CouponHistory.product_id == product.asin
            ).order_by(CouponHistory.updated_at.desc()).first()
            
            # 转换优惠券对象为字典
            coupon_history = None
            if latest_coupon:
                coupon_history = {
                    "id": latest_coupon.id,
                    "product_id": latest_coupon.product_id,
                    "coupon_type": latest_coupon.coupon_type,
                    "coupon_value": latest_coupon.coupon_value,
                    "expiration_date": latest_coupon.expiration_date.isoformat() if latest_coupon.expiration_date else None,
                    "terms": latest_coupon.terms,
                    "updated_at": latest_coupon.updated_at.isoformat() if latest_coupon.updated_at else None
                }
            
            # 构建商品信息对象
            product_info = ProductInfo(
                asin=product.asin,
                title=product.title,
                url=product.url,
                brand=product.brand,
                main_image=product.main_image,
                timestamp=product.timestamp or datetime.utcnow(),
                binding=product.binding,
                product_group=product.product_group,
                categories=categories,
                browse_nodes=browse_nodes,
                features=features,
                cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                api_provider=product.api_provider,
                source=product.source,  # 添加数据来源字段
                offers=[
                    ProductOffer(
                        condition=o.condition or "New",
                        price=o.price or 0.0,
                        original_price=product.original_price,
                        currency=o.currency or "USD",
                        savings=o.savings,
                        savings_percentage=o.savings_percentage,
                        is_prime=o.is_prime or False,
                        availability=o.availability or "Available",
                        merchant_name=o.merchant_name or "Amazon",
                        is_buybox_winner=o.is_buybox_winner or False,
                        deal_type=o.deal_type,
                        coupon_type=getattr(o, 'coupon_type', None),
                        coupon_value=getattr(o, 'coupon_value', None),
                        commission=o.commission if product.api_provider == "cj-api" else None
                    ) for o in offers
                ],
                # 添加优惠券过期日期和条款
                coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                coupon_terms=latest_coupon.terms if latest_coupon else None,
                # 添加完整的优惠券历史信息
                coupon_history=coupon_history
            )
            
            # 添加元数据（如果需要）
            if include_metadata and product.raw_data:
                try:
                    raw_data = json.loads(product.raw_data)
                    product_info.raw_data = raw_data
                except:
                    pass
            
            return product_info
            
        except Exception as e:
            logger.error(f"获取商品 {asin} 详情时出错: {str(e)}")
            raise e
    
    @staticmethod
    def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[Product]:
        """获取商品列表"""
        return db.query(Product).offset(skip).limit(limit).all()
    
    @staticmethod
    def create_or_update_product(db: Session, product_info: ProductInfo, source: str = "pa-api") -> Product:
        """创建或更新商品信息"""
        existing_product = ProductService.get_product_by_asin(db, product_info.asin)
        if existing_product:
            return ProductService.update_product(db, product_info, source)
        return ProductService.create_product(db, product_info, source)
    
    @staticmethod
    def bulk_create_or_update_products(
        db: Session, 
        products: List[ProductInfo], 
        include_coupon: bool = False,
        source: Optional[str] = None,
        include_metadata: bool = False
    ) -> List[ProductInfo]:
        """批量创建或更新商品信息"""
        saved_products = []
        current_time = datetime.now(timezone.utc) # 使用 timezone.utc
        
        for product_info in products:
            try:
                # 获取第一个优惠（通常是最佳优惠）
                best_offer = product_info.offers[0] if product_info.offers else None
                
                # 查找现有产品
                product = db.query(Product).filter(Product.asin == product_info.asin).first()
                
                # 序列化列表类型的字段
                features = json.dumps(product_info.features) if product_info.features else json.dumps([])
                categories = json.dumps(product_info.categories) if product_info.categories else json.dumps([])
                browse_nodes = json.dumps(product_info.browse_nodes) if product_info.browse_nodes else json.dumps([])
                raw_data = json.dumps(product_info.dict())
                
                if not product:
                    # 创建新产品
                    product = Product(
                        asin=product_info.asin,
                        title=product_info.title,
                        url=product_info.url,
                        brand=product_info.brand,
                        main_image=product_info.main_image,
                        
                        # 价格信息
                        current_price=best_offer.price if best_offer else None,
                        original_price=best_offer.price + best_offer.savings if best_offer and best_offer.savings else None,
                        currency=best_offer.currency if best_offer else None,
                        savings_amount=best_offer.savings if best_offer else None,
                        savings_percentage=best_offer.savings_percentage if best_offer else None,
                        
                        # Prime信息
                        is_prime=best_offer.is_prime if best_offer else None,
                        is_prime_exclusive=False,
                        
                        # 商品状态
                        condition=best_offer.condition if best_offer else None,
                        availability=best_offer.availability if best_offer else None,
                        merchant_name=best_offer.merchant_name if best_offer else None,
                        is_buybox_winner=best_offer.is_buybox_winner if best_offer else None,
                        
                        # 其他信息
                        deal_type=best_offer.deal_type if best_offer else None,
                        features=features,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        
                        # 时间信息
                        created_at=current_time,
                        updated_at=current_time,
                        timestamp=current_time,
                        
                        # 元数据
                        source=source,
                        api_provider=product_info.api_provider,
                        raw_data=raw_data,
                        
                        # CJ特有信息
                        cj_url=product_info.cj_url if hasattr(product_info, 'cj_url') else None
                    )
                    
                    # 添加分类相关信息
                    if include_metadata:
                        product.binding = product_info.binding
                        product.product_group = product_info.product_group
                        
                    db.add(product)
                else:
                    # 更新现有产品
                    product.title = product_info.title
                    product.url = product_info.url
                    product.brand = product_info.brand
                    product.main_image = product_info.main_image
                    product.features = features
                    product.categories = categories
                    product.browse_nodes = browse_nodes
                    
                    # 更新价格信息
                    if best_offer:
                        product.current_price = best_offer.price
                        product.original_price = best_offer.price + best_offer.savings if best_offer.savings else None
                        product.currency = best_offer.currency
                        product.savings_amount = best_offer.savings
                        product.savings_percentage = best_offer.savings_percentage
                        
                        # 更新Prime信息
                        product.is_prime = best_offer.is_prime
                        
                        # 更新商品状态
                        product.condition = best_offer.condition
                        product.availability = best_offer.availability
                        product.merchant_name = best_offer.merchant_name
                        product.is_buybox_winner = best_offer.is_buybox_winner
                        product.deal_type = best_offer.deal_type
                    
                    # 更新分类相关信息
                    if include_metadata:
                        product.binding = product_info.binding
                        product.product_group = product_info.product_group
                    
                    # 更新CJ URL
                    if hasattr(product_info, 'cj_url'):
                        product.cj_url = product_info.cj_url
                    
                    # 更新时间和元数据
                    product.updated_at = current_time
                    product.timestamp = current_time
                    if source:  # 只在明确指定source时更新
                        product.source = source
                    product.api_provider = product_info.api_provider
                    product.raw_data = raw_data
                
                # 删除旧的优惠信息
                db.query(Offer).filter(Offer.product_id == product.asin).delete()
                
                # 添加新的优惠信息
                for offer_info in product_info.offers:
                    offer = Offer(
                        product_id=product.asin,
                        condition=offer_info.condition,
                        price=offer_info.price,
                        currency=offer_info.currency,
                        savings=offer_info.savings,
                        savings_percentage=offer_info.savings_percentage,
                        is_prime=offer_info.is_prime,
                        is_amazon_fulfilled=offer_info.is_amazon_fulfilled,
                        is_free_shipping_eligible=offer_info.is_free_shipping_eligible,
                        availability=offer_info.availability,
                        merchant_name=offer_info.merchant_name,
                        is_buybox_winner=offer_info.is_buybox_winner,
                        deal_type=offer_info.deal_type,
                        created_at=current_time,
                        updated_at=current_time,
                        commission=offer_info.commission if hasattr(offer_info, 'commission') else None
                    )
                    
                    # 如果包含优惠券信息，添加优惠券相关字段
                    if include_coupon and hasattr(offer_info, 'coupon_type') and hasattr(offer_info, 'coupon_value'):
                        offer.coupon_type = offer_info.coupon_type
                        offer.coupon_value = offer_info.coupon_value
                        
                        # 添加优惠券历史记录
                        coupon_history = CouponHistory(
                            product_id=product.asin,
                            coupon_type=offer_info.coupon_type,
                            coupon_value=offer_info.coupon_value,
                            created_at=current_time,
                            updated_at=current_time
                        )
                        db.add(coupon_history)
                    
                    db.add(offer)
                
                saved_products.append(product_info)
                
            except Exception as e:
                raise Exception(f"处理商品时出错 {product_info.asin}: {str(e)}")
        
        try:
            # 提交事务
            db.commit()
            return saved_products
        except Exception as e:
            db.rollback()
            raise Exception(f"提交事务时出错: {str(e)}")

    @staticmethod
    @lru_cache(maxsize=128)  # 设置缓存大小为128
    def get_category_stats(db: Session, product_type: Optional[str] = None, 
                          page: int = 1, page_size: int = 50, 
                          sort_by: str = 'count', sort_order: str = 'desc') -> Dict[str, Any]:
        """获取类别统计信息，仅处理product_groups数据
        
        Args:
            db: 数据库会话
            product_type: 商品类型 ('discount'/'coupon'/None)
            page: 页码，默认为1
            page_size: 每页数量，默认为50
            sort_by: 排序字段，可选 'group'(商品组名称) 或 'count'(数量)
            sort_order: 排序顺序，可选 'asc'(升序) 或 'desc'(降序)
            
        Returns:
            Dict[str, Any]: 类别统计信息，同时包含分页信息
        """
        try:
            # 构建基础查询 - 直接使用SQL聚合
            query = db.query(Product.product_group, func.count(Product.id).label('count')).group_by(Product.product_group)
            
            # 根据商品类型筛选
            if product_type:
                query = query.filter(Product.source == product_type)
            
            # 获取总数，用于分页信息
            total_query = db.query(func.count(func.distinct(Product.product_group)))
            if product_type:
                total_query = total_query.filter(Product.source == product_type)
            total_count = total_query.scalar() or 0
            
            # 应用排序
            if sort_by == 'group':
                order_column = Product.product_group
            else:  # 默认按count排序
                order_column = func.count(Product.id)
                
            if sort_order == 'asc':
                query = query.order_by(asc(order_column))
            else:  # 默认降序
                query = query.order_by(desc(order_column))
            
            # 应用分页
            query = query.offset((page - 1) * page_size).limit(page_size)
            
            # 执行查询
            results = query.all()
            
            # 为保持API兼容性，保留原有的返回结构
            stats = {
                "browse_nodes": {},     # 空字典，不再处理
                "browse_tree": {},      # 空字典，不再处理
                "bindings": {},         # 空字典，不再处理
                "product_groups": {},   # 商品组统计
            }
            
            # 填充product_groups数据
            for group, count in results:
                if group:  # 过滤掉None值
                    stats["product_groups"][group] = count
            
            # 添加分页信息
            stats["pagination"] = {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取类别统计信息失败: {str(e)}")
            return {
                "browse_nodes": {},
                "browse_tree": {},
                "bindings": {},
                "product_groups": {},
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": 0,
                    "total_pages": 0
                }
            }

    @staticmethod
    def clear_category_stats_cache():
        """清除get_category_stats函数的缓存"""
        if hasattr(ProductService.get_category_stats, 'cache_clear'):
            ProductService.get_category_stats.cache_clear()
            return True
        return False

    @staticmethod
    def _apply_sorting(query, sort_by: Optional[str], sort_order: str = "desc"):
        """
        应用排序逻辑的通用方法
        
        Args:
            query: SQLAlchemy查询对象
            sort_by: 排序字段
            sort_order: 排序方向 ('asc' 或 'desc')
            
        Returns:
            SQLAlchemy查询对象
        """
        if not sort_by:
            # 默认按更新时间倒序排序
            return query.order_by(desc(Product.timestamp))
            
        # 定义排序字段映射
        sort_field_mapping = {
            "price": Product.current_price,
            "discount": Product.savings_percentage,
            "timestamp": Product.timestamp,
            "commission": Offer.commission
        }
        
        # 获取排序字段
        sort_field = sort_field_mapping.get(sort_by)
        if not sort_field:
            # 如果没有找到对应的排序字段，使用默认排序
            return query.order_by(desc(Product.timestamp))
            
        # 如果是按佣金排序，需要确保已经连接了Offer表
        if sort_by == "commission":
            if "offer" not in str(query):
                query = query.outerjoin(Offer)
            
        # 应用排序
        if sort_order == "desc":
            query = query.order_by(desc(sort_field))
        else:
            query = query.order_by(asc(sort_field))
            
        # 添加第二排序字段（按时间戳倒序）
        if sort_by != "timestamp":
            query = query.order_by(desc(Product.timestamp))
            
        return query

    @staticmethod
    def list_products(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        is_prime_only: bool = False,
        product_type: str = "all",
        browse_node_ids: Optional[List[str]] = None,  # 使用browse_node_ids替代main_categories和sub_categories
        bindings: Optional[List[str]] = None,
        product_groups: Optional[List[str]] = None,
        api_provider: Optional[str] = None,  # 将source改为api_provider
        min_commission: Optional[int] = None,
        brands: Optional[List[str]] = None  # 新增brands参数
    ) -> Dict[str, Any]:
        """获取商品列表，支持分页、筛选和排序"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 根据product_type筛选
            if product_type != "all":
                query = query.filter(Product.source == product_type)
                
            # 根据数据来源筛选 - 直接使用api_provider值
            if api_provider:
                query = query.filter(Product.api_provider == api_provider)
                
            # 应用佣金筛选
            if min_commission is not None:
                query = query.join(Offer).filter(
                    cast(Offer.commission, Float) >= min_commission
                )
                
            # 应用价格筛选
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
                
            # 应用折扣率筛选
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
                
            # 应用Prime筛选
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
                
            # 应用browse nodes筛选
            if browse_node_ids:
                browse_node_conditions = []
                for node_id in browse_node_ids:
                    # 使用JSON字符串匹配，查找browse_nodes中包含指定id的商品
                    browse_node_conditions.append(
                        Product.browse_nodes.like(f'%"id": "{node_id}"%')
                    )
                if browse_node_conditions:
                    query = query.filter(or_(*browse_node_conditions))
                    
            # 应用binding筛选
            if bindings:
                query = query.filter(Product.binding.in_(bindings))
                
            # 应用product_group筛选
            if product_groups:
                query = query.filter(Product.product_group.in_(product_groups))
                
            # 应用品牌筛选
            if brands:
                query = query.filter(Product.brand.in_(brands))
                
            # 应用排序
            query = ProductService._apply_sorting(query, sort_by, sort_order)
            
            # 应用分页
            total = query.count()
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 执行查询
            products = query.all()
            
            # 转换为ProductInfo对象
            result = []
            for product in products:
                try:
                    # 解析JSON字符串
                    categories = json.loads(product.categories) if product.categories else []
                    browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                    features = json.loads(product.features) if product.features else []
                    
                    # 确保解析后的数据是列表类型
                    if not isinstance(categories, list):
                        categories = []
                    if not isinstance(browse_nodes, list):
                        browse_nodes = []
                    if not isinstance(features, list):
                        features = []
                    
                    offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                    
                    # 获取最新的优惠券历史记录
                    latest_coupon = db.query(CouponHistory).filter(
                        CouponHistory.product_id == product.asin
                    ).order_by(CouponHistory.created_at.desc()).first()
                    
                    product_info = ProductInfo(
                        asin=product.asin,
                        title=product.title,
                        url=product.url,
                        brand=product.brand,
                        main_image=product.main_image,
                        timestamp=product.timestamp or datetime.utcnow(),
                        binding=product.binding,
                        product_group=product.product_group,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        features=features,
                        cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                        api_provider=product.api_provider,
                        source=product.source,  # 添加数据来源字段
                        offers=[
                            ProductOffer(
                                condition=offer.condition or "New",
                                price=offer.price or 0.0,
                                original_price=product.original_price,
                                currency=offer.currency or "USD",
                                savings=offer.savings,
                                savings_percentage=offer.savings_percentage,
                                is_prime=offer.is_prime or False,
                                availability=offer.availability or "Available",
                                merchant_name=offer.merchant_name or "Amazon",
                                is_buybox_winner=offer.is_buybox_winner or False,
                                deal_type=offer.deal_type,
                                coupon_type=getattr(offer, 'coupon_type', None),
                                coupon_value=getattr(offer, 'coupon_value', None),
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ],
                        # 添加优惠券过期日期和条款
                        coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                        coupon_terms=latest_coupon.terms if latest_coupon else None
                    )
                    result.append(product_info)
                except json.JSONDecodeError as e:
                    logger.error(f"解析商品 {product.asin} 的JSON数据时出错: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理商品 {product.asin} 时出错: {str(e)}")
                    continue
                
            return {
                "items": result,
                "total": total,
                "page": page,
                "page_size": page_size
            }
            
        except Exception as e:
            logger.error(f"获取商品列表失败: {str(e)}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size
            }

    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        """获取商品统计信息"""
        # 基本统计
        total_products = db.query(func.count(Product.asin)).scalar()
        
        # 价格统计
        price_stats = db.query(
            func.min(Offer.price),
            func.max(Offer.price),
            func.avg(Offer.price)
        ).first()
        
        # 折扣统计
        discount_stats = db.query(
            func.min(Offer.savings_percentage),
            func.max(Offer.savings_percentage),
            func.avg(Offer.savings_percentage)
        ).first()
        
        # Prime商品数量
        prime_products = db.query(func.count(Offer.id))\
            .filter(Offer.is_prime == True)\
            .scalar()
            
        # 最后更新时间
        last_update = db.query(func.max(Product.timestamp)).scalar()
        
        return {
            "total_products": total_products,
            "min_price": float(price_stats[0]) if price_stats[0] else 0,
            "max_price": float(price_stats[1]) if price_stats[1] else 0,
            "avg_price": float(price_stats[2]) if price_stats[2] else 0,
            "min_discount": int(discount_stats[0]) if discount_stats[0] else 0,
            "max_discount": int(discount_stats[1]) if discount_stats[1] else 0,
            "avg_discount": float(discount_stats[2]) if discount_stats[2] else 0,
            "prime_products": prime_products,
            "last_update": last_update
        }

    @staticmethod
    def batch_delete_products(db: Session, asins: List[str]) -> Dict[str, int]:
        """批量删除商品"""
        success_count = 0
        fail_count = 0
        
        try:
            # 开始事务
            for asin in asins:
                try:
                    # 删除关联的优惠信息
                    db.query(Offer).filter(Offer.product_id == asin).delete()
                    
                    # 删除商品记录
                    result = db.query(Product).filter(Product.asin == asin).delete()
                    
                    if result > 0:
                        success_count += 1
                    else:
                        fail_count += 1
                        
                except Exception:
                    fail_count += 1
                    continue
            
            # 提交事务
            db.commit()
            
        except Exception as e:
            # 如果发生错误，回滚事务
            db.rollback()
            raise e
            
        return {
            "success_count": success_count,
            "fail_count": fail_count
        }

    @staticmethod
    def remove_products_without_discount(
        db: Session, 
        dry_run: bool = True,
        min_days_old: int = 0,
        max_days_old: Optional[int] = None,
        api_provider: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        删除没有任何优惠的商品（既没有折扣也没有优惠券）
        
        Args:
            db: 数据库会话
            dry_run: 是否仅模拟执行而不实际删除，默认为True
            min_days_old: 商品创建时间至少几天前，默认为0（不限制）
            max_days_old: 商品创建时间最多几天前，默认为None（不限制）
            api_provider: 筛选特定API提供商的商品，如"pa-api"或"cj-api"
            min_price: 最低价格筛选
            max_price: 最高价格筛选
            limit: 最大处理数量，默认为None（不限制）
        
        Returns:
            Dict[str, Any]: 删除操作的结果统计
        """
        try:
            logger.info(f"开始{'模拟' if dry_run else ''}删除没有优惠的商品")
            
            # 构建时间条件
            time_conditions = []
            if min_days_old > 0:
                min_date = datetime.now(timezone.utc) - timedelta(days=min_days_old)
                time_conditions.append(Product.created_at <= min_date)
            if max_days_old is not None and max_days_old > 0:
                max_date = datetime.now(timezone.utc) - timedelta(days=max_days_old)
                time_conditions.append(Product.created_at >= max_date)
            
            # 构建价格条件
            price_conditions = []
            if min_price is not None:
                price_conditions.append(Product.current_price >= min_price)
            if max_price is not None:
                price_conditions.append(Product.current_price <= max_price)
            
            # 构建API提供商条件
            api_provider_condition = []
            if api_provider:
                api_provider_condition.append(Product.api_provider == api_provider)
            
            # 先找出有优惠券历史的商品ASIN
            products_with_coupons = db.query(CouponHistory.product_id).distinct().all()
            products_with_coupons_asins = [p[0] for p in products_with_coupons]
            
            # 查找没有任何优惠的商品：
            # 1. 没有优惠券历史记录
            # 2. 没有折扣（savings_percentage为0或null）
            # 3. 在Offer表中没有coupon_type和coupon_value
            query = db.query(Product).filter(
                # 没有优惠券历史
                ~Product.asin.in_(products_with_coupons_asins),
                # 没有折扣或折扣为0
                or_(
                    Product.savings_percentage.is_(None),
                    Product.savings_percentage == 0
                )
            )
            
            # 应用时间条件
            if time_conditions:
                query = query.filter(and_(*time_conditions))
                
            # 应用价格条件
            if price_conditions:
                query = query.filter(and_(*price_conditions))
                
            # 应用API提供商条件
            if api_provider_condition:
                query = query.filter(and_(*api_provider_condition))
            
            # 查找在Offer表中没有优惠券的商品
            # 获取所有候选商品的ASIN
            candidate_products = query.all()
            products_to_delete = []
            
            for product in candidate_products:
                # 检查该商品的所有offer是否都没有优惠券
                offers = db.query(Offer).filter(
                    Offer.product_id == product.asin,
                    or_(
                        Offer.coupon_type.isnot(None),
                        Offer.coupon_value.isnot(None)
                    )
                ).all()
                
                # 如果没有带优惠券的offer，则添加到删除列表
                if not offers:
                    products_to_delete.append(product)
                    
                # 如果设置了限制，并且已达到限制，则停止处理
                if limit is not None and len(products_to_delete) >= limit:
                    break
            
            # 获取详细信息以便记录
            products_info = [{
                "asin": p.asin,
                "title": p.title,
                "price": p.current_price,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "api_provider": p.api_provider
            } for p in products_to_delete]
            
            total_found = len(products_to_delete)
            logger.info(f"找到 {total_found} 个没有优惠的商品")
            
            # 如果是dry_run模式，不执行删除操作
            if dry_run:
                logger.info("模拟模式，不执行实际删除")
                
                return {
                    "dry_run": True,
                    "total_found": total_found,
                    "products": products_info
                }
            
            # 实际执行删除操作
            asins_to_delete = [p.asin for p in products_to_delete]
            
            # 记录将要删除的商品ASIN
            logger.info(f"准备删除以下商品: {asins_to_delete}")
            
            # 使用批量删除方法执行删除
            delete_result = ProductService.batch_delete_products(db, asins_to_delete)
            
            # 返回删除结果
            return {
                "dry_run": False,
                "total_found": total_found,
                "deleted": delete_result["success_count"],
                "failed": delete_result["fail_count"],
                "products": products_info
            }
            
        except Exception as e:
            logger.error(f"删除没有优惠的商品时出错: {str(e)}")
            # 如果不是dry_run模式，尝试回滚事务
            if not dry_run:
                try:
                    db.rollback()
                except:
                    pass
            
            # 返回错误信息
            return {
                "error": str(e),
                "total_found": 0,
                "deleted": 0,
                "failed": 0
            }

    @staticmethod
    def list_coupon_products(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        is_prime_only: bool = False,
        coupon_type: Optional[str] = None,
        api_provider: Optional[str] = None,
        min_commission: Optional[int] = None,
        browse_node_ids: Optional[List[str]] = None,
        bindings: Optional[List[str]] = None,
        product_groups: Optional[List[str]] = None,
        brands: Optional[List[str]] = None  # 新增brands参数
    ) -> Dict[str, Any]:
        """获取优惠券商品列表"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 确保是优惠券商品
            query = query.filter(Product.source == "coupon")
            
            # 根据api_provider参数筛选数据来源
            if api_provider:
                query = query.filter(Product.api_provider == api_provider)
            
            # 连接优惠券历史表
            query = query.join(
                CouponHistory,
                Product.asin == CouponHistory.product_id
            )
            
            # 应用佣金筛选
            if min_commission is not None:
                query = query.join(Offer).filter(
                    cast(Offer.commission, Float) >= min_commission
                )
            
            # 应用过滤条件
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
            if coupon_type:
                query = query.filter(CouponHistory.coupon_type == coupon_type)
                
            # 应用browse nodes筛选
            if browse_node_ids:
                browse_node_conditions = []
                for node_id in browse_node_ids:
                    browse_node_conditions.append(
                        Product.browse_nodes.like(f'%"id": "{node_id}"%')
                    )
                if browse_node_conditions:
                    query = query.filter(or_(*browse_node_conditions))
                    
            # 应用binding筛选
            if bindings:
                query = query.filter(Product.binding.in_(bindings))
                
            # 应用product_group筛选
            if product_groups:
                query = query.filter(Product.product_group.in_(product_groups))
                
            # 应用品牌筛选
            if brands:
                query = query.filter(Product.brand.in_(brands))
                
            # 应用排序
            query = ProductService._apply_sorting(query, sort_by, sort_order)
            
            # 应用分页
            total = query.count()
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 执行查询
            products = query.all()
            
            # 转换为ProductInfo对象
            result = []
            for product in products:
                try:
                    # 解析JSON字符串
                    categories = json.loads(product.categories) if product.categories else []
                    browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                    features = json.loads(product.features) if product.features else []
                    
                    # 确保解析后的数据是列表类型
                    if not isinstance(categories, list):
                        categories = []
                    if not isinstance(browse_nodes, list):
                        browse_nodes = []
                    if not isinstance(features, list):
                        features = []
                    
                    offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                    
                    # 获取最新的优惠券历史记录，包含过期日期和条款
                    latest_coupon = db.query(CouponHistory).filter(
                        CouponHistory.product_id == product.asin
                    ).order_by(CouponHistory.updated_at.desc()).first()
                    
                    # 转换优惠券对象为字典
                    coupon_history = None
                    if latest_coupon:
                        coupon_history = {
                            "id": latest_coupon.id,
                            "product_id": latest_coupon.product_id,
                            "coupon_type": latest_coupon.coupon_type,
                            "coupon_value": latest_coupon.coupon_value,
                            "expiration_date": latest_coupon.expiration_date.isoformat() if latest_coupon.expiration_date else None,
                            "terms": latest_coupon.terms,
                            "updated_at": latest_coupon.updated_at.isoformat() if latest_coupon.updated_at else None
                        }
                    
                    product_info = ProductInfo(
                        asin=product.asin,
                        title=product.title,
                        url=product.url,
                        brand=product.brand,
                        main_image=product.main_image,
                        timestamp=product.timestamp or datetime.utcnow(),
                        binding=product.binding,
                        product_group=product.product_group,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        features=features,
                        cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                        api_provider=product.api_provider,
                        source=product.source,  # 添加数据来源字段
                        offers=[
                            ProductOffer(
                                condition=offer.condition or "New",
                                price=offer.price or 0.0,
                                original_price=product.original_price,
                                currency=offer.currency or "USD",
                                savings=offer.savings,
                                savings_percentage=offer.savings_percentage,
                                is_prime=offer.is_prime or False,
                                availability=offer.availability or "Available",
                                merchant_name=offer.merchant_name or "Amazon",
                                is_buybox_winner=offer.is_buybox_winner or False,
                                deal_type=offer.deal_type,
                                coupon_type=getattr(offer, 'coupon_type', None),
                                coupon_value=getattr(offer, 'coupon_value', None),
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ],
                        # 添加优惠券过期日期和条款
                        coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                        coupon_terms=latest_coupon.terms if latest_coupon else None,
                        # 添加完整的优惠券历史信息
                        coupon_history=coupon_history
                    )
                    result.append(product_info)
                except json.JSONDecodeError as e:
                    logger.error(f"解析商品 {product.asin} 的JSON数据时出错: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理商品 {product.asin} 时出错: {str(e)}")
                    continue
                
            return {
                "items": result,
                "total": total,
                "page": page,
                "page_size": page_size
            }
            
        except Exception as e:
            logger.error(f"获取优惠券商品列表失败: {str(e)}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size
            }

    @staticmethod
    def list_discount_products(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        is_prime_only: bool = False,
        api_provider: Optional[str] = None,  # 使用api_provider参数来筛选API来源
        min_commission: Optional[int] = None,
        browse_node_ids: Optional[List[str]] = None,  # 添加browse_node_ids参数
        bindings: Optional[List[str]] = None,         # 添加bindings参数
        product_groups: Optional[List[str]] = None,    # 添加product_groups参数
        brands: Optional[List[str]] = None  # 新增brands参数
    ) -> Dict[str, Any]:
        """获取折扣商品列表"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 确保是折扣商品
            query = query.filter(Product.source == "discount")
            
            # 根据api_provider参数筛选数据来源
            if api_provider:
                query = query.filter(Product.api_provider == api_provider)
            
            # 应用佣金筛选
            if min_commission is not None:
                query = query.join(Offer).filter(
                    cast(Offer.commission, Float) >= min_commission
                )

            # 应用其他筛选条件
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
                
            # 应用browse nodes筛选
            if browse_node_ids:
                browse_node_conditions = []
                for node_id in browse_node_ids:
                    browse_node_conditions.append(
                        Product.browse_nodes.like(f'%"id": "{node_id}"%')
                    )
                if browse_node_conditions:
                    query = query.filter(or_(*browse_node_conditions))
                    
            # 应用binding筛选
            if bindings:
                query = query.filter(Product.binding.in_(bindings))
                
            # 应用product_group筛选
            if product_groups:
                query = query.filter(Product.product_group.in_(product_groups))
                
            # 应用品牌筛选
            if brands:
                query = query.filter(Product.brand.in_(brands))
                
            # 应用排序
            query = ProductService._apply_sorting(query, sort_by, sort_order)
                
            # 应用分页
            total = query.count()
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 执行查询
            products = query.all()
            
            # 转换为ProductInfo对象
            result = []
            for product in products:
                try:
                    # 解析JSON字符串
                    categories = json.loads(product.categories) if product.categories else []
                    browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                    features = json.loads(product.features) if product.features else []
                    
                    # 确保解析后的数据是列表类型
                    if not isinstance(categories, list):
                        categories = []
                    if not isinstance(browse_nodes, list):
                        browse_nodes = []
                    if not isinstance(features, list):
                        features = []
                    
                    offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                    
                    # 获取最新的优惠券历史记录，使用updated_at排序
                    latest_coupon = db.query(CouponHistory).filter(
                        CouponHistory.product_id == product.asin
                    ).order_by(CouponHistory.updated_at.desc()).first()
                    
                    # 转换优惠券对象为字典
                    coupon_history = None
                    if latest_coupon:
                        coupon_history = {
                            "id": latest_coupon.id,
                            "product_id": latest_coupon.product_id,
                            "coupon_type": latest_coupon.coupon_type,
                            "coupon_value": latest_coupon.coupon_value,
                            "expiration_date": latest_coupon.expiration_date.isoformat() if latest_coupon.expiration_date else None,
                            "terms": latest_coupon.terms,
                            "updated_at": latest_coupon.updated_at.isoformat() if latest_coupon.updated_at else None
                        }
                    
                    product_info = ProductInfo(
                        asin=product.asin,
                        title=product.title,
                        url=product.url,
                        brand=product.brand,
                        main_image=product.main_image,
                        timestamp=product.timestamp or datetime.utcnow(),
                        binding=product.binding,
                        product_group=product.product_group,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        features=features,
                        cj_url=product.cj_url if product.api_provider == "cj-api" else None,
                        api_provider=product.api_provider,
                        source=product.source,  # 添加数据来源字段
                        offers=[
                            ProductOffer(
                                condition=offer.condition or "New",
                                price=offer.price or 0.0,
                                original_price=product.original_price,
                                currency=offer.currency or "USD",
                                savings=offer.savings,
                                savings_percentage=offer.savings_percentage,
                                is_prime=offer.is_prime or False,
                                availability=offer.availability or "Available",
                                merchant_name=offer.merchant_name or "Amazon",
                                is_buybox_winner=offer.is_buybox_winner or False,
                                deal_type=offer.deal_type,
                                coupon_type=getattr(offer, 'coupon_type', None),
                                coupon_value=getattr(offer, 'coupon_value', None),
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ],
                        # 添加优惠券过期日期和条款
                        coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                        coupon_terms=latest_coupon.terms if latest_coupon else None,
                        # 添加完整的优惠券历史信息
                        coupon_history=coupon_history
                    )
                    result.append(product_info)
                except json.JSONDecodeError as e:
                    logger.error(f"解析商品 {product.asin} 的JSON数据时出错: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理商品 {product.asin} 时出错: {str(e)}")
                    continue
                
            return {
                "items": result,
                "total": total,
                "page": page,
                "page_size": page_size
            }
            
        except Exception as e:
            logger.error(f"获取折扣商品列表失败: {str(e)}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size
            }

    @staticmethod
    def get_products_stats(db: Session, product_type: Optional[str] = None) -> dict:
        """获取商品统计信息
        
        Args:
            db: 数据库会话
            product_type: 商品类型筛选
            
        Returns:
            dict: 统计信息
        """
        try:
            # 基础查询
            query = db.query(Product)
            
            # 根据商品类型筛选
            if product_type:
                if product_type == "discount":
                    query = query.join(Offer).filter(Offer.savings_percentage.isnot(None))
                elif product_type == "coupon":
                    query = query.join(Offer).filter(Offer.coupon_type.isnot(None))
            
            # 获取基本统计信息
            total_products = query.count()
            
            # 获取折扣商品数量
            discount_products = db.query(Product).join(Offer).filter(
                Offer.savings_percentage.isnot(None)
            ).count()
            
            # 获取优惠券商品数量
            coupon_products = db.query(Product).join(Offer).filter(
                Offer.coupon_type.isnot(None)
            ).count()
            
            # 获取Prime商品数量
            prime_products = db.query(Product).join(Offer).filter(
                Offer.is_prime.is_(True)
            ).count()
            
            # 获取价格和折扣统计
            price_stats = db.query(
                func.avg(Offer.price).label('avg_price'),
                func.min(Offer.price).label('min_price'),
                func.max(Offer.price).label('max_price'),
                func.avg(Offer.savings_percentage).label('avg_discount'),
                func.min(Offer.savings_percentage).label('min_discount'),
                func.max(Offer.savings_percentage).label('max_discount'),
                func.avg(Offer.savings).label('avg_savings'),
                func.min(Offer.savings).label('min_savings'),
                func.max(Offer.savings).label('max_savings')
            ).select_from(Product).join(Offer).first()
            
            # 获取优惠券统计
            coupon_stats = db.query(
                func.count(Offer.coupon_type).label('total_coupons'),
                func.avg(Offer.coupon_value).label('avg_coupon_value'),
                func.min(Offer.coupon_value).label('min_coupon_value'),
                func.max(Offer.coupon_value).label('max_coupon_value')
            ).select_from(Product).join(Offer).filter(
                Offer.coupon_type.isnot(None)
            ).first()
            
            # 获取商品分类统计
            category_stats = db.query(
                Product.binding,
                func.count(Product.id).label('count')
            ).group_by(Product.binding).all()
            
            # 获取商品组统计
            group_stats = db.query(
                Product.product_group,
                func.count(Product.id).label('count')
            ).group_by(Product.product_group).all()
            
            # 获取商品品牌统计
            brand_stats = db.query(
                Product.brand,
                func.count(Product.id).label('count')
            ).group_by(Product.brand).all()
            
            return {
                # 基本统计
                "total_products": total_products,
                "discount_products": discount_products,
                "coupon_products": coupon_products,
                "prime_products": prime_products,
                
                # 价格统计
                "avg_price": float(price_stats.avg_price or 0),
                "min_price": float(price_stats.min_price or 0),
                "max_price": float(price_stats.max_price or 0),
                
                # 折扣统计
                "avg_discount": float(price_stats.avg_discount or 0),
                "min_discount": float(price_stats.min_discount or 0),
                "max_discount": float(price_stats.max_discount or 0),
                
                # 节省金额统计
                "avg_savings": float(price_stats.avg_savings or 0),
                "min_savings": float(price_stats.min_savings or 0),
                "max_savings": float(price_stats.max_savings or 0),
                
                # 优惠券统计
                "total_coupons": int(coupon_stats.total_coupons or 0),
                "avg_coupon_value": float(coupon_stats.avg_coupon_value or 0),
                "min_coupon_value": float(coupon_stats.min_coupon_value or 0),
                "max_coupon_value": float(coupon_stats.max_coupon_value or 0),
                
                # 分类统计
                "categories": {
                    "bindings": {
                        cat.binding: cat.count for cat in category_stats if cat.binding
                    },
                    "groups": {
                        group.product_group: group.count for group in group_stats if group.product_group
                    },
                    "brands": {
                        brand.brand: brand.count for brand in brand_stats if brand.brand
                    }
                },
                
                # 时间统计
                "last_update": db.query(func.max(Product.updated_at)).scalar()
            }
            
        except Exception as e:
            logger.error(f"获取商品统计信息失败: {str(e)}")
            raise 

    @staticmethod
    @lru_cache(maxsize=128)  # 设置缓存大小为128
    def get_brand_stats(db: Session, product_type: Optional[str] = None, 
                         page: int = 1, page_size: int = 50, 
                         sort_by: str = 'count', sort_order: str = 'desc') -> Dict[str, Any]:
        """获取品牌统计信息
        
        Args:
            db: 数据库会话
            product_type: 商品类型 ('discount'/'coupon'/None)
            page: 页码，默认为1
            page_size: 每页数量，默认为50
            sort_by: 排序字段，可选 'brand'(品牌名称) 或 'count'(数量)
            sort_order: 排序顺序，可选 'asc'(升序) 或 'desc'(降序)
            
        Returns:
            Dict[str, Any]: 品牌统计信息，包含分页信息
        """
        try:
            # 构建基础查询 - 直接使用SQL聚合
            query = db.query(Product.brand, func.count(Product.id).label('count')).group_by(Product.brand)
            
            # 根据商品类型筛选
            if product_type:
                query = query.filter(Product.source == product_type)
            
            # 获取总数，用于分页信息
            total_query = db.query(func.count(func.distinct(Product.brand)))
            if product_type:
                total_query = total_query.filter(Product.source == product_type)
            total_count = total_query.scalar() or 0
            
            # 应用排序
            if sort_by == 'brand':
                order_column = Product.brand
            else:  # 默认按count排序
                order_column = func.count(Product.id)
                
            if sort_order == 'asc':
                query = query.order_by(asc(order_column))
            else:  # 默认降序
                query = query.order_by(desc(order_column))
            
            # 应用分页
            query = query.offset((page - 1) * page_size).limit(page_size)
            
            # 执行查询
            results = query.all()
            
            # 构建返回结构
            stats = {
                "brands": {},        # 品牌统计
                "total_brands": total_count  # 品牌总数
            }
            
            # 填充品牌数据
            for brand, count in results:
                if brand:  # 过滤掉None值
                    stats["brands"][brand] = count
            
            # 添加分页信息
            stats["pagination"] = {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取品牌统计信息失败: {str(e)}")
            return {
                "brands": {},
                "total_brands": 0,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": 0,
                    "total_pages": 0
                }
            }

    @staticmethod
    def clear_brand_stats_cache():
        """清空品牌统计信息缓存"""
        ProductService.get_brand_stats.cache_clear()
        return {"cleared": True, "message": "品牌统计缓存已清空"}
        
    @staticmethod
    def is_valid_asin(string: str) -> bool:
        """
        检查字符串是否符合亚马逊ASIN格式
        
        根据亚马逊ASIN的常见格式，有两种主要模式：
        1. 10位纯数字ISBN (9位数字 + 最后一位可能是X或数字)
        2. 以B开头的10位字符串，通常是B + 2位数字 + 7位字母数字混合字符
           但也可能是B + 9位字母数字混合字符
        
        Args:
            string: 要检查的字符串
            
        Returns:
            bool: 如果符合ASIN格式返回True，否则返回False
        """
        if not string or not isinstance(string, str) or len(string) != 10:
            return False
            
        # 纯数字ISBN格式 (9位数字 + 最后一位可能是X或数字)
        if string.isdigit() or (string[:9].isdigit() and string[9] in "0123456789X"):
            return True
            
        # B开头的非ISBN格式
        # 最新的格式是B + 9位字母数字混合
        if string[0] == "B" and all(c.isalnum() for c in string[1:]) and any(c.isdigit() for c in string[1:]):
            return True
            
        # 严格的传统格式：B + 2位数字 + 7位字母数字混合
        # 如果需要更严格的验证，可以使用下面的代码
        # if string[0] == "B" and string[1:3].isdigit() and all(c.isalnum() for c in string[3:]):
        #     return True
            
        return False
        
    @staticmethod
    def search_products(
        db: Session,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        sort_by: Optional[str] = "relevance",
        sort_order: str = "desc",
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,
        is_prime_only: bool = False,
        product_groups: Optional[Union[List[str], str]] = None,
        brands: Optional[Union[List[str], str]] = None,
        api_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据关键词搜索产品
        
        Args:
            db: 数据库会话
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量
            sort_by: 排序字段 ('relevance'/'price'/'discount'/'created')
            sort_order: 排序方向 ('asc'/'desc')
            min_price: 最低价格
            max_price: 最高价格
            min_discount: 最低折扣率
            is_prime_only: 是否只显示Prime商品
            product_groups: 商品分类
            brands: 品牌
            api_provider: API提供商
            
        Returns:
            Dict: 包含商品列表和分页信息的字典
        """
        try:
            # 检查关键词是否是ASIN格式
            if ProductService.is_valid_asin(keyword):
                logger.info(f"检测到ASIN格式关键词: {keyword}，尝试直接查询产品")
                
                # 直接按ASIN查询产品
                product = db.query(Product).filter(Product.asin == keyword).first()
                
                if product:
                    # 产品存在，直接返回结果
                    try:
                        # 解析JSON字符串
                        categories = json.loads(product.categories) if product.categories else []
                        browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                        features = json.loads(product.features) if product.features else []
                        
                        # 确保解析后的数据是列表类型
                        if not isinstance(categories, list):
                            categories = []
                        if not isinstance(browse_nodes, list):
                            browse_nodes = []
                        if not isinstance(features, list):
                            features = []
                        
                        # 获取商品的优惠信息
                        offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                        
                        # 如果是优惠券商品，获取优惠券历史记录
                        latest_coupon = None
                        if product.source == "coupon":
                            latest_coupon = db.query(CouponHistory).filter(
                                CouponHistory.product_id == product.asin
                            ).order_by(CouponHistory.updated_at.desc()).first()
                        
                        # 转换为ProductOffer对象
                        product_offers = []
                        for offer in offers:
                            product_offers.append(
                                ProductOffer(
                                    condition=offer.condition,
                                    price=offer.price,
                                    original_price=product.original_price,
                                    currency=offer.currency,
                                    savings=offer.savings,
                                    savings_percentage=offer.savings_percentage,
                                    is_prime=offer.is_prime,
                                    is_amazon_fulfilled=offer.is_amazon_fulfilled,
                                    is_free_shipping_eligible=offer.is_free_shipping_eligible,
                                    availability=offer.availability,
                                    merchant_name=offer.merchant_name,
                                    is_buybox_winner=offer.is_buybox_winner,
                                    deal_type=offer.deal_type,
                                    coupon_type=offer.coupon_type,
                                    coupon_value=offer.coupon_value,
                                    commission=offer.commission
                                )
                            )
                        
                        # 创建ProductInfo对象
                        product_info = ProductInfo(
                            asin=product.asin,
                            title=product.title,
                            url=product.url,
                            brand=product.brand,
                            main_image=product.main_image,
                            timestamp=product.timestamp or datetime.utcnow(),
                            binding=product.binding,
                            product_group=product.product_group,
                            categories=categories,
                            browse_nodes=browse_nodes,
                            features=features,
                            cj_url=product.cj_url,
                            api_provider=product.api_provider,
                            source=product.source,  # 添加数据来源字段
                            offers=product_offers,
                            # 只有优惠券商品才添加优惠券过期日期和条款
                            coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                            coupon_terms=latest_coupon.terms if latest_coupon else None
                        )
                        
                        return {
                            "success": True,
                            "data": {
                                "items": [product_info],
                                "total": 1,
                                "page": 1,
                                "page_size": 1,
                                "is_asin_search": True  # 标识这是ASIN搜索结果
                            }
                        }
                    except Exception as e:
                        logger.error(f"处理ASIN产品时出错: {str(e)}")
                        # 如果处理ASIN产品出错，回退到关键词搜索
                
                # 如果找不到产品或处理出错，记录信息并继续执行关键词搜索
                logger.info(f"未找到ASIN为{keyword}的产品，继续执行关键词搜索")
            
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 添加关键词搜索条件
            # 将关键词分割为多个单词，实现更灵活的搜索
            keywords = keyword.split()
            search_conditions = []
            
            for kw in keywords:
                # 在title、brand和features字段中搜索
                search_conditions.append(Product.title.ilike(f'%{kw}%'))
                search_conditions.append(Product.brand.ilike(f'%{kw}%'))
                # features是JSON字符串，需要进行文本匹配
                search_conditions.append(Product.features.ilike(f'%{kw}%'))
                
            # 将所有条件用OR连接
            query = query.filter(or_(*search_conditions))
            
            # 应用其他筛选条件
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
                
            # 处理product_groups参数
            if product_groups:
                group_list = product_groups
                if isinstance(product_groups, str):
                    group_list = [g.strip() for g in product_groups.split(",") if g.strip()]
                query = query.filter(Product.product_group.in_(group_list))
                
            # 处理brands参数
            if brands:
                brand_list = brands
                if isinstance(brands, str):
                    brand_list = [b.strip() for b in brands.split(",") if b.strip()]
                query = query.filter(Product.brand.in_(brand_list))
                
            # 应用API提供商筛选
            if api_provider:
                query = query.filter(Product.api_provider == api_provider)
                
            # 应用排序
            if sort_by == "relevance":
                # 基于关键词在标题中出现的次数的相关性排序
                # 为每个关键词创建一个相关性评分表达式
                relevance_expressions = []
                for kw in keywords:
                    # 标题中关键词出现的次数权重最高
                    title_relevance = func.length(Product.title) - func.length(
                        func.replace(func.lower(Product.title), kw.lower(), '')
                    )
                    relevance_expressions.append(title_relevance)
                    
                    # 品牌名称匹配权重次之
                    brand_relevance = func.length(func.coalesce(Product.brand, '')) - func.length(
                        func.replace(func.lower(func.coalesce(Product.brand, '')), kw.lower(), '')
                    )
                    relevance_expressions.append(brand_relevance * 0.5)
                
                # 组合所有相关性表达式
                if relevance_expressions:
                    combined_relevance = sum(relevance_expressions)
                    if sort_order == "desc":
                        query = query.order_by(desc(combined_relevance), desc(Product.timestamp))
                    else:
                        query = query.order_by(asc(combined_relevance), desc(Product.timestamp))
                else:
                    # 如果没有关键词，则按时间戳排序
                    query = query.order_by(desc(Product.timestamp))
            elif sort_by == "created":
                # 按创建时间排序
                if sort_order == "desc":
                    query = query.order_by(desc(Product.created_at))
                else:
                    query = query.order_by(asc(Product.created_at))
            else:
                # 使用通用排序方法
                query = ProductService._apply_sorting(query, sort_by, sort_order)
                
            # 应用分页
            total = query.count()
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 执行查询
            products = query.all()
            
            # 转换为ProductInfo对象
            result = []
            for product in products:
                try:
                    # 解析JSON字符串
                    categories = json.loads(product.categories) if product.categories else []
                    browse_nodes = json.loads(product.browse_nodes) if product.browse_nodes else []
                    features = json.loads(product.features) if product.features else []
                    
                    # 确保解析后的数据是列表类型
                    if not isinstance(categories, list):
                        categories = []
                    if not isinstance(browse_nodes, list):
                        browse_nodes = []
                    if not isinstance(features, list):
                        features = []
                    
                    # 获取商品的优惠信息
                    offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                    
                    # 如果是优惠券商品，获取优惠券历史记录
                    latest_coupon = None
                    if product.source == "coupon":
                        latest_coupon = db.query(CouponHistory).filter(
                            CouponHistory.product_id == product.asin
                        ).order_by(CouponHistory.updated_at.desc()).first()
                    
                    # 转换优惠券对象为字典
                    coupon_history = None
                    if latest_coupon:
                        coupon_history = {
                            "id": latest_coupon.id,
                            "product_id": latest_coupon.product_id,
                            "coupon_type": latest_coupon.coupon_type,
                            "coupon_value": latest_coupon.coupon_value,
                            "expiration_date": latest_coupon.expiration_date.isoformat() if latest_coupon.expiration_date else None,
                            "terms": latest_coupon.terms,
                            "updated_at": latest_coupon.updated_at.isoformat() if latest_coupon.updated_at else None
                        }
                    
                    product_info = ProductInfo(
                        asin=product.asin,
                        title=product.title,
                        url=product.url,
                        brand=product.brand,
                        main_image=product.main_image,
                        timestamp=product.timestamp or datetime.utcnow(),
                        binding=product.binding,
                        product_group=product.product_group,
                        categories=categories,
                        browse_nodes=browse_nodes,
                        features=features,
                        cj_url=product.cj_url,
                        api_provider=product.api_provider,
                        source=product.source,  # 添加数据来源字段
                        offers=[
                            ProductOffer(
                                condition=offer.condition or "New",
                                price=offer.price or 0.0,
                                original_price=product.original_price,
                                currency=offer.currency or "USD",
                                savings=offer.savings,
                                savings_percentage=offer.savings_percentage,
                                is_prime=offer.is_prime or False,
                                availability=offer.availability or "Available",
                                merchant_name=offer.merchant_name or "Amazon",
                                is_buybox_winner=offer.is_buybox_winner or False,
                                deal_type=offer.deal_type,
                                coupon_type=offer.coupon_type,
                                coupon_value=offer.coupon_value,
                                commission=offer.commission
                            ) for offer in offers
                        ],
                        # 添加优惠券过期日期和条款
                        coupon_expiration_date=latest_coupon.expiration_date if latest_coupon else None,
                        coupon_terms=latest_coupon.terms if latest_coupon else None,
                        # 添加完整的优惠券历史信息
                        coupon_history=coupon_history
                    )
                    
                    result.append(product_info)
                except Exception as e:
                    logger.error(f"处理商品 {product.asin} 时出错: {str(e)}")
                    continue
                
            # 返回结果
            return {
                "success": True,
                "data": {
                    "items": result,
                    "total": total,
                    "page": page,
                    "page_size": page_size
                }
            }
            
        except Exception as e:
            logger.error(f"搜索产品失败: {str(e)}")
            return {
                "success": False,
                "data": {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size
                },
                "error": str(e)
            } 