import os
import sys
import signal
import subprocess
import psutil
import threading
from typing import List, Optional
import time
import yaml
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import asyncio
import socket

# 将项目根目录添加到Python路径，确保可以导入项目模块
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
from models.scheduler import SchedulerManager

class DevServiceManager:
    """
    开发环境服务管理器
    
    负责管理和协调开发环境中的各个服务组件：
    1. FastAPI后端服务
    2. Streamlit前端服务
    3. 后台调度器服务
    
    主要功能：
    - 服务的启动、停止和重启
    - 进程监控和自动恢复
    - 配置管理
    - 日志记录
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化服务管理器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """
        self.processes: List[subprocess.Popen] = []  # 存储所有受管理的子进程
        self.config_path = config_path
        self.config = self.load_config(config_path)  # 加载配置
        self.setup_logging()  # 设置日志系统
        self.setup_signal_handlers()  # 设置信号处理器
        self.scheduler = None  # 调度器实例
        self.loop = None  # 事件循环实例
        
    async def init_scheduler(self):
        """异步初始化调度器服务"""
        if not self.scheduler:
            # 确保使用正确的数据库路径
            data_dir = project_root / "data" / "db"
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # 设置环境变量，确保所有组件使用相同的数据库路径
            os.environ["SCHEDULER_DB_PATH"] = str(data_dir / "scheduler.db")
            os.environ["PRODUCTS_DB_PATH"] = str(data_dir / "amazon_products.db")
            
            self.scheduler = SchedulerManager()
            
    def load_config(self, config_path: Optional[str]) -> dict:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            dict: 合并后的配置字典，包含默认值和用户自定义值
            
        Note:
            如果配置文件不存在或加载失败，将使用默认配置
        """
        # 默认配置
        default_config = {
            "environment": "development",
            "api": {
                "host": "localhost",
                "port": 5001,
                "reload": True,
                "workers": 1
            },
            "frontend": {
                "port": 5002,
                "host": "localhost"
            },
            "logging": {
                "level": "DEBUG",
                "max_size": 10485760,  # 10MB
                "backup_count": 5
            }
        }
        
        if not config_path:
            print("未指定配置文件路径，使用开发环境默认配置")
            return default_config
            
        try:
            config_path = os.path.abspath(config_path)
            print(f"\n正在加载配置文件: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print(f"成功加载配置文件，当前环境: {config.get('environment', 'development')}")
                return {**default_config, **config}
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            print("将使用开发环境默认配置")
            return default_config
        
    def setup_logging(self):
        """
        配置日志系统
        
        功能：
        1. 创建日志目录
        2. 配置控制台和文件日志
        3. 设置不同模块的日志级别
        4. 优化日志格式和输出
        """
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # 获取日志配置
        log_config = self.config.get("logging", {})
        log_level = getattr(logging, log_config.get("level", "DEBUG"))
        
        # 创建格式化器
        console_formatter = logging.Formatter(
            fmt=log_config.get("console", {}).get("format", "%(asctime)s [%(levelname)s] %(message)s"),
            datefmt=log_config.get("console", {}).get("date_format", "%H:%M:%S")
        )
        
        file_formatter = logging.Formatter(
            fmt=log_config.get("file", {}).get("format", "%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        )
        
        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # 清除现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 添加控制台处理器
        if log_config.get("console", {}).get("enabled", True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(log_level)
            root_logger.addHandler(console_handler)
        
        # 添加文件处理器
        if log_config.get("file", {}).get("enabled", True):
            file_handler = RotatingFileHandler(
                log_dir / "development.log",
                maxBytes=log_config.get("file", {}).get("max_size", 10*1024*1024),
                backupCount=log_config.get("file", {}).get("backup_count", 5)
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        
        # 配置各模块的日志级别
        loggers_config = log_config.get("loggers", {})
        for logger_name, level in loggers_config.items():
            logging.getLogger(logger_name).setLevel(getattr(logging, level))
        
        # 创建开发服务管理器的日志记录器
        self.logger = logging.getLogger("DevServiceManager")
        
    def setup_signal_handlers(self):
        """
        设置信号处理器
        
        处理：
        - SIGINT (Ctrl+C)
        - SIGTERM (终止信号)
        确保服务可以优雅地关闭
        """
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
    def handle_shutdown(self, signum, frame):
        """处理关闭信号"""
        print("\n正在关闭开发服务...")
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
        if self.config_path:
            env["CONFIG_PATH"] = str(self.config_path)
        else:
            env["CONFIG_PATH"] = str(project_root / "config" / "development.yaml")
            
        env["PYTHONPATH"] = str(project_root)
        
        # 切换到src目录
        os.chdir(str(project_root / "src"))
        
        cmd = [
            sys.executable,
            "-m", "uvicorn",
            "core.fastapi.amazon_crawler_api:app",
            "--host", config['host'],
            "--port", str(config['port']),
            "--reload",
            "--reload-dir", str(project_root / "src"),
            "--log-level", "error"
        ]
        
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
                # 过滤不必要的日志信息
                if any(skip in line for skip in [
                    "INFO:     Started server process",
                    "INFO:     Waiting for application startup",
                    "INFO:     Uvicorn running on",
                    "INFO:     Application startup complete"
                ]):
                    continue
                if "ERROR" in line:
                    self.logger.error(f"{line.strip()}")
                elif "WARNING" in line:
                    self.logger.warning(f"{line.strip()}")
                else:
                    self.logger.info(f"{line.strip()}")
        
        threading.Thread(target=log_output, args=(process.stdout, "FastAPI"), daemon=True).start()
        threading.Thread(target=log_output, args=(process.stderr, "FastAPI Error"), daemon=True).start()
        
        self.processes.append(process)
        self.logger.info(f"✓ FastAPI开发服务已启动: http://{config['host']}:{config['port']}")
        
        os.chdir(str(project_root))
        return process
        
    def is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return False
            except socket.error:
                return True
                
    def find_available_port(self, start_port: int, max_attempts: int = 10) -> int:
        """查找可用端口"""
        port = start_port
        for _ in range(max_attempts):
            if not self.is_port_in_use(port):
                return port
            port += 1
        raise RuntimeError(f"无法找到可用端口（尝试范围：{start_port}-{start_port + max_attempts - 1}）")
        
    def start_frontend(self):
        """启动Streamlit前端"""
        config = self.config["frontend"]
        frontend_path = project_root / "frontend" / "main.py"
        
        if not frontend_path.exists():
            self.logger.error(f"错误: 找不到前端入口文件 {frontend_path}")
            return None
            
        cmd = [
            "streamlit",
            "run",
            str(frontend_path),
            "--server.port", str(config['port']),
            "--server.address", config['host'],
            "--logger.level=error",
            "--logger.messageFormat=%(message)s"
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        def log_output(pipe, prefix):
            for line in pipe:
                # 过滤Streamlit的启动信息
                if any(skip in line for skip in [
                    "You can now view your Streamlit app in your browser",
                    "Local URL:",
                    "Network URL:",
                    "For better performance, install the Watchdog module:",
                    "  $ pip install watchdog"
                ]):
                    continue
                if "error" in line.lower():
                    self.logger.error(f"{line.strip()}")
                elif "warning" in line.lower():
                    self.logger.warning(f"{line.strip()}")
                else:
                    self.logger.info(f"{line.strip()}")
        
        threading.Thread(target=log_output, args=(process.stdout, "Streamlit"), daemon=True).start()
        threading.Thread(target=log_output, args=(process.stderr, "Streamlit Error"), daemon=True).start()
        
        self.processes.append(process)
        self.logger.info(f"✓ Streamlit开发前端已启动: http://{config['host']}:{config['port']}")
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
        """
        监控进程状态
        
        功能：
        1. 持续检查所有子进程的状态
        2. 检测到进程退出时自动重启
        3. 记录进程状态变化
        """
        while self.processes:
            for process in self.processes[:]:
                if process.poll() is not None:
                    self.logger.warning(f"进程 {process.pid} 已退出，退出码: {process.returncode}")
                    # 开发环境下自动重启进程
                    self.logger.info("正在重启进程...")
                    self.restart_process(process)
            time.sleep(1)
            
    def restart_process(self, process: subprocess.Popen):
        """
        重启指定进程
        
        Args:
            process: 需要重启的进程实例
            
        功能：
        1. 停止原进程
        2. 从进程列表中移除
        3. 根据进程类型重新启动相应服务
        4. 记录重启过程
        """
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
        self.logger.info("正在启动开发环境服务...")
        
        try:
            await self.init_scheduler()
            self.logger.info("✓ 调度器服务已启动")
            
            api_process = self.start_api()
            if not api_process:
                self.logger.error("✗ API服务启动失败")
                if self.scheduler:
                    self.scheduler.stop()
                self.stop_all()
                return False
            
            await asyncio.sleep(2)
            
            frontend_process = self.start_frontend()
            if not frontend_process:
                self.logger.error("✗ 前端服务启动失败")
                if self.scheduler:
                    self.scheduler.stop()
                self.stop_all()
                return False
            
            self.logger.info("\n✓ 所有开发服务启动完成!")
            self.logger.info("按 Ctrl+C 停止服务\n")
            
            while True:
                for process in self.processes[:]:
                    if process.poll() is not None:
                        self.logger.warning("检测到服务异常退出，正在重启...")
                        self.restart_process(process)
                await asyncio.sleep(1)
        except Exception as e:
            self.logger.error(f"启动服务时发生错误: {e}")
            if self.scheduler:
                self.scheduler.stop()
            self.stop_all()
            return False

async def main():
    """
    主函数
    
    功能：
    1. 检查必要的依赖包
    2. 处理配置文件路径
    3. 创建并启动服务管理器
    4. 异常处理
    """
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
    config_path = os.getenv("CONFIG_PATH", "config/development.yaml")
    if not os.path.exists(config_path):
        print(f"警告: 配置文件 {config_path} 不存在，将使用默认开发配置")
        config_path = None
    
    # 创建并启动服务管理器
    manager = DevServiceManager(config_path)
    await manager.start_all()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n开发服务被用户中断")
