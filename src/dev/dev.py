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
                "port": 8000,
                "reload": True,
                "workers": 1
            },
            "frontend": {
                "port": 8501,
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
        2. 配置日志格式和处理器
        3. 设置日志轮转
        """
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # 配置根日志记录器
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(
                    log_dir / "dev_service.log",
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                ),
                logging.StreamHandler()
            ]
        )
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
        if self.config_path:
            env["CONFIG_PATH"] = str(self.config_path)
        else:
            env["CONFIG_PATH"] = str(project_root / "config" / "development.yaml")
            
        # 添加项目根目录到PYTHONPATH
        env["PYTHONPATH"] = str(project_root)
        
        # 确保API服务使用正确的数据库路径
        if "SCHEDULER_DB_PATH" in os.environ:
            env["SCHEDULER_DB_PATH"] = os.environ["SCHEDULER_DB_PATH"]
        if "PRODUCTS_DB_PATH" in os.environ:
            env["PRODUCTS_DB_PATH"] = os.environ["PRODUCTS_DB_PATH"]
            
        # 切换到src目录
        os.chdir(str(project_root / "src"))
        
        # 构建uvicorn启动命令
        cmd = [
            sys.executable,  # 使用当前Python解释器
            "-m", "uvicorn",
            "core.fastapi.amazon_crawler_api:app",  # 使用正确的模块路径
            "--host", config['host'],
            "--port", str(config['port']),
            "--reload",  # 开发环境始终启用热重载
            "--reload-dir", str(project_root / "src"),  # 监视src目录的变化
            "--log-level", "debug"  # 开发环境使用debug日志级别
        ]
        
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
        self.logger.info(f"FastAPI 开发服务已启动: http://{config['host']}:{config['port']}")
        
        # 切回项目根目录
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
            print(f"错误: 找不到前端入口文件 {frontend_path}")
            return None
            
        # 查找可用端口
        try:
            port = self.find_available_port(config['port'])
            if port != config['port']:
                self.logger.warning(f"端口 {config['port']} 已被占用，使用端口 {port}")
        except RuntimeError as e:
            self.logger.error(str(e))
            return None
            
        # 设置环境变量
        env = os.environ.copy()
        if self.config_path:
            env["CONFIG_PATH"] = str(self.config_path)
        else:
            env["CONFIG_PATH"] = str(project_root / "config" / "development.yaml")
            
        # 添加项目根目录到PYTHONPATH
        env["PYTHONPATH"] = str(project_root)
            
        cmd = [
            sys.executable,  # 使用当前Python解释器
            "-m", "streamlit",
            "run",
            str(frontend_path),
            "--server.port", str(port),
            "--server.address", config['host']
        ]
        
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
        threading.Thread(target=log_output, args=(process.stdout, "Streamlit"), daemon=True).start()
        threading.Thread(target=log_output, args=(process.stderr, "Streamlit Error"), daemon=True).start()
        
        self.processes.append(process)
        self.logger.info(f"Streamlit 开发前端已启动: http://{config['host']}:{port}")
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
        """
        启动所有服务
        
        启动顺序：
        1. 初始化并启动调度器
        2. 启动API服务
        3. 等待API服务就绪
        4. 启动前端服务
        5. 开始进程监控
        
        错误处理：
        - 任何服务启动失败都会导致所有服务关闭
        - 自动重启异常退出的服务
        """
        print("正在启动开发环境服务...")
        
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
            
        print("\n所有开发服务已启动!")
        print("使用 Ctrl+C 可以停止所有服务")
        
        # 监控进程
        while True:
            for process in self.processes[:]:
                if process.poll() is not None:
                    self.logger.warning(f"进程 {process.pid} 已退出，退出码: {process.returncode}")
                    self.logger.info("正在重启进程...")
                    self.restart_process(process)
            await asyncio.sleep(1)

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
