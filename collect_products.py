import os
import time
from datetime import datetime
from typing import List, Set
from amazon_bestseller import crawl_deals
from amazon_product_api import AmazonProductAPI
from models.database import init_db, SessionLocal
from models.product_service import ProductService
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def collect_products(
    max_items: int = None,
    batch_size: int = 10,
    timeout: int = 30,
    headless: bool = True
) -> None:
    """
    采集Amazon产品数据并存储到数据库
    
    Args:
        max_items: 要采集的最大商品数量，如果为None则从环境变量读取
        batch_size: 每批处理的ASIN数量（PA-API限制最多10个）
        timeout: 爬虫超时时间（秒）
        headless: 是否使用无头模式运行爬虫
    """
    # 从环境变量获取max_items
    if max_items is None:
        max_items = int(os.getenv("MAX_ITEMS", 100))
        
    print("\n" + "="*50)
    print(f"[{datetime.now()}] 开始数据采集任务")
    print(f"目标数量: {max_items}")
    print(f"批处理大小: {batch_size}")
    print("="*50 + "\n")
    
    try:
        # 初始化数据库
        print(f"[{datetime.now()}] 初始化数据库...")
        init_db()
        
        # 获取环境变量
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            raise ValueError("缺少必要的Amazon PA-API凭证，请检查环境变量设置")
        
        # 初始化PA-API客户端
        print(f"[{datetime.now()}] 初始化Amazon Product API客户端...")
        api = AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        
        # 爬取ASIN列表
        print(f"[{datetime.now()}] 开始爬取商品ASIN...")
        asins = crawl_deals(
            max_items=max_items,
            timeout=timeout,
            headless=headless
        )
        
        if not asins:
            print(f"[{datetime.now()}] ⚠️ 未获取到任何ASIN，任务终止")
            return
            
        print(f"[{datetime.now()}] ✓ 成功获取 {len(asins)} 个ASIN")
        
        # 分批处理ASIN
        total_processed = 0
        total_success = 0
        asin_list = list(asins)
        
        for i in range(0, len(asin_list), batch_size):
            batch_asins = asin_list[i:i + batch_size]
            print(f"\n[{datetime.now()}] 处理第 {i//batch_size + 1} 批 ({len(batch_asins)} 个ASIN)")
            
            try:
                # 获取产品详细信息
                products = api.get_products_by_asins(batch_asins)
                
                if products:
                    # 存储到数据库
                    with SessionLocal() as db:
                        saved_products = ProductService.bulk_create_or_update_products(db, products)
                        total_success += len(saved_products)
                        
                    print(f"[{datetime.now()}] ✓ 成功保存 {len(saved_products)} 个产品信息")
                else:
                    print(f"[{datetime.now()}] ⚠️ 未获取到产品信息")
                    
            except Exception as e:
                print(f"[{datetime.now()}] ❌ 处理批次时出错: {str(e)}")
                
            total_processed += len(batch_asins)
            print(f"[{datetime.now()}] 进度: {total_processed}/{len(asins)} ({total_processed/len(asins)*100:.1f}%)")
            
            # 添加延迟以避免API限制
            if i + batch_size < len(asin_list):
                time.sleep(1)  # 每批次间隔1秒
                
        print("\n" + "="*50)
        print("数据采集任务完成!")
        print(f"总处理ASIN数: {total_processed}")
        print(f"成功保存产品数: {total_success}")
        print(f"完成时间: {datetime.now()}")
        print("="*50)
        
    except Exception as e:
        print(f"\n[{datetime.now()}] ❌ 任务执行出错: {str(e)}")

if __name__ == "__main__":
    # 开始采集任务
    collect_products(
        batch_size=10,  # 每次查询10个ASIN
        timeout=30,     # 爬虫超时时间30秒
        headless=False   # 使用无头模式
    ) 