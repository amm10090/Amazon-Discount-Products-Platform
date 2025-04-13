#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
删除没有优惠的商品CLI工具

用于批量删除既没有折扣也没有优惠券的商品，支持多种过滤条件。
"""

import sys
import os
import argparse
from typing import Optional
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from sqlalchemy.orm import Session
from models.database import SessionLocal
from models.product_service import ProductService
from src.utils.log_config import get_logger, LogContext

def main():
    """CLI入口函数"""
    # 创建日志记录器
    logger = get_logger("RemoveProductsWithoutDiscount")
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='删除没有优惠的商品（既没有折扣也没有优惠券）')
    parser.add_argument('--dry-run', action='store_true', 
                      help='模拟执行但不实际删除，用于预览要删除的商品')
    parser.add_argument('--min-days-old', type=int, default=0, 
                      help='商品创建时间至少几天前，默认为0（不限制）')
    parser.add_argument('--max-days-old', type=int, default=None, 
                      help='商品创建时间最多几天前，默认为None（不限制）')
    parser.add_argument('--api-provider', type=str, choices=['pa-api', 'cj-api'], 
                      help='仅删除特定API提供商的商品（pa-api或cj-api）')
    parser.add_argument('--min-price', type=float, 
                      help='最低价格筛选，仅删除价格大于等于此值的商品')
    parser.add_argument('--max-price', type=float, 
                      help='最高价格筛选，仅删除价格小于等于此值的商品')
    parser.add_argument('--limit', type=int, 
                      help='最多删除的商品数量，默认不限制')
    parser.add_argument('--yes', action='store_true', 
                      help='自动确认删除操作，不提示确认')
    
    args = parser.parse_args()
    
    with LogContext(
        dry_run=args.dry_run,
        min_days_old=args.min_days_old,
        max_days_old=args.max_days_old,
        api_provider=args.api_provider,
        min_price=args.min_price,
        max_price=args.max_price,
        limit=args.limit
    ):
        # 打印运行参数
        logger.info(f"开始{'模拟' if args.dry_run else ''}删除没有优惠的商品，参数:")
        logger.info(f"  模拟模式: {args.dry_run}")
        logger.info(f"  最少天数: {args.min_days_old}")
        logger.info(f"  最多天数: {args.max_days_old}")
        logger.info(f"  API提供商: {args.api_provider or '所有'}")
        logger.info(f"  最低价格: {args.min_price or '不限'}")
        logger.info(f"  最高价格: {args.max_price or '不限'}")
        logger.info(f"  数量限制: {args.limit or '不限'}")
        
        # 创建数据库会话
        db = SessionLocal()
        
        try:
            # 调用服务方法查找没有优惠的商品
            result = ProductService.remove_products_without_discount(
                db=db,
                dry_run=True,  # 第一次总是使用dry_run来预览
                min_days_old=args.min_days_old,
                max_days_old=args.max_days_old,
                api_provider=args.api_provider,
                min_price=args.min_price,
                max_price=args.max_price,
                limit=args.limit
            )
            
            total_found = result.get("total_found", 0)
            
            if total_found == 0:
                logger.info("没有找到符合条件的商品，无需删除")
                return
                
            # 打印找到的商品信息（仅显示前10个）
            logger.info(f"找到 {total_found} 个没有优惠的商品")
            
            products_info = result.get("products", [])
            if products_info:
                display_count = min(10, len(products_info))
                logger.info(f"以下是找到的部分商品（显示前{display_count}个）:")
                
                for i, product in enumerate(products_info[:display_count]):
                    logger.info(f"  {i+1}. ASIN: {product['asin']}, 标题: {product['title'][:50]}..., 价格: {product['price']}, 创建时间: {product['created_at']}, 数据源: {product['api_provider']}")
                
                if len(products_info) > display_count:
                    logger.info(f"  ...以及其他 {len(products_info) - display_count} 个商品")
            
            # 如果不是dry_run模式，请求用户确认（除非使用--yes参数）
            if not args.dry_run and not args.yes:
                confirm = input(f"\n确认删除这 {total_found} 个商品？(y/N): ").strip().lower()
                
                if confirm != 'y':
                    logger.info("操作已取消")
                    return
                    
                logger.info("用户已确认删除操作")
                
                # 执行实际的删除操作
                delete_result = ProductService.remove_products_without_discount(
                    db=db,
                    dry_run=False,
                    min_days_old=args.min_days_old,
                    max_days_old=args.max_days_old,
                    api_provider=args.api_provider,
                    min_price=args.min_price,
                    max_price=args.max_price,
                    limit=args.limit
                )
                
                deleted = delete_result.get("deleted", 0)
                failed = delete_result.get("failed", 0)
                
                logger.info(f"删除操作完成: 成功删除 {deleted}/{total_found} 个商品, 失败 {failed} 个")
            
        except Exception as e:
            logger.error(f"删除没有优惠的商品时出错: {str(e)}")
            
        finally:
            db.close()

if __name__ == "__main__":
    main() 