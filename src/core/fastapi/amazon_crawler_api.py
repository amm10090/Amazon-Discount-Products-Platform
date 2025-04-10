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
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, UTC
import asyncio
import uvicorn
import sys
import os
from pathlib import Path as PathLib
import aiohttp
from sqlalchemy import or_, and_
from fastapi.responses import FileResponse, JSONResponse
from models.crawler import CrawlerRequest, CrawlerResponse, CrawlerResult
from models.product import ProductInfo, ProductOffer
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from models.database import SessionLocal, init_db, Product, ProductVariant
from models.product_service import ProductService
from enum import Enum
from models.scheduler import SchedulerManager
from models.scheduler_models import JobConfig, JobStatus, SchedulerStatus, JobHistory
import pytz
import logging
from contextlib import asynccontextmanager
from loguru import logger
from logging.config import dictConfig
from starlette.status import HTTP_400_BAD_REQUEST

# 添加项目根目录到Python路径
project_root = PathLib(__file__).parent.parent.parent.parent
if project_root not in sys.path:
    sys.path.append(str(project_root))

try:
    from src.core.amazon_bestseller import crawl_deals, save_results
    from src.core.amazon_product_api import AmazonProductAPI
    from src.core.cj_api_client import CJAPIClient
except ImportError as e:
    logger.error(f"导入错误: {str(e)}")
    raise

# 加载环境变量
load_dotenv()

# 初始化数据库
init_db()

# 配置日志
log_dir = PathLib(os.getenv("APP_LOG_DIR", str(project_root / "logs"))).resolve()
log_dir.mkdir(parents=True, exist_ok=True)

# 获取应用logger，避免重新定义
app_logger = logger

# 配置 loguru 日志
logger.remove()  # 移除默认的处理器

# 添加主日志处理器
logger.add(
    log_dir / "app.{time:YYYY-MM-DD}.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    rotation="00:00",  # 每天轮转
    retention="7 days",  # 保留7天
    compression="zip",  # 压缩旧日志
    enqueue=True,  # 异步写入
    catch=True  # 捕获所有异常
)

# 添加错误日志处理器
logger.add(
    log_dir / "error.{time:YYYY-MM-DD}.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    enqueue=True,
    catch=True,  # 捕获所有异常
    filter=lambda record: record["level"].name == "ERROR"
)

# 在进程启动时仅配置一次日志重定向
# 防止工作进程重复配置导致冲突
if os.environ.get("UVICORN_WORKER_INITIALIZED", "0") != "1":
    os.environ["UVICORN_WORKER_INITIALIZED"] = "1"
    
    # 禁用所有默认的日志处理器
    logging.getLogger().handlers = []
    logging.getLogger("uvicorn").handlers = []
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []
    logging.getLogger("fastapi").handlers = []
    
    # 配置日志
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,  # 改为False以避免禁用已存在的logger
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            }
        },
        "handlers": {
            "null": {
                "class": "logging.NullHandler",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["null"], "propagate": False},
            "uvicorn.access": {"handlers": ["null"], "propagate": False},
            "uvicorn.error": {"handlers": ["null"], "propagate": False},
            "fastapi": {"handlers": ["null"], "propagate": False},
            "": {"handlers": ["null"], "propagate": False}  # 根日志记录器
        }
    }
    dictConfig(logging_config)
    
    # 将标准库的日志重定向到loguru
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # 获取对应的loguru级别
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
    
            # 找到调用者的栈帧
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
    
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
    
    # 添加拦截处理器到根日志记录器
    logging.getLogger().handlers = [InterceptHandler()]
    logging.getLogger().setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 创建并启动调度器
    scheduler_manager = SchedulerManager()
    scheduler_manager.start()
    logger.info("调度器已启动")
    yield
    # 在这里可以添加应用关闭时需要执行的清理代码
    logger.info("应用关闭，执行清理工作")

# 创建FastAPI应用
app = FastAPI(
    title="Amazon Data API",
    description="API for crawling Amazon deals and retrieving product information",
    version="2.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的前端域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)

# 导入日志分析API路由
try:
    from src.api.log_analysis_api import router as log_analysis_router
    # 添加日志分析API路由
    app.include_router(log_analysis_router)
except ImportError as e:
    logger.warning(f"无法导入日志分析API路由: {str(e)}")

# 存储任务状态的字典
tasks_status: Dict[str, Dict] = {}

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

class CategoryStats(BaseModel):
    """类别统计响应模型"""
    browse_nodes: Dict[str, Dict[str, Any]]  # 浏览节点统计
    browse_tree: Dict[str, Any]              # 浏览节点树形结构
    bindings: Dict[str, int]                 # 商品绑定类型统计
    product_groups: Dict[str, int]           # 商品组统计

class BrandStats(BaseModel):
    """品牌统计响应模型"""
    brands: Dict[str, int]                  # 品牌统计
    total_brands: int                       # 品牌总数
    pagination: Dict[str, Any]              # 分页信息

class ProductQueryRequest(BaseModel):
    """商品查询请求模型"""
    asins: List[str] = Field(..., min_items=1, max_items=50, description="产品ASIN列表,最多50个")
    include_metadata: bool = Field(False, description="是否包含元数据")
    include_browse_nodes: Optional[List[str]] = Field(None, description="要包含的浏览节点ID列表，为空则包含所有节点")

    @field_validator('asins')
    @classmethod
    def validate_asins(cls, v):
        """验证每个ASIN的格式"""
        for asin in v:
            if not isinstance(asin, str) or len(asin) != 10:
                raise ValueError(f"无效的ASIN格式: {asin}")
        return v

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
        output_dir = PathLib("crawler_results")
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
async def health_check(db: Session = Depends(get_db)):
    """健康检查端点"""
    try:
        # 获取商品统计信息
        stats = ProductService.get_products_stats(db)
        
        return {
            "status": "healthy",
            "service": "amazon-data-api",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "total_products": stats["total_products"],
                "discount_products": stats["discount_products"],
                "coupon_products": stats["coupon_products"],
                "prime_products": stats["prime_products"],
                "last_update": stats["last_update"].isoformat() if stats["last_update"] else None
            }
        }
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return {
            "status": "unhealthy",
            "service": "amazon-data-api",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

# 爬虫任务相关API
@app.post("/api/crawl", response_model=CrawlerResponse, include_in_schema=False)
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

@app.get("/api/status/{task_id}", response_model=CrawlerResult, include_in_schema=False)
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

@app.get("/api/download/{task_id}", include_in_schema=False)
async def download_results(task_id: str):
    """下载爬虫结果"""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_info = tasks_status[task_id]
    if task_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")
        
    output_file = PathLib("crawler_results") / f"{task_id}.{task_info.get('output_format', 'json')}"
    if not output_file.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
        
    return FileResponse(
        path=output_file,
        filename=output_file.name,
        media_type="application/octet-stream"
    )

# 商品管理相关API
@app.get("/api/products/discount")
async def list_discount_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品"),
    api_provider: Optional[str] = Query(None, description="数据来源：pa-api/cj-api"),
    min_commission: Optional[int] = Query(None, ge=0, le=100, description="最低佣金比例"),
    browse_node_ids: Optional[List[str]] = Query(None, description="Browse Node IDs"),
    bindings: Optional[List[str]] = Query(None, description="商品绑定类型"),
    product_groups: Optional[List[str]] = Query(None, description="商品组"),
    brands: Optional[List[str]] = Query(None, description="品牌")
):
    """获取折扣商品列表"""
    try:
        result = ProductService.list_discount_products(
            db=db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only,
            api_provider=api_provider,
            min_commission=min_commission,
            browse_node_ids=browse_node_ids,
            bindings=bindings,
            product_groups=product_groups,
            brands=brands
        )
        
        # 确保使用数据库中的current_price字段
        if "items" in result and result["items"]:
            for product_info in result["items"]:
                if product_info.offers and len(product_info.offers) > 0:
                    # 从数据库查询当前价格
                    db_product = db.query(Product).filter(Product.asin == product_info.asin).first()
                    if db_product and db_product.current_price is not None:
                        # 更新第一个offer中的价格为数据库中的current_price
                        product_info.offers[0].price = db_product.current_price
                        # 确保original_price字段有值
                        if db_product.original_price is not None and product_info.offers[0].original_price is None:
                            product_info.offers[0].original_price = db_product.original_price
                    
        return result
    except Exception as e:
        logger.error(f"获取折扣商品列表失败: {str(e)}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }

@app.get("/api/products/coupon")
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
    coupon_type: Optional[str] = Query(None, description="优惠券类型：percentage/fixed"),
    api_provider: Optional[str] = Query(None, description="数据来源：pa-api/cj-api"),
    min_commission: Optional[int] = Query(None, ge=0, le=100, description="最低佣金比例"),
    browse_node_ids: Optional[List[str]] = Query(None, description="Browse Node IDs"),
    bindings: Optional[List[str]] = Query(None, description="商品绑定类型"),
    product_groups: Optional[List[str]] = Query(None, description="商品组"),
    brands: Optional[List[str]] = Query(None, description="品牌")
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
            coupon_type=coupon_type,
            api_provider=api_provider,
            min_commission=min_commission,
            browse_node_ids=browse_node_ids,
            bindings=bindings,
            product_groups=product_groups,
            brands=brands
        )
        
        # 确保使用数据库中的current_price字段
        if "items" in products and products["items"]:
            for product_info in products["items"]:
                if product_info.offers and len(product_info.offers) > 0:
                    # 从数据库查询当前价格
                    db_product = db.query(Product).filter(Product.asin == product_info.asin).first()
                    if db_product and db_product.current_price is not None:
                        # 更新第一个offer中的价格为数据库中的current_price
                        product_info.offers[0].price = db_product.current_price
                        # 确保original_price字段有值
                        if db_product.original_price is not None and product_info.offers[0].original_price is None:
                            product_info.offers[0].original_price = db_product.original_price
        
        return products
    except Exception as e:
        logger.error(f"获取优惠券商品列表失败: {str(e)}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }

@app.get("/api/products/list")
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
    product_type: str = Query("all", description="商品类型：discount/coupon/all"),
    browse_node_ids: Optional[Union[List[str], str]] = Query(None, description="Browse Node IDs，支持数组或逗号分隔的字符串"),
    bindings: Optional[Union[List[str], str]] = Query(None, description="商品绑定类型，支持数组或逗号分隔的字符串"),
    product_groups: Optional[Union[List[str], str]] = Query(None, description="商品组，支持数组或逗号分隔的字符串"),
    api_provider: Optional[str] = Query(None, description="数据来源：pa-api/cj-api/all"),
    min_commission: Optional[int] = Query(None, ge=0, le=100, description="最低佣金比例"),
    brands: Optional[Union[List[str], str]] = Query(None, description="品牌，支持数组或逗号分隔的字符串")
):
    """获取商品列表，支持分页、筛选和排序"""
    try:
        # 处理bindings参数
        binding_list = None
        if bindings:
            if isinstance(bindings, str):
                # 处理逗号分隔的字符串
                binding_list = [b.strip() for b in bindings.split(",") if b.strip()]
            elif isinstance(bindings, list):
                # 处理数组形式，并处理每个元素中可能的逗号分隔
                binding_list = []
                for binding in bindings:
                    if isinstance(binding, str) and ',' in binding:
                        binding_list.extend([b.strip() for b in binding.split(",") if b.strip()])
                    else:
                        binding_list.append(str(binding).strip())
            logger.info(f"处理后的binding_list: {binding_list}")

        # 处理product_groups参数
        group_list = None
        if product_groups:
            if isinstance(product_groups, str):
                # 处理逗号分隔的字符串
                group_list = [g.strip() for g in product_groups.split(",") if g.strip()]
            elif isinstance(product_groups, list):
                # 处理数组形式，并处理每个元素中可能的逗号分隔
                group_list = []
                for group in product_groups:
                    if isinstance(group, str) and ',' in group:
                        group_list.extend([g.strip() for g in group.split(",") if g.strip()])
                    else:
                        group_list.append(str(group).strip())
            logger.info(f"处理后的group_list: {group_list}")

        # 处理browse_node_ids参数
        node_list = None
        if browse_node_ids:
            if isinstance(browse_node_ids, str):
                # 处理逗号分隔的字符串
                if ',' in browse_node_ids:
                    node_list = [n.strip() for n in browse_node_ids.split(",") if n.strip()]
                else:
                    node_list = [browse_node_ids.strip()]
            elif isinstance(browse_node_ids, list):
                # 处理数组形式，并处理每个元素中可能的逗号分隔
                node_list = []
                for node_id in browse_node_ids:
                    if isinstance(node_id, str) and ',' in node_id:
                        node_list.extend([n.strip() for n in node_id.split(",") if n.strip()])
                    else:
                        node_list.append(str(node_id).strip())
            logger.info(f"处理后的node_list: {node_list}")
            
        # 处理brands参数
        brand_list = None
        if brands:
            if isinstance(brands, str):
                # 处理逗号分隔的字符串
                brand_list = [b.strip() for b in brands.split(",") if b.strip()]
            elif isinstance(brands, list):
                # 处理数组形式，并处理每个元素中可能的逗号分隔
                brand_list = []
                for brand in brands:
                    if isinstance(brand, str) and ',' in brand:
                        brand_list.extend([b.strip() for b in brand.split(",") if b.strip()])
                    else:
                        brand_list.append(str(brand).strip())
            logger.info(f"处理后的brand_list: {brand_list}")

        result = ProductService.list_products(
            db=db,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            is_prime_only=is_prime_only,
            product_type=product_type,
            browse_node_ids=node_list,
            bindings=binding_list,
            product_groups=group_list,
            api_provider=api_provider,
            min_commission=min_commission,
            brands=brand_list
        )
        
        # 确保使用数据库中的current_price字段
        if "items" in result and result["items"]:
            for product_info in result["items"]:
                if product_info.offers and len(product_info.offers) > 0:
                    # 从数据库查询当前价格
                    db_product = db.query(Product).filter(Product.asin == product_info.asin).first()
                    if db_product and db_product.current_price is not None:
                        # 更新第一个offer中的价格为数据库中的current_price
                        product_info.offers[0].price = db_product.current_price
                        # 确保original_price字段有值
                        if db_product.original_price is not None and product_info.offers[0].original_price is None:
                            product_info.offers[0].original_price = db_product.original_price
                        
        return result
    except Exception as e:
        logger.error(f"获取商品列表失败: {str(e)}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }

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

@app.post("/api/products/save", include_in_schema=False)
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

@app.get("/api/products/stats")
async def get_products_stats(
    db: Session = Depends(get_db),
    product_type: Optional[str] = Query(None, description="商品类型：discount/coupon/all")
):
    """获取商品统计信息
    
    Args:
        db: 数据库会话
        product_type: 商品类型筛选
        
    Returns:
        dict: 统计信息
    """
    try:
        stats = ProductService.get_products_stats(db, product_type)
        return stats
    except Exception as e:
        logger.error(f"获取商品统计信息失败: {str(e)}")
        return {
            "total_products": 0,
            "discount_products": 0,
            "coupon_products": 0,
            "prime_products": 0,
            "avg_discount": 0,
            "avg_price": 0,
            "min_price": 0,
            "max_price": 0
        }

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
            
        # 确保使用products表中的current_price
        if product.offers and len(product.offers) > 0:
            # 从数据库查询当前价格
            db_product = db.query(Product).filter(Product.asin == asin).first()
            if db_product and db_product.current_price is not None:
                # 更新第一个offer中的价格为数据库中的current_price
                product.offers[0].price = db_product.current_price
                # 确保original_price字段有值
                if db_product.original_price is not None and product.offers[0].original_price is None:
                    product.offers[0].original_price = db_product.original_price
                
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取产品信息失败: {str(e)}"
        )

@app.post("/api/products/query", response_model=Union[ProductInfo, List[Optional[ProductInfo]]])
async def query_product(
    request: ProductQueryRequest,
    db: Session = Depends(get_db)
):
    """通过ASIN查询商品详细信息，支持批量查询
    
    Args:
        request: 包含ASIN列表和查询选项的请求对象
        db: 数据库会话
        
    Returns:
        单个ASIN时返回单个ProductInfo对象
        ASIN列表时返回ProductInfo对象列表，未找到的项为None
        
    Raises:
        HTTPException: 当查询失败时抛出
    """
    try:
        products = ProductService.get_product_details_by_asin(
            db, 
            request.asins,
            include_metadata=request.include_metadata,
            include_browse_nodes=request.include_browse_nodes
        )
        
        if not products:
            raise HTTPException(
                status_code=404,
                detail="未找到任何商品"
            )
            
        # 如果是单个ASIN的查询，直接返回结果
        if isinstance(request.asins, str):
            if products is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"未找到ASIN为 {request.asins} 的商品"
                )
            
            # 确保使用products表中的current_price和original_price
            if products.offers and len(products.offers) > 0:
                db_product = db.query(Product).filter(Product.asin == request.asins).first()
                if db_product and db_product.current_price is not None:
                    products.offers[0].price = db_product.current_price
                    # 确保original_price字段有值
                    if db_product.original_price is not None and products.offers[0].original_price is None:
                        products.offers[0].original_price = db_product.original_price
                
            return products
            
        # 如果是批量查询，处理每个商品的价格
        if isinstance(products, list):
            for product in products:
                if product and product.offers and len(product.offers) > 0:
                    db_product = db.query(Product).filter(Product.asin == product.asin).first()
                    if db_product and db_product.current_price is not None:
                        product.offers[0].price = db_product.current_price
                        # 确保original_price字段有值
                        if db_product.original_price is not None and product.offers[0].original_price is None:
                            product.offers[0].original_price = db_product.original_price
        
        # 返回结果列表
        return products
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取商品信息失败: {str(e)}"
        )

# 缓存管理相关API
@app.get("/api/cache/stats", include_in_schema=False)
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

@app.post("/api/cache/clear", include_in_schema=False)
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

@app.post("/api/cache/clear-all", include_in_schema=False)
async def clear_all_cache():
    """清理所有缓存"""
    try:
        api = get_product_api()
        api.cache_manager.clear_all()
        return {"status": "success", "message": "所有缓存已清理"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"清理所有缓存失败: {str(e)}"
        )

# 调度器相关API
@app.post("/api/scheduler/jobs", include_in_schema=False)
async def add_job(job_config: JobConfig):
    """添加新的定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.add_job(job_config.dict())
        return {"status": "success", "message": "任务添加成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/scheduler/jobs", response_model=List[JobStatus], include_in_schema=False)
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

@app.delete("/api/scheduler/jobs/{job_id}", include_in_schema=False)
async def delete_job(job_id: str):
    """删除定时任务"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.remove_job(job_id)
        return {"status": "success", "message": "任务删除成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/scheduler/jobs/{job_id}/pause", include_in_schema=False)
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

@app.post("/api/scheduler/jobs/{job_id}/resume", include_in_schema=False)
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

@app.get("/api/scheduler/jobs/{job_id}/history", response_model=List[JobHistory], include_in_schema=False)
async def get_job_history(job_id: str):
    """获取任务执行历史"""
    try:
        scheduler_manager = SchedulerManager()
        return scheduler_manager.get_job_history(job_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/scheduler/status", response_model=SchedulerStatus, include_in_schema=False)
async def get_scheduler_status():
    """获取调度器状态"""
    try:
        scheduler_manager = SchedulerManager()
        return scheduler_manager.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/start", include_in_schema=False)
async def start_scheduler():
    """启动调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.start()
        return {"status": "success", "message": "调度器已启动"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/stop", include_in_schema=False)
async def stop_scheduler():
    """停止调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.stop()
        return {"status": "success", "message": "调度器已停止"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/reload", include_in_schema=False)
async def reload_scheduler():
    """重新加载调度器"""
    try:
        scheduler_manager = SchedulerManager()
        scheduler_manager.reload()
        return {"status": "success", "message": "调度器已重新加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/timezone", include_in_schema=False)
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

@app.post("/api/scheduler/jobs/{job_id}/execute", include_in_schema=False)
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

@app.get("/api/categories/stats", response_model=CategoryStats, include_in_schema=False)
async def get_category_stats(
    product_type: Optional[str] = Query(None, description="商品类型: discount/coupon"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    sort_by: str = Query("count", description="排序字段: group/count"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    db: Session = Depends(get_db)
):
    """获取类别统计信息"""
    try:
        stats = ProductService.get_category_stats(
            db, 
            product_type=product_type,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return CategoryStats(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取类别统计信息失败: {str(e)}"
        )

@app.post("/api/categories/stats/clear-cache", include_in_schema=False)
async def clear_category_stats_cache():
    """清空类别统计缓存"""
    try:
        result = ProductService.clear_category_stats_cache()
        return JSONResponse(
            content={"status": "success", "message": "类别统计缓存已清空", "result": result},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"清空类别统计缓存失败: {str(e)}"
        )

@app.get("/api/brands/stats", response_model=BrandStats)
async def get_brand_stats(
    product_type: Optional[str] = Query(None, description="商品类型: discount/coupon"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    sort_by: str = Query("count", description="排序字段: brand/count"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    db: Session = Depends(get_db)
):
    """获取品牌统计信息"""
    try:
        stats = ProductService.get_brand_stats(
            db, 
            product_type=product_type,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return BrandStats(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取品牌统计信息失败: {str(e)}"
        )

@app.post("/api/brands/stats/clear-cache", include_in_schema=False)
async def clear_brand_stats_cache():
    """清空品牌统计缓存"""
    try:
        result = ProductService.clear_brand_stats_cache()
        return JSONResponse(
            content={"status": "success", "message": "品牌统计缓存已清空", "result": result},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"清空品牌统计缓存失败: {str(e)}"
        )

@app.get("/api/search/products")
async def search_products(
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    sort_by: Optional[str] = Query("relevance", description="排序字段：relevance/price/discount/created"),
    sort_order: str = Query("desc", description="排序方向：asc/desc"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    min_discount: Optional[int] = Query(None, ge=0, le=100, description="最低折扣率"),
    is_prime_only: bool = Query(False, description="是否只显示Prime商品"),
    product_groups: Optional[str] = Query(None, description="商品分类，逗号分隔"),
    brands: Optional[str] = Query(None, description="品牌，逗号分隔"),
    api_provider: Optional[str] = Query(None, description="数据来源：pa-api/cj-api"),
    db: Session = Depends(get_db)
):
    """根据关键词搜索产品"""
    try:
        # 检查关键词是否是ASIN格式
        is_asin_format = ProductService.is_valid_asin(keyword)
        
        result = ProductService.search_products(
            db=db,
            keyword=keyword,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            is_prime_only=is_prime_only,
            product_groups=product_groups,
            brands=brands,
            api_provider=api_provider
        )
        
        # 处理ASIN搜索没有结果的情况
        if is_asin_format and (not result["success"] or len(result["data"]["items"]) == 0):
            # 如果是ASIN格式但没有找到商品，返回特定的消息
            return {
                "success": False,
                "data": {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "is_asin_search": True
                },
                "error": f"未找到ASIN为'{keyword}'的商品。这是有效的ASIN格式，但在数据库中不存在。"
            }
            
        # 如果有ASIN搜索标记，保留它
        if result.get("data", {}).get("is_asin_search"):
            return result
            
        return result
    except Exception as e:
        logger.error(f"搜索产品失败: {str(e)}")
        
        # 检查是否为ASIN格式，提供不同的错误消息
        is_asin_format = ProductService.is_valid_asin(keyword)
        error_message = str(e)
        
        if is_asin_format:
            error_message = f"搜索ASIN '{keyword}' 失败: {str(e)}"
        
        return {
            "success": False,
            "data": {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "is_asin_search": is_asin_format
            },
            "error": error_message
        }

@app.post("/api/cj/check-products")
async def check_cj_products(request: ProductRequest):
    """检查商品在CJ平台的可用性
    
    Args:
        request: 包含ASIN列表的请求对象
        
    Returns:
        Dict[str, bool]: 商品可用性字典，key为ASIN，value为是否可用
    """
    try:
        cj_client = CJAPIClient()
        availability = await cj_client.check_products_availability(request.asins)
        return availability
    except Exception as e:
        logger.error(f"检查CJ商品可用性失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"检查商品可用性失败: {str(e)}"
        )

@app.get("/api/cj/generate-link/{asin}")
async def generate_cj_link(asin: str = Path(..., description="商品ASIN")):
    """生成CJ推广链接
    
    Args:
        asin: 商品ASIN
        
    Returns:
        Dict: 包含生成的推广链接
    """
    try:
        cj_client = CJAPIClient()
        url = await cj_client.generate_product_link(asin)
        return {"url": url}
    except Exception as e:
        logger.error(f"生成CJ推广链接失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"生成推广链接失败: {str(e)}"
        )

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