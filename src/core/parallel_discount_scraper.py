"""
并行优惠信息抓取模块
该模块是DiscountScraper的并行优化版本，通过多线程和WebDriver池技术大幅提高抓取速度。

主要功能：
1. 并行抓取多个商品的优惠信息
2. 智能管理WebDriver资源
3. 自适应调整并发度
4. 失败重试机制
"""

import os
import sys
import time
import random
import logging
import argparse
import threading
import traceback
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from tqdm import tqdm
from sqlalchemy import func, text

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from models.database import Product, CouponHistory, Offer, get_db
from src.core.webdriver_pool import WebDriverPool
from src.core.discount_scheduler import DiscountUpdateScheduler, TaskLoggerAdapter
from src.core.discount_scraper import DiscountScraper


class ParallelDiscountScraper:
    """并行优惠信息抓取器"""
    
    def __init__(self, 
                 db: Session, 
                 batch_size: int = 50, 
                 concurrent_workers: int = 5,
                 headless: bool = True,
                 min_delay: float = 1.0, 
                 max_delay: float = 3.0,
                 specific_asins: list = None,
                 use_scheduler: bool = True, 
                 scheduler: DiscountUpdateScheduler = None,
                 retry_count: int = 2,
                 retry_delay: int = 5,
                 before_date: str = None):
        """
        初始化并行抓取器
        
        Args:
            db: 数据库会话
            batch_size: 每批处理的商品数量
            concurrent_workers: 并发工作线程数量
            headless: 是否使用无头模式
            min_delay: 最小请求延迟(秒)
            max_delay: 最大请求延迟(秒)
            specific_asins: 指定要处理的商品ASIN列表
            use_scheduler: 是否使用调度器
            scheduler: 调度器实例
            retry_count: 失败重试次数
            retry_delay: 重试间隔(秒)
            before_date: 只处理在指定日期之前创建的商品
        """
        self.db = db
        self.batch_size = batch_size
        self.concurrent_workers = concurrent_workers
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.specific_asins = specific_asins
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.before_date = before_date
        
        # 初始化WebDriver池
        self.driver_pool = None
        
        # 线程本地存储
        self._thread_local = threading.local()
        
        # 初始化日志记录器
        self.logger = TaskLoggerAdapter(logging.getLogger("ParallelScraper"), {'task_id': 'SYSTEM'})
        
        # 初始化调度器
        self.use_scheduler = use_scheduler
        self.scheduler = scheduler if use_scheduler else None
        
        # 统计信息
        self.stats = {
            'start_time': None,
            'end_time': None,
            'processed_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'retry_count': 0,
        }
        
        # 已处理的商品集合，用于去重
        self._processed_asins = set()
        self._lock = threading.Lock()
        
    def _init_driver_pool(self):
        """初始化WebDriver池"""
        if not self.driver_pool:
            self.driver_pool = WebDriverPool(
                size=self.concurrent_workers,
                headless=self.headless,
                min_idle=1
            )
            self.logger.info(f"WebDriver池初始化完成，最大并发数: {self.concurrent_workers}")
            
    def _close_driver_pool(self):
        """关闭WebDriver池"""
        if self.driver_pool:
            self.driver_pool.close_all()
            self.driver_pool = None
            self.logger.info("WebDriver池已关闭")
            
    def process_product(self, product: Product, driver) -> bool:
        """
        处理单个商品的优惠信息
        
        Args:
            product: 商品对象
            driver: WebDriver实例
            
        Returns:
            bool: 处理是否成功
        """
        task_id = f'PROCESS:{product.asin}'
        task_log = TaskLoggerAdapter(logging.getLogger("ParallelScraper"), {'task_id': task_id})
        thread_id = threading.get_ident()
        
        try:
            url = f"https://www.amazon.com/dp/{product.asin}?th=1"
            task_log.info(f"[线程{thread_id}] 开始处理商品: {url}")
            driver.get(url)
            
            # 随机等待1-2秒，模拟人类行为
            wait_time = random.uniform(1, 2)
            time.sleep(wait_time)
            
            # 创建一个临时的DiscountScraper实例，复用其提取方法
            temp_scraper = DiscountScraper(self.db)
            temp_scraper.driver = driver
            
            # 提取折扣信息
            task_log.debug("提取折扣信息...")
            savings, savings_percentage, actual_current_price = temp_scraper._extract_discount_info(product)
            
            # 提取优惠券信息
            task_log.debug("提取优惠券信息...")
            coupon_type, coupon_value = temp_scraper._extract_coupon_info()
            
            # 提取促销标签信息
            task_log.debug("提取促销标签信息...")
            deal_badge = temp_scraper._extract_deal_badge_info()
            
            # 安全处理可能为None的数值
            savings_str = f"${savings:.2f}" if savings is not None else "无"
            percentage_str = f"{savings_percentage}%" if savings_percentage is not None else "无"
            coupon_value_str = str(coupon_value) if coupon_value is not None else "无"
            actual_price_str = f"${actual_current_price:.2f}" if actual_current_price is not None else "无"
            
            # 记录提取到的信息
            task_log.info(
                f"优惠信息提取结果: 折扣={percentage_str}, 节省={savings_str}, "
                f"实际当前价格={actual_price_str}, 优惠券={coupon_type}({coupon_value_str}), 促销={deal_badge}"
            )
            
            # 更新数据库 - 使用本地session
            local_session = next(get_db())
            try:
                # 重新获取商品（避免线程间的session冲突）
                local_product = local_session.query(Product).filter(Product.asin == product.asin).first()
                if local_product:
                    temp_scraper.db = local_session
                    temp_scraper._update_product_discount(
                        local_product, savings, savings_percentage,
                        coupon_type, coupon_value, deal_badge, actual_current_price
                    )
                    local_session.commit()
                    task_log.info(f"商品优惠信息更新成功")
                    return True
                else:
                    task_log.warning(f"在本地会话中未找到商品: {product.asin}")
                    return False
            except Exception as e:
                local_session.rollback()
                task_log.error(f"更新数据库失败: {str(e)}")
                return False
            finally:
                local_session.close()
                
        except Exception as e:
            task_log.error(f"处理失败: {str(e)}")
            task_log.debug(f"异常堆栈: {traceback.format_exc()}")
            return False
            
    def process_asin(self, asin: str, executor=None) -> Tuple[str, bool]:
        """
        处理单个商品ASIN的优惠信息
        
        Args:
            asin: 商品ASIN
            executor: 可选的线程池，用于异步处理
            
        Returns:
            Tuple[str, bool]: (ASIN, 是否成功)
        """
        task_id = f'ASIN:{asin}'
        task_log = TaskLoggerAdapter(logging.getLogger("ParallelScraper"), {'task_id': task_id})
        thread_id = threading.get_ident()
        
        # 检查是否已经处理过
        with self._lock:
            if asin in self._processed_asins:
                task_log.warning(f"[线程{thread_id}] 商品已处理过，跳过: {asin}")
                return asin, False
            self._processed_asins.add(asin)
            
        # 获取WebDriver
        driver = None
        try:
            driver = self.driver_pool.get_driver()
            if not driver:
                task_log.error(f"[线程{thread_id}] 无法获取WebDriver实例，放弃处理: {asin}")
                return asin, False
                
            # 尝试从数据库获取商品
            task_log.info(f"[线程{thread_id}] 查询数据库中的商品信息")
            local_session = next(get_db())
            try:
                product = local_session.query(Product).filter(Product.asin == asin).first()
                
                # 如果数据库中不存在该商品，则创建一个新的记录
                if not product:
                    task_log.info(f"[线程{thread_id}] 数据库中不存在商品，创建新记录")
                    product = Product(asin=asin, created_at=datetime.now(UTC))
                    local_session.add(product)
                    local_session.flush()  # 刷新以获取ID，但不提交
                    
                # 处理商品优惠信息
                success = self.process_product(product, driver)
                if success:
                    local_session.commit()
                else:
                    local_session.rollback()
                
                return asin, success
                
            except Exception as e:
                local_session.rollback()
                task_log.error(f"[线程{thread_id}] 处理异常: {str(e)}")
                return asin, False
            finally:
                local_session.close()
                
        except Exception as e:
            task_log.error(f"[线程{thread_id}] 处理出错: {str(e)}")
            return asin, False
        finally:
            # 释放WebDriver
            if driver:
                self.driver_pool.release_driver(driver)
                
    def process_batch_parallel(self, asins_to_process: List[str]) -> List[Tuple[str, bool]]:
        """
        并行处理一批商品
        
        Args:
            asins_to_process: 待处理的ASIN列表
            
        Returns:
            List[Tuple[str, bool]]: 处理结果列表，每个元素为(ASIN, 是否成功)
        """
        results = []
        failed_asins = []
        retry_count = 0
        
        # 使用ThreadPoolExecutor进行并行处理
        with ThreadPoolExecutor(max_workers=self.concurrent_workers) as executor:
            # 第一次处理
            future_to_asin = {executor.submit(self.process_asin, asin): asin for asin in asins_to_process}
            
            for future in as_completed(future_to_asin):
                asin = future_to_asin[future]
                try:
                    asin, success = future.result()
                    results.append((asin, success))
                    
                    with self._lock:
                        self.stats['processed_count'] += 1
                        if success:
                            self.stats['success_count'] += 1
                        else:
                            self.stats['failure_count'] += 1
                            failed_asins.append(asin)
                            
                except Exception as e:
                    self.logger.error(f"获取任务结果时出错: {str(e)}")
                    results.append((asin, False))
                    failed_asins.append(asin)
                    with self._lock:
                        self.stats['processed_count'] += 1
                        self.stats['failure_count'] += 1
                        
        # 失败重试逻辑
        while failed_asins and retry_count < self.retry_count:
            retry_count += 1
            retry_asins = failed_asins.copy()
            failed_asins = []
            
            self.logger.info(f"第{retry_count}次重试，处理{len(retry_asins)}个失败商品")
            time.sleep(self.retry_delay)  # 重试前等待
            
            # 重试失败的商品
            with ThreadPoolExecutor(max_workers=self.concurrent_workers) as executor:
                future_to_asin = {executor.submit(self.process_asin, asin): asin for asin in retry_asins}
                
                for future in as_completed(future_to_asin):
                    asin = future_to_asin[future]
                    try:
                        asin, success = future.result()
                        
                        # 更新状态
                        for i, (existing_asin, existing_success) in enumerate(results):
                            if existing_asin == asin:
                                results[i] = (asin, success)
                                break
                                
                        with self._lock:
                            self.stats['retry_count'] += 1
                            if success:
                                self.stats['success_count'] += 1
                                self.stats['failure_count'] -= 1
                            else:
                                failed_asins.append(asin)
                                
                    except Exception as e:
                        self.logger.error(f"重试获取任务结果时出错: {str(e)}")
                        failed_asins.append(asin)
            
        return results
                
    def run(self):
        """运行并行抓取器"""
        main_log = TaskLoggerAdapter(logging.getLogger("ParallelScraper"), {'task_id': 'MAIN'})
        self.stats['start_time'] = time.time()
        
        try:
            main_log.info("初始化WebDriver池...")
            self._init_driver_pool()
            
            main_log.info("=====================================================")
            main_log.info("            开始并行优惠信息抓取任务")
            main_log.info("=====================================================")
            main_log.info(f"并发工作线程: {self.concurrent_workers}")
            
            # 处理特定的ASIN列表或按日期过滤或从调度器获取商品
            if self.specific_asins:
                main_log.info(f"将处理指定的 {len(self.specific_asins)} 个商品ASIN")
                asins_to_process = self.specific_asins
            elif self.before_date:
                main_log.info(f"将处理在 {self.before_date} 之前创建的商品")
                # 将字符串日期转换为datetime对象
                try:
                    filter_date = datetime.strptime(self.before_date, "%Y-%m-%d").replace(tzinfo=UTC)
                    main_log.info(f"过滤日期: {filter_date}")
                    
                    # 获取符合条件的商品总数
                    total_count = self.db.query(func.count(Product.id)).filter(
                        Product.created_at < filter_date
                    ).scalar()
                    main_log.info(f"找到 {total_count} 个在 {self.before_date} 之前创建的商品")
                    
                    # 获取指定数量的商品
                    products = self.db.query(Product).filter(
                        Product.created_at < filter_date
                    ).order_by(
                        Product.created_at.asc()
                    ).limit(self.batch_size).all()
                    
                    # 提取ASIN
                    asins_to_process = [p.asin for p in products if p.asin]
                    main_log.info(f"本次将处理 {len(asins_to_process)} 个商品")
                    
                    # 如果没有找到符合条件的商品，输出详细信息以帮助诊断
                    if not asins_to_process:
                        main_log.warning("未找到符合条件的商品，尝试不同的日期或检查商品是否有ASIN")
                        
                        # 获取一些样本商品，分析创建时间
                        sample_products = self.db.query(Product).order_by(
                            Product.created_at.desc()
                        ).limit(5).all()
                        
                        if sample_products:
                            main_log.info("数据库中最新的5个商品:")
                            for p in sample_products:
                                main_log.info(f"ID: {p.id}, ASIN: {p.asin}, 创建时间: {p.created_at}")
                        else:
                            main_log.warning("数据库中没有找到任何商品")
                except ValueError as e:
                    main_log.error(f"日期格式错误: {str(e)}")
                    main_log.info("请使用YYYY-MM-DD格式，例如: 2025-03-25")
                    return
            elif self.use_scheduler:
                main_log.info("使用调度器获取待处理商品...")
                # 更新调度器任务队列
                self.scheduler.update_task_queue()
                
                # 获取任务队列中每个任务的信息（调试用）
                main_log.info("分析任务队列中的任务状态...")
                queue_size = self.scheduler.task_queue.qsize()
                if queue_size > 0:
                    # 创建临时列表，用于存储任务
                    temp_tasks = []
                    current_time = datetime.now(UTC)
                    ready_tasks = 0
                    future_tasks = 0
                    
                    # 遍历任务队列中的所有任务
                    while not self.scheduler.task_queue.empty():
                        task = self.scheduler.task_queue.get()
                        temp_tasks.append(task)
                        
                        # 判断任务是否准备好执行
                        time_diff = (task.next_update_time - current_time).total_seconds() if task.next_update_time else 0
                        if not task.next_update_time or task.next_update_time <= current_time:
                            ready_tasks += 1
                            main_log.debug(f"任务就绪: ASIN={task.asin}, 优先级={task.priority:.2f}, 准备时间=现在")
                        else:
                            future_tasks += 1
                            main_log.debug(f"任务未就绪: ASIN={task.asin}, 优先级={task.priority:.2f}, 剩余时间={time_diff:.0f}秒")
                    
                    # 将任务放回队列
                    for task in temp_tasks:
                        self.scheduler.task_queue.put(task)
                    
                    main_log.info(f"任务队列状态: 就绪任务={ready_tasks}, 未就绪任务={future_tasks}, 总任务数={queue_size}")
                
                # 临时设置强制更新标志，确保能获取到任务
                original_force_update = self.scheduler.force_update
                if queue_size > 0 and ready_tasks == 0:
                    main_log.warning("没有就绪任务，临时启用强制更新模式")
                    self.scheduler.force_update = True
                
                # 获取下一批要处理的商品
                asins_to_process = self.scheduler.get_next_batch()
                
                # 恢复原始强制更新标志
                if queue_size > 0 and ready_tasks == 0:
                    self.scheduler.force_update = original_force_update
                
                main_log.info(f"调度器返回 {len(asins_to_process)} 个待处理商品")
                
                # 添加更详细的日志，记录调度器状态
                scheduler_stats = self.scheduler.get_statistics()
                main_log.info(f"调度器状态: 队列大小={scheduler_stats['queue_size']}, 总任务数={scheduler_stats['total_tasks']}")
                
                # 如果没有商品，但队列中有任务，尝试强制获取一批
                if not asins_to_process and scheduler_stats['queue_size'] > 0:
                    main_log.warning("尝试强制获取任务...")
                    # 临时保存force_update状态
                    original_force_update = self.scheduler.force_update
                    # 强制更新
                    self.scheduler.force_update = True
                    # 再次尝试获取任务
                    asins_to_process = self.scheduler.get_next_batch()
                    # 恢复原始状态
                    self.scheduler.force_update = original_force_update
                    main_log.info(f"强制模式下获取到 {len(asins_to_process)} 个待处理商品")
            else:
                # 获取按创建时间排序的商品
                main_log.info("从数据库获取待处理商品列表...")
                
                # 先检查数据库中的商品总数
                total_products = self.db.query(func.count(Product.id)).scalar()
                main_log.info(f"数据库中共有 {total_products} 个商品记录")
                
                if total_products == 0:
                    main_log.warning("数据库中没有任何商品记录，请先导入商品数据")
                else:
                    # 检查是否有符合条件的商品
                    products_count = self.db.query(func.count(Product.id)).filter(
                        Product.asin.isnot(None)  # ASIN不为空
                    ).scalar()
                    main_log.info(f"数据库中有 {products_count} 个有效ASIN的商品记录")
                
                products = self.db.query(Product).order_by(
                    Product.created_at
                ).limit(self.batch_size).all()
                
                if not products:
                    main_log.warning("未找到任何商品记录，可能的原因:")
                    main_log.warning(" - 数据库中没有商品数据")
                    main_log.warning(" - 商品表结构可能不正确")
                    main_log.warning(" - 数据库连接问题")
                    
                    # 尝试获取表结构信息
                    try:
                        # 尝试检查Product表的列信息
                        column_info = [c.name for c in Product.__table__.columns]
                        main_log.info(f"Product表结构: {column_info}")
                    except Exception as e:
                        main_log.error(f"获取表结构时出错: {str(e)}")
                
                asins_to_process = [p.asin for p in products]
                main_log.info(f"获取到 {len(asins_to_process)} 个待处理商品")
                
                # 如果没有商品，输出详细的调试信息
                if not asins_to_process:
                    # 尝试检查数据库连接
                    try:
                        connection_test = self.db.execute(text("SELECT 1")).scalar()
                        main_log.info(f"数据库连接测试: {'成功' if connection_test == 1 else '失败'}")
                    except Exception as e:
                        main_log.error(f"数据库连接测试失败: {str(e)}")
                
            # 如果没有商品需要处理，提前退出
            if not asins_to_process:
                main_log.warning("没有商品需要处理，任务退出")
                return
                
            # 开始处理
            main_log.info("开始并行处理商品...")
            batch_results = self.process_batch_parallel(asins_to_process)
            
            # 处理调度器反馈
            if self.use_scheduler:
                for asin, success in batch_results:
                    process_time = 0  # 这里可以补充实际处理时间逻辑
                    self.scheduler.record_task_result(asin, success, process_time)
                    
        except Exception as e:
            main_log.error(f"抓取过程发生错误: {str(e)}")
            main_log.debug(f"异常堆栈: {traceback.format_exc()}")
            raise
            
        finally:
            main_log.info("关闭WebDriver池...")
            self._close_driver_pool()
            
            # 输出任务统计信息
            self.stats['end_time'] = time.time()
            duration = self.stats['end_time'] - self.stats['start_time']
            
            main_log.info("=====================================================")
            main_log.info("                  任务完成")
            main_log.info("=====================================================")
            main_log.info(f"任务统计:")
            main_log.info(f"  • 总耗时: {duration:.1f} 秒")
            main_log.info(f"  • 处理商品: {self.stats['processed_count']} 个")
            main_log.info(f"  • 成功更新: {self.stats['success_count']} 个")
            main_log.info(f"  • 失败数量: {self.stats['failure_count']} 个")
            main_log.info(f"  • 重试次数: {self.stats['retry_count']} 次")
            success_rate = (self.stats['success_count']/self.stats['processed_count']*100) if self.stats['processed_count'] > 0 else 0
            main_log.info(f"  • 成功率: {success_rate:.1f}%")
            main_log.info(f"  • 平均速度: {self.stats['processed_count']/duration:.2f} 个/秒" if duration > 0 else "N/A")
            
            # 如果使用调度器，输出调度器统计信息
            if self.use_scheduler:
                scheduler_stats = self.scheduler.get_statistics()
                main_log.info("\n调度器统计:")
                main_log.info(f"  • 总任务数: {scheduler_stats['total_tasks']}")
                main_log.info(f"  • 完成任务: {scheduler_stats['completed_tasks']}")
                main_log.info(f"  • 失败任务: {scheduler_stats['failed_tasks']}")
                main_log.info(f"  • 成功率: {scheduler_stats['success_rate']:.1f}%")
                main_log.info(f"  • 平均处理时间: {scheduler_stats['avg_processing_time']:.2f} 秒")
                main_log.info(f"  • 剩余任务数: {scheduler_stats['queue_size']}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='亚马逊商品优惠信息并行爬虫')
    parser.add_argument('--batch-size', type=int, default=100, help='批处理大小')
    parser.add_argument('--workers', type=int, default=5, help='并发工作线程数')
    parser.add_argument('--no-headless', action='store_true', help='不使用无头模式')
    parser.add_argument('--force-update', action='store_true', help='强制更新所有商品，忽略时间间隔检查')
    parser.add_argument('--test-add-products', action='store_true', help='测试添加样本商品到数据库')
    parser.add_argument('--asin', type=str, help='指定单个ASIN进行处理')
    parser.add_argument('--debug', action='store_true', help='启用调试日志')
    parser.add_argument('--before-date', type=str, help='只处理在指定日期之前创建的商品(格式: YYYY-MM-DD)')
    parser.add_argument('--skip-scheduler', action='store_true', help='跳过调度器，直接按创建时间获取商品')
    args = parser.parse_args()

    # 配置日志级别
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler()]
    )

    # 初始化数据库会话
    db = next(get_db())
    
    # 测试添加样本商品
    if args.test_add_products:
        try:
            print("测试添加样本商品到数据库...")
            # 常见的测试ASIN
            test_asins = [
                "B07ZPKN6YR",  # Echo Dot (4th Gen)
                "B08DFPV5HL",  # Fire TV Stick 4K
                "B07FZ8S74R",  # Echo Show 5
                "B07P6X58BD",  # Kindle Paperwhite
                "B0CFV3HSHF",  # USB C Cable
                "B08HNHTTF1",  # TP-Link WiFi 6 Router
                "B082LZ9GDW",  # Robot Vacuum
                "B00FLYWNYQ",  # Anker PowerCore
                "B07JH1CBGV",  # SAMSUNG EVO Select Micro SD
                "B07XR5TRSZ",  # Apple AirPods Pro
            ]
            
            # 检查数据库中是否已存在这些商品
            for asin in test_asins:
                existing = db.query(Product).filter(Product.asin == asin).first()
                if existing:
                    print(f"商品已存在: {asin}")
                else:
                    # 创建新商品
                    new_product = Product(
                        asin=asin,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC)
                    )
                    db.add(new_product)
                    print(f"添加新商品: {asin}")
            
            db.commit()
            print("样本商品添加完成！")
            
            # 确认添加结果
            product_count = db.query(func.count(Product.id)).scalar()
            print(f"数据库中现有商品总数: {product_count}")
            
            return
        except Exception as e:
            db.rollback()
            print(f"添加样本商品时出错: {str(e)}")
            return
        finally:
            db.close()
    
    # 处理单个ASIN
    specific_asins = None
    if args.asin:
        specific_asins = [args.asin]
        print(f"将只处理指定的ASIN: {args.asin}")
    
    # 初始化调度器
    scheduler = DiscountUpdateScheduler(
        db=db, 
        batch_size=args.batch_size,
        force_update=args.force_update
    )
    
    # 初始化并行爬虫
    scraper = ParallelDiscountScraper(
        db=db,
        batch_size=args.batch_size,
        concurrent_workers=args.workers,
        scheduler=scheduler,
        headless=not args.no_headless,
        specific_asins=specific_asins,
        before_date=args.before_date,
        use_scheduler=not args.skip_scheduler
    )
    
    try:
        # 运行爬虫
        scraper.run()
    except KeyboardInterrupt:
        logging.info("收到中断信号，正在停止爬虫...")
    finally:
        # 关闭数据库连接
        db.close()

if __name__ == "__main__":
    main() 