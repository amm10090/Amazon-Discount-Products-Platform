#!/usr/bin/env python3
"""
优惠券详情更新脚本

此脚本用于检查数据库中优惠券商品是否有到期日期和条款信息，如果没有则执行抓取。
可通过命令行参数或直接导入使用。

用法示例:
    # 更新所有需要补充信息的优惠券商品(默认最多50个)
    python update_coupon_details.py
    
    # 指定批量大小和线程数
    python update_coupon_details.py --batch-size 100 --threads 4
    
    # 只更新指定ASIN列表
    python update_coupon_details.py --asin-list "B0C9TZYNJP,B0C9TY3GRQ"
    
    # 显示调试信息
    python update_coupon_details.py --debug

可以定期通过计划任务执行此脚本，确保优惠券信息完整。
"""

import os
import sys
import argparse
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入必要的模块
from src.core.discount_scraper_mt import check_and_scrape_coupon_details, init_logger

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='优惠券详情更新工具')
    parser.add_argument('--batch-size', type=int, default=50, help='每批处理的商品数量，默认50')
    parser.add_argument('--threads', type=int, default=2, help='抓取线程数量，默认2')
    parser.add_argument('--no-headless', action='store_true', help='禁用无头模式')
    parser.add_argument('--min-delay', type=float, default=2.0, help='最小请求延迟(秒)')
    parser.add_argument('--max-delay', type=float, default=4.0, help='最大请求延迟(秒)')
    parser.add_argument('--asin', type=str, help='要处理的单个商品ASIN')
    parser.add_argument('--asin-list', type=str, help='要处理的多个商品ASIN列表，用逗号分隔')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    
    # 初始化日志
    logger = init_logger(
        log_level='DEBUG' if args.debug else 'INFO',
        log_to_console=True
    )
    
    # 处理ASIN列表
    specific_asins = None
    if args.asin:
        specific_asins = [args.asin]
        logger.info(f"将处理指定的单个ASIN: {args.asin}")
    elif args.asin_list:
        specific_asins = [asin.strip() for asin in args.asin_list.split(',')]
        logger.info(f"将处理指定的{len(specific_asins)}个ASIN")
    
    # 记录开始时间
    start_time = datetime.now()
    logger.info(f"开始执行优惠券详情更新，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 调用check_and_scrape_coupon_details函数
    processed_count, updated_count = check_and_scrape_coupon_details(
        asins=specific_asins,
        batch_size=args.batch_size,
        num_threads=args.threads,
        headless=not args.no_headless,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        debug=args.debug
    )
    
    # 计算耗时
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # 输出结果统计
    logger.info(f"优惠券详情更新完成，耗时: {duration:.1f}秒")
    logger.info(f"处理商品数: {processed_count}")
    logger.info(f"成功更新详情数: {updated_count}")
    logger.info(f"成功率: {(updated_count/processed_count*100) if processed_count > 0 else 0:.1f}%")
    
    return 0 if processed_count > 0 and updated_count > 0 else 1

if __name__ == "__main__":
    sys.exit(main()) 