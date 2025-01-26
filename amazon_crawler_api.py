from fastapi import FastAPI, HTTPException, BackgroundTasks
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import uvicorn
from amazon_bestseller import crawl_deals, save_results
import os
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse
from models.crawler import CrawlerRequest, CrawlerResponse, CrawlerResult
from models.product import ProductInfo
from pydantic import BaseModel
from amazon_product_api import AmazonProductAPI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 创建FastAPI应用
app = FastAPI(
    title="Amazon Data API",
    description="API for crawling Amazon deals and retrieving product information",
    version="1.0.0"
)

# 存储任务状态
tasks_status: Dict[str, Dict] = {}

# 产品API请求模型
class ProductRequest(BaseModel):
    asins: List[str]
    marketplace: Optional[str] = "www.amazon.com"

# 初始化AmazonProductAPI
def get_product_api(marketplace: str = "www.amazon.com") -> AmazonProductAPI:
    """获取AmazonProductAPI实例"""
    access_key = os.getenv("AMAZON_ACCESS_KEY")
    secret_key = os.getenv("AMAZON_SECRET_KEY")
    partner_tag = os.getenv("AMAZON_PARTNER_TAG")
    
    if not all([access_key, secret_key, partner_tag]):
        raise HTTPException(
            status_code=500,
            detail="缺少必要的API凭证配置"
        )
    
    return AmazonProductAPI(
        access_key=access_key,
        secret_key=secret_key,
        partner_tag=partner_tag,
        marketplace=marketplace
    )

async def crawl_task(task_id: str, params: CrawlerRequest):
    """后台爬虫任务"""
    try:
        start_time = datetime.now()
        
        # 创建输出目录
        output_dir = Path("crawler_results")
        output_dir.mkdir(exist_ok=True)
        
        # 执行爬虫
        asins = crawl_deals(
            max_items=params.max_items,
            timeout=params.timeout,
            headless=params.headless
        )
        
        # 保存结果
        output_file = output_dir / f"{task_id}.{params.output_format}"
        save_results(asins, str(output_file), params.output_format)
        
        # 更新任务状态
        duration = (datetime.now() - start_time).total_seconds()
        tasks_status[task_id] = {
            "status": "completed",
            "total_items": len(asins),
            "asins": list(asins),
            "duration": duration,
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        tasks_status[task_id] = {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now()
        }

@app.post("/api/crawl", response_model=CrawlerResponse)
async def start_crawler(
    params: CrawlerRequest,
    background_tasks: BackgroundTasks
):
    """启动爬虫任务"""
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 初始化任务状态
    tasks_status[task_id] = {
        "status": "running",
        "timestamp": datetime.now()
    }
    
    # 添加后台任务
    background_tasks.add_task(crawl_task, task_id, params)
    
    return CrawlerResponse(
        task_id=task_id,
        status="accepted",
        message="Task started successfully",
        timestamp=datetime.now()
    )

@app.get("/api/status/{task_id}", response_model=CrawlerResult)
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_info = tasks_status[task_id]
    
    if task_info["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Task failed: {task_info.get('error', 'Unknown error')}"
        )
        
    return CrawlerResult(
        task_id=task_id,
        status=task_info["status"],
        total_items=task_info.get("total_items", 0),
        asins=task_info.get("asins", []),
        duration=task_info.get("duration", 0),
        timestamp=task_info["timestamp"]
    )

@app.get("/api/download/{task_id}")
async def download_results(task_id: str):
    """下载爬虫结果"""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_info = tasks_status[task_id]
    if task_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")
        
    output_file = Path("crawler_results") / f"{task_id}.{task_info.get('output_format', 'json')}"
    if not output_file.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
        
    return FileResponse(
        path=output_file,
        filename=output_file.name,
        media_type="application/octet-stream"
    )

# 新增产品API相关端点
@app.post("/api/products", response_model=List[ProductInfo])
async def get_products(request: ProductRequest):
    """获取商品信息"""
    try:
        api = get_product_api(request.marketplace)
        products = api.get_products_by_asins(request.asins)
        
        if not products:
            raise HTTPException(
                status_code=404,
                detail="未找到商品信息"
            )
            
        return products
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取商品信息时出错: {str(e)}")

@app.post("/api/products/save")
async def save_products(request: ProductRequest, output_file: str):
    """获取并保存商品信息到文件"""
    try:
        api = get_product_api(request.marketplace)
        products = api.get_products_by_asins(request.asins)
        
        if not products:
            raise HTTPException(
                status_code=404,
                detail="未找到商品信息"
            )
        
        api.save_products_info(products, output_file)
        return {"status": "success", "message": f"商品信息已保存到: {output_file}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "amazon-data-api",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/cache/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    try:
        api = get_product_api()
        return api.cache_manager.get_cache_stats()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取缓存统计信息失败: {str(e)}"
        )

@app.post("/api/cache/clear")
async def clear_cache():
    """清理过期缓存"""
    try:
        api = get_product_api()
        api.cache_manager.clear_expired()
        return {"status": "success", "message": "过期缓存已清理"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"清理缓存失败: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run("amazon_crawler_api:app", host="localhost", port=8000, reload=True) 