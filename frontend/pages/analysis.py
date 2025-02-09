import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from frontend.i18n.language import init_language, get_text
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from frontend.main import load_config
from frontend.utils.cache_manager import cache_manager

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

st.title("📊 " + get_text("analysis_title"))

# 数据加载和处理函数
@cache_manager.data_cache(
    ttl=300,
    show_spinner="正在加载商品数据..."
)
def load_products_data(api_url: str, product_type: str = "all") -> pd.DataFrame:
    """加载商品数据
    
    Args:
        api_url: API服务地址
        product_type: 商品类型，可选值：all, discount, coupon
        
    Returns:
        pd.DataFrame: 商品数据DataFrame
    """
    try:
        response = requests.get(
            f"{api_url}/api/products/list",
            params={
                "page_size": config["frontend"]["cache"]["max_entries"],
                "product_type": product_type
            },
            timeout=5
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
        return pd.DataFrame()
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return pd.DataFrame()

@cache_manager.data_cache(
    ttl=300,
    show_spinner="正在加载统计数据..."
)
def load_stats_data(api_url: str) -> dict:
    """加载统计数据
    
    Args:
        api_url: API服务地址
        
    Returns:
        dict: 统计数据
    """
    try:
        response = requests.get(f"{api_url}/api/products/stats", timeout=5)
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return {}

@cache_manager.data_cache(ttl=300)
def process_price_analysis(df: pd.DataFrame) -> dict:
    """处理价格分析数据
    
    Args:
        df: 商品数据DataFrame
        
    Returns:
        dict: 价格分析结果
    """
    if df.empty:
        return {}
    
    price_stats = df["price"].describe()
    price_bins = pd.cut(df["price"], bins=5)
    price_dist = price_bins.value_counts().sort_index()
    
    return {
        "stats": price_stats,
        "distribution": {
            "bins": [f"${int(b.left)}-${int(b.right)}" for b in price_dist.index],
            "values": price_dist.values
        }
    }

@cache_manager.data_cache(ttl=300)
def process_discount_analysis(df: pd.DataFrame) -> dict:
    """处理折扣分析数据
    
    Args:
        df: 商品数据DataFrame
        
    Returns:
        dict: 折扣分析结果
    """
    if df.empty:
        return {}
    
    df_with_discount = df[df["savings_percentage"].notna()]
    if df_with_discount.empty:
        return {}
    
    discount_stats = df_with_discount["savings_percentage"].describe()
    discount_bins = pd.cut(
        df_with_discount["savings_percentage"],
        bins=[0, 20, 40, 60, 80, 100]
    )
    discount_dist = discount_bins.value_counts().sort_index()
    
    return {
        "stats": discount_stats,
        "distribution": {
            "bins": [f"{int(b.left)}-{int(b.right)}%" for b in discount_dist.index],
            "values": discount_dist.values
        }
    }

@cache_manager.data_cache(ttl=300)
def process_prime_analysis(df: pd.DataFrame) -> dict:
    """处理Prime分析数据
    
    Args:
        df: 商品数据DataFrame
        
    Returns:
        dict: Prime分析结果
    """
    if df.empty:
        return {}
    
    prime_count = df["is_prime"].sum()
    total_count = len(df)
    
    return {
        "prime_count": prime_count,
        "total_count": total_count,
        "prime_ratio": prime_count / total_count * 100 if total_count > 0 else 0,
        "price_comparison": {
            "prime": df[df["is_prime"]]["price"].tolist(),
            "non_prime": df[~df["is_prime"]]["price"].tolist()
        },
        "discount_comparison": {
            "prime": df[df["is_prime"]]["savings_percentage"].tolist(),
            "non_prime": df[~df["is_prime"]]["savings_percentage"].tolist()
        }
    }

@cache_manager.data_cache(ttl=300)
def process_coupon_analysis(df: pd.DataFrame) -> dict:
    """处理优惠券分析数据
    
    Args:
        df: 商品数据DataFrame
        
    Returns:
        dict: 优惠券分析结果
    """
    if df.empty:
        return {}
    
    df_with_coupon = df[df["coupon_type"].notna()]
    if df_with_coupon.empty:
        return {}
    
    coupon_type_counts = df_with_coupon["coupon_type"].value_counts()
    coupon_value_stats = df_with_coupon[df_with_coupon["coupon_value"].notna()]["coupon_value"].describe()
    
    return {
        "type_distribution": {
            "types": coupon_type_counts.index.tolist(),
            "counts": coupon_type_counts.values.tolist()
        },
        "value_stats": coupon_value_stats,
        "price_relation": {
            "prices": df_with_coupon["price"].tolist(),
            "values": df_with_coupon["coupon_value"].tolist(),
            "types": df_with_coupon["coupon_type"].tolist()
        }
    }

def main():
    # 加载数据
    api_url = f"http://{config['api']['host']}:{config['api']['port']}"
    df = load_products_data(api_url)
    
    if not df.empty:
        # 数据预处理
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["savings_percentage"] = pd.to_numeric(df["savings_percentage"], errors="coerce")
        df["coupon_value"] = pd.to_numeric(df["coupon_value"], errors="coerce")
        
        # 创建分析选项卡
        tab1, tab2, tab3, tab4 = st.tabs([
            get_text("price_analysis"),
            get_text("discount_analysis"),
            get_text("prime_analysis"),
            "🎫 " + get_text("coupon_analysis")
        ])
        
        # 价格分析
        with tab1:
            st.subheader("💰 " + get_text("price_analysis"))
            price_analysis = process_price_analysis(df)
            
            if price_analysis:
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
                    stats = price_analysis["stats"]
                    st.markdown(f"""
                    **{get_text("price_stats")}:**
                    - {get_text("min_price")}: ${stats['min']:.2f}
                    - {get_text("max_price")}: ${stats['max']:.2f}
                    - {get_text("avg_price")}: ${stats['mean']:.2f}
                    - {get_text("median_price")}: ${stats['50%']:.2f}
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
                    dist = price_analysis["distribution"]
                    fig_price_range = px.bar(
                        x=dist["bins"],
                        y=dist["values"],
                        title=get_text("price_range_distribution"),
                        labels={
                            "x": get_text("price_range"),
                            "y": get_text("product_count")
                        },
                        color_discrete_sequence=["#ff9900"]
                    )
                    st.plotly_chart(fig_price_range, use_container_width=True)
            else:
                st.info(get_text("no_price_data"))
        
        # 折扣分析
        with tab2:
            st.subheader("🏷️ " + get_text("discount_analysis"))
            discount_analysis = process_discount_analysis(df)
            
            if discount_analysis:
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
                    stats = discount_analysis["stats"]
                    st.markdown(f"""
                    **{get_text("discount_stats")}:**
                    - {get_text("min_discount")}: {stats['min']:.1f}%
                    - {get_text("max_discount")}: {stats['max']:.1f}%
                    - {get_text("avg_discount")}: {stats['mean']:.1f}%
                    - {get_text("median_discount")}: {stats['50%']:.1f}%
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
                    dist = discount_analysis["distribution"]
                    fig_discount_range = px.bar(
                        x=dist["bins"],
                        y=dist["values"],
                        title=get_text("discount_range_distribution"),
                        labels={
                            "x": get_text("discount_range"),
                            "y": get_text("product_count")
                        },
                        color_discrete_sequence=["#ff9900"]
                    )
                    st.plotly_chart(fig_discount_range, use_container_width=True)
            else:
                st.info(get_text("no_discount_data"))
        
        # Prime分析
        with tab3:
            st.subheader("✨ " + get_text("prime_analysis"))
            prime_analysis = process_prime_analysis(df)
            
            if prime_analysis:
                col1, col2 = st.columns(2)
                
                with col1:
                    # Prime商品比例
                    fig_prime_pie = go.Figure(data=[go.Pie(
                        labels=[get_text("prime_products"), get_text("non_prime_products")],
                        values=[
                            prime_analysis["prime_count"],
                            prime_analysis["total_count"] - prime_analysis["prime_count"]
                        ],
                        hole=.3,
                        marker_colors=["#ff9900", "#232f3e"]
                    )])
                    fig_prime_pie.update_layout(title=get_text("prime_ratio"))
                    st.plotly_chart(fig_prime_pie, use_container_width=True)
                    
                    st.markdown(f"""
                    **{get_text("prime_stats")}:**
                    - {get_text("prime_count")}: {prime_analysis["prime_count"]}
                    - {get_text("non_prime_count")}: {prime_analysis["total_count"] - prime_analysis["prime_count"]}
                    - {get_text("prime_ratio")}: {prime_analysis["prime_ratio"]:.1f}%
                    """)
                
                with col2:
                    # Prime vs 非Prime价格对比
                    fig_prime_price = go.Figure()
                    
                    fig_prime_price.add_trace(go.Box(
                        y=prime_analysis["price_comparison"]["prime"],
                        name=get_text("prime_products"),
                        marker_color="#ff9900"
                    ))
                    
                    fig_prime_price.add_trace(go.Box(
                        y=prime_analysis["price_comparison"]["non_prime"],
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
                        y=prime_analysis["discount_comparison"]["prime"],
                        name=get_text("prime_products"),
                        marker_color="#ff9900"
                    ))
                    
                    fig_prime_discount.add_trace(go.Box(
                        y=prime_analysis["discount_comparison"]["non_prime"],
                        name=get_text("non_prime_products"),
                        marker_color="#232f3e"
                    ))
                    
                    fig_prime_discount.update_layout(
                        title=get_text("prime_discount_comparison"),
                        yaxis_title=get_text("discount_rate") + " (%)"
                    )
                    st.plotly_chart(fig_prime_discount, use_container_width=True)
            else:
                st.info(get_text("no_prime_data"))
        
        # 优惠券分析
        with tab4:
            st.subheader("🎫 " + get_text("coupon_analysis"))
            coupon_analysis = process_coupon_analysis(df)
            
            if coupon_analysis:
                col1, col2 = st.columns(2)
                
                with col1:
                    # 优惠券类型分布
                    fig_coupon_type = px.pie(
                        values=coupon_analysis["type_distribution"]["counts"],
                        names=coupon_analysis["type_distribution"]["types"],
                        title=get_text("coupon_type_distribution"),
                        color_discrete_sequence=["#ff9900", "#232f3e"]
                    )
                    st.plotly_chart(fig_coupon_type, use_container_width=True)
                    
                    # 优惠券统计信息
                    st.markdown(f"""
                    **{get_text("coupon_stats")}:**
                    - {get_text("total_coupons")}: {sum(coupon_analysis["type_distribution"]["counts"])}
                    - {get_text("percentage_coupons")}: {coupon_analysis["type_distribution"]["counts"][0]}
                    - {get_text("fixed_coupons")}: {coupon_analysis["type_distribution"]["counts"][1]}
                    """)
                
                with col2:
                    # 优惠券值分布
                    value_stats = coupon_analysis["value_stats"]
                    if not pd.isna(value_stats["count"]):
                        fig_coupon_value = px.histogram(
                            x=coupon_analysis["price_relation"]["values"],
                            nbins=20,
                            title=get_text("coupon_value_distribution"),
                            labels={
                                "x": get_text("coupon_value"),
                                "y": get_text("product_count")
                            },
                            color_discrete_sequence=["#ff9900"]
                        )
                        st.plotly_chart(fig_coupon_value, use_container_width=True)
                        
                        # 优惠券值统计
                        st.markdown(f"""
                        **{get_text("coupon_value_stats")}:**
                        - {get_text("min_value")}: {value_stats['min']:.2f}
                        - {get_text("max_value")}: {value_stats['max']:.2f}
                        - {get_text("avg_value")}: {value_stats['mean']:.2f}
                        - {get_text("median_value")}: {value_stats['50%']:.2f}
                        """)
                    else:
                        st.info(get_text("no_coupon_value_data"))
                
                # 优惠券与价格关系分析
                st.subheader(get_text("coupon_price_analysis"))
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # 优惠券类型与商品价格的关系
                    coupon_price_df = pd.DataFrame({
                        'coupon_type': coupon_analysis["price_relation"]["types"],
                        'price': coupon_analysis["price_relation"]["prices"]
                    })
                    fig_coupon_price = px.box(
                        data_frame=coupon_price_df,
                        x='coupon_type',
                        y='price',
                        title=get_text("coupon_price_relation"),
                        labels={
                            "coupon_type": get_text("coupon_type"),
                            "price": get_text("price") + " ($)"
                        },
                        color='coupon_type',
                        color_discrete_sequence=["#ff9900", "#232f3e"]
                    )
                    st.plotly_chart(fig_coupon_price, use_container_width=True)
                
                with col2:
                    # 优惠券值与商品价格的散点图
                    value_price_df = pd.DataFrame({
                        'price': coupon_analysis["price_relation"]["prices"],
                        'coupon_value': coupon_analysis["price_relation"]["values"]
                    })
                    fig_value_price = px.scatter(
                        data_frame=value_price_df,
                        x='price',
                        y='coupon_value',
                        title=get_text("coupon_value_price_relation"),
                        labels={
                            "price": get_text("price") + " ($)",
                            "coupon_value": get_text("coupon_value")
                        },
                        color_discrete_sequence=["#ff9900"]
                    )
                    st.plotly_chart(fig_value_price, use_container_width=True)
            else:
                st.info(get_text("no_coupon_data"))
    else:
        st.warning(get_text("no_products"))

if __name__ == "__main__":
    main() 