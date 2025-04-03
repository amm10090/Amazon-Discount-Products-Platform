# Loguru 日志系统代码示例

本文档提供了项目中 Loguru 日志系统的各种功能代码示例，可作为开发参考。每个示例均可直接复制使用，帮助快速实现各种日志记录需求。

## 目录

- [基础日志记录](#基础日志记录)
- [上下文管理](#上下文管理)
- [错误处理](#错误处理)
- [API日志记录](#API日志记录)
- [日志分析与可视化](#日志分析与可视化)
- [日志迁移](#日志迁移)

## 基础日志记录

### 初始化日志记录器

```python
from src.utils.log_config import get_logger

# 简单初始化
logger = get_logger("my_module")

# 带有额外上下文的初始化
logger = get_logger("user_service", user_id="12345", component="authentication")
```

### 各级别日志记录

```python
# 调试信息（开发环境）
logger.debug("数据库连接成功，连接ID: {conn_id}", conn_id=db_connection.id)

# 一般信息
logger.info("用户 {username} 已登录系统", username=user.username)

# 警告信息
logger.warning("API响应时间超过预期: {response_time}ms", response_time=duration)

# 错误信息
logger.error("无法连接到数据库: {error}", error=str(exception))

# 严重错误
logger.critical("系统无法启动核心服务: {details}", details=failure_details)
```

### 结构化日志记录

```python
# 记录结构化数据
logger.info("商品信息已更新", extra={
    "product_id": product.id,
    "old_price": old_price,
    "new_price": new_price,
    "price_change": new_price - old_price,
    "change_percent": (new_price - old_price) / old_price * 100 if old_price else 0
})

# 记录复杂对象
user_data = {
    "id": user.id,
    "username": user.username,
    "email": user.email,
    "roles": [role.name for role in user.roles],
    "last_login": user.last_login.isoformat() if user.last_login else None
}
logger.info("用户详情: {user}", user=user_data)
```

### 使用日志装饰器

```python
from src.utils.log_config import log_function_call

# 自动记录函数调用
@log_function_call
def update_product_price(product_id, new_price):
    # 函数逻辑...
    return updated_product

# 带有模块名称的装饰器
@log_function_call
def delete_product(product_id):
    # 函数逻辑...
    pass
```

## 上下文管理

### 使用上下文管理器

```python
from src.utils.log_config import LogContext

# 基本上下文
with LogContext(task_id="123", operation="data_import"):
    logger.info("开始导入数据")
    # 操作代码...
    logger.info("数据导入完成")

# 嵌套上下文
with LogContext(request_id="req123"):
    logger.info("开始处理请求")
    
    # 处理用户认证
    with LogContext(operation="authentication"):
        logger.info("验证用户凭证")
        # 认证逻辑...
    
    # 处理业务逻辑
    with LogContext(operation="business_logic"):
        logger.info("执行业务逻辑")
        # 业务逻辑...
    
    logger.info("请求处理完成")
```

### 异步上下文管理

```python
from src.utils.log_config import LogContext
import asyncio

async def process_async_request(request_data):
    async with LogContext(request_id=request_data["id"]):
        logger.info("开始处理异步请求")
        
        # 异步操作...
        await asyncio.sleep(1)
        
        logger.info("异步请求处理完成")

# 绑定上下文到任务
async def main():
    task = asyncio.create_task(some_coroutine())
    await bind_context(task, task_id="task123")
```

### 性能跟踪

```python
from src.utils.log_config import LogContext, track_performance

# 使用上下文管理器跟踪性能
with LogContext(operation="data_processing", track_performance=True):
    # 耗时操作...
    process_large_dataset()

# 使用装饰器跟踪性能
@track_performance
def expensive_database_query():
    # 数据库查询...
    return results
```

## 错误处理

### 基本异常记录

```python
try:
    # 可能引发异常的代码
    result = process_data(input_data)
except ValueError as e:
    logger.error(f"数据处理失败: {e}")
except Exception as e:
    logger.exception("发生未预期的错误")  # 自动包含异常堆栈
```

### 使用错误处理装饰器

```python
from src.utils.error_handling import error_handler, ErrorCode, ErrorLevel

@error_handler(
    default_error_code=ErrorCode.DATABASE_ERROR,
    error_level=ErrorLevel.ERROR,
    capture_exception=True
)
def update_database_record(record_id, data):
    # 数据库操作...
    return updated_record

# 带有自定义错误映射的装饰器
@error_handler(
    default_error_code=ErrorCode.API_ERROR,
    error_mapping={
        ConnectionError: (ErrorCode.NETWORK_ERROR, ErrorLevel.ERROR),
        TimeoutError: (ErrorCode.TIMEOUT_ERROR, ErrorLevel.WARNING),
        ValueError: (ErrorCode.VALIDATION_ERROR, ErrorLevel.WARNING)
    }
)
def call_external_api(endpoint, payload):
    # API调用...
    return response
```

### 自定义异常处理

```python
from src.utils.error_handling import CustomException, ErrorCode

# 抛出自定义异常
def validate_user_input(data):
    if not data.get("username"):
        raise CustomException(
            message="用户名不能为空",
            error_code=ErrorCode.VALIDATION_ERROR,
            context={"data": data}
        )

# 使用错误处理上下文管理器
from src.utils.error_handling import error_context

with error_context(operation="file_processing"):
    # 文件处理逻辑
    process_file(file_path)
```

## API日志记录

### 记录API请求和响应

```python
from src.utils.api_logger import APILogger

api_logger = APILogger()

# 记录API请求
response = requests.get("https://api.example.com/products")
api_logger.log_response(response, operation="get_products")

# 包含请求信息
api_logger.log_request_response(
    method="POST",
    url="https://api.example.com/orders",
    data=order_data,
    response=response,
    operation="create_order"
)
```

### 敏感信息过滤

```python
from src.utils.api_logger import APILogger

# 初始化带有敏感字段的API记录器
api_logger = APILogger(
    sensitive_fields=["password", "credit_card", "token", "secret"]
)

# 记录包含敏感信息的请求
api_logger.log_request_response(
    method="POST",
    url="https://api.example.com/login",
    data={
        "username": "user123",
        "password": "supersecretpassword"  # 会被遮蔽
    },
    response=response,
    operation="user_login"
)
```

### 集成到FastAPI中

```python
from fastapi import FastAPI, Request, Response
from src.utils.api_logger import APILogger
from src.utils.log_config import LogContext

app = FastAPI()
api_logger = APILogger()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 提取请求信息
    request_id = str(uuid.uuid4())
    client_ip = request.client.host
    
    # 创建请求上下文
    async with LogContext(request_id=request_id, client_ip=client_ip):
        # 记录请求开始
        start_time = time.time()
        
        # 处理请求
        response = await call_next(request)
        
        # 记录请求结束
        duration = time.time() - start_time
        status_code = response.status_code
        
        # 使用API记录器记录请求信息
        await api_logger.log_fastapi_request(
            request=request,
            response=response,
            duration=duration,
            operation=f"{request.method} {request.url.path}"
        )
        
        return response
```

## 日志分析与可视化

### 基本日志查询

```python
from src.utils.log_analysis import LogQuery

# 初始化日志查询
log_query = LogQuery("logs")

# 查询特定时间段的错误日志
from datetime import datetime, timedelta

yesterday = datetime.now() - timedelta(days=1)
error_logs = log_query.search(
    start_time=yesterday,
    end_time=datetime.now(),
    level="ERROR",
    limit=100
)

# 查询特定模块的日志
auth_logs = log_query.search(
    module="auth_service",
    message_pattern="login failed",
    limit=50
)
```

### 日志聚合分析

```python
from src.utils.log_analysis import LogAnalytics

# 初始化分析工具
log_query = LogQuery("logs")
analytics = LogAnalytics(log_query)

# 获取错误分布
error_distribution = analytics.get_error_distribution(
    start_time=datetime.now() - timedelta(days=7),
    group_by="day"
)

# 检测响应时间异常
response_time_anomalies = analytics.detect_anomalies(
    metric="response_time",
    threshold=3.0  # 标准差的倍数
)

# 输出分析结果
print(f"过去7天的每日错误分布: {error_distribution}")
print(f"检测到的响应时间异常: {len(response_time_anomalies)}")
```

### 生成可视化图表

```python
from src.utils.log_visualization import LogChartGenerator

# 初始化图表生成器
log_query = LogQuery("logs")
chart_generator = LogChartGenerator(log_query)

# 生成错误率图表
error_chart_path = chart_generator.error_rate_chart(
    start_time=datetime.now() - timedelta(days=30),
    interval="day",
    output_path="reports/error_rate.png"
)

# 生成响应时间图表
response_time_chart_path = chart_generator.response_time_chart(
    start_time=datetime.now() - timedelta(days=7),
    output_path="reports/response_time.png"
)

# 生成模块活动图表
activity_chart_path = chart_generator.module_activity_chart(
    start_time=datetime.now() - timedelta(days=7),
    output_path="reports/module_activity.png"
)
```

### 生成系统健康仪表板

```python
from src.utils.log_visualization import SystemHealthDashboard

# 初始化仪表板生成器
dashboard = SystemHealthDashboard("logs")

# 生成包含多个图表的仪表板
dashboard_files = dashboard.generate_dashboard(
    start_time=datetime.now() - timedelta(days=7),
    output_dir="reports/dashboard"
)

# 获取仪表板HTML文件路径
dashboard_html = dashboard_files["dashboard"]
print(f"系统健康仪表板已生成: {dashboard_html}")
```

### 导出日志数据

```python
from src.utils.log_visualization import LogExporter

# 初始化日志导出器
log_query = LogQuery("logs")
exporter = LogExporter(log_query)

# 导出为JSON格式
json_path = exporter.export_to_json(
    output_path="exports/error_logs.json",
    start_time=datetime.now() - timedelta(days=7),
    level="ERROR"
)

# 导出为CSV格式
csv_path = exporter.export_to_csv(
    output_path="exports/api_logs.csv",
    start_time=datetime.now() - timedelta(days=1),
    module="api_service"
)
```

## 日志迁移

### 使用双重日志记录

```python
from src.utils.dual_logging import DualLogger

# 初始化双重日志记录器
dual_logger = DualLogger(name="migration_module")

# 记录基本日志
dual_logger.debug("这是调试信息")
dual_logger.info("这是一般信息")
dual_logger.warning("这是警告信息")
dual_logger.error("这是错误信息")
dual_logger.critical("这是严重错误信息")

# 记录带有额外信息的日志
dual_logger.info(
    "用户操作已完成",
    extra={"user_id": "12345", "action": "update_profile"}
)

# 记录异常信息
try:
    # 可能引发异常的代码
    result = process_data()
except Exception as e:
    dual_logger.exception("处理数据时出错: %s", str(e))
```

### 验证迁移结果

```python
from src.utils.log_audit import LogVerifier

# 初始化日志验证器
verifier = LogVerifier(
    original_module="old_logging_module",
    migrated_module="new_loguru_module"
)

# 验证特定函数的日志输出
result = verifier.verify_function(
    "process_data",
    test_input_data
)

if result["success"]:
    print("日志输出一致，迁移成功!")
else:
    print(f"日志输出不一致: {result['differences']}")

# 生成完整验证报告
report = verifier.generate_report()
print(report)
``` 