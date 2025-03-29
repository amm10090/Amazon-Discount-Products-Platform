# Amazon折扣产品平台API文档

欢迎使用Amazon折扣产品平台API文档。本文档提供了平台所有可用API的详细信息和使用说明。

## 可用API文档

- [产品搜索API](./product_search_api.md) - 通过关键词搜索产品
- [商品查询API](./product_query_api.md) - 通过ASIN批量查询商品详情
- 产品列表API - 获取折扣/优惠券商品列表
- 产品详情API - 获取单个产品的详细信息
- 品牌统计API - 获取品牌相关统计数据
- 类别统计API - 获取商品类别统计数据

## 快速开始

所有API都是RESTful风格，返回JSON格式的数据。API端点的基础URL为：

```
http://your-server/api
```

大多数API支持以下通用参数：

- `page`: 页码，默认为1
- `page_size`: 每页数量，默认和最大值因API而异

## 认证

目前，API不需要认证即可访问。未来可能会添加API密钥认证机制。

## 错误处理

所有API使用标准HTTP状态码表示请求状态，并在响应体中提供详细的错误信息。

## 贡献

如果您发现文档中的错误或有改进建议，请提交Issue或Pull Request。 