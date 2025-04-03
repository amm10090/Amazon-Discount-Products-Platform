# 日志系统故障排查指南

本文档提供了项目中日志系统可能遇到的常见问题以及相应的排查和解决方法。当日志系统出现问题时，可参考本指南进行诊断和修复。

## 目录

- [常见问题](#常见问题)
  - [日志未生成](#日志未生成)
  - [日志级别问题](#日志级别问题)
  - [日志格式不正确](#日志格式不正确)
  - [性能问题](#性能问题)
  - [文件权限问题](#文件权限问题)
- [日志分析工具使用问题](#日志分析工具使用问题)
- [日志迁移问题](#日志迁移问题)
- [上下文管理问题](#上下文管理问题)
- [进阶诊断技巧](#进阶诊断技巧)

## 常见问题

### 日志未生成

#### 症状

- 找不到日志文件
- 日志文件存在但内容为空
- 预期的日志记录没有出现

#### 排查步骤

1. **检查配置**

   确认 LogConfig 配置正确且已初始化：

   ```python
   from src.utils.log_config import LogConfig
   
   # 检查是否有自定义配置覆盖了默认配置
   print(LogConfig().config)
   ```

2. **检查日志路径**

   确认日志目录存在且具有适当的写入权限：

   ```python
   import os
   from src.utils.log_config import LogConfig
   
   log_path = LogConfig().config["LOG_PATH"]
   print(f"日志路径: {log_path}")
   print(f"路径存在: {os.path.exists(log_path)}")
   print(f"可写入: {os.access(log_path, os.W_OK)}")
   ```

3. **检查日志级别**

   确认日志级别允许记录相应的消息：

   ```python
   from src.utils.log_config import LogConfig
   
   print(f"当前日志级别: {LogConfig().config['LOG_LEVEL']}")
   ```

4. **添加临时监控**

   在关键位置添加直接输出，确认代码执行到日志记录点：

   ```python
   print(f"DEBUG: 即将记录日志，数据: {data}")
   logger.info("处理数据完成")
   print(f"DEBUG: 日志已记录")
   ```

#### 解决方案

- 确保日志目录存在且具有正确的权限
- 降低日志级别（例如，将 INFO 改为 DEBUG）以查看更多信息
- 验证日志配置是否在应用程序启动时正确初始化
- 检查是否有环境变量覆盖了日志配置

### 日志级别问题

#### 症状

- 某些日志消息未记录
- 记录了过多不必要的日志
- 不同环境的日志级别不一致

#### 排查步骤

1. **检查当前日志级别**

   ```python
   from src.utils.log_config import log, LogConfig
   
   # 检查全局日志级别
   print(f"当前配置的日志级别: {LogConfig().config['LOG_LEVEL']}")
   
   # 检查特定logger的级别
   print(f"logger实际级别: {log.level}")
   ```

2. **验证环境变量**

   检查是否有环境变量设置了日志级别：

   ```bash
   echo $LOG_LEVEL  # 在Linux/Mac终端
   echo %LOG_LEVEL%  # 在Windows命令提示符
   ```

3. **检查模块特定级别**

   确认是否对特定模块设置了不同的日志级别：

   ```python
   # 列出所有logger及其级别
   from loguru import logger
   
   for handler in logger._core.handlers.values():
       print(f"Handler: {handler}")
       print(f"Level: {handler._level}")
       if handler._filter:
           print(f"Filter: {handler._filter}")
   ```

#### 解决方案

- 明确设置适当的日志级别：

  ```python
  from src.utils.log_config import LogConfig
  
  # 全局设置
  LogConfig.set_log_level("DEBUG")  # 或 INFO, WARNING, ERROR, CRITICAL
  ```

- 对特定模块设置不同级别：

  ```python
  from loguru import logger
  import sys
  
  # 为auth模块设置DEBUG级别，其他保持INFO
  logger.remove()  # 移除现有处理器
  logger.add(sys.stderr, level="INFO")  # 基础级别
  logger.add(sys.stderr, level="DEBUG", filter=lambda record: "auth" in record["name"])
  ```

- 检查并统一环境变量设置

### 日志格式不正确

#### 症状

- 日志消息格式混乱
- 时间戳格式不一致
- 结构化数据未正确记录

#### 排查步骤

1. **检查日志格式配置**

   ```python
   from src.utils.log_config import LogConfig
   
   # 打印控制台和文件日志格式
   print(f"控制台格式: {LogConfig().config['CONSOLE_LOG_FORMAT']}")
   print(f"文件格式: {LogConfig().config['FILE_LOG_FORMAT']}")
   ```

2. **检查日志调用**

   确认日志调用语法正确：

   ```python
   # 正确的Loguru语法
   logger.info("处理 {name} 完成", name="任务1")
   
   # 不正确的混合语法
   logger.info("处理 {} 完成".format("任务1"))  # 不推荐
   logger.info("处理 %s 完成" % "任务1")  # 不推荐
   ```

3. **验证结构化数据**

   确认结构化数据格式正确：

   ```python
   # 正确用法
   logger.info("用户登录", extra={"user_id": 123, "ip": "192.168.1.1"})
   
   # 不正确用法
   logger.info("用户登录 {extra}", extra={"user_id": 123})  # 错误，extra是关键字参数
   ```

#### 解决方案

- 统一使用Loguru的格式化语法
- 更新日志格式模板
- 确保结构化数据正确传递
- 检查自定义日志处理器是否正确处理格式

### 性能问题

#### 症状

- 应用程序在日志密集操作时速度变慢
- 日志文件迅速增长
- 内存使用率增加

#### 排查步骤

1. **检查日志调用频率**

   确认循环或高频代码中的日志调用：

   ```python
   # 性能分析示例
   import cProfile
   
   def profile_logging():
       for i in range(10000):
           logger.debug(f"处理项 {i}")
   
   cProfile.run('profile_logging()')
   ```

2. **检查日志内容大小**

   ```python
   import sys
   
   # 估算日志消息大小
   data = {"large_field": "x" * 10000}
   msg = f"处理数据: {data}"
   print(f"日志消息占用内存: {sys.getsizeof(msg)} 字节")
   ```

3. **检查IO操作**

   确认是否频繁刷新日志文件：

   ```python
   from src.utils.log_config import LogConfig
   
   # 检查是否启用了自动刷新
   handlers = LogConfig._handler_ids
   print(f"handlers: {handlers}")
   ```

#### 解决方案

- 减少循环中的日志调用
- 使用批量日志或汇总日志
- 使用日志采样（只记录部分事件）
- 增加日志缓冲区大小
- 调整日志级别，减少记录的信息量
- 使用异步日志记录

  ```python
  from loguru import logger
  
  # 配置异步日志
  logger.add("app.log", enqueue=True)  # 使用队列实现异步记录
  ```

### 文件权限问题

#### 症状

- 日志文件创建失败
- 权限错误
- 在某些环境中工作但在其他环境中不工作

#### 排查步骤

1. **检查当前权限**

   ```bash
   # Linux/Mac
   ls -la /path/to/logs/
   
   # 检查进程用户
   ps aux | grep python
   ```

2. **测试文件创建**

   ```python
   import os
   
   log_dir = "/path/to/logs"
   test_file = os.path.join(log_dir, "test_write.tmp")
   
   try:
       with open(test_file, 'w') as f:
           f.write("测试写入权限")
       print(f"文件写入成功: {test_file}")
       os.remove(test_file)
   except Exception as e:
       print(f"文件写入失败: {e}")
   ```

#### 解决方案

- 更改日志目录权限：`chmod 755 /path/to/logs`
- 将日志目录更改为应用程序可写的位置
- 使用相对路径而非绝对路径
- 在应用程序启动时创建日志目录：

  ```python
  import os
  
  log_dir = "logs"
  os.makedirs(log_dir, exist_ok=True)
  ```

## 日志分析工具使用问题

### 查询返回空结果

#### 症状

- LogQuery.search() 返回空列表
- 图表生成未显示数据

#### 排查步骤

1. **检查日志文件存在性**

   ```python
   from src.utils.log_analysis import LogQuery
   import os
   
   query = LogQuery("logs")
   log_files = [f for f in os.listdir("logs") if f.endswith(".log")]
   print(f"日志文件: {log_files}")
   ```

2. **检查过滤条件**

   ```python
   from datetime import datetime, timedelta
   
   # 测试不带过滤器的搜索
   results = query.search(limit=5)
   print(f"无过滤搜索结果: {len(results)}")
   
   # 逐步添加过滤器
   start_time = datetime.now() - timedelta(days=7)
   results = query.search(start_time=start_time, limit=5)
   print(f"带时间过滤搜索结果: {len(results)}")
   ```

3. **检查日志格式**

   确保日志文件格式与解析逻辑匹配：

   ```python
   # 读取日志样本
   with open("logs/app.log", "r") as f:
       sample = f.readline()
   print(f"日志样本: {sample}")
   
   # 测试解析
   record = query._parse_log_record(sample)
   print(f"解析结果: {record}")
   ```

#### 解决方案

- 调整查询参数，使用更宽松的过滤条件
- 确认日志文件的格式与解析器兼容
- 验证日期时间格式和时区设置
- 更新日志解析逻辑以匹配实际日志格式

### 图表生成失败

#### 症状

- 生成图表时出现错误
- 生成的图表为空或显示不正确

#### 排查步骤

1. **检查依赖项**

   确认所有必要的库已安装：

   ```bash
   pip install matplotlib pandas numpy
   ```

2. **验证数据源**

   ```python
   from src.utils.log_analysis import LogQuery
   from src.utils.log_visualization import LogChartGenerator
   
   query = LogQuery("logs")
   chart_gen = LogChartGenerator(query)
   
   # 获取错误分布数据
   from datetime import datetime, timedelta
   
   start_time = datetime.now() - timedelta(days=7)
   err_dist = chart_gen._get_error_distribution_data(start_time=start_time)
   print(f"错误分布数据: {err_dist}")
   ```

3. **检查路径和权限**

   ```python
   import os
   
   output_dir = "reports"
   if not os.path.exists(output_dir):
       os.makedirs(output_dir)
   
   test_file = os.path.join(output_dir, "test.png")
   try:
       # 尝试创建简单图表
       import matplotlib.pyplot as plt
       plt.figure()
       plt.plot([1, 2, 3], [1, 2, 3])
       plt.savefig(test_file)
       print(f"测试图表已保存: {test_file}")
   except Exception as e:
       print(f"图表生成失败: {e}")
   ```

#### 解决方案

- 安装或更新必要的依赖库
- 确保有足够的数据用于生成图表
- 检查输出目录是否存在且具有写入权限
- 使用绝对路径而非相对路径
- 在服务器环境中，使用非交互式后端：

  ```python
  import matplotlib
  matplotlib.use('Agg')  # 使用非交互式后端
  ```

## 日志迁移问题

### 双重日志记录问题

#### 症状

- 同一消息出现两次或多次
- 日志格式不一致
- 丢失部分日志消息

#### 排查步骤

1. **检查双重记录器配置**

   ```python
   from src.utils.dual_logging import DualLogger
   
   # 创建测试日志记录器
   test_logger = DualLogger("test_module")
   print(f"DualLogger配置: {test_logger.__dict__}")
   ```

2. **验证输出捕获**

   ```python
   import io
   import sys
   from contextlib import redirect_stdout, redirect_stderr
   
   # 捕获标准输出和标准错误
   stdout = io.StringIO()
   stderr = io.StringIO()
   
   with redirect_stdout(stdout), redirect_stderr(stderr):
       test_logger.info("测试消息")
       
   print(f"标准输出: {stdout.getvalue()}")
   print(f"标准错误: {stderr.getvalue()}")
   ```

3. **检查日志处理器**

   ```python
   import logging
   
   # 检查标准logging配置
   root_logger = logging.getLogger()
   print(f"根日志记录器级别: {root_logger.level}")
   print(f"根日志记录器处理器: {root_logger.handlers}")
   
   # 检查Loguru处理器
   from loguru import logger
   print(f"Loguru处理器: {logger._core.handlers}")
   ```

#### 解决方案

- 确保标准logging和Loguru不会同时输出到同一目标
- 检查全局日志配置是否在多处初始化
- 在迁移期间暂时关闭一个日志系统的特定处理器
- 使用消息ID或格式区分来自不同系统的日志

### 自定义日志级别兼容性

#### 症状

- 自定义日志级别未正确转换
- 出现"级别不存在"的错误
- 日志级别不匹配

#### 排查步骤

1. **检查级别映射**

   ```python
   from src.utils.dual_logging import DualLogger
   
   # 打印级别映射
   test_logger = DualLogger("test_module")
   print(f"日志级别映射: {test_logger._level_mapping}")
   ```

2. **测试自定义级别**

   ```python
   import logging
   
   # 创建自定义级别
   CUSTOM_LEVEL = 25
   logging.addLevelName(CUSTOM_LEVEL, "CUSTOM")
   
   # 测试双重记录器
   from src.utils.dual_logging import DualLogger
   
   test_logger = DualLogger("test_module")
   try:
       test_logger.log(CUSTOM_LEVEL, "自定义级别测试消息")
       print("自定义级别记录成功")
   except Exception as e:
       print(f"自定义级别记录失败: {e}")
   ```

#### 解决方案

- 确保自定义级别在两个系统中都定义
- 实现更灵活的级别映射机制
- 为Loguru添加自定义级别：

  ```python
  from loguru import logger
  
  # 添加自定义级别
  logger.level("CUSTOM", no=25, color="<magenta>")
  ```

## 上下文管理问题

### 上下文数据丢失

#### 症状

- 日志记录中缺少预期的上下文数据
- 嵌套上下文未正确合并
- 异步代码中上下文未传递

#### 排查步骤

1. **检查上下文栈**

   ```python
   from src.utils.log_config import _context_stack, LogContext, get_current_context
   
   # 检查初始上下文
   print(f"初始上下文: {get_current_context()}")
   
   # 嵌套上下文测试
   with LogContext(level_1="value1"):
       print(f"级别1上下文: {get_current_context()}")
       with LogContext(level_2="value2"):
           print(f"级别2上下文: {get_current_context()}")
       print(f"返回级别1上下文: {get_current_context()}")
   
   print(f"退出所有上下文: {get_current_context()}")
   ```

2. **检查异步上下文**

   ```python
   import asyncio
   
   async def test_async_context():
       print(f"异步前上下文: {get_current_context()}")
       async with LogContext(async_key="async_value"):
           print(f"异步中上下文: {get_current_context()}")
       print(f"异步后上下文: {get_current_context()}")
   
   # 运行测试
   asyncio.run(test_async_context())
   ```

3. **检查上下文变量实现**

   ```python
   # 检查上下文变量实现
   import inspect
   
   print(inspect.getsource(_context_stack))
   ```

#### 解决方案

- 确保所有上下文管理器正确实现`__enter__`和`__exit__`方法
- 在异步代码中使用`__aenter__`和`__aexit__`
- 实现上下文复制而非引用共享
- 使用`contextvars`确保异步代码的上下文隔离
- 在任务创建时绑定上下文：

  ```python
  from src.utils.log_config import bind_context
  
  async def main():
      task = asyncio.create_task(some_coroutine())
      await bind_context(task, task_id="123")
  ```

## 进阶诊断技巧

### 启用调试日志

要调试日志系统本身，可以启用Loguru的内部调试日志：

```python
import os
os.environ["LOGURU_DEBUG"] = "1"

from loguru import logger
# 现在将看到Loguru的内部调试信息
```

### 创建最小复现示例

当遇到复杂问题时，创建最小复现示例有助于隔离问题：

```python
# minimal_test.py
from loguru import logger
import sys

# 最小配置
logger.remove()
logger.add(sys.stderr, level="DEBUG")
logger.add("test.log", level="INFO")

# 测试用例
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")

try:
    1/0
except Exception:
    logger.exception("Exception occurred")
```

### 编写专用诊断工具

为持续监控和问题诊断创建专用工具：

```python
# log_diagnostics.py
import os
import sys
import logging
from loguru import logger

def diagnose_logging_system():
    """诊断日志系统状态并输出报告"""
    report = []
    
    # 检查环境变量
    report.append("=== 环境变量 ===")
    for var in ['LOG_LEVEL', 'LOGURU_DEBUG', 'LOGURU_FORMAT']:
        report.append(f"{var}: {os.environ.get(var, '未设置')}")
    
    # 检查Python logging
    report.append("\n=== Python logging ===")
    root = logging.getLogger()
    report.append(f"Root logger level: {logging.getLevelName(root.level)}")
    report.append(f"Handlers: {len(root.handlers)}")
    for i, h in enumerate(root.handlers):
        report.append(f"  Handler {i}: {h.__class__.__name__}, "
                     f"level={logging.getLevelName(h.level)}")
    
    # 检查Loguru
    report.append("\n=== Loguru ===")
    handlers = logger._core.handlers
    report.append(f"Handlers: {len(handlers)}")
    for id, h in handlers.items():
        report.append(f"  Handler {id}: level={h._level}, "
                     f"formatter={h._format}, "
                     f"path={getattr(h._sink, 'path', 'N/A')}")
    
    # 检查文件系统
    report.append("\n=== 文件系统 ===")
    log_path = "logs"  # 使用实际的日志路径
    if os.path.exists(log_path):
        report.append(f"日志目录: {os.path.abspath(log_path)}")
        report.append(f"权限: {oct(os.stat(log_path).st_mode)[-3:]}")
        files = os.listdir(log_path)
        report.append(f"文件数: {len(files)}")
        for i, f in enumerate(files[:5]):  # 只显示前5个
            full_path = os.path.join(log_path, f)
            size = os.path.getsize(full_path)
            report.append(f"  {i}: {f}, 大小={size}字节")
        if len(files) > 5:
            report.append(f"  ... 还有 {len(files)-5} 个文件")
    else:
        report.append(f"日志目录不存在: {log_path}")
    
    return "\n".join(report)

if __name__ == "__main__":
    print(diagnose_logging_system())
```

### 检查线程安全问题

当在多线程环境中使用日志时，添加线程诊断：

```python
import threading
import time
from loguru import logger

def test_thread_safety():
    """测试多线程环境下的日志记录"""
    def worker(name):
        logger.info(f"线程 {name} 开始")
        for i in range(5):
            logger.debug(f"线程 {name}: 步骤 {i}")
            time.sleep(0.1)
        logger.info(f"线程 {name} 结束")
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(f"worker-{i}",))
        threads.append(t)
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    logger.info("所有线程已完成")

test_thread_safety()
``` 