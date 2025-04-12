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
from src.core.cj_api_client import CJAPIClient

# 初始化组件日志配置
def init_logger():
    """初始化日志配置"""
    collector_config = config_loader.get_component_config('collector')
    if collector_config:
        log_file = collector_config.get('file', 'logs/collector.log')
        set_log_config(
            log_level=collector_config.get('level', 'INFO'),
            log_file=log_file,
            max_file_size=10 * 1024 * 1024,  # 10MB
            backup_count=5,
            use_colors=True
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
    CJ = "cj"
    
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
    cj_client: CJAPIClient,
    batch_asins: List[str],
    batch_index: int,
    total_batches: int,
    coupon_info: Optional[Dict] = None,
    max_retries: int = 3,  # 最大重试次数
    retry_delay: float = 2.0  # 重试延迟（秒）
) -> int:
    """处理一批产品数据"""
    for retry in range(max_retries):
        try:
            log_progress(f"处理第 {batch_index + 1}/{total_batches} 批 ({len(batch_asins)} 个ASIN)")
            if retry > 0:
                log_info(f"第 {retry} 次重试...")
            
            # 首先检查CJ平台的可用性
            log_progress(f"正在检查CJ平台可用性: {batch_asins}")
            cj_availability = await cj_client.check_products_availability(batch_asins)
            available_count = sum(1 for v in cj_availability.values() if v)
            log_progress(f"CJ平台可用商品数量: {available_count}/{len(batch_asins)}")
            
            cj_asins = [asin for asin, available in cj_availability.items() if available]
            if available_count > 0:
                log_info(f"CJ平台可用商品: {cj_asins}")
            
            products = []
            try:
                # 获取PA-API产品详细信息
                log_progress("正在从PA-API获取商品信息...")
                products = await api.get_products_by_asins(batch_asins)
                if products:
                    log_success(f"成功获取 {len(products)} 个商品的PA-API数据")
            except Exception as e:
                if "429" in str(e):
                    log_warning("PA-API达到速率限制，跳过PA-API数据获取")
                    # 如果有CJ商品，我们仍然继续处理
                    if not cj_asins:
                        return 0  # 如果没有CJ商品，直接返回
                else:
                    raise  # 如果是其他错误，继续抛出
            
            # 如果有PA-API数据或CJ商品，继续处理
            if products or cj_asins:
                cj_processed = 0
                
                # 如果有CJ商品，创建基本的ProductInfo对象
                if cj_asins and not products:
                    from models.product import ProductInfo
                    # 为CJ商品创建基本的ProductInfo对象
                    for asin in cj_asins:
                        products.append(ProductInfo(
                            asin=asin,
                            title="",  # 将在CJ数据处理时更新
                            api_provider="cj-api"
                        ))
                
                # 处理所有产品
                for product in products:
                    if product.asin in cj_asins:
                        try:
                            log_progress(f"正在处理CJ商品数据: {product.asin}")
                            
                            # 获取CJ商品详情
                            cj_product = await cj_client.get_product_details(product.asin)
                            if cj_product and isinstance(cj_product, dict):
                                log_success(f"成功获取CJ商品详情: {product.asin}")
                                
                                # 生成CJ推广链接
                                cj_link = await cj_client.generate_product_link(product.asin)
                                log_success(f"成功生成CJ推广链接: {product.asin}")
                                
                                # 整合CJ数据到product对象
                                if not hasattr(product, 'offers') or not product.offers:
                                    product.offers = []
                                if not product.offers:
                                    from models.product import ProductOffer
                                    product.offers.append(ProductOffer(
                                        condition="New",  # 默认值
                                        price=0.0,       # 默认值
                                        currency="USD",   # 默认值
                                        availability="Available",  # 默认值
                                        merchant_name="Amazon"    # 默认值
                                    ))
                                
                                if product.offers and len(product.offers) > 0:
                                    main_offer = product.offers[0]
                                    
                                    # 添加佣金信息（CJ特有）
                                    commission = cj_product.get('commission')
                                    if isinstance(commission, str):
                                        # 移除百分号并转换为字符串
                                        main_offer.commission = commission.rstrip('%')
                                    elif isinstance(commission, (int, float)):
                                        main_offer.commission = str(commission)
                                    log_debug(f"CJ佣金信息: {product.asin} - {main_offer.commission}")
                                    
                                    # 如果CJ有优惠券信息，使用CJ的数据
                                    coupon_data = cj_product.get('coupon', {})
                                    if isinstance(coupon_data, dict):
                                        main_offer.coupon_type = coupon_data.get('type')
                                        coupon_value = coupon_data.get('value')
                                        if coupon_value is not None:
                                            main_offer.coupon_value = float(coupon_value)
                                        log_debug(f"CJ优惠券信息: {product.asin} - {main_offer.coupon_type}:{main_offer.coupon_value}")
                                    
                                    # 如果CJ有折扣信息，使用CJ的数据
                                    discount = cj_product.get('discount')
                                    if isinstance(discount, str):
                                        try:
                                            discount_value = float(discount.strip('%'))
                                            main_offer.savings_percentage = int(discount_value)
                                            if main_offer.price:
                                                main_offer.savings = (main_offer.price * discount_value) / 100
                                            log_debug(f"CJ折扣信息: {product.asin} - {main_offer.savings_percentage}%")
                                        except (ValueError, TypeError) as e:
                                            log_error(f"处理折扣信息时出错: {str(e)}")
                                
                                # 添加CJ推广链接到ProductInfo对象
                                product.cj_url = cj_link
                                product.api_provider = "cj-api"  # 设置API提供者为cj-api
                                cj_processed += 1
                                log_success(f"成功整合CJ数据: {product.asin}")
                        except Exception as e:
                            log_error(f"处理CJ数据时出错 (ASIN: {product.asin}): {str(e)}")
                    
                    # 如果有优惠券信息，添加到产品中
                    if coupon_info and product.asin in coupon_info:
                        if not hasattr(product, 'offers') or not product.offers:
                            from models.product import ProductOffer
                            product.offers = [ProductOffer()]
                        
                        if product.offers and len(product.offers) > 0:
                            main_offer = product.offers[0]
                            coupon_data = coupon_info[product.asin]
                            if isinstance(coupon_data, dict):
                                main_offer.coupon_type = coupon_data.get('type')
                                coupon_value = coupon_data.get('value')
                                if coupon_value is not None:
                                    main_offer.coupon_value = float(coupon_value)
                                log_debug(f"添加优惠券信息: {product.asin} - {main_offer.coupon_type}:{main_offer.coupon_value}")
                
                if cj_processed > 0:
                    log_success(f"成功处理 {cj_processed} 个CJ商品数据")
                
                # 存储到数据库
                if products:
                    log_progress("正在保存商品数据到数据库...")
                    with SessionLocal() as db:
                        # 根据每个商品的CJ可用性设置api_provider
                        for product in products:
                            if not hasattr(product, 'api_provider'):
                                product.api_provider = "cj-api" if product.asin in cj_asins else "pa-api"
                        
                        saved_products = ProductService.bulk_create_or_update_products(
                            db, 
                            products,
                            include_coupon=True,  # 包含优惠券数据
                            source="coupon" if coupon_info else "discount",  # 根据是否有优惠券信息决定来源类型
                            include_metadata=True  # 包含元数据
                        )
                        log_success(f"成功保存 {len(saved_products)} 个商品信息，其中包含 {cj_processed} 个CJ商品")
                        return len(saved_products)
            else:
                log_warning("未获取到任何产品信息")
                
            # 如果成功执行到这里，跳出重试循环
            break
                
        except Exception as e:
            if "429" not in str(e):  # 如果不是429错误才记录
                log_error(f"处理批次时出错: {str(e)}")
            if retry < max_retries - 1:  # 如果还有重试机会
                await asyncio.sleep(retry_delay * (retry + 1))  # 指数退避延迟
                continue
            return 0
    
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
        
        # 初始化CJ客户端
        cj_client = CJAPIClient()
        
        # 分批处理ASIN
        total_success = 0
        asin_list = list(asins)
        total_batches = (len(asin_list) + batch_size - 1) // batch_size
        
        # 使用异步上下文管理器确保会话正确关闭
        async with api:
            for i in range(0, len(asin_list), batch_size):
                batch_asins = asin_list[i:i + batch_size]
                success_count = await process_products_batch(
                    api,
                    cj_client,
                    batch_asins,
                    i // batch_size,
                    total_batches
                )
                total_success += success_count
                
                # 增加批次间的延迟
                if i + batch_size < len(asin_list):
                    await asyncio.sleep(5)  # 增加到5秒延迟
                
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
        
        # 初始化CJ客户端
        cj_client = CJAPIClient()
        
        # 提取ASIN列表和优惠券信息
        asins = []
        coupon_info = {}
        for item in results:
            asin = item['asin']
            asins.append(asin)
            if 'coupon' in item and item['coupon']:
                coupon_info[asin] = item['coupon']
        
        total_success = 0
        total_batches = (len(asins) + batch_size - 1) // batch_size
        
        # 使用异步上下文管理器
        async with api:
            # 分批处理
            for i in range(0, len(asins), batch_size):
                batch_asins = asins[i:i + batch_size]
                # 为每个批次提取相应的优惠券信息
                batch_coupon_info = {
                    asin: coupon_info[asin]
                    for asin in batch_asins
                    if asin in coupon_info
                }
                
                success_count = await process_products_batch(
                    api,
                    cj_client,
                    batch_asins,
                    i // batch_size,
                    total_batches,
                    batch_coupon_info  # 传递优惠券信息
                )
                total_success += success_count
                
                if i + batch_size < len(asins):
                    await asyncio.sleep(1)  # 避免API限制
                
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
    log_section("启动数据采集任务")
    log_info("任务配置:")
    log_info(f"  • 爬虫类型: {[t.value for t in config.crawler_types]}")
    log_info(f"  • 目标数量: 每类 {config.max_items} 个商品")
    log_info(f"  • 批处理大小: {config.batch_size} 个商品/批次")
    log_info(f"  • 超时时间: {config.timeout} 秒")
    log_info(f"  • 无头模式: {'是' if config.headless else '否'}")
    
    try:
        # 初始化数据库
        log_progress("正在初始化数据库...")
        init_db()
        log_success("数据库初始化完成")
        
        # 获取环境变量
        log_progress("正在验证API凭证...")
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            log_error("缺少必要的Amazon PA-API凭证")
            raise ValueError("请检查环境变量设置: AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG")
        
        # 初始化PA-API客户端
        log_progress("正在初始化Amazon Product API客户端...")
        api = AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        log_success("API客户端初始化完成")
        
        # 准备要运行的爬虫任务
        tasks = []
        run_all = CrawlerType.ALL in config.crawler_types
        
        log_section("准备爬虫任务")
        if run_all or CrawlerType.BESTSELLER in config.crawler_types:
            log_info("添加畅销商品爬虫任务")
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
            log_info("添加优惠券商品爬虫任务")
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
        log_section("开始执行爬虫任务")
        results = await asyncio.gather(*tasks)
        
        # 输出统计信息
        log_section("任务完成统计")
        
        if len(results) == 2:
            bestseller_count, coupon_count = results
            log_success(f"采集结果:")
            log_success(f"  • 畅销商品: {bestseller_count} 个")
            log_success(f"  • 优惠券商品: {coupon_count} 个")
            log_success(f"  • 总计: {sum(results)} 个商品")
        elif len(results) == 1:
            count = results[0]
            crawler_type = "畅销商品" if CrawlerType.BESTSELLER in config.crawler_types else "优惠券商品"
            log_success(f"采集结果:")
            log_success(f"  • {crawler_type}: {count} 个")
            
        log_success(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        log_error(f"任务执行失败: {str(e)}")
        raise

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