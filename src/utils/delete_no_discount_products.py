#!/usr/bin/env python
"""
批量删除没有优惠的商品工具

该工具用于清理数据库中没有任何优惠信息的商品。
根据多种标准过滤商品，可以仅列出而不删除(dry-run模式)。

用法:
    python delete_no_discount_products.py [选项]

选项:
    --dry-run            仅列出符合条件的商品，不执行删除(默认启用)
    --execute            确认执行删除操作
    --min-days-old N     仅处理N天前创建的商品
    --max-days-old N     仅处理最多N天前创建的商品
    --min-price N        仅处理价格大于N的商品
    --max-price N        仅处理价格小于N的商品
    --limit N            最多处理N个商品
    --verbose            显示详细信息
"""

import os
import sys
import argparse
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Any
import logging
from sqlalchemy import func, and_, or_
from tqdm import tqdm

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, Offer, get_db
from src.utils.log_config import get_logger

# 初始化日志记录器
logger = get_logger("DeleteNoDiscountProducts")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='批量删除没有优惠的商品')
    parser.add_argument('--dry-run', action='store_true', default=True, 
                       help='仅列出符合条件的商品，不执行删除(默认启用)')
    parser.add_argument('--execute', action='store_true', 
                       help='确认执行删除操作')
    parser.add_argument('--min-days-old', type=int, default=0,
                       help='仅处理至少N天前创建的商品')
    parser.add_argument('--max-days-old', type=int, 
                       help='仅处理最多N天前创建的商品')
    parser.add_argument('--min-price', type=float,
                       help='仅处理价格大于N的商品')
    parser.add_argument('--max-price', type=float,
                       help='仅处理价格小于N的商品')
    parser.add_argument('--limit', type=int,
                       help='最多处理N个商品')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细信息')
    
    args = parser.parse_args()
    
    # 如果指定了execute，则关闭dry-run
    if args.execute:
        args.dry_run = False
        
    return args

def find_products_without_discount(db, min_days_old=0, max_days_old=None, 
                                  min_price=None, max_price=None, limit=None):
    """查找没有任何优惠的商品"""
    
    # 构建基本查询
    query = db.query(Product)
    
    # 日期过滤条件
    if min_days_old > 0:
        min_date = datetime.now(UTC) - timedelta(days=min_days_old)
        query = query.filter(Product.created_at <= min_date)
        
    if max_days_old is not None:
        max_date = datetime.now(UTC) - timedelta(days=max_days_old)
        query = query.filter(Product.created_at >= max_date)
    
    # 价格过滤条件
    if min_price is not None:
        query = query.filter(Product.current_price >= min_price)
        
    if max_price is not None:
        query = query.filter(Product.current_price <= max_price)
    
    # 构建"没有优惠"的条件
    # 1. 没有折扣
    no_discount_condition = and_(
        or_(Product.savings_amount.is_(None), Product.savings_amount <= 0),
        or_(Product.savings_percentage.is_(None), Product.savings_percentage <= 0)
    )
    
    # 2. 没有优惠券 - 使用offers关联查询
    query = query.outerjoin(Offer, Product.asin == Offer.product_id)
    no_coupon_condition = and_(
        or_(Offer.coupon_type.is_(None), Offer.coupon_type == ''),
        or_(Offer.coupon_value.is_(None), Offer.coupon_value <= 0)
    )
    
    # 3. 没有促销标签
    no_deal_condition = or_(Offer.deal_badge.is_(None), Offer.deal_badge == '')
    
    # 组合条件
    query = query.filter(and_(no_discount_condition, no_coupon_condition, no_deal_condition))
    
    # 可选的结果限制
    if limit:
        query = query.limit(limit)
    
    return query.all()

def delete_products(db, products, dry_run=True, verbose=False):
    """删除指定的商品列表"""
    results = {
        'total_found': len(products),
        'deleted': 0,
        'failed': 0,
        'details': []
    }
    
    if dry_run:
        logger.info(f"模拟模式：发现{len(products)}个没有优惠的商品")
        for product in products:
            if verbose:
                logger.info(f"将删除商品: {product.asin} (创建于 {product.created_at})")
            results['details'].append({
                'asin': product.asin,
                'created_at': product.created_at.isoformat() if product.created_at else None,
                'current_price': product.current_price,
                'savings_amount': product.savings_amount,
                'savings_percentage': product.savings_percentage
            })
        return results
    
    logger.info(f"开始删除{len(products)}个没有优惠的商品...")
    progress_bar = tqdm(total=len(products), desc="删除商品", unit="个")
    
    for product in products:
        try:
            # 删除关联的offers记录
            db.query(Offer).filter(Offer.product_id == product.asin).delete()
            
            # 删除商品记录
            db.delete(product)
            
            if verbose:
                logger.info(f"已删除商品: {product.asin}")
                
            results['deleted'] += 1
            results['details'].append({
                'asin': product.asin,
                'status': 'deleted'
            })
            
        except Exception as e:
            logger.error(f"删除商品{product.asin}时出错: {str(e)}")
            results['failed'] += 1
            results['details'].append({
                'asin': product.asin,
                'status': 'failed',
                'error': str(e)
            })
            
        progress_bar.update(1)
    
    # 提交事务
    try:
        db.commit()
        logger.info(f"成功删除{results['deleted']}个商品，失败{results['failed']}个")
    except Exception as e:
        db.rollback()
        logger.error(f"提交事务时出错: {str(e)}")
        results['failed'] = len(products)
        results['deleted'] = 0
        
    progress_bar.close()
    return results

def main():
    """主函数"""
    args = parse_arguments()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        # 输出运行模式
        if args.dry_run:
            logger.info("运行模式: 仅查询模拟 (不会删除任何数据)")
        else:
            logger.info("运行模式: 实际删除")
            
        # 构建过滤条件说明
        filters = []
        if args.min_days_old > 0:
            filters.append(f"创建时间 >= {args.min_days_old}天前")
        if args.max_days_old:
            filters.append(f"创建时间 <= {args.max_days_old}天前")
        if args.min_price:
            filters.append(f"价格 >= ${args.min_price}")
        if args.max_price:
            filters.append(f"价格 <= ${args.max_price}")
        if args.limit:
            filters.append(f"最多处理{args.limit}个商品")
            
        if filters:
            logger.info(f"应用过滤条件: {', '.join(filters)}")
        
        # 查找没有任何优惠的商品
        logger.info("查询没有任何优惠的商品...")
        products = find_products_without_discount(
            db, 
            min_days_old=args.min_days_old,
            max_days_old=args.max_days_old,
            min_price=args.min_price,
            max_price=args.max_price,
            limit=args.limit
        )
        
        if not products:
            logger.info("没有找到符合条件的商品")
            return
            
        # 删除商品或模拟删除
        results = delete_products(
            db, 
            products, 
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        
        # 输出统计信息
        logger.info(f"统计信息:")
        logger.info(f"  • 找到商品: {results['total_found']}个")
        
        if not args.dry_run:
            logger.info(f"  • 成功删除: {results['deleted']}个")
            logger.info(f"  • 删除失败: {results['failed']}个")
            
    except Exception as e:
        logger.error(f"处理过程中出错: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
    finally:
        db.close()

if __name__ == "__main__":
    main() 