# Amazon Deals ASIN 爬虫

这是一个用于爬取 Amazon Deals 页面商品 ASIN 的自动化工具。

## 功能特点

- 自动爬取 Amazon Deals 页面的商品 ASIN
- 支持多种输出格式（TXT、CSV、JSON）
- 智能滚动和动态加载处理
- 自动处理连接问题和重试机制
- 默认使用无头模式运行
- 可配置的超时和目标数量
- 详细的进度和统计信息

## 环境要求

- Python 3.6+
- Chrome 浏览器
- 以下 Python 包：
  ```
  selenium
  webdriver_manager
  ```

## 安装

1. 克隆仓库：
   ```bash
   git clone <repository-url>
   cd amazon-deals-crawler
   ```

2. 安装依赖：
   ```bash
   pip install selenium webdriver-manager
   ```

3. 确保已安装 Chrome 浏览器

## 使用方法

### 基本用法

```bash
python amazon_bestseller.py
```

### 命令行参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| --max-items | 要爬取的商品数量 | 500 | --max-items 1000 |
| --output | 输出文件路径 | asin_list.txt | --output results.csv |
| --format | 输出格式(txt/csv/json) | txt | --format json |
| --no-headless | 禁用无头模式 | False | --no-headless |
| --timeout | 无新商品超时时间(秒) | 30 | --timeout 60 |

### 使用示例

1. 爬取1000个商品并保存为JSON格式：
   ```bash
   python amazon_bestseller.py --max-items 1000 --format json
   ```

2. 禁用无头模式运行（显示浏览器界面）：
   ```bash
   python amazon_bestseller.py --no-headless --output results/deals.csv --format csv
   ```

3. 自定义超时时间：
   ```bash
   python amazon_bestseller.py --timeout 60 --max-items 200
   ```

## 输出格式

### TXT 格式
```
B07XXXXX1
B07XXXXX2
B07XXXXX3
```

### CSV 格式
```csv
ASIN,Index
B07XXXXX1,1
B07XXXXX2,2
B07XXXXX3,3
```

### JSON 格式
```json
{
  "metadata": {
    "total_count": 500,
    "timestamp": "2025-01-25 16:38:21",
    "source": "amazon_deals"
  },
  "asins": [
    "B07XXXXX1",
    "B07XXXXX2",
    "B07XXXXX3"
  ]
}
```

## 代码结构

### 主要函数

- `parse_arguments()`: 命令行参数解析
- `save_results()`: 结果保存，支持多种格式
- `setup_driver()`: 配置 Selenium WebDriver
- `scroll_page()`: 智能滚动页面
- `handle_connection_problem()`: 处理连接问题
- `extract_asin_from_url()`: 从URL提取ASIN
- `crawl_deals()`: 主爬虫逻辑

## 性能优化

1. 禁用图片加载加快页面加载
2. 智能滚动算法避免无效滚动
3. 自动重试机制处理连接问题
4. 动态等待时间减少不必要的延迟

## 注意事项

1. 需要稳定的网络连接
2. 可能需要配置代理以避免 IP 限制
3. 建议不要设置过大的爬取数量
4. 遵守 Amazon 的使用条款和爬虫规则

## 常见问题

1. 如果遇到连接问题，脚本会自动重试
2. 无头模式可能在某些环境下不稳定
3. 输出目录不存在会自动创建

## 更新日志

### v1.0.0 (2025-01-25)
- 初始版本发布
- 支持基本的ASIN爬取功能
- 添加命令行参数支持
- 支持多种输出格式

## 待优化项

1. 添加代理支持
2. 实现断点续传
3. 添加更多的数据验证
4. 优化内存使用
5. 添加并发支持

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目。

## 许可证

MIT License 