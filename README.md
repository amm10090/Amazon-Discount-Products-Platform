# Amazon Deals & Products API

[English](#english) | [中文](#chinese)

## English

### Project Overview
A comprehensive platform for fetching Amazon deals and product information, featuring web crawling and PA-API integration capabilities using FastAPI framework.

### Features
- Crawl Amazon deals pages for product ASINs
  - Support for maintaining product display order
  - Smart handling of color variants (avoiding duplicate ASINs)
  - Intelligent scrolling and pagination
  - Configurable timeout and item limits
- Fetch detailed product information via PA-API
- RESTful API endpoints for all functionalities
- Background task processing
- Multiple output formats support (JSON, CSV, TXT)
- Health monitoring endpoint
- Support for Amazon PA-API product data retrieval
- Implementation of intelligent caching mechanism for optimization and stability
- Support for product discount and promotional information crawling
- YAML configuration support for flexible crawler control
- Clear distinction between data sources and API providers
  - Data sources: bestseller/coupon crawlers
  - API providers: PA-API (extensible for future APIs)
- Separate endpoints for discount and coupon products

### Project Structure
```
.
├── README.md                  # Project documentation
├── amazon_crawler_api.py      # Main API implementation
├── amazon_bestseller.py       # Web crawler core logic
├── amazon_product_api.py      # PA-API integration
├── config/                    # Configuration files
│   └── crawler.yaml          # Crawler configuration
├── models/                    # Data models
│   ├── __init__.py
│   ├── crawler.py            # Crawler related models
│   ├── product.py            # Product related models
│   └── cache_manager.py      # Cache manager
├── cache/                    # Cache directory
└── crawler_results/          # Crawler output directory
```

### Crawler Usage
```bash
# Basic usage with default configuration
python collect_products.py

# Using configuration file
python collect_products.py --config config/crawler.yaml

# With command line parameters
python collect_products.py --crawler-type bestseller --max-items 100 --timeout 60 --no-headless

# Parameters:
--config        Configuration file path (YAML format)
--crawler-type  Crawler type (bestseller/coupon/all)
--max-items     Number of items to crawl (default: 100)
--batch-size    Batch size for API requests (default: 10)
--timeout       Timeout for no new items (default: 30 seconds)
--no-headless   Disable headless mode
```

### Configuration File (crawler.yaml)
```yaml
# Crawler type configuration (choose one)
# Option 1: Single crawler
crawler_types: bestseller    # or coupon or all

# Option 2: Multiple crawlers
# crawler_types: 
#   - bestseller
#   - coupon

# Data collection parameters
max_items: 100   # Maximum items per category
batch_size: 10   # API batch request size (1-10)
timeout: 30      # Crawler timeout (seconds)

# Browser configuration
headless: true   # true=headless mode, false=show browser window
```

### API Endpoints
- **Crawler Endpoints**
  - `POST /api/crawl` - Start a new crawler task
  - `GET /api/status/{task_id}` - Check task status
  - `GET /api/download/{task_id}` - Download crawler results

- **Product Endpoints**
  - `POST /api/products` - Get product information
  - `POST /api/products/save` - Save product information to file

- **Scheduler Endpoints**
  - `POST /api/scheduler/jobs` - Add a new scheduled task
  - `GET /api/scheduler/jobs` - List all scheduled tasks
  - `DELETE /api/scheduler/jobs/{job_id}` - Delete a specific task
  - `POST /api/scheduler/jobs/{job_id}/pause` - Pause a specific task
  - `POST /api/scheduler/jobs/{job_id}/resume` - Resume a specific task
  - `GET /api/scheduler/jobs/{job_id}/history` - Get task execution history
  - `GET /api/scheduler/status` - Get scheduler status
  - `POST /api/scheduler/start` - Start the scheduler
  - `POST /api/scheduler/stop` - Stop the scheduler
  - `POST /api/scheduler/reload` - Reload scheduler configuration

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

# Scheduler Configuration
SCHEDULER_TIMEZONE=Asia/Shanghai  # Default timezone for scheduler
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

### Scheduler System
The system implements a flexible task scheduling system, supporting both cron and interval execution tasks:

1. Scheduler Features:
- Supports both cron and interval task types
- Configurable task execution time and interval
- Task pause/resume control
- Execution history
- Status monitoring
- Timezone configuration support
- Singleton mode to ensure global unique instance
- Automatic task recovery (after system restart)
- Task execution status tracking
- Error handling and logging

2. Timezone Configuration:
- Default timezone: Asia/Shanghai
- Supports configuring default timezone via environment variable
- Frontend interface supports timezone selection
- All time display is based on configured timezone
- Supported timezones:
  * Asia/Shanghai
  * Asia/Tokyo
  * America/New_York
  * Europe/London
  * UTC
  * Other standard timezones

3. Task Types:
- Cron tasks: Execute at specified time points
- Interval tasks: Execute at fixed time intervals

4. Task Configuration:
```yaml
# Cron task example
{
  "id": "bestseller_daily",
  "type": "cron",
  "crawler_type": "bestseller",
  "max_items": 200,
  "hour": "*/4",
  "minute": "30"
}

# Interval task example
{
  "id": "coupon_hourly",
  "type": "interval",
  "crawler_type": "coupon",
  "max_items": 100,
  "hours": 1,
  "minutes": 30
}
```

5. Scheduler API:
- Task management:
  * Add task: POST /api/scheduler/jobs
  * Delete task: DELETE /api/scheduler/jobs/{job_id}
  * Pause task: POST /api/scheduler/jobs/{job_id}/pause
  * Resume task: POST /api/scheduler/jobs/{job_id}/resume
- Status query:
  * Get all tasks: GET /api/scheduler/jobs
  * Get scheduler status: GET /api/scheduler/status
  * Get task history: GET /api/scheduler/jobs/{job_id}/history
- Scheduler control:
  * Start scheduler: POST /api/scheduler/start
  * Stop scheduler: POST /api/scheduler/stop
  * Reload scheduler: POST /api/scheduler/reload
  * Update timezone: POST /api/scheduler/timezone

6. Frontend Interface:
- Visual task management
  * Add new task form
  * Task list display
  * Task control buttons (pause/resume/delete)
- Real-time status display
  * Running status indicator
  * Next execution time
  * Task type and configuration
- Execution history view
  * Recent 10 execution records
  * Execution status and result
  * Error information display
- Multi-language support
  * English/Chinese interface switch
  * Time format localization
  * Status information translation

7. Data persistence:
- Use SQLite database storage:
  * Task configuration and status
  * Execution history record
  - Database table structure:
    * job_history: Task execution history
    * jobstore: APScheduler task storage

### Logging and Error Handling System
The system implements a comprehensive logging and error handling framework:

1. Structured Logging:
- Centralized log configuration with Loguru
- Different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Contextual logging with request tracking
- Automatic log rotation and retention
- JSON log format support

2. Error Handling:
- Custom error types with error codes
- Error context capturing
- Global exception handler
- Detailed error tracking and statistics
- Automatic error level assignment

3. Log Analysis and Visualization:
- Advanced log querying and filtering:
  * Time-based filtering
  * Module-based filtering
  * Level-based filtering
  * Context-based filtering
  * Pattern matching
- Statistical analysis:
  * Error rate trends
  * Module activity statistics
  * Response time analysis
  * Anomaly detection
- Log visualization dashboard:
  * System health status overview
  * Interactive charts and graphs
  * Error distribution visualization
  * Module activity visualization
  * Response time trend analysis
- Log export capabilities:
  * JSON export
  * CSV export
  * Filtered export options

4. System Health Monitoring:
- Real-time system status overview
- Automatic anomaly detection
- Performance statistics
- Error rate monitoring
- Visual indicators for system health status

5. Log Analysis API:
- Query logs: `GET /api/logs/query`
- Generate statistics: `GET /api/logs/stats`
- Generate dashboard: `GET /api/logs/dashboard`
- Export logs: `GET /api/logs/export`

### Installation
```bash
# Install dependencies
pnpm install

# Development mode (with hot-reload)
python dev.py

# Production mode
uvicorn amazon_crawler_api:app --host 0.0.0.0 --port 8000
```

### API Documentation
Access the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Development
The project supports hot-reload during development:

1. Start in development mode:
```bash
python dev.py
```

2. Features in development mode:
- Hot-reload enabled
- Auto-restart on code changes
- Debug logging
- Monitored directories: `.` and `models/`

3. Environment configuration:
```bash
# Development settings in .env
API_HOST=127.0.0.1  # Development server host
API_PORT=8000       # Development server port
DEBUG_MODE=True     # Enable debug mode
```

---

## Chinese

### 项目概述
一个用于获取Amazon优惠和商品信息的综合平台，使用FastAPI框架实现网页爬虫和PA-API集成功能。

### 功能特点
- 爬取Amazon优惠页面获取商品ASIN
  - 支持保持商品显示顺序
  - 智能处理颜色变体（避免重复ASIN）
  - 智能滚动和分页加载
  - 可配置超时和商品数量限制
- 通过PA-API获取详细商品信息
- 所有功能均提供RESTful API接口
- 后台任务处理
- 支持多种输出格式（JSON、CSV、TXT）
- 健康监控接口
- YAML配置文件支持，灵活控制爬虫行为
- 清晰区分数据来源和API提供者
  - 数据来源：bestseller/coupon爬虫
  - API提供者：PA-API（可扩展支持其他API）
- 独立的折扣和优惠券商品接口

### 项目结构
```
.
├── README.md                  # 项目文档
├── amazon_crawler_api.py      # 主API实现
├── amazon_bestseller.py       # 爬虫核心逻辑
├── amazon_product_api.py      # PA-API集成
├── config/                    # 配置文件目录
│   └── crawler.yaml          # 爬虫配置文件
├── models/                    # 数据模型
│   ├── __init__.py
│   ├── crawler.py            # 爬虫相关模型
│   ├── product.py            # 商品相关模型
│   └── cache_manager.py      # 缓存管理器
├── cache/                    # 缓存目录
└── crawler_results/          # 爬虫结果输出目录
```

### 爬虫使用方法
```bash
# 基本用法（使用默认配置）
python collect_products.py

# 使用配置文件
python collect_products.py --config config/crawler.yaml

# 使用命令行参数
python collect_products.py --crawler-type bestseller --max-items 100 --timeout 60 --no-headless

# 参数说明：
--config        配置文件路径（YAML格式）
--crawler-type  爬虫类型（bestseller/coupon/all）
--max-items     要爬取的商品数量（默认：100）
--batch-size    API批量请求大小（默认：10）
--timeout       无新商品超时时间（默认：30秒）
--no-headless   禁用无头模式
```

### 配置文件说明 (crawler.yaml)
```yaml
# 爬虫类型配置（选择以下配置之一）
# 方式1：运行单个爬虫
crawler_types: bestseller    # 或 coupon 或 all

# 方式2：运行多个爬虫（取消注释下面的配置）
# crawler_types: 
#   - bestseller
#   - coupon

# 数据采集参数
max_items: 100   # 每类商品的最大采集数量
batch_size: 10   # API批量请求大小(1-10)
timeout: 30      # 爬虫超时时间(秒)

# 浏览器配置
headless: true   # true=无界面模式，false=显示浏览器窗口
```

### API接口
- **爬虫相关接口**
  - `POST /api/crawl` - 启动新的爬虫任务
  - `GET /api/status/{task_id}` - 检查任务状态
  - `GET /api/download/{task_id}` - 下载爬虫结果

- **商品相关接口**
  - `POST /api/products` - 获取商品信息
  - `POST /api/products/save` - 保存商品信息到文件

- **调度器接口**
  - `POST /api/scheduler/jobs` - 添加新的调度任务
  - `GET /api/scheduler/jobs` - 列出所有调度任务
  - `DELETE /api/scheduler/jobs/{job_id}` - 删除特定任务
  - `POST /api/scheduler/jobs/{job_id}/pause` - 暂停特定任务
  - `POST /api/scheduler/jobs/{job_id}/resume` - 恢复特定任务
  - `GET /api/scheduler/jobs/{job_id}/history` - 获取任务执行历史
  - `GET /api/scheduler/status` - 获取调度器状态
  - `POST /api/scheduler/start` - 启动调度器
  - `POST /api/scheduler/stop` - 停止调度器
  - `POST /api/scheduler/reload` - 重新加载调度器配置

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

# Scheduler Configuration
SCHEDULER_TIMEZONE=Asia/Shanghai  # Default timezone for scheduler
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

### 调度器系统
系统实现了一个灵活的任务调度系统，支持定时和间隔执行任务：

1. 调度器功能：
- 支持cron和interval两种任务类型
- 可配置任务执行时间和间隔
- 任务暂停/恢复控制
- 执行历史记录
- 状态监控
- 时区配置支持
- 单例模式确保全局唯一实例
- 自动任务恢复（系统重启后）
- 任务执行状态追踪
- 错误处理和日志记录

2. 时区配置：
- 默认时区：Asia/Shanghai
- 支持通过环境变量配置默认时区
- 前端界面支持时区选择
- 所有时间显示基于配置的时区
- 支持的时区：
  * Asia/Shanghai
  * Asia/Tokyo
  * America/New_York
  * Europe/London
  * UTC
  * 其他标准时区

3. 任务类型：
- Cron任务：在指定时间点执行
  * 支持标准cron表达式
  * 支持小时和分钟级别的配置
  * 支持间隔执行（如：每4小时）
- 间隔任务：按固定时间间隔执行
  * 支持小时和分钟级别的间隔
  * 精确的时间控制
  * 自动计算下次执行时间

4. 任务配置示例：
```yaml
# Cron任务示例
{
  "id": "bestseller_daily",
  "type": "cron",
  "crawler_type": "bestseller",
  "max_items": 200,
  "hour": "*/4",    # 每4小时执行一次
  "minute": "30"    # 在每小时的第30分钟执行
}

# 间隔任务示例
{
  "id": "coupon_hourly",
  "type": "interval",
  "crawler_type": "coupon",
  "max_items": 100,
  "hours": 1,      # 每1小时
  "minutes": 30    # 零30分钟执行一次
}
```

5. 调度器API：
- 任务管理：
  * 添加任务：POST /api/scheduler/jobs
  * 删除任务：DELETE /api/scheduler/jobs/{job_id}
  * 暂停任务：POST /api/scheduler/jobs/{job_id}/pause
  * 恢复任务：POST /api/scheduler/jobs/{job_id}/resume
- 状态查询：
  * 获取所有任务：GET /api/scheduler/jobs
  * 获取调度器状态：GET /api/scheduler/status
  * 获取任务历史：GET /api/scheduler/jobs/{job_id}/history
- 调度器控制：
  * 启动调度器：POST /api/scheduler/start
  * 停止调度器：POST /api/scheduler/stop
  * 重载调度器：POST /api/scheduler/reload
  * 更新时区：POST /api/scheduler/timezone

6. 前端界面功能：
- 可视化任务管理
  * 添加新任务的表单
  * 任务列表显示
  * 任务控制按钮（暂停/恢复/删除）
- 实时状态显示
  * 运行状态指示
  * 下次执行时间
  * 任务类型和配置
- 执行历史查看
  * 最近10次执行记录
  * 执行状态和结果
  * 错误信息显示
- 多语言支持
  * 中英文界面切换
  * 时间格式本地化
  * 状态信息翻译

7. 数据持久化：
- 使用SQLite数据库存储：
  * Task configuration and status
  * Execution history record
  * Timezone setting
- Database table structure:
  * job_history: Task execution history
  * jobstore: APScheduler task storage

### Logging and Error Handling System
The system implements a comprehensive logging and error handling framework:

1. Structured Logging:
- Centralized log configuration with Loguru
- Different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Contextual logging with request tracking
- Automatic log rotation and retention
- JSON log format support

2. Error Handling:
- Custom error types with error codes
- Error context capturing
- Global exception handler
- Detailed error tracking and statistics
- Automatic error level assignment

3. Log Analysis and Visualization:
- Advanced log querying and filtering:
  * Time-based filtering
  * Module-based filtering
  * Level-based filtering
  * Context-based filtering
  * Pattern matching
- Statistical analysis:
  * Error rate trends
  * Module activity statistics
  * Response time analysis
  * Anomaly detection
- Log visualization dashboard:
  * System health status overview
  * Interactive charts and graphs
  * Error distribution visualization
  * Module activity visualization
  * Response time trend analysis
- Log export capabilities:
  * JSON export
  * CSV export
  * Filtered export options

4. System Health Monitoring:
- Real-time system status overview
- Automatic anomaly detection
- Performance statistics
- Error rate monitoring
- Visual indicators for system health status

5. Log Analysis API:
- Query logs: `GET /api/logs/query`
- Generate statistics: `GET /api/logs/stats`
- Generate dashboard: `GET /api/logs/dashboard`
- Export logs: `GET /api/logs/export`

### Installation
```bash
# 安装依赖
pnpm install

# 开发模式（支持热更新）
python dev.py

# 生产模式
uvicorn amazon_crawler_api:app --host 0.0.0.0 --port 8000
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

### Data Model
The system implements a clear separation between data sources and API providers:

1. Data Sources:
- `bestseller`: Products discovered through bestseller deals crawler
- `coupon`: Products discovered through coupon deals crawler

2. API Providers:
- `pa-api`: Amazon Product Advertising API
- Extensible for future API integrations

3. API Behavior:
- `/api/products/discount`: Returns only products from bestseller source
- `/api/products/coupon`: Returns only products from coupon source
- Both endpoints may use the same API provider (pa-api) for detailed product information

4. 数据更新策略：
- 新增商品时记录来源和API提供者
- 更新商品时保留原始来源
- 始终更新API提供者信息

5. 最佳实践：
- 使用source字段标记数据来源（bestseller/coupon）
- 使用api_provider字段记录数据提供者
- 基于source字段进行API过滤
- 支持未来扩展其他API提供者
