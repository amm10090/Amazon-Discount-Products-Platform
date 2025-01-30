import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger
from pathlib import Path

Base = declarative_base()

class JobHistoryModel(Base):
    """任务执行历史记录数据库模型"""
    __tablename__ = 'job_history'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(50), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    status = Column(String(20), nullable=False, index=True)
    items_collected = Column(Integer, default=0)
    error = Column(Text)
    
    # 添加索引以提高查询性能
    __table_args__ = (
        Index('idx_job_id', 'job_id'),
        Index('idx_start_time', 'start_time'),
        Index('idx_status', 'status'),
    )

class SchedulerManager:
    """调度器管理器"""
    _instance = None
    _initialized = False
    _scheduler = None
    _db_path = None  # 将在初始化时设置
    _timezone = os.getenv('SCHEDULER_TIMEZONE', 'Asia/Shanghai')
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            # 优先使用环境变量中的数据库路径
            if "SCHEDULER_DB_PATH" in os.environ:
                db_file = os.environ["SCHEDULER_DB_PATH"]
                self._db_path = f"sqlite:///{db_file}"
            else:
                # 默认路径
                data_dir = Path(__file__).parent.parent / "data" / "db"
                data_dir.mkdir(parents=True, exist_ok=True)
                self._db_path = f"sqlite:///{data_dir}/scheduler.db"
            
            self._setup_database()
            self._init_scheduler()
            SchedulerManager._initialized = True
    
    def _setup_database(self):
        """设置数据库"""
        engine = create_engine(self._db_path)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
    
    def _init_scheduler(self):
        """初始化调度器"""
        if SchedulerManager._scheduler is None:
            jobstores = {
                'default': SQLAlchemyJobStore(url=self._db_path)
            }
            
            SchedulerManager._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                timezone=pytz.timezone(self._timezone)
            )
            
            # 如果调度器未运行，则启动它
            if not SchedulerManager._scheduler.running:
                SchedulerManager._scheduler.start()
    
    @property
    def scheduler(self):
        """获取调度器实例"""
        return SchedulerManager._scheduler
    
    @staticmethod
    async def _crawl_products(crawler_type: str, max_items: int):
        """执行爬虫任务
        
        Args:
            crawler_type: 爬虫类型 (bestseller/coupon/all)
            max_items: 最大采集数量
            
        Returns:
            int: 采集到的商品数量
        """
        from core.collect_products import Config, crawl_bestseller_products, crawl_coupon_products
        from core.amazon_product_api import AmazonProductAPI
        
        # 检查必要的环境变量
        required_env_vars = ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"]
        for var in required_env_vars:
            if not os.getenv(var):
                raise ValueError(f"缺少必要的环境变量: {var}")
        
        # 初始化API客户端
        api = AmazonProductAPI(
            access_key=os.getenv("AMAZON_ACCESS_KEY"),
            secret_key=os.getenv("AMAZON_SECRET_KEY"),
            partner_tag=os.getenv("AMAZON_PARTNER_TAG")
        )
        
        # 从环境变量读取配置参数
        config = Config(
            max_items=max_items,
            batch_size=int(os.getenv("CRAWLER_BATCH_SIZE", "10")),
            timeout=int(os.getenv("CRAWLER_TIMEOUT", "30")),
            headless=os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
        )
        
        logger.info(f"爬虫配置: {config}")
        
        try:
            # 根据类型执行不同的爬虫
            if crawler_type == "bestseller":
                return await crawl_bestseller_products(
                    api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
            elif crawler_type == "coupon":
                return await crawl_coupon_products(
                    api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
            elif crawler_type == "all":
                bestseller_items = await crawl_bestseller_products(
                    api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
                coupon_items = await crawl_coupon_products(
                    api,
                    config.max_items,
                    config.batch_size,
                    config.timeout,
                    config.headless
                )
                return bestseller_items + coupon_items
            else:
                raise ValueError(f"不支持的爬虫类型: {crawler_type}")
                
        except Exception as e:
            logger.error(f"爬虫执行失败: {str(e)}")
            raise

    @staticmethod
    def _execute_job(job_id: str, crawler_type: str, max_items: int):
        """执行任务"""
        import asyncio
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        try:
            # 优先使用环境变量中的数据库路径
            if "SCHEDULER_DB_PATH" in os.environ:
                db_file = os.environ["SCHEDULER_DB_PATH"]
                db_path = f"sqlite:///{db_file}"
            else:
                # 默认路径
                data_dir = Path(__file__).parent.parent / "data" / "db"
                data_dir.mkdir(parents=True, exist_ok=True)
                db_path = f"sqlite:///{data_dir}/scheduler.db"
            
            logger.info(f"使用数据库路径: {db_path}")
            
            # 创建数据库引擎和会话
            engine = create_engine(db_path)
            Base.metadata.create_all(engine)  # 确保表已创建
            Session = sessionmaker(bind=engine)
            session = Session()
            
            # 创建历史记录
            history = JobHistoryModel(
                job_id=job_id,
                start_time=datetime.now(),
                status='running'
            )
            session.add(history)
            session.commit()
            
            try:
                logger.info(f"开始执行爬虫任务: {crawler_type}, 目标数量: {max_items}")
                
                # 创建新的事件循环来运行异步任务
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 执行爬虫任务
                items_collected = loop.run_until_complete(
                    SchedulerManager._crawl_products(crawler_type, max_items)
                )
                
                logger.info(f"爬虫任务完成，收集到 {len(items_collected)} 个商品")
                
                # 更新历史记录
                history.end_time = datetime.now()
                history.status = 'completed'
                history.result = f"成功收集 {len(items_collected)} 个商品"
                session.commit()
                
                # 关闭事件循环
                loop.close()
                
            except Exception as e:
                logger.error(f"爬虫任务执行失败: {str(e)}")
                history.end_time = datetime.now()
                history.status = 'failed'
                history.result = f"执行失败: {str(e)}"
                session.commit()
                raise
            
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"任务执行失败: {str(e)}")
            raise

    def add_job(self, job_config: Dict[str, Any]):
        """添加新任务"""
        job_id = job_config["id"]
        job_type = job_config["type"]
        
        # 创建触发器
        if job_type == "cron":
            trigger = CronTrigger(
                hour=job_config.get("hour", "*"),
                minute=job_config.get("minute", "0"),
                timezone=self.scheduler.timezone
            )
        elif job_type == "interval":
            trigger = IntervalTrigger(
                hours=job_config.get("hours", 0),
                minutes=job_config.get("minutes", 0),
                timezone=self.scheduler.timezone
            )
        else:
            raise ValueError(f"不支持的任务类型: {job_type}")
        
        # 添加任务
        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job_id,
            args=[
                job_id,
                job_config["crawler_type"],
                job_config["max_items"]
            ],
            replace_existing=True
        )
        
        logger.info(f"已添加任务: {job_id}")
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        try:
            jobs = []
            for job in self.scheduler.get_jobs():
                job_info = {
                    "id": job.id,
                    "type": "cron" if isinstance(job.trigger, CronTrigger) else "interval",
                    "crawler_type": job.args[1] if len(job.args) > 1 else None,
                    "max_items": job.args[2] if len(job.args) > 2 else 100,
                    "next_run_time": job.next_run_time.timestamp() if job.next_run_time else None,
                    "paused": job.next_run_time is None
                }
                
                # 添加触发器特定的信息
                if isinstance(job.trigger, CronTrigger):
                    job_info.update({
                        "hour": str(job.trigger.fields[5]),  # hour field
                        "minute": str(job.trigger.fields[4])  # minute field
                    })
                else:  # IntervalTrigger
                    total_seconds = job.trigger.interval.total_seconds()
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    job_info.update({
                        "hours": hours,
                        "minutes": minutes
                    })
                
                jobs.append(job_info)
            
            return jobs
            
        except Exception as e:
            logger.error(f"获取任务列表失败: {str(e)}")
            return []
    
    def remove_job(self, job_id: str):
        """删除任务"""
        self.scheduler.remove_job(job_id)
        logger.info(f"已删除任务: {job_id}")
    
    def pause_job(self, job_id: str):
        """暂停任务"""
        self.scheduler.pause_job(job_id)
        logger.info(f"已暂停任务: {job_id}")
    
    def resume_job(self, job_id: str):
        """恢复任务"""
        self.scheduler.resume_job(job_id)
        logger.info(f"已恢复任务: {job_id}")
    
    def get_job_history(self, job_id: str) -> List[Dict[str, Any]]:
        """获取任务执行历史"""
        session = self.Session()
        try:
            history = session.query(JobHistoryModel)\
                .filter_by(job_id=job_id)\
                .order_by(JobHistoryModel.start_time.desc())\
                .limit(10)\
                .all()
            
            return [{
                "start_time": h.start_time,
                "end_time": h.end_time,
                "status": h.status,
                "items_collected": h.items_collected,
                "error": h.error
            } for h in history]
        finally:
            session.close()
    
    def get_timezone(self) -> str:
        """获取当前时区"""
        return self._timezone
    
    def set_timezone(self, timezone: str) -> bool:
        """设置时区
        
        Args:
            timezone: 新的时区名称
            
        Returns:
            bool: 是否设置成功
        """
        try:
            # 验证时区是否有效
            pytz.timezone(timezone)
            
            # 保存当前的任务配置
            jobs_config = []
            for job in self.scheduler.get_jobs():
                config = {
                    "id": job.id,
                    "type": "cron" if isinstance(job.trigger, CronTrigger) else "interval",
                    "crawler_type": job.args[1],
                    "max_items": job.args[2]
                }
                
                if isinstance(job.trigger, CronTrigger):
                    config.update({
                        "hour": str(job.trigger.fields[5]),
                        "minute": str(job.trigger.fields[4])
                    })
                else:
                    total_seconds = job.trigger.interval.total_seconds()
                    config.update({
                        "hours": int(total_seconds // 3600),
                        "minutes": int((total_seconds % 3600) // 60)
                    })
                jobs_config.append(config)
            
            # 停止调度器
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
            
            # 更新时区
            SchedulerManager._timezone = timezone
            os.environ['SCHEDULER_TIMEZONE'] = timezone
            SchedulerManager._scheduler = None
            
            # 重新初始化调度器
            self._init_scheduler()
            
            # 重新添加任务
            for job_config in jobs_config:
                self.add_job(job_config)
            
            logger.info(f"时区已更新为: {timezone}")
            return True
            
        except Exception as e:
            logger.error(f"设置时区失败: {str(e)}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        running_jobs = len([job for job in self.scheduler.get_jobs() if not getattr(job, 'next_run_time', None) is None])
        return {
            'running': self.scheduler.running if self.scheduler else False,
            'running_jobs': running_jobs,
            'total_jobs': len(self.scheduler.get_jobs()),
            'timezone': self._timezone
        }
    
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("调度器已启动")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("调度器已停止")
    
    def reload(self):
        """重新加载调度器"""
        self.stop()
        self._init_scheduler()
        logger.info("调度器已重新加载")

    def execute_job_now(self, job_id: str):
        """立即执行任务
        
        Args:
            job_id: 任务ID
            
        Raises:
            ValueError: 任务不存在时抛出
        """
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                raise ValueError(f"任务 {job_id} 不存在")
            
            # 获取任务参数
            crawler_type = job.args[1]
            max_items = job.args[2]
            
            # 在后台执行任务
            import threading
            thread = threading.Thread(
                target=self._execute_job,
                args=[job_id, crawler_type, max_items]
            )
            thread.start()
            
            logger.info(f"已开始执行任务: {job_id}")
            
        except Exception as e:
            logger.error(f"立即执行任务 {job_id} 失败: {str(e)}")
            raise 