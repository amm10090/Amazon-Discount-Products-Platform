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
from src.core.cj_products_crawler import CJProductsCrawler

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
        # 使用环境变量中的日志目录，如果未设置则使用项目根目录下的logs目录
        log_dir = Path(os.getenv("APP_LOG_DIR", str(Path(project_root) / "logs"))).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 移除默认处理器
        logger.remove()
        
        # 添加控制台处理器（带颜色）
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            colorize=True
        )
        
        # 添加文件处理器（不带颜色）
        logger.add(
            log_dir / "scheduler.log",
            rotation="1 day",
            retention="7 days",
            level="INFO",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            colorize=False  # 明确禁用文件日志的颜色
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
                    },
                    {
                        "id": "discount_daily",
                        "type": "interval",
                        "hours": 8,  # 每8小时执行一次
                        "crawler_type": "discount",
                        "max_items": 50  # 每次处理50个商品
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
    async def _execute_crawler(job_id: str, crawler_type: str, max_items: int, config_params: Optional[Dict[str, Any]] = None):
        """执行爬虫任务
        
        根据指定的爬虫类型执行相应的数据采集任务。
        
        Args:
            job_id: 任务ID
            crawler_type: 爬虫类型（bestseller/coupon/update/cj）
            max_items: 最大采集商品数量
            config_params: 额外的配置参数
            
        Raises:
            ValueError: 不支持的爬虫类型
        """
        try:
            logger.info(f"开始执行任务 {job_id} - {crawler_type}")
            start_time = datetime.now()
            
            if crawler_type == "update":
                # 执行商品更新任务
                updater = ProductUpdater()
                
                # 确保使用前端设置的商品更新数量
                if config_params and "batch_size" in config_params:
                    logger.info(f"配置中的batch_size为: {config_params['batch_size']}, 但将使用前端设置的数量: {max_items}")
                    # 修改配置中的batch_size为前端传入的值
                    config_params["batch_size"] = max_items
                
                success_count, failed_count, deleted_count = await updater.run_scheduled_update(batch_size=max_items)
                result = success_count
                logger.success(f"商品更新任务完成，成功更新 {success_count}/{success_count + failed_count} 个商品，删除 {deleted_count} 个商品")
            elif crawler_type == "discount":
                # 执行折扣商品爬虫任务
                from src.core.discount_scraper_mt import CouponScraperMT
                
                # 检查是否有自定义配置
                if config_params:
                    logger.info(f"使用自定义优惠券爬虫配置: {config_params}")
                    # 创建折扣爬虫实例，使用自定义配置
                    scraper = CouponScraperMT(
                        num_threads=config_params.get("num_threads", int(os.getenv("DISCOUNT_SCRAPER_THREADS", "4"))),
                        batch_size=max_items,
                        headless=config_params.get("headless", os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"),
                        min_delay=config_params.get("min_delay", float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0"))),
                        max_delay=config_params.get("max_delay", float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0"))),
                        update_interval=config_params.get("update_interval", int(os.getenv("DISCOUNT_SCRAPER_UPDATE_INTERVAL", "24"))),
                        force_update=config_params.get("force_update", os.getenv("DISCOUNT_SCRAPER_FORCE_UPDATE", "false").lower() == "true"),
                        debug=config_params.get("debug", os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true"),
                        log_to_console=config_params.get("log_to_console", os.getenv("DISCOUNT_SCRAPER_LOG_TO_CONSOLE", "false").lower() == "true"),
                        file_use_colors=False  # 明确设置文件日志不使用颜色
                    )
                else:
                    # 使用默认配置
                    logger.info("使用默认优惠券爬虫配置")
                    scraper = CouponScraperMT(
                        num_threads=int(os.getenv("DISCOUNT_SCRAPER_THREADS", "4")),
                        batch_size=max_items,
                        headless=os.getenv("CRAWLER_HEADLESS", "true").lower() == "true",
                        min_delay=float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0")),
                        max_delay=float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0")),
                        update_interval=int(os.getenv("DISCOUNT_SCRAPER_UPDATE_INTERVAL", "24")),
                        force_update=os.getenv("DISCOUNT_SCRAPER_FORCE_UPDATE", "false").lower() == "true",
                        debug=os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true",
                        log_to_console=os.getenv("DISCOUNT_SCRAPER_LOG_TO_CONSOLE", "false").lower() == "true",
                        file_use_colors=False  # 明确设置文件日志不使用颜色
                    )
                
                # 运行爬虫
                scraper.run()
                
                # 获取统计数据
                stats = scraper.stats.get()
                result = stats['success_count']
                logger.success(f"折扣商品爬取完成，处理: {stats['processed_count']}，成功: {result}，失败: {stats['failure_count']}")
            elif crawler_type == "coupon_details":
                # 执行优惠券详情抓取任务
                from src.core.discount_scraper_mt import check_and_scrape_coupon_details
                
                # 检查是否有自定义配置
                num_threads = 2  # 默认使用较少线程，避免触发Amazon反爬
                headless = True
                min_delay = 2.0
                max_delay = 4.0
                debug = False
                
                if config_params and "coupon_details_config" in config_params:
                    coupon_details_config = config_params.get("coupon_details_config", {})
                    logger.info(f"使用自定义优惠券详情抓取配置: {coupon_details_config}")
                    num_threads = coupon_details_config.get("num_threads", int(os.getenv("DISCOUNT_SCRAPER_THREADS", "2")))
                    headless = coupon_details_config.get("headless", os.getenv("CRAWLER_HEADLESS", "true").lower() == "true")
                    min_delay = coupon_details_config.get("min_delay", float(os.getenv("DISCOUNT_SCRAPER_MIN_DELAY", "2.0")))
                    max_delay = coupon_details_config.get("max_delay", float(os.getenv("DISCOUNT_SCRAPER_MAX_DELAY", "4.0")))
                    debug = coupon_details_config.get("debug", os.getenv("DISCOUNT_SCRAPER_DEBUG", "false").lower() == "true")
                else:
                    logger.info("使用默认优惠券详情抓取配置")
                
                # 运行优惠券详情抓取（使用None让函数自动选择商品）
                processed_count, updated_count = check_and_scrape_coupon_details(
                    asins=None,  # 使用优化的商品选择逻辑
                    batch_size=max_items,
                    num_threads=num_threads,
                    headless=headless,
                    min_delay=min_delay,
                    max_delay=max_delay,
                    debug=debug
                )
                
                result = updated_count
                logger.success(f"优惠券详情抓取完成，处理: {processed_count}，成功更新: {updated_count}")
            elif crawler_type == "cj":
                # 执行CJ爬虫任务
                # 获取数据库会话
                db = SessionLocal()
                try:
                    # 创建CJ爬虫实例
                    crawler = CJProductsCrawler()
                    
                    # 检查配置参数
                    use_parallel = config_params.get("use_parallel", True) if config_params else True
                    workers = config_params.get("workers", 3) if config_params else 3
                    use_random_cursor = config_params.get("use_random_cursor", False) if config_params else False
                    skip_existing = config_params.get("skip_existing", True) if config_params else True
                    
                    if use_parallel:
                        # 使用并行抓取
                        logger.info(f"使用并行抓取模式，工作进程数: {workers}")
                        success, fail, variants, coupon, discount = await crawler.fetch_all_products_parallel(
                            db=db,
                            max_items=max_items,
                            max_workers=workers,
                            skip_existing=skip_existing,
                            filter_similar_variants=True
                        )
                    else:
                        # 使用串行抓取
                        logger.info("使用串行抓取模式")
                        success, fail, variants, coupon, discount = await crawler.fetch_all_products(
                            db=db,
                            max_items=max_items,
                            use_random_cursor=use_random_cursor,
                            skip_existing=skip_existing,
                            use_persistent_cursor=True
                        )
                        
                    logger.success(f"CJ商品爬取完成，成功：{success}，失败：{fail}，优惠券：{coupon}，折扣：{discount}，变体：{variants}")
                    result = success
                finally:
                    db.close()
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
            ValueError: 不支持的任务类型或无效的任务ID
        """
        # 检查任务ID是否有效
        job_id = job_config.get("id")
        if not job_id or not isinstance(job_id, str) or job_id.strip() == "":
            logger.error(f"添加任务失败: 任务ID不能为空")
            raise ValueError("任务ID不能为空")
            
        job_id = job_id.strip()  # 去除可能的前后空格
        job_type = job_config["type"]
        
        logger.info(f"正在添加任务: {job_id}，类型: {job_type}")
        
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
            error_msg = f"不支持的任务类型: {job_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        # 准备任务参数
        args = [
            job_id,
            job_config["crawler_type"],
            job_config.get("max_items", 100)
        ]
        
        # 添加配置参数
        config_params = {}
        if "updater_config" in job_config:
            config_params = job_config["updater_config"]
        elif "discount_config" in job_config:
            config_params = job_config["discount_config"]
            
        # 如果有配置参数，添加到args
        if config_params:
            args.append(config_params)
            logger.info(f"任务 {job_id} 添加了自定义配置参数: {config_params}")
        else:
            logger.info(f"任务 {job_id} 使用默认配置")
            
        try:
            # 添加任务，使用静态方法
            self.scheduler.add_job(
                SchedulerManager._execute_crawler,
                trigger=trigger,
                id=job_id,
                args=args,
                replace_existing=True
            )
            
            logger.info(f"成功添加任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"添加任务 {job_id} 失败: {str(e)}", exc_info=True)
            raise

    def execute_job_now(self, job_id: str):
        """立即执行任务
        
        Args:
            job_id: 任务ID
            
        Raises:
            ValueError: 任务不存在时抛出
        """
        logger.info(f"正在立即执行任务：{job_id}")
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                raise ValueError(f"任务 {job_id} 不存在")
            
            # 获取任务参数
            crawler_type = job.args[1]
            max_items = job.args[2]
            
            logger.info(f"开始执行任务 {job_id}，类型：{crawler_type}，目标数量：{max_items}")
            
            # 在后台执行任务
            import threading
            # 检查是否有额外配置参数
            config_params = job.args[3] if len(job.args) > 3 else None
            thread = threading.Thread(
                target=self._execute_job,
                args=[job_id, crawler_type, max_items, config_params]
            )
            thread.start()
            
            logger.info(f"任务 {job_id} 已在后台开始执行")
            
        except Exception as e:
            logger.error(f"立即执行任务 {job_id} 失败: {str(e)}")
            # 添加异常堆栈跟踪以便调试
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
            raise

    @staticmethod
    def _execute_job(job_id: str, crawler_type: str, max_items: int, config_params: Optional[Dict[str, Any]] = None):
        """执行任务"""
        import asyncio
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.core.product_updater import TaskLogContext
        from models.scheduler import Base
        
        try:
            with TaskLogContext(task_id=job_id) as task_log:
                task_log.info(f"开始执行任务，类型：{crawler_type}，目标数量：{max_items}")
                if config_params:
                    task_log.info(f"使用自定义配置参数: {config_params}")
                
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
                    # 创建事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 执行实际的任务
                    result = loop.run_until_complete(SchedulerManager._execute_crawler(job_id, crawler_type, max_items, config_params))
                    
                    # 更新历史记录
                    history.end_time = datetime.now()
                    history.status = 'success'
                    history.items_collected = result
                    session.commit()
                    
                    task_log.success(f"任务执行成功，采集数量: {result}")
                    return result
                except Exception as e:
                    # 更新失败状态
                    history.end_time = datetime.now()
                    history.status = 'failed'
                    history.error = str(e)
                    session.commit()
                    
                    task_log.error(f"任务执行失败: {str(e)}")
                    raise
                finally:
                    session.close()
        except Exception as e:
            task_log.error(f"任务执行出错: {str(e)}")
            import traceback
            task_log.error(f"错误详情: {traceback.format_exc()}")
            raise

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