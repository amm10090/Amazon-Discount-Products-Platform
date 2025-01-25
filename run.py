import os
import uvicorn
from dotenv import load_dotenv
from pathlib import Path

def init_environment():
    """初始化环境配置"""
    # 加载.env文件
    env_path = Path('.env')
    if not env_path.exists():
        print("警告: .env文件不存在，将使用默认配置")
        load_dotenv('.env.example')
    else:
        load_dotenv()
    
    # 创建必要的目录
    Path('crawler_results').mkdir(exist_ok=True)
    
    # 检查必要的环境变量
    required_vars = [
        'AMAZON_ACCESS_KEY',
        'AMAZON_SECRET_KEY',
        'AMAZON_PARTNER_TAG'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print("错误: 缺少必要的环境变量:")
        for var in missing_vars:
            print(f"  - {var}")
        return False
    
    return True

def main():
    """主函数"""
    print("正在初始化Amazon优惠商品平台...")
    
    # 初始化环境
    if not init_environment():
        print("初始化失败，请检查配置后重试")
        return
    
    # 获取API配置
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    debug = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    
    print("\n配置信息:")
    print(f"API地址: http://{host}:{port}")
    print(f"调试模式: {'开启' if debug else '关闭'}")
    print("\nAPI文档地址:")
    print(f"Swagger UI: http://{host}:{port}/docs")
    print(f"ReDoc: http://{host}:{port}/redoc")
    
    # 启动API服务
    print("\n正在启动API服务...")
    uvicorn.run(
        "amazon_crawler_api:app",
        host=host,
        port=port,
        reload=debug
    )

if __name__ == "__main__":
    main() 