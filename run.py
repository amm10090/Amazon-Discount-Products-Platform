import os
import sys
import signal
import subprocess
import psutil
from typing import List, Optional
import time
import yaml
from pathlib import Path

class ServiceManager:
    """服务管理器，用于管理FastAPI和Streamlit服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.processes: List[subprocess.Popen] = []
        self.config = self.load_config(config_path)
        self.setup_signal_handlers()
        
    def load_config(self, config_path: Optional[str]) -> dict:
        """加载配置文件"""
        default_config = {
            "api": {
                "host": "localhost",
                "port": 8000,
                "reload": True
            },
            "frontend": {
                "port": 8501,
                "host": "localhost"
            }
        }
        
        if not config_path:
            return default_config
            
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return {**default_config, **config}
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return default_config
            
    def setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
    def handle_shutdown(self, signum, frame):
        """处理关闭信号"""
        print("\n正在关闭服务...")
        self.stop_all()
        sys.exit(0)
        
    def start_api(self):
        """启动FastAPI服务"""
        config = self.config["api"]
        cmd = [
            "uvicorn",
            "amazon_crawler_api:app",
            f"--host={config['host']}",
            f"--port={config['port']}",
            "--reload" if config.get('reload', True) else ""
        ]
        
        process = subprocess.Popen(
            [arg for arg in cmd if arg],  # 过滤空字符串
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        self.processes.append(process)
        print(f"FastAPI 服务已启动: http://{config['host']}:{config['port']}")
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
                    print(f"进程 {process.pid} 已退出，退出码: {process.returncode}")
                    self.processes.remove(process)
            time.sleep(1)
            
    def start_all(self):
        """启动所有服务"""
        print("正在启动服务...")
        
        # 启动API服务
        api_process = self.start_api()
        if not api_process:
            print("启动API服务失败")
            self.stop_all()
            return False
            
        # 等待API服务启动
        time.sleep(2)
        
        # 启动前端服务
        frontend_process = self.start_frontend()
        if not frontend_process:
            print("启动前端服务失败")
            self.stop_all()
            return False
            
        print("\n所有服务已启动!")
        print("使用 Ctrl+C 可以停止所有服务")
        
        # 监控进程
        self.monitor_processes()
        return True

def main():
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
    config_path = "config/app.yaml" if os.path.exists("config/app.yaml") else None
    
    # 创建并启动服务管理器
    manager = ServiceManager(config_path)
    manager.start_all()

if __name__ == "__main__":
    main() 