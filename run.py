import os
import sys
import signal
import subprocess
import psutil
from typing import List, Optional
import time
import yaml
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from models.scheduler import SchedulerManager
from loguru import logger

class ServiceManager:
    """服务管理器，用于管理FastAPI、Streamlit和调度器服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.processes: List[subprocess.Popen] = []
        self.config = self.load_config(config_path)
        
        # 设置统一的日志目录
        project_root = Path.cwd()
        self.log_dir = project_root / "logs"
        self.log_dir.mkdir(exist_ok=True)
        # 设置环境变量，让其他模块都使用这个日志目录
        os.environ["APP_LOG_DIR"] = str(self.log_dir)
        
        self.setup_logging()
        self.setup_signal_handlers()
        self.scheduler = None
        self.loop = None
        
    async def init_scheduler(self):
        """异步初始化调度器"""
        if not self.scheduler:
            self.scheduler = SchedulerManager()
            
    def load_config(self, config_path: Optional[str]) -> dict:
        """加载配置文件"""
        default_config = {
            "environment": "production",
            "api": {
                "host": "0.0.0.0",
                "port": 5001,
                "reload": False,
                "workers": 4
            },
            "frontend": {
                "port": 5002,
                "host": "0.0.0.0"
            },
            "logging": {
                "level": "INFO",
                "max_size": 10485760,
                "backup_count": 5
            }
        }
        
        if not config_path:
            print("未指定配置文件路径，使用默认配置")
            return default_config
            
        try:
            config_path = os.path.abspath(config_path)
            print(f"\n正在加载配置文件: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print(f"成功加载配置文件，当前环境: {config.get('environment', 'production')}")
                return {**default_config, **config}
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            print("将使用默认配置")
            return default_config
        
    def setup_logging(self):
        """配置日志系统"""
        # 使用统一的日志目录
        log_dir = self.log_dir
        
        # 配置根日志记录器
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                RotatingFileHandler(
                    log_dir / "service.log",
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                ),
                logging.StreamHandler()
            ]
        )
        
        # 配置collector日志
        from src.utils.logger_manager import set_log_config
        set_log_config(
            log_level="INFO",
            log_file=str(log_dir / "collector.log"),
            use_colors=True,
            max_file_size=10*1024*1024,
            backup_count=5
        )
        
        # 设置其他模块的日志级别
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
        logging.getLogger("fastapi").setLevel(logging.WARNING)
        
        self.logger = logging.getLogger("ServiceManager")
        
    def setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
    def handle_shutdown(self, signum, frame):
        """处理关闭信号"""
        print("\n正在关闭服务...")
        if self.scheduler:
            self.scheduler.stop()
        self.stop_all()
        if self.loop and self.loop.is_running():
            self.loop.stop()
        sys.exit(0)
        
    def start_api(self):
        """启动FastAPI服务"""
        config = self.config["api"]
        
        # 设置环境变量
        env = os.environ.copy()
        project_root = Path.cwd()
        
        if hasattr(self, 'config_path') and self.config_path:
            env["CONFIG_PATH"] = str(self.config_path)
        else:
            env["CONFIG_PATH"] = str(project_root / "config" / "production.yaml")
            
        env["PYTHONPATH"] = str(project_root)
        # 设置日志相关的环境变量
        env["APP_LOG_DIR"] = str(self.log_dir)
        # 移除可能与FastAPI应用内部日志配置冲突的环境变量
        env.pop("UVICORN_LOG_LEVEL", None)
        env.pop("UVICORN_NO_ACCESS_LOG", None)
        env.pop("UVICORN_NO_PROCESS_LOG", None)
        env.pop("FASTAPI_LOG_LEVEL", None)
        
        os.chdir(str(project_root / "src"))
        
        # 验证模块路径是否存在
        module_path = project_root / "src" / "core" / "fastapi" / "amazon_crawler_api.py"
        if not module_path.exists():
            self.logger.error(f"错误: FastAPI模块文件不存在: {module_path}")
            return None
        
        # 先尝试单进程模式，以便调试
        cmd = [
            sys.executable,
            "-m", "uvicorn",
            "core.fastapi.amazon_crawler_api:app",
            "--host", config['host'],
            "--port", str(config['port']),
            # 临时使用一个工作进程，解决多进程日志冲突问题
            "--workers", "1",
            # 不再指定日志级别，避免与应用内部日志配置冲突
            "--reload" if self.config.get('environment') == 'development' else "",  # 根据环境决定是否启用reload
        ]
        
        # 清理空字符串
        cmd = [arg for arg in cmd if arg]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=env,
                bufsize=1
            )
            
            def log_output(pipe, prefix):
                for line in pipe:
                    # 记录所有输出
                    self.logger.info(f"{prefix}: {line.strip()}")
            
            import threading
            threading.Thread(target=log_output, args=(process.stdout, "FastAPI"), daemon=True).start()
            threading.Thread(target=log_output, args=(process.stderr, "FastAPI Error"), daemon=True).start()
            
            # 等待几秒检查进程是否正常运行
            time.sleep(2)
            if process.poll() is not None:
                self.logger.error(f"FastAPI服务启动失败，退出码: {process.poll()}")
                return None
                
            self.processes.append(process)
            self.logger.info(f"FastAPI服务已启动: http://{config['host']}:{config['port']}")
            
            os.chdir(str(project_root))
            return process
            
        except Exception as e:
            self.logger.error(f"启动FastAPI服务时发生错误: {str(e)}")
            return None
        
    def start_frontend(self):
        """启动Streamlit前端"""
        config = self.config["frontend"]
        frontend_path = os.path.join("frontend", "main.py")
        
        if not os.path.exists(frontend_path):
            self.logger.error(f"错误: 找不到前端入口文件 {frontend_path}")
            return None
            
        # 设置环境变量
        env = os.environ.copy()
        project_root = Path.cwd()
        env["PYTHONPATH"] = str(project_root)
            
        cmd = [
            "streamlit",
            "run",
            frontend_path,
            "--server.port",
            str(config['port']),
            "--server.address",
            config['host'],
            "--logger.level=error"  # 设置streamlit日志级别
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env  # 添加环境变量
        )
        self.processes.append(process)
        self.logger.info(f"✓ Streamlit前端已启动: http://{config['host']}:{config['port']}")
        return process
        
    def stop_process(self, process: subprocess.Popen):
        """停止指定进程及其子进程"""
        if process:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                
                for child in children:
                    child.terminate()
                parent.terminate()
                
                # 等待进程结束
                gone, alive = psutil.wait_procs([parent], timeout=3)
                
                # 如果进程仍然存活，强制结束
                for p in alive:
                    p.kill()
            except psutil.NoSuchProcess:
                pass
            
    def stop_all(self):
        """停止所有服务"""
        for process in self.processes:
            self.stop_process(process)
        self.processes.clear()
        
    def monitor_processes(self):
        """监控进程状态"""
        while self.processes:
            for process in self.processes[:]:
                if process.poll() is not None:
                    self.logger.warning(f"进程 {process.pid} 已退出，退出码: {process.returncode}")
                    # 检查是否需要重启进程
                    if self.config.get('environment') == 'production':
                        self.logger.info("正在尝试重启进程...")
                        self.restart_process(process)
                    else:
                        self.processes.remove(process)
            time.sleep(1)
            
    def restart_process(self, process: subprocess.Popen):
        """重启指定进程"""
        try:
            self.stop_process(process)
            self.processes.remove(process)
            if "uvicorn" in process.args[0]:
                new_process = self.start_api()
            else:
                new_process = self.start_frontend()
            self.logger.info(f"进程已成功重启，新PID: {new_process.pid}")
        except Exception as e:
            self.logger.error(f"重启进程失败: {e}")
            
    async def start_all(self):
        """启动所有服务"""
        self.logger.info("正在启动服务...")
        
        try:
            await self.init_scheduler()
            self.logger.info("✓ 调度器服务已启动")
            
            api_process = self.start_api()
            if not api_process:
                self.logger.error("启动API服务失败")
                if self.scheduler:
                    self.scheduler.stop()
                self.stop_all()
                return False
            
            await asyncio.sleep(2)
            
            frontend_process = self.start_frontend()
            if not frontend_process:
                self.logger.error("启动前端服务失败")
                if self.scheduler:
                    self.scheduler.stop()
                self.stop_all()
                return False
            
            self.logger.info("\n服务启动完成!")
            
            while True:
                for process in self.processes[:]:
                    if process.poll() is not None:
                        if self.config.get('environment') == 'production':
                            self.logger.warning(f"检测到进程退出，正在重启...")
                            self.restart_process(process)
                        else:
                            self.processes.remove(process)
                await asyncio.sleep(1)
        except Exception as e:
            self.logger.error(f"启动服务时发生错误: {e}")
            if self.scheduler:
                self.scheduler.stop()
            self.stop_all()
            return False

async def main():
    """主函数"""
    # 检查依赖
    try:
        import uvicorn
        import streamlit
        import psutil
    except ImportError as e:
        print(f"错误: 缺少必要的依赖包 - {e}")
        print("请运行: pip install uvicorn streamlit psutil")
        return
        
    # 获取配置文件路径
    config_path = os.getenv("CONFIG_PATH", "config/production.yaml")
    if not os.path.exists(config_path):
        print(f"警告: 配置文件 {config_path} 不存在")
        config_path = None
    
    # 创建并启动服务管理器
    manager = ServiceManager(config_path)
    await manager.start_all()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断") 