# CJ API商品抓取器

本文档介绍如何使用CJ API商品抓取器从CJ平台直接获取商品数据并保存到数据库。

## 功能概述

CJ API商品抓取器(`cj_products_crawler.py`)提供以下功能：

1. 直接从CJ API获取商品数据
2. 自动将CJ的数据格式转换为系统内部的数据模型
3. 根据商品是否有优惠券，自动设置商品来源(`source`)为"coupon"或"discount"
4. 处理商品变体关系
5. 支持分页获取大量商品数据
6. 支持随机游标策略，提高商品发现率和数据多样性
7. 支持跳过数据库中已有的商品，避免重复采集或强制更新现有数据
8. **游标持久化存储**：将游标历史保存到文件系统，便于任务停止后恢复
9. **游标过期机制**：支持单个游标和全局扫描的过期策略，确保定期更新商品数据

## 命令行使用

```bash
# 基本用法
python -m src.core.cj_products_crawler --limit 100

# 筛选优惠券商品
python -m src.core.cj_products_crawler --have-coupon 1 --limit 50

# 筛选特定类别
python -m src.core.cj_products_crawler --category "Electronics" --limit 200

# 导出结果
python -m src.core.cj_products_crawler --limit 100 --output asins.txt

# 调试模式
python -m src.core.cj_products_crawler --debug --limit 10

# 处理商品变体关系
python -m src.core.cj_products_crawler --limit 100 --save-variants

# 使用随机游标策略
python -m src.core.cj_products_crawler --limit 100 --random-cursor

# 不跳过已存在的商品（默认会跳过）
python -m src.core.cj_products_crawler --limit 100 --no-skip-existing

# 组合使用多个功能
python -m src.core.cj_products_crawler --category "Electronics" --have-coupon 1 --limit 200 --random-cursor --save-variants
```

## 命令行参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--category` | 字符串 | 无 | 商品类别 |
| `--subcategory` | 字符串 | 无 | 商品子类别 |
| `--limit` | 整数 | 100 | 最大获取数量 |
| `--have-coupon` | 整数(0/1/2) | 2 | 是否有优惠券(0:无 1:有 2:全部) |
| `--min-discount` | 整数 | 0 | 最低折扣率 |
| `--save-variants` | 布尔值 | False | 是否保存变体关系 |
| `--output` | 字符串 | 无 | 输出文件路径 |
| `--debug` | 布尔值 | False | 是否启用调试模式 |
| `--random-cursor` | 布尔值 | False | 是否使用随机游标策略 |
| `--no-skip-existing` | 布尔值 | False | 是否不跳过已存在的商品 |

## 程序化使用

除了命令行使用外，你也可以在Python代码中使用CJProductsCrawler类：

```python
from models.database import SessionLocal
from src.core.cj_products_crawler import CJProductsCrawler

async def fetch_products():
    crawler = CJProductsCrawler()
    db = SessionLocal()
    
    try:
        # 获取有优惠券的商品，使用持久化游标功能
        success, fail, variants, coupon, discount = await crawler.fetch_all_products(
            db=db,
            max_items=100,
            have_coupon=1,  # 只获取有优惠券的商品
            category="Electronics",
            save_variants=True,
            use_random_cursor=False,  # 不使用随机游标策略
            skip_existing=True,  # 跳过已存在的商品
            use_persistent_cursor=True  # 启用游标持久化功能
        )
        
        print(f"成功: {success}, 优惠券: {coupon}, 折扣: {discount}")
        
        # 日常增量更新示例
        await crawler.fetch_all_products(
            db=db,
            max_items=200,
            skip_existing=True,
            use_persistent_cursor=True  # 使用持久化游标，继续上次爬取位置
        )
        
        # 全量更新示例（忽略保存的游标历史）
        await crawler.fetch_all_products(
            db=db,
            max_items=500,
            skip_existing=False,
            use_persistent_cursor=False  # 禁用持久化游标，从头开始爬取
        )
        
    finally:
        db.close()

# 运行异步函数
import asyncio
asyncio.run(fetch_products())
```

## 数据处理

### 数据转换

CJProductsCrawler会自动将CJ API返回的数据格式转换为系统内部的ProductInfo模型：

- 解析价格格式：从"$239.99"转换为浮点数239.99
- 解析优惠券：识别金额优惠券($30)和百分比优惠券(6%)
- 计算节省金额和折扣百分比
- 设置商品数据来源："coupon"或"discount"
- 将商品数据保存到数据库中

### 变体处理

如果启用了`--save-variants`选项，爬虫将处理CJ API返回的变体关系：

1. 从商品数据中提取`parent_asin`和`variant_asin`
2. 创建ProductVariant表记录，存储变体关系
3. 记录变体属性信息

### 游标策略

爬虫支持三种游标策略：

1. **顺序游标（默认策略）**：
   - 按顺序使用API返回的游标获取下一页商品
   - 适合首次采集或全量更新
   - 当连续多次（默认5次）无新商品时结束

2. **随机游标策略**：
   - 通过`--random-cursor`命令行参数或`use_random_cursor=True`参数启用
   - 当连续多次无新商品时，从历史游标中随机选择一个游标
   - 有效提高商品发现率，特别是在大量数据已存在的情况下
   - 会自动记录历史游标供后续使用（仅会话内有效）
   - 建议定期执行增量更新时使用此策略

3. **持久化游标策略（推荐）**：
   - 通过`use_persistent_cursor=True`参数启用（默认启用）
   - 将游标历史保存到文件系统，在任务重启后仍然可用
   - 支持游标过期机制，自动淘汰长期未使用的游标
   - 支持定期全局扫描，确保不会错过新商品
   - 建议在调度任务和长期运行的系统中使用

### 游标持久化机制

游标持久化功能通过以下机制实现高效的商品采集：

1. **游标存储**：
   - 将游标历史保存在JSON文件中（`data/cursors/cj_cursors.json`）
   - 每个游标记录包含：游标字符串、上次使用时间、成功获取的商品数和ASIN列表
   - 每次使用和成功获取商品后自动更新游标记录

2. **过期机制**：
   - **单个游标过期**：默认7天未使用的游标会被标记为过期
   - **全局扫描过期**：默认每30天执行一次全局扫描（从头开始爬取）
   - 过期时间可在代码中配置（`cursor_expiry_days`和`full_scan_expiry_days`）

3. **游标选择策略**：
   - 检查是否需要执行全局扫描（根据上次全局扫描时间）
   - 过滤出未过期的有效游标
   - 按照历史成功率排序，选择最有可能获取到新商品的游标
   - 如果没有有效游标，则从头开始爬取

4. **优势**：
   - 任务之间可共享游标历史，提高爬取效率
   - 定时任务和调度系统可以从上次停止的位置继续
   - 自动平衡新商品发现和历史爬取位置
   - 定期全局扫描确保不会长期错过新商品

### 游标历史管理

在使用持久化游标功能时，可以通过以下方式管理游标历史：

```python
# 获取当前游标历史
cursor_history = crawler.cursor_history
print(f"有效游标数量: {len(cursor_history)}")

# 检查游标是否已过期
is_expired = crawler._is_cursor_expired("your_cursor_string")

# 检查是否需要执行全局扫描
need_full_scan = crawler._is_full_scan_expired()

# 手动设置过期时间
crawler.cursor_expiry_days = 14  # 将单个游标过期时间设为14天
crawler.full_scan_expiry_days = 60  # 将全局扫描间隔设为60天

# 清除所有游标历史（强制从头开始）
crawler.cursor_history = {}
crawler._save_cursor_history()
```

### 重复商品处理

爬虫提供两种处理重复商品的方式：

1. **跳过已存在商品（默认行为）**：
   - 通过ASIN检查商品是否已存在于数据库
   - 跳过已存在的商品，只保存新商品
   - 适合增量更新场景，提高采集效率

2. **更新已存在商品**：
   - 通过`--no-skip-existing`参数或`skip_existing=False`启用
   - 对已存在的商品进行信息更新（价格、优惠券等）
   - 适合需要更新商品最新信息的场景
   - 注意：此选项会增加数据库操作次数

## 依赖关系

CJ API商品抓取器依赖以下组件：

- `CJAPIClient`：提供与CJ API的通信
- `ProductService`：提供商品数据库操作
- `models.database`：数据库模型定义
- `models.product`：商品信息模型

## 日志

爬虫会生成日志到控制台和`logs/cj_crawler.log`文件，包含以下信息：

- 爬取进度
- 商品处理状态
- 错误信息
- 优惠券和折扣商品统计
- 游标使用记录和选择逻辑
- 游标过期和全局扫描状态
- 重复商品过滤统计

## 性能注意事项

- **游标持久化功能**：定期执行全局扫描会降低短期效率，但确保长期不会错过新商品
- **游标选择策略**：优先使用历史上成功率高的游标，提高采集效率
- **随机游标策略**：启用随机游标可能会导致部分重复请求，但能提高长期数据采集的多样性
- **跳过现有商品**：启用此功能可显著减少数据库写入操作，提高采集效率
- **变体关系处理**：保存变体关系会增加数据库操作，但提供更完整的商品关联信息
- **游标历史存储**：随着时间推移，游标历史文件可能会增大，系统会自动清理过期游标

## 使用场景

1. **定时任务采集**：调度系统中的自动任务，持久化游标确保每次任务从上次位置继续
   ```bash
   python -m src.core.cj_products_crawler --limit 500 # 默认使用持久化游标
   ```

2. **批量获取商品数据**：直接从CJ API获取大量商品数据，无需先抓取ASIN
   ```bash
   python -m src.core.cj_products_crawler --limit 1000
   ```

3. **优惠券商品获取**：专门获取有优惠券的商品
   ```bash
   python -m src.core.cj_products_crawler --have-coupon 1 --limit 200
   ```

4. **分类商品获取**：获取特定类别的商品
   ```bash
   python -m src.core.cj_products_crawler --category "Electronics" --limit 300
   ```

5. **初次全量采集**：禁用持久化游标，从头开始采集大量新商品
   ```python
   await crawler.fetch_all_products(db=db, max_items=500, use_persistent_cursor=False)
   ```

6. **增量更新**：使用持久化游标策略确保从上次停止位置继续
   ```bash
   python -m src.core.cj_products_crawler --limit 300
   ```

7. **商品信息更新**：更新现有商品的价格和优惠信息
   ```bash
   python -m src.core.cj_products_crawler --limit 200 --no-skip-existing
   ```

8. **完整采集方案**：同时使用多种功能的组合
   ```bash
   python -m src.core.cj_products_crawler --category "Electronics" --have-coupon 1 --limit 300 --save-variants
   ```

## 最佳实践

1. **初次采集**：首次使用时，禁用持久化游标功能，采集尽可能多的商品建立基础数据
2. **定期增量更新**：在调度任务中使用持久化游标功能，确保每次任务从上次位置继续
3. **周期性全扫描**：保持默认的全局扫描过期设置（30天），确保定期从头开始扫描一次
4. **定期更新**：对于重要商品，定期使用不跳过现有商品的选项，更新最新价格和优惠信息
5. **分类管理**：按类别分批次采集，便于管理和监控
6. **变体关系**：对重要类别启用变体关系保存，提供更完整的商品信息
7. **游标维护**：如需修改默认过期时间，可在代码中设置`cursor_expiry_days`和`full_scan_expiry_days`

## 注意事项

- CJ API有请求频率限制，爬虫会添加适当的延迟避免请求过快
- 爬虫会自动处理分页，获取指定数量的商品
- 游标过期机制确保定期重新扫描商品，避免错过更新
- 默认情况下不保存变体关系，如需保存请使用`--save-variants`选项
- 默认会跳过已存在的商品，如需更新现有商品信息，请使用`--no-skip-existing`选项
- 游标持久化数据存储在`data/cursors/cj_cursors.json`文件中，确保该目录有写入权限 