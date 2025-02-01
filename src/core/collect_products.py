import os
import time
import asyncio
import argparse
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Set, Dict, Any, Optional
from enum import Enum
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
from src.core.amazon_bestseller import crawl_deals
from src.core.amazon_coupon_crawler import crawl_coupon_deals
from src.core.amazon_product_api import AmazonProductAPI
from models.database import init_db, SessionLocal
from models.product_service import ProductService
from dotenv import load_dotenv
from src.utils.logger_manager import (
    log_info, log_debug, log_warning, 
    log_error, log_success, log_progress,
    log_section, set_log_config
)
from src.utils.config_loader import config_loader

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    collector_config = config_loader.get_component_config('collector')
    if collector_config:
        set_log_config(
            log_to_file=True,
            log_dir=os.path.dirname(collector_config.get('file', 'logs/collector.log')),
            max_file_size=10 * 1024 * 1024,  # 10MB
            backup_count=5,
            use_colors=True,
            buffer_size=1000,
            flush_interval=5
        )
        
        # 设置环境变量来控制日志级别
        os.environ['DEBUG_LEVEL'] = collector_config.get('level', 'INFO')

# 调用初始化
init_logger()

class CrawlerType(Enum):
    """爬虫类型枚举"""
    BESTSELLER = "bestseller"
    COUPON = "coupon"
    ALL = "all"
    
    @classmethod
    def from_str(cls, value: str) -> "CrawlerType":
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"不支持的爬虫类型: {value}")

class Config:
    """配置类"""
    def __init__(self, **kwargs):
        self.max_items = kwargs.get("max_items", 100)
        self.batch_size = kwargs.get("batch_size", 10)
        self.timeout = kwargs.get("timeout", 30)
        self.headless = kwargs.get("headless", True)
        self.crawler_types = kwargs.get("crawler_types", [CrawlerType.ALL])
        
    @classmethod
    def from_file(cls, config_path: str) -> "Config":
        """从YAML配置文件加载配置"""
        log_info(f"尝试加载配置文件: {config_path}")
        
        if not os.path.exists(config_path):
            log_warning(f"配置文件不存在: {config_path}，将使用默认配置")
            return cls()
            
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
                
            if not config_data:
                log_warning("配置文件为空，将使用默认配置")
                return cls()
                
            log_debug(f"加载的配置内容: {config_data}")
                
            crawler_types = []
            if "crawler_types" in config_data:
                types = config_data["crawler_types"]
                if isinstance(types, str):
                    crawler_types = [CrawlerType.from_str(types)]
                elif isinstance(types, list):
                    crawler_types = [CrawlerType.from_str(t) for t in types]
                    
            config = cls(
                max_items=config_data.get("max_items", 100),
                batch_size=config_data.get("batch_size", 10),
                timeout=config_data.get("timeout", 30),
                headless=config_data.get("headless", True),
                crawler_types=crawler_types or [CrawlerType.ALL]
            )
            
            log_success(f"成功加载配置: {config.__dict__}")
            return config
            
        except Exception as e:
            log_error(f"加载配置文件出错: {str(e)}")
            return cls()
        
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """从命令行参数加载配置"""
        crawler_types = []
        if args.crawler_type:
            crawler_types = [CrawlerType.from_str(args.crawler_type)]
            
        return cls(
            max_items=args.max_items,
            batch_size=args.batch_size,
            timeout=args.timeout,
            headless=not args.no_headless,
            crawler_types=crawler_types or [CrawlerType.ALL]
        )

async def process_products_batch(
    api: AmazonProductAPI,
    batch_asins: List[str],
    batch_index: int,
    total_batches: int
) -> int:
    """处理一批产品数据"""
    try:
        log_info(f"处理第 {batch_index + 1}/{total_batches} 批 ({len(batch_asins)} 个ASIN)")
        
        # 获取产品详细信息
        products = await api.get_products_by_asins(batch_asins)
        
        if products:
            # 存储到数据库
            with SessionLocal() as db:
                saved_products = ProductService.bulk_create_or_update_products(db, products)
                log_success(f"成功保存 {len(saved_products)} 个产品信息")
                return len(saved_products)
        else:
            log_warning("未获取到产品信息")
            return 0
            
    except Exception as e:
        log_error(f"处理批次时出错: {str(e)}")
        return 0

async def crawl_bestseller_products(
    api: AmazonProductAPI,
    max_items: int,
    batch_size: int,
    timeout: int,
    headless: bool
) -> int:
    """爬取畅销商品数据"""
    try:
        log_info("开始爬取畅销商品ASIN...")
        asins = await crawl_deals(
            max_items=max_items,
            timeout=timeout,
            headless=headless
        )
        
        if not asins:
            log_warning("未获取到任何畅销商品ASIN")
            return 0
            
        log_success(f"成功获取 {len(asins)} 个畅销商品ASIN")
        
        # 分批处理ASIN
        total_success = 0
        asin_list = list(asins)
        total_batches = (len(asin_list) + batch_size - 1) // batch_size
        
        # 使用异步上下文管理器确保会话正确关闭
        async with api:
            for i in range(0, len(asin_list), batch_size):
                batch_asins = asin_list[i:i + batch_size]
                # 获取产品详细信息
                products = await api.get_products_by_asins(batch_asins)
                if products:
                    # 存储到数据库
                    with SessionLocal() as db:
                        saved_products = ProductService.bulk_create_or_update_products(
                            db, 
                            products,
                            source="bestseller",  # 数据来源渠道
                            api_provider="pa-api"  # API提供者
                        )
                        total_success += len(saved_products)
                        log_success(f"成功保存 {len(saved_products)} 个产品信息")
                
                if i + batch_size < len(asin_list):
                    await asyncio.sleep(1)  # 避免API限制
                
        return total_success
        
    except Exception as e:
        log_error(f"畅销商品爬取任务出错: {str(e)}")
        return 0

async def crawl_coupon_products(
    api: AmazonProductAPI,
    max_items: int,
    batch_size: int,
    timeout: int,
    headless: bool
) -> int:
    """爬取优惠券商品数据"""
    try:
        log_info("开始爬取优惠券商品...")
        results, stats = await crawl_coupon_deals(
            max_items=max_items,
            timeout=timeout,
            headless=headless
        )
        
        if not results:
            log_warning("未获取到任何优惠券商品")
            return 0
            
        log_success(f"成功获取 {len(results)} 个优惠券商品")
        
        # 提取ASIN列表
        asins = [item['asin'] for item in results]
        total_success = 0
        total_batches = (len(asins) + batch_size - 1) // batch_size
        
        # 使用异步上下文管理器
        async with api:
            # 分批处理
            for i in range(0, len(asins), batch_size):
                batch = results[i:i + batch_size]
                batch_asins = [item['asin'] for item in batch]
                
                # 获取产品详细信息并添加优惠券信息
                products = await api.get_products_by_asins(batch_asins)
                if products:
                    # 将优惠券信息添加到产品数据中
                    for product, result in zip(products, batch):
                        if 'coupon' in result and result['coupon']:
                            coupon_info = result['coupon']
                            # 验证优惠券信息格式
                            if isinstance(coupon_info, dict) and 'type' in coupon_info and 'value' in coupon_info:
                                # 将优惠券信息添加到第一个offer中
                                if product.offers:
                                    product.offers[0].coupon_type = coupon_info['type']
                                    product.offers[0].coupon_value = float(coupon_info['value'])
                    
                    # 存储到数据库
                    with SessionLocal() as db:
                        saved_products = ProductService.bulk_create_or_update_products(
                            db, 
                            products,
                            include_coupon=True,
                            source="coupon",  # 数据来源渠道
                            api_provider="pa-api"  # API提供者
                        )
                        total_success += len(saved_products)
                        log_success(f"成功保存 {len(saved_products)} 个优惠券商品信息")
                
                if i + batch_size < len(asins):
                    await asyncio.sleep(1)
                    
        return total_success
        
    except Exception as e:
        log_error(f"优惠券商品爬取任务出错: {str(e)}")
        return 0

async def collect_products(config: Config) -> None:
    """
    异步采集Amazon产品数据并存储到数据库
    
    Args:
        config: 配置对象，包含所有运行参数
    """
    log_info("\n" + "="*50)
    log_info("开始数据采集任务")
    log_info(f"运行爬虫类型: {[t.value for t in config.crawler_types]}")
    log_info(f"目标数量: 每类 {config.max_items} 个商品")
    log_info(f"批处理大小: {config.batch_size}")
    log_info("="*50 + "\n")
    
    try:
        # 初始化数据库
        log_info("初始化数据库...")
        init_db()
        
        # 获取环境变量
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            raise ValueError("缺少必要的Amazon PA-API凭证，请检查环境变量设置")
        
        # 初始化PA-API客户端
        log_info("初始化Amazon Product API客户端...")
        api = AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        
        # 准备要运行的爬虫任务
        tasks = []
        run_all = CrawlerType.ALL in config.crawler_types
        
        if run_all or CrawlerType.BESTSELLER in config.crawler_types:
            tasks.append(
                crawl_bestseller_products(
                    api, 
                    config.max_items, 
                    config.batch_size, 
                    config.timeout, 
                    config.headless
                )
            )
            
        if run_all or CrawlerType.COUPON in config.crawler_types:
            tasks.append(
                crawl_coupon_products(
                    api, 
                    config.max_items, 
                    config.batch_size, 
                    config.timeout, 
                    config.headless
                )
            )
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 输出统计信息
        log_info("\n" + "="*50)
        log_info("数据采集任务完成!")
        
        if len(results) == 2:
            bestseller_count, coupon_count = results
            log_info(f"畅销商品: 成功保存 {bestseller_count} 个")
            log_info(f"优惠券商品: 成功保存 {coupon_count} 个")
            log_info(f"总计: {sum(results)} 个商品")
        elif len(results) == 1:
            count = results[0]
            crawler_type = "畅销商品" if CrawlerType.BESTSELLER in config.crawler_types else "优惠券商品"
            log_info(f"{crawler_type}: 成功保存 {count} 个")
            
        log_info(f"完成时间: {datetime.now()}")
        log_info("="*50)
        
    except Exception as e:
        log_error(f"任务执行出错: {str(e)}")

def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Amazon商品数据采集工具")
    
    parser.add_argument(
        "--config",
        type=str,
        help="YAML配置文件路径"
    )
    
    parser.add_argument(
        "--crawler-type",
        type=str,
        choices=["bestseller", "coupon", "all"],
        help="要运行的爬虫类型"
    )
    
    parser.add_argument(
        "--max-items",
        type=int,
        default=100,
        help="每类要采集的最大商品数量"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="每批处理的ASIN数量"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="爬虫超时时间(秒)"
    )
    
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="禁用无头模式"
    )
    
    return parser.parse_args()

if __name__ == "__main__":
    # 加载环境变量
    load_dotenv()
    
    # 解析命令行参数
    args = parse_args()
    
    # 优先使用配置文件
    if args.config:
        config = Config.from_file(args.config)
    else:
        config = Config.from_args(args)
    
    # 运行异步任务
    asyncio.run(collect_products(config)) 