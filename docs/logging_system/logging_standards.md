# 日志记录标准和规范

本文档定义了项目中日志记录的标准和规范，旨在确保团队成员以一致的方式使用日志系统，便于日志的查看、搜索和分析。所有开发人员在开发过程中都应遵循这些标准。

## 目录

- [日志级别使用标准](#日志级别使用标准)
- [日志内容格式规范](#日志内容格式规范)
- [上下文信息规范](#上下文信息规范)
- [结构化日志规范](#结构化日志规范)
- [性能考虑](#性能考虑)
- [错误和异常记录](#错误和异常记录)
- [敏感信息处理](#敏感信息处理)
- [代码评审检查项](#代码评审检查项)

## 日志级别使用标准

正确使用日志级别对于信息分类和过滤至关重要。在本项目中，各级别的具体使用标准如下：

### DEBUG

- **用途**：详细的开发和调试信息，仅在开发环境中使用
- **示例场景**：
  - 函数的输入参数和返回值
  - 循环中的中间状态
  - 条件分支的执行路径
  - 数据库查询和结果（不含敏感数据）
  - 第三方API调用的详细参数

```python
logger.debug("处理商品批次，总数: {count}", count=len(products))
logger.debug("数据库查询参数: {params}", params=query_params)
```

### INFO

- **用途**：记录系统正常运行的重要事件和状态变化
- **示例场景**：
  - 应用启动和关闭
  - 用户登录和登出
  - 完成重要操作（商品添加、更新、订单创建等）
  - 计划任务的开始和完成
  - 系统配置变更

```python
logger.info("应用启动完成，版本: {version}", version=APP_VERSION)
logger.info("用户 {user_id} 已登录系统", user_id=user.id)
logger.info("成功处理批次任务，处理项: {processed}，跳过项: {skipped}", processed=success_count, skipped=skip_count)
```

### WARNING

- **用途**：潜在问题或需要注意但不会导致功能失败的情况
- **示例场景**：
  - 使用了已废弃的功能
  - 超出预期但仍在可接受范围的性能问题
  - 重试操作（如网络请求）
  - 配置不理想但可以使用默认值继续
  - 非关键特性的降级

```python
logger.warning("API响应时间超出阈值: {time}ms，阈值: {threshold}ms", time=response_time, threshold=THRESHOLD)
logger.warning("使用已废弃的配置项 '{config_key}'，将在 v2.0 中移除", config_key=key)
logger.warning("第 {attempt} 次重试 API 请求", attempt=retry_count)
```

### ERROR

- **用途**：导致操作失败或功能无法正常工作的错误
- **示例场景**：
  - 数据库连接失败
  - API调用返回错误
  - 输入验证失败
  - 业务规则验证失败
  - 文件操作失败

```python
logger.error("无法连接到数据库: {error}", error=str(e))
logger.error("处理商品 {product_id} 失败: {reason}", product_id=product.id, reason=failure_reason)
logger.exception("上传文件时发生错误")  # 包含异常堆栈
```

### CRITICAL

- **用途**：系统级灾难性错误，影响整个应用或核心功能的可用性
- **示例场景**：
  - 应用无法启动
  - 关键服务不可用
  - 数据损坏或一致性问题
  - 安全事件或入侵检测

```python
logger.critical("核心服务无法启动: {details}", details=failure_details)
logger.critical("检测到数据不一致: {table} 表中的 {records} 条记录受影响", table=table_name, records=affected_count)
```

## 日志内容格式规范

### 基本原则

1. **清晰简洁**：日志消息应清晰简洁，直接说明发生了什么
2. **包含足够上下文**：确保包含识别问题所需的所有相关信息
3. **避免多余信息**：不要记录无用或重复的信息
4. **使用模板字符串**：使用命名参数而非字符串连接

### 日志消息格式

- 以动词开头，说明发生了什么事情
- 使用明确的术语，避免模糊的描述
- 包含相关的标识符（ID、名称等）
- 区分相似操作（例如，读取vs写入，添加vs更新）

#### 推荐格式

```python
# 良好实践 - 清晰、带上下文的模板格式
logger.info("更新商品 {product_id} 价格从 {old_price} 到 {new_price}", 
           product_id=product.id, old_price=old_price, new_price=new_price)

# 良好实践 - 错误信息包含原因和影响
logger.error("保存订单 {order_id} 失败: {reason}，客户将收到通知", 
            order_id=order.id, reason=str(e))
```

#### 不推荐格式

```python
# 不推荐 - 缺乏上下文
logger.info("商品更新完成")

# 不推荐 - 使用字符串连接
logger.info("更新商品 " + str(product.id) + " 价格从 " + str(old_price) + " 到 " + str(new_price))

# 不推荐 - 混合使用格式化方法
logger.error("保存订单 {} 失败: %s".format(order.id) % str(e))
```

## 上下文信息规范

### 全局上下文

应用程序启动时应设置以下全局上下文信息：

- 应用名称和版本
- 环境（开发、测试、生产）
- 部署标识符或实例ID
- 主机名和IP地址

```python
from src.utils.log_config import LogContext

# 应用启动时
with LogContext(
    app_name="discount_products_platform",
    app_version="1.2.3",
    environment="production",
    instance_id="web-01",
    hostname=socket.gethostname()
):
    # 应用程序代码...
```

### 请求上下文

处理HTTP请求时应包含以下上下文信息：

- 请求ID（唯一标识符）
- 用户ID（如已认证）
- 客户端IP地址
- 请求方法和路径
- 用户代理（浏览器信息）

```python
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    user_id = get_user_id_from_request(request)
    
    async with LogContext(
        request_id=request_id,
        user_id=user_id,
        client_ip=request.client.host,
        method=request.method,
        path=request.url.path,
        user_agent=request.headers.get("user-agent", "")
    ):
        # 处理请求...
        response = await call_next(request)
        return response
```

### 任务上下文

处理后台任务或计划任务时应包含以下上下文信息：

- 任务ID
- 任务类型
- 队列名称
- 计划执行时间
- 优先级（如适用）

```python
def process_scheduled_task(task_data):
    with LogContext(
        task_id=task_data["id"],
        task_type=task_data["type"],
        queue=task_data["queue"],
        scheduled_time=task_data["scheduled_at"],
        priority=task_data.get("priority", "normal")
    ):
        # 任务处理逻辑...
```

## 结构化日志规范

### 基本字段

所有结构化日志记录应包含以下基本字段：

- `timestamp`：事件发生时间（ISO 8601格式）
- `level`：日志级别
- `message`：人类可读的日志消息
- `module`：生成日志的模块或类
- `function`：生成日志的函数或方法
- `line`：生成日志的代码行号
- `context`：上下文信息（通过LogContext提供）

### 事件特定字段

根据不同类型的事件，应包含以下特定字段：

#### 用户相关事件

- `user_id`：用户标识符
- `username`：用户名（如可用）
- `action`：执行的操作（login, logout, update等）
- `result`：操作结果（success, failure）

#### 性能相关事件

- `duration_ms`：操作持续时间（毫秒）
- `resource_type`：资源类型（database, api, cache等）
- `operation`：操作类型（query, insert, update等）
- `resource_name`：资源名称（表名、API端点等）

#### 错误相关事件

- `error_code`：错误代码
- `error_type`：错误类型（ValidationError, DatabaseError等）
- `stack_trace`：异常堆栈（自动由logger.exception提供）
- `affected_component`：受影响的组件

## 性能考虑

### 日志效率

1. **避免昂贵的操作**：不要在日志语句中执行昂贵的计算或函数调用

   ```python
   # 不推荐 - 在日志调用中执行昂贵操作
   logger.debug("用户数据: {data}", data=get_full_user_details(user_id))  # 可能触发数据库查询
   
   # 推荐 - 仅在实际记录日志时才执行操作
   if logger.isEnabledFor(DEBUG):
       user_data = get_full_user_details(user_id)
       logger.debug("用户数据: {data}", data=user_data)
   ```

2. **使用延迟计算**：利用Loguru的延迟计算特性

   ```python
   # Loguru支持延迟计算表达式
   logger.debug("复杂统计数据: {stats}", stats=lambda: calculate_expensive_stats())
   ```

3. **限制日志数量**：避免在高频循环中记录日志

   ```python
   # 不推荐 - 在循环中记录每个项
   for item in large_list:
       logger.debug("处理项: {item}", item=item)
   
   # 推荐 - 仅记录摘要信息
   logger.debug("开始处理 {count} 个项", count=len(large_list))
   # 处理逻辑...
   logger.debug("完成处理 {count} 个项，耗时: {time}秒", count=len(large_list), time=processing_time)
   ```

### 日志级别过滤

1. 确保在生产环境中使用适当的日志级别（通常为INFO或更高）
2. 开发环境可以使用DEBUG级别以获取更详细的信息
3. 可以为特定模块设置不同的日志级别

```python
from src.utils.log_config import LogConfig

# 为所有模块设置基础级别
LogConfig.set_log_level("INFO")

# 为特定模块设置更详细的级别（如果需要）
logger.configure(handlers=[{"sink": sys.stderr, "level": "DEBUG", "filter": lambda record: "auth_service" in record["name"]}])
```

## 错误和异常记录

### 异常处理最佳实践

1. **使用logger.exception**：自动包含异常堆栈

   ```python
   try:
       # 可能引发异常的代码
       process_data(data)
   except Exception as e:
       logger.exception(f"处理数据时出错: {e}")
       # 错误处理...
   ```

2. **使用error_handler装饰器**：简化错误处理和日志记录

   ```python
   from src.utils.error_handling import error_handler, ErrorCode
   
   @error_handler(default_error_code=ErrorCode.PROCESSING_ERROR)
   def process_data(data):
       # 处理逻辑...
   ```

3. **区分预期和非预期异常**：使用不同的日志级别

   ```python
   try:
       validate_input(data)
   except ValidationError as e:
       # 预期的错误，使用ERROR级别
       logger.error(f"输入验证失败: {e}")
       return error_response(str(e))
   except Exception as e:
       # 非预期错误，使用CRITICAL级别并包含堆栈
       logger.critical(f"处理请求时发生意外错误: {e}")
       logger.exception("详细错误信息")
       return system_error_response()
   ```

### 错误上下文

确保错误日志包含足够的上下文信息以便调试：

```python
try:
    process_order(order_id, items)
except Exception as e:
    logger.exception(
        "处理订单失败",
        extra={
            "order_id": order_id,
            "item_count": len(items),
            "total_amount": sum(item.price for item in items),
            "customer_id": customer_id,
            "payment_method": payment_method
        }
    )
```

## 敏感信息处理

### 需要保护的敏感信息

- 密码和认证令牌
- 信用卡信息
- 个人身份信息（PII）
- API密钥和密钥
- 内部系统地址和凭据

### 保护敏感数据的方法

1. **使用掩码**：遮蔽部分敏感数据

   ```python
   def mask_card_number(card_number):
       if not card_number or len(card_number) < 8:
           return "****"
       return f"****{card_number[-4:]}"
   
   logger.info("处理支付，卡号: {card}", card=mask_card_number(card_number))
   ```

2. **使用APILogger自动过滤**：配置敏感字段列表

   ```python
   from src.utils.api_logger import APILogger
   
   api_logger = APILogger(sensitive_fields=[
       "password", "token", "api_key", "secret",
       "card_number", "cvv", "ssn", "passport"
   ])
   
   api_logger.log_request_response(
       method="POST",
       url="https://api.example.com/auth",
       data={"username": "user123", "password": "secret123"},  # 密码将被遮蔽
       response=response
   )
   ```

3. **避免记录完整对象**：仅记录必要字段

   ```python
   # 不推荐 - 记录完整的用户对象可能包含敏感信息
   logger.info("用户信息: {user}", user=user)
   
   # 推荐 - 仅记录非敏感字段
   logger.info("用户信息: {user_info}", user_info={
       "id": user.id,
       "username": user.username,
       "email_domain": user.email.split('@')[1] if user.email else None,
       "account_type": user.account_type
   })
   ```

## 代码评审检查项

在代码评审时，对日志记录部分应检查以下项目：

### 基本检查

- [ ] 是否使用了正确的日志级别？
- [ ] 日志消息是否清晰且包含足够上下文？
- [ ] 是否避免了记录敏感信息？
- [ ] 是否正确处理了异常并记录了相关日志？
- [ ] 高频循环中是否避免了过多的日志记录？

### 高级检查

- [ ] 是否使用了结构化日志记录？
- [ ] 是否使用了日志上下文？
- [ ] 日志是否遵循了项目的命名和格式规范？
- [ ] 日志中是否包含了调试所需的所有信息？
- [ ] 日志是否会在适当的情况下触发告警？

### 性能检查

- [ ] 是否避免了在日志语句中执行昂贵的操作？
- [ ] 是否使用了条件日志记录来避免不必要的字符串格式化？
- [ ] 日志记录是否会影响应用程序性能？ 