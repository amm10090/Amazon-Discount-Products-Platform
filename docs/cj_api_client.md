# CJ API客户端

本文档介绍了CJ API客户端的使用方法，该客户端提供了与CJ平台进行交互的API封装。

## 概述

`CJAPIClient`类封装了与CJ平台API的通信，主要提供以下功能：

1. 获取商品列表
2. 生成商品推广链接
3. 检查商品可用性
4. 获取商品详情
5. 支持随机游标策略

## 配置

CJ API客户端需要以下环境变量配置：

- `CJ_API_BASE_URL`: CJ API的基础URL，默认为"https://cj.partnerboost.com/api"
- `CJ_PID`: CJ平台的PID (合作伙伴ID)
- `CJ_CID`: CJ平台的CID (渠道ID)

可以在项目的`.env`文件中配置这些变量：

```
CJ_API_BASE_URL=https://cj.partnerboost.com/api
CJ_PID=your_pid_here
CJ_CID=your_cid_here
```

## 使用方法

### 初始化客户端

```python
from src.core.cj_api_client import CJAPIClient

# 初始化客户端
client = CJAPIClient()
```

### 获取商品列表

```python
# 获取所有商品
response = await client.get_products()

# 获取特定类别的商品
response = await client.get_products(category="Electronics")

# 获取有优惠券的商品
response = await client.get_products(have_coupon=1)

# 获取指定ASIN的商品
response = await client.get_products(asins=["B07XYZ123", "B07ABC456"])

# 使用随机游标策略
response = await client.get_products(category="Electronics", use_random_cursor=True)
```

### 参数说明

`get_products`方法支持以下参数：

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `asins` | List[str] | None | ASIN列表 |
| `category` | str | None | 商品类别 |
| `subcategory` | str | None | 商品子类别 |
| `cursor` | str | "" | 分页游标 |
| `limit` | int | 50 | 每页数量，最大50 |
| `country_code` | str | "US" | 国家代码 |
| `brand_id` | int | 0 | 品牌ID |
| `is_featured_product` | int | 2 | 是否精选商品(0:否, 1:是, 2:全部) |
| `is_amazon_choice` | int | 2 | 是否亚马逊之选(0:否, 1:是, 2:全部) |
| `have_coupon` | int | 2 | 是否有优惠券(0:否, 1:是, 2:全部) |
| `discount_min` | int | 0 | 最低折扣率 |
| `use_random_cursor` | bool | False | 是否使用随机游标策略 |

### 游标策略

客户端支持两种游标策略：

1. **顺序游标**：默认策略，使用API返回的下一个游标，按顺序获取数据。
2. **随机游标**：当连续多次未获取到新商品时，从历史游标记录中随机选择一个，提高数据发现率。

使用随机游标策略：
```python
# 启用随机游标策略
client.set_cursor_strategy(random_strategy=True)

# 或者在请求时指定
response = await client.get_products(use_random_cursor=True)
```

### 游标历史管理

客户端会自动记录历史游标，并提供以下方法管理：

```python
# 获取历史游标列表
cursor_history = client.get_cursor_history()

# 清除游标历史
client.clear_cursor_history()

# 从历史中获取随机游标
random_cursor = client.get_random_cursor()
```

### 生成商品推广链接

```python
# 为指定ASIN生成推广链接
link = await client.generate_product_link(asin="B07XYZ123")
```

### 检查商品可用性

```python
# 检查多个ASIN的可用性
availability = await client.check_products_availability(
    asins=["B07XYZ123", "B07ABC456", "B07DEF789"]
)

# 结果示例：{"B07XYZ123": True, "B07ABC456": False, "B07DEF789": True}
```

### 获取单个商品详情

```python
# 获取单个商品的详细信息
product_details = await client.get_product_details(asin="B07XYZ123")
```

## 响应格式

### 获取商品列表响应

```json
{
  "message": "success",
  "code": 0,
  "data": {
    "list": [
      {
        "asin": "B0D5BBHG5R",
        "availability": "IN_STOCK",
        "brand_id": 133528,
        "brand_name": "nevilywood",
        "category": "Patio, Lawn & Garden",
        "commission": "18%",
        "country_code": "US",
        "coupon": null,
        "discount": "0%",
        "discount_code": null,
        "discount_price": "$239.99",
        "image": "https://m.media-amazon.com/images/I/41DZRsu6tpL._SS500_.jpg",
        "is_amazon_choice": 0,
        "is_featured_product": 0,
        "original_price": "$239.99",
        "parent_asin": "B0D5B4W16L",
        "product_id": "d34ea967c642f082d3f3ab2900938d88",
        "product_name": "Folding Adirondack Chair...",
        "rating": "4.9",
        "reviews": 40,
        "subcategory": "Adirondack Chairs",
        "update_time": "2025-04-08",
        "url": "https://www.amazon.com/dp/B0D5BBHG5R",
        "variant_asin": "B0DFT3QT9F,B0D5BDBHKC,..."
      }
    ],
    "has_more": true,
    "cursor": "eyJsYXN0X2lkIjoxMTQwOTg3..."
  }
}
```

## 错误处理

客户端会自动处理API请求失败的情况，包括：

- 重试失败的请求
- 处理HTTP错误
- 解析API错误响应

错误发生时会抛出异常，异常信息包含API返回的错误消息。

## 最佳实践

1. **批量获取商品数据**：使用`get_products`方法时，建议设置适当的筛选条件，如类别或优惠券状态，以获取更精确的结果。

2. **分页处理**：当需要获取大量商品时，使用游标(cursor)进行分页请求，每次获取50个商品。

3. **随机游标策略**：当需要发现更多不同的商品时，启用随机游标策略，避免陷入单一数据流。

4. **推广链接**：在展示商品时，使用`generate_product_link`方法生成带有推广信息的链接，以便跟踪转化率。

5. **错误处理**：总是使用try-except处理API请求可能出现的异常，确保程序健壮性。

6. **限制请求频率**：避免短时间内发送过多请求，这可能导致API限制。建议在请求之间添加适当的延迟。

## 示例代码

```python
import asyncio
from src.core.cj_api_client import CJAPIClient

async def main():
    client = CJAPIClient()
    
    # 1. 获取有优惠券的电子产品，使用随机游标策略
    products_response = await client.get_products(
        category="Electronics",
        have_coupon=1,
        limit=10,
        use_random_cursor=True
    )
    
    products = products_response.get("data", {}).get("list", [])
    print(f"获取到 {len(products)} 个带优惠券的电子产品")
    
    # 2. 为第一个商品生成推广链接
    if products:
        first_product = products[0]
        asin = first_product["asin"]
        link = await client.generate_product_link(asin=asin)
        print(f"商品 {asin} 的推广链接: {link}")
    
    # 3. 检查多个商品的可用性
    if len(products) >= 3:
        test_asins = [p["asin"] for p in products[:3]]
        availability = await client.check_products_availability(asins=test_asins)
        print(f"商品可用性检查结果: {availability}")
    
    # 4. 查看当前游标历史
    cursor_history = client.get_cursor_history()
    print(f"游标历史记录数量: {len(cursor_history)}")

if __name__ == "__main__":
    asyncio.run(main())
``` 