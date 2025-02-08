from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from loguru import logger

from .database import CJProduct, CJSessionLocal, ProductVariant
from src.core.cj_api_client import CJAPIClient

class CJProductService:
    """CJ商品数据服务"""
    
    @staticmethod
    def create_product(db: Session, product_data: Dict[str, Any]) -> CJProduct:
        """创建新的CJ商品记录
        
        Args:
            db: 数据库会话
            product_data: CJ API返回的商品数据
            
        Returns:
            CJProduct: 创建的商品记录
        """
        try:
            # 处理价格字符串，移除$符号并转换为float
            original_price = float(product_data["original_price"].replace("$", "")) if product_data.get("original_price") else None
            discount_price = float(product_data["discount_price"].replace("$", "")) if product_data.get("discount_price") else None
            commission = float(product_data["commission"].replace("%", "")) if product_data.get("commission") else None
            
            # 判断是否为父商品
            is_parent = (
                product_data.get("parent_asin") == product_data.get("asin") or
                (not product_data.get("parent_asin") and product_data.get("variant_asin"))
            )
            
            # 创建商品记录
            product = CJProduct(
                asin=product_data["asin"],
                product_id=product_data["product_id"],
                product_name=product_data["product_name"],
                brand_name=product_data["brand_name"],
                brand_id=product_data["brand_id"],
                
                image=product_data["image"],
                url=product_data["url"],
                affiliate_url=product_data.get("affiliate_url"),
                
                original_price=original_price,
                discount_price=discount_price,
                commission=commission,
                
                discount_code=product_data.get("discount_code"),
                coupon=product_data.get("coupon"),
                
                parent_asin=product_data.get("parent_asin"),
                is_parent=is_parent,
                
                rating=float(product_data["rating"]) if product_data.get("rating") else None,
                reviews=int(product_data["reviews"]) if product_data.get("reviews") else None,
                
                category=product_data.get("category"),
                subcategory=product_data.get("subcategory"),
                
                is_featured_product=product_data.get("is_featured_product") == 1,
                is_amazon_choice=product_data.get("is_amazon_choice") == 1,
                
                update_time=datetime.fromisoformat(product_data["update_time"]) if product_data.get("update_time") else datetime.utcnow(),
                raw_data=product_data
            )
            
            db.add(product)
            db.commit()
            db.refresh(product)
            
            # 如果是父商品且有变体,创建变体关系
            if is_parent and product_data.get("variant_asin"):
                variant_asins = product_data["variant_asin"].split(",")
                for variant_asin in variant_asins:
                    if variant_asin and variant_asin != product.asin:
                        variant = ProductVariant(
                            parent_asin=product.asin,
                            variant_asin=variant_asin.strip(),
                            variant_attributes={}  # 可以从API响应中提取变体特有属性
                        )
                        db.add(variant)
                
                db.commit()
            
            return product
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建CJ商品记录失败: {str(e)}")
            raise
    
    @staticmethod
    def update_product(db: Session, product_data: Dict[str, Any]) -> Optional[CJProduct]:
        """更新现有的CJ商品记录
        
        Args:
            db: 数据库会话
            product_data: CJ API返回的商品数据
            
        Returns:
            Optional[CJProduct]: 更新的商品记录，如果不存在则返回None
        """
        try:
            product = db.query(CJProduct).filter(CJProduct.asin == product_data["asin"]).first()
            if not product:
                return None
                
            # 处理价格字符串
            original_price = float(product_data["original_price"].replace("$", "")) if product_data.get("original_price") else None
            discount_price = float(product_data["discount_price"].replace("$", "")) if product_data.get("discount_price") else None
            commission = float(product_data["commission"].replace("%", "")) if product_data.get("commission") else None
            
            # 更新商品信息
            product.product_name = product_data["product_name"]
            product.brand_name = product_data["brand_name"]
            product.brand_id = product_data["brand_id"]
            
            product.image = product_data["image"]
            product.url = product_data["url"]
            product.affiliate_url = product_data.get("affiliate_url")
            
            product.original_price = original_price
            product.discount_price = discount_price
            product.commission = commission
            
            product.discount_code = product_data.get("discount_code")
            product.coupon = product_data.get("coupon")
            
            product.parent_asin = product_data.get("parent_asin")
            product.variant_asin = product_data.get("variant_asin")
            
            product.rating = float(product_data["rating"]) if product_data.get("rating") else None
            product.reviews = int(product_data["reviews"]) if product_data.get("reviews") else None
            
            product.category = product_data.get("category")
            product.subcategory = product_data.get("subcategory")
            
            product.is_featured_product = product_data.get("is_featured_product") == 1
            product.is_amazon_choice = product_data.get("is_amazon_choice") == 1
            
            product.update_time = datetime.fromisoformat(product_data["update_time"]) if product_data.get("update_time") else datetime.utcnow()
            product.raw_data = product_data
            
            db.commit()
            db.refresh(product)
            return product
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新CJ商品记录失败: {str(e)}")
            raise
    
    @staticmethod
    def process_variants(db: Session, product_data: Dict[str, Any]) -> None:
        """处理商品变体关系
        
        Args:
            db: 数据库会话
            product_data: CJ API返回的商品数据
        """
        # 获取变体信息
        parent_asin = product_data.get("parent_asin")
        variant_asins = product_data.get("variant_asin", "").split(",") if product_data.get("variant_asin") else []
        
        if parent_asin and variant_asins:
            # 删除旧的变体关系
            db.query(ProductVariant).filter(
                ProductVariant.parent_asin == parent_asin
            ).delete()
            
            # 添加新的变体关系
            for variant_asin in variant_asins:
                if variant_asin:  # 确保ASIN不为空
                    variant = ProductVariant(
                        parent_asin=parent_asin,
                        variant_asin=variant_asin,
                        variant_attributes={}  # 可以从API响应中提取变体特有属性
                    )
                    db.add(variant)
            
            db.commit()

    @staticmethod
    def create_or_update_product(db: Session, product_data: Dict[str, Any]) -> CJProduct:
        """创建或更新CJ商品记录
        
        Args:
            db: 数据库会话
            product_data: CJ API返回的商品数据
            
        Returns:
            CJProduct: 创建或更新的商品记录
        """
        try:
            # 检查是否已存在相同parent_asin的商品
            parent_asin = product_data.get("parent_asin")
            if parent_asin:
                existing_product = db.query(CJProduct).filter(
                    CJProduct.parent_asin == parent_asin
                ).first()
                
                # 如果存在同parent_asin的商品,且当前商品不是主变体,则跳过
                if existing_product and existing_product.asin != parent_asin:
                    return existing_product
            
            # 原有的创建或更新逻辑...
            product = CJProductService.update_product(db, product_data)
            if not product:
                product = CJProductService.create_product(db, product_data)
            
            # 处理变体关系
            CJProductService.process_variants(db, product_data)
            
            return product
            
        except Exception as e:
            db.rollback()
            logger.error(f"处理CJ商品记录失败: {str(e)}")
            raise
    
    @staticmethod
    def bulk_create_or_update_products(db: Session, products_data: List[Dict[str, Any]]) -> List[CJProduct]:
        """批量创建或更新CJ商品记录
        
        Args:
            db: 数据库会话
            products_data: CJ API返回的商品数据列表
            
        Returns:
            List[CJProduct]: 创建或更新的商品记录列表
        """
        results = []
        for product_data in products_data:
            try:
                product = CJProductService.create_or_update_product(db, product_data)
                results.append(product)
            except Exception as e:
                logger.error(f"处理商品 {product_data.get('asin')} 失败: {str(e)}")
                continue
        return results
    
    @staticmethod
    def get_product_by_asin(db: Session, asin: str) -> Optional[CJProduct]:
        """根据ASIN获取CJ商品
        
        Args:
            db: 数据库会话
            asin: 商品ASIN
            
        Returns:
            Optional[CJProduct]: 商品记录，如果不存在则返回None
        """
        return db.query(CJProduct).filter(CJProduct.asin == asin).first()
    
    @staticmethod
    def list_products(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_commission: Optional[float] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        is_featured: Optional[bool] = None,
        is_amazon_choice: Optional[bool] = None
    ) -> List[Dict]:
        """获取CJ商品列表
        
        Args:
            db: 数据库会话
            page: 页码
            page_size: 每页数量
            min_price: 最低价格
            max_price: 最高价格
            min_commission: 最低佣金比例
            sort_by: 排序字段
            sort_order: 排序方向
            category: 主分类
            subcategory: 子分类
            is_featured: 是否精选商品
            is_amazon_choice: 是否亚马逊之选
            
        Returns:
            List[Dict]: 商品记录列表
        """
        try:
            query = db.query(CJProduct)
            
            # 应用过滤条件
            if min_price is not None:
                query = query.filter(CJProduct.discount_price >= min_price)
            if max_price is not None:
                query = query.filter(CJProduct.discount_price <= max_price)
            if min_commission is not None:
                query = query.filter(CJProduct.commission >= min_commission)
            if category:
                query = query.filter(CJProduct.category == category)
            if subcategory:
                query = query.filter(CJProduct.subcategory == subcategory)
            if is_featured is not None:
                query = query.filter(CJProduct.is_featured_product == is_featured)
            if is_amazon_choice is not None:
                query = query.filter(CJProduct.is_amazon_choice == is_amazon_choice)
            
            # 应用排序
            if sort_by:
                sort_column = getattr(CJProduct, sort_by, CJProduct.update_time)
                if sort_order == "desc":
                    query = query.order_by(desc(sort_column))
                else:
                    query = query.order_by(asc(sort_column))
            else:
                query = query.order_by(desc(CJProduct.update_time))
            
            # 应用分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            # 获取结果并转换为字典列表
            products = query.all()
            return [
                {
                    "id": p.id,
                    "asin": p.asin,
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "brand_name": p.brand_name,
                    "brand_id": p.brand_id,
                    "image": p.image,
                    "url": p.url,
                    "affiliate_url": p.affiliate_url,
                    "original_price": p.original_price,
                    "discount_price": p.discount_price,
                    "commission": p.commission,
                    "discount_code": p.discount_code,
                    "coupon": p.coupon,
                    "parent_asin": p.parent_asin,
                    "variant_asin": p.variant_asin,
                    "rating": p.rating,
                    "reviews": p.reviews,
                    "category": p.category,
                    "subcategory": p.subcategory,
                    "is_featured_product": p.is_featured_product,
                    "is_amazon_choice": p.is_amazon_choice,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    "update_time": p.update_time.isoformat() if p.update_time else None
                }
                for p in products
            ]
            
        except Exception as e:
            logger.error(f"获取CJ商品列表失败: {str(e)}")
            return []
    
    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        """获取CJ商品统计信息
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            total = db.query(func.count(CJProduct.id)).scalar()
            return {
                "total": total or 0,
                "last_update": db.query(func.max(CJProduct.updated_at)).scalar()
            }
        except Exception as e:
            logger.error(f"获取CJ商品统计信息失败: {str(e)}")
            return {
                "total": 0,
                "last_update": None
            } 