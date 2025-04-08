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
        # 获取有优惠券的商品
        success, fail, variants, coupon, discount = await crawler.fetch_all_products(
            db=db,
            max_items=100,
            have_coupon=1,  # 只获取有优惠券的商品
            category="Electronics",
            save_variants=True,
            use_random_cursor=True,  # 使用随机游标策略
            skip_existing=True  # 跳过已存在的商品
        )
        
        print(f"成功: {success}, 优惠券: {coupon}, 折扣: {discount}")
        
        # 获取游标历史
        cursor_history = crawler.get_cursor_history()
        print(f"游标历史数量: {len(cursor_history)}")
        
        # 清除游标历史（如需要）
        # crawler.clear_cursor_history()
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

爬虫支持两种游标策略：

1. **顺序游标（默认策略）**：
   - 按顺序使用API返回的游标获取下一页商品
   - 适合首次采集或全量更新
   - 当连续多次（默认5次）无新商品时结束

2. **随机游标策略**：
   - 通过`--random-cursor`命令行参数或`use_random_cursor=True`参数启用
   - 当连续多次无新商品时，从历史游标中随机选择一个游标
   - 有效提高商品发现率，特别是在大量数据已存在的情况下
   - 会自动记录历史游标供后续使用
   - 通过程序接口可获取或清除游标历史
   - 建议定期执行增量更新时使用此策略

### 游标历史管理

随机游标策略会记录并使用历史游标：

```python
# 获取当前游标历史
cursor_history = crawler.get_cursor_history()

# 清除游标历史
crawler.clear_cursor_history()

# 添加自定义游标到历史
crawler.add_cursor_to_history("YOUR_CUSTOM_CURSOR")
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
- 随机游标使用记录
- 重复商品过滤统计

## 性能注意事项

- **随机游标策略**：启用随机游标可能会导致部分重复请求，但能提高长期数据采集的多样性
- **跳过现有商品**：启用此功能可显著减少数据库写入操作，提高采集效率
- **变体关系处理**：保存变体关系会增加数据库操作，但提供更完整的商品关联信息
- **游标历史**：随机游标策略会在内存中保存游标历史，大量采集时注意内存使用

## 使用场景

1. **批量获取商品数据**：直接从CJ API获取大量商品数据，无需先抓取ASIN
   ```bash
   python -m src.core.cj_products_crawler --limit 1000
   ```

2. **优惠券商品获取**：专门获取有优惠券的商品
   ```bash
   python -m src.core.cj_products_crawler --have-coupon 1 --limit 200
   ```

3. **分类商品获取**：获取特定类别的商品
   ```bash
   python -m src.core.cj_products_crawler --category "Electronics" --limit 300
   ```

4. **初次全量采集**：采集大量新商品，不使用随机游标
   ```bash
   python -m src.core.cj_products_crawler --limit 500
   ```

5. **增量更新**：使用随机游标策略提高新商品发现率
   ```bash
   python -m src.core.cj_products_crawler --limit 300 --random-cursor
   ```

6. **商品信息更新**：更新现有商品的价格和优惠信息
   ```bash
   python -m src.core.cj_products_crawler --limit 200 --no-skip-existing
   ```

7. **完整采集方案**：同时使用多种功能的组合
   ```bash
   python -m src.core.cj_products_crawler --category "Electronics" --have-coupon 1 --limit 300 --random-cursor --save-variants
   ```

## 最佳实践

1. **初次采集**：不使用随机游标，采集尽可能多的商品
2. **定期增量更新**：启用随机游标和跳过现有商品，提高效率和数据多样性
3. **全量更新**：定期使用不跳过现有商品的选项，更新所有商品的最新信息
4. **分类管理**：按类别分批次采集，便于管理和监控
5. **变体关系**：对重要类别启用变体关系保存，提供更完整的商品信息

## 注意事项

- CJ API有请求频率限制，爬虫会添加适当的延迟避免请求过快
- 爬虫会自动处理分页，获取指定数量的商品
- 默认情况下不保存变体关系，如需保存请使用`--save-variants`选项
- 默认会跳过已存在的商品，如需更新现有商品信息，请使用`--no-skip-existing`选项 