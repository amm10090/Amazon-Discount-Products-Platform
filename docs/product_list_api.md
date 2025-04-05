# 产品列表API文档

## 概述

产品列表API(`/api/products/list`)提供了一个灵活的接口，用于获取亚马逊平台上的商品列表。该API支持多种筛选条件、排序选项和分页功能，使您能够按需检索特定类型的商品数据。

## API端点

```
GET /api/products/list
```

## 请求参数

该API支持以下查询参数：

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|-------|------|------|--------|-----|
| page | 整数 | 否 | 1 | 页码，从1开始 |
| page_size | 整数 | 否 | 20 | 每页显示的商品数量，范围1-100 |
| min_price | 浮点数 | 否 | 无 | 最低价格筛选 |
| max_price | 浮点数 | 否 | 无 | 最高价格筛选 |
| min_discount | 整数 | 否 | 无 | 最低折扣率(%)，范围0-100 |
| sort_by | 字符串 | 否 | 无 | 排序字段，可选值包括：price(价格)、discount(折扣)、created(创建时间) |
| sort_order | 字符串 | 否 | "desc" | 排序方向，可选值：asc(升序)、desc(降序) |
| is_prime_only | 布尔值 | 否 | false | 是否只显示Prime商品 |
| product_type | 字符串 | 否 | "all" | 商品类型，可选值：discount(折扣商品)、coupon(优惠券商品)、all(所有商品) |
| browse_node_ids | 字符串/数组 | 否 | 无 | 浏览节点ID，支持多个值(数组或逗号分隔的字符串) |
| bindings | 字符串/数组 | 否 | 无 | 商品绑定类型，支持多个值(数组或逗号分隔的字符串) |
| product_groups | 字符串/数组 | 否 | 无 | 商品组，支持多个值(数组或逗号分隔的字符串) |
| api_provider | 字符串 | 否 | 无 | 数据来源，可选值：pa-api(亚马逊PA API)、cj-api(CJ联盟API)、all(所有来源) |
| min_commission | 整数 | 否 | 无 | 最低佣金比例(%)，范围0-100 |
| brands | 字符串/数组 | 否 | 无 | 品牌，支持多个值(数组或逗号分隔的字符串) |

## 返回结果

### 成功响应

响应状态码：`200 OK`

响应示例：

```json
{
  "items": [
    {
      "asin": "B01MXXYZ12",
      "title": "示例商品标题",
      "description": "商品描述...",
      "features": ["特点1", "特点2", "特点3"],
      "images": {
        "primary": {
          "small": "https://example.com/images/small.jpg",
          "medium": "https://example.com/images/medium.jpg",
          "large": "https://example.com/images/large.jpg"
        },
        "variants": [
          {
            "small": "https://example.com/images/variant1_small.jpg",
            "medium": "https://example.com/images/variant1_medium.jpg",
            "large": "https://example.com/images/variant1_large.jpg"
          }
        ]
      },
      "brand": "示例品牌",
      "offers": [
        {
          "price": 89.99,
          "original_price": 129.99,
          "discount_percent": 30,
          "currency": "USD",
          "availability": "InStock",
          "condition": "New",
          "is_prime": true
        }
      ],
      "browse_nodes": [
        {
          "id": "12345",
          "name": "电子产品"
        },
        {
          "id": "67890",
          "name": "家用电器"
        }
      ],
      "product_group": "家电",
      "binding": "电子配件",
      "is_coupon": false,
      "coupon_info": null,
      "created_at": "2023-01-01T12:00:00Z",
      "updated_at": "2023-01-10T15:30:00Z",
      "source": "pa-api",
      "commission_rate": 3
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|-----|------|-----|
| items | 数组 | 商品列表 |
| total | 整数 | 符合条件的商品总数 |
| page | 整数 | 当前页码 |
| page_size | 整数 | 每页数量 |

### 商品对象(ProductInfo)字段说明

| 字段 | 类型 | 说明 |
|-----|------|-----|
| asin | 字符串 | 亚马逊标准识别号 |
| title | 字符串 | 商品标题 |
| description | 字符串 | 商品描述 |
| features | 字符串数组 | 商品特点列表 |
| images | 对象 | 商品图片信息 |
| brand | 字符串 | 品牌名称 |
| offers | 数组 | 商品报价信息 |
| browse_nodes | 数组 | 商品分类节点 |
| product_group | 字符串 | 产品组 |
| binding | 字符串 | 绑定类型 |
| is_coupon | 布尔值 | 是否有优惠券 |
| coupon_info | 对象/null | 优惠券信息 |
| created_at | 字符串 | 创建时间(ISO格式) |
| updated_at | 字符串 | 更新时间(ISO格式) |
| source | 字符串 | 数据来源 |
| commission_rate | 整数 | 佣金比例(%) |

### 错误响应

当API调用失败时，将返回以下格式的响应：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

## 使用示例

### 基本用法

获取第一页20个商品：

```
GET /api/products/list
```

### 分页和排序

获取第2页、每页10条、按价格降序排列的商品：

```
GET /api/products/list?page=2&page_size=10&sort_by=price&sort_order=desc
```

### 筛选条件

获取价格在10-50之间、折扣率至少20%的Prime商品：

```
GET /api/products/list?min_price=10&max_price=50&min_discount=20&is_prime_only=true
```

### 按类别筛选

获取电子产品分类下的商品：

```
GET /api/products/list?browse_node_ids=123456,789012
```

### 按品牌筛选

获取特定品牌的商品：

```
GET /api/products/list?brands=Apple,Samsung
```

### 组合查询

获取电子产品类别下、价格在100-500之间、折扣至少30%、属于特定品牌的优惠券商品：

```
GET /api/products/list?product_type=coupon&browse_node_ids=123456&min_price=100&max_price=500&min_discount=30&brands=Apple,Samsung
```

## 注意事项

1. 所有价格相关的筛选参数均使用美元(USD)作为单位
2. 当同时提供多个筛选条件时，条件之间是"与"(AND)的关系
3. 对于列表参数(browse_node_ids, bindings, product_groups, brands)，支持两种传参方式：
   - 数组格式：`?browse_node_ids[]=123&browse_node_ids[]=456`
   - 逗号分隔的字符串：`?browse_node_ids=123,456`
4. API结果默认按创建时间倒序排列(最新的商品在前)
5. 商品价格总是使用数据库中的current_price字段，确保价格信息的准确性 