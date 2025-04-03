# Loguru 日志系统培训与知识转移

本文档旨在为开发团队提供关于本项目中 Loguru 日志系统的培训材料和知识转移指南。目标是确保团队成员能够理解、有效使用并维护该日志系统。

## 目录

1.  [引言与目标](#1-引言与目标)
2.  [日志系统概览](#2-日志系统概览)
    -   [核心组件](#核心组件)
    -   [主要特性](#主要特性)
3.  [快速上手](#3-快速上手)
    -   [基本配置](#基本配置)
    -   [简单日志记录](#简单日志记录)
4.  [核心功能详解](#4-核心功能详解)
    -   [日志级别](#日志级别)
    -   [日志格式化](#日志格式化)
    -   [上下文管理](#上下文管理)
    -   [错误与异常处理](#错误与异常处理)
    -   [API 调用日志](#api-调用日志)
5.  [实用工具介绍](#5-实用工具介绍)
    -   [日志分析与查询 (`LogQuery`)](#日志分析与查询-logquery)
    -   [日志统计与聚合 (`LogAnalytics`)](#日志统计与聚合-loganalytics)
    -   [日志可视化 (`LogChartGenerator`, `SystemHealthDashboard`)](#日志可视化-logchartgenerator-systemhealthdashboard)
    -   [日志质量评估 (`LogQualityAnalyzer`)](#日志质量评估-logqualityanalyzer)
    -   [日志审计 (`LogAuditor`, `LogVerifier`)](#日志审计-logauditor-logverifier)
6.  [最佳实践与规范](#6-最佳实践与规范)
    -   [何时记录日志](#何时记录日志)
    -   [写什么日志](#写什么日志)
    -   [日志级别选择](#日志级别选择-1)
    -   [上下文的重要性](#上下文的重要性)
    -   [性能考量](#性能考量)
7.  [常见问题与故障排查](#7-常见问题与故障排查)
8.  [知识资源](#8-知识资源)

---

## 1. 引言与目标

**目标：**
-   理解本项目中 Loguru 日志系统的架构和优势。
-   掌握使用 Loguru 进行有效日志记录的基本和高级技巧。
-   了解如何利用提供的日志分析和可视化工具。
-   遵循项目定义的日志记录标准和最佳实践。
-   能够独立排查常见的日志相关问题。

**为什么选择 Loguru？**
-   简洁易用的 API。
-   开箱即用的丰富功能（颜色、格式化、轮转、压缩等）。
-   强大的上下文管理。
-   更好的异常格式化。
-   高性能（特别是结合异步使用时）。

## 2. 日志系统概览

### 核心组件

-   **`src/utils/log_config.py`**: 核心配置模块，封装了 Loguru 的初始化、处理器配置、上下文管理 (`LogContext`) 和常用辅助函数 (`get_logger`, `log_function_call`)。
-   **`src/utils/error_handling.py`**: 错误处理模块，定义了自定义异常、错误码，并集成了全局异常捕获与日志记录。
-   **`src/utils/api_logger.py`**: API 调用日志记录器，用于记录 HTTP 请求和响应。
-   **`src/utils/log_analysis.py`**: 日志分析工具，提供查询 (`LogQuery`)、聚合和异常检测 (`LogAnalytics`) 功能。
-   **`src/utils/log_visualization.py`**: 日志可视化工具，生成图表 (`LogChartGenerator`) 和系统健康仪表板 (`SystemHealthDashboard`)。
-   **`src/utils/log_quality.py`**: 日志质量评估工具，用于分析代码库中的日志实践。
-   **`src/utils/log_audit.py`**: 日志审计工具，用于比较不同日志实现的输出。
-   **`src/utils/dual_logging.py`**: （过渡性）双重日志记录器，用于平滑迁移。

### 主要特性

-   **多目标输出：** 同时输出到控制台（带颜色）和文件（自动轮转、压缩）。
-   **JSON/文本格式：** 支持结构化 JSON 日志和可读性强的文本格式。
-   **上下文注入：** 通过 `LogContext` 或装饰器自动或手动添加上下文信息（如 `task_id`, `user_id`）。
-   **性能追踪：** `LogContext` 可用于记录代码块执行时间。
-   **全局错误捕获：** 自动捕获未处理的异常并记录详细信息。
-   **日志分析与可视化：** 提供工具查询、分析日志数据并生成图表和仪表板。
-   **异步日志：** 支持将日志写入操作移至后台，减少主线程阻塞。

## 3. 快速上手

### 基本配置

系统已通过 `src/utils/log_config.py` 进行了默认配置。在应用入口处（如 `main.py`）通常会自动初始化。

### 简单日志记录

在任何模块中，直接导入并使用 `logger` 或获取特定模块的 logger：

```python
# 方式一：直接使用全局 logger (不推荐在大型模块中使用)
# from loguru import logger 
# logger.info("这是一条信息日志")

# 方式二：获取带名称的 logger (推荐)
from src.utils.log_config import get_logger

# 获取当前模块的 logger
logger = get_logger(__name__) 

# 记录不同级别的日志
logger.debug("详细的调试信息")
logger.info("程序运行的关键信息")
logger.warning("潜在问题或警告")
logger.error("发生错误，但不影响程序继续运行")
logger.critical("严重错误，可能导致程序终止")

# 记录异常
try:
    result = 1 / 0
except ZeroDivisionError:
    logger.exception("计算失败") # 会自动附加异常信息
```

## 4. 核心功能详解

### 日志级别

-   **TRACE (5):** 比 DEBUG 更详细的信息。
-   **DEBUG (10):** 用于诊断问题的详细信息。
-   **INFO (20):** 确认程序按预期运行的常规信息。
-   **SUCCESS (25):** 操作成功的标志（自定义级别）。
-   **WARNING (30):** 表明发生了意外或潜在问题，但程序仍能工作。
-   **ERROR (40):** 由于更严重的问题，程序的某些功能无法执行。
-   **CRITICAL (50):** 严重错误，表明程序本身可能无法继续运行。

> **注意:** 生产环境通常设置为 `INFO` 或 `WARNING`，可以通过环境变量 `LOG_LEVEL` 控制。

### 日志格式化

-   **控制台：** 带有颜色，包含时间、级别、模块名、代码位置和消息。
-   **文件（文本）：** 更详细，包含进程和线程信息。
-   **文件（JSON）：** 如果 `JSON_LOGS` 配置为 `True`，日志将以 JSON 格式存储，便于机器解析。
-   **消息格式化：** 推荐使用 f-string 或 Loguru 的 `{}` 占位符。
    ```python
    user = "Alice"
    logger.info(f"用户 {user} 登录成功")
    logger.info("处理任务 {} 完成", task_id)
    ```

### 上下文管理 (`LogContext`)

自动将上下文信息（如请求 ID、用户 ID）添加到范围内的所有日志记录中。

```python
from src.utils.log_config import LogContext, logger

def process_request(request_id):
    with LogContext(req_id=request_id, component='Processor'):
        logger.info("开始处理请求")
        # ... 执行操作 ...
        logger.debug("获取数据...")
        # 离开 'with' 块后，req_id 和 component 会自动移除
    logger.info("请求处理完成") # 这条日志不包含 req_id

# 异步使用
async def handle_async_task(task_id):
    async with LogContext(task_id=task_id):
        logger.info("异步任务开始")
        await asyncio.sleep(1)
        logger.info("异步任务结束")

# 装饰器
from src.utils.log_config import with_context

@with_context(service='AuthService')
def authenticate_user(username):
    logger.info(f"尝试认证用户 {username}")
```

### 错误与异常处理

-   **自动捕获：** `src/utils/error_handling.py` 配置了全局异常钩子，未捕获的异常会被自动记录。
-   **手动记录：** 使用 `logger.exception()` 在 `except` 块中记录异常信息。
-   **自定义异常：** 可以使用 `src.utils.error_handling.CustomException` 结合错误码。

```python
from src.utils.error_handling import error_handler, ErrorCode

@error_handler(default_message="处理数据时发生错误")
def process_data(data):
    try:
        # ... 处理 ...
        if data is None:
            raise ValueError("数据不能为空")
    except ValueError as e:
        logger.error("数据验证失败: {}", e, error_code=ErrorCode.VALIDATION_ERROR)
        # 或者 logger.exception("数据验证失败", error_code=ErrorCode.VALIDATION_ERROR) 
```

### API 调用日志

使用 `src.utils.api_logger.APILogger` 记录对外部 API 的调用。

```python
from src.utils.api_logger import APILogger

api_logger = APILogger(service_name="ExternalPaymentAPI")

async def make_payment(payload):
    # ... 准备请求 ...
    request_info = api_logger.log_request(url, method="POST", headers=headers, data=payload)
    try:
        response = await http_client.post(url, json=payload, headers=headers)
        api_logger.log_response(request_info, status_code=response.status_code, response_data=response.text)
        # ... 处理响应 ...
    except Exception as e:
        api_logger.log_error(request_info, error=e)
        raise
```

## 5. 实用工具介绍

### 日志分析与查询 (`LogQuery`)

用于搜索和过滤日志文件。

```python
from src.utils.log_analysis import LogQuery
from datetime import datetime, timedelta

query = LogQuery("logs") # 指定日志目录

# 查询过去一小时内 'AuthService' 模块的 ERROR 日志
results = query.search(
    start_time=datetime.now() - timedelta(hours=1),
    level="ERROR",
    module="AuthService"
)

for record in results:
    print(record)
```

### 日志统计与聚合 (`LogAnalytics`)

用于计算统计数据和检测异常。

```python
from src.utils.log_analysis import LogAnalytics

analytics = LogAnalytics(query)

# 获取按天分组的错误数量
error_dist = analytics.get_error_distribution(group_by='day')
print(error_dist)

# 检测响应时间的异常
anomalies = analytics.detect_anomalies(metric='response_time')
print(anomalies)
```

### 日志可视化 (`LogChartGenerator`, `SystemHealthDashboard`)

生成图表和仪表板。

```python
from src.utils.log_visualization import LogChartGenerator, SystemHealthDashboard

# 生成错误率图表
chart_gen = LogChartGenerator(query)
chart_path = chart_gen.error_rate_chart(output_path="reports/error_rate.png")
print(f"错误率图表已保存到: {chart_path}")

# 生成系统健康仪表板
dashboard_gen = SystemHealthDashboard("logs")
dashboard_paths = dashboard_gen.generate_dashboard(output_dir="reports/dashboard")
print(f"仪表板已生成在: {dashboard_paths['dashboard']}")
```

### 日志质量评估 (`LogQualityAnalyzer`)

评估代码库中的日志记录实践。

```bash
# 从命令行运行
python src/utils/log_quality.py --path ./src --report reports/log_quality_report.txt
```

### 日志审计 (`LogAuditor`, `LogVerifier`)

用于比较迁移前后的日志输出，确保一致性（主要用于迁移阶段）。

## 6. 最佳实践与规范

请参考 `docs/logging_system/logging_standards.md` 获取详细规范。

### 何时记录日志

-   关键业务流程的开始和结束。
-   外部系统交互（API 调用、数据库操作）。
-   重要的状态变更。
-   错误和异常发生时。
-   用户认证、授权等安全相关事件。
-   定时任务的执行。
-   需要调试的复杂逻辑。

### 写什么日志

-   清晰、简洁地描述事件。
-   包含关键的上下文信息（ID、参数、状态）。
-   避免记录敏感信息（密码、密钥、个人身份信息），或进行脱敏处理。
-   对于错误，包含足够的信息以供诊断（错误码、堆栈跟踪、相关参数）。

### 日志级别选择

-   **DEBUG:** 开发时用于追踪代码执行细节。
-   **INFO:** 重要的业务流程节点、配置信息、系统启动/关闭。
-   **WARNING:** 非预期但不影响核心功能的事件、可恢复的错误、即将废弃的特性使用。
-   **ERROR:** 影响功能但系统仍可运行的错误、外部系统错误。
-   **CRITICAL:** 导致系统崩溃或数据损坏的严重错误。

### 上下文的重要性

日志缺乏上下文将难以追踪问题。始终考虑添加以下信息：
-   请求 ID / 事务 ID
-   用户 ID
-   任务/作业 ID
-   相关实体 ID (如订单号、产品 ID)

### 性能考量

-   优先使用异步日志 (`enqueue=True`)。
-   避免在高性能要求的循环中记录日志。
-   使用惰性求值。
-   生产环境避免 DEBUG 级别。
-   参考 `docs/logging_system/performance_optimization.md`。

## 7. 常见问题与故障排查

请参考 `docs/logging_system/troubleshooting.md`。

## 8. 知识资源

-   **本项目文档:**
    -   `docs/logging_system/loguru_usage_guide.md`
    -   `docs/logging_system/logging_standards.md`
    -   `docs/logging_system/troubleshooting.md`
    -   `docs/logging_system/performance_optimization.md`
    -   `docs/logging_system/code_examples.md`
-   **Loguru 官方文档:** [https://loguru.readthedocs.io/](https://loguru.readthedocs.io/)
-   **核心代码:**
    -   `src/utils/log_config.py`
    -   `src/utils/error_handling.py`
    -   (其他相关 `src/utils/log_*.py` 模块)

如有疑问，请咨询项目负责人或负责日志模块的同事。 