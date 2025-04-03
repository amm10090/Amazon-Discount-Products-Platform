# 产品搜索API文档

## 简介

产品搜索API提供了一个强大的接口，允许用户通过关键词搜索系统中的产品数据。API支持多种过滤和排序选项，使用户能够精确地找到他们需要的产品信息。
此外，API现在支持ASIN格式识别，用户可以直接输入ASIN作为关键词进行精确查询。

## API端点

```
GET /api/search/products
```

## 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| keyword | string | 是 | - | 搜索关键词，用于在产品标题、品牌和特性中进行匹配，也支持ASIN格式 |
| page | integer | 否 | 1 | 页码，从1开始 |
| page_size | integer | 否 | 10 | 每页返回的产品数量，范围：1-100 |
| sort_by | string | 否 | "relevance" | 排序字段：<br>- "relevance": 按相关性排序<br>- "price": 按价格排序<br>- "discount": 按折扣率排序<br>- "created": 按创建时间排序 |
| sort_order | string | 否 | "desc" | 排序方向：<br>- "asc": 升序<br>- "desc": 降序 |
| min_price | number | 否 | null | 最低价格过滤，单位：美元 |
| max_price | number | 否 | null | 最高价格过滤，单位：美元 |
| min_discount | integer | 否 | null | 最低折扣率过滤，范围：0-100 |
| is_prime_only | boolean | 否 | false | 是否只显示Prime商品 |
| product_groups | string | 否 | null | 商品分类过滤，多个分类用逗号分隔 |
| brands | string | 否 | null | 品牌过滤，多个品牌用逗号分隔 |
| api_provider | string | 否 | null | 数据来源过滤：<br>- "pa-api": 亚马逊PA-API数据源<br>- "cj-api": CJ联盟数据源 |

## 响应格式

成功响应（HTTP状态码：200）

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "asin": "B0123456789",
        "title": "产品标题",
        "url": "https://www.amazon.com/dp/B0123456789",
        "brand": "品牌名称",
        "main_image": "https://images-na.ssl-images-amazon.com/images/I/71aBLaSlF8L._AC_SL1500_.jpg",
        "offers": [
          {
            "condition": "New",
            "price": 99.99,
            "currency": "USD",
            "savings": 20.00,
            "savings_percentage": 17,
            "is_prime": true,
            "is_amazon_fulfilled": true,
            "is_free_shipping_eligible": true,
            "availability": "In Stock",
            "merchant_name": "Amazon.com",
            "is_buybox_winner": true,
            "deal_type": "LIGHTNING_DEAL",
            "coupon_type": "percentage",
            "coupon_value": 5.0
          }
        ],
        "timestamp": "2023-01-01T12:00:00",
        "binding": "Electronics",
        "product_group": "Consumer Electronics",
        "categories": ["Electronics", "Computers & Accessories"],
        "browse_nodes": [
          {
            "id": "172282",
            "name": "Electronics"
          }
        ],
        "features": ["特性1", "特性2", "特性3"],
        "cj_url": "https://www.anrdoezrs.net/links/...",
        "api_provider": "pa-api"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 10,
    "is_asin_search": false
  }
}
```

当使用ASIN搜索且成功匹配单个产品时:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "asin": "B0123456789",
        "title": "产品标题",
        // 其他产品字段
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 1,
    "is_asin_search": true
  }
}
```

当使用ASIN搜索但未找到产品时:

```json
{
  "success": false,
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 10,
    "is_asin_search": true
  },
  "error": "未找到ASIN为'B0123456789'的商品。这是有效的ASIN格式，但在数据库中不存在。"
}
```

失败响应（HTTP状态码：200，但操作失败）

```json
{
  "success": false,
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 10,
    "is_asin_search": false
  },
  "error": "错误信息"
}
```

## 字段说明

### 响应字段

| 字段名 | 描述 |
|--------|------|
| success | 布尔值，表示请求是否成功 |
| data.items | 产品列表，包含匹配搜索条件的产品详情 |
| data.total | 总匹配产品数量 |
| data.page | 当前页码 |
| data.page_size | 每页产品数量 |
| data.is_asin_search | 布尔值，表示搜索是否按ASIN格式进行 |
| error | 错误信息（仅在失败时存在） |

### 产品对象字段

| 字段名 | 描述 |
|--------|------|
| asin | Amazon标准识别号 |
| title | 产品标题 |
| url | 产品链接 |
| brand | 品牌名称 |
| main_image | 主图链接 |
| offers | 产品优惠信息列表 |
| timestamp | 数据采集时间 |
| binding | 商品绑定类型 |
| product_group | 商品分组 |
| categories | 商品分类列表 |
| browse_nodes | 亚马逊浏览节点信息 |
| features | 商品特性列表 |
| cj_url | CJ推广链接（仅当api_provider为"cj-api"时有值） |
| api_provider | 数据来源："pa-api"或"cj-api" |

### 优惠对象字段

| 字段名 | 描述 |
|--------|------|
| condition | 商品状态（例如："New"、"Used"） |
| price | 当前价格 |
| currency | 货币单位 |
| savings | 节省金额 |
| savings_percentage | 折扣百分比 |
| is_prime | 是否Prime商品 |
| is_amazon_fulfilled | 是否由亚马逊配送 |
| is_free_shipping_eligible | 是否符合免运费条件 |
| availability | 库存状态 |
| merchant_name | 卖家名称 |
| is_buybox_winner | 是否为购买框优胜者 |
| deal_type | 优惠类型 |
| coupon_type | 优惠券类型：percentage(百分比)/fixed(固定金额) |
| coupon_value | 优惠券面值 |
| commission | CJ佣金信息（仅当api_provider为"cj-api"时有值） |

## 搜索算法说明

搜索API使用以下逻辑进行匹配和排序：

1. **ASIN检测**：系统首先检查搜索关键词是否符合ASIN格式（10位字符，以B开头的字母数字组合或10位纯数字ISBN）。如果是有效的ASIN格式，系统会尝试直接通过ASIN查询产品。

2. **关键词搜索**：如果不是ASIN格式或通过ASIN未找到产品，系统会执行以下步骤：
   - **关键词拆分**：系统会将搜索关键词拆分为多个单词，分别在产品标题、品牌和特性中进行匹配
   - **匹配方式**：使用包含匹配（LIKE '%关键词%'），而不是精确匹配，以提高搜索灵敏度
   - **相关性排序**：当sort_by设置为"relevance"时，系统会计算相关性得分：
     - 标题匹配的权重最高
     - 品牌名称匹配的权重次之
     - 多个关键词匹配的得分会累加

## 使用示例

### ASIN搜索

```
GET /api/search/products?keyword=B07PXGQC1Q
```

直接通过ASIN "B07PXGQC1Q" 查询产品。

### 基本关键词搜索

```
GET /api/search/products?keyword=apple
```

搜索所有与"apple"相关的产品。

### 高级搜索

```
GET /api/search/products?keyword=laptop&min_price=500&max_price=1000&min_discount=20&is_prime_only=true&sort_by=price&sort_order=asc&product_groups=Electronics&brands=Apple,Dell&page=1&page_size=20
```

搜索符合以下条件的产品：
- 关键词包含"laptop"
- 价格在500-1000美元之间
- 折扣率至少20%
- 仅Prime商品
- 按价格升序排序
- 产品分类为Electronics
- 品牌为Apple或Dell
- 返回第1页，每页20条记录

## 注意事项

1. 关键词搜索对大小写不敏感
2. 多个关键词之间用空格分隔，系统会自动拆分并查找匹配所有关键词的产品
3. 当使用品牌过滤时，系统只会返回完全匹配指定品牌的产品
4. 相关性排序算法会优先考虑标题中的关键词匹配
5. API的性能与数据库性能直接相关，大数据量查询可能会导致响应延迟
6. ASIN格式的关键词会触发精确查询，如果数据库中不存在该ASIN，系统会给出明确提示

## 错误代码和处理

虽然API通常返回HTTP状态码200，但响应体中的`success`字段会指示操作是否成功。当`success`为`false`时，请检查`error`字段获取错误详情。

常见错误包括：
- 数据库连接失败
- 查询参数格式错误
- 服务器内部错误
- ASIN格式有效但未找到对应产品

## 限制和性能考虑

- 每页最多返回100条记录
- 对于高流量网站，建议实施缓存策略
- 复杂查询可能需要更长的响应时间 