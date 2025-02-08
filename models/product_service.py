from typing import List, Optional, Dict, Any
import logging
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey, or_, cast, and_

# 配置logger
logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from datetime import datetime, timedelta
from .database import Product, Offer, CouponHistory
from .product import ProductInfo, ProductOffer

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
            features=[],  # 需要从API响应中提取
            
            # 元数据
            source=source,
            raw_data=product_info.dict()
        )
        
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def update_product(db: Session, product_info: ProductInfo, source: str = "pa-api") -> Optional[Product]:
        """更新商品信息"""
        db_product = db.query(Product).filter(Product.asin == product_info.asin).first()
        if not db_product:
            return None
            
        best_offer = product_info.offers[0] if product_info.offers else None
        
        # 更新产品信息
        db_product.title = product_info.title
        db_product.url = product_info.url
        db_product.brand = product_info.brand
        db_product.main_image = product_info.main_image
        
        # 更新价格信息
        if best_offer:
            db_product.current_price = best_offer.price
            db_product.original_price = best_offer.price + best_offer.savings if best_offer.savings else None
            db_product.currency = best_offer.currency
            db_product.savings_amount = best_offer.savings
            db_product.savings_percentage = best_offer.savings_percentage
            
            # 更新Prime信息
            db_product.is_prime = best_offer.is_prime
            
            # 更新商品状态
            db_product.condition = best_offer.condition
            db_product.availability = best_offer.availability
            db_product.merchant_name = best_offer.merchant_name
            db_product.is_buybox_winner = best_offer.is_buybox_winner
            db_product.deal_type = best_offer.deal_type
        
        # 更新元数据
        db_product.updated_at = datetime.utcnow()
        db_product.source = source
        db_product.raw_data = product_info.dict()
        
        db.commit()
        db.refresh(db_product)
        return db_product
    
    @staticmethod
    def get_product_by_asin(db: Session, asin: str) -> Optional[ProductInfo]:
        """根据ASIN获取商品信息"""
        try:
            product = db.query(Product).filter(Product.asin == asin).first()
            
            if not product:
                return None
            
            # 获取商品的所有优惠信息
            offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
            print(f"Debug - 商品 {product.asin} 有 {len(offers)} 个优惠")
                
            return ProductInfo(
                asin=product.asin,
                title=product.title,
                url=product.url,
                brand=product.brand,
                main_image=product.main_image,
                timestamp=product.timestamp or datetime.utcnow(),
                offers=[
                    ProductOffer(
                        condition=o.condition or "New",  # 提供默认值
                        price=o.price or 0.0,  # 提供默认值
                        currency=o.currency or "USD",  # 提供默认值
                        savings=o.savings,
                        savings_percentage=o.savings_percentage,
                        is_prime=o.is_prime or False,
                        availability=o.availability or "Available",  # 提供默认值
                        merchant_name=o.merchant_name or "Amazon",  # 提供默认值
                        is_buybox_winner=o.is_buybox_winner or False,
                        deal_type=o.deal_type,
                        coupon_type=o.coupon_type if hasattr(o, 'coupon_type') else None,
                        coupon_value=o.coupon_value if hasattr(o, 'coupon_value') else None
                    ) for o in offers
                ]
            )
        except Exception as e:
            print(f"Debug - 获取商品 {asin} 详情时出错: {str(e)}")
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
        include_cj_data: bool = False,  # 新增参数：是否包含CJ数据
        source: Optional[str] = None,  # 数据来源渠道：bestseller/coupon/cj
        api_provider: str = "pa-api",  # API提供者：pa-api/cj-api
        include_metadata: bool = False  # 是否包含元数据（分类信息等）
    ) -> List[ProductInfo]:
        """批量创建或更新商品信息"""
        saved_products = []
        current_time = datetime.utcnow()
        
        for product_info in products:
            # 获取第一个优惠（通常是最佳优惠）
            best_offer = product_info.offers[0] if product_info.offers else None
            
            # 查找现有产品
            product = db.query(Product).filter(Product.asin == product_info.asin).first()
            
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
                    features=[],
                    
                    # 时间信息
                    created_at=current_time,
                    updated_at=current_time,
                    timestamp=current_time,
                    
                    # 元数据
                    source=source,
                    api_provider=api_provider,
                    raw_data=product_info.dict()
                )
                
                # 添加分类相关信息
                if include_metadata:
                    product.binding = product_info.binding
                    product.product_group = product_info.product_group
                    product.categories = product_info.categories
                    product.browse_nodes = product_info.browse_nodes
                    
                # 添加CJ相关信息
                if include_cj_data and hasattr(product_info, 'cj_url'):
                    product.cj_url = product_info.cj_url
                    
                db.add(product)
            else:
                # 更新现有产品
                product.title = product_info.title
                product.url = product_info.url
                product.brand = product_info.brand
                product.main_image = product_info.main_image
                
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
                    product.categories = product_info.categories
                    product.browse_nodes = product_info.browse_nodes
                
                # 更新CJ相关信息
                if include_cj_data and hasattr(product_info, 'cj_url'):
                    product.cj_url = product_info.cj_url
                
                # 更新时间和元数据
                product.updated_at = current_time
                product.timestamp = current_time
                if source:  # 只在明确指定source时更新
                    product.source = source
                product.api_provider = api_provider  # 始终更新API提供者
                product.raw_data = product_info.dict()
            
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
                    updated_at=current_time
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
                
                # 添加CJ特有信息
                if include_cj_data and hasattr(offer_info, 'commission'):
                    offer.commission = offer_info.commission
                
                db.add(offer)
            
            saved_products.append(product_info)
        
        # 提交事务
        db.commit()
        
        return saved_products

    @staticmethod
    def get_category_stats(db: Session) -> Dict[str, Any]:
        """获取类别统计信息"""
        try:
            # 获取所有商品的类别信息
            products = db.query(Product).all()
            
            # 初始化统计字典
            stats = {
                "main_categories": {},  # 主要类别统计
                "sub_categories": {},   # 子类别统计
                "bindings": {},         # 商品绑定类型统计
                "product_groups": {},   # 商品组统计
            }
            
            for product in products:
                # 处理categories (商品分类路径)
                if product.categories:
                    for category_path in product.categories:
                        if isinstance(category_path, list) and len(category_path) > 0:
                            # 主要类别统计
                            main_category = category_path[0]
                            stats["main_categories"][main_category] = stats["main_categories"].get(main_category, 0) + 1
                            
                            # 子类别统计
                            if len(category_path) > 1:
                                sub_category = category_path[1]
                                parent_key = f"{main_category}:{sub_category}"
                                stats["sub_categories"][parent_key] = stats["sub_categories"].get(parent_key, 0) + 1
                
                # 处理binding (商品绑定类型)
                if product.binding:
                    stats["bindings"][product.binding] = stats["bindings"].get(product.binding, 0) + 1
                
                # 处理product_group (商品组)
                if product.product_group:
                    stats["product_groups"][product.product_group] = stats["product_groups"].get(product.product_group, 0) + 1
            
            # 对每个统计结果按数量降序排序
            for key in stats:
                stats[key] = dict(sorted(stats[key].items(), key=lambda x: x[1], reverse=True))
            
            return stats
            
        except Exception as e:
            logger.error(f"获取类别统计信息失败: {str(e)}")
            return {
                "main_categories": {},
                "sub_categories": {},
                "bindings": {},
                "product_groups": {}
            }

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
        main_categories: Optional[List[str]] = None,
        sub_categories: Optional[List[str]] = None,
        bindings: Optional[List[str]] = None,
        product_groups: Optional[List[str]] = None,
        source: Optional[str] = None,
        min_commission: Optional[int] = None
    ) -> List[ProductInfo]:
        """获取商品列表"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 应用过滤条件
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
                
            # 根据product_type筛选
            if product_type == "cj":
                query = query.filter(Product.source == "cj")
                
            # 应用数据来源筛选
            if source:
                if source == "cj":
                    query = query.filter(Product.source == "cj")
                elif source == "pa-api":
                    query = query.filter(or_(
                        Product.source == "bestseller",
                        Product.source == "coupon",
                        Product.source == "pa-api",
                        Product.source.is_(None)
                    ))
                    
            # 应用佣金筛选
            if min_commission is not None:
                if source == "cj":
                    query = query.join(Offer).filter(
                        cast(Offer.commission, Float) >= min_commission
                    )
                elif source == "all":
                    query = query.outerjoin(Offer).filter(or_(
                        and_(Product.source == "cj", cast(Offer.commission, Float) >= min_commission),
                        Product.source != "cj"
                    ))
                    
            # 应用类别筛选
            if main_categories:
                conditions = []
                for category in main_categories:
                    conditions.append(Product.categories.cast(String).like(f'%["{category}"%'))
                if conditions:
                    query = query.filter(or_(*conditions))
                    
            if sub_categories:
                conditions = []
                for category_path in sub_categories:
                    main_cat, sub_cat = category_path.split(":")
                    conditions.append(Product.categories.cast(String).like(f'%["{main_cat}", "{sub_cat}"%'))
                if conditions:
                    query = query.filter(or_(*conditions))
                    
            if bindings:
                query = query.filter(Product.binding.in_(bindings))
                
            if product_groups:
                query = query.filter(Product.product_group.in_(product_groups))
                
            # 应用排序
            query = ProductService._apply_sorting(query, sort_by, sort_order)
            
            # 应用分页
            total = query.count()  # 获取总数
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 执行查询
            products = query.all()
            
            # 转换为ProductInfo对象
            result = []
            for product in products:
                offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                
                product_info = ProductInfo(
                    asin=product.asin,
                    title=product.title,
                    url=product.url,
                    brand=product.brand,
                    main_image=product.main_image,
                    timestamp=product.timestamp or datetime.utcnow(),
                    binding=product.binding,
                    product_group=product.product_group,
                    categories=product.categories,
                    browse_nodes=product.browse_nodes,
                    cj_url=product.cj_url if product.source == "cj" else None,
                    offers=[
                        ProductOffer(
                            condition=offer.condition or "New",
                            price=offer.price or 0.0,
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
                            commission=offer.commission if product.source == "cj" else None
                        ) for offer in offers
                    ]
                )
                result.append(product_info)
                
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
        source: Optional[str] = None,
        min_commission: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取优惠券商品列表"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 连接优惠券历史表
            query = query.join(
                CouponHistory,
                Product.asin == CouponHistory.product_id
            )
            
            # 应用数据来源筛选
            if source:
                if source == "cj":
                    query = query.filter(Product.source == "cj")
                elif source == "pa-api":
                    query = query.filter(or_(
                        Product.source == "bestseller",
                        Product.source == "coupon",
                        Product.source == "pa-api",
                        Product.source.is_(None)
                    ))
            
            # 应用佣金筛选
            if min_commission is not None:
                if source == "cj":
                    query = query.join(Offer).filter(
                        cast(Offer.commission, Float) >= min_commission
                    )
                elif source == "all":
                    query = query.outerjoin(Offer).filter(or_(
                        and_(Product.source == "cj", cast(Offer.commission, Float) >= min_commission),
                        Product.source != "cj"
                    ))
            
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
                offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                
                product_info = ProductInfo(
                    asin=product.asin,
                    title=product.title,
                    url=product.url,
                    brand=product.brand,
                    main_image=product.main_image,
                    timestamp=product.timestamp or datetime.utcnow(),
                    binding=product.binding or None,
                    product_group=product.product_group or None,
                    categories=product.categories or [],
                    browse_nodes=product.browse_nodes or [],
                    cj_url=product.cj_url if product.source == "cj" else None,
                    offers=[
                        ProductOffer(
                            condition=offer.condition or "New",
                            price=offer.price or 0.0,
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
                            commission=offer.commission if product.source == "cj" else None
                        ) for offer in offers
                    ]
                )
                result.append(product_info)
                
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
        source: Optional[str] = None,
        min_commission: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取折扣商品列表"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 确保商品有折扣
            query = query.filter(Product.savings_percentage > 0)
            
            # 应用数据来源筛选
            if source:
                if source == "cj":
                    query = query.filter(Product.source == "cj")
                elif source == "pa-api":
                    query = query.filter(or_(
                        Product.source == "bestseller",
                        Product.source == "coupon",
                        Product.source == "pa-api",
                        Product.source.is_(None)
                    ))
            
            # 应用佣金筛选
            if min_commission is not None:
                if source == "cj":
                    query = query.join(Offer).filter(
                        cast(Offer.commission, Float) >= min_commission
                    )
                elif source == "all":
                    query = query.outerjoin(Offer).filter(or_(
                        and_(Product.source == "cj", cast(Offer.commission, Float) >= min_commission),
                        Product.source != "cj"
                    ))

            # 应用其他筛选条件
            if min_price is not None:
                query = query.filter(Product.current_price >= min_price)
            if max_price is not None:
                query = query.filter(Product.current_price <= max_price)
            if min_discount is not None:
                query = query.filter(Product.savings_percentage >= min_discount)
            if is_prime_only:
                query = query.filter(Product.is_prime == True)
                
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
                offers = db.query(Offer).filter(Offer.product_id == product.asin).all()
                
                product_info = ProductInfo(
                    asin=product.asin,
                    title=product.title,
                    url=product.url,
                    brand=product.brand,
                    main_image=product.main_image,
                    timestamp=product.timestamp or datetime.utcnow(),
                    binding=product.binding or None,
                    product_group=product.product_group or None,
                    categories=product.categories or [],
                    browse_nodes=product.browse_nodes or [],
                    cj_url=product.cj_url if product.source == "cj" else None,
                    offers=[
                        ProductOffer(
                            condition=offer.condition or "New",
                            price=offer.price or 0.0,
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
                            commission=offer.commission if product.source == "cj" else None
                        ) for offer in offers
                    ]
                )
                result.append(product_info)
                
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