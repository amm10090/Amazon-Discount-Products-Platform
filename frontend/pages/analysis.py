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
        # 使用固定的page_size=100，避免超出API限制
        response = requests.get(
            f"{api_url}/api/products/list",
            params={
                "page_size": 100,  # 固定使用100，而不是从配置文件读取
                "product_type": product_type
            },
            timeout=5
        )
        
        if response.status_code != 200:
            st.error(f"{get_text('loading_failed')}: API返回状态码 {response.status_code}")
            return pd.DataFrame()
            
        data = response.json()
        if not isinstance(data, dict) or "items" not in data:
            st.error(f"{get_text('loading_failed')}: API响应格式不正确")
            return pd.DataFrame()
            
        items = data.get("items", [])
        if not items:
            # 如果没有数据，返回空DataFrame但不显示错误
            return pd.DataFrame()
            
        df_data = []
        for item in items:
            # 检查必需字段
            if not all(k in item for k in ["asin", "title", "offers"]):
                continue
                
            # 获取第一个offer
            offers = item.get("offers", [])
            if not offers:
                continue
                
            offer = offers[0]
            
            # 构建数据行
            row = {
                'asin': item.get('asin'),
                'title': item.get('title'),
                'brand': item.get('brand'),
                'binding': item.get('binding'),
                'product_group': item.get('product_group'),
                'timestamp': pd.to_datetime(item.get('timestamp')),
                'price': offer.get('price'),
                'savings_percentage': offer.get('savings_percentage'),
                'savings': offer.get('savings'),
                'is_prime': offer.get('is_prime', False),
                'coupon_type': offer.get('coupon_type'),
                'coupon_value': offer.get('coupon_value'),
                'merchant_name': offer.get('merchant_name'),
                'availability': offer.get('availability')
            }
            
            # 添加到数据列表
            df_data.append(row)
        
        if not df_data:
            # 如果没有有效数据，返回空DataFrame但不显示错误
            return pd.DataFrame()
            
        # 创建DataFrame并设置数据类型
        df = pd.DataFrame(df_data)
        
        # 转换数据类型
        numeric_columns = ['price', 'savings_percentage', 'savings', 'coupon_value']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        boolean_columns = ['is_prime']
        for col in boolean_columns:
            if col in df.columns:
                df[col] = df[col].fillna(False)
                
        # 确保timestamp列是datetime类型
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            
        return df
        
    except requests.exceptions.ConnectionError:
        st.error(f"{get_text('loading_failed')}: 无法连接到API服务")
        return pd.DataFrame()
    except requests.exceptions.Timeout:
        st.error(f"{get_text('loading_failed')}: API请求超时")
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
            stats = response.json()
            
            # 验证返回的数据格式
            required_fields = [
                "total_products", "discount_products", "coupon_products",
                "prime_products", "avg_discount", "avg_price", "min_price", "max_price"
            ]
            
            # 检查所有必需字段是否存在
            if not all(field in stats for field in required_fields):
                missing_fields = [field for field in required_fields if field not in stats]
                st.error(f"{get_text('loading_failed')}: 缺少必需字段: {', '.join(missing_fields)}")
                return {}
                
            # 验证数值字段的类型
            numeric_fields = ["total_products", "discount_products", "coupon_products", 
                            "prime_products", "avg_discount", "avg_price", "min_price", "max_price"]
            
            for field in numeric_fields:
                if not isinstance(stats[field], (int, float)):
                    st.error(f"{get_text('loading_failed')}: 字段 {field} 的值类型不正确")
                    return {}
                    
            # 验证数值的合理性
            if stats["total_products"] < 0 or \
               stats["discount_products"] < 0 or \
               stats["coupon_products"] < 0 or \
               stats["prime_products"] < 0:
                st.error(f"{get_text('loading_failed')}: 统计数据包含负数")
                return {}
                
            if stats["discount_products"] > stats["total_products"] or \
               stats["coupon_products"] > stats["total_products"] or \
               stats["prime_products"] > stats["total_products"]:
                st.error(f"{get_text('loading_failed')}: 统计数据不一致")
                return {}
                
            # 计算平均节省金额
            if "avg_savings" not in stats and stats["avg_price"] > 0 and stats["avg_discount"] > 0:
                stats["avg_savings"] = stats["avg_price"] * (stats["avg_discount"] / 100)
                
            return stats
            
        st.error(f"{get_text('loading_failed')}: API返回状态码 {response.status_code}")
        return {}
    except requests.exceptions.ConnectionError:
        st.error(f"{get_text('loading_failed')}: 无法连接到API服务")
        return {}
    except requests.exceptions.Timeout:
        st.error(f"{get_text('loading_failed')}: API请求超时")
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
    
    # 加载统计数据
    stats_data = load_stats_data(api_url)
    
    # 加载详细商品数据
    df = load_products_data(api_url)
    
    # 检查是否有数据
    if stats_data and stats_data.get("total_products", 0) > 0:
        st.header("📈 " + get_text("overview"))
        
        # 显示总体统计信息
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label=get_text("total_products"),
                value=stats_data["total_products"],
                help="商品总数"
            )
        
        with col2:
            st.metric(
                label=get_text("discount_products"),
                value=stats_data["discount_products"],
                delta=f"{(stats_data['discount_products']/stats_data['total_products']*100):.1f}%",
                help="折扣商品数量及占比"
            )
        
        with col3:
            st.metric(
                label=get_text("coupon_products"),
                value=stats_data["coupon_products"],
                delta=f"{(stats_data['coupon_products']/stats_data['total_products']*100):.1f}%",
                help="优惠券商品数量及占比"
            )
        
        with col4:
            st.metric(
                label=get_text("prime_products"),
                value=stats_data["prime_products"],
                delta=f"{(stats_data['prime_products']/stats_data['total_products']*100):.1f}%",
                help="Prime商品数量及占比"
            )
        
        st.markdown("---")
        
        # 显示价格和折扣统计
        st.subheader("💰 " + get_text("price_discount_overview"))
        
        # 价格统计
        st.markdown("#### " + get_text("price_stats"))
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label=get_text("avg_price"),
                value=f"${stats_data['avg_price']:.2f}",
                help="平均价格"
            )
        
        with col2:
            st.metric(
                label=get_text("price_range"),
                value=f"${stats_data['min_price']:.2f} - ${stats_data['max_price']:.2f}",
                help="价格区间"
            )
            
        with col3:
            st.metric(
                label=get_text("total_value"),
                value=f"${stats_data['avg_price'] * stats_data['total_products']:.2f}",
                help="商品总价值"
            )
            
        # 折扣统计
        st.markdown("#### " + get_text("discount_stats"))
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label=get_text("avg_discount"),
                value=f"{stats_data['avg_discount']:.1f}%",
                help="平均折扣率"
            )
            
        with col2:
            st.metric(
                label=get_text("discount_range"),
                value=f"{stats_data['min_discount']:.1f}% - {stats_data['max_discount']:.1f}%",
                help="折扣率区间"
            )
            
        with col3:
            st.metric(
                label=get_text("total_savings"),
                value=f"${stats_data['avg_savings'] * stats_data['total_products']:.2f}",
                help="总节省金额"
            )
            
        # 优惠券统计
        st.markdown("#### " + get_text("coupon_stats"))
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label=get_text("total_coupons"),
                value=stats_data["total_coupons"],
                delta=f"{(stats_data['total_coupons']/stats_data['total_products']*100):.1f}%",
                help="优惠券总数及占比"
            )
            
        with col2:
            st.metric(
                label=get_text("avg_coupon_value"),
                value=f"${stats_data['avg_coupon_value']:.2f}",
                help="平均优惠券金额"
            )
            
        with col3:
            st.metric(
                label=get_text("coupon_value_range"),
                value=f"${stats_data['min_coupon_value']:.2f} - ${stats_data['max_coupon_value']:.2f}",
                help="优惠券金额区间"
            )
            
        # 分类统计
        if "categories" in stats_data and any(stats_data["categories"].values()):
            st.markdown("---")
            st.subheader("📊 " + get_text("category_stats"))
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # 商品类型统计
                if stats_data["categories"]["bindings"]:
                    st.markdown("#### " + get_text("product_binding"))
                    fig_bindings = px.pie(
                        values=list(stats_data["categories"]["bindings"].values()),
                        names=list(stats_data["categories"]["bindings"].keys()),
                        title=get_text("binding_distribution")
                    )
                    st.plotly_chart(fig_bindings, use_container_width=True)
            
            with col2:
                # 商品组统计
                if stats_data["categories"]["groups"]:
                    st.markdown("#### " + get_text("product_group"))
                    fig_groups = px.pie(
                        values=list(stats_data["categories"]["groups"].values()),
                        names=list(stats_data["categories"]["groups"].keys()),
                        title=get_text("group_distribution")
                    )
                    st.plotly_chart(fig_groups, use_container_width=True)
            
            with col3:
                # 品牌统计
                if stats_data["categories"]["brands"]:
                    st.markdown("#### " + get_text("brand_stats"))
                    # 只显示前10个品牌
                    brands_sorted = dict(sorted(
                        stats_data["categories"]["brands"].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10])
                    fig_brands = px.bar(
                        x=list(brands_sorted.keys()),
                        y=list(brands_sorted.values()),
                        title=get_text("top_brands")
                    )
                    st.plotly_chart(fig_brands, use_container_width=True)
        
        # 显示最后更新时间
        if "last_update" in stats_data and stats_data["last_update"]:
            st.markdown("---")
            st.markdown(f"*{get_text('last_update')}: {stats_data['last_update']}*")
    
    # 如果有详细商品数据，显示详细分析
    if not df.empty:
        st.markdown("---")
        
        # 创建分析选项卡
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 " + get_text("price_analysis"),
            "🏷️ " + get_text("discount_analysis"),
            "✨ " + get_text("prime_analysis"),
            "🎫 " + get_text("coupon_analysis"),
            "📅 " + get_text("trend_analysis")
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
                    - {get_text("std_price")}: ${stats['std']:.2f}
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
                    - {get_text("std_discount")}: {stats['std']:.1f}%
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
                
        # 时间趋势分析
        with tab5:
            st.subheader("📅 " + get_text("trend_analysis"))
            
            # 按天统计数据
            df['date'] = df['timestamp'].dt.date
            daily_stats = df.groupby('date').agg({
                'price': ['mean', 'count'],
                'savings_percentage': 'mean',
                'is_prime': 'sum'
            }).reset_index()
            
            daily_stats.columns = ['date', 'avg_price', 'product_count', 'avg_discount', 'prime_count']
            
            # 显示时间趋势图
            col1, col2 = st.columns(2)
            
            with col1:
                # 每日商品数量趋势
                fig_daily_count = px.line(
                    daily_stats,
                    x='date',
                    y='product_count',
                    title=get_text("daily_product_count"),
                    labels={
                        'date': get_text("date"),
                        'product_count': get_text("product_count")
                    }
                )
                st.plotly_chart(fig_daily_count, use_container_width=True)
                
                # 每日平均折扣趋势
                fig_daily_discount = px.line(
                    daily_stats,
                    x='date',
                    y='avg_discount',
                    title=get_text("daily_avg_discount"),
                    labels={
                        'date': get_text("date"),
                        'avg_discount': get_text("avg_discount") + " (%)"
                    }
                )
                st.plotly_chart(fig_daily_discount, use_container_width=True)
            
            with col2:
                # 每日平均价格趋势
                fig_daily_price = px.line(
                    daily_stats,
                    x='date',
                    y='avg_price',
                    title=get_text("daily_avg_price"),
                    labels={
                        'date': get_text("date"),
                        'avg_price': get_text("avg_price") + " ($)"
                    }
                )
                st.plotly_chart(fig_daily_price, use_container_width=True)
                
                # 每日Prime商品数量趋势
                fig_daily_prime = px.line(
                    daily_stats,
                    x='date',
                    y='prime_count',
                    title=get_text("daily_prime_count"),
                    labels={
                        'date': get_text("date"),
                        'prime_count': get_text("prime_count")
                    }
                )
                st.plotly_chart(fig_daily_prime, use_container_width=True)
    else:
        # 如果没有任何数据，显示提示信息
        if not stats_data or stats_data.get("total_products", 0) == 0:
            st.warning(get_text("no_products"))

if __name__ == "__main__":
    main() 