"""
Amazon爬虫和产品API FastAPI服务

这个模块提供了一个FastAPI应用，用于：
1. 爬取Amazon商品信息
2. 管理产品数据
3. 调度定时任务
4. 提供RESTful API接口

主要功能：
- 爬虫任务管理
- 产品信息查询和管理
- 定时任务调度
- 缓存管理
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Path, Depends
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import uvicorn
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from ..amazon_bestseller import crawl_deals, save_results
import os
from fastapi.responses import FileResponse, JSONResponse
from models.crawler import CrawlerRequest, CrawlerResponse, CrawlerResult
from models.product import ProductInfo
from pydantic import BaseModel, Field
from ..amazon_product_api import AmazonProductAPI
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from models.database import SessionLocal, init_db
from models.product_service import ProductService
from enum import Enum
from models.scheduler import SchedulerManager
from models.scheduler_models import JobConfig, JobStatus, SchedulerStatus, JobHistory
import pytz
import logging

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

# 存储任务状态的字典
tasks_status: Dict[str, Dict] = {}

logger = logging.getLogger(__name__)

class BatchDeleteRequest(BaseModel):
    """批量删除请求模型"""
    asins: List[str] = Field(..., description="要删除的商品ASIN列表")

class ProductRequest(BaseModel):
    """
    产品API请求模型
    
    属性:
        asins: ASIN列表
        marketplace: 亚马逊市场域名，默认为美国站
    """
    asins: List[str]
    marketplace: Optional[str] = "www.amazon.com"

class TimezoneUpdate(BaseModel):
    """
    时区更新请求模型
    
    属性:
        timezone: 新的时区字符串
    """
    timezone: str

class SortField(str, Enum):
    """
    排序字段枚举
    
    可选值:
        price: 按价格排序
        discount: 按折扣排序
        timestamp: 按时间戳排序
    """
    price = "price"
    discount = "discount"
    timestamp = "timestamp"

class SortOrder(str, Enum):
    """
    排序方向枚举
    
    可选值:
        asc: 升序
        desc: 降序
    """
    asc = "asc"
    desc = "desc"

def get_db():
    """
    数据库会话依赖函数
    
    用于FastAPI依赖注入，确保每个请求都有独立的数据库会话，
    并在请求结束后正确关闭会话
    
    Yields:
        Session: SQLAlchemy会话对象
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass

def get_product_api(marketplace: str = "www.amazon.com") -> AmazonProductAPI:
    """
    获取AmazonProductAPI实例
    
    Args:
        marketplace: 亚马逊市场域名，默认为美国站
        
    Returns:
        AmazonProductAPI: API实例
        
    Raises:
        HTTPException: 当缺少必要的API凭证时抛出
    """
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
    """
    后台爬虫任务
    
    Args:
        task_id: 任务ID
        params: 爬虫请求参数
        
    执行爬虫任务并更新任务状态。任务完成后，结果将保存到文件系统。
    """
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

# 系统状态相关API
@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "amazon-data-api",
        "timestamp": datetime.now().isoformat()
    }

# 爬虫任务相关API
@app.post("/api/crawl", response_model=CrawlerResponse)
async def start_crawler(params: CrawlerRequest, background_tasks: BackgroundTasks):
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

# 商品管理相关API
@app.get("/api/products/discount", response_model=List[ProductInfo])
async def list_discount_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品")
):
    """获取折扣商品列表"""
    try:
        products = ProductService.list_discount_products(
            db=db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only
        )
        if not products:
            return []
        return products
    except Exception as e:
        logger.error(f"获取折扣商品列表失败: {str(e)}")
        return []

@app.get("/api/products/coupon", response_model=List[ProductInfo])
async def list_coupon_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品"),
    coupon_type: Optional[str] = Query(None, description="优惠券类型：percentage/fixed")
):
    """获取优惠券商品列表"""
    try:
        products = ProductService.list_coupon_products(
            db=db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only,
            coupon_type=coupon_type
        )
        if not products:
            return []
        return products
    except Exception as e:
        logger.error(f"获取优惠券商品列表失败: {str(e)}")
        return []

@app.get("/api/products/list", response_model=List[ProductInfo])
async def list_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品"),
    product_type: str = Query("all", description="商品类型：discount/coupon/all")
):
    """获取商品列表，支持分页、筛选和排序"""
    try:
        products = ProductService.list_products(
            db=db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only,
            product_type=product_type
        )
        if not products:
            return []
        return products
    except Exception as e:
        logger.error(f"获取商品列表失败: {str(e)}")
        return []

@app.post("/api/products/batch-delete")
async def batch_delete_products(request: BatchDeleteRequest, db: Session = Depends(get_db)):
    """批量删除商品"""
    try:
        result = ProductService.batch_delete_products(db, request.asins)
        return JSONResponse(
            content={
                "status": "success",
                "message": f"批量删除完成",
                "success_count": result["success_count"],
                "fail_count": result["fail_count"]
            },
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"批量删除失败: {str(e)}"
        )

@app.post("/api/products/save")
async def save_products(request: ProductRequest, output_file: str):
    """保存商品信息到文件"""
    try:
        api = get_product_api(request.marketplace)
        # 使用await调用异步方法
        products = await api.get_products_by_asins(request.asins)
        
        if not products:
            raise HTTPException(
                status_code=404,
                detail="未找到商品信息"
            )
        
        # 使用await调用异步方法
        await api.save_products_info(products, output_file)
        return {"status": "success", "message": f"商品信息已保存到: {output_file}"}
        
    except Exception as e:
        logger.error(f"保存商品信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/products", response_model=List[ProductInfo])
async def get_products(request: ProductRequest):
    """批量获取商品信息"""
    try:
        api = get_product_api(request.marketplace)
        # 使用await调用异步方法
        products = await api.get_products_by_asins(request.asins)
        
        if not products:
            raise HTTPException(
                status_code=404,
                detail="未找到商品信息"
            )
            
        return products
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取商品信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取商品信息时出错: {str(e)}")

@app.get("/api/products/{asin}", response_model=ProductInfo)
async def get_product(
    asin: str = Path(title="Product ASIN", description="产品ASIN", min_length=10, max_length=10),
    db: Session = Depends(get_db)
):
    """获取单个商品详情"""
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

# 缓存管理相关API
@app.get("/api/cache/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    try:
        # 获取API实例
        api = get_product_api()
        
        # 获取原始缓存统计信息
        raw_stats = api.cache_manager.get_stats()
        
        # 格式化统计信息
        formatted_stats = {
            # 将字节转换为MB，保留2位小数
            "total_size_mb": round(raw_stats["total_size"] / (1024 * 1024), 2),
            "total_files": raw_stats["total_files"],
            "by_type": {},
            "last_cleanup": raw_stats["last_cleanup"],
            "status": "healthy"  # 默认状态
        }
        
        # 格式化各类型的统计信息
        for cache_type, type_stats in raw_stats["by_type"].items():
            formatted_stats["by_type"][cache_type] = {
                "size_mb": round(type_stats["size"] / (1024 * 1024), 2),
                "count": type_stats["count"]
            }
            
        # 添加额外的状态信息
        formatted_stats["status_details"] = {
            "is_cleanup_running": True,  # 清理线程状态
            "cache_types": list(formatted_stats["by_type"].keys()),
            "cache_health": "good" if formatted_stats["total_files"] > 0 else "empty"
        }
        
        return formatted_stats
        
    except Exception as e:
        # 如果发生错误，返回带有错误信息的500响应
        raise HTTPException(
            status_code=500,
            detail={
                "error": "获取缓存统计信息失败",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
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

# 调度器相关API
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
        scheduler = SchedulerManager()
        jobs = scheduler.get_jobs()
        return JSONResponse(
            content=jobs,
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取任务列表失败: {str(e)}"
        )

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
    """暂停任务"""
    try:
        scheduler = SchedulerManager()
        scheduler.pause_job(job_id)
        return JSONResponse(
            content={"status": "success", "message": f"任务 {job_id} 已暂停"},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.post("/api/scheduler/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """恢复任务"""
    try:
        scheduler = SchedulerManager()
        scheduler.resume_job(job_id)
        return JSONResponse(
            content={"status": "success", "message": f"任务 {job_id} 已恢复"},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

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

@app.post("/api/scheduler/jobs/{job_id}/execute")
async def execute_job_now(job_id: str):
    """立即执行任务
    
    Args:
        job_id: 任务ID
        
    Returns:
        Dict: 执行结果
    """
    try:
        scheduler = SchedulerManager()
        scheduler.execute_job_now(job_id)
        return JSONResponse(
            content={"status": "success", "message": f"任务 {job_id} 已开始执行"},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    # 确保数据库表已创建
    init_db()
    print("数据库初始化完成")

if __name__ == "__main__":
    """
    FastAPI开发服务器启动入口
    
    支持的命令行参数：
    --host: 绑定的主机地址
    --port: 绑定的端口
    --reload: 是否启用自动重载
    --workers: 工作进程数
    --reload-dir: 监视变更的目录
    --log-level: 日志级别
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="FastAPI Development Server")
    parser.add_argument("--host", default="localhost", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--reload-dir", help="Directory to watch for changes")
    parser.add_argument("--log-level", default="info", help="Logging level")
    
    args = parser.parse_args()
    
    uvicorn.run(
        "amazon_crawler_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        reload_dir=args.reload_dir,
        log_level=args.log_level
    ) 