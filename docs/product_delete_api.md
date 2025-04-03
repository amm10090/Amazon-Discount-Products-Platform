# 商品批量删除API

本文档描述了批量删除商品的API接口，该接口支持删除单个或多个商品。

## API端点

```
POST /api/products/batch-delete
```

## 请求格式

请求体应为JSON格式，包含以下字段：

| 字段名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| asins | Array[String] | 是 | 要删除的商品ASIN列表 |

### 示例请求

#### 删除多个商品
```json
{
  "asins": ["B0ABCDEFGH", "B0HIJKLMNO", "B0PQRSTUVW"]
}
```

#### 删除单个商品
```json
{
  "asins": ["B0ABCDEFGH"]
}
```

## 响应格式

响应为JSON格式，包含以下字段：

| 字段名 | 类型 | 描述 |
|-------|------|------|
| status | String | 请求状态，成功为"success" |
| message | String | 操作结果描述 |
| success_count | Integer | 成功删除的商品数量 |
| fail_count | Integer | 删除失败的商品数量 |

### 示例响应

```json
{
  "status": "success", 
  "message": "批量删除完成",
  "success_count": 3,
  "fail_count": 0
}
```

## 错误响应

当请求处理失败时，API将返回HTTP 500状态码和详细的错误信息：

```json
{
  "detail": "批量删除失败: <错误详情>"
}
```

## 使用场景

1. 删除过期或不再需要的商品数据
2. 清理无效的商品信息
3. 管理产品数据库，移除不符合要求的商品

## 注意事项

1. 删除操作是不可逆的，请谨慎操作
2. 建议先备份重要数据再执行批量删除
3. 系统会自动处理相关联的商品信息（如优惠、变体等）
4. 每次请求的ASIN数量建议不超过100个，以避免请求超时 