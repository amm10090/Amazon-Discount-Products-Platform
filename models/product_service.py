from typing import List, Optional, Dict, Any
import logging
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey, or_, cast, and_
import json

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
            features=json.dumps([]) if not product_info.features else json.dumps(product_info.features),
            
            # 分类信息
            categories=json.dumps(product_info.categories) if product_info.categories else json.dumps([]),
            browse_nodes=json.dumps(product_info.browse_nodes) if product_info.browse_nodes else json.dumps([]),
            binding=product_info.binding,
            product_group=product_info.product_group,
            
            # 元数据
            source=source,
            raw_data=json.dumps(product_info.dict())
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
        include_cj_data: bool = False,
        source: Optional[str] = None,
        api_provider: str = "pa-api",
        include_metadata: bool = False
    ) -> List[ProductInfo]:
        """批量创建或更新商品信息"""
        saved_products = []
        current_time = datetime.utcnow()
        
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
                        cj_url=product_info.cj_url if include_cj_data and hasattr(product_info, 'cj_url') else None
                    )
                    
                    # 添加分类相关信息
                    if include_metadata:
                        product.binding = product_info.binding
                        product.product_group = product_info.product_group
                        
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
                    
                    # 更新CJ相关信息
                    if include_cj_data and hasattr(product_info, 'cj_url'):
                        product.cj_url = product_info.cj_url
                    
                    # 更新时间和元数据
                    product.updated_at = current_time
                    product.timestamp = current_time
                    if source:  # 只在明确指定source时更新
                        product.source = source
                    product.api_provider = product_info.api_provider  # 使用ProductInfo对象中的api_provider
                    product.raw_data = raw_data
                
                # 删除旧的优惠信息
                db.query(Offer).filter(Offer.product_id == product.asin).delete()
                
                # 添加新的优惠信息
                for offer_info in product_info.offers:
                    # 添加调试日志
                    if hasattr(offer_info, 'commission'):
                        logger.debug(f"处理商品 {product.asin} 的佣金信息: {offer_info.commission}")
                        
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
                    
                    # 添加调试日志
                    if offer.commission:
                        logger.debug(f"已设置商品 {product.asin} 的佣金信息到数据库: {offer.commission}")
                    
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
                logger.error(f"处理商品时出错 {product_info.asin}: {str(e)}")
                continue
        
        try:
            # 提交事务
            db.commit()
        except Exception as e:
            logger.error(f"提交事务时出错: {str(e)}")
            db.rollback()
            raise
        
        return saved_products

    @staticmethod
    def get_category_stats(db: Session, product_type: Optional[str] = None) -> Dict[str, Any]:
        """获取类别统计信息
        
        Args:
            db: 数据库会话
            product_type: 商品类型 ('discount'/'coupon'/None)
            
        Returns:
            Dict[str, Any]: 类别统计信息
        """
        try:
            # 构建基础查询
            query = db.query(Product)
            
            # 根据商品类型筛选
            if product_type:
                query = query.filter(Product.source == product_type)
            
            # 获取所有符合条件的商品
            products = query.all()
            
            # 初始化统计字典
            stats = {
                "browse_nodes": {},     # 浏览节点统计
                "browse_tree": {},      # 浏览节点树形结构
                "bindings": {},         # 商品绑定类型统计
                "product_groups": {},   # 商品组统计
            }
            
            # 用于构建树形结构的临时存储
            node_relations = {}  # 存储节点之间的关系
            
            for product in products:
                try:
                    # 处理binding (商品绑定类型)
                    if product.binding:
                        stats["bindings"][product.binding] = stats["bindings"].get(product.binding, 0) + 1
                    
                    # 处理product_group (商品组)
                    if product.product_group:
                        stats["product_groups"][product.product_group] = stats["product_groups"].get(product.product_group, 0) + 1
                    
                    # 解析browse_nodes JSON字符串
                    if product.browse_nodes:
                        try:
                            browse_nodes = json.loads(product.browse_nodes)
                            if isinstance(browse_nodes, list):
                                # 构建节点关系
                                for node in browse_nodes:
                                    if isinstance(node, dict) and "id" in node and "name" in node:
                                        node_id = node["id"]
                                        node_name = node["name"]
                                        parent_id = node.get("parent_id")  # 获取父节点ID
                                        
                                        # 更新节点统计
                                        if node_id not in stats["browse_nodes"]:
                                            stats["browse_nodes"][node_id] = {
                                                "id": node_id,
                                                "name": node_name,
                                                "count": 0,
                                                "is_root": not parent_id,  # 如果没有父节点,则为根节点
                                                "level": node.get("level", 0)  # 节点层级
                                            }
                                        stats["browse_nodes"][node_id]["count"] += 1
                                        
                                        # 存储节点关系用于构建树形结构
                                        if node_id not in node_relations:
                                            node_relations[node_id] = {
                                                "name": node_name,
                                                "count": 1,
                                                "children": set(),
                                                "parents": set(),
                                                "level": node.get("level", 0)
                                            }
                                        else:
                                            node_relations[node_id]["count"] += 1
                                            
                                        # 建立父子关系
                                        if parent_id:
                                            if parent_id not in node_relations:
                                                node_relations[parent_id] = {
                                                    "name": "",  # 暂时为空,后续可能会更新
                                                    "count": 0,
                                                    "children": {node_id},
                                                    "parents": set(),
                                                    "level": node.get("level", 0) - 1
                                                }
                                            else:
                                                node_relations[parent_id]["children"].add(node_id)
                                            node_relations[node_id]["parents"].add(parent_id)
                                            
                        except json.JSONDecodeError as e:
                            logger.error(f"解析商品 {product.asin} 的browse_nodes时出错: {str(e)}")
                            continue
                            
                except Exception as e:
                    logger.error(f"处理商品 {product.asin} 的统计信息时出错: {str(e)}")
                    continue
            
            # 构建树形结构
            def build_tree(node_id: str) -> Dict:
                node = node_relations[node_id]
                return {
                    "id": node_id,
                    "name": node["name"],
                    "count": node["count"],
                    "level": node["level"],
                    "children": {
                        child_id: build_tree(child_id) 
                        for child_id in node["children"]
                    }
                }
            
            # 找出根节点（没有父节点的节点）
            root_nodes = {
                node_id for node_id in node_relations 
                if not node_relations[node_id]["parents"]
            }
            
            # 从根节点开始构建树
            stats["browse_tree"] = {
                root_id: build_tree(root_id)
                for root_id in root_nodes
            }
            
            # 对统计结果排序
            stats["bindings"] = dict(sorted(stats["bindings"].items(), key=lambda x: x[1], reverse=True))
            stats["product_groups"] = dict(sorted(stats["product_groups"].items(), key=lambda x: x[1], reverse=True))
            stats["browse_nodes"] = dict(sorted(
                stats["browse_nodes"].items(), 
                key=lambda x: (x[1]["level"], -x[1]["count"])  # 先按层级排序,同层级按数量倒序
            ))
            
            return stats
            
        except Exception as e:
            logger.error(f"获取类别统计信息失败: {str(e)}")
            return {
                "browse_nodes": {},
                "browse_tree": {},
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
        browse_node_ids: Optional[List[str]] = None,  # 使用browse_node_ids替代main_categories和sub_categories
        bindings: Optional[List[str]] = None,
        product_groups: Optional[List[str]] = None,
        source: Optional[str] = None,
        min_commission: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取商品列表，支持分页、筛选和排序"""
        try:
            # 构建基础查询
            query = db.query(Product).distinct(Product.asin)
            
            # 根据product_type筛选
            if product_type != "all":
                query = query.filter(Product.source == product_type)
                
            # 根据数据来源筛选
            if source:
                if source == "cj":
                    query = query.filter(Product.api_provider == "cj-api")
                elif source == "pa-api":
                    query = query.filter(Product.api_provider == "pa-api")
                    
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
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ]
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
        product_groups: Optional[List[str]] = None
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
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ]
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
        product_groups: Optional[List[str]] = None    # 添加product_groups参数
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
                                commission=offer.commission if product.api_provider == "cj-api" else None
                            ) for offer in offers
                        ]
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