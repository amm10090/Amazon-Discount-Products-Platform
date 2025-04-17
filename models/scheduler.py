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
import logging
from logging.handlers import RotatingFileHandler
from src.core.product_updater import TaskLogContext
# 导入CJ产品爬虫
from src.core.cj_products_crawler import CJProductsCrawler

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent

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
    _db_path = None
    _timezone = os.getenv('SCHEDULER_TIMEZONE', 'Asia/Shanghai')
    _logger = None  # 添加日志记录器引用
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            # 初始化日志记录器
            self._setup_logger()
            
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
            
            self._logger.info("调度器管理器初始化完成")
    
    def _setup_logger(self):
        """设置日志记录器"""
        # 使用环境变量中的日志目录，如果未设置则使用项目根目录下的logs目录
        log_dir = Path(os.getenv("APP_LOG_DIR", str(Path(project_root) / "logs"))).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置调度器专用日志
        scheduler_log_file = log_dir / "scheduler.log"
        
        # 创建日志记录器
        logger = logging.getLogger("SchedulerManager")
        logger.setLevel(logging.INFO)
        
        # 移除现有的处理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # 创建文件处理器
        file_handler = RotatingFileHandler(
            scheduler_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # 设置格式化器
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        
        # 保存日志记录器引用
        self._logger = logger
    
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
    async def _crawl_products(crawler_type: str, max_items: int, updater_config: Optional[Dict[str, Any]] = None):
        """执行爬虫任务
        
        Args:
            crawler_type: 爬虫类型 (bestseller/coupon/all/update/cj)
            max_items: 最大采集数量
            updater_config: 更新器配置参数
            
        Returns:
            int: 采集到的商品数量
        """
        from src.core.collect_products import Config, crawl_bestseller_products, crawl_coupon_products
        from src.core.amazon_product_api import AmazonProductAPI
        from src.core.product_updater import ProductUpdater, UpdateConfiguration, TaskLogContext
        from src.core.cj_products_crawler import CJProductsCrawler
        
        # 检查必要的环境变量
        required_env_vars = ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"]
        for var in required_env_vars:
            if not os.getenv(var):
                raise ValueError(f"缺少必要的环境变量: {var}")
        
        # 从环境变量读取配置参数
        config = Config(
            max_items=max_items,
            batch_size=int(os.getenv("CRAWLER_BATCH_SIZE", "10")),
            timeout=int(os.getenv("CRAWLER_TIMEOUT", "30")),
            headless=os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
        )
        
        async with TaskLogContext(task_id=f"CRAWLER:{crawler_type}") as task_log:
            task_log.info(f"爬虫配置: {config}")
            
            try:
                # 如果是更新任务，使用ProductUpdater
                if crawler_type == "update":
                    # 根据传入的更新器配置创建配置对象
                    if updater_config:
                        task_log.info(f"使用自定义更新器配置: {updater_config}")
                        update_config = UpdateConfiguration(
                            urgent_priority_hours=updater_config.get('urgent_priority_hours', 1),
                            high_priority_hours=updater_config.get('high_priority_hours', 6),
                            medium_priority_hours=updater_config.get('medium_priority_hours', 24),
                            low_priority_hours=updater_config.get('low_priority_hours', 72),
                            very_low_priority_hours=updater_config.get('very_low_priority_hours', 168),
                            batch_size=updater_config.get('batch_size', max_items),
                            max_retries=updater_config.get('max_retries', 3),
                            retry_delay=updater_config.get('retry_delay', 2.0),
                            update_category_info=updater_config.get('update_category_info', False),
                            force_cj_check=updater_config.get('force_cj_check', False),
                            parallel_requests=updater_config.get('parallel_requests', 5)
                        )
                        updater = ProductUpdater(config=update_config)
                    else:
                        task_log.info("使用默认更新器配置")
                        updater = ProductUpdater()
                        
                    await updater.initialize_clients()
                    # 如果传入了batch_size，则使用它，否则使用max_items
                    batch_size = updater_config.get('batch_size', max_items) if updater_config else max_items
                    success_count, failed_count, deleted_count = await updater.run_scheduled_update(batch_size=batch_size)
                    task_log.success(f"商品更新任务完成，成功更新 {success_count}/{success_count + failed_count} 个商品，删除 {deleted_count} 个商品")
                    return success_count
                # 如果是CJ爬虫任务
                elif crawler_type == "cj":
                    # 获取数据库会话
                    from models.database import SessionLocal
                    db = SessionLocal()
                    try:
                        # 创建CJ爬虫实例
                        crawler = CJProductsCrawler()
                        # 执行CJ爬虫
                        success, fail, variants, coupon, discount = await crawler.fetch_all_products(
                            db=db,
                            max_items=max_items,
                            use_random_cursor=True,
                            skip_existing=True
                        )
                        task_log.success(f"CJ商品爬取完成，成功：{success}，失败：{fail}，优惠券：{coupon}，折扣：{discount}，变体：{variants}")
                        return success
                    finally:
                        db.close()
                # 折扣商品爬虫
                elif crawler_type == "discount":
                    from src.core.discount_scraper_mt import CouponScraperMT
                    # 导入需要的模块
                    task_log.info(f"启动优惠券更新爬虫，批量大小: {max_items}")
                    
                    try:
                        # 记录完整的配置信息
                        task_log.info(f"完整配置参数: {updater_config}")
                        
                        # 创建折扣爬虫并设置参数
                        if updater_config:
                            # 检查是否存在discount_config配置
                            discount_config = None
                            if isinstance(updater_config, dict):
                                # 直接在updater_config字典中查找discount_config
                                if "discount_config" in updater_config:
                                    discount_config = updater_config["discount_config"]
                                    task_log.info(f"从updater_config中解析出discount_config: {discount_config}")
                                # 或者updater_config本身就是discount_config
                                elif "num_threads" in updater_config or "force_update" in updater_config:
                                    discount_config = updater_config
                                    task_log.info(f"将updater_config作为discount_config使用: {discount_config}")
                            
                            if discount_config:
                                task_log.info(f"使用自定义优惠券更新爬虫配置: {discount_config}")
                                scraper = CouponScraperMT(
                                    num_threads=discount_config.get("num_threads", int(os.getenv("DISCOUNT_SCRAPER_THREADS", "4"))),
                                    batch_size=max_items,
                                    headless=discount_config.get("headless", os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"),
                                    min_delay=discount_config.get("min_delay", float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0"))),
                                    max_delay=discount_config.get("max_delay", float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0"))),
                                    update_interval=discount_config.get("update_interval", int(os.getenv("DISCOUNT_SCRAPER_UPDATE_INTERVAL", "24"))),
                                    force_update=discount_config.get("force_update", os.getenv("DISCOUNT_SCRAPER_FORCE_UPDATE", "false").lower() == "true"),
                                    debug=discount_config.get("debug", os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true"),
                                    log_to_console=discount_config.get("log_to_console", os.getenv("DISCOUNT_SCRAPER_LOG_TO_CONSOLE", "false").lower() == "true")
                                )
                            else:
                                # 使用默认配置
                                task_log.info("未找到优惠券更新爬虫配置，使用默认配置")
                                scraper = CouponScraperMT(
                                    num_threads=int(os.getenv("DISCOUNT_SCRAPER_THREADS", "4")),
                                    batch_size=max_items,
                                    headless=os.getenv("CRAWLER_HEADLESS", "true").lower() == "true",
                                    min_delay=float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0")),
                                    max_delay=float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0")),
                                    update_interval=int(os.getenv("DISCOUNT_SCRAPER_UPDATE_INTERVAL", "24")),
                                    force_update=os.getenv("DISCOUNT_SCRAPER_FORCE_UPDATE", "false").lower() == "true",
                                    debug=os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true",
                                    log_to_console=os.getenv("DISCOUNT_SCRAPER_LOG_TO_CONSOLE", "false").lower() == "true"
                                )
                        else:
                            # 使用默认配置
                            task_log.info("使用默认优惠券更新爬虫配置")
                            scraper = CouponScraperMT(
                                num_threads=int(os.getenv("DISCOUNT_SCRAPER_THREADS", "4")),
                                batch_size=max_items,
                                headless=os.getenv("CRAWLER_HEADLESS", "true").lower() == "true",
                                min_delay=float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0")),
                                max_delay=float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0")),
                                update_interval=int(os.getenv("DISCOUNT_SCRAPER_UPDATE_INTERVAL", "24")),
                                force_update=os.getenv("DISCOUNT_SCRAPER_FORCE_UPDATE", "false").lower() == "true",
                                debug=os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true",
                                log_to_console=os.getenv("DISCOUNT_SCRAPER_LOG_TO_CONSOLE", "false").lower() == "true"
                            )
                        
                        # 运行爬虫
                        task_log.info("开始运行优惠券更新爬虫")
                        scraper.run()
                        
                        # 获取统计数据
                        stats = scraper.stats.get()
                        success_count = stats['success_count']
                        task_log.success(f"优惠券更新爬虫完成，处理: {stats['processed_count']}，成功: {success_count}，失败: {stats['failure_count']}")
                        return success_count
                    except Exception as e:
                        import traceback
                        task_log.error(f"优惠券爬虫执行失败: {str(e)}")
                        task_log.error(f"错误详情: {traceback.format_exc()}")
                        raise
                # 其他爬虫类型
                else:
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
                        task_log.success(f"畅销商品爬取完成，采集到 {result} 个商品")
                        return result
                    elif crawler_type == "coupon":
                        result = await crawl_coupon_products(
                            api,
                            config.max_items,
                            config.batch_size,
                            config.timeout,
                            config.headless
                        )
                        task_log.success(f"优惠券商品爬取完成，采集到 {result} 个商品")
                        return result
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
                        total_items = bestseller_items + coupon_items
                        task_log.success(f"全部商品爬取完成，采集到 {total_items} 个商品")
                        return total_items
                    else:
                        raise ValueError(f"不支持的爬虫类型: {crawler_type}")
                    
            except Exception as e:
                task_log.error(f"爬虫执行失败: {str(e)}")
                raise

    @staticmethod
    def _execute_job(job_id: str, crawler_type: str, max_items: int, config_params: Optional[Dict[str, Any]] = None):
        """执行任务"""
        import asyncio
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.core.product_updater import TaskLogContext
        
        try:
            with TaskLogContext(task_id=job_id) as task_log:
                task_log.info(f"开始执行任务，类型：{crawler_type}，目标数量：{max_items}")
                if config_params:
                    # 记录配置参数信息
                    if "updater_config" in config_params:
                        task_log.info(f"使用自定义更新器配置: {config_params['updater_config']}")
                    if "discount_config" in config_params:
                        task_log.info(f"使用自定义折扣爬虫配置: {config_params['discount_config']}")
                
                # 优先使用环境变量中的数据库路径
                if "SCHEDULER_DB_PATH" in os.environ:
                    db_file = os.environ["SCHEDULER_DB_PATH"]
                    db_path = f"sqlite:///{db_file}"
                else:
                    # 默认路径
                    data_dir = Path(__file__).parent.parent / "data" / "db"
                    data_dir.mkdir(parents=True, exist_ok=True)
                    db_path = f"sqlite:///{data_dir}/scheduler.db"
                
                task_log.info(f"使用数据库路径: {db_path}")
                
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
                    task_log.info("开始执行爬虫")
                    
                    # 创建新的事件循环来运行异步任务
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 执行爬虫任务，传递配置参数
                    items_collected = loop.run_until_complete(
                        SchedulerManager._crawl_products(crawler_type, max_items, config_params)
                    )
                    
                    task_log.success(f"执行完成，采集到 {items_collected} 个商品")
                    
                    # 更新历史记录
                    history.end_time = datetime.now()
                    history.status = 'completed'
                    history.items_collected = items_collected
                    session.commit()
                    
                    # 关闭事件循环
                    loop.close()
                    
                except Exception as e:
                    task_log.error(f"执行失败: {str(e)}")
                    history.end_time = datetime.now()
                    history.status = 'failed'
                    history.error = str(e)
                    session.commit()
                    raise
                
                finally:
                    session.close()
                    
        except Exception as e:
            logger.error(f"任务 {job_id} 执行过程中发生错误: {str(e)}")
            raise

    def add_job(self, job_config: Dict[str, Any]):
        """添加新任务"""
        job_id = job_config["id"]
        job_type = job_config["type"]
        
        self._logger.info(f"正在添加新任务：{job_id}，类型：{job_type}")
        
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
        
        # 处理任务配置参数
        args = [
            job_id,
            job_config["crawler_type"],
            job_config["max_items"]
        ]
        
        # 添加额外的配置参数
        extra_config = {}
        
        # 处理更新器配置
        if "updater_config" in job_config:
            extra_config["updater_config"] = job_config["updater_config"]
            self._logger.info(f"任务 {job_id} 包含updater_config: {job_config['updater_config']}")
            
        # 处理折扣爬虫配置
        if "discount_config" in job_config:
            # 将discount_config直接添加到extra_config根级别
            if job_config["crawler_type"] == "discount":
                # 如果是discount爬虫，把discount_config作为单独参数
                extra_config["discount_config"] = job_config["discount_config"]
                self._logger.info(f"任务 {job_id} 包含discount_config: {job_config['discount_config']}")
            else:
                # 其他类型则放入updater_config
                if "updater_config" not in extra_config:
                    extra_config["updater_config"] = {}
                extra_config["updater_config"]["discount_config"] = job_config["discount_config"]
                self._logger.info(f"任务 {job_id} 的updater_config中添加了discount_config")
        
        # 将所有配置合并为一个参数传递
        args.append(extra_config if extra_config else None)
        
        self._logger.info(f"任务 {job_id} 最终配置参数: {extra_config}")
        
        # 添加任务
        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job_id,
            args=args,
            replace_existing=True
        )
        
        self._logger.info(f"成功添加任务：{job_id}")
    
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
                
                # 添加任务配置参数（如果有的话）
                if len(job.args) > 3 and job.args[3] is not None:
                    config_params = job.args[3]
                    
                    # 添加更新器配置
                    if job_info["crawler_type"] == "update" and isinstance(config_params, dict) and "updater_config" in config_params:
                        job_info["updater_config"] = config_params["updater_config"]
                    
                    # 添加折扣爬虫配置
                    if job_info["crawler_type"] == "discount" and isinstance(config_params, dict):
                        if "discount_config" in config_params:
                            job_info["discount_config"] = config_params["discount_config"]
                
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
        self._logger.info(f"正在删除任务：{job_id}")
        try:
            self.scheduler.remove_job(job_id)
            self._logger.info(f"成功删除任务：{job_id}")
        except Exception as e:
            self._logger.error(f"删除任务 {job_id} 失败: {str(e)}")
            raise
    
    def pause_job(self, job_id: str):
        """暂停任务"""
        self._logger.info(f"正在暂停任务：{job_id}")
        try:
            self.scheduler.pause_job(job_id)
            self._logger.info(f"成功暂停任务：{job_id}")
        except Exception as e:
            self._logger.error(f"暂停任务 {job_id} 失败: {str(e)}")
            raise
    
    def resume_job(self, job_id: str):
        """恢复任务"""
        self._logger.info(f"正在恢复任务：{job_id}")
        try:
            self.scheduler.resume_job(job_id)
            self._logger.info(f"成功恢复任务：{job_id}")
        except Exception as e:
            self._logger.error(f"恢复任务 {job_id} 失败: {str(e)}")
            raise
    
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
        self._logger.info("正在启动调度器")
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                self._logger.info("调度器启动成功")
        except Exception as e:
            self._logger.error(f"启动调度器失败: {str(e)}")
            raise
    
    def stop(self):
        """停止调度器"""
        self._logger.info("正在停止调度器")
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                self._logger.info("调度器已停止")
        except Exception as e:
            self._logger.error(f"停止调度器失败: {str(e)}")
            raise
    
    def reload(self):
        """重新加载调度器"""
        self._logger.info("正在重新加载调度器")
        try:
            self.stop()
            self._init_scheduler()
            self._logger.info("调度器重新加载完成")
        except Exception as e:
            self._logger.error(f"重新加载调度器失败: {str(e)}")
            raise

    def execute_job_now(self, job_id: str):
        """立即执行任务
        
        Args:
            job_id: 任务ID
            
        Raises:
            ValueError: 任务不存在时抛出
        """
        self._logger.info(f"正在立即执行任务：{job_id}")
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                raise ValueError(f"任务 {job_id} 不存在")
            
            # 获取任务参数
            crawler_type = job.args[1]
            max_items = job.args[2]
            
            self._logger.info(f"开始执行任务 {job_id}，类型：{crawler_type}，目标数量：{max_items}")
            
            # 在后台执行任务
            import threading
            # 检查是否有额外配置参数
            config_params = job.args[3] if len(job.args) > 3 else None
            thread = threading.Thread(
                target=self._execute_job,
                args=[job_id, crawler_type, max_items, config_params]
            )
            thread.start()
            
            self._logger.info(f"任务 {job_id} 已在后台开始执行")
            
        except Exception as e:
            self._logger.error(f"立即执行任务 {job_id} 失败: {str(e)}")
            # 添加异常堆栈跟踪以便调试
            import traceback
            self._logger.error(f"异常详情: {traceback.format_exc()}")
            raise 