# 商品管理 API

本文档详细介绍了用于手动管理商品的 API 端点，包括添加和编辑功能。

## 1. 手动添加商品

### 端点

`POST /api/products/manual`

### 描述

此 API 允许用户通过提供完整的商品信息（遵循 `ProductInfo` 模型）来手动创建一条新的商品记录。这对于添加来自非标准来源或需要手动校正的数据非常有用。

### 请求体

请求体必须是一个有效的 JSON 对象，其结构符合 `models.product.ProductInfo` 模型。

**关键字段说明:**

*   `asin` (string, **必需**): 商品的唯一 ASIN。如果此 ASIN 已存在于数据库中，请求将失败。
*   `title` (string, **必需**): 商品标题。
*   `url` (string, **必需**): 商品的亚马逊链接。
*   `offers` (array, **必需**): 一个包含至少一个 `ProductOffer` 对象的数组。第一个 offer 的信息将用于填充商品的主要价格、状态等字段。
    *   `price` (float, **必需**): 当前售价。
    *   `currency` (string, **必需**): 货币代码 (例如 "USD")。
    *   `condition` (string, **必需**): 商品状况 (例如 "New")。
    *   `availability` (string, **必需**): 库存状况。
    *   `merchant_name` (string, **必需**): 卖家名称。
    *   `original_price` (float, 可选): 商品原价。
    *   `savings` (float, 可选): 节省金额。
    *   `savings_percentage` (integer, 可选): 折扣百分比。
    *   `is_prime` (boolean, 可选): 是否为 Prime 商品。
    *   `coupon_type` (string, 可选): 优惠券类型 ('percentage' 或 'fixed')。
    *   `coupon_value` (float, 可选): 优惠券面值。
    *   `commission` (string, 可选): CJ 佣金信息。
*   `brand` (string, 可选): 品牌名称。
*   `main_image` (string, 可选): 主图链接。
*   `timestamp` (string, 可选): 数据采集的时间戳 (ISO 8601 格式)。如果未提供，将使用当前时间。
*   `binding` (string, 可选): 商品绑定类型。
*   `product_group` (string, 可选): 商品分组。
*   `categories` (array, 可选): 商品分类路径列表 (字符串数组)。
*   `browse_nodes` (array, 可选): 亚马逊浏览节点信息列表 (对象数组，每个对象应包含 'id' 和 'name' 等键)。
*   `features` (array, 可选): 商品特性列表 (字符串数组)。
*   `cj_url` (string, 可选): CJ 推广链接。
*   `api_provider` (string, 可选): API 提供者标识 (例如 "pa-api", "cj-api", "manual")。默认为 "manual"。
*   `source` (string, 可选): 数据来源标识 (例如 "bestseller", "coupon", "manual")。默认为 "manual"。
*   `coupon_expiration_date` (string, 可选): 优惠券过期日期 (ISO 8601 格式)。
*   `coupon_terms` (string, 可选): 优惠券使用条款。
*   `raw_data` (object, 可选): 包含原始数据的 JSON 对象。如果提供，将直接存储；否则，将基于输入信息生成。

**请求示例:**

```json
{
  "asin": "B0TESTMANUAL",
  "title": "手动添加的测试商品",
  "url": "https://www.amazon.com/dp/B0TESTMANUAL",
  "brand": "ManualBrand",
  "main_image": "https://example.com/image.jpg",
  "offers": [
    {
      "condition": "New",
      "price": 99.99,
      "original_price": 129.99,
      "currency": "USD",
      "savings": 30.00,
      "savings_percentage": 23,
      "is_prime": true,
      "availability": "In Stock",
      "merchant_name": "Manual Seller",
      "is_buybox_winner": true,
      "coupon_type": "percentage",
      "coupon_value": 10
    }
  ],
  "timestamp": "2024-10-27T10:00:00Z",
  "binding": "Electronics",
  "product_group": "Test Products",
  "categories": ["Electronics", "Test Category"],
  "browse_nodes": [{"id": "12345", "name": "Test Node"}],
  "features": ["手动添加", "高品质"],
  "source": "manual_import",
  "api_provider": "manual",
  "coupon_expiration_date": "2024-12-31T23:59:59Z",
  "coupon_terms": "满100可用"
}
```

### 成功响应

*   **状态码:** `201 Created`
*   **响应体:** 返回一个与请求体结构相同的 `ProductInfo` JSON 对象，包含已创建商品的所有信息（可能包含由服务器生成的默认值或时间戳）。

**响应示例:**

```json
{
  "asin": "B0TESTMANUAL",
  "title": "手动添加的测试商品",
  "url": "https://www.amazon.com/dp/B0TESTMANUAL",
  "brand": "ManualBrand",
  "main_image": "https://example.com/image.jpg",
  "offers": [
    {
      "condition": "New",
      "price": 99.99,
      "original_price": 129.99,
      "currency": "USD",
      "savings": 30.00,
      "savings_percentage": 23,
      "is_prime": true,
      "is_amazon_fulfilled": false,
      "is_free_shipping_eligible": false,
      "availability": "In Stock",
      "merchant_name": "Manual Seller",
      "is_buybox_winner": true,
      "deal_type": null,
      "coupon_type": "percentage",
      "coupon_value": 10,
      "coupon_history": [
        {
          "id": 1,
          "product_id": "B0TESTMANUAL",
          "coupon_type": "percentage",
          "coupon_value": 10.0,
          "expiration_date": "2024-12-31T23:59:59+00:00",
          "terms": "满100可用",
          "updated_at": "2024-10-28T12:34:56.789Z"
        }
      ],
      "commission": null
    }
  ],
  "timestamp": "2024-10-27T10:00:00+00:00",
  "coupon_info": null,
  "binding": "Electronics",
  "product_group": "Test Products",
  "categories": ["Electronics", "Test Category"],
  "browse_nodes": [{"id": "12345", "name": "Test Node"}],
  "features": ["手动添加", "高品质"],
  "cj_url": null,
  "api_provider": "manual",
  "source": "manual_import",
  "raw_data": "{\"asin\": \"B0TESTMANUAL\", ...}",
  "coupon_expiration_date": "2024-12-31T23:59:59+00:00",
  "coupon_terms": "满100可用",
  "coupon_history": {
      "id": 1,
      "product_id": "B0TESTMANUAL",
      "coupon_type": "percentage",
      "coupon_value": 10.0,
      "expiration_date": "2024-12-31T23:59:59+00:00",
      "terms": "满100可用",
      "updated_at": "2024-10-28T12:34:56.789Z"
  }
}
```

### 错误响应

*   **状态码:** `400 Bad Request`
    *   **原因:** 请求体 JSON 格式无效，或 `ProductInfo` 模型验证失败（例如缺少必需字段 `asin`, `title`, `url`, `offers` 或 `offers` 为空数组）。
    *   **响应体:**
        ```json
        {
          "detail": "具体的验证错误信息，例如 '必须至少提供一个商品优惠信息 (offer)。'"
        }
        ```
*   **状态码:** `409 Conflict`
    *   **原因:** 提供的 `asin` 已存在于数据库中。
    *   **响应体:**
        ```json
        {
          "detail": "ASIN B0TESTMANUAL 已存在，无法手动创建。"
        }
        ```
*   **状态码:** `500 Internal Server Error`
    *   **原因:** 服务器在处理请求时发生内部错误（例如数据库操作失败）。
    *   **响应体:**
        ```json
        {
          "detail": "手动添加商品失败: 具体的错误信息"
        }
        ```

### 示例 CURL 请求

```bash
curl -X POST "http://your-server/api/products/manual" \
-H "Content-Type: application/json" \
-d '{
  "asin": "B0NEWITEM123",
  "title": "另一个手动添加的商品",
  "url": "https://www.amazon.com/dp/B0NEWITEM123",
  "brand": "NewBrand",
  "offers": [
    {
      "condition": "New",
      "price": 49.95,
      "currency": "USD",
      "availability": "Usually ships within 3 days",
      "merchant_name": "Direct Seller"
    }
  ],
  "features": ["特性1", "特性2"]
}'
```

## 2. 编辑/更新商品

### 端点

`PUT /api/products/{asin}`

### 描述

此 API 允许用户更新已存在商品的信息。通过提供完整的商品信息（遵循 `ProductInfo` 模型）来更新指定 ASIN 的商品记录。

### 路径参数

*   `asin` (string, **必需**): 要更新的商品的 ASIN。必须为 10 个字符。

### 请求体

请求体必须是一个有效的 JSON 对象，其结构符合 `models.product.ProductInfo` 模型。所有字段的要求与添加商品 API 相同。

**重要说明:**
- 请求体中的 `asin` 必须与 URL 路径中的 `asin` 完全一致。
- 所有字段都将被更新，即使请求中未提供某些可选字段，它们也会被更新为 null 或默认值。
- 如果需要保留某些字段的现有值，请先获取商品当前信息，然后在请求中包含这些值。

**请求示例:**

```json
{
  "asin": "B0TESTMANUAL",
  "title": "更新后的测试商品标题",
  "url": "https://www.amazon.com/dp/B0TESTMANUAL",
  "brand": "UpdatedBrand",
  "main_image": "https://example.com/new-image.jpg",
  "offers": [
    {
      "condition": "New",
      "price": 89.99,
      "original_price": 129.99,
      "currency": "USD",
      "savings": 40.00,
      "savings_percentage": 31,
      "is_prime": true,
      "availability": "In Stock",
      "merchant_name": "Updated Seller",
      "is_buybox_winner": true,
      "coupon_type": "fixed",
      "coupon_value": 15
    }
  ],
  "timestamp": "2024-10-28T15:00:00Z",
  "binding": "Electronics",
  "product_group": "Updated Products",
  "categories": ["Electronics", "Updated Category"],
  "browse_nodes": [{"id": "12345", "name": "Updated Node"}],
  "features": ["更新的特性1", "更新的特性2", "新增特性"],
  "source": "manual_update",
  "api_provider": "manual",
  "coupon_expiration_date": "2025-01-31T23:59:59Z",
  "coupon_terms": "满80可用，新用户专享"
}
```

### 成功响应

*   **状态码:** `200 OK`
*   **响应体:** 返回一个与请求体结构相同的 `ProductInfo` JSON 对象，包含已更新商品的所有信息。

**响应示例:**

```json
{
  "asin": "B0TESTMANUAL",
  "title": "更新后的测试商品标题",
  "url": "https://www.amazon.com/dp/B0TESTMANUAL",
  "brand": "UpdatedBrand",
  "main_image": "https://example.com/new-image.jpg",
  "offers": [
    {
      "condition": "New",
      "price": 89.99,
      "original_price": 129.99,
      "currency": "USD",
      "savings": 40.00,
      "savings_percentage": 31,
      "is_prime": true,
      "is_amazon_fulfilled": false,
      "is_free_shipping_eligible": false,
      "availability": "In Stock",
      "merchant_name": "Updated Seller",
      "is_buybox_winner": true,
      "deal_type": null,
      "coupon_type": "fixed",
      "coupon_value": 15,
      "commission": null
    }
  ],
  "timestamp": "2024-10-28T15:00:00+00:00",
  "coupon_info": null,
  "binding": "Electronics",
  "product_group": "Updated Products",
  "categories": ["Electronics", "Updated Category"],
  "browse_nodes": [{"id": "12345", "name": "Updated Node"}],
  "features": ["更新的特性1", "更新的特性2", "新增特性"],
  "cj_url": null,
  "api_provider": "manual",
  "source": "manual_update",
  "raw_data": "{\"asin\": \"B0TESTMANUAL\", ...}",
  "coupon_expiration_date": "2025-01-31T23:59:59+00:00",
  "coupon_terms": "满80可用，新用户专享",
  "coupon_history": {
      "id": 2,
      "product_id": "B0TESTMANUAL",
      "coupon_type": "fixed",
      "coupon_value": 15.0,
      "expiration_date": "2025-01-31T23:59:59+00:00",
      "terms": "满80可用，新用户专享",
      "updated_at": "2024-10-28T15:00:00.000Z"
  }
}
```

### 错误响应

*   **状态码:** `400 Bad Request`
    *   **原因:** 
        - 请求体 JSON 格式无效
        - `ProductInfo` 模型验证失败
        - 请求体中的 ASIN 与 URL 中的 ASIN 不一致
    *   **响应体:**
        ```json
        {
          "detail": "具体的验证错误信息"
        }
        ```
*   **状态码:** `404 Not Found`
    *   **原因:** 指定的 ASIN 不存在于数据库中。
    *   **响应体:**
        ```json
        {
          "detail": "未找到ASIN为 B0TESTMANUAL 的商品"
        }
        ```
*   **状态码:** `500 Internal Server Error`
    *   **原因:** 服务器在处理请求时发生内部错误（例如数据库操作失败）。
    *   **响应体:**
        ```json
        {
          "detail": "更新商品失败: 具体的错误信息"
        }
        ```

### 示例 CURL 请求

```bash
curl -X PUT "http://your-server/api/products/B0TESTMANUAL" \
-H "Content-Type: application/json" \
-d '{
  "asin": "B0TESTMANUAL",
  "title": "价格调整后的商品",
  "url": "https://www.amazon.com/dp/B0TESTMANUAL",
  "brand": "UpdatedBrand",
  "offers": [
    {
      "condition": "New",
      "price": 79.99,
      "original_price": 99.99,
      "currency": "USD",
      "savings": 20.00,
      "savings_percentage": 20,
      "availability": "Limited Stock",
      "merchant_name": "Official Store"
    }
  ],
  "features": ["更新特性1", "更新特性2"]
}'
```

## 最佳实践

1. **添加商品前检查**: 在添加新商品前，建议先使用查询 API 检查 ASIN 是否已存在。
2. **完整更新**: 更新商品时，建议先获取商品当前的完整信息，修改需要更新的字段后再提交，以避免丢失其他字段的数据。
3. **优惠券历史**: 系统会自动记录优惠券的变化历史。每次更新优惠券信息时，如果有变化，会创建新的历史记录。
4. **时间戳**: 如果不提供 `timestamp` 字段，系统会自动使用当前时间。
5. **数据验证**: 确保所有必需字段都有有效值，特别是 `offers` 数组至少要包含一个有效的优惠信息。 