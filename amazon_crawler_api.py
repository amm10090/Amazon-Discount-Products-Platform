from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Path, Depends
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
from sqlalchemy.orm import Session
from models.database import SessionLocal, init_db
from models.product_service import ProductService
from enum import Enum
from models.scheduler import SchedulerManager
from models.scheduler_models import JobConfig, JobStatus, SchedulerStatus, JobHistory
import pytz

# 加载环境变量
load_dotenv()

# 初始化数据库
init_db()

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

# 时区更新请求模型
class TimezoneUpdate(BaseModel):
    timezone: str

# 排序字段枚举
class SortField(str, Enum):
    price = "price"
    discount = "discount"
    timestamp = "timestamp"

# 排序方向枚举
class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

# 数据库会话依赖
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass  # 忽略关闭时的错误

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

@app.get("/api/products/list", response_model=List[ProductInfo])
async def list_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    sort_by: Optional[SortField] = Query(None, description="排序字段"),
    sort_order: SortOrder = Query(SortOrder.desc, description="排序方向"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品")
):
    """
    获取产品列表，支持分页、价格范围、折扣率筛选和排序
    """
    try:
        products = ProductService.list_products(
            db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only
        )
        return products
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取产品列表失败: {str(e)}"
        )

@app.get("/api/products/stats")
async def get_products_stats(db: Session = Depends(get_db)):
    """
    获取产品数据统计信息
    """
    try:
        stats = ProductService.get_stats(db)
        return {
            "total_products": stats["total_products"],
            "avg_price": stats["avg_price"],
            "avg_discount": stats["avg_discount"],
            "prime_products": stats["prime_products"],
            "last_update": stats["last_update"],
            "price_range": {
                "min": stats["min_price"],
                "max": stats["max_price"]
            },
            "discount_range": {
                "min": stats["min_discount"],
                "max": stats["max_discount"]
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取统计信息失败: {str(e)}"
        )


@app.get("/api/products/{asin}", response_model=ProductInfo)
async def get_product(
    asin: str = Path(title="Product ASIN", description="产品ASIN", min_length=10, max_length=10),
    db: Session = Depends(get_db)
):
    """
    根据ASIN获取单个产品详情
    """
    try:
        product = ProductService.get_product_by_asin(db, asin)
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"未找到ASIN为 {asin} 的产品"
            )
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取产品信息失败: {str(e)}"
        )

# 调度器相关端点
@app.post("/api/scheduler/jobs")
async def add_job(job_config: JobConfig):
    """添加新的定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.add_job(job_config.dict())
        return {"status": "success", "message": "任务添加成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/scheduler/jobs", response_model=List[JobStatus])
async def list_jobs():
    """获取所有定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        return scheduler_manager.get_jobs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/scheduler/jobs/{job_id}")
async def delete_job(job_id: str):
    """删除定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.remove_job(job_id)
        return {"status": "success", "message": "任务删除成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/scheduler/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """暂停定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.pause_job(job_id)
        return {"status": "success", "message": "任务已暂停"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/scheduler/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """恢复定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.resume_job(job_id)
        return {"status": "success", "message": "任务已恢复"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/scheduler/jobs/{job_id}/history", response_model=List[JobHistory])
async def get_job_history(job_id: str):
    """获取任务执行历史"""
    try:
        scheduler_manager = SchedulerManager()
        return scheduler_manager.get_job_history(job_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/scheduler/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """获取调度器状态"""
    try:
        scheduler_manager = SchedulerManager()
        return scheduler_manager.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/start")
async def start_scheduler():
    """启动调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.start()
        return {"status": "success", "message": "调度器已启动"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/stop")
async def stop_scheduler():
    """停止调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.stop()
        return {"status": "success", "message": "调度器已停止"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/reload")
async def reload_scheduler():
    """重新加载调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.reload()
        return {"status": "success", "message": "调度器已重新加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/timezone")
async def update_timezone(timezone_update: TimezoneUpdate):
    """更新调度器时区
    
    Args:
        timezone_update: 包含新时区的请求体
        
    Returns:
        Dict: 更新结果
    """
    try:
        # 验证时区是否有效
        pytz.timezone(timezone_update.timezone)
        
        # 更新调度器时区
        scheduler_manager = SchedulerManager()
        if scheduler_manager.set_timezone(timezone_update.timezone):
            return {"message": "Timezone updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update timezone")
    except pytz.exceptions.UnknownTimeZoneError:
        raise HTTPException(status_code=400, detail="Invalid timezone")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    # 确保数据库表已创建
    init_db()
    print("数据库初始化完成")

if __name__ == "__main__":
    print("请使用以下命令启动服务：")
    print("开发模式（支持热更新）: python dev.py")
    print("生产模式: uvicorn amazon_crawler_api:app --host localhost --port 8000") 