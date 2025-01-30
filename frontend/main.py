import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import plotly.express as px
from i18n import init_language, get_text, language_selector
import yaml
import os
from pathlib import Path

def load_config(config_path: str = None) -> dict:
    """加载配置文件
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        dict: 配置字典
    """
    # 默认配置
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
                "backgroundColor": "#f0f0f0",
                "textColor": "#333333"
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
            print(f"配置文件 {config_path} 不存在，使用默认配置")
            return default_config
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return default_config

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
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(f"{api_url}/api/health")
        if response.status_code == 200:
            st.success(get_text("api_running"))
        else:
            st.error(get_text("api_error"))
    except:
        st.error(get_text("api_connection_error"))
    
    st.markdown("---")
    
    # 缓存统计
    try:
        cache_stats = requests.get(f"{api_url}/api/cache/stats").json()
        st.subheader("📊 " + get_text("cache_stats"))
        col1, col2 = st.columns(2)
        with col1:
            st.metric(get_text("cache_files"), cache_stats.get("total_files", 0))
        with col2:
            st.metric(get_text("cache_size"), f"{cache_stats.get('total_size_mb', 0):.1f}MB")
        
        # 清理缓存按钮
        if st.button("🧹 " + get_text("clear_cache")):
            response = requests.post(f"{api_url}/api/cache/clear")
            if response.status_code == 200:
                st.success(get_text("cache_cleared"))
            else:
                st.error(get_text("cache_clear_failed"))
    except:
        st.warning(get_text("loading_failed"))

# 主页面
st.title(get_text("nav_home"))

# 功能区块
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🔍 " + get_text("nav_crawler"))
    with st.container():
        st.markdown(f"""
        - {get_text("start_crawler")}
        - {get_text("task_status")}
        - {get_text("download_results")}
        """)
        st.page_link("pages/crawler.py", label=get_text("nav_crawler"), icon="🔍")

with col2:
    st.subheader("📊 " + get_text("nav_analysis"))
    with st.container():
        st.markdown(f"""
        - {get_text("price_analysis")}
        - {get_text("discount_analysis")}
        - {get_text("prime_analysis")}
        """)
        st.page_link("pages/analysis.py", label=get_text("nav_analysis"), icon="📊")

with col3:
    st.subheader("📦 " + get_text("nav_products"))
    with st.container():
        st.markdown(f"""
        - {get_text("products_title")}
        - {get_text("view_details")}
        - {get_text("export_data")}
        """)
        st.page_link("pages/products.py", label=get_text("nav_products"), icon="📦")

# 获取商品统计信息
try:
    stats = requests.get("http://localhost:8000/api/products/stats").json()
    
    st.markdown("---")
    st.subheader("📈 " + get_text("nav_analysis"))
    
    # 显示关键指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(get_text("total_items"), stats["total_products"])
    with col2:
        st.metric(get_text("avg_price"), f"${stats['avg_price']:.2f}")
    with col3:
        st.metric(get_text("discount_stats"), f"{stats['avg_discount']}%")
    with col4:
        st.metric("Prime", stats["prime_products"])
        
    # 价格区间分布
    price_range = stats["price_range"]
    st.markdown(f"💰 {get_text('price_range')}: ${price_range['min']:.2f} - ${price_range['max']:.2f}")
    
    # 折扣区间分布
    discount_range = stats["discount_range"]
    st.markdown(f"🏷️ {get_text('discount_distribution')}: {discount_range['min']}% - {discount_range['max']}%")
    
    # 更新时间
    st.caption(f"{get_text('update_time')}: {stats['last_update']}")
    
except Exception as e:
    st.warning(get_text("loading_failed"))
    st.caption(f"{get_text('error')}: {str(e)}") 