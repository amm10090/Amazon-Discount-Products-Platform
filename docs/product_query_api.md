# 商品查询API文档

## 简介

商品查询API提供了一个批量查询商品详细信息的接口。支持通过ASIN（Amazon标准识别号）查询单个或多个商品的详细信息，包括价格、优惠、分类等数据。

## API端点

```
POST /api/products/query
```

## 请求格式

```json
{
  "asins": ["B0123456789", "B0987654321"],  // 或单个ASIN字符串
  "include_metadata": false,
  "include_browse_nodes": ["123", "456"]
}
```

## 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| asins | string/array | 是 | - | 单个ASIN字符串或ASIN数组(最多50个) |
| include_metadata | boolean | 否 | false | 是否包含商品元数据 |
| include_browse_nodes | array | 否 | null | 要包含的浏览节点ID列表 |

## 响应格式

### 单个ASIN查询响应

```json
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
      "availability": "In Stock",
      "merchant_name": "Amazon.com",
      "is_buybox_winner": true,
      "deal_type": "LIGHTNING_DEAL",
      "coupon_type": "percentage",
      "coupon_value": 5.0,
      "commission": "10%"
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
```

### 批量ASIN查询响应

```json
[
  {
    // 商品1详情（格式同上）
  },
  null,  // 未找到的商品返回null
  {
    // 商品3详情（格式同上）
  }
]
```

## 错误响应

```json
{
  "detail": "错误信息"
}
```

## 字段说明

### 请求参数详细说明

| 参数名 | 说明 |
|--------|------|
| asins | ASIN必须是10位字符串。批量查询时最多支持50个ASIN |
| include_metadata | 设为true时会返回商品的原始元数据 |
| include_browse_nodes | 指定要返回的浏览节点ID，为空则返回所有节点 |

### 响应字段说明

| 字段名 | 说明 |
|--------|------|
| asin | Amazon标准识别号 |
| title | 商品标题 |
| url | 商品链接 |
| brand | 品牌名称 |
| main_image | 主图链接 |
| offers | 商品优惠信息列表 |
| timestamp | 数据更新时间 |
| binding | 商品绑定类型 |
| product_group | 商品分组 |
| categories | 商品分类列表 |
| browse_nodes | 浏览节点信息 |
| features | 商品特性列表 |
| cj_url | CJ推广链接(仅CJ商品) |
| api_provider | 数据来源(pa-api/cj-api) |
| source | 数据来源类型(bestseller/coupon/discount) |
| coupon_expiration_date | 优惠券过期日期(仅优惠券商品) |
| coupon_terms | 优惠券使用条款(仅优惠券商品) |

### 优惠信息字段说明

| 字段名 | 说明 |
|--------|------|
| condition | 商品状态 |
| price | 当前价格 |
| currency | 货币单位 |
| savings | 节省金额 |
| savings_percentage | 折扣百分比 |
| is_prime | 是否Prime商品 |
| availability | 库存状态 |
| merchant_name | 卖家名称 |
| is_buybox_winner | 是否购买框优胜者 |
| deal_type | 优惠类型 |
| coupon_type | 优惠券类型 |
| coupon_value | 优惠券面值 |
| commission | CJ佣金比例 |

## 使用示例

### 单个商品查询

```bash
curl -X POST "http://your-server/api/products/query" \
  -H "Content-Type: application/json" \
  -d '{
    "asins": "B0123456789",
    "include_metadata": true
  }'
```

### 批量商品查询

```bash
curl -X POST "http://your-server/api/products/query" \
  -H "Content-Type: application/json" \
  -d '{
    "asins": ["B0123456789", "B0987654321"],
    "include_metadata": false,
    "include_browse_nodes": ["123", "456"]
  }'
```

## 注意事项

1. 批量查询时，未找到的商品在返回列表中对应位置为null
2. 建议单次查询的ASIN数量不要超过20个，以获得最佳性能
3. include_metadata参数会增加响应大小，请按需使用
4. 返回的数据可能包含缓存内容，timestamp字段表示数据的最后更新时间
5. 部分字段可能为null，调用方需要做好空值处理

## 错误代码

| HTTP状态码 | 说明 |
|-----------|------|
| 400 | 请求参数错误 |
| 404 | 未找到任何商品 |
| 500 | 服务器内部错误 |

## 限制说明

1. 每个请求最多包含50个ASIN
2. 请求频率限制：每IP每分钟100次
3. 响应超时时间：10秒
4. 单次请求最大响应大小：10MB 