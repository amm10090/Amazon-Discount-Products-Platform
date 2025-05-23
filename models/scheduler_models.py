from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class JobConfig(BaseModel):
    """定时任务配置模型"""
    id: str = Field(..., description="任务ID")
    type: str = Field(..., description="任务类型：cron或interval")
    crawler_type: str = Field(..., description="爬虫类型：bestseller、coupon、all、update、cj、coupon_details")
    max_items: int = Field(..., ge=10, le=1000, description="最大采集数量")
    hour: Optional[str] = Field(None, description="Cron任务的小时设置")
    minute: Optional[str] = Field(None, description="Cron任务的分钟设置")
    hours: Optional[int] = Field(None, ge=0, le=24, description="间隔任务的小时数")
    minutes: Optional[int] = Field(None, ge=0, le=59, description="间隔任务的分钟数")
    # 折扣爬虫配置参数
    updater_config: Optional[dict] = Field(None, description="更新器配置参数")
    discount_config: Optional[dict] = Field(None, description="折扣爬虫配置参数")
    # 优惠券详情配置参数
    coupon_details_config: Optional[dict] = Field(None, description="优惠券详情爬虫配置参数")
    # 直接支持的折扣爬虫参数
    num_threads: Optional[int] = Field(None, description="爬虫线程数")
    update_interval: Optional[int] = Field(None, description="更新间隔(小时)")
    force_update: Optional[bool] = Field(None, description="强制更新")
    headless: Optional[bool] = Field(None, description="无头模式")
    min_delay: Optional[float] = Field(None, description="最小延迟(秒)")
    max_delay: Optional[float] = Field(None, description="最大延迟(秒)")
    debug: Optional[bool] = Field(None, description="调试模式")
    log_to_console: Optional[bool] = Field(None, description="输出日志到控制台")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "bestseller_daily",
                "type": "cron",
                "crawler_type": "bestseller",
                "max_items": 100,
                "hour": "*/4",
                "minute": "0"
            }
        }
        # 允许额外的属性
        extra = "allow"

class JobStatus(BaseModel):
    """任务状态模型"""
    id: str = Field(..., description="任务ID")
    type: str = Field(..., description="任务类型")
    crawler_type: str = Field(..., description="爬虫类型：bestseller、coupon、all、update、cj、coupon_details")
    max_items: int = Field(..., description="最大采集数量")
    next_run_time: float = Field(..., description="下次执行时间戳")
    paused: bool = Field(..., description="是否暂停")
    hour: Optional[str] = Field(None, description="Cron任务的小时设置")
    minute: Optional[str] = Field(None, description="Cron任务的分钟设置")
    hours: Optional[int] = Field(None, description="间隔任务的小时数")
    minutes: Optional[int] = Field(None, description="间隔任务的分钟数")
    # 折扣爬虫配置参数
    updater_config: Optional[dict] = Field(None, description="更新器配置参数")
    discount_config: Optional[dict] = Field(None, description="折扣爬虫配置参数")
    # 优惠券详情配置参数
    coupon_details_config: Optional[dict] = Field(None, description="优惠券详情爬虫配置参数")
    # 直接支持的折扣爬虫参数
    num_threads: Optional[int] = Field(None, description="爬虫线程数")
    update_interval: Optional[int] = Field(None, description="更新间隔(小时)")
    force_update: Optional[bool] = Field(None, description="强制更新")
    headless: Optional[bool] = Field(None, description="无头模式")
    min_delay: Optional[float] = Field(None, description="最小延迟(秒)")
    max_delay: Optional[float] = Field(None, description="最大延迟(秒)")
    debug: Optional[bool] = Field(None, description="调试模式")
    log_to_console: Optional[bool] = Field(None, description="输出日志到控制台")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "bestseller_daily",
                "type": "cron",
                "crawler_type": "bestseller",
                "max_items": 100,
                "next_run_time": 1677649200.0,
                "paused": False,
                "hour": "*/4",
                "minute": "0"
            }
        }
        # 允许额外的属性
        extra = "allow"

class SchedulerStatus(BaseModel):
    """调度器状态模型"""
    running: bool = Field(..., description="是否正在运行")
    running_jobs: int = Field(..., description="正在运行的任务数")
    total_jobs: int = Field(..., description="总任务数")
    timezone: str = Field(..., description="时区")

    class Config:
        json_schema_extra = {
            "example": {
                "running": True,
                "running_jobs": 2,
                "total_jobs": 3,
                "timezone": "Asia/Shanghai"
            }
        }

class JobHistory(BaseModel):
    """任务执行历史模型"""
    start_time: datetime = Field(..., description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    status: str = Field(..., description="执行状态")
    items_collected: int = Field(..., description="采集数量")
    error: Optional[str] = Field(None, description="错误信息")

    class Config:
        json_schema_extra = {
            "example": {
                "start_time": "2024-02-28T10:00:00+08:00",
                "end_time": "2024-02-28T10:05:30+08:00",
                "status": "completed",
                "items_collected": 100,
                "error": None
            }
        }

class JobHistoryDB(BaseModel):
    """任务执行历史数据库模型"""
    id: int = Field(..., description="记录ID")
    job_id: str = Field(..., description="任务ID")
    start_time: datetime = Field(..., description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    status: str = Field(..., description="执行状态")
    items_collected: int = Field(0, description="采集数量")
    error: Optional[str] = Field(None, description="错误信息")

    class Config:
        from_attributes = True 