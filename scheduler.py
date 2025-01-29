import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import yaml
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from loguru import logger
from collect_products import Config, crawl_bestseller_products, crawl_coupon_products
from amazon_product_api import AmazonProductAPI

class SchedulerManager:
    """定时任务管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self.load_config(config_path)
        self.scheduler = self._init_scheduler()
        self.api = self._init_api()
        self._setup_logging()
        
    def _setup_logging(self):
        """配置日志"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 配置日志格式和输出
        logger.add(
            log_dir / "scheduler.log",
            rotation="1 day",
            retention="7 days",
            level="INFO",
            encoding="utf-8"
        )
        
    def load_config(self, config_path: Optional[str]) -> dict:
        """加载配置文件"""
        default_config = {
            "scheduler": {
                "jobs": [
                    {
                        "id": "bestseller_daily",
                        "type": "cron",
                        "hour": "*/4",  # 每4小时执行一次
                        "crawler_type": "bestseller",
                        "max_items": 100
                    },
                    {
                        "id": "coupon_hourly",
                        "type": "interval",
                        "hours": 1,  # 每小时执行一次
                        "crawler_type": "coupon",
                        "max_items": 50
                    }
                ],
                "timezone": "Asia/Shanghai",
                "job_store": {
                    "url": "sqlite:///jobs.db"
                }
            }
        }
        
        if not config_path:
            return default_config
            
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return {**default_config, **config}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return default_config
            
    def _init_scheduler(self) -> AsyncIOScheduler:
        """初始化调度器"""
        jobstores = {
            'default': SQLAlchemyJobStore(
                url=self.config['scheduler']['job_store']['url']
            )
        }
        
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=self.config['scheduler']['timezone']
        )
        return scheduler
        
    def _init_api(self) -> AmazonProductAPI:
        """初始化Amazon Product API"""
        access_key = os.getenv("AMAZON_ACCESS_KEY")
        secret_key = os.getenv("AMAZON_SECRET_KEY")
        partner_tag = os.getenv("AMAZON_PARTNER_TAG")
        
        if not all([access_key, secret_key, partner_tag]):
            raise ValueError("缺少必要的Amazon PA-API凭证")
            
        return AmazonProductAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag
        )
        
    async def _execute_crawler(self, job_id: str, crawler_type: str, max_items: int):
        """执行爬虫任务"""
        try:
            logger.info(f"开始执行任务 {job_id} - {crawler_type}")
            start_time = datetime.now()
            
            # 创建任务配置
            config = Config(
                max_items=max_items,
                batch_size=10,
                timeout=30,
                headless=True
            )
            
            # 根据类型执行不同的爬虫
            if crawler_type == "bestseller":
                result = await crawl_bestseller_products(
                    self.api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
            elif crawler_type == "coupon":
                result = await crawl_coupon_products(
                    self.api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
            else:
                raise ValueError(f"不支持的爬虫类型: {crawler_type}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.success(
                f"任务 {job_id} 完成! "
                f"采集数量: {result}, "
                f"耗时: {duration:.2f}秒"
            )
            
        except Exception as e:
            logger.error(f"任务 {job_id} 执行失败: {str(e)}")
            
    def add_job(self, job_config: Dict[str, Any]):
        """添加定时任务"""
        job_id = job_config["id"]
        job_type = job_config["type"]
        
        # 创建触发器
        if job_type == "cron":
            trigger = CronTrigger(
                hour=job_config.get("hour", "*"),
                minute=job_config.get("minute", "0"),
                timezone=self.config['scheduler']['timezone']
            )
        elif job_type == "interval":
            trigger = IntervalTrigger(
                hours=job_config.get("hours", 0),
                minutes=job_config.get("minutes", 0),
                timezone=self.config['scheduler']['timezone']
            )
        else:
            raise ValueError(f"不支持的任务类型: {job_type}")
            
        # 添加任务
        self.scheduler.add_job(
            self._execute_crawler,
            trigger=trigger,
            id=job_id,
            args=[
                job_id,
                job_config["crawler_type"],
                job_config.get("max_items", 100)
            ],
            replace_existing=True
        )
        
        logger.info(f"已添加任务: {job_id}")
        
    def start(self):
        """启动调度器"""
        try:
            # 添加配置的任务
            for job_config in self.config['scheduler']['jobs']:
                self.add_job(job_config)
                
            # 启动调度器
            self.scheduler.start()
            logger.success("调度器已启动")
            
        except Exception as e:
            logger.error(f"启动调度器失败: {str(e)}")
            raise
            
    def stop(self):
        """停止调度器"""
        try:
            self.scheduler.shutdown()
            logger.info("调度器已停止")
        except Exception as e:
            logger.error(f"停止调度器失败: {str(e)}")

async def main():
    """主函数"""
    try:
        # 获取配置文件路径
        config_path = "config/app.yaml"
        
        # 创建调度器管理器
        scheduler_manager = SchedulerManager(config_path)
        
        # 启动调度器
        scheduler_manager.start()
        
        # 保持程序运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("正在关闭调度器...")
        scheduler_manager.stop()
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        
if __name__ == "__main__":
    asyncio.run(main()) 