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
        "cache_type_distribution": "缓存类型分布",
        "cache_status": "缓存状态",
        "cache_health": "健康状态",
        "cleanup_status": "清理状态",
        "last_cleanup": "最后清理时间",
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
        "no_matching_products": "暂无符合条件的商品数据",
        
        # 调度器相关
        "scheduler_title": "定时任务管理",
        "add_new_job": "添加新任务",
        "job_id": "任务ID",
        "job_id_help": "任务的唯一标识符，例如：bestseller_daily",
        "job_type": "任务类型",
        "job_type_help": "cron: 按时间点执行，interval: 按时间间隔执行",
        "crawler_type": "爬虫类型",
        "crawler_type_help": "选择要执行的爬虫类型",
        "hour": "小时",
        "hour_help": "cron任务的小时设置，例如：*/4 表示每4小时执行一次",
        "minute": "分钟",
        "minute_help": "cron任务的分钟设置，例如：30 表示在30分时执行",
        "interval_hours": "间隔（小时）",
        "interval_minutes": "间隔（分钟）",
        "add_job": "添加任务",
        "job_added": "任务添加成功！",
        "add_job_failed": "添加任务失败",
        
        "existing_jobs": "现有任务",
        "no_jobs": "暂无定时任务",
        "schedule": "执行计划",
        "interval": "执行间隔",
        "next_run": "下次执行时间",
        "resume": "恢复",
        "pause": "暂停",
        "delete": "删除",
        "delete_all": "批量删除",
        "confirm_delete": "确认要删除这个商品吗？",
        "confirm_delete_all": "确认要删除所有显示的商品吗？此操作不可恢复！",
        "delete_success": "商品删除成功",
        "delete_failed": "删除商品失败",
        "batch_delete_success": "成功删除 {success_count} 个商品",
        "batch_delete_failed": "删除 {fail_count} 个商品失败",
        "job_resumed": "任务已恢复",
        "job_paused": "任务已暂停",
        "job_deleted": "任务已删除",
        
        "show_history": "显示执行历史",
        "no_history": "暂无执行历史",
        
        "scheduler_status": "调度器状态",
        "running_jobs": "运行中任务",
        "total_jobs": "总任务数",
        "timezone": "时区",
        "stop_scheduler": "停止调度器",
        "start_scheduler": "启动调度器",
        "reload_scheduler": "重新加载",
        "scheduler_stopped": "调度器已停止",
        "scheduler_started": "调度器已启动",
        "scheduler_reloaded": "调度器已重新加载",
        
        # 任务状态
        "status_running": "运行中",
        "status_completed": "已完成",
        "status_failed": "失败",
        "status_paused": "已暂停",
        
        # 爬虫类型
        "crawler_bestseller": "畅销商品",
        "crawler_coupon": "优惠券商品",
        "crawler_all": "全部商品",
        
        # 调度器相关
        "start_time": "开始时间",
        "end_time": "结束时间",
        "items_collected": "采集数量",
        "error": "错误信息",
        "save": "保存",
        "seconds": "秒",
        "price_low_to_high": "价格从低到高",
        "price_high_to_low": "价格从高到低",
        "discount_low_to_high": "折扣从低到高",
        "discount_high_to_low": "折扣从高到低",
        "time_old_to_new": "时间从早到晚",
        "time_new_to_old": "时间从晚到早",
        
        # 时区设置
        "timezone_settings": "时区设置",
        "select_timezone": "选择时区",
        "timezone_help": "选择显示时间的时区，所有时间将按照所选时区显示",
        "update_timezone": "更新时区",
        "timezone_updated": "时区更新成功！",
        "update_timezone_failed": "更新时区失败",
        "current_timezone": "当前时区",
        
        "price_unavailable": "暂无价格",
        
        # 调度器相关
        "execute_now": "立即执行",
        "job_started": "任务已开始执行",
        "job_execution_failed": "任务执行失败",
        
        # 新增翻译
        "discount_products": "折扣商品",
        "coupon_products": "优惠券商品",
        "product_list": "商品列表",
        "product_count": "商品数量",
        
        # 优惠券分析
        "coupon_analysis": "优惠券分析",
        "coupon_type_distribution": "优惠券类型分布",
        "coupon_value_distribution": "优惠券金额分布",
        "coupon_stats": "优惠券统计",
        "total_coupons": "优惠券总数",
        "percentage_coupons": "百分比优惠券",
        "fixed_coupons": "固定金额优惠券",
        "coupon_value": "优惠券金额",
        "coupon_value_stats": "优惠券金额统计",
        "min_value": "最小金额",
        "max_value": "最大金额",
        "avg_value": "平均金额",
        "median_value": "中位金额",
        "coupon_price_analysis": "优惠券与价格关系分析",
        "coupon_price_relation": "优惠券类型与商品价格关系",
        "coupon_value_price_relation": "优惠券金额与商品价格关系",
        "no_coupon_data": "暂无优惠券数据",
        "no_coupon_value_data": "暂无优惠券金额数据",
        "no_coupon_price_data": "暂无优惠券价格关系数据",
        "no_coupon_value_price_data": "暂无优惠券金额与价格关系数据",
        "coupon_type": "优惠券类型",
        
        # 缓存相关
        "cache_stats": "缓存统计",
        "cache_files": "总文件数",
        "cache_size": "总大小",
        "cache_type_distribution": "缓存类型分布",
        "cache_status": "缓存状态",
        "cache_health": "健康状态",
        "cleanup_status": "清理状态",
        "last_cleanup": "最后清理时间",
        "clear_cache": "清理缓存",
        "cache_cleared": "缓存已成功清理",
        "cache_clear_failed": "清理缓存失败",
        "loading_failed": "加载数据失败",
        "size": "大小",
        "files": "文件数",
        
        # 商品分类相关
        "product_category": "商品分类",
        "product_binding": "商品类型",
        "product_group": "商品分组",
        "categories": "分类",
        "browse_nodes": "浏览节点",
        "category_path": "分类路径",
        "category_breadcrumb": "分类导航",
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
        "cache_files": "Total Files",
        "cache_size": "Total Size",
        "cache_type_distribution": "Cache Type Distribution",
        "cache_status": "Cache Status",
        "cache_health": "Health Status",
        "cleanup_status": "Cleanup Status",
        "last_cleanup": "Last Cleanup Time",
        "clear_cache": "Clear Cache",
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
        "no_matching_products": "No products match the filter conditions",
        
        # Scheduler Related
        "scheduler_title": "Task Scheduler",
        "add_new_job": "Add New Task",
        "job_id": "Task ID",
        "job_id_help": "Unique identifier for the task, e.g., bestseller_daily",
        "job_type": "Task Type",
        "job_type_help": "cron: execute at specific times, interval: execute at intervals",
        "crawler_type": "Crawler Type",
        "crawler_type_help": "Select the type of crawler to execute",
        "hour": "Hour",
        "hour_help": "Hour setting for cron task, e.g., */4 means every 4 hours",
        "minute": "Minute",
        "minute_help": "Minute setting for cron task, e.g., 30 means at minute 30",
        "interval_hours": "Interval (Hours)",
        "interval_minutes": "Interval (Minutes)",
        "add_job": "Add Task",
        "job_added": "Task added successfully!",
        "add_job_failed": "Failed to add task",
        
        "existing_jobs": "Existing Tasks",
        "no_jobs": "No scheduled tasks",
        "schedule": "Schedule",
        "interval": "Interval",
        "next_run": "Next Run Time",
        "resume": "Resume",
        "pause": "Pause",
        "delete": "Delete",
        "delete_all": "Delete All",
        "confirm_delete": "Are you sure you want to delete this product?",
        "confirm_delete_all": "Are you sure you want to delete all displayed products? This action cannot be undone!",
        "delete_success": "Product deleted successfully",
        "delete_failed": "Failed to delete product",
        "batch_delete_success": "Successfully deleted {success_count} products",
        "batch_delete_failed": "Failed to delete {fail_count} products",
        "job_resumed": "Task resumed",
        "job_paused": "Task paused",
        "job_deleted": "Task deleted",
        
        "show_history": "Show History",
        "no_history": "No execution history",
        
        "scheduler_status": "Scheduler Status",
        "running_jobs": "Running Tasks",
        "total_jobs": "Total Tasks",
        "timezone": "Timezone",
        "stop_scheduler": "Stop Scheduler",
        "start_scheduler": "Start Scheduler",
        "reload_scheduler": "Reload",
        "scheduler_stopped": "Scheduler stopped",
        "scheduler_started": "Scheduler started",
        "scheduler_reloaded": "Scheduler reloaded",
        
        # Task Status
        "status_running": "Running",
        "status_completed": "Completed",
        "status_failed": "Failed",
        "status_paused": "Paused",
        
        # Crawler Types
        "crawler_bestseller": "Bestseller Products",
        "crawler_coupon": "Coupon Products",
        "crawler_all": "All Products",
        
        # Scheduler Related
        "start_time": "Start Time",
        "end_time": "End Time",
        "items_collected": "Items Collected",
        "error": "Error",
        "save": "Save",
        "seconds": "seconds",
        "price_low_to_high": "Price: Low to High",
        "price_high_to_low": "Price: High to Low",
        "discount_low_to_high": "Discount: Low to High",
        "discount_high_to_low": "Discount: High to Low",
        "time_old_to_new": "Time: Old to New",
        "time_new_to_old": "Time: New to Old",
        
        # Timezone Settings
        "timezone_settings": "Timezone Settings",
        "select_timezone": "Select Timezone",
        "timezone_help": "Select the timezone for displaying times, all times will be shown in the selected timezone",
        "update_timezone": "Update Timezone",
        "timezone_updated": "Timezone updated successfully!",
        "update_timezone_failed": "Failed to update timezone",
        "current_timezone": "Current Timezone",
        
        "price_unavailable": "Price unavailable",
        
        # Scheduler Related
        "execute_now": "Execute Now",
        "job_started": "Task execution started",
        "job_execution_failed": "Task execution failed",
        
        # 新增翻译
        "discount_products": "Discount Products",
        "coupon_products": "Coupon Products",
        "product_list": "Product List",
        "product_count": "Product Count",
        
        # Coupon Analysis
        "coupon_analysis": "Coupon Analysis",
        "coupon_type_distribution": "Coupon Type Distribution",
        "coupon_value_distribution": "Coupon Value Distribution",
        "coupon_stats": "Coupon Statistics",
        "total_coupons": "Total Coupons",
        "percentage_coupons": "Percentage Coupons",
        "fixed_coupons": "Fixed Amount Coupons",
        "coupon_value": "Coupon Value",
        "coupon_value_stats": "Coupon Value Statistics",
        "min_value": "Minimum Value",
        "max_value": "Maximum Value",
        "avg_value": "Average Value",
        "median_value": "Median Value",
        "coupon_price_analysis": "Coupon & Price Analysis",
        "coupon_price_relation": "Coupon Type vs Product Price",
        "coupon_value_price_relation": "Coupon Value vs Product Price",
        "no_coupon_data": "No coupon data available",
        "no_coupon_value_data": "No coupon value data available",
        "no_coupon_price_data": "No coupon price relation data available",
        "no_coupon_value_price_data": "No coupon value and price relation data available",
        "coupon_type": "Coupon Type",
        
        # 缓存相关
        "cache_stats": "Cache Statistics",
        "cache_files": "Total Files",
        "cache_size": "Total Size",
        "cache_type_distribution": "Cache Type Distribution",
        "cache_status": "Cache Status",
        "cache_health": "Health Status",
        "cleanup_status": "Cleanup Status",
        "last_cleanup": "Last Cleanup Time",
        "clear_cache": "Clear Cache",
        "cache_cleared": "Cache cleared successfully",
        "cache_clear_failed": "Failed to clear cache",
        "loading_failed": "Failed to load data",
        "size": "Size",
        "files": "Files",
        
        # 商品分类相关
        "product_category": "Product Category",
        "product_binding": "Product Type",
        "product_group": "Product Group",
        "categories": "Categories",
        "browse_nodes": "Browse Nodes",
        "category_path": "Category Path",
        "category_breadcrumb": "Category Navigation",
    }
} 