from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
from .database import Product
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
    def bulk_create_or_update_products(db: Session, product_infos: List[ProductInfo], source: str = "pa-api") -> List[Product]:
        """批量创建或更新产品记录"""
        results = []
        for product_info in product_infos:
            product = ProductService.create_or_update_product(db, product_info, source)
            results.append(product)
        return results 