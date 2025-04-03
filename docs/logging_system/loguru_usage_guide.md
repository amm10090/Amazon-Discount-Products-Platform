# Loguru 日志系统使用指南

## 目录

- [简介](#简介)
- [安装与配置](#安装与配置)
- [基础用法](#基础用法)
- [高级功能](#高级功能)
  - [上下文管理](#上下文管理)
  - [错误处理](#错误处理)
  - [API日志记录](#API日志记录)
  - [日志分析](#日志分析)
- [最佳实践](#最佳实践)
- [常见问题](#常见问题)
- [迁移指南](#迁移指南)

## 简介

本项目使用 Loguru 作为主要的日志记录解决方案，提供了丰富的日志记录、分析和可视化功能。相对于 Python 标准库中的 `logging` 模块，Loguru 提供了更简单的配置、更丰富的功能和更漂亮的日志输出。

### 主要特点

- 简单直观的 API
- 自动异常捕获和格式化
- 精美的彩色终端输出
- 结构化 JSON 日志输出
- 高级上下文管理
- 强大的日志分析功能
- 完整的可观测性解决方案

## 安装与配置

### 依赖安装

Loguru 已经包含在项目的 `requirements.txt` 中，确保通过以下命令安装：

```bash
pip install -r requirements.txt
```

### 基本配置

项目中的 Loguru 配置通过 `src/utils/log_config.py` 模块进行管理。默认配置提供：

- 控制台彩色输出
- 文件日志记录（轮转和压缩）
- 错误日志单独存储
- 可选的 JSON 格式输出

示例配置：

```python
from src.utils.log_config import LogConfig

# 使用默认配置
config = LogConfig()

# 使用自定义配置
custom_config = LogConfig({
    "LOG_LEVEL": "DEBUG",
    "JSON_LOGS": True,
    "LOG_PATH": "custom_logs",
    "MAX_LOG_SIZE": "50 MB",
    "LOG_RETENTION": "7 days"
})
```

### 日志级别

系统支持以下日志级别，按严重程度递增：

- `DEBUG`：详细的调试信息
- `INFO`：常规信息
- `WARNING`：警告但不影响程序运行
- `ERROR`：错误导致特定操作失败
- `CRITICAL`：严重错误可能导致程序崩溃

动态修改日志级别：

```python
from src.utils.log_config import LogConfig

LogConfig.set_log_level("DEBUG")  # 设置全局日志级别
```

## 基础用法

### 获取 Logger

使用 `get_logger` 函数获取带有上下文的日志记录器：

```python
from src.utils.log_config import get_logger

# 创建带有模块名称的记录器
logger = get_logger("product_service")

# 创建带有更多上下文的记录器
logger = get_logger("auth_service", user_id="12345", session_id="abc123")
```

### 基本日志记录

```python
# 基本日志记录
logger.debug("详细的调试信息")
logger.info("一般操作信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")

# 携带额外信息
logger.info("用户登录成功", extra={"user_id": "12345", "ip": "192.168.1.1"})

# 异常记录
try:
    1 / 0
except Exception as e:
    logger.exception(f"操作失败: {e}")  # 自动包含异常堆栈
```

### 装饰器用法

使用日志装饰器自动记录函数调用：

```python
from src.utils.log_config import log_function_call

@log_function_call
def process_order(order_id, items):
    # 函数逻辑...
    return result
```

## 高级功能

### 上下文管理

使用日志上下文管理器跟踪相关操作：

```python
from src.utils.log_config import LogContext

# 同步上下文
with LogContext(task_id="123", user_id="456"):
    logger.info("开始处理任务")
    # 操作代码...
    logger.info("任务处理完成")

# 异步上下文
async with LogContext(request_id="req123", service="payment"):
    logger.info("开始处理支付")
    # 异步操作...
    logger.info("支付处理完成")
```

### 性能跟踪

```python
from src.utils.log_config import track_performance

# 使用装饰器自动追踪函数执行时间
@track_performance
def expensive_operation():
    # 耗时操作...
    pass

# 使用上下文管理器追踪代码块执行时间
with LogContext(track_performance=True):
    # 耗时操作...
    pass
```

## 即将添加的文档内容

本文档仍在完善中，即将添加的内容包括：

- 错误处理详解
- API日志记录指南
- 日志分析和可视化功能
- 最佳实践和代码示例
- 常见问题解答
- 从标准 logging 迁移指南

敬请期待！ 