import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from i18n import init_language, get_text, language_selector
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from main import load_config

# 加载配置
config = load_config()

# 初始化语言设置
init_language()

st.set_page_config(
    page_title=get_text("analysis_title"),
    page_icon="📊",
    layout=config["frontend"]["page"]["layout"],
    initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"]
)

# 自定义CSS
st.markdown(f"""
<style>
    .plot-container {{
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
    }}
    .stButton>button {{
        background-color: {config["frontend"]["theme"]["primaryColor"]};
        color: white;
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
    # 语言选择器
    language_selector()
    st.markdown("---")

st.title("📊 " + get_text("analysis_title"))

# 获取商品数据
@st.cache_data(ttl=config["frontend"]["cache"]["ttl"])
def load_products_data():
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(
            f"{api_url}/api/products/list",
            params={
                "page_size": config["frontend"]["cache"]["max_entries"],
                "product_type": "all"  # 获取所有类型的商品
            }
        )
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame([
                {
                    'asin': item['asin'],
                    'title': item['title'],
                    'price': item['offers'][0]['price'] if item['offers'] else None,
                    'savings_percentage': item['offers'][0]['savings_percentage'] if item['offers'] else None,
                    'is_prime': item['offers'][0]['is_prime'] if item['offers'] else False,
                    'coupon_type': item['offers'][0]['coupon_type'] if item['offers'] and 'coupon_type' in item['offers'][0] else None,
                    'coupon_value': item['offers'][0]['coupon_value'] if item['offers'] and 'coupon_value' in item['offers'][0] else None,
                    'timestamp': item['timestamp']
                }
                for item in data
            ])
            return df
        return None
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return None

# 加载数据
df = load_products_data()

if df is not None and not df.empty:
    # 数据预处理
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["savings_percentage"] = pd.to_numeric(df["savings_percentage"], errors="coerce")
    df["coupon_value"] = pd.to_numeric(df["coupon_value"], errors="coerce")
    
    # 创建分析选项卡
    tab1, tab2, tab3, tab4 = st.tabs([
        get_text("price_analysis"),
        get_text("discount_analysis"),
        get_text("prime_analysis"),
        "🎫 " + get_text("coupon_analysis")  # 新增优惠券分析选项卡
    ])
    
    with tab1:
        st.subheader("💰 " + get_text("price_analysis"))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 价格分布直方图
            fig_price_dist = px.histogram(
                df,
                x="price",
                nbins=30,
                title=get_text("price_distribution"),
                labels={
                    "price": get_text("price") + " ($)",
                    "count": get_text("product_count")
                },
                color_discrete_sequence=["#ff9900"]
            )
            fig_price_dist.update_layout(showlegend=False)
            st.plotly_chart(fig_price_dist, use_container_width=True)
            
            # 价格统计信息
            price_stats = df["price"].describe()
            st.markdown(f"""
            **{get_text("price_stats")}:**
            - {get_text("min_price")}: ${price_stats['min']:.2f}
            - {get_text("max_price")}: ${price_stats['max']:.2f}
            - {get_text("avg_price")}: ${price_stats['mean']:.2f}
            - {get_text("median_price")}: ${price_stats['50%']:.2f}
            """)
        
        with col2:
            # 价格箱线图
            fig_price_box = px.box(
                df,
                y="price",
                title=get_text("price_distribution"),
                labels={"price": get_text("price") + " ($)"},
                color_discrete_sequence=["#ff9900"]
            )
            st.plotly_chart(fig_price_box, use_container_width=True)
            
            # 价格区间分布
            price_bins = pd.cut(df["price"], bins=5)
            price_dist = price_bins.value_counts().sort_index()
            
            fig_price_range = px.bar(
                x=[f"${int(b.left)}-${int(b.right)}" for b in price_dist.index],
                y=price_dist.values,
                title=get_text("price_range_distribution"),
                labels={
                    "x": get_text("price_range"),
                    "y": get_text("product_count")
                },
                color_discrete_sequence=["#ff9900"]
            )
            st.plotly_chart(fig_price_range, use_container_width=True)
    
    with tab2:
        st.subheader("🏷️ " + get_text("discount_analysis"))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 折扣率分布直方图
            fig_discount_dist = px.histogram(
                df[df["savings_percentage"].notna()],
                x="savings_percentage",
                nbins=20,
                title=get_text("discount_distribution"),
                labels={
                    "savings_percentage": get_text("discount_rate") + " (%)",
                    "count": get_text("product_count")
                },
                color_discrete_sequence=["#ff9900"]
            )
            fig_discount_dist.update_layout(showlegend=False)
            st.plotly_chart(fig_discount_dist, use_container_width=True)
            
            # 折扣统计信息
            discount_stats = df["savings_percentage"].describe()
            st.markdown(f"""
            **{get_text("discount_stats")}:**
            - {get_text("min_discount")}: {discount_stats['min']:.1f}%
            - {get_text("max_discount")}: {discount_stats['max']:.1f}%
            - {get_text("avg_discount")}: {discount_stats['mean']:.1f}%
            - {get_text("median_discount")}: {discount_stats['50%']:.1f}%
            """)
        
        with col2:
            # 价格与折扣率散点图
            fig_price_discount = px.scatter(
                df[df["savings_percentage"].notna()],
                x="price",
                y="savings_percentage",
                title=get_text("price_discount_relation"),
                labels={
                    "price": get_text("price") + " ($)",
                    "savings_percentage": get_text("discount_rate") + " (%)"
                },
                color_discrete_sequence=["#ff9900"]
            )
            st.plotly_chart(fig_price_discount, use_container_width=True)
            
            # 折扣区间分布
            discount_bins = pd.cut(
                df["savings_percentage"].dropna(),
                bins=[0, 20, 40, 60, 80, 100]
            )
            discount_dist = discount_bins.value_counts().sort_index()
            
            fig_discount_range = px.bar(
                x=[f"{int(b.left)}-{int(b.right)}%" for b in discount_dist.index],
                y=discount_dist.values,
                title=get_text("discount_range_distribution"),
                labels={
                    "x": get_text("discount_range"),
                    "y": get_text("product_count")
                },
                color_discrete_sequence=["#ff9900"]
            )
            st.plotly_chart(fig_discount_range, use_container_width=True)
    
    with tab3:
        st.subheader("✨ " + get_text("prime_analysis"))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Prime商品比例
            prime_count = df["is_prime"].sum()
            total_count = len(df)
            prime_ratio = prime_count / total_count * 100
            
            fig_prime_pie = go.Figure(data=[go.Pie(
                labels=[get_text("prime_products"), get_text("non_prime_products")],
                values=[prime_count, total_count - prime_count],
                hole=.3,
                marker_colors=["#ff9900", "#232f3e"]
            )])
            fig_prime_pie.update_layout(title=get_text("prime_ratio"))
            st.plotly_chart(fig_prime_pie, use_container_width=True)
            
            st.markdown(f"""
            **{get_text("prime_stats")}:**
            - {get_text("prime_count")}: {prime_count}
            - {get_text("non_prime_count")}: {total_count - prime_count}
            - {get_text("prime_ratio")}: {prime_ratio:.1f}%
            """)
        
        with col2:
            # Prime vs 非Prime价格对比
            fig_prime_price = go.Figure()
            
            fig_prime_price.add_trace(go.Box(
                y=df[df["is_prime"]]["price"],
                name=get_text("prime_products"),
                marker_color="#ff9900"
            ))
            
            fig_prime_price.add_trace(go.Box(
                y=df[~df["is_prime"]]["price"],
                name=get_text("non_prime_products"),
                marker_color="#232f3e"
            ))
            
            fig_prime_price.update_layout(
                title=get_text("prime_price_comparison"),
                yaxis_title=get_text("price") + " ($)"
            )
            st.plotly_chart(fig_prime_price, use_container_width=True)
            
            # Prime vs 非Prime折扣对比
            fig_prime_discount = go.Figure()
            
            fig_prime_discount.add_trace(go.Box(
                y=df[df["is_prime"]]["savings_percentage"],
                name=get_text("prime_products"),
                marker_color="#ff9900"
            ))
            
            fig_prime_discount.add_trace(go.Box(
                y=df[~df["is_prime"]]["savings_percentage"],
                name=get_text("non_prime_products"),
                marker_color="#232f3e"
            ))
            
            fig_prime_discount.update_layout(
                title=get_text("prime_discount_comparison"),
                yaxis_title=get_text("discount_rate") + " (%)"
            )
            st.plotly_chart(fig_prime_discount, use_container_width=True)
            
    with tab4:
        st.subheader("🎫 " + get_text("coupon_analysis"))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 优惠券类型分布
            coupon_type_counts = df[df["coupon_type"].notna()]["coupon_type"].value_counts()
            
            if not coupon_type_counts.empty:
                fig_coupon_type = px.pie(
                    values=coupon_type_counts.values,
                    names=coupon_type_counts.index,
                    title=get_text("coupon_type_distribution"),
                    color_discrete_sequence=["#ff9900", "#232f3e"]
                )
                st.plotly_chart(fig_coupon_type, use_container_width=True)
                
                # 优惠券统计信息
                st.markdown(f"""
                **{get_text("coupon_stats")}:**
                - {get_text("total_coupons")}: {len(df[df["coupon_type"].notna()])}
                - {get_text("percentage_coupons")}: {len(df[df["coupon_type"] == "percentage"])}
                - {get_text("fixed_coupons")}: {len(df[df["coupon_type"] == "fixed"])}
                """)
            else:
                st.info(get_text("no_coupon_data"))
        
        with col2:
            # 优惠券值分布
            if not df[df["coupon_value"].notna()].empty:
                fig_coupon_value = px.histogram(
                    df[df["coupon_value"].notna()],
                    x="coupon_value",
                    nbins=20,
                    title=get_text("coupon_value_distribution"),
                    labels={
                        "coupon_value": get_text("coupon_value"),
                        "count": get_text("product_count")
                    },
                    color_discrete_sequence=["#ff9900"]
                )
                st.plotly_chart(fig_coupon_value, use_container_width=True)
                
                # 优惠券值统计
                coupon_value_stats = df[df["coupon_value"].notna()]["coupon_value"].describe()
                st.markdown(f"""
                **{get_text("coupon_value_stats")}:**
                - {get_text("min_value")}: {coupon_value_stats['min']:.2f}
                - {get_text("max_value")}: {coupon_value_stats['max']:.2f}
                - {get_text("avg_value")}: {coupon_value_stats['mean']:.2f}
                - {get_text("median_value")}: {coupon_value_stats['50%']:.2f}
                """)
            else:
                st.info(get_text("no_coupon_value_data"))
        
        # 优惠券与价格关系分析
        st.subheader(get_text("coupon_price_analysis"))
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 优惠券类型与商品价格的关系
            if not df[df["coupon_type"].notna()].empty:
                fig_coupon_price = px.box(
                    df[df["coupon_type"].notna()],
                    x="coupon_type",
                    y="price",
                    title=get_text("coupon_price_relation"),
                    labels={
                        "coupon_type": get_text("coupon_type"),
                        "price": get_text("price") + " ($)"
                    },
                    color="coupon_type",
                    color_discrete_sequence=["#ff9900", "#232f3e"]
                )
                st.plotly_chart(fig_coupon_price, use_container_width=True)
            else:
                st.info(get_text("no_coupon_price_data"))
        
        with col2:
            # 优惠券值与商品价格的散点图
            if not df[df["coupon_value"].notna()].empty:
                fig_value_price = px.scatter(
                    df[df["coupon_value"].notna()],
                    x="price",
                    y="coupon_value",
                    title=get_text("coupon_value_price_relation"),
                    labels={
                        "price": get_text("price") + " ($)",
                        "coupon_value": get_text("coupon_value")
                    },
                    color_discrete_sequence=["#ff9900"]
                )
                st.plotly_chart(fig_value_price, use_container_width=True)
            else:
                st.info(get_text("no_coupon_value_price_data"))
else:
    st.warning(get_text("no_products")) 