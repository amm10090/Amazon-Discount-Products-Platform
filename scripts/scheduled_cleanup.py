#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
定时清理脚本

定期清理没有优惠的商品，可以作为计划任务运行。
根据不同的策略清理不同来源和创建时间的商品。
"""

import sys
import os
import time
import argparse
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from sqlalchemy.orm import Session
from models.database import SessionLocal
from models.product_service import ProductService
from src.utils.log_config import get_logger, LogContext

# 清理策略配置
CLEANUP_STRATEGIES = [
    # 删除3天前创建的PA-API无优惠商品
    {
        "name": "过期PA-API商品",
        "api_provider": "pa-api",
        "min_days_old": 3,
        "max_days_old": None,
        "min_price": None,
        "max_price": None,
        "limit": 1000,
    },
    # 删除7天前创建的CJ-API无优惠商品
    {
        "name": "过期CJ-API商品",
        "api_provider": "cj-api",
        "min_days_old": 7,
        "max_days_old": None,
        "min_price": None,
        "max_price": None,
        "limit": 1000,
    },
    # 删除价格较低的无优惠商品
    {
        "name": "低价无优惠商品",
        "api_provider": None,
        "min_days_old": 1,
        "max_days_old": None,
        "min_price": None,
        "max_price": 10.0,  # 10美元以下的商品
        "limit": 500,
    },
    # 删除价格较高的无优惠商品
    {
        "name": "高价无优惠商品",
        "api_provider": None,
        "min_days_old": 14,  # 给高价商品更长的保留期
        "max_days_old": None,
        "min_price": 100.0,  # 100美元以上的商品
        "max_price": None,
        "limit": 200,
    }
]

def run_cleanup_strategy(
    db: Session, 
    strategy: Dict[str, Any], 
    dry_run: bool = False,
    logger = None
) -> Dict[str, Any]:
    """
    执行单个清理策略
    
    Args:
        db: 数据库会话
        strategy: 清理策略配置
        dry_run: 是否为模拟模式
        logger: 日志记录器
        
    Returns:
        Dict: 清理结果
    """
    strategy_name = strategy.get("name", "未命名策略")
    
    if logger:
        logger.info(f"执行清理策略: {strategy_name}")
        logger.info(f"  参数: API提供商={strategy.get('api_provider', '所有')}, " +
                   f"最少天数={strategy.get('min_days_old', 0)}, " +
                   f"最多天数={strategy.get('max_days_old', '不限')}, " +
                   f"最低价格={strategy.get('min_price', '不限')}, " +
                   f"最高价格={strategy.get('max_price', '不限')}, " +
                   f"数量限制={strategy.get('limit', '不限')}")
    
    result = ProductService.remove_products_without_discount(
        db=db,
        dry_run=dry_run,
        min_days_old=strategy.get("min_days_old", 0),
        max_days_old=strategy.get("max_days_old"),
        api_provider=strategy.get("api_provider"),
        min_price=strategy.get("min_price"),
        max_price=strategy.get("max_price"),
        limit=strategy.get("limit")
    )
    
    total_found = result.get("total_found", 0)
    
    if logger:
        if dry_run:
            logger.info(f"  找到 {total_found} 个符合条件的商品（模拟模式，未删除）")
        else:
            deleted = result.get("deleted", 0)
            failed = result.get("failed", 0)
            logger.info(f"  删除结果: 成功={deleted}/{total_found}, 失败={failed}")
    
    return {
        "strategy": strategy_name,
        "result": result
    }

def main():
    """主函数"""
    # 创建日志记录器
    logger = get_logger("ScheduledCleanup")
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='定时清理没有优惠的商品')
    parser.add_argument('--dry-run', action='store_true', 
                      help='模拟执行但不实际删除，用于测试')
    parser.add_argument('--strategies', type=str, 
                      help='要执行的策略名称，用逗号分隔，不指定则执行所有策略')
    parser.add_argument('--list', action='store_true',
                      help='列出所有可用的清理策略')
    
    args = parser.parse_args()
    
    # 如果是列出策略模式，显示所有可用的策略
    if args.list:
        logger.info("可用的清理策略:")
        for i, strategy in enumerate(CLEANUP_STRATEGIES):
            logger.info(f"  {i+1}. {strategy['name']}")
            logger.info(f"     - API提供商: {strategy.get('api_provider', '所有')}")
            logger.info(f"     - 最少天数: {strategy.get('min_days_old', 0)}")
            logger.info(f"     - 最多天数: {strategy.get('max_days_old', '不限')}")
            logger.info(f"     - 价格范围: {strategy.get('min_price', '不限')} - {strategy.get('max_price', '不限')}")
            logger.info(f"     - 数量限制: {strategy.get('limit', '不限')}")
        return
    
    # 确定要执行的策略
    if args.strategies:
        strategy_names = [name.strip() for name in args.strategies.split(',')]
        selected_strategies = [s for s in CLEANUP_STRATEGIES if s["name"] in strategy_names]
        
        if not selected_strategies:
            logger.error(f"未找到指定的策略: {args.strategies}，使用 --list 查看所有可用策略")
            return
            
        logger.info(f"将执行 {len(selected_strategies)}/{len(strategy_names)} 个指定的策略")
    else:
        selected_strategies = CLEANUP_STRATEGIES
        logger.info(f"将执行所有 {len(selected_strategies)} 个策略")
    
    with LogContext(dry_run=args.dry_run):
        start_time = time.time()
        logger.info(f"开始{'模拟' if args.dry_run else ''}清理没有优惠的商品: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 创建数据库会话
        db = SessionLocal()
        
        try:
            # 执行每个策略
            results = []
            for strategy in selected_strategies:
                strategy_start = time.time()
                
                result = run_cleanup_strategy(
                    db=db, 
                    strategy=strategy,
                    dry_run=args.dry_run,
                    logger=logger
                )
                
                strategy_end = time.time()
                result["duration"] = round(strategy_end - strategy_start, 2)
                results.append(result)
                
                # 添加短暂延迟，避免连续操作对数据库压力过大
                time.sleep(1)
            
            # 输出汇总信息
            total_found = sum(r["result"].get("total_found", 0) for r in results)
            if not args.dry_run:
                total_deleted = sum(r["result"].get("deleted", 0) for r in results)
                total_failed = sum(r["result"].get("failed", 0) for r in results)
                
                logger.info(f"清理完成: 共找到 {total_found} 个商品，成功删除 {total_deleted}，失败 {total_failed}")
            else:
                logger.info(f"模拟清理完成: 共找到 {total_found} 个可删除商品")
            
            # 输出每个策略的详细结果
            logger.info("各策略执行结果:")
            for result in results:
                strategy_name = result["strategy"]
                total = result["result"].get("total_found", 0)
                duration = result["duration"]
                
                if args.dry_run:
                    logger.info(f"  - {strategy_name}: 找到 {total} 个商品，耗时 {duration}秒")
                else:
                    deleted = result["result"].get("deleted", 0)
                    failed = result["result"].get("failed", 0)
                    logger.info(f"  - {strategy_name}: 找到 {total} 个商品，删除 {deleted}，失败 {failed}，耗时 {duration}秒")
            
        except Exception as e:
            logger.error(f"执行清理任务时出错: {str(e)}")
            
        finally:
            db.close()
            
        end_time = time.time()
        logger.info(f"清理任务完成，总耗时: {round(end_time - start_time, 2)}秒")

if __name__ == "__main__":
    main() 