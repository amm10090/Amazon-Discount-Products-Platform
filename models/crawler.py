from pydantic import BaseModel, Field
from typing import List
from datetime import datetime

class CrawlerRequest(BaseModel):
    """爬虫请求参数模型"""
    max_items: int = Field(default=100, gt=0, le=1000, description="要爬取的最大商品数量")
    timeout: int = Field(default=30, gt=0, description="无新商品超时时间(秒)")
    headless: bool = Field(default=True, description="是否使用无头模式")
    output_format: str = Field(default="json", description="输出格式(txt/csv/json)")

class CrawlerResponse(BaseModel):
    """爬虫任务响应模型"""
    task_id: str
    status: str
    message: str
    timestamp: datetime

class CrawlerResult(BaseModel):
    """爬虫结果模型"""
    task_id: str
    status: str
    total_items: int
    asins: List[str]
    duration: float
    timestamp: datetime 