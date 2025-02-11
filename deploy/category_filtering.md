# 商品类别筛选功能文档 | Category Filtering Documentation

## 目录 | Table of Contents
1. [功能概述 | Overview](#功能概述--overview)
2. [API 参数说明 | API Parameters](#api-参数说明--api-parameters)
3. [使用方法 | Usage](#使用方法--usage)
4. [开发指南 | Development Guide](#开发指南--development-guide)
5. [示例代码 | Code Examples](#示例代码--code-examples)
6. [最佳实践 | Best Practices](#最佳实践--best-practices)
7. [常见问题 | FAQ](#常见问题--faq)

## 功能概述 | Overview

商品类别筛选功能支持通过以下三种维度进行商品筛选：
Category filtering supports product filtering through three dimensions:

- Browse Node IDs（浏览节点ID | Browse Node IDs）
- Bindings（商品绑定类型 | Product Binding Types）
- Product Groups（商品组 | Product Groups）

每种筛选维度都支持：
Each filtering dimension supports:

- 单个值筛选 | Single value filtering
- 多个值组合筛选 | Multiple value combination filtering
- 数组参数方式 | Array parameter method
- 逗号分隔的字符串方式 | Comma-separated string method

## API 参数说明 | API Parameters

### 1. browse_node_ids
- **描述 | Description**：Amazon商品分类节点ID | Amazon product category node ID
- **类型 | Type**：`Optional[Union[List[str], str]]`
- **示例值 | Example**：`13900821`（厨房用品 | Kitchen）, `510112`（吸尘器 | Vacuum）
- **支持格式 | Supported Formats**：
  - 数组格式 | Array format：`browse_node_ids=13900821&browse_node_ids=510112`
  - 字符串格式 | String format：`browse_node_ids=13900821,510112`

### 2. bindings
- **描述 | Description**：商品绑定类型 | Product binding type
- **类型 | Type**：`Optional[Union[List[str], str]]`
- **示例值 | Example**：`Kitchen`（厨房 | Kitchen）, `Electronics`（电子产品 | Electronics）
- **支持格式 | Supported Formats**：
  - 数组格式 | Array format：`bindings=Kitchen&bindings=Electronics`
  - 字符串格式 | String format：`bindings=Kitchen,Electronics`

### 3. product_groups
- **描述 | Description**：商品组 | Product group
- **类型 | Type**：`Optional[Union[List[str], str]]`
- **示例值 | Example**：`Home`（家居 | Home）, `Beauty`（美妆 | Beauty）
- **支持格式 | Supported Formats**：
  - 数组格式 | Array format：`product_groups=Home&product_groups=Beauty`
  - 字符串格式 | String format：`product_groups=Home,Beauty`

## 使用方法 | Usage

### 1. 单个类别筛选 | Single Category Filtering

```http
# 使用单个 Browse Node ID | Using single Browse Node ID
GET /api/products/list?browse_node_ids=13900821

# 使用单个商品绑定类型 | Using single binding type
GET /api/products/list?bindings=Kitchen

# 使用单个商品组 | Using single product group
GET /api/products/list?product_groups=Home
```

### 2. 多个类别组合筛选 | Multiple Category Combination Filtering

#### 数组参数方式 | Array Parameter Method：
```http
# Browse Node IDs
GET /api/products/list?browse_node_ids=13900821&browse_node_ids=510112

# 商品绑定类型 | Product binding types
GET /api/products/list?bindings=Kitchen&bindings=Electronics

# 商品组 | Product groups
GET /api/products/list?product_groups=Home&product_groups=Beauty
```

#### 逗号分隔字符串方式 | Comma-separated String Method：
```http
# Browse Node IDs
GET /api/products/list?browse_node_ids=13900821,510112

# 商品绑定类型 | Product binding types
GET /api/products/list?bindings=Kitchen,Electronics

# 商品组 | Product groups
GET /api/products/list?product_groups=Home,Beauty
```

### 3. 多维度组合筛选 | Multi-dimensional Combination Filtering

```http
# 组合使用多个筛选维度 | Combining multiple filtering dimensions
GET /api/products/list?browse_node_ids=13900821,510112&bindings=Kitchen,Electronics&product_groups=Home,Beauty
```

## 开发指南 | Development Guide

### 1. 参数处理逻辑 | Parameter Processing Logic

```python
# 处理 browse_node_ids 参数 | Processing browse_node_ids parameter
if browse_node_ids:
    if isinstance(browse_node_ids, str):
        # 处理逗号分隔的字符串 | Process comma-separated string
        if ',' in browse_node_ids:
            node_list = [n.strip() for n in browse_node_ids.split(",") if n.strip()]
        else:
            node_list = [browse_node_ids.strip()]
    elif isinstance(browse_node_ids, list):
        # 处理数组形式 | Process array format
        node_list = []
        for node_id in browse_node_ids:
            if isinstance(node_id, str) and ',' in node_id:
                node_list.extend([n.strip() for n in node_id.split(",") if n.strip()])
            else:
                node_list.append(str(node_id).strip())
```

### 2. SQL 查询构建 | SQL Query Construction

```python
# Browse Node IDs 查询条件 | Browse Node IDs query conditions
if browse_node_ids:
    browse_node_conditions = []
    for node_id in browse_node_ids:
        browse_node_conditions.append(
            Product.browse_nodes.like(f'%"id": "{node_id}"%')
        )
    if browse_node_conditions:
        query = query.filter(or_(*browse_node_conditions))

# Bindings 查询条件 | Bindings query conditions
if bindings:
    query = query.filter(Product.binding.in_(bindings))

# Product Groups 查询条件 | Product Groups query conditions
if product_groups:
    query = query.filter(Product.product_group.in_(product_groups))
```

## 示例代码 | Code Examples

### 前端调用示例 | Frontend Example

```javascript
// 使用 fetch API 调用 | Using fetch API
const fetchProducts = async (filters) => {
  const params = new URLSearchParams();
  
  // 添加 Browse Node IDs | Add Browse Node IDs
  if (filters.browseNodeIds) {
    filters.browseNodeIds.forEach(id => {
      params.append('browse_node_ids', id);
    });
  }
  
  // 添加 Bindings | Add Bindings
  if (filters.bindings) {
    params.append('bindings', filters.bindings.join(','));
  }
  
  // 添加 Product Groups | Add Product Groups
  if (filters.productGroups) {
    params.append('product_groups', filters.productGroups.join(','));
  }
  
  const response = await fetch(`/api/products/list?${params.toString()}`);
  return await response.json();
};
```

### Python 客户端调用示例 | Python Client Example

```python
import requests

def get_filtered_products(browse_node_ids=None, bindings=None, product_groups=None):
    params = {}
    
    if browse_node_ids:
        params['browse_node_ids'] = ','.join(browse_node_ids)
        
    if bindings:
        params['bindings'] = ','.join(bindings)
        
    if product_groups:
        params['product_groups'] = ','.join(product_groups)
        
    response = requests.get('http://localhost:5001/api/products/list', params=params)
    return response.json()
```

## 最佳实践 | Best Practices

1. **参数验证 | Parameter Validation**
   - 始终对输入参数进行清理和验证 | Always clean and validate input parameters
   - 移除空白字符 | Remove whitespace
   - 过滤掉空值 | Filter out empty values

2. **错误处理 | Error Handling**
   - 实现适当的错误处理机制 | Implement proper error handling mechanisms
   - 记录详细的错误日志 | Log detailed error messages
   - 返回友好的错误信息 | Return user-friendly error messages

3. **性能优化 | Performance Optimization**
   - 使用适当的索引 | Use appropriate indexes
   - 优化查询语句 | Optimize query statements
   - 实现缓存机制 | Implement caching mechanisms

4. **日志记录 | Logging**
   - 记录参数处理过程 | Log parameter processing
   - 记录查询执行情况 | Log query execution
   - 记录异常情况 | Log exceptions

## 常见问题 | FAQ

### 1. 参数格式问题 | Parameter Format Issues

**问题 | Problem**：传递的参数格式不正确 | Incorrect parameter format
**解决方案 | Solution**：
- 确保参数值不包含特殊字符 | Ensure parameter values don't contain special characters
- 正确编码 URL 参数 | Properly encode URL parameters
- 使用推荐的参数格式 | Use recommended parameter formats

### 2. 查询性能问题 | Query Performance Issues

**问题 | Problem**：类别组合查询性能较差 | Poor performance with category combination queries
**解决方案 | Solution**：
- 优化数据库索引 | Optimize database indexes
- 使用缓存机制 | Use caching mechanisms
- 限制查询范围 | Limit query scope

### 3. 空结果问题 | Empty Results Issues

**问题 | Problem**：查询返回空结果 | Query returns empty results
**解决方案 | Solution**：
- 检查参数值是否正确 | Check if parameter values are correct
- 确认数据库中是否存在相应数据 | Confirm if corresponding data exists in database
- 查看日志了解具体原因 | Check logs for specific reasons

### 4. 参数组合问题 | Parameter Combination Issues

**问题 | Problem**：多个筛选条件组合使用时出现问题 | Issues when combining multiple filtering conditions
**解决方案 | Solution**：
- 确保参数之间的逻辑关系正确 | Ensure correct logical relationships between parameters
- 检查参数处理逻辑 | Check parameter processing logic
- 验证 SQL 查询条件的正确性 | Verify SQL query conditions are correct 