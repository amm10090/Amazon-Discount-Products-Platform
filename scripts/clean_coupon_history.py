#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理无效的优惠券历史记录

该脚本用于清理coupon_history表中的无效记录：
- 检查coupon_history表中的product_id字段
- 如果在products表中找不到对应的asin，则删除该记录
- 删除coupon_history表中product_id对应products表中source为discount的商品的记录
- 为每个商品只保留最新的三条优惠券历史记录，删除更早的记录
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import text
from collections import defaultdict

# 添加项目根目录到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.append(str(project_root))

from models.database import SessionLocal, Product, CouponHistory

def setup_logging():
    """配置日志系统"""
    log_dir = Path(project_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台处理器
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True
    )
    
    # 添加文件处理器
    logger.add(
        log_dir / "clean_coupon_history.log",
        rotation="1 day",
        retention="7 days",
        level="INFO",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        colorize=False
    )

def clean_invalid_records():
    """清理优惠券历史记录中的无效记录（没有对应产品的记录）"""
    db = SessionLocal()
    try:
        # 获取products表中所有asin
        valid_asins = {product.asin for product in db.query(Product.asin).all()}
        logger.info(f"数据库中有效的商品ASIN数量: {len(valid_asins)}")
        
        # 获取coupon_history表中的所有记录
        coupon_records = db.query(CouponHistory).all()
        total_records = len(coupon_records)
        logger.info(f"优惠券历史记录总数: {total_records}")
        
        # 找出无效的记录并删除
        invalid_records = []
        for record in coupon_records:
            if record.product_id not in valid_asins:
                invalid_records.append(record)
        
        # 批量删除无效记录
        if invalid_records:
            for record in invalid_records:
                db.delete(record)
            db.commit()
            logger.success(f"成功删除 {len(invalid_records)} 条无效的优惠券历史记录")
        else:
            logger.info("没有发现无效的优惠券历史记录")
        
        return len(invalid_records), total_records
    except Exception as e:
        db.rollback()
        logger.error(f"清理无效优惠券历史记录失败: {str(e)}")
        raise
    finally:
        db.close()

def clean_discount_source_records():
    """删除coupon_history表中product_id对应products表中source为discount的商品的记录"""
    db = SessionLocal()
    try:
        # 查询source为discount的商品ASIN列表
        discount_asins = {product.asin for product in db.query(Product.asin).filter(Product.source == 'discount').all()}
        logger.info(f"数据库中source为discount的商品ASIN数量: {len(discount_asins)}")
        
        if not discount_asins:
            logger.info("没有找到source为discount的商品")
            return 0, 0
        
        # 查询在coupon_history中存在的discount来源的商品记录数
        discount_records = db.query(CouponHistory).filter(
            CouponHistory.product_id.in_(discount_asins)
        ).all()
        
        deleted_count = len(discount_records)
        
        # 删除这些记录
        if discount_records:
            for record in discount_records:
                db.delete(record)
            db.commit()
            logger.success(f"成功删除 {deleted_count} 条source为discount的商品的优惠券历史记录")
        else:
            logger.info("没有找到需要删除的source为discount的商品的优惠券历史记录")
        
        # 返回删除的记录数和受影响的商品数
        affected_products = len(set(record.product_id for record in discount_records))
        return deleted_count, affected_products
    
    except Exception as e:
        db.rollback()
        logger.error(f"清理source为discount的商品的优惠券历史记录失败: {str(e)}")
        raise
    finally:
        db.close()

def clean_old_records(keep_records=3):
    """为每个商品只保留最新的N条记录，删除旧记录"""
    db = SessionLocal()
    try:
        # 获取所有商品ID
        product_ids = [pid[0] for pid in db.query(CouponHistory.product_id).distinct().all()]
        logger.info(f"在优惠券历史中发现 {len(product_ids)} 个不同的商品ASIN")
        
        # 统计数据
        total_deleted = 0
        affected_products = 0
        
        # 为每个商品处理历史记录
        for product_id in product_ids:
            # 获取该商品的所有历史记录，按创建时间降序排列
            records = db.query(CouponHistory).filter(
                CouponHistory.product_id == product_id
            ).order_by(CouponHistory.created_at.desc()).all()
            
            # 如果记录数超过保留数量，删除旧记录
            if len(records) > keep_records:
                # 保留的记录
                keep = records[:keep_records]
                # 要删除的记录
                to_delete = records[keep_records:]
                
                # 删除旧记录
                for record in to_delete:
                    db.delete(record)
                
                total_deleted += len(to_delete)
                affected_products += 1
                
                logger.debug(f"商品 {product_id}: 保留 {len(keep)} 条记录，删除 {len(to_delete)} 条旧记录")
        
        # 提交更改
        if total_deleted > 0:
            db.commit()
            logger.success(f"成功为 {affected_products} 个商品删除 {total_deleted} 条旧的优惠券历史记录")
        else:
            logger.info("没有需要删除的旧优惠券历史记录")
        
        return total_deleted, affected_products
    except Exception as e:
        db.rollback()
        logger.error(f"清理旧优惠券历史记录失败: {str(e)}")
        raise
    finally:
        db.close()

def optimize_database():
    """执行数据库优化"""
    db = SessionLocal()
    try:
        # 执行数据库优化（SQLite特有）
        db.execute(text("VACUUM"))
        db.commit()
        logger.info("数据库优化完成")
    except Exception as e:
        logger.error(f"数据库优化失败: {str(e)}")
    finally:
        db.close()

def clean_coupon_history():
    """清理优惠券历史记录"""
    # 第一步：清理无效记录（没有对应商品的记录）
    invalid_deleted, total_before = clean_invalid_records()
    
    # 第二步：清理source为discount的商品的记录
    discount_deleted, discount_affected = clean_discount_source_records()
    
    # 第三步：清理旧记录（只保留最新的三条）
    old_deleted, affected_products = clean_old_records(keep_records=3)
    
    # 第四步：优化数据库
    optimize_database()
    
    # 获取清理后的记录总数
    db = SessionLocal()
    try:
        total_after = db.query(CouponHistory).count()
    finally:
        db.close()
    
    return {
        'total_before': total_before,
        'invalid_deleted': invalid_deleted,
        'discount_deleted': discount_deleted,
        'discount_affected': discount_affected,
        'old_deleted': old_deleted,
        'affected_products': affected_products,
        'total_after': total_after
    }

def main():
    """主函数"""
    setup_logging()
    logger.info("开始清理优惠券历史记录")
    start_time = datetime.now()
    
    try:
        results = clean_coupon_history()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.success(
            f"清理完成! "
            f"总记录数(清理前): {results['total_before']}, "
            f"删除无效记录数: {results['invalid_deleted']}, "
            f"删除discount来源记录数: {results['discount_deleted']} (影响商品数: {results['discount_affected']}), "
            f"删除旧记录数: {results['old_deleted']} (影响商品数: {results['affected_products']}), "
            f"总记录数(清理后): {results['total_after']}, "
            f"耗时: {duration:.2f}秒"
        )
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 