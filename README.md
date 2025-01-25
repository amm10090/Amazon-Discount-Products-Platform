
# Amazon Deals & Products API

[English](#english) | [中文](#chinese)

## English

### Project Overview
A comprehensive platform for fetching Amazon deals and product information, featuring web crawling and PA-API integration capabilities using FastAPI framework.

### Features
- Crawl Amazon deals pages for product ASINs
- Fetch detailed product information via PA-API
- RESTful API endpoints for all functionalities
- Background task processing
- Multiple output formats support (JSON, CSV, TXT)
- Health monitoring endpoint

### Project Structure
```
.
├── README.md                  # Project documentation
├── amazon_crawler_api.py      # Main API implementation
├── amazon_bestseller.py       # Web crawler core logic
├── amazon_product_api.py      # PA-API integration
├── models/                    # Data models
│   ├── __init__.py
│   ├── crawler.py            # Crawler related models
│   └── product.py            # Product related models
└── crawler_results/          # Crawler output directory
```

### API Endpoints
- **Crawler Endpoints**
  - `POST /api/crawl` - Start a new crawler task
  - `GET /api/status/{task_id}` - Check task status
  - `GET /api/download/{task_id}` - Download crawler results

- **Product Endpoints**
  - `POST /api/products` - Get product information
  - `POST /api/products/save` - Save product information to file

- **System Endpoint**
  - `GET /api/health` - Health check

### Environment Variables
```
AMAZON_ACCESS_KEY=your_access_key
AMAZON_SECRET_KEY=your_secret_key
AMAZON_PARTNER_TAG=your_partner_tag
```

### Installation
```bash
# Install dependencies
pnpm install

# Run the application
python amazon_crawler_api.py
```

### API Documentation
Access the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Chinese

### 项目概述
一个用于获取Amazon优惠和商品信息的综合平台，使用FastAPI框架实现网页爬虫和PA-API集成功能。

### 功能特点
- 爬取Amazon优惠页面获取商品ASIN
- 通过PA-API获取详细商品信息
- 所有功能均提供RESTful API接口
- 后台任务处理
- 支持多种输出格式（JSON、CSV、TXT）
- 健康监控接口

### 项目结构
```
.
├── README.md                  # 项目文档
├── amazon_crawler_api.py      # 主API实现
├── amazon_bestseller.py       # 爬虫核心逻辑
├── amazon_product_api.py      # PA-API集成
├── models/                    # 数据模型
│   ├── __init__.py
│   ├── crawler.py            # 爬虫相关模型
│   └── product.py            # 商品相关模型
└── crawler_results/          # 爬虫结果输出目录
```

### API接口
- **爬虫相关接口**
  - `POST /api/crawl` - 启动新的爬虫任务
  - `GET /api/status/{task_id}` - 检查任务状态
  - `GET /api/download/{task_id}` - 下载爬虫结果

- **商品相关接口**
  - `POST /api/products` - 获取商品信息
  - `POST /api/products/save` - 保存商品信息到文件

- **系统接口**
  - `GET /api/health` - 健康检查

### 环境变量
```
AMAZON_ACCESS_KEY=你的访问密钥
AMAZON_SECRET_KEY=你的秘密密钥
AMAZON_PARTNER_TAG=你的合作伙伴标签
```

### 安装部署
```bash
# 安装依赖
pnpm install

# 运行应用
python amazon_crawler_api.py
```

### API文档
访问交互式API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 开发规范
1. 代码风格遵循PEP 8规范
2. 每个函数和类都需要添加文档字符串
3. 使用类型注解
4. 代码提交前进行格式化和测试
5. 保持代码模块化和可维护性

### 注意事项
1. 确保环境变量正确配置
2. 爬虫使用时注意遵守目标网站的robots.txt规则
3. 定期检查PA-API的配额使用情况
4. 建议在生产环境中使用代理池
```

此外，建议在项目根目录下创建以下文件：

1. `.env.example` 文件示例：
```plaintext:.env.example
AMAZON_ACCESS_KEY=your_access_key
AMAZON_SECRET_KEY=your_secret_key
AMAZON_PARTNER_TAG=your_partner_tag
```

2. `.gitignore` 文件：
```plaintext:.gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Project specific
crawler_results/
.env
```

3. `requirements.txt` 文件：
```plaintext:requirements.txt
fastapi==0.104.1
uvicorn==0.24.0
selenium==4.15.2
webdriver-manager==4.0.1
python-dotenv==1.0.0
pydantic==2.5.1
requests==2.31.0
beautifulsoup4==4.12.2
```
