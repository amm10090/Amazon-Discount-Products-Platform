"""
爬虫任务执行脚本

该脚本设计用于在独立进程中执行各种爬虫任务，与Streamlit环境完全隔离。
主要功能：
1. 接收命令行参数指定要执行的爬虫类型
2. 解析配置文件获取详细参数
3. 执行相应的爬虫任务
4. 记录执行结果和日志

使用方法：
python -m src.core.run_crawler --job-id <任务ID> --crawler-type <爬虫类型> --max-items <最大采集数量> [--config-file <配置文件路径>]
"""

import os
import sys
import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import traceback

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if project_root not in sys.path:
    sys.path.append(str(project_root))

# 导入日志配置
from src.utils.log_config import get_logger, LogConfig, LogContext

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='爬虫任务执行脚本')
    parser.add_argument('--job-id', type=str, required=True, help='任务ID')
    parser.add_argument('--crawler-type', type=str, required=True, help='爬虫类型：bestseller/coupon/all/update/cj')
    parser.add_argument('--max-items', type=int, required=True, help='最大采集数量')
    parser.add_argument('--config-file', type=str, help='配置文件路径')
    return parser.parse_args()

async def execute_task(job_id: str, crawler_type: str, max_items: int, config: Optional[Dict[str, Any]] = None):
    """执行爬虫任务
    
    Args:
        job_id: 任务ID
        crawler_type: 爬虫类型
        max_items: 最大采集数量
        config: 配置参数
        
    Returns:
        int: 采集到的商品数量
    """
    logger.info(f"开始执行任务 {job_id}，类型：{crawler_type}，目标数量：{max_items}")
    
    # 根据爬虫类型执行不同的任务
    if crawler_type == "update":
        # 执行商品更新任务
        from models.database import SessionLocal
        from src.core.product_updater import ProductUpdater, UpdateConfiguration
        
        # 解析更新器配置
        update_config = None
        if config and "updater_config" in config:
            logger.info(f"使用自定义更新器配置: {config['updater_config']}")
            updater_config = config["updater_config"]
            # 确保前端传入的max_items覆盖配置中的batch_size
            batch_size = max_items
            logger.info(f"使用前端设置的更新数量: {batch_size} (覆盖配置中的 {updater_config.get('batch_size', 500)})")
            
            update_config = UpdateConfiguration(
                urgent_priority_hours=updater_config.get('urgent_priority_hours', 1),
                high_priority_hours=updater_config.get('high_priority_hours', 6),
                medium_priority_hours=updater_config.get('medium_priority_hours', 24),
                low_priority_hours=updater_config.get('low_priority_hours', 72),
                very_low_priority_hours=updater_config.get('very_low_priority_hours', 168),
                batch_size=batch_size,  # 使用前端指定的数量
                max_retries=updater_config.get('max_retries', 3),
                retry_delay=updater_config.get('retry_delay', 2.0),
                update_category_info=updater_config.get('update_category_info', False),
                force_cj_check=updater_config.get('force_cj_check', False),
                parallel_requests=updater_config.get('parallel_requests', 5)
            )
        
        # 创建更新器实例
        updater = ProductUpdater(config=update_config)
        await updater.initialize_clients()
        
        # 执行更新，始终使用前端传入的max_items
        success_count, failed_count, deleted_count = await updater.run_scheduled_update(batch_size=max_items)
        
        logger.success(f"商品更新任务完成，成功更新 {success_count}/{success_count + failed_count} 个商品，删除 {deleted_count} 个商品")
        return success_count
    
    elif crawler_type == "cj":
        # 执行CJ爬虫任务
        from models.database import SessionLocal
        from src.core.cj_products_crawler import CJProductsCrawler
        
        # 获取数据库会话
        db = SessionLocal()
        try:
            # 创建CJ爬虫实例
            crawler = CJProductsCrawler()
            
            # 获取配置参数
            cj_config = config.get("cj_config", {}) if config else {}
            use_parallel = cj_config.get("use_parallel", True)
            workers = cj_config.get("workers", 3)
            use_random_cursor = cj_config.get("use_random_cursor", False)
            skip_existing = cj_config.get("skip_existing", True)
            filter_similar_variants = cj_config.get("filter_similar_variants", True)
            
            logger.info(f"CJ爬虫配置: 并行={use_parallel}, 工作进程={workers}, 随机游标={use_random_cursor}, 跳过已存在={skip_existing}")
            
            # 执行CJ爬虫
            if use_parallel:
                # 使用并行抓取
                logger.info(f"使用并行抓取模式，工作进程数: {workers}")
                success, fail, variants, coupon, discount = await crawler.fetch_all_products_parallel(
                    db=db,
                    max_items=max_items,
                    max_workers=workers,
                    skip_existing=skip_existing,
                    filter_similar_variants=filter_similar_variants
                )
            else:
                # 使用串行抓取
                logger.info("使用串行抓取模式")
                success, fail, variants, coupon, discount = await crawler.fetch_all_products(
                    db=db,
                    max_items=max_items,
                    use_random_cursor=use_random_cursor,
                    skip_existing=skip_existing,
                    use_persistent_cursor=True,
                    filter_similar_variants=filter_similar_variants
                )
                
            logger.success(f"CJ商品爬取完成，成功：{success}，失败：{fail}，优惠券：{coupon}，折扣：{discount}，变体：{variants}")
            return success
        finally:
            db.close()
    
    else:
        # 执行通用爬虫任务
        from src.core.collect_products import Config, crawl_bestseller_products, crawl_coupon_products
        from src.core.amazon_product_api import AmazonProductAPI
        
        # 检查必要的环境变量
        required_env_vars = ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"]
        for var in required_env_vars:
            if not os.getenv(var):
                raise ValueError(f"缺少必要的环境变量: {var}")
        
        # 从环境变量和配置文件获取配置参数
        crawler_config = config.get("crawler_config", {}) if config else {}
        headless = crawler_config.get("headless", os.getenv("CRAWLER_HEADLESS", "true").lower() == "true")
        timeout = crawler_config.get("timeout", int(os.getenv("CRAWLER_TIMEOUT", "30")))
        batch_size = crawler_config.get("batch_size", int(os.getenv("CRAWLER_BATCH_SIZE", "10")))
        
        crawler_conf = Config(
            max_items=max_items,
            batch_size=batch_size,
            timeout=timeout,
            headless=headless
        )
        
        logger.info(f"爬虫配置: max_items={crawler_conf.max_items}, batch_size={crawler_conf.batch_size}, "
                   f"timeout={crawler_conf.timeout}, headless={crawler_conf.headless}")
        
        # 初始化API客户端
        api = AmazonProductAPI(
            access_key=os.getenv("AMAZON_ACCESS_KEY"),
            secret_key=os.getenv("AMAZON_SECRET_KEY"),
            partner_tag=os.getenv("AMAZON_PARTNER_TAG")
        )
        
        if crawler_type == "bestseller":
            # 爬取畅销商品
            result = await crawl_bestseller_products(
                api,
                crawler_conf.max_items,
                crawler_conf.batch_size,
                crawler_conf.timeout,
                crawler_conf.headless
            )
            logger.success(f"畅销商品爬取完成，采集到 {result} 个商品")
            return result
        elif crawler_type == "coupon":
            # 爬取优惠券商品
            result = await crawl_coupon_products(
                api,
                crawler_conf.max_items,
                crawler_conf.batch_size,
                crawler_conf.timeout,
                crawler_conf.headless
            )
            logger.success(f"优惠券商品爬取完成，采集到 {result} 个商品")
            return result
        elif crawler_type == "all":
            # 爬取所有类型商品
            bestseller_items = await crawl_bestseller_products(
                api,
                crawler_conf.max_items,
                crawler_conf.batch_size,
                crawler_conf.timeout,
                crawler_conf.headless
            )
            logger.info(f"畅销商品爬取完成，采集到 {bestseller_items} 个商品")
            
            coupon_items = await crawl_coupon_products(
                api,
                crawler_conf.max_items,
                crawler_conf.batch_size,
                crawler_conf.timeout,
                crawler_conf.headless
            )
            logger.info(f"优惠券商品爬取完成，采集到 {coupon_items} 个商品")
            
            total_items = bestseller_items + coupon_items
            logger.success(f"全部商品爬取完成，总计采集到 {total_items} 个商品")
            return total_items
        else:
            raise ValueError(f"不支持的爬虫类型: {crawler_type}")

async def main():
    """主函数"""
    global logger
    
    # 解析命令行参数
    args = parse_arguments()
    
    # 初始化日志
    log_dir = Path(os.getenv("APP_LOG_DIR", str(project_root / "logs"))).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查环境变量，判断是否应该禁用颜色
    force_no_color = False
    if (os.getenv("COLORTERM") == "0" or 
        os.getenv("DISCOUNT_SCRAPER_LOG_COLOR_OUTPUT") == "false" or
        os.getenv("LOG_COLORS") == "false" or
        os.getenv("FORCE_COLOR") == "0" or
        os.getenv("TERM") == "dumb"):
        force_no_color = True
        print("检测到环境变量设置，强制禁用日志颜色")
    
    # 设置日志配置
    log_config = {
        "LOG_LEVEL": "INFO",
        "JSON_LOGS": False,
        "LOG_PATH": str(log_dir),
        "LOG_FILE": f"crawler_{args.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        "CONSOLE_LOGS": True,
        "ASYNC_LOGS": True,
        "ROTATION": "10 MB",
        "RETENTION": "5 days",
        "CONSOLE_LOG_FORMAT": (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[name]}</cyan> | "
            "<level>{message}</level>"
        ),
        "FILE_LOG_FORMAT": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[name]} | "
            "{message}"
        ),
        "COLORIZE_CONSOLE": not force_no_color,  # 根据环境变量决定是否使用颜色
        "COLORIZE_FILE": False  # 明确禁用文件日志的颜色
    }
    
    # 应用日志配置
    LogConfig(log_config)
    logger = get_logger(f"Crawler:{args.job_id}")
    
    if force_no_color:
        logger.info("已禁用日志颜色输出")
    
    # 加载配置文件
    config = None
    if args.config_file and os.path.exists(args.config_file):
        try:
            with open(args.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"已加载配置文件: {args.config_file}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
    
    try:
        # 执行爬虫任务
        with LogContext(job_id=args.job_id, crawler_type=args.crawler_type):
            logger.info(f"开始执行爬虫任务: ID={args.job_id}, 类型={args.crawler_type}, 最大数量={args.max_items}")
            
            # 记录开始时间
            start_time = datetime.now()
            
            # 执行任务
            result = await execute_task(args.job_id, args.crawler_type, args.max_items, config)
            
            # 记录结束时间和耗时
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.success(f"爬虫任务 {args.job_id} 完成! 处理数量: {result}, 耗时: {duration:.2f}秒")
            
        # 删除配置文件
        if args.config_file and os.path.exists(args.config_file):
            try:
                os.unlink(args.config_file)
                logger.debug(f"已删除临时配置文件: {args.config_file}")
            except Exception as e:
                logger.warning(f"删除临时配置文件失败: {str(e)}")
        
        # 正常退出
        sys.exit(0)
            
    except Exception as e:
        logger.error(f"爬虫任务执行失败: {str(e)}")
        logger.error(f"异常详情: {traceback.format_exc()}")
        # 异常退出
        sys.exit(1)

if __name__ == "__main__":
    # 执行主函数
    asyncio.run(main()) 