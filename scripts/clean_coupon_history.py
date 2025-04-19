#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理无效的优惠券历史记录

该脚本用于清理coupon_history表中的无效记录：
- 检查coupon_history表中的product_id字段
- 如果在products表中找不到对应的asin，则删除该记录
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import text

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

def clean_coupon_history():
    """清理优惠券历史记录中的无效记录"""
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
            
        # 执行数据库优化（SQLite特有）
        db.execute(text("VACUUM"))
        db.commit()
        logger.info("数据库优化完成")
        
        return len(invalid_records), total_records
    except Exception as e:
        db.rollback()
        logger.error(f"清理优惠券历史记录失败: {str(e)}")
        raise
    finally:
        db.close()

def main():
    """主函数"""
    setup_logging()
    logger.info("开始清理无效的优惠券历史记录")
    start_time = datetime.now()
    
    try:
        deleted_count, total_count = clean_coupon_history()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.success(
            f"清理完成! "
            f"总记录数: {total_count}, "
            f"删除记录数: {deleted_count}, "
            f"耗时: {duration:.2f}秒"
        )
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 