# 从标准 logging 迁移到 Loguru 指南

本文档提供了将现有 Python 标准日志系统迁移到 Loguru 的详细指南。迁移过程分为多个阶段，可以逐步进行，最大限度地减少对现有代码的影响。

## 目录

- [迁移前的准备](#迁移前的准备)
- [迁移策略](#迁移策略)
- [迁移工具](#迁移工具)
- [分阶段迁移步骤](#分阶段迁移步骤)
- [常见挑战及解决方案](#常见挑战及解决方案)
- [迁移后验证](#迁移后验证)
- [最佳实践](#最佳实践)

## 迁移前的准备

### 评估现有日志系统

在开始迁移之前，应对现有日志系统进行全面评估：

1. **日志使用情况分析**

   使用 `log_migration_scanner.py` 工具扫描项目代码库：

   ```bash
   python -m src.utils.log_migration_scanner --path /path/to/project
   ```

   此工具将生成报告，展示：
   - 日志调用的分布
   - 使用的日志级别统计
   - 常见的日志模式
   - 潜在的特殊定制部分

2. **确定兼容性要求**

   列出项目中可能需要特殊处理的情况：
   - 自定义日志级别
   - 自定义格式化器
   - 自定义处理器
   - 第三方库集成
   - 特殊日志路由规则

3. **创建基线**

   记录当前日志系统的输出样本，用于迁移后的比较验证：

   ```python
   from src.utils.log_audit import capture_logs
   
   # 捕获现有日志系统的输出
   with capture_logs() as logs:
       # 执行一系列典型操作
       app.process_typical_workflow()
       
   # 保存日志样本
   with open("migration/baseline_logs.txt", "w") as f:
       f.write(logs.get_logging_output())
   ```

### 准备迁移环境

1. **创建测试分支**

   在版本控制系统中创建专门的迁移分支：

   ```bash
   git checkout -b loguru-migration
   ```

2. **设置测试环境**

   准备一个与生产环境隔离的测试环境，用于验证迁移结果。

3. **更新依赖**

   确保所有必要的库都已安装：

   ```bash
   pip install loguru pytest pytest-cov
   ```

## 迁移策略

Loguru 迁移可以采用以下三种策略之一：

### 1. 替换策略

- **适用场景**：项目较小，日志使用简单标准
- **方法**：直接替换标准日志库为Loguru
- **优点**：简单直接，一次性完成迁移
- **缺点**：风险较高，可能导致系统不稳定

### 2. 并行策略（推荐）

- **适用场景**：中大型项目，无法承受停机时间
- **方法**：保持标准日志库，同时使用Loguru记录日志，通过兼容层实现
- **优点**：风险低，可以逐步迁移，便于回滚
- **缺点**：临时维护两套日志系统，略有性能开销

### 3. 模块策略

- **适用场景**：复杂项目，模块间耦合度低
- **方法**：按模块逐个迁移，每个模块完全迁移后再进行下一个
- **优点**：降低复杂度，便于管理迁移进度
- **缺点**：迁移期间系统使用混合日志模式，可能造成不一致

## 迁移工具

项目提供了以下工具协助迁移过程：

### LogMigrationScanner

用于扫描项目中的日志使用情况：

```python
from src.utils.log_migration import LogMigrationScanner

scanner = LogMigrationScanner("/path/to/project")
log_usages = scanner.scan_directory()

print(f"发现 {len(log_usages)} 处日志使用")
for usage in log_usages[:5]:  # 显示前5个示例
    print(f"{usage.file_path}:{usage.line_number} - {usage.log_call}")
```

### LogMigrationPlanner

基于扫描结果生成迁移计划：

```python
from src.utils.log_migration import LogMigrationPlanner

planner = LogMigrationPlanner(log_usages)
plans = planner.create_plan()

print(f"创建了 {len(plans)} 个迁移计划")
print(planner.generate_report())
```

### LogMigrationExecutor

执行迁移计划，自动替换代码中的日志调用：

```python
from src.utils.log_migration import LogMigrationExecutor, execute_batch_migration

# 执行单个文件的迁移
executor = LogMigrationExecutor(plans[0])
success = executor.execute(create_backup=True)

# 批量执行多个文件的迁移
results = execute_batch_migration(plans[:5], batch_size=5, create_backup=True)
print(f"成功: {results['success']}, 失败: {results['failed']}")
```

### DualLogger

提供兼容层，允许同时使用标准日志库和Loguru：

```python
from src.utils.dual_logging import DualLogger

# 创建双重日志记录器
logger = DualLogger("my_module")

# 使用标准日志库语法，同时记录到Loguru
logger.info("这条消息将同时记录到标准日志和Loguru")
logger.error("错误消息", exc_info=True)
```

### LogVerifier

验证迁移后的日志输出与原始输出是否一致：

```python
from src.utils.log_audit import LogVerifier

verifier = LogVerifier(
    original_module="old_module_with_std_logging",
    migrated_module="new_module_with_loguru"
)

# 验证特定函数
result = verifier.verify_function("process_data", test_data)
if result["success"]:
    print("日志输出一致")
else:
    print(f"检测到差异: {result['differences']}")
```

## 分阶段迁移步骤

### 阶段1: 添加兼容层

首先添加 DualLogger 兼容层，允许同时使用标准日志库和Loguru：

1. **集成DualLogger**

   在关键模块中引入DualLogger：

   ```python
   # 修改前
   import logging
   logger = logging.getLogger(__name__)
   
   # 修改后
   from src.utils.dual_logging import DualLogger
   logger = DualLogger(__name__)
   ```

2. **配置DualLogger**

   确保DualLogger正确配置，使其输出与原始日志系统一致：

   ```python
   from src.utils.dual_logging import setup_dual_logging
   
   setup_dual_logging(
       log_file="app.log",
       log_level="INFO",
       format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
       loguru_format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}"
   )
   ```

3. **测试兼容层**

   验证日志输出在两个系统中都能正常工作。

### 阶段2: 分批迁移

使用迁移工具分批处理模块：

1. **扫描日志使用情况**

   ```python
   from src.utils.log_migration import scan_and_plan
   
   log_usages, plans, report = scan_and_plan("/path/to/project")
   print(report)
   ```

2. **按优先级执行迁移**

   从低风险模块开始，逐步迁移到核心模块：

   ```python
   from src.utils.log_migration import execute_batch_migration
   
   # 按优先级排序
   priority_1_plans = [p for p in plans if p.priority == 1]
   results = execute_batch_migration(priority_1_plans, batch_size=5)
   
   print(f"迁移结果: 成功={results['success']}, 失败={results['failed']}")
   ```

3. **持续验证**

   每批迁移后运行测试，确保系统正常工作。

### 阶段3: 过渡到纯Loguru

当所有模块都支持DualLogger后，可以开始移除对标准日志库的依赖：

1. **配置纯Loguru环境**

   ```python
   from src.utils.log_config import LogConfig
   
   # 使用Loguru原生配置
   log_config = LogConfig({
       "LOG_LEVEL": "INFO",
       "LOG_PATH": "logs",
       "JSON_LOGS": True
   })
   ```

2. **迁移DualLogger到直接使用Loguru**

   ```python
   # 修改前
   from src.utils.dual_logging import DualLogger
   logger = DualLogger(__name__)
   
   # 修改后
   from src.utils.log_config import get_logger
   logger = get_logger(__name__)
   ```

3. **移除双重记录**

   逐步停用DualLogger的标准日志部分。

### 阶段4: 清理和优化

完成基本迁移后，进行清理和优化：

1. **移除兼容代码**

   删除不再需要的兼容层和临时代码。

2. **应用Loguru最佳实践**

   重构日志代码，利用Loguru的高级功能：

   ```python
   # 使用上下文管理
   from src.utils.log_config import LogContext
   
   with LogContext(request_id="req123", user_id="user456"):
       logger.info("处理用户请求")
       
   # 使用结构化日志
   logger.info("订单已处理", extra={
       "order_id": order.id,
       "total": order.total,
       "items": len(order.items)
   })
   ```

3. **优化日志性能**

   使用异步日志记录、采样和其他性能优化技术。

## 常见挑战及解决方案

### 第三方库集成

**问题**: 第三方库使用标准日志库，与Loguru整合困难。

**解决方案**: 使用日志拦截器捕获第三方库日志：

```python
import logging
from loguru import logger

# 拦截标准库日志
class InterceptHandler(logging.Handler):
    def emit(self, record):
        level = logger.level(record.levelname).name
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

# 应用拦截器
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
```

### 自定义日志级别

**问题**: 项目使用自定义日志级别，需要在Loguru中保持一致。

**解决方案**: 在Loguru中添加相同的自定义级别：

```python
from loguru import logger

# 添加与标准库相同的自定义级别
logger.level("AUDIT", no=25, color="<cyan>")
logger.level("METRIC", no=15, color="<light-blue>")

# 在DualLogger中注册级别映射
from src.utils.dual_logging import register_level_mapping

register_level_mapping({
    25: "AUDIT",
    15: "METRIC"
})
```

### 格式兼容性

**问题**: 日志格式字符串语法在标准库和Loguru中不同。

**解决方案**: 使用格式转换器：

```python
def convert_format(logging_format):
    """将标准日志格式转换为Loguru格式"""
    # 基本转换
    replacements = {
        '%(asctime)s': '{time:YYYY-MM-DD HH:mm:ss}',
        '%(name)s': '{name}',
        '%(levelname)s': '{level}',
        '%(message)s': '{message}',
        '%(filename)s': '{file.name}',
        '%(lineno)d': '{line}',
        '%(funcName)s': '{function}',
        '%(process)d': '{process}',
        '%(thread)d': '{thread}'
    }
    
    result = logging_format
    for old, new in replacements.items():
        result = result.replace(old, new)
        
    return result
```

### 性能影响

**问题**: 双重日志记录可能影响性能。

**解决方案**: 使用异步记录和适当的缓冲：

```python
from loguru import logger

# 配置异步日志记录
logger.add("app.log", enqueue=True, backtrace=True, diagnose=True)
```

## 迁移后验证

完成迁移后，使用以下方法验证结果：

### 日志输出比较

使用LogVerifier比较迁移前后的日志输出：

```python
from src.utils.log_audit import LogVerifier

verifier = LogVerifier(
    original_module="original",
    migrated_module="migrated"
)

# 生成验证报告
report = verifier.generate_report()
print(report)
```

### 运行自动化测试

执行包含日志断言的测试套件，确保日志行为一致：

```python
import pytest
from src.utils.log_audit import LogCapture

def test_logging_behavior():
    with LogCapture() as logs:
        # 执行被测试的操作
        app.process_something()
        
        # 验证日志内容
        output = logs.get_loguru_output()
        assert "预期的日志消息" in output
        assert "错误消息" in output
```

### 性能基准测试

比较迁移前后的日志性能：

```python
import timeit

def benchmark_logging(logger_type, iterations=1000):
    setup = f"""
from {logger_type} import logger
data = {{'key1': 'value1', 'key2': 'value2'}}
    """
    
    stmt = """
for i in range(100):
    logger.info(f"Test message {i}")
    logger.debug(f"Debug with data: {data}")
    """
    
    return timeit.timeit(stmt, setup, number=iterations)

std_time = benchmark_logging("logging")
loguru_time = benchmark_logging("loguru")

print(f"标准日志: {std_time:.4f}秒")
print(f"Loguru: {loguru_time:.4f}秒")
print(f"性能变化: {((loguru_time - std_time) / std_time) * 100:.2f}%")
```

## 最佳实践

### 渐进式迁移

- 从低风险模块开始迁移
- 在每个阶段都进行测试和验证
- 保持备份和回滚方案

### 代码规范

- 采用一致的日志记录风格
- 使用结构化日志而非字符串拼接
- 为每个模块使用有意义的记录器名称

### 集成与部署

- 在部署前彻底测试新日志系统
- 监控日志系统性能和存储使用情况
- 提供详细的迁移文档给团队成员

### 培训

- 为团队提供Loguru使用培训
- 创建示例和最佳实践文档
- 定期审查日志质量

## 迁移后下一步

成功迁移后，考虑以下增强：

1. **利用Loguru高级功能**
   - 上下文管理
   - 异步日志记录
   - 结构化JSON日志
   - 自定义过滤器

2. **改进可观测性**
   - 集成日志分析工具
   - 建立日志可视化仪表板
   - 实现智能告警

3. **优化日志策略**
   - 细化日志级别使用
   - 改进日志轮转和保留策略
   - 实现日志采样以减少容量 