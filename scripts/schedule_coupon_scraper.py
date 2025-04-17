#!/usr/bin/env python
"""
优惠券信息抓取定时任务脚本
该脚本使用APScheduler设置discount_scraper_mt.py的定时执行任务
"""

import os
import sys
import subprocess
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入日志配置
from src.utils.log_config import get_logger, LogConfig

# 初始化日志
log_dir = os.path.join(project_root, "logs")
os.makedirs(log_dir, exist_ok=True)

log_config = {
    "LOG_LEVEL": "INFO",
    "JSON_LOGS": False,
    "LOG_PATH": log_dir,
    "LOG_FILE": "coupon_scheduler.log",
    "CONSOLE_LOGS": True,
    "ROTATION": "10 MB",
    "RETENTION": "5 days"
}

LogConfig(log_config)
logger = get_logger("CouponScheduler")

def run_coupon_scraper(batch_size=50, threads=4, update_interval=72, force_update=False):
    """
    执行优惠券抓取脚本
    
    Args:
        batch_size: 每批处理的商品数量
        threads: 线程数
        update_interval: 更新间隔(小时)
        force_update: 是否强制更新
    """
    logger.info("开始执行定时优惠券抓取任务")
    
    cmd = [
        sys.executable,
        os.path.join(project_root, "src", "core", "discount_scraper_mt.py"),
        "--batch-size", str(batch_size),
        "--threads", str(threads),
        "--update-interval", str(update_interval)
    ]
    
    if force_update:
        cmd.append("--force-update")
    
    # 添加日志输出到控制台
    cmd.extend(["--log-to-console"])
    
    try:
        logger.info(f"执行命令: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # 实时输出日志
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logger.info(output.strip())
        
        # 获取返回码
        return_code = process.poll()
        if return_code == 0:
            logger.info("优惠券抓取任务执行成功")
        else:
            stderr = process.stderr.read()
            logger.error(f"优惠券抓取任务执行失败，返回码: {return_code}")
            logger.error(f"错误信息: {stderr}")
    
    except Exception as e:
        logger.exception(f"执行优惠券抓取任务时出现异常: {e}")

def main():
    """主函数，设置并启动调度器"""
    logger.info("====================================")
    logger.info("优惠券抓取定时任务调度器启动")
    logger.info("====================================")
    
    scheduler = BlockingScheduler()
    
    # 设置每天凌晨2点执行一次常规更新任务
    scheduler.add_job(
        run_coupon_scraper,
        CronTrigger(hour=2, minute=0),
        kwargs={
            'batch_size': 100,
            'threads': 4,
            'update_interval': 24,
            'force_update': False
        },
        id='daily_coupon_update',
        name='每日优惠券更新',
        replace_existing=True
    )
    
    # 设置每周日凌晨3点执行一次全量更新任务
    scheduler.add_job(
        run_coupon_scraper,
        CronTrigger(day_of_week='sun', hour=3, minute=0),
        kwargs={
            'batch_size': 200,
            'threads': 6,
            'update_interval': 0,
            'force_update': True
        },
        id='weekly_full_update',
        name='每周全量更新',
        replace_existing=True
    )
    
    # 打印任务信息
    logger.info("已配置的定时任务:")
    jobs = scheduler.get_jobs()
    for job in jobs:
        next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"- {job.name}: 下次执行时间 {next_run}")
    
    # 启动调度器
    try:
        logger.info("调度器已启动，按Ctrl+C停止")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止调度器...")
    except Exception as e:
        logger.exception(f"调度器运行过程中发生错误: {e}")
    finally:
        logger.info("调度器已停止")

if __name__ == "__main__":
    main() 