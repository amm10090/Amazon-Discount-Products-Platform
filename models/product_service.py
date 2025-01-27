from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from datetime import datetime, timedelta
from .database import Product, Offer
from .product import ProductInfo, ProductOffer

class ProductService:
    """产品数据服务"""
    
    @staticmethod
    def create_product(db: Session, product_info: ProductInfo, source: str = "pa-api") -> Product:
        """创建新产品记录"""
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
        """更新现有产品记录"""
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
    def get_product_by_asin(db: Session, asin: str) -> Optional[Product]:
        """通过ASIN获取产品"""
        return db.query(Product).filter(Product.asin == asin).first()
    
    @staticmethod
    def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[Product]:
        """获取产品列表"""
        return db.query(Product).offset(skip).limit(limit).all()
    
    @staticmethod
    def create_or_update_product(db: Session, product_info: ProductInfo, source: str = "pa-api") -> Product:
        """创建或更新产品记录"""
        existing_product = ProductService.get_product_by_asin(db, product_info.asin)
        if existing_product:
            return ProductService.update_product(db, product_info, source)
        return ProductService.create_product(db, product_info, source)
    
    @staticmethod
    def bulk_create_or_update_products(db: Session, products: List[ProductInfo]) -> List[ProductInfo]:
        """
        批量创建或更新产品信息
        """
        saved_products = []
        current_time = datetime.utcnow()
        
        for product_info in products:
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
                    created_at=current_time,
                    updated_at=current_time,
                    timestamp=current_time
                )
                db.add(product)
            else:
                # 更新现有产品
                product.title = product_info.title
                product.url = product_info.url
                product.brand = product_info.brand
                product.main_image = product_info.main_image
                product.updated_at = current_time
                product.timestamp = current_time
            
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
                    availability=offer_info.availability,
                    merchant_name=offer_info.merchant_name,
                    is_buybox_winner=offer_info.is_buybox_winner,
                    deal_type=offer_info.deal_type,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(offer)
            
            saved_products.append(product_info)
        
        # 提交事务
        db.commit()
        
        return saved_products

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
        is_prime_only: bool = False
    ) -> List[ProductInfo]:
        """
        获取产品列表，支持分页、筛选和排序
        """
        # 构建基础查询
        query = db.query(Product).join(Offer)
        
        # 应用筛选条件
        if min_price is not None:
            query = query.filter(Offer.price >= min_price)
        if max_price is not None:
            query = query.filter(Offer.price <= max_price)
        if min_discount is not None:
            query = query.filter(Offer.savings_percentage >= min_discount)
        if is_prime_only:
            query = query.filter(Offer.is_prime == True)
            
        # 应用排序
        if sort_by:
            order_func = desc if sort_order == "desc" else asc
            if sort_by == "price":
                query = query.order_by(order_func(Offer.price))
            elif sort_by == "discount":
                query = query.order_by(order_func(Offer.savings_percentage))
            elif sort_by == "timestamp":
                query = query.order_by(order_func(Product.timestamp))
                
        # 应用分页
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        # 执行查询
        products = query.all()
        
        # 转换为ProductInfo对象
        return [
            ProductInfo(
                asin=p.asin,
                title=p.title,
                url=p.url,
                brand=p.brand,
                main_image=p.main_image,
                offers=[
                    ProductOffer(
                        condition=o.condition,
                        price=o.price,
                        currency=o.currency,
                        savings=o.savings,
                        savings_percentage=o.savings_percentage,
                        is_prime=o.is_prime,
                        availability=o.availability,
                        merchant_name=o.merchant_name,
                        is_buybox_winner=o.is_buybox_winner,
                        deal_type=o.deal_type
                    ) for o in p.offers
                ],
                timestamp=p.timestamp
            ) for p in products
        ]

    @staticmethod
    def get_product_by_asin(db: Session, asin: str) -> Optional[ProductInfo]:
        """
        根据ASIN获取单个产品详情
        """
        product = db.query(Product).filter(Product.asin == asin).first()
        
        if not product:
            return None
            
        return ProductInfo(
            asin=product.asin,
            title=product.title,
            url=product.url,
            brand=product.brand,
            main_image=product.main_image,
            offers=[
                ProductOffer(
                    condition=o.condition,
                    price=o.price,
                    currency=o.currency,
                    savings=o.savings,
                    savings_percentage=o.savings_percentage,
                    is_prime=o.is_prime,
                    availability=o.availability,
                    merchant_name=o.merchant_name,
                    is_buybox_winner=o.is_buybox_winner,
                    deal_type=o.deal_type
                ) for o in product.offers
            ],
            timestamp=product.timestamp
        )

    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        """
        获取产品数据统计信息
        """
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