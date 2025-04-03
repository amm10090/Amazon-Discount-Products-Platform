"""
日志分析和可视化API接口。
提供日志查询、统计分析、仪表板生成和日志导出功能。
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Response
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, JSONResponse
from starlette.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from src.utils.log_analysis import LogQuery, LogAnalytics, LogMonitor
from src.utils.log_visualization import LogChartGenerator, SystemHealthDashboard, LogExporter
from src.utils.log_config import LogConfig

# 创建路由器
router = APIRouter(prefix="/api/logs", tags=["logs"])

# 模型定义
class LogFilterParams(BaseModel):
    """日志过滤参数模型。"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    level: Optional[str] = None
    module: Optional[str] = None
    message_pattern: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    limit: int = Field(default=100, ge=1, le=1000)

class LogAggregateParams(BaseModel):
    """日志聚合参数模型。"""
    group_by: List[str]
    metrics: List[str]
    filters: Optional[Dict[str, Any]] = None
    interval: Optional[str] = None

class LogChartParams(BaseModel):
    """日志图表参数模型。"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    chart_type: str = Field(..., description="Chart type: error_rate, response_time, module_activity")
    metric: Optional[str] = "response_time"
    interval: Optional[str] = "hour"

class LogExportParams(BaseModel):
    """日志导出参数模型。"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    level: Optional[str] = None
    module: Optional[str] = None
    format: str = Field(..., description="Export format: json or csv")

# 全局设置
LOG_PATH = os.environ.get("LOG_PATH", "logs")
OUTPUT_DIR = os.environ.get("LOG_OUTPUT_DIR", "log_outputs")

# 初始化
Path(OUTPUT_DIR).mkdir(exist_ok=True)

# 路由定义
@router.get("/query", response_model=List[Dict[str, Any]])
async def query_logs(
    params: LogFilterParams = None
):
    """
    查询日志记录。
    
    支持按时间、级别、模块等条件过滤。
    
    Args:
        params: 日志过滤参数
        
    Returns:
        符合条件的日志记录列表
    """
    try:
        query = LogQuery(LOG_PATH)
        logs = query.search(
            start_time=params.start_time,
            end_time=params.end_time,
            level=params.level,
            module=params.module,
            message_pattern=params.message_pattern,
            context=params.context,
            limit=params.limit
        )
        return logs
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to query logs: {str(e)}"
        )

@router.post("/aggregate", response_model=Dict[str, Any])
async def aggregate_logs(
    params: LogAggregateParams
):
    """
    聚合日志数据。
    
    支持多维度分组和指标计算。
    
    Args:
        params: 日志聚合参数
        
    Returns:
        聚合结果
    """
    try:
        query = LogQuery(LOG_PATH)
        results = query.aggregate(
            group_by=params.group_by,
            metrics=params.metrics,
            filters=params.filters,
            interval=params.interval
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to aggregate logs: {str(e)}"
        )

@router.get("/stats", response_model=Dict[str, Any])
async def get_log_statistics(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    metric: str = "response_time",
    group_by: str = "hour"
):
    """
    获取日志统计信息。
    
    Args:
        start_time: 开始时间
        end_time: 结束时间
        metric: 指标名称
        group_by: 分组间隔
        
    Returns:
        统计结果
    """
    try:
        query = LogQuery(LOG_PATH)
        analytics = LogAnalytics(query)
        
        # 获取错误分布
        error_dist = analytics.get_error_distribution(
            start_time=start_time,
            end_time=end_time,
            group_by=group_by
        )
        
        # 获取异常
        anomalies = analytics.detect_anomalies(
            metric=metric
        )
        
        # 获取总体统计
        logs = query.search(
            start_time=start_time,
            end_time=end_time
        )
        error_logs = query.search(
            start_time=start_time,
            end_time=end_time,
            level="ERROR"
        )
        
        # 计算错误率
        error_rate = (len(error_logs) / len(logs)) * 100 if logs else 0
        
        return {
            "total_logs": len(logs),
            "error_logs": len(error_logs),
            "error_rate": error_rate,
            "error_distribution": error_dist,
            "anomalies": anomalies
        }
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to get log statistics: {str(e)}"
        )

@router.get("/chart")
async def generate_chart(
    chart_type: str = Query(..., description="Chart type: error_rate, response_time, module_activity"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    metric: str = "response_time",
    interval: str = "hour",
    background_tasks: BackgroundTasks = None
):
    """
    生成日志图表。
    
    Args:
        chart_type: 图表类型
        start_time: 开始时间
        end_time: 结束时间
        metric: 指标名称
        interval: 时间间隔
        background_tasks: 后台任务
        
    Returns:
        图表文件
    """
    try:
        query = LogQuery(LOG_PATH)
        chart_generator = LogChartGenerator(query)
        
        output_path = os.path.join(OUTPUT_DIR, f"{chart_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
        
        if chart_type == "error_rate":
            chart_path = chart_generator.error_rate_chart(
                start_time=start_time,
                end_time=end_time,
                interval=interval,
                output_path=output_path
            )
        elif chart_type == "response_time":
            chart_path = chart_generator.response_time_chart(
                start_time=start_time,
                end_time=end_time,
                metric=metric,
                output_path=output_path
            )
        elif chart_type == "module_activity":
            chart_path = chart_generator.module_activity_chart(
                start_time=start_time,
                end_time=end_time,
                output_path=output_path
            )
        else:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid chart type: {chart_type}"
            )
        
        # 添加清理任务
        if background_tasks:
            background_tasks.add_task(lambda file_path: os.unlink(file_path) if os.path.exists(file_path) else None, chart_path)
        
        return FileResponse(
            path=chart_path,
            filename=os.path.basename(chart_path),
            media_type="image/png"
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate chart: {str(e)}"
        )

@router.get("/dashboard")
async def generate_dashboard(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    background_tasks: BackgroundTasks = None
):
    """
    生成系统健康状态仪表板。
    
    Args:
        start_time: 开始时间
        end_time: 结束时间
        background_tasks: 后台任务
        
    Returns:
        仪表板HTML文件
    """
    try:
        dashboard = SystemHealthDashboard(LOG_PATH)
        output_dir = os.path.join(OUTPUT_DIR, f"dashboard_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        
        charts = dashboard.generate_dashboard(
            start_time=start_time,
            end_time=end_time,
            output_dir=output_dir
        )
        
        # 添加清理任务（延迟1小时）
        if background_tasks:
            background_tasks.add_task(
                lambda dir_path: shutil.rmtree(dir_path) if os.path.exists(dir_path) else None,
                output_dir
            )
        
        return FileResponse(
            path=charts["dashboard"],
            filename=os.path.basename(charts["dashboard"]),
            media_type="text/html"
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate dashboard: {str(e)}"
        )

@router.get("/export")
async def export_logs(
    format: str = Query(..., description="Export format: json or csv"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    level: Optional[str] = None,
    module: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """
    导出日志。
    
    Args:
        format: 导出格式（json或csv）
        start_time: 开始时间
        end_time: 结束时间
        level: 日志级别
        module: 模块名称
        background_tasks: 后台任务
        
    Returns:
        导出文件
    """
    try:
        query = LogQuery(LOG_PATH)
        exporter = LogExporter(query)
        
        filename = f"logs_{datetime.now().strftime('%Y%m%d%H%M%S')}.{format}"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        if format.lower() == "json":
            result_path = exporter.export_to_json(
                output_path=output_path,
                start_time=start_time,
                end_time=end_time,
                level=level,
                module=module
            )
            media_type = "application/json"
        elif format.lower() == "csv":
            result_path = exporter.export_to_csv(
                output_path=output_path,
                start_time=start_time,
                end_time=end_time,
                level=level,
                module=module
            )
            media_type = "text/csv"
        else:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid export format: {format}"
            )
        
        # 添加清理任务
        if background_tasks:
            background_tasks.add_task(lambda file_path: os.unlink(file_path) if os.path.exists(file_path) else None, result_path)
        
        return FileResponse(
            path=result_path,
            filename=os.path.basename(result_path),
            media_type=media_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to export logs: {str(e)}"
        )

@router.post("/level")
async def set_log_level(level: str = Query(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")):
    """
    设置日志级别。
    
    Args:
        level: 日志级别
        
    Returns:
        操作结果
    """
    try:
        LogConfig.set_log_level(level.upper())
        return {"message": f"Log level set to {level.upper()}"}
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to set log level: {str(e)}"
        ) 