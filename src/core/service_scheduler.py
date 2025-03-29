"""
定时任务服务调度器模块

该模块提供了一个完整的定时任务调度系统，用于管理和执行Amazon商品数据采集任务。
主要功能包括：
1. 支持cron和interval两种调度方式
2. 支持任务的添加、删除、暂停、恢复
3. 支持任务执行历史记录
4. 支持时区管理
5. 支持多种爬虫类型（畅销商品、优惠券商品等）
"""

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
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
from src.core.collect_products import Config, crawl_bestseller_products, crawl_coupon_products
from src.core.amazon_product_api import AmazonProductAPI
from src.core.product_updater import ProductUpdater, UpdateConfiguration
from models.database import SessionLocal
from models.scheduler import JobHistoryModel

class SchedulerManager:
    """定时任务管理器
    
    该类负责管理所有定时任务的生命周期，包括创建、执行、监控和删除任务。
    使用单例模式确保全局只有一个调度器实例。
    
    属性:
        config (dict): 调度器配置信息
        scheduler (AsyncIOScheduler): APScheduler异步调度器实例
        api (AmazonProductAPI): Amazon商品API客户端实例
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化调度器管理器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """
        self.config = self.load_config(config_path)
        self.scheduler = self._init_scheduler()
        self.api = self._init_api()
        self._setup_logging()
        
    def _setup_logging(self):
        """配置日志系统
        
        设置日志输出格式、轮转策略和保留策略：
        - 按天轮转日志文件
        - 保留最近7天的日志
        - 日志级别为INFO
        - 使用UTF-8编码
        """
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logger.add(
            log_dir / "scheduler.log",
            rotation="1 day",
            retention="7 days",
            level="INFO",
            encoding="utf-8"
        )
        
    def load_config(self, config_path: Optional[str]) -> dict:
        """加载调度器配置
        
        从YAML配置文件加载调度器配置，如果配置文件不存在则使用默认配置。
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            dict: 包含调度器配置的字典
        """
        # 确保data/db目录存在
        data_dir = Path(__file__).parent.parent.parent / "data" / "db"
        data_dir.mkdir(parents=True, exist_ok=True)
        
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
                    },
                    {
                        "id": "product_update",
                        "type": "interval",
                        "hours": 2,  # 每2小时执行一次
                        "crawler_type": "update",
                        "max_items": 100  # 每次更新100个商品
                    }
                ],
                "timezone": "Asia/Shanghai",
                "job_store": {
                    "url": f"sqlite:///{data_dir}/scheduler.db"
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
        """初始化APScheduler调度器
        
        创建并配置APScheduler异步调度器实例：
        - 设置SQLite作为任务存储后端
        - 配置默认时区
        
        Returns:
            AsyncIOScheduler: 配置好的调度器实例
        """
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
        """初始化Amazon Product API客户端
        
        从环境变量获取API凭证并创建API客户端实例。
        
        Returns:
            AmazonProductAPI: API客户端实例
            
        Raises:
            ValueError: 缺少必要的API凭证时抛出
        """
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
        
    @staticmethod
    async def _execute_crawler(job_id: str, crawler_type: str, max_items: int):
        """执行爬虫任务
        
        根据指定的爬虫类型执行相应的数据采集任务。
        
        Args:
            job_id: 任务ID
            crawler_type: 爬虫类型（bestseller/coupon/update）
            max_items: 最大采集商品数量
            
        Raises:
            ValueError: 不支持的爬虫类型
        """
        try:
            logger.info(f"开始执行任务 {job_id} - {crawler_type}")
            start_time = datetime.now()
            
            if crawler_type == "update":
                # 执行商品更新任务
                updater = ProductUpdater()
                success_count, total = await updater.run_scheduled_update(batch_size=max_items)
                result = success_count
                logger.success(f"商品更新任务完成，成功更新 {success_count}/{total} 个商品")
            else:
                # 从环境变量获取配置
                headless = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
                timeout = int(os.getenv("CRAWLER_TIMEOUT", "30"))
                batch_size = int(os.getenv("CRAWLER_BATCH_SIZE", "10"))
                
                # 创建任务配置
                config = Config(
                    max_items=max_items,
                    batch_size=batch_size,
                    timeout=timeout,
                    headless=headless,
                    crawler_types=[crawler_type]  # 设置爬虫类型
                )
                
                # 初始化API客户端
                api = AmazonProductAPI(
                    access_key=os.getenv("AMAZON_ACCESS_KEY"),
                    secret_key=os.getenv("AMAZON_SECRET_KEY"),
                    partner_tag=os.getenv("AMAZON_PARTNER_TAG")
                )
                
                # 根据类型执行不同的爬虫
                if crawler_type == "bestseller":
                    result = await crawl_bestseller_products(
                        api,
                        config.max_items,
                        config.batch_size,
                        config.timeout,
                        config.headless
                    )
                elif crawler_type == "coupon":
                    result = await crawl_coupon_products(
                        api,
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
                f"处理数量: {result}, "
                f"耗时: {duration:.2f}秒"
            )
            
            # 记录任务执行状态
            with SessionLocal() as db:
                job_history = JobHistoryModel(
                    job_id=job_id,
                    start_time=start_time,
                    end_time=datetime.now(),
                    status="success",
                    items_collected=result
                )
                db.add(job_history)
                db.commit()
            
        except Exception as e:
            logger.error(f"任务 {job_id} 执行失败: {str(e)}")
            # 记录失败状态
            with SessionLocal() as db:
                job_history = JobHistoryModel(
                    job_id=job_id,
                    start_time=start_time if 'start_time' in locals() else datetime.now(),
                    end_time=datetime.now(),
                    status="failed",
                    error=str(e)
                )
                db.add(job_history)
                db.commit()
            
    def add_job(self, job_config: Dict[str, Any]):
        """添加定时任务
        
        根据配置添加新的定时任务到调度器。
        
        Args:
            job_config: 任务配置字典，包含任务ID、类型、执行计划等
            
        Raises:
            ValueError: 不支持的任务类型
        """
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
            
        # 添加任务，使用静态方法
        self.scheduler.add_job(
            SchedulerManager._execute_crawler,
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
        """启动调度器
        
        启动调度器并添加配置文件中定义的所有任务。
        """
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
        """停止调度器
        
        安全地关闭调度器，确保所有资源被正确释放。
        """
        try:
            self.scheduler.shutdown()
            logger.info("调度器已停止")
        except Exception as e:
            logger.error(f"停止调度器失败: {str(e)}")

async def main():
    """主函数
    
    创建并启动调度器管理器的入口点。
    处理键盘中断和其他异常。
    """
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