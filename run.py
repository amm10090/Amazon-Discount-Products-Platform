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

class ServiceManager:
    """服务管理器，用于管理FastAPI、Streamlit和调度器服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.processes: List[subprocess.Popen] = []
        self.config = self.load_config(config_path)
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
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 配置根日志记录器
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(
                    log_dir / "service.log",
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                ),
                logging.StreamHandler()
            ]
        )
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
        """
        启动FastAPI服务
        
        功能：
        1. 设置必要的环境变量
        2. 配置Python路径
        3. 启动uvicorn服务器
        4. 设置日志重定向
        
        Returns:
            subprocess.Popen: 启动的进程实例
        """
        config = self.config["api"]
        
        # 设置环境变量
        env = os.environ.copy()
        project_root = Path.cwd()  # 获取项目根目录
        
        # 设置配置文件路径
        if hasattr(self, 'config_path') and self.config_path:
            env["CONFIG_PATH"] = str(self.config_path)
        else:
            env["CONFIG_PATH"] = str(project_root / "config" / "production.yaml")
            
        # 添加项目根目录到PYTHONPATH
        env["PYTHONPATH"] = str(project_root)
            
        # 切换到src目录
        os.chdir(str(project_root / "src"))
        
        # 构建uvicorn启动命令
        cmd = [
            sys.executable,  # 使用当前Python解释器
            "-m", "uvicorn",
            "core.fastapi.amazon_crawler_api:app",  # 使用正确的模块路径
            "--host", config['host'],
            "--port", str(config['port']),
            "--workers", str(config.get('workers', 4))
        ]
        
        # 仅在开发环境启用热重载
        if self.config.get('environment') == 'development' and config.get('reload', False):
            cmd.extend([
                "--reload",
                "--reload-dir", str(project_root / "src")
            ])
            
        self.logger.info(f"启动命令: {' '.join(cmd)}")
        self.logger.info(f"工作目录: {os.getcwd()}")
        self.logger.info(f"PYTHONPATH: {env.get('PYTHONPATH')}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
            bufsize=1  # 行缓冲
        )
        
        # 创建日志线程
        def log_output(pipe, prefix):
            for line in pipe:
                self.logger.info(f"{prefix}: {line.strip()}")
                
        import threading
        threading.Thread(target=log_output, args=(process.stdout, "FastAPI"), daemon=True).start()
        threading.Thread(target=log_output, args=(process.stderr, "FastAPI Error"), daemon=True).start()
        
        self.processes.append(process)
        self.logger.info(f"FastAPI 服务已启动: http://{config['host']}:{config['port']}")
        
        # 切回项目根目录
        os.chdir(str(project_root))
        
        return process
        
    def start_frontend(self):
        """启动Streamlit前端"""
        config = self.config["frontend"]
        frontend_path = os.path.join("frontend", "main.py")
        
        if not os.path.exists(frontend_path):
            print(f"错误: 找不到前端入口文件 {frontend_path}")
            return None
            
        cmd = [
            "streamlit",
            "run",
            frontend_path,
            "--server.port",
            str(config['port']),
            "--server.address",
            config['host']
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        self.processes.append(process)
        print(f"Streamlit 前端已启动: http://{config['host']}:{config['port']}")
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
        print("正在启动服务...")
        
        # 启动调度器
        try:
            await self.init_scheduler()
            print("调度器服务已启动")
        except Exception as e:
            print(f"启动调度器失败: {e}")
            return False
        
        # 启动API服务
        api_process = self.start_api()
        if not api_process:
            print("启动API服务失败")
            if self.scheduler:
                self.scheduler.stop()
            self.stop_all()
            return False
            
        # 等待API服务启动
        await asyncio.sleep(2)
        
        # 启动前端服务
        frontend_process = self.start_frontend()
        if not frontend_process:
            print("启动前端服务失败")
            if self.scheduler:
                self.scheduler.stop()
            self.stop_all()
            return False
            
        print("\n所有服务已启动!")
        print("使用 Ctrl+C 可以停止所有服务")
        
        # 监控进程
        while True:
            for process in self.processes[:]:
                if process.poll() is not None:
                    self.logger.warning(f"进程 {process.pid} 已退出，退出码: {process.returncode}")
                    if self.config.get('environment') == 'production':
                        self.logger.info("正在尝试重启进程...")
                        self.restart_process(process)
                    else:
                        self.processes.remove(process)
            await asyncio.sleep(1)

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