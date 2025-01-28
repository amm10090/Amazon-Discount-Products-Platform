import os
import time
import asyncio
from datetime import datetime
from typing import List, Set, Dict, Any
from amazon_bestseller import crawl_deals
from amazon_coupon_crawler import crawl_coupon_deals
from amazon_product_api import AmazonProductAPI
from models.database import init_db, SessionLocal
from models.product_service import ProductService
from dotenv import load_dotenv
import colorama
from colorama import Fore, Style

# 初始化colorama
colorama.init()

# 日志格式常量
LOG_INFO = f"{Fore.GREEN}[INFO]{Style.RESET_ALL}"
LOG_DEBUG = f"{Fore.BLUE}[DEBUG]{Style.RESET_ALL}"
LOG_WARNING = f"{Fore.YELLOW}[WARN]{Style.RESET_ALL}"
LOG_ERROR = f"{Fore.RED}[ERROR]{Style.RESET_ALL}"
LOG_SUCCESS = f"{Fore.GREEN}[✓]{Style.RESET_ALL}"

def log_message(level: str, message: str) -> None:
    """输出带时间戳的日志消息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level} {message}")

def log_info(message: str) -> None:
    log_message(LOG_INFO, message)

def log_debug(message: str) -> None:
    log_message(LOG_DEBUG, message)

def log_warning(message: str) -> None:
    log_message(LOG_WARNING, message)

def log_error(message: str) -> None:
    log_message(LOG_ERROR, message)

def log_success(message: str) -> None:
    log_message(LOG_SUCCESS, message)

def format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """生成进度条"""
    percentage = current / total
    filled = int(width * percentage)
    bar = '█' * filled + '░' * (width - filled)
    return f"{Fore.CYAN}[{bar}] {current}/{total} ({percentage*100:.1f}%){Style.RESET_ALL}"

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
        
        for i in range(0, len(asin_list), batch_size):
            batch_asins = asin_list[i:i + batch_size]
            saved_count = await process_products_batch(
                api, 
                batch_asins, 
                i // batch_size,
                total_batches
            )
            total_success += saved_count
            
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
        results = await crawl_coupon_deals(
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
        
        # 分批处理
        for i in range(0, len(asins), batch_size):
            batch_asins = asins[i:i + batch_size]
            batch_results = results[i:i + batch_size]
            
            # 获取产品详细信息并添加优惠券信息
            products = await api.get_products_by_asins(batch_asins)
            if products:
                # 将优惠券信息添加到产品数据中
                for product, result in zip(products, batch_results):
                    product['coupon_info'] = result['coupon']
                
                # 存储到数据库
                with SessionLocal() as db:
                    saved_products = ProductService.bulk_create_or_update_products(
                        db, 
                        products,
                        include_coupon=True
                    )
                    total_success += len(saved_products)
                    log_success(f"成功保存 {len(saved_products)} 个优惠券商品信息")
            
            if i + batch_size < len(asins):
                await asyncio.sleep(1)
                
        return total_success
        
    except Exception as e:
        log_error(f"优惠券商品爬取任务出错: {str(e)}")
        return 0

async def collect_products(
    max_items: int = None,
    batch_size: int = 10,
    timeout: int = 30,
    headless: bool = True
) -> None:
    """
    异步采集Amazon产品数据并存储到数据库
    
    Args:
        max_items: 每种类型要采集的最大商品数量
        batch_size: 每批处理的ASIN数量（PA-API限制最多10个）
        timeout: 爬虫超时时间（秒）
        headless: 是否使用无头模式运行爬虫
    """
    # 从环境变量获取max_items
    if max_items is None:
        max_items = int(os.getenv("MAX_ITEMS", 100))
    
    log_info("\n" + "="*50)
    log_info("开始数据采集任务")
    log_info(f"目标数量: 每类 {max_items} 个商品")
    log_info(f"批处理大小: {batch_size}")
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
        
        # 异步执行两个爬虫任务
        bestseller_task = crawl_bestseller_products(
            api, max_items, batch_size, timeout, headless
        )
        coupon_task = crawl_coupon_products(
            api, max_items, batch_size, timeout, headless
        )
        
        # 等待两个任务完成
        bestseller_count, coupon_count = await asyncio.gather(
            bestseller_task,
            coupon_task
        )
        
        # 输出统计信息
        log_info("\n" + "="*50)
        log_info("数据采集任务完成!")
        log_info(f"畅销商品: 成功保存 {bestseller_count} 个")
        log_info(f"优惠券商品: 成功保存 {coupon_count} 个")
        log_info(f"总计: {bestseller_count + coupon_count} 个商品")
        log_info(f"完成时间: {datetime.now()}")
        log_info("="*50)
        
    except Exception as e:
        log_error(f"任务执行出错: {str(e)}")

if __name__ == "__main__":
    # 运行异步任务
    asyncio.run(collect_products(
        batch_size=10,  # 每次查询10个ASIN
        timeout=30,     # 爬虫超时时间30秒
        headless=True   # 使用无头模式
    )) 