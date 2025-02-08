import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import plotly.express as px
from i18n import init_language, get_text, language_selector
import yaml
import os
from pathlib import Path
from utils.cache_manager import cache_manager

@cache_manager.resource_cache(show_spinner=False)
def load_config(config_path: str = None) -> dict:
    """加载配置文件
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        dict: 配置字典
    """
    default_config = {
        "environment": "development",
        "frontend": {
            "host": "localhost",
            "port": 8501,
            "page": {
                "layout": "wide",
                "initial_sidebar_state": "expanded"
            },
            "theme": {
                "primaryColor": "#ff9900",
                "backgroundColor": "#ffffff",
                "secondaryBackgroundColor": "#f0f2f6",
                "textColor": "#31333F"
            },
            "cache": {
                "ttl": 300,
                "max_entries": 1000
            }
        },
        "api": {
            "host": "localhost",
            "port": 8000
        },
        "logging": {
            "level": "INFO",
            "max_size": 10485760,
            "backup_count": 5
        }
    }
    
    if not config_path:
        config_path = os.getenv("CONFIG_PATH", "config/production.yaml")
    
    try:
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return {**default_config, **config}
        else:
            st.warning(f"配置文件 {config_path} 不存在，使用默认配置")
            return default_config
    except Exception as e:
        st.error(f"加载配置文件失败: {e}")
        return default_config

@cache_manager.data_cache(show_spinner="正在检查API状态...")
def check_api_status(api_url: str) -> bool:
    """检查API服务状态
    
    Args:
        api_url: API服务地址
        
    Returns:
        bool: API服务是否正常运行
    """
    try:
        response = requests.get(f"{api_url}/api/health", timeout=5)
        return response.status_code == 200
    except:
        return False

@cache_manager.data_cache(show_spinner="正在加载缓存统计信息...")
def get_cache_stats(api_url: str) -> dict:
    """获取缓存统计信息
    
    Args:
        api_url: API服务地址
        
    Returns:
        dict: 缓存统计信息
    """
    try:
        response = requests.get(f"{api_url}/api/cache/stats")
        if response.status_code == 200:
            return response.json()
        return {}
    except:
        return {}

def clear_cache_data(api_url: str, clear_all: bool = False) -> dict:
    """清理PA-API缓存数据
    
    Args:
        api_url: API服务地址
        clear_all: 是否清理所有缓存
        
    Returns:
        dict: 清理结果
    """
    result = {
        "success": False,
        "message": ""
    }
    
    try:
        # 根据clear_all参数选择不同的API端点
        endpoint = "/api/cache/clear-all" if clear_all else "/api/cache/clear"
        response = requests.post(f"{api_url}{endpoint}")
        result["success"] = response.status_code == 200
        
        if result["success"]:
            result["message"] = "所有PA-API缓存已清理" if clear_all else "过期PA-API缓存已清理"
        else:
            result["message"] = "PA-API缓存清理失败"
            
        return result
    except Exception as e:
        result["message"] = f"PA-API缓存清理过程发生错误: {str(e)}"
        return result

def main():
    # 加载配置
    config = load_config()
    
    # 初始化语言设置
    init_language()
    
    # 设置页面配置
    st.set_page_config(
        page_title="Amazon优惠商品平台",
        page_icon="🛍️",
        layout=config["frontend"]["page"]["layout"],
        initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"],
        menu_items={
            'Get Help': 'https://github.com/yourusername/amazon-deals-platform',
            'Report a bug': "https://github.com/yourusername/amazon-deals-platform/issues",
            'About': "Amazon优惠商品平台 - 帮助用户发现和追踪Amazon平台上的优惠商品"
        }
    )
    
    # 自定义CSS样式
    st.markdown(f"""
    <style>
        .main {{
            padding: 0rem 1rem;
        }}
        .stButton>button {{
            width: 100%;
            background-color: {config["frontend"]["theme"]["primaryColor"]};
            color: white;
        }}
        .stProgress > div > div > div > div {{
            background-color: {config["frontend"]["theme"]["primaryColor"]};
        }}
        .css-1v0mbdj.ebxwdo61 {{
            width: 100%;
            max-width: 100%;
        }}
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            background-color: {config["frontend"]["theme"]["backgroundColor"]};
        }}
        .sidebar .sidebar-content {{
            background-color: {config["frontend"]["theme"]["secondaryBackgroundColor"]};
        }}
        body {{
            color: {config["frontend"]["theme"]["textColor"]};
        }}
        .metric-container {{
            background-color: {config["frontend"]["theme"]["secondaryBackgroundColor"]};
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 0.5rem 0;
        }}
        .info-container {{
            background-color: {config["frontend"]["theme"]["secondaryBackgroundColor"]};
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
        }}
        .stSpinner {{
            position: relative;
            display: inline-block;
            width: 1em;
            height: 1em;
        }}
        .stSpinner::before {{
            content: '';
            box-sizing: border-box;
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0.8em;
            height: 0.8em;
            margin-top: -0.4em;
            margin-left: -0.4em;
            border-radius: 50%;
            border: 2px solid {config["frontend"]["theme"]["primaryColor"]};
            border-top-color: transparent;
            animation: spinner .6s linear infinite;
        }}
        @keyframes spinner {{
            to {{transform: rotate(360deg);}}
        }}
    </style>
    """, unsafe_allow_html=True)
    
    # 侧边栏
    with st.sidebar:
        st.title("🛍️ " + get_text("nav_home"))
        st.markdown("---")
        
        # 语言选择器
        language_selector()
        st.markdown("---")
        
        # API状态检查
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        api_status = check_api_status(api_url)
        
        if api_status:
            st.success(get_text("api_running"))
        else:
            st.error(get_text("api_connection_error"))
        
        st.markdown("---")
        
        # 缓存统计
        with st.spinner(get_text("loading")):
            cache_stats = get_cache_stats(api_url)
            
            if cache_stats:
                st.subheader("📊 " + get_text("cache_stats"))
                
                # 使用columns布局显示关键指标
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        get_text("cache_files"),
                        cache_stats.get("total_files", 0)
                    )
                with col2:
                    st.metric(
                        get_text("cache_size"),
                        f"{cache_stats.get('total_size_mb', 0):.1f}MB"
                    )
                
                # 显示缓存类型分布
                if cache_stats.get("by_type"):
                    with st.expander(get_text("cache_type_distribution")):
                        for cache_type, stats in cache_stats["by_type"].items():
                            st.markdown(f"""
                            **{cache_type}**:
                            - {get_text("size")}: {stats['size_mb']:.1f}MB
                            - {get_text("files")}: {stats['count']}
                            """)
                
                # 显示缓存状态
                if cache_stats.get("status_details"):
                    with st.expander(get_text("cache_status")):
                        status_details = cache_stats["status_details"]
                        st.markdown(f"""
                        - {get_text("cache_health")}: {status_details['cache_health']}
                        - {get_text("cleanup_status")}: {'运行中' if status_details['is_cleanup_running'] else '已停止'}
                        - {get_text("last_cleanup")}: {cache_stats.get('last_cleanup', '未知')}
                        """)
                
                # 清理缓存按钮
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🧹 " + get_text("clear_expired_cache")):
                        with st.spinner(get_text("clearing_cache")):
                            result = clear_cache_data(api_url, clear_all=False)
                            if result["success"]:
                                st.success(result["message"])
                                st.rerun()
                            else:
                                st.error(result["message"])
                                
                with col2:
                    if st.button("🗑️ " + get_text("clear_all_cache")):
                        # 添加确认对话框
                        if st.warning(get_text("clear_all_cache_warning")):
                            with st.spinner(get_text("clearing_cache")):
                                result = clear_cache_data(api_url, clear_all=True)
                                if result["success"]:
                                    st.success(result["message"])
                                    st.rerun()
                                else:
                                    st.error(result["message"])
            else:
                st.warning(get_text("loading_failed"))
    
    # 主页面内容
    st.title(get_text("nav_home"))
    
    # 使用container组织相关内容
    with st.container():
        # 功能区块
        col1, col2, col3 = st.columns(3)
        
        with col1:
            with st.container():
                st.subheader("⏰ " + get_text("scheduler_title"))
                st.markdown(f"""
                - {get_text("add_new_job")}
                - {get_text("existing_jobs")}
                - {get_text("scheduler_status")}
                - {get_text("timezone_settings")}
                """)
                st.page_link("pages/scheduler.py", label=get_text("scheduler_title"), icon="⏰")
        
        with col2:
            with st.container():
                st.subheader("📊 " + get_text("nav_analysis"))
                st.markdown(f"""
                - {get_text("price_analysis")}
                - {get_text("discount_analysis")}
                - {get_text("prime_analysis")}
                - {get_text("coupon_analysis")}
                """)
                st.page_link("pages/analysis.py", label=get_text("nav_analysis"), icon="📊")
        
        with col3:
            with st.container():
                st.subheader("📦 " + get_text("nav_products"))
                st.markdown(f"""
                - {get_text("discount_products")}
                - {get_text("coupon_products")}
                - {get_text("view_details")}
                - {get_text("export_data")}
                """)
                st.page_link("pages/products.py", label=get_text("nav_products"), icon="📦")

if __name__ == "__main__":
    main() 