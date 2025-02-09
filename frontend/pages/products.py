import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import json
from i18n import init_language, get_text, language_selector
import sys
from pathlib import Path
import yaml
sys.path.append(str(Path(__file__).parent.parent))
from main import load_config
from utils.cache_manager import cache_manager
from typing import List, Dict, Optional

# 加载配置
def load_yaml_config():
    config_path = Path(__file__).parent.parent.parent / "config" / "production.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_yaml_config()

# 初始化语言设置
init_language()

st.set_page_config(
    page_title=get_text("products_title"),
    page_icon="📦",
    layout=config["frontend"]["page"]["layout"],
    initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"]
)

# 自定义CSS
st.markdown(f"""
<style>
    /* 全局样式 */
    .stApp {{
        background-color: #f5f5f7;
    }}
    
    /* 标签页样式 */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        padding: 0.5rem;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        padding: 0 24px;
        background-color: white;
        border-radius: 100px;
        gap: 8px;
        color: #1d1d1f;
        font-weight: 500;
        border: none;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }}
    
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, #1E88E5, #1976D2);
        color: white !important;
    }}
    
    /* 侧边栏样式 */
    .css-1d391kg {{
        background-color: white;
        padding: 2rem 1rem;
        border-right: 1px solid #e0e0e0;
    }}
    
    /* 标签样式 */
    .source-tag {{
        display: inline-flex;
        align-items: center;
        padding: 6px 16px;
        border-radius: 100px;
        font-size: 0.85em;
        font-weight: 500;
        margin: 4px;
        color: white;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }}
    
    .source-tag.cj {{
        background: linear-gradient(135deg, #FF6B6B, #FF5252);
    }}
    
    .source-tag.amazon {{
        background: linear-gradient(135deg, #9C27B0, #7B1FA2);
    }}
    
    .source-tag.prime {{
        background: linear-gradient(135deg, #00A8E1, #0091EA);
    }}
    
    .source-tag.commission {{
        background: linear-gradient(135deg, #4CAF50, #43A047);
    }}
    
    .source-tag.coupon {{
        background: linear-gradient(135deg, #FF5722, #F4511E);
    }}
    
    /* 按钮样式 */
    .stButton>button {{
        border-radius: 100px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s ease;
        border: none;
        background: linear-gradient(135deg, #1E88E5, #1976D2);
        color: white;
    }}
    
    .stButton>button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}
    
    /* 输入框样式 */
    .stNumberInput>div>div>input {{
        border-radius: 8px;
        border: 1px solid #e0e0e0;
    }}
    
    .stSlider>div>div {{
        background-color: white;
        border-radius: 100px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }}
    
    /* 选择框样式 */
    .stSelectbox>div>div {{
        border-radius: 8px;
        border: 1px solid #e0e0e0;
    }}
    
    /* 卡片样式 */
    .product-card {{
        background-color: white;
        border-radius: 20px;
        padding: 24px;
        margin: 16px 0;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    
    .product-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
    }}
    
    /* 图片容器样式 */
    .image-container {{
        background-color: #f5f5f7;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        transition: transform 0.2s ease;
    }}
    
    .image-container:hover {{
        transform: scale(1.02);
    }}
    
    /* 价格样式 */
    .price-container {{
        margin: 16px 0;
    }}
    
    .original-price {{
        color: #86868b;
        text-decoration: line-through;
        font-size: 0.9em;
    }}
    
    .current-price {{
        color: #1d1d1f;
        font-size: 1.4em;
        font-weight: 600;
        margin-top: 4px;
    }}
    
    /* 链接按钮样式 */
    .link-button {{
        display: block;
        padding: 12px 20px;
        border-radius: 100px;
        text-decoration: none;
        text-align: center;
        font-weight: 500;
        margin: 8px 0;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    
    .link-button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}
    
    .link-button.cj {{
        background: linear-gradient(135deg, #FF6B6B, #FF5252);
        color: white;
    }}
    
    .link-button.amazon {{
        background: linear-gradient(135deg, #1E88E5, #1976D2);
        color: white;
    }}
    
    /* 分类标签样式 */
    .category-chip {{
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 100px;
        font-size: 0.85em;
        font-weight: 500;
        margin: 4px;
        background-color: #f5f5f7;
        color: #1d1d1f;
        transition: all 0.2s ease;
    }}
    
    .category-chip:hover {{
        background-color: #e0e0e0;
        transform: translateY(-1px);
    }}
    
    /* 分隔符样式 */
    .separator {{
        color: #86868b;
        margin: 0 4px;
    }}
    
    /* 品牌信息样式 */
    .brand-info {{
        color: #1d1d1f;
        margin: 16px 0;
        font-size: 0.95em;
    }}
    
    .brand-label {{
        color: #86868b;
    }}
    
    .brand-value {{
        font-weight: 500;
    }}
    
    /* 更新时间样式 */
    .update-time {{
        color: #86868b;
        font-size: 0.85em;
        text-align: center;
        margin-top: 16px;
    }}
</style>
""", unsafe_allow_html=True)

# 定义API基础URL
API_BASE_URL = f"http://{config['api']['host']}:{config['api']['port']}"

@cache_manager.data_cache(
    ttl=config["frontend"]["cache"]["ttl"],
    show_spinner="正在加载商品数据..."
)
def load_products(
    product_type: str = "all",
    page: int = 1,
    page_size: int = 20,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_discount: Optional[int] = None,
    prime_only: bool = False,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    selected_categories: Optional[Dict[str, List[str]]] = None,
    source_filter: str = "all",
    min_commission: Optional[int] = None
) -> Dict:
    """加载商品数据"""
    try:
        # 构建请求参数
        params = {
            "page": page,
            "page_size": page_size,
            "min_price": min_price,
            "max_price": max_price,
            "min_discount": min_discount,
            "is_prime_only": prime_only,
            "product_type": product_type,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
        
        # 添加数据来源筛选
        if source_filter != "all":
            params["source"] = source_filter
        
        # 添加佣金筛选
        if min_commission is not None and source_filter in ["all", "cj"]:
            params["min_commission"] = min_commission
        
        # 添加类别筛选参数
        if selected_categories:
            if selected_categories.get("main_categories"):
                params["main_categories"] = selected_categories["main_categories"]
            if selected_categories.get("sub_categories"):
                params["sub_categories"] = selected_categories["sub_categories"]
            if selected_categories.get("bindings"):
                params["bindings"] = selected_categories["bindings"]
            if selected_categories.get("product_groups"):
                params["product_groups"] = selected_categories["product_groups"]
        
        # 移除None值和空列表的参数
        params = {k: v for k, v in params.items() if (isinstance(v, list) and len(v) > 0) or (not isinstance(v, list) and v is not None)}
        
        # 根据商品类型选择不同的API端点
        if product_type == "discount":
            endpoint = "/api/products/discount"
        elif product_type == "coupon":
            endpoint = "/api/products/coupon"
        else:
            endpoint = "/api/products/list"
        
        # 发送请求
        response = requests.get(f"{API_BASE_URL}{endpoint}", params=params)
        response.raise_for_status()
        
        data = response.json()
        if isinstance(data, dict):
            return data
        else:
            return {
                "items": data,
                "total": len(data),
                "page": page,
                "page_size": page_size
            }
        
    except Exception as e:
        st.error(f"加载商品列表失败: {str(e)}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

def display_products(
    products_data: Dict,
    api_url: str,
    key_suffix: str = ""
):
    """显示商品列表"""
    if not products_data or not isinstance(products_data, dict):
        st.warning(get_text("no_matching_products"))
        return
    
    products = products_data.get("items", [])
    total = products_data.get("total", 0)
    
    if len(products) == 0:
        st.info(get_text("no_products"))
        return
    
    # 显示商品总数
    st.markdown(f"""
        <div style="
            background-color: #f5f5f7;
            padding: 16px 24px;
            border-radius: 16px;
            margin: 20px 0;
            font-size: 1.1em;
            color: #1d1d1f;
            font-weight: 500;
            text-align: center;
        ">
            共找到 {total} 个商品
        </div>
    """, unsafe_allow_html=True)
    
    # 显示商品列表
    for product in products:
        with st.container():
            # 创建商品卡片
            st.markdown("""
                <div style="
                    background-color: white;
                    border-radius: 20px;
                    padding: 24px;
                    margin: 16px 0;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
                    transition: transform 0.2s ease, box-shadow 0.2s ease;
                ">
            """, unsafe_allow_html=True)
            
            # 显示分类导航
            if (product.get("browse_nodes") or 
                product.get("categories") or 
                product.get("binding") or 
                product.get("product_group")):
                
                # 准备类别列表
                categories = []
                
                # 优先使用browse_nodes
                if product.get("browse_nodes") and len(product.get("browse_nodes", [])) > 0:
                    browse_node = product["browse_nodes"][0]
                    
                    def get_ancestors(node):
                        if not node:
                            return
                        node_name = (
                            node.get("display_name") or 
                            node.get("DisplayName") or 
                            node.get("context_free_name") or 
                            node.get("ContextFreeName") or 
                            node.get("name")
                        )
                        if node_name:
                            categories.insert(0, node_name.strip())
                        ancestor = node.get("ancestor") or node.get("Ancestor")
                        if ancestor:
                            get_ancestors(ancestor)
                    
                    current_name = (
                        browse_node.get("display_name") or 
                        browse_node.get("DisplayName") or 
                        browse_node.get("context_free_name") or 
                        browse_node.get("ContextFreeName") or 
                        browse_node.get("name")
                    )
                    if current_name:
                        categories.append(current_name.strip())
                    
                    ancestor = browse_node.get("ancestor") or browse_node.get("Ancestor")
                    if ancestor:
                        get_ancestors(ancestor)
                
                # 如果没有browse_nodes，使用categories
                elif product.get("categories") and len(product["categories"]) > 0:
                    categories = [cat.strip() for cat in product["categories"][0].split(" > ")] if isinstance(product["categories"][0], str) else []
                
                # 如果前两者都没有，使用binding和product_group
                elif product.get("binding") or product.get("product_group"):
                    if product.get("product_group"):
                        categories.append(product["product_group"])
                    if product.get("binding"):
                        categories.append(product["binding"])
                
                # 使用pills组件显示类别
                if categories:
                    st.markdown("""
                        <style>
                            div[data-testid="stPills"] {
                                margin-bottom: 1rem;
                            }
                            div[data-testid="stPills"] button {
                                background-color: #f5f5f7 !important;
                                border-radius: 100px !important;
                                color: #1d1d1f !important;
                                font-weight: 500 !important;
                                border: none !important;
                                padding: 0.25rem 0.75rem !important;
                                margin-right: 0.5rem !important;
                            }
                            div[data-testid="stPills"] button:hover {
                                background-color: #e8e8e8 !important;
                                color: #1d1d1f !important;
                            }
                            div[data-testid="stPills"] button[data-testid="pill"] {
                                cursor: default !important;
                            }
                        </style>
                    """, unsafe_allow_html=True)
                    st.write("类别导航:")
                    _ = st.pills(
                        "类别",
                        options=categories,
                        key=f"category_pills_{product.get('asin', '')}_{key_suffix}"
                    )
            
            # 商品布局
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                if product.get("main_image"):
                    st.markdown(f"""
                        <div style="
                            background-color: #f5f5f7;
                            border-radius: 16px;
                            padding: 16px;
                            text-align: center;
                        ">
                            <img src="{product['main_image']}" 
                                style="max-width: 100%; height: auto; border-radius: 8px;"
                            >
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                        <div style="
                            background-color: #f5f5f7;
                            border-radius: 16px;
                            padding: 16px;
                            text-align: center;
                            color: #86868b;
                        ">
                            🖼️ 暂无图片
                        </div>
                    """, unsafe_allow_html=True)
            
            with col2:
                # 商品标题
                st.markdown(f"""
                    <div style="margin-bottom: 16px;">
                        <h3 style="
                            color: #1d1d1f;
                            font-size: 1.2em;
                            font-weight: 600;
                            margin: 0 0 12px 0;
                            line-height: 1.4;
                        ">{product.get('title', get_text('unknown_product'))}</h3>
                    </div>
                """, unsafe_allow_html=True)
                
                # 标签容器
                tag_container = st.container()
                tag_cols = tag_container.columns(4)
                
                # 来源标签
                if product.get('source') == 'cj':
                    tag_cols[0].markdown("""
                        <div style="
                            background: linear-gradient(135deg, #FF6B6B, #FF5252);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                            box-shadow: 0 2px 8px rgba(255, 107, 107, 0.2);
                        ">
                            🔄 CJ
                        </div>
                    """, unsafe_allow_html=True)
                elif product.get('source') == 'pa-api':
                    tag_cols[0].markdown("""
                        <div style="
                            background: linear-gradient(135deg, #9C27B0, #7B1FA2);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                            box-shadow: 0 2px 8px rgba(156, 39, 176, 0.2);
                        ">
                            🛍️ Amazon API
                        </div>
                    """, unsafe_allow_html=True)
                
                # 佣金标签
                if product.get("source") == "cj" and product.get("offers"):
                    main_offer = product["offers"][0]
                    if main_offer.get("commission"):
                        tag_cols[1].markdown(f"""
                            <div style="
                                background: linear-gradient(135deg, #4CAF50, #43A047);
                                color: white;
                                padding: 6px 12px;
                                border-radius: 100px;
                                text-align: center;
                                font-size: 0.85em;
                                font-weight: 500;
                                margin: 4px 0;
                                box-shadow: 0 2px 8px rgba(76, 175, 80, 0.2);
                            ">
                                💰 佣金: {main_offer["commission"]}
                            </div>
                        """, unsafe_allow_html=True)
                
                # Prime标签
                if product.get("offers") and len(product["offers"]) > 0:
                    if product["offers"][0].get("is_prime"):
                        tag_cols[2].markdown("""
                            <div style="
                                background: linear-gradient(135deg, #00A8E1, #0091EA);
                                color: white;
                                padding: 6px 12px;
                                border-radius: 100px;
                                text-align: center;
                                font-size: 0.85em;
                                font-weight: 500;
                                margin: 4px 0;
                                box-shadow: 0 2px 8px rgba(0, 168, 225, 0.2);
                            ">
                                ✓ Prime
                            </div>
                        """, unsafe_allow_html=True)
                
                # 优惠券标签
                if product.get("offers") and product["offers"][0].get("coupon_type"):
                    coupon_type = product["offers"][0]["coupon_type"]
                    coupon_value = product["offers"][0]["coupon_value"]
                    tag_cols[3].markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #FF5722, #F4511E);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                            box-shadow: 0 2px 8px rgba(255, 87, 34, 0.2);
                        ">
                            🏷️ {coupon_value}{'%' if coupon_type == 'percentage' else '$'} OFF
                        </div>
                    """, unsafe_allow_html=True)
                
                # 品牌信息
                if product.get("brand"):
                    st.markdown(f"""
                        <div style="
                            color: #1d1d1f;
                            margin: 16px 0;
                            font-size: 0.95em;
                        ">
                            <span style="color: #86868b;">品牌:</span>
                            <span style="font-weight: 500;">{product['brand']}</span>
                        </div>
                    """, unsafe_allow_html=True)
                
                # 价格信息
                if product.get("offers") and len(product["offers"]) > 0:
                    offer = product["offers"][0]
                    price = offer.get("price")
                    savings = offer.get("savings")
                    currency = offer.get("currency", "USD")
                    
                    if price is not None:
                        price_col, discount_col = st.columns([1, 1])
                        with price_col:
                            if savings:
                                original_price = price + savings
                                st.markdown(f"""
                                    <div style="margin: 16px 0;">
                                        <div style="
                                            color: #86868b;
                                            text-decoration: line-through;
                                            font-size: 0.9em;
                                        ">
                                            ${original_price:.2f} {currency}
                                        </div>
                                        <div style="
                                            color: #1d1d1f;
                                            font-size: 1.4em;
                                            font-weight: 600;
                                            margin-top: 4px;
                                        ">
                                            ${price:.2f} {currency}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                    <div style="
                                        color: #1d1d1f;
                                        font-size: 1.4em;
                                        font-weight: 600;
                                        margin: 16px 0;
                                    ">
                                        ${price:.2f} {currency}
                                    </div>
                                """, unsafe_allow_html=True)
                        
                        with discount_col:
                            if savings:
                                savings_percentage = int((savings / (price + savings)) * 100)
                                st.markdown(f"""
                                    <div style="
                                        background: linear-gradient(135deg, #067D62, #00695C);
                                        color: white;
                                        padding: 8px 16px;
                                        border-radius: 100px;
                                        text-align: center;
                                        font-size: 0.95em;
                                        font-weight: 500;
                                        margin: 16px 0;
                                        box-shadow: 0 2px 8px rgba(6, 125, 98, 0.2);
                                    ">
                                        节省 {savings_percentage}%
                                    </div>
                                """, unsafe_allow_html=True)
            
            with col3:
                # CJ推广链接
                if product.get("cj_url"):
                    st.markdown(f"""
                        <a href="{product['cj_url']}" target="_blank" style="
                            display: block;
                            background: linear-gradient(135deg, #FF6B6B, #FF5252);
                            color: white;
                            padding: 12px 20px;
                            border-radius: 100px;
                            text-decoration: none;
                            text-align: center;
                            font-weight: 500;
                            margin: 8px 0;
                            box-shadow: 0 2px 8px rgba(255, 107, 107, 0.2);
                            transition: transform 0.2s ease, box-shadow 0.2s ease;
                        ">
                            CJ推广链接
                        </a>
                    """, unsafe_allow_html=True)
                
                # 商品链接
                if product.get("url"):
                    st.markdown(f"""
                        <a href="{product['url']}" target="_blank" style="
                            display: block;
                            background: linear-gradient(135deg, #1E88E5, #1976D2);
                            color: white;
                            padding: 12px 20px;
                            border-radius: 100px;
                            text-decoration: none;
                            text-align: center;
                            font-weight: 500;
                            margin: 8px 0;
                            box-shadow: 0 2px 8px rgba(30, 136, 229, 0.2);
                            transition: transform 0.2s ease, box-shadow 0.2s ease;
                        ">
                            查看详情
                        </a>
                    """, unsafe_allow_html=True)
                
                # 删除按钮
                delete_button = st.button(
                    "🗑️ 删除",
                    key=f"delete_{product['asin']}_{key_suffix}",
                    type="secondary",
                    use_container_width=True
                )
                
                if delete_button:
                    st.markdown("""
                        <div style="
                            background-color: #ffebee;
                            color: #c62828;
                            padding: 12px;
                            border-radius: 8px;
                            margin: 8px 0;
                            text-align: center;
                            font-size: 0.9em;
                        ">
                            确认要删除此商品吗？
                        </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("取消", key=f"cancel_{product['asin']}"):
                            st.rerun()
                    with col2:
                        if st.button("确认", key=f"confirm_{product['asin']}", type="primary"):
                            if delete_product(product["asin"]):
                                st.success("删除成功")
                                st.rerun()
                
                # 更新时间
                if product.get("timestamp"):
                    st.markdown(f"""
                        <div style="
                            color: #86868b;
                            font-size: 0.85em;
                            text-align: center;
                            margin-top: 16px;
                        ">
                            更新于 {product['timestamp']}
                        </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

def handle_pagination(
    total_items: int,
    page: int,
    page_size: int,
    key_suffix: str = ""
) -> int:
    """处理分页
    
    Args:
        total_items: 总商品数
        page: 当前页码
        page_size: 每页数量
        key_suffix: 状态键后缀
        
    Returns:
        int: 新的页码
    """
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 1:
            if st.button(
                get_text("prev_page"),
                key=f"prev_{key_suffix}"
            ):
                return page - 1
    
    with col2:
        total_pages = (total_items + page_size - 1) // page_size
        st.markdown(
            get_text("page_info").format(
                current=page,
                total=total_pages
            )
        )
    
    with col3:
        if total_items >= page_size:
            if st.button(
                get_text("next_page"),
                key=f"next_{key_suffix}"
            ):
                return page + 1
    
    return page

def handle_export(
    products: List[Dict],
    key_suffix: str = ""
):
    """处理数据导出
    
    Args:
        products: 商品列表
        key_suffix: 状态键后缀
    """
    st.markdown("---")
    st.subheader(get_text("export_data"))
    
    export_format = st.selectbox(
        get_text("export_format"),
        options=["CSV", "JSON", "Excel"],
        index=0,
        key=f"export_format_{key_suffix}"
    )
    
    if st.button(
        get_text("export_button"),
        key=f"export_{key_suffix}"
    ):
        if products:
            try:
                df = pd.DataFrame(products)
                
                # 根据选择的格式导出
                if export_format == "CSV":
                    csv = df.to_csv(index=False)
                    st.download_button(
                        f"{get_text('save')} CSV",
                        csv,
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv",
                        key=f"download_csv_{key_suffix}"
                    )
                
                elif export_format == "JSON":
                    json_str = df.to_json(orient="records", force_ascii=False)
                    st.download_button(
                        f"{get_text('save')} JSON",
                        json_str,
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        "application/json",
                        key=f"download_json_{key_suffix}"
                    )
                
                else:  # Excel
                    excel_buffer = pd.ExcelWriter(
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        engine="openpyxl"
                    )
                    df.to_excel(excel_buffer, index=False)
                    excel_buffer.save()
                    
                    with open(excel_buffer.path, "rb") as f:
                        st.download_button(
                            f"{get_text('save')} Excel",
                            f,
                            f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"download_excel_{key_suffix}"
                        )
                
                st.success(get_text("export_success"))
                
            except Exception as e:
                st.error(f"{get_text('export_failed')}: {str(e)}")
        else:
            st.warning(get_text("no_data"))

def delete_product(asin: str) -> bool:
    """删除商品"""
    try:
        response = requests.delete(f"{API_BASE_URL}/api/products/{asin}")
        success = response.status_code == 200
        if success:
            # 清除相关缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('delete_failed')}: {str(e)}")
        return False

def batch_delete_products(products: List[Dict]) -> Dict[str, int]:
    """批量删除商品"""
    try:
        asins = [product["asin"] for product in products]
        response = requests.post(
            f"{API_BASE_URL}/api/products/batch-delete",
            json={"asins": asins}
        )
        
        if response.status_code == 200:
            result = response.json()
            # 清除相关缓存
            cache_manager.clear_cache()
            return result
        return {"success_count": 0, "fail_count": len(asins)}
    except Exception as e:
        st.error(f"{get_text('delete_failed')}: {str(e)}")
        return {"success_count": 0, "fail_count": len(asins)}

def load_category_stats() -> Dict[str, Dict[str, int]]:
    """加载类别统计信息"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/categories/stats")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"加载类别统计信息失败: {str(e)}")
        return {
            "main_categories": {},
            "sub_categories": {},
            "bindings": {},
            "product_groups": {}
        }

def render_category_filter(category_stats: Dict[str, Dict[str, int]]) -> Dict[str, List[str]]:
    """渲染类别筛选组件"""
    selected_categories = {
        "main_categories": [],
        "sub_categories": [],
        "bindings": [],
        "product_groups": []
    }
    
    with st.sidebar:
        st.subheader("类别筛选")
        
        # 主要类别多选
        if category_stats["main_categories"]:
            with st.expander("主要类别", expanded=True):
                for category, count in category_stats["main_categories"].items():
                    if st.checkbox(f"{category} ({count})", key=f"main_{category}"):
                        selected_categories["main_categories"].append(category)
        
        # 子类别多选（按主类别分组显示）
        if category_stats["sub_categories"]:
            with st.expander("子类别", expanded=True):
                # 按主类别分组
                sub_categories_by_main = {}
                for sub_path, count in category_stats["sub_categories"].items():
                    main_cat, sub_cat = sub_path.split(":")
                    if main_cat not in sub_categories_by_main:
                        sub_categories_by_main[main_cat] = []
                    sub_categories_by_main[main_cat].append((sub_cat, count))
                
                # 显示分组的子类别
                for main_cat, sub_cats in sub_categories_by_main.items():
                    with st.expander(main_cat):
                        for sub_cat, count in sub_cats:
                            if st.checkbox(f"{sub_cat} ({count})", key=f"sub_{main_cat}_{sub_cat}"):
                                selected_categories["sub_categories"].append(f"{main_cat}:{sub_cat}")
        
        # 商品绑定类型多选
        if category_stats["bindings"]:
            with st.expander("商品绑定类型"):
                for binding, count in category_stats["bindings"].items():
                    if st.checkbox(f"{binding} ({count})", key=f"binding_{binding}"):
                        selected_categories["bindings"].append(binding)
        
        # 商品组多选
        if category_stats["product_groups"]:
            with st.expander("商品组"):
                for group, count in category_stats["product_groups"].items():
                    if st.checkbox(f"{group} ({count})", key=f"group_{group}"):
                        selected_categories["product_groups"].append(group)
    
    # 如果没有选择任何类别，返回None
    if not any(selected_categories.values()):
        return None
    
    return selected_categories

def render_products_page():
    """渲染商品列表页面"""
    st.title("商品列表")
    
    # 加载类别统计信息
    category_stats = load_category_stats()
    
    # 渲染类别筛选组件
    selected_categories = render_category_filter(category_stats)
    
    # 其他筛选条件
    with st.sidebar:
        st.subheader("筛选条件")
        
        # 添加数据源筛选
        source_filter = st.selectbox(
            "数据来源",
            options=["all", "pa-api", "cj"],
            format_func=lambda x: {
                "all": "全部来源",
                "pa-api": "Amazon API",
                "cj": "CJ API"
            }[x]
        )
        
        col1, col2 = st.columns(2)
        with col1:
            min_price = st.number_input("最低价格", min_value=0.0, value=0.0)
        with col2:
            max_price = st.number_input("最高价格", min_value=0.0, value=9999.0)
            
        min_discount = st.slider("最低折扣率", min_value=0, max_value=100, value=0)
        is_prime_only = st.checkbox("只显示Prime商品")
        
        # 添加CJ佣金筛选
        min_commission = None
        if source_filter in ["all", "cj"]:
            min_commission = st.slider("最低佣金比例", min_value=0, max_value=100, value=0)
        
        sort_by = st.selectbox(
            "排序方式",
            options=[None, "price", "discount", "timestamp", "commission"],
            format_func=lambda x: {
                None: "默认排序",
                "price": "按价格",
                "discount": "按折扣",
                "timestamp": "按时间",
                "commission": "按佣金"
            }[x]
        )
        
        sort_order = st.selectbox(
            "排序方向",
            options=["desc", "asc"],
            format_func=lambda x: "降序" if x == "desc" else "升序"
        )
        
        page_size = st.selectbox(
            "每页显示数量",
            options=[10, 20, 50, 100],
            index=1
        )
    
    # 创建标签页
    tab_discount, tab_coupon = st.tabs([
        "🏷️ 折扣商品",
        "🎫 优惠券商品"
    ])
    
    # 处理折扣商品标签页
    with tab_discount:
        # 分页控制
        if "discount_page" not in st.session_state:
            st.session_state.discount_page = 1
        
        # 加载折扣商品数据
        discount_products = load_products(
            product_type="discount",
            page=st.session_state.discount_page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            prime_only=is_prime_only,
            sort_by=sort_by,
            sort_order=sort_order,
            selected_categories=selected_categories,
            source_filter=source_filter,
            min_commission=min_commission
        )
        
        # 显示折扣商品
        display_products(discount_products, API_BASE_URL, "discount")
        
        # 处理分页
        if discount_products and discount_products.get("total", 0) > 0:
            total_pages = (discount_products["total"] + page_size - 1) // page_size
            
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                if st.session_state.discount_page > 1:
                    if st.button("上一页", key="discount_prev"):
                        st.session_state.discount_page -= 1
                        st.rerun()
            
            with col2:
                st.write(f"第 {st.session_state.discount_page} 页 / 共 {total_pages} 页")
            
            with col3:
                if st.session_state.discount_page < total_pages:
                    if st.button("下一页", key="discount_next"):
                        st.session_state.discount_page += 1
                        st.rerun()
    
    # 处理优惠券商品标签页
    with tab_coupon:
        # 分页控制
        if "coupon_page" not in st.session_state:
            st.session_state.coupon_page = 1
        
        # 加载优惠券商品数据
        coupon_products = load_products(
            product_type="coupon",
            page=st.session_state.coupon_page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            prime_only=is_prime_only,
            sort_by=sort_by,
            sort_order=sort_order,
            selected_categories=selected_categories,
            source_filter=source_filter,
            min_commission=min_commission
        )
        
        # 显示优惠券商品
        display_products(coupon_products, API_BASE_URL, "coupon")
        
        # 处理分页
        if coupon_products and coupon_products.get("total", 0) > 0:
            total_pages = (coupon_products["total"] + page_size - 1) // page_size
            
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                if st.session_state.coupon_page > 1:
                    if st.button("上一页", key="coupon_prev"):
                        st.session_state.coupon_page -= 1
                        st.rerun()
            
            with col2:
                st.write(f"第 {st.session_state.coupon_page} 页 / 共 {total_pages} 页")
            
            with col3:
                if st.session_state.coupon_page < total_pages:
                    if st.button("下一页", key="coupon_next"):
                        st.session_state.coupon_page += 1
                        st.rerun()

if __name__ == "__main__":
    render_products_page() 