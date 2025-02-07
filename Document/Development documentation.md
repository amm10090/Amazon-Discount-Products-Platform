# Amazon优惠商品平台开发文档

## 目录
1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [环境要求](#3-环境要求)
4. [项目结构](#4-项目结构)
5. [配置说明](#5-配置说明)
6. [核心模块](#6-核心模块)
7. [API文档](#7-api文档)
8. [前端界面](#8-前端界面)
9. [部署指南](#9-部署指南)
10. [开发指南](#10-开发指南)

## 1. 项目概述

### 1.1 项目简介
本项目是一个用于获取和管理Amazon优惠商品信息的综合平台，集成了爬虫、PA-API、数据分析和管理功能。

### 1.2 主要功能
- Amazon商品数据采集
- 优惠商品实时监控
- 数据分析和可视化
- 定时任务调度管理
- 多语言支持

### 1.3 技术栈
- 后端：Python FastAPI
- 前端：Streamlit
- 数据库：SQLite/PostgreSQL
- 缓存：Redis(可选)
- 爬虫：Selenium
- API：Amazon PA-API

## 2. 系统架构

### 2.1 整体架构
```
+----------------+     +----------------+     +---------------+
|   前端界面      |     |   FastAPI服务   |     |  数据存储层    |
| (Streamlit)    | --> |   (后端API)    | --> |  (DB/Cache)  |
+----------------+     +----------------+     +---------------+
                            |
                            v
                    +----------------+
                    |   数据采集服务   |
                    | (爬虫/PA-API)   |
                    +----------------+
```

### 2.2 模块划分
- 数据采集模块
- API服务模块
- 前端展示模块
- 任务调度模块
- 数据分析模块

## 3. 环境要求

### 3.1 系统要求
- Python 3.7+
- Chrome浏览器（爬虫使用）
- Redis（可选，用于缓存）
- SQLite/PostgreSQL

### 3.2 依赖安装
```bash
# 安装项目依赖
pip install -r requirements.txt

# requirements.txt主要依赖：
fastapi==0.68.0
streamlit==1.8.0
selenium==4.1.0
sqlalchemy==1.4.23
aiohttp==3.8.1
pandas==1.3.3
plotly==5.5.0
```

## 4. 项目结构

### 4.1 目录结构
```
项目根目录/
├── config/          # 配置文件目录
│   ├── app.yaml           # 主应用配置
│   ├── cache_config.yaml  # 缓存配置
│   ├── crawler.yaml       # 爬虫配置
│   ├── development.yaml   # 开发环境配置
│   └── production.yaml    # 生产环境配置
├── data/           # 数据存储目录
│   ├── coupon_deals/      # 优惠券数据
│   ├── crawler_results/   # 爬虫结果
│   └── db/               # 数据库文件
├── frontend/       # 前端应用
│   ├── main.py           # 主入口
│   └── pages/           # 功能页面
├── models/         # 数据模型
├── src/            # 源代码
│   ├── core/           # 核心功能
│   └── utils/          # 工具类
└── deploy/         # 部署配置
```

### 4.2 关键文件说明
- `run.py`: 应用程序入口
- `src/core/amazon_crawler_api.py`: API服务实现
- `src/core/collect_products.py`: 数据采集实现
- `models/database.py`: 数据库模型定义
- `frontend/main.py`: 前端主程序

## 5. 配置说明

### 5.1 应用配置 (app.yaml)
```yaml
environment: production
api:
  host: "0.0.0.0"
  port: 5001
frontend:
  host: "0.0.0.0"
  port: 5002
  theme:
    primaryColor: "#ff9900"
```

### 5.2 缓存配置 (cache_config.yaml)
```yaml
cache:
  base_dir: "cache"
  ttl:
    offers: 3600
    browse_nodes: 3600
    others: 86400
```

### 5.3 爬虫配置 (crawler.yaml)
```yaml
crawler_types: all
max_items: 100
batch_size: 10
timeout: 30
headless: true
```

## 6. 核心模块

### 6.1 数据采集核心模块

#### 6.1.1 商品采集协调器 (collect_products.py)
```python
"""
商品数据采集的核心协调模块，负责整合不同数据源的采集过程
主要功能：
1. 协调多种数据源的采集
2. 统一数据处理和存储
3. 错误处理和重试机制
4. 采集任务状态管理
"""

async def collect_products(config: Config) -> None:
    """
    主采集流程：
    1. 初始化数据库连接
    2. 创建PA-API客户端
    3. 根据配置执行不同类型的采集任务
    4. 处理和存储采集结果
    """

async def crawl_bestseller_products(
    api: AmazonProductAPI,
    max_items: int,
    batch_size: int,
    timeout: int,
    headless: bool
) -> int:
    """畅销商品采集流程"""

async def crawl_coupon_products(
    api: AmazonProductAPI,
    max_items: int,
    batch_size: int,
    timeout: int,
    headless: bool
) -> int:
    """优惠券商品采集流程"""
```

#### 6.1.2 Amazon PA-API客户端 (amazon_product_api.py)
```python
"""
Amazon Product Advertising API的异步客户端实现
特点：
1. 异步HTTP请求
2. 智能重试机制
3. 请求限流控制
4. 结果缓存支持
"""

class AmazonProductAPI:
    async def get_products_by_asins(self, asins: List[str]) -> List[ProductInfo]:
        """
        批量获取商品详细信息
        流程：
        1. 检查缓存
        2. 构建API请求
        3. 发送请求并等待响应
        4. 解析响应数据
        5. 更新缓存
        6. 返回结果
        """

    def _sign(self, key: bytes, msg: str) -> bytes:
        """AWS签名计算"""

    def _serialize(self, data: Any) -> bytes:
        """数据序列化处理"""
```

#### 6.1.3 畅销商品爬虫 (amazon_bestseller.py)
```python
"""
Amazon畅销商品爬虫模块
特点：
1. 基于Selenium的动态页面爬取
2. 智能页面滚动
3. 自动重试机制
4. 数据验证和清洗
"""

async def crawl_deals(
    max_items: int = 100,
    timeout: int = 30,
    headless: bool = True
) -> List[str]:
    """
    爬取畅销商品流程：
    1. 初始化WebDriver
    2. 访问目标页面
    3. 智能滚动加载
    4. 提取商品ASIN
    5. 数据验证和去重
    """

def scroll_page(driver, scroll_count: int):
    """智能滚动算法"""

def extract_asin_from_url(url: str) -> Optional[str]:
    """URL解析和ASIN提取"""
```

#### 6.1.4 优惠券爬虫 (amazon_coupon_crawler.py)
```python
"""
Amazon优惠券商品爬虫模块
特点：
1. 优惠券信息精确提取
2. 实时价格监控
3. 优惠力度分析
4. 历史记录追踪
"""

async def crawl_coupon_deals(
    max_items: int,
    timeout: int,
    headless: bool
) -> tuple[List[Dict], CrawlStats]:
    """
    优惠券商品爬取流程：
    1. 初始化爬虫
    2. 页面导航和加载
    3. 提取优惠券信息
    4. 统计分析处理
    5. 数据存储和缓存
    """

def extract_coupon_info(card_element) -> Optional[Dict]:
    """优惠券信息解析"""

def process_visible_products(
    driver,
    seen_asins: set,
    stats: CrawlStats
) -> List[Dict]:
    """商品信息处理"""
```

#### 6.1.5 调度服务 (service_scheduler.py)
```python
"""
任务调度服务模块
功能：
1. 定时任务管理
2. 任务状态追踪
3. 执行历史记录
4. 错误处理和恢复
"""

class SchedulerManager:
    """
    调度管理器实现：
    1. 单例模式确保全局唯一
    2. 支持多种调度策略
    3. 任务执行状态监控
    4. 数据库持久化
    """

    async def _execute_crawler(
        self,
        job_id: str,
        crawler_type: str,
        max_items: int
    ):
        """
        爬虫任务执行器：
        1. 任务参数验证
        2. 环境准备
        3. 调用相应爬虫
        4. 结果处理和存储
        5. 状态更新
        """
```

### 6.8 模块交互关系

### 6.9 核心模块集成

#### 6.9.1 数据采集与API集成
```python
# collect_products.py 与 amazon_product_api.py 的集成
async def collect_products(config: Config) -> None:
    """数据采集与API集成流程"""
    # 1. 初始化API客户端
    api = AmazonProductAPI(
        access_key=os.getenv("AMAZON_ACCESS_KEY"),
        secret_key=os.getenv("AMAZON_SECRET_KEY"),
        partner_tag=os.getenv("AMAZON_PARTNER_TAG")
    )
    
    # 2. 根据配置选择爬虫
    if config.crawler_type == "bestseller":
        asins = await crawl_bestseller_products(...)
    elif config.crawler_type == "coupon":
        asins = await crawl_coupon_products(...)
        
    # 3. 通过API获取详细信息
    products = await api.get_products_by_asins(asins)
    
    # 4. 存储数据
    with SessionLocal() as db:
        ProductService.bulk_create_or_update_products(db, products)
```

#### 6.9.2 调度器与爬虫集成
```python
# service_scheduler.py 与爬虫模块的集成
class SchedulerManager:
    async def _execute_crawler(self, job_id: str, crawler_type: str):
        """调度器执行爬虫任务"""
        try:
            # 1. 准备配置
            config = Config(
                crawler_type=crawler_type,
                max_items=100,
                headless=True
            )
            
            # 2. 执行采集
            await collect_products(config)
            
            # 3. 更新任务状态
            self.update_job_status(job_id, "completed")
            
        except Exception as e:
            # 4. 错误处理
            self.update_job_status(job_id, "failed", error=str(e))
```

#### 6.9.3 前端与API服务集成
```python
# frontend/pages/products.py 与 FastAPI服务集成
@cache_manager.data_cache(ttl=300)
async def load_products(api_url: str, **params) -> List[Dict]:
    """前端数据加载与API集成"""
    try:
        # 1. 调用API
        response = await httpx.get(f"{api_url}/api/products/list", params=params)
        data = response.json()
        
        # 2. 数据处理
        products = process_products_data(data)
        
        # 3. 缓存结果
        return products
    except Exception as e:
        log_error(f"加载商品数据失败: {str(e)}")
        return []
```

#### 6.9.4 错误处理链
```python
# 错误处理在各模块间的传递
try:
    # 1. 爬虫层错误
    async with WebDriverManager() as driver:
        try:
            products = await crawl_products(driver)
        except WebDriverException as e:
            raise CrawlerError(f"爬虫错误: {str(e)}")
            
    # 2. API层错误
    try:
        api_products = await api.get_products_by_asins(products)
    except APIError as e:
        raise DataProcessError(f"API错误: {str(e)}")
        
    # 3. 数据库层错误
    try:
        db.save_products(api_products)
    except DBError as e:
        raise StorageError(f"存储错误: {str(e)}")
        
except Exception as e:
    # 4. 全局错误处理
    log_error(str(e))
    notify_admin(e)
```

#### 6.9.5 数据流监控
```python
# 数据流监控和统计
class DataFlowMonitor:
    def __init__(self):
        self.stats = {
            "crawled": 0,
            "processed": 0,
            "stored": 0,
            "errors": 0
        }
    
    def update_stats(self, stage: str, count: int):
        """更新数据流统计"""
        self.stats[stage] += count
        
    def get_summary(self) -> Dict:
        """获取数据流摘要"""
        return {
            "total_crawled": self.stats["crawled"],
            "success_rate": (self.stats["stored"] / self.stats["crawled"]) * 100,
            "error_rate": (self.stats["errors"] / self.stats["crawled"]) * 100
        }
```

#### 6.9.6 性能优化策略
1. 并发控制：
```python
# 爬虫并发控制
async def crawl_with_concurrency(asins: List[str], max_concurrent: int = 3):
    """控制并发爬取数量"""
    semaphore = asyncio.Semaphore(max_concurrent)
    async with semaphore:
        tasks = [crawl_single_product(asin) for asin in asins]
        return await asyncio.gather(*tasks)
```

2. 批量处理：
```python
# 数据批量处理
def batch_process_products(products: List[Dict], batch_size: int = 100):
    """批量处理商品数据"""
    for i in range(0, len(products), batch_size):
        batch = products[i:i + batch_size]
        process_batch(batch)
```

3. 缓存策略：
```python
# 多级缓存策略
class CacheStrategy:
    def __init__(self):
        self.memory_cache = {}  # 内存缓存
        self.redis_cache = Redis()  # Redis缓存
        
    async def get_product(self, asin: str) -> Optional[Dict]:
        """多级缓存获取"""
        # 1. 检查内存缓存
        if asin in self.memory_cache:
            return self.memory_cache[asin]
            
        # 2. 检查Redis缓存
        if await self.redis_cache.exists(asin):
            return await self.redis_cache.get(asin)
            
        # 3. 从数据库获取
        product = await db.get_product(asin)
        
        # 4. 更新缓存
        if product:
            self.update_cache(asin, product)
            
        return product
```

## 7. API文档

### 7.1 商品相关API
```
GET /api/products/list - 获取商品列表
GET /api/products/{asin} - 获取商品详情
POST /api/products/batch-delete - 批量删除商品
```

### 7.2 调度器相关API
```
GET /api/scheduler/jobs - 获取任务列表
POST /api/scheduler/jobs - 添加新任务
DELETE /api/scheduler/jobs/{job_id} - 删除任务
```

## 8. 前端界面

### 8.1 页面说明
- `pages/products.py`: 商品管理页面
- `pages/analysis.py`: 数据分析页面
- `pages/scheduler.py`: 调度管理页面

### 8.2 国际化支持
文件位置：`frontend/i18n/translations.py`
```python
translations = {
    "zh": {
        "products_title": "商品管理",
        "analysis_title": "数据分析",
        # ...
    }
}
```

## 9. 部署指南

### 9.1 环境准备
```bash
# 1. 克隆代码
git clone <repository_url>

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### 9.2 配置文件
1. 复制并修改配置文件
```bash
cp config/development.yaml config/production.yaml
```

2. 设置环境变量
```bash
export AMAZON_ACCESS_KEY="your_access_key"
export AMAZON_SECRET_KEY="your_secret_key"
export AMAZON_PARTNER_TAG="your_partner_tag"
```

### 9.3 启动服务
```bash
# 启动API服务
python run.py --mode api

# 启动前端服务
python run.py --mode frontend
```

## 10. 开发指南

### 10.1 开发环境设置
```bash
# 1. 安装开发依赖
pip install -r requirements-dev.txt

# 2. 设置开发环境配置
export ENV=development
```

### 10.2 代码规范
- 使用Python Type Hints
- 遵循PEP 8规范
- 编写详细的文档字符串

### 10.3 测试
```bash
# 运行测试
pytest src/tests/

# 运行特定测试
pytest src/tests/test_crawler.py
```

### 10.4 日志管理
文件位置：`src/utils/logger_manager.py`
```python
# 使用示例
from src.utils.logger_manager import log_info, log_error

log_info("操作成功")
log_error("发生错误")
```

### 10.5 缓存使用
文件位置：`src/utils/cache_manager.py`
```python
# 使用示例
from src.utils.cache_manager import cache_manager

@cache_manager.cache_decorator(cache_type="products")
async def get_product(asin: str):
    # 获取商品信息
    pass
```

