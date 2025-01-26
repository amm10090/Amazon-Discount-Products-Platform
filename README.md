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
- Support for Amazon PA-API product data retrieval
- Implementation of intelligent caching mechanism for optimization and stability
- Support for product discount and promotional information crawling

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
│   ├── product.py            # Product related models
│   └── cache_manager.py      # Cache manager
├── cache/                    # Cache directory
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

- **Cache Management Endpoints**
  - `GET /api/cache/stats` - Get cache statistics
  - `POST /api/cache/clear` - Clear expired cache

- **System Endpoint**
  - `GET /api/health` - Health check

### Environment Variables
```bash
# Amazon PA-API Credentials
AMAZON_ACCESS_KEY=your_access_key
AMAZON_SECRET_KEY=your_secret_key
AMAZON_PARTNER_TAG=your_partner_tag

# Cache Configuration
CACHE_ENABLED=true           # Enable/disable caching
CACHE_DIR=cache             # Cache directory path
CACHE_TTL_OFFERS=3600      # Offers data TTL (1 hour)
CACHE_TTL_BROWSE_NODE=3600 # BrowseNode data TTL (1 hour)
CACHE_TTL_DEFAULT=86400    # Default TTL (24 hours)
```

### Cache System
The system implements an intelligent caching mechanism to optimize API calls and improve performance:

1. Cache Configuration:
- Controlled via environment variables
- Configurable TTL for different data types
- Automatic cache cleanup

2. Cache Types and TTL:
- Offers data: 1 hour
- BrowseNode data: 1 hour
- Other data (Images, ItemInfo, etc.): 24 hours

3. Cache Management:
- Automatic expiration handling
- File-based storage with JSON format
- Cache statistics monitoring
- Manual cleanup option

4. Cache API Endpoints:
- Get cache statistics: `GET /api/cache/stats`
- Clear expired cache: `POST /api/cache/clear`

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
- 支持Amazon PA-API产品数据获取
- 实现智能缓存机制，提高性能和稳定性
- 支持商品折扣和优惠信息爬取

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
│   ├── product.py            # 商品相关模型
│   └── cache_manager.py      # 缓存管理器
├── cache/                    # 缓存目录
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

- **缓存管理接口**
  - `GET /api/cache/stats` - 获取缓存统计信息
  - `POST /api/cache/clear` - 清理过期缓存

- **系统接口**
  - `GET /api/health` - 健康检查

### 环境变量配置
```bash
# Amazon PA-API 凭证
AMAZON_ACCESS_KEY=你的访问密钥
AMAZON_SECRET_KEY=你的秘密密钥
AMAZON_PARTNER_TAG=你的合作伙伴标签

# 缓存配置
CACHE_ENABLED=true           # 是否启用缓存
CACHE_DIR=cache             # 缓存目录路径
CACHE_TTL_OFFERS=3600      # Offers数据缓存时间（1小时）
CACHE_TTL_BROWSE_NODE=3600 # BrowseNode数据缓存时间（1小时）
CACHE_TTL_DEFAULT=86400    # 默认缓存时间（24小时）
```

### 缓存系统
系统实现了智能缓存机制，以优化API调用并提高性能：

1. 缓存配置：
- 通过环境变量控制
- 可配置不同数据类型的缓存时间
- 自动清理过期缓存

2. 缓存类型和时间：
- Offers数据：1小时
- BrowseNode数据：1小时
- 其他数据(Images、ItemInfo等)：24小时

3. 缓存管理：
- 自动过期处理
- 基于文件的JSON格式存储
- 缓存统计监控
- 手动清理选项

4. 缓存API接口：
- 获取缓存统计：`GET /api/cache/stats`
- 清理过期缓存：`POST /api/cache/clear`

5. 缓存统计信息：
- 缓存状态（启用/禁用）
- 缓存目录路径
- 缓存文件总数
- 缓存总大小（MB）
- 过期文件数量
- TTL配置信息

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
5. 请遵守Amazon API的调用限制
6. 定期清理过期缓存
7. 监控系统性能和错误日志

### 性能优化
1. 缓存机制：
- 实现了分层缓存策略
- 自动过期管理
- 错误处理和容错机制
2. API调用优化：
- 批量请求处理
- 智能重试机制
- 并发控制

### License
MIT
