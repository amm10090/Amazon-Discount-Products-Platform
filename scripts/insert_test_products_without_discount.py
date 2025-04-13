#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
插入没有优惠的测试商品脚本

用于向数据库插入没有优惠和折扣的测试商品，
以便测试系统中的商品清理功能。
"""

import sys
import os
import random
import json
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import func
from models.database import SessionLocal, Product, Offer
from models.product import ProductInfo, ProductOffer
from models.product_service import ProductService
from src.utils.log_config import get_logger

# 创建日志记录器
logger = get_logger("InsertTestProducts")

# 测试商品数据
TEST_PRODUCTS = [
    # 基本低价商品 - PA-API
    {
        "asin": "T1PA000001",
        "title": "测试商品1 - 低价无优惠",
        "brand": "测试品牌",
        "price": 9.99,
        "api_provider": "pa-api",
        "days_old": 1
    },
    # 中价商品 - PA-API
    {
        "asin": "T1PA000002",
        "title": "测试商品2 - 中价无优惠",
        "brand": "测试品牌",
        "price": 29.99,
        "api_provider": "pa-api",
        "days_old": 5
    },
    # 高价商品 - PA-API
    {
        "asin": "T1PA000003",
        "title": "测试商品3 - 高价无优惠",
        "brand": "测试品牌",
        "price": 149.99,
        "api_provider": "pa-api",
        "days_old": 10
    },
    # 低价商品 - CJ-API
    {
        "asin": "T1CJ000001",
        "title": "测试商品4 - 低价无优惠CJ",
        "brand": "测试品牌CJ",
        "price": 8.99,
        "api_provider": "cj-api",
        "days_old": 2
    },
    # 中价商品 - CJ-API
    {
        "asin": "T1CJ000002",
        "title": "测试商品5 - 中价无优惠CJ",
        "brand": "测试品牌CJ",
        "price": 39.99,
        "api_provider": "cj-api",
        "days_old": 7
    },
    # 高价商品 - CJ-API
    {
        "asin": "T1CJ000003",
        "title": "测试商品6 - 高价无优惠CJ",
        "brand": "测试品牌CJ",
        "price": 199.99,
        "api_provider": "cj-api",
        "days_old": 15
    },
    # 非常老的商品 - PA-API
    {
        "asin": "T1PA000004",
        "title": "测试商品7 - 很老无优惠",
        "brand": "测试品牌",
        "price": 19.99,
        "api_provider": "pa-api",
        "days_old": 45
    },
    # 非常老的商品 - CJ-API
    {
        "asin": "T1CJ000004",
        "title": "测试商品8 - 很老无优惠CJ",
        "brand": "测试品牌CJ",
        "price": 19.99,
        "api_provider": "cj-api",
        "days_old": 60
    },
    # Prime会员商品 - PA-API
    {
        "asin": "T1PA000005",
        "title": "测试商品9 - Prime无优惠",
        "brand": "测试品牌",
        "price": 49.99,
        "api_provider": "pa-api",
        "days_old": 3,
        "is_prime": True
    },
    # 非常高价商品 - PA-API
    {
        "asin": "T1PA000006",
        "title": "测试商品10 - 超高价无优惠",
        "brand": "测试品牌",
        "price": 499.99,
        "api_provider": "pa-api",
        "days_old": 5
    }
]

def create_product_using_orm(
    db: Session,
    product_data: Dict[str, Any],
    create_offer: bool = True
) -> Product:
    """
    使用ORM模型直接创建商品
    
    Args:
        db: 数据库会话
        product_data: 商品数据
        create_offer: 是否创建Offer记录
        
    Returns:
        Product: 创建的商品对象
    """
    # 计算创建时间
    created_at = datetime.now() - timedelta(days=product_data.get("days_old", 0))
    
    # 创建Product对象
    product = Product(
        asin=product_data["asin"],
        title=product_data["title"],
        url=f"https://www.amazon.com/dp/{product_data['asin']}",
        brand=product_data.get("brand", "Test Brand"),
        main_image=f"https://example.com/images/{product_data['asin']}.jpg",
        
        # 价格信息 - 注意这里设置为无折扣
        current_price=product_data.get("price", 29.99),
        original_price=product_data.get("price", 29.99),  # 与当前价格相同，表示无折扣
        currency="USD",
        savings_amount=0.0,  # 无节省金额
        savings_percentage=0,  # 无折扣百分比
        
        # Prime信息
        is_prime=product_data.get("is_prime", False),
        is_prime_exclusive=False,
        
        # 商品状态
        condition="New",
        availability="In Stock",
        merchant_name="Amazon",
        is_buybox_winner=True,
        
        # 分类信息
        binding=product_data.get("binding", "其他"),
        product_group=product_data.get("product_group", "家居"),
        categories=json.dumps(["测试分类", "无优惠商品"]),
        
        # 其他信息
        features=json.dumps(["测试功能1", "测试功能2"]),
        
        # 时间信息 - 根据days_old设置
        created_at=created_at,
        updated_at=created_at,
        timestamp=created_at,
        
        # 元数据
        source="test",
        api_provider=product_data.get("api_provider", "pa-api")
    )
    
    # 添加商品到数据库
    db.add(product)
    db.flush()  # 刷新以获取ID
    
    # 如果需要创建Offer，则添加Offer记录
    if create_offer:
        offer = Offer(
            product_id=product.asin,
            condition="New",
            price=product_data.get("price", 29.99),
            currency="USD",
            savings=0.0,  # 无节省金额
            savings_percentage=0,  # 无折扣百分比
            is_prime=product_data.get("is_prime", False),
            is_amazon_fulfilled=product_data.get("is_prime", False),
            is_free_shipping_eligible=product_data.get("is_prime", False),
            availability="In Stock",
            merchant_name="Amazon",
            is_buybox_winner=True,
            created_at=created_at,
            updated_at=created_at
            # 注意：没有设置coupon_type和coupon_value，表示无优惠券
        )
        db.add(offer)
    
    db.commit()
    db.refresh(product)
    
    return product

def create_product_using_service(
    db: Session,
    product_data: Dict[str, Any]
) -> Product:
    """
    使用ProductService创建商品
    
    Args:
        db: 数据库会话
        product_data: 商品数据
        
    Returns:
        Product: 创建的商品对象
    """
    # 计算创建时间
    created_at = datetime.now() - timedelta(days=product_data.get("days_old", 0))
    
    # 创建ProductOffer对象
    offer = ProductOffer(
        condition="New",
        price=product_data.get("price", 29.99),
        currency="USD",
        savings=0.0,  # 无节省金额
        savings_percentage=0,  # 无折扣百分比
        is_prime=product_data.get("is_prime", False),
        is_amazon_fulfilled=product_data.get("is_prime", False),
        is_free_shipping_eligible=product_data.get("is_prime", False),
        availability="In Stock",
        merchant_name="Amazon",
        is_buybox_winner=True
        # 注意：没有设置coupon_type和coupon_value，表示无优惠券
    )
    
    # 创建ProductInfo对象
    product_info = ProductInfo(
        asin=product_data["asin"],
        title=product_data["title"],
        url=f"https://www.amazon.com/dp/{product_data['asin']}",
        brand=product_data.get("brand", "Test Brand"),
        main_image=f"https://example.com/images/{product_data['asin']}.jpg",
        offers=[offer],
        timestamp=created_at,
        categories=["测试分类", "无优惠商品"],
        binding=product_data.get("binding", "其他"),
        product_group=product_data.get("product_group", "家居"),
        features=["测试功能1", "测试功能2"],
        api_provider=product_data.get("api_provider", "pa-api")
    )
    
    # 使用服务创建商品
    product = ProductService.create_product(db, product_info, source="test")
    
    # 更新创建时间以模拟不同时间创建的商品
    product.created_at = created_at
    product.updated_at = created_at
    product.timestamp = created_at
    db.commit()
    
    return product

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='向数据库插入没有优惠的测试商品')
    parser.add_argument('--count', type=int, default=len(TEST_PRODUCTS),
                        help=f'要插入的商品数量，默认为所有测试商品({len(TEST_PRODUCTS)}个)')
    parser.add_argument('--method', choices=['orm', 'service', 'both'], default='both',
                        help='创建商品的方法: orm(直接ORM), service(ProductService), both(两种方法各半)')
    parser.add_argument('--check', action='store_true',
                        help='检查商品是否符合"无优惠"条件')
    parser.add_argument('--force', action='store_true',
                        help='强制插入，即使商品已存在')
    
    args = parser.parse_args()
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 设置要插入的商品数量
        count = min(args.count, len(TEST_PRODUCTS))
        
        # 检查商品是否已存在
        existing_count = 0
        for i in range(count):
            product_data = TEST_PRODUCTS[i]
            asin = product_data["asin"]
            
            existing = db.query(Product).filter(Product.asin == asin).first()
            if existing:
                existing_count += 1
                if not args.force:
                    logger.warning(f"商品已存在: {asin}，跳过（使用--force选项覆盖）")
                    continue
                else:
                    # 删除现有商品
                    logger.info(f"商品已存在: {asin}，将删除并重新创建")
                    db.delete(existing)
                    db.commit()
        
        if existing_count > 0 and not args.force:
            logger.warning(f"已存在 {existing_count}/{count} 个商品，使用--force选项覆盖")
        
        # 根据选择的方法，决定对每个商品使用哪种创建方式
        inserted_count = 0
        for i in range(count):
            product_data = TEST_PRODUCTS[i]
            asin = product_data["asin"]
            
            # 检查商品是否存在
            existing = db.query(Product).filter(Product.asin == asin).first()
            if existing and not args.force:
                continue
                
            # 根据方法选择创建方式
            if args.method == 'orm' or (args.method == 'both' and i % 2 == 0):
                logger.info(f"使用ORM方法创建商品: {asin}")
                create_product_using_orm(db, product_data)
            else:
                logger.info(f"使用Service方法创建商品: {asin}")
                create_product_using_service(db, product_data)
                
            inserted_count += 1
        
        # 打印创建结果
        logger.info(f"成功插入 {inserted_count} 个无优惠测试商品")
        
        # 检查商品是否符合"无优惠"条件
        if args.check:
            logger.info("检查商品是否符合'无优惠'条件...")
            
            # 使用remove_products_without_discount的条件检查
            result = ProductService.remove_products_without_discount(
                db=db,
                dry_run=True,
                api_provider=None,
                min_days_old=0
            )
            
            # 获取所有符合条件的商品
            total_found = result.get("total_found", 0)
            products = result.get("products", [])
            
            # 检查测试商品是否在结果中
            test_asins = [p["asin"] for p in TEST_PRODUCTS[:count]]
            found_asins = [p["asin"] for p in products]
            
            missing_asins = [asin for asin in test_asins if asin not in found_asins]
            
            if missing_asins:
                logger.warning(f"以下测试商品不符合'无优惠'条件: {missing_asins}")
                logger.warning("请检查这些商品是否有优惠券历史或折扣记录")
            else:
                logger.info(f"所有测试商品都符合'无优惠'条件，可以被清理功能识别")
            
            # 打印详细结果
            logger.info(f"共有 {total_found} 个商品符合'无优惠'条件")
            if products:
                logger.info("符合条件的商品ASIN列表:")
                for p in products[:10]:  # 只显示前10个
                    logger.info(f"  {p['asin']} - {p['title']}")
                if len(products) > 10:
                    logger.info(f"  ... 以及其他 {len(products) - 10} 个商品")
            
    except Exception as e:
        logger.error(f"插入测试商品时出错: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main() 