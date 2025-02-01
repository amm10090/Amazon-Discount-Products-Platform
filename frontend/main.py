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
        response = requests.get(f"{api_url}/api/health", timeout=5)
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
        
        # 显示各类型缓存使用情况
        if cache_stats.get("by_type"):
            st.markdown("### " + get_text("cache_type_distribution"))
            for cache_type, stats in cache_stats["by_type"].items():
                with st.container():
                    st.markdown(f"""
                    **{cache_type}**:
                    - {get_text("size")}: {stats['size_mb']:.1f}MB
                    - {get_text("files")}: {stats['count']}
                    """)
        
        # 显示缓存状态
        if cache_stats.get("status_details"):
            st.markdown("### " + get_text("cache_status"))
            status_details = cache_stats["status_details"]
            st.markdown(f"""
            - {get_text("cache_health")}: {status_details['cache_health']}
            - {get_text("cleanup_status")}: {'运行中' if status_details['is_cleanup_running'] else '已停止'}
            - {get_text("last_cleanup")}: {cache_stats.get('last_cleanup', '未知')}
            """)
        
        # 清理缓存按钮
        if st.button("🧹 " + get_text("clear_cache")):
            response = requests.post(f"{api_url}/api/cache/clear")
            if response.status_code == 200:
                st.success(get_text("cache_cleared"))
                st.rerun()
            else:
                st.error(get_text("cache_clear_failed"))
    except Exception as e:
        st.warning(get_text("loading_failed"))

# 主页面
st.title(get_text("nav_home"))

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

# 数据统计区域
st.markdown("---")
st.subheader("📈 " + get_text("nav_analysis"))

# 加载统计数据
@st.cache_data(ttl=300)
def load_stats():
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(f"{api_url}/api/products/stats", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# 加载优惠券数据
@st.cache_data(ttl=300)
def load_coupon_stats():
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(
            f"{api_url}/api/products/list",
            params={"product_type": "coupon", "page_size": 1000},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# 显示统计信息
stats = load_stats()
if stats:
    # 关键指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container():
            st.metric(
                get_text("total_items"),
                f"{stats.get('total_products', 0):,}",
                help="商品总数"
            )
    with col2:
        with st.container():
            st.metric(
                get_text("avg_price"),
                f"${stats.get('avg_price', 0):.2f}",
                help="平均价格"
            )
    with col3:
        with st.container():
            st.metric(
                get_text("discount_stats"),
                f"{stats.get('avg_discount', 0):.1f}%",
                help="平均折扣率"
            )
    with col4:
        with st.container():
            st.metric(
                "Prime",
                f"{stats.get('prime_products', 0):,}",
                help="Prime商品数量"
            )
    
    # 详细统计
    st.markdown("### 📊 " + get_text("product_list"))
    col1, col2 = st.columns(2)
    
    with col1:
        with st.container():
            # 价格统计
            if all(key in stats for key in ['min_price', 'max_price', 'avg_price']):
                st.markdown(f"""
                💰 {get_text('price_range')}:
                - {get_text('min_price')}: ${stats['min_price']:.2f}
                - {get_text('max_price')}: ${stats['max_price']:.2f}
                - {get_text('avg_price')}: ${stats['avg_price']:.2f}
                """)
            else:
                st.info(get_text('price_unavailable'))
            
            # 折扣统计
            if all(key in stats for key in ['min_discount', 'max_discount', 'avg_discount']):
                st.markdown(f"""
                🏷️ {get_text('discount_distribution')}:
                - {get_text('min_discount')}: {stats['min_discount']}%
                - {get_text('max_discount')}: {stats['max_discount']}%
                - {get_text('avg_discount')}: {stats['avg_discount']:.1f}%
                """)
            else:
                st.info(get_text('no_discount_data'))
    
    with col2:
        coupon_data = load_coupon_stats()
        if coupon_data:
            percentage_coupons = sum(
                1 for p in coupon_data 
                if p['offers'] and p['offers'][0].get('coupon_type') == 'percentage'
            )
            fixed_coupons = sum(
                1 for p in coupon_data 
                if p['offers'] and p['offers'][0].get('coupon_type') == 'fixed'
            )
            
            st.markdown(f"""
            🎫 {get_text('coupon_stats')}:
            - {get_text('total_coupons')}: {len(coupon_data)}
            - {get_text('percentage_coupons')}: {percentage_coupons}
            - {get_text('fixed_coupons')}: {fixed_coupons}
            """)
        else:
            st.info(get_text('no_coupon_data'))
    
    # 更新时间
    if stats.get('last_update'):
        st.caption(f"{get_text('update_time')}: {stats['last_update']}")
else:
    st.error(get_text("loading_failed")) 