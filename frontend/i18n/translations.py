"""
多语言翻译配置
"""

TRANSLATIONS = {
    "zh": {
        # 通用
        "language": "语言",
        "chinese": "中文",
        "english": "English",
        
        # 导航
        "nav_home": "首页",
        "nav_crawler": "爬虫控制",
        "nav_analysis": "数据分析",
        "nav_products": "商品管理",
        
        # 系统状态
        "api_status": "API服务状态",
        "api_running": "API服务正常运行",
        "api_error": "API服务异常",
        "api_connection_error": "无法连接到API服务",
        
        # 缓存管理
        "cache_stats": "缓存统计",
        "cache_files": "缓存文件数",
        "cache_size": "缓存大小",
        "clear_cache": "清理过期缓存",
        "cache_cleared": "缓存清理成功",
        "cache_clear_failed": "缓存清理失败",
        
        # 爬虫控制
        "crawler_title": "爬虫控制面板",
        "crawler_config": "任务配置",
        "max_items": "爬取商品数量",
        "timeout": "超时时间（秒）",
        "output_format": "输出格式",
        "headless_mode": "使用无头模式",
        "start_crawler": "启动爬虫任务",
        "task_status": "任务状态",
        "task_id": "任务ID",
        "status": "状态",
        "total_items": "总商品数",
        "duration": "耗时",
        "download_results": "下载结果",
        
        # 数据分析
        "analysis_title": "数据分析",
        "price_analysis": "价格分析",
        "discount_analysis": "折扣分析",
        "prime_analysis": "Prime分析",
        "price_distribution": "商品价格分布",
        "price_stats": "价格统计",
        "min_price": "最低价格",
        "max_price": "最高价格",
        "avg_price": "平均价格",
        "median_price": "中位价格",
        "discount_distribution": "折扣率分布",
        "discount_stats": "折扣统计",
        "prime_ratio": "Prime商品占比",
        
        # 商品管理
        "products_title": "商品管理",
        "filter_conditions": "筛选条件",
        "price_range": "价格范围",
        "min_discount_rate": "最低折扣率",
        "prime_only": "只显示Prime商品",
        "sort_by": "排序方式",
        "items_per_page": "每页显示",
        "brand": "品牌",
        "save_money": "节省",
        "view_details": "查看商品详情",
        "update_time": "更新时间",
        "prev_page": "上一页",
        "next_page": "下一页",
        "page_info": "第 {current} 页 / 共 {total} 页",
        
        # 数据导出
        "export_data": "数据导出",
        "export_format": "选择导出格式",
        "export_button": "导出数据",
        "export_success": "数据导出成功！",
        "export_failed": "导出数据失败",
        "no_data": "没有数据可供导出",
        
        # 错误信息
        "loading_failed": "加载数据失败",
        "no_products": "暂无商品数据，请先运行爬虫任务采集数据。",
        "no_matching_products": "暂无符合条件的商品数据"
    },
    
    "en": {
        # General
        "language": "Language",
        "chinese": "中文",
        "english": "English",
        
        # Navigation
        "nav_home": "Home",
        "nav_crawler": "Crawler Control",
        "nav_analysis": "Data Analysis",
        "nav_products": "Product Management",
        
        # System Status
        "api_status": "API Service Status",
        "api_running": "API Service Running",
        "api_error": "API Service Error",
        "api_connection_error": "Cannot connect to API Service",
        
        # Cache Management
        "cache_stats": "Cache Statistics",
        "cache_files": "Cached Files",
        "cache_size": "Cache Size",
        "clear_cache": "Clear Expired Cache",
        "cache_cleared": "Cache cleared successfully",
        "cache_clear_failed": "Failed to clear cache",
        
        # Crawler Control
        "crawler_title": "Crawler Control Panel",
        "crawler_config": "Task Configuration",
        "max_items": "Number of Items",
        "timeout": "Timeout (seconds)",
        "output_format": "Output Format",
        "headless_mode": "Headless Mode",
        "start_crawler": "Start Crawler",
        "task_status": "Task Status",
        "task_id": "Task ID",
        "status": "Status",
        "total_items": "Total Items",
        "duration": "Duration",
        "download_results": "Download Results",
        
        # Data Analysis
        "analysis_title": "Data Analysis",
        "price_analysis": "Price Analysis",
        "discount_analysis": "Discount Analysis",
        "prime_analysis": "Prime Analysis",
        "price_distribution": "Price Distribution",
        "price_stats": "Price Statistics",
        "min_price": "Minimum Price",
        "max_price": "Maximum Price",
        "avg_price": "Average Price",
        "median_price": "Median Price",
        "discount_distribution": "Discount Distribution",
        "discount_stats": "Discount Statistics",
        "prime_ratio": "Prime Product Ratio",
        
        # Product Management
        "products_title": "Product Management",
        "filter_conditions": "Filter Conditions",
        "price_range": "Price Range",
        "min_discount_rate": "Minimum Discount Rate",
        "prime_only": "Prime Products Only",
        "sort_by": "Sort By",
        "items_per_page": "Items Per Page",
        "brand": "Brand",
        "save_money": "Save",
        "view_details": "View Details",
        "update_time": "Update Time",
        "prev_page": "Previous",
        "next_page": "Next",
        "page_info": "Page {current} of {total}",
        
        # Data Export
        "export_data": "Export Data",
        "export_format": "Export Format",
        "export_button": "Export Data",
        "export_success": "Data exported successfully!",
        "export_failed": "Failed to export data",
        "no_data": "No data available for export",
        
        # Error Messages
        "loading_failed": "Failed to load data",
        "no_products": "No product data available. Please run the crawler first.",
        "no_matching_products": "No products match the filter conditions"
    }
} 