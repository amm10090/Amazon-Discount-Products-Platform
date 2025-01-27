import uvicorn
from dotenv import load_dotenv
import os

if __name__ == "__main__":
    # 加载环境变量
    load_dotenv()
    
    # 获取配置
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    reload_dirs = [".", "models"]  # 监视这些目录的变化
    
    # 启动开发服务器
    uvicorn.run(
        "amazon_crawler_api:app",
        host=host,
        port=port,
        reload=True,  # 启用热更新
        reload_dirs=reload_dirs,  # 指定要监视的目录
        workers=1,  # 开发模式使用单个worker
        log_level="debug"
    ) 