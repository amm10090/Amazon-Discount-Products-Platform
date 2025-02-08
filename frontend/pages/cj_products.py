import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import sys
from pathlib import Path
import yaml
sys.path.append(str(Path(__file__).parent.parent))
from main import load_config
from utils.cache_manager import cache_manager
from i18n import init_language, get_text, language_selector

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
    page_icon="🛍️",
    layout=config["frontend"]["page"]["layout"],
    initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"]
)

# 自定义CSS
st.markdown(f"""
<style>
    .variant-card {{
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
    }}
    .variant-image {{
        max-width: 100px;
        height: auto;
        border-radius: 4px;
    }}
    .variant-title {{
        font-size: 0.9em;
        font-weight: 500;
        margin: 5px 0;
        color: {config["frontend"]["theme"]["textColor"]};
    }}
    .variant-price {{
        color: #B12704;
        font-weight: bold;
    }}
    .variant-original-price {{
        text-decoration: line-through;
        color: {config["frontend"]["theme"]["textColor"]};
        font-size: 0.9em;
    }}
    .variant-discount {{
        background-color: {config["frontend"]["theme"]["primaryColor"]};
        color: white;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.8em;
        display: inline-block;
    }}
    .product-card {{
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
    }}
    .product-image {{
        max-width: 200px;
        height: auto;
        border-radius: 8px;
    }}
    .product-title {{
        font-size: 1.2em;
        font-weight: 500;
        margin: 10px 0;
        color: {config["frontend"]["theme"]["textColor"]};
    }}
    .product-brand {{
        color: {config["frontend"]["theme"]["textColor"]};
        font-size: 0.9em;
    }}
    .product-price {{
        color: #B12704;
        font-size: 1.3em;
        font-weight: bold;
        margin: 10px 0;
    }}
    .product-original-price {{
        text-decoration: line-through;
        color: {config["frontend"]["theme"]["textColor"]};
    }}
    .product-discount {{
        background-color: {config["frontend"]["theme"]["primaryColor"]};
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        margin-left: 10px;
    }}
    .product-rating {{
        color: {config["frontend"]["theme"]["primaryColor"]};
    }}
    .product-reviews {{
        color: {config["frontend"]["theme"]["textColor"]};
        font-size: 0.9em;
    }}
    .product-category {{
        background-color: {config["frontend"]["theme"]["secondaryBackgroundColor"]};
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.9em;
        color: {config["frontend"]["theme"]["textColor"]};
        display: inline-block;
        margin: 5px;
    }}
    .product-commission {{
        color: {config["frontend"]["theme"]["primaryColor"]};
        font-weight: bold;
    }}
    .product-coupon {{
        background-color: {config["frontend"]["theme"]["primaryColor"]};
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
        margin: 5px 0;
        display: inline-block;
    }}
</style>
""", unsafe_allow_html=True)

# 定义API基础URL
API_BASE_URL = f"http://{config['api']['host']}:{config['api']['port']}"

@cache_manager.data_cache(
    ttl=config["frontend"]["cache"]["ttl"],
    show_spinner=get_text("loading_products")
)
def load_cj_products(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    country_code: str = "US",
    brand_id: int = 0,
    is_featured_product: int = 2,
    is_amazon_choice: int = 2,
    have_coupon: int = 2,
    discount_min: int = 0
) -> Dict:
    """加载CJ商品数据"""
    try:
        params = {
            "page": page,
            "page_size": page_size,
            "category": category,
            "subcategory": subcategory,
            "country_code": country_code,
            "brand_id": brand_id,
            "is_featured_product": is_featured_product,
            "is_amazon_choice": is_amazon_choice,
            "have_coupon": have_coupon,
            "discount_min": discount_min
        }
        
        response = requests.get(f"{API_BASE_URL}/api/cj/products", params=params)
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

def display_cj_products(products_data: Dict):
    """显示CJ商品列表"""
    if not products_data or not isinstance(products_data, dict):
        st.warning(get_text("no_matching_products"))
        return
    
    products = products_data.get("items", [])
    total = products_data.get("total", 0)
    current_page = products_data.get("page", 1)
    page_size = products_data.get("page_size", 20)
    
    if len(products) == 0:
        st.info(get_text("no_products"))
        return
    
    # 显示商品总数
    st.success(f"{get_text('total_items')}: {total}")
    
    # 显示商品列表
    for product in products:
        with st.container():
            st.markdown('<div class="product-card">', unsafe_allow_html=True)
            
            cols = st.columns([1, 2])
            
            with cols[0]:
                if product.get("image"):
                    st.image(product["image"], use_container_width=True)
                
                # 显示评分和评论
                if product.get("rating"):
                    st.markdown(
                        f'<div class="product-rating">⭐ {product["rating"]}</div>',
                        unsafe_allow_html=True
                    )
                if product.get("reviews"):
                    st.markdown(
                        f'<div class="product-reviews">{product["reviews"]} {get_text("reviews")}</div>',
                        unsafe_allow_html=True
                    )
            
            with cols[1]:
                # 商品标题
                st.markdown(
                    f'<div class="product-title">{product.get("product_name", get_text("unknown_product"))}</div>',
                    unsafe_allow_html=True
                )
                
                # 品牌信息
                if product.get("brand_name"):
                    st.markdown(
                        f'<div class="product-brand">{get_text("brand")}: {product["brand_name"]}</div>',
                        unsafe_allow_html=True
                    )
                
                # 价格信息
                original_price = float(product["original_price"].replace("$", "")) if isinstance(product["original_price"], str) else product["original_price"]
                discount_price = float(product["discount_price"].replace("$", "")) if isinstance(product["discount_price"], str) else product["discount_price"]
                
                if original_price > discount_price:
                    discount_percentage = ((original_price - discount_price) / original_price) * 100
                    st.markdown(
                        f'''
                        <div class="product-price">
                            <span class="product-original-price">${original_price:.2f}</span>
                            <span>${discount_price:.2f}</span>
                            <span class="product-discount">-{discount_percentage:.0f}% OFF</span>
                        </div>
                        ''',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div class="product-price">${discount_price:.2f}</div>',
                        unsafe_allow_html=True
                    )
                
                # 佣金信息
                if product.get("commission"):
                    st.markdown(
                        f'<div class="product-commission">{get_text("commission")}: {product["commission"]}</div>',
                        unsafe_allow_html=True
                    )
                
                # 优惠券信息
                if product.get("coupon"):
                    st.markdown(
                        f'<div class="product-coupon">{get_text("coupon")}: {product["coupon"]}</div>',
                        unsafe_allow_html=True
                    )
                
                # 分类信息
                if product.get("category") or product.get("subcategory"):
                    st.markdown('<div style="margin: 10px 0;">', unsafe_allow_html=True)
                    if product.get("category"):
                        st.markdown(
                            f'<span class="product-category">{product["category"]}</span>',
                            unsafe_allow_html=True
                        )
                    if product.get("subcategory"):
                        st.markdown(
                            f'<span class="product-category">{product["subcategory"]}</span>',
                            unsafe_allow_html=True
                        )
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # 商品链接
                cols2 = st.columns(2)
                with cols2[0]:
                    if product.get("url"):
                        st.markdown(f"[🔗 {get_text('view_details')}]({product['url']})")
                with cols2[1]:
                    if product.get("affiliate_url"):
                        st.markdown(f"[🔗 {get_text('affiliate_link')}]({product['affiliate_url']})")
            
            # 显示变体信息
            if product.get("variants") and len(product["variants"]) > 0:
                with st.expander(get_text("view_variants")):
                    for variant in product["variants"]:
                        st.markdown('<div class="variant-card">', unsafe_allow_html=True)
                        vcols = st.columns([1, 2, 1])
                        
                        with vcols[0]:
                            if variant.get("image"):
                                st.image(variant["image"], use_container_width=True)
                        
                        with vcols[1]:
                            st.markdown(
                                f'<div class="variant-title">{variant.get("product_name", get_text("unknown_variant"))}</div>',
                                unsafe_allow_html=True
                            )
                            
                            # 变体价格信息
                            v_original_price = float(variant["original_price"].replace("$", "")) if isinstance(variant["original_price"], str) else variant["original_price"]
                            v_discount_price = float(variant["discount_price"].replace("$", "")) if isinstance(variant["discount_price"], str) else variant["discount_price"]
                            
                            if v_original_price > v_discount_price:
                                v_discount_percentage = ((v_original_price - v_discount_price) / v_original_price) * 100
                                st.markdown(
                                    f'''
                                    <div class="variant-price">
                                        <span class="variant-original-price">${v_original_price:.2f}</span>
                                        <span>${v_discount_price:.2f}</span>
                                        <span class="variant-discount">-{v_discount_percentage:.0f}%</span>
                                    </div>
                                    ''',
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f'<div class="variant-price">${v_discount_price:.2f}</div>',
                                    unsafe_allow_html=True
                                )
                        
                        with vcols[2]:
                            if variant.get("url"):
                                st.markdown(f"[🔗 {get_text('view_details')}]({variant['url']})")
                            if variant.get("affiliate_url"):
                                st.markdown(f"[🔗 {get_text('affiliate_link')}]({variant['affiliate_url']})")
                        
                        st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")

def render_cj_products_page():
    """渲染CJ商品列表页面"""
    st.title(get_text("cj_products_title"))
    
    # 侧边栏筛选条件
    with st.sidebar:
        # 语言选择器
        language_selector()
        st.markdown("---")
        
        st.subheader(get_text("filter_conditions"))
        
        # 分类筛选
        category = st.selectbox(
            get_text("select_main_category"),
            options=[None, "Home & Kitchen", "Pet Supplies", "Clothing, Shoes & Jewelry"],
            format_func=lambda x: get_text("all_categories") if x is None else x
        )
        
        subcategory = st.selectbox(
            get_text("select_subcategory"),
            options=[None, "Chairs", "Storage Cabinets", "Trees", "Basic Crates"],
            format_func=lambda x: get_text("all_subcategories") if x is None else x
        )
        
        # 其他筛选条件
        is_featured = st.selectbox(
            get_text("featured_products"),
            options=[2, 1, 0],
            format_func=lambda x: get_text("all") if x == 2 else (get_text("yes") if x == 1 else get_text("no"))
        )
        
        is_amazon_choice = st.selectbox(
            get_text("amazon_choice"),
            options=[2, 1, 0],
            format_func=lambda x: get_text("all") if x == 2 else (get_text("yes") if x == 1 else get_text("no"))
        )
        
        have_coupon = st.selectbox(
            get_text("coupon"),
            options=[2, 1, 0],
            format_func=lambda x: get_text("all") if x == 2 else (get_text("has_coupon") if x == 1 else get_text("no_coupon"))
        )
        
        discount_min = st.slider(get_text("min_discount_rate"), 0, 100, 0)
        
        page_size = st.selectbox(
            get_text("items_per_page"),
            options=[10, 20, 50],
            index=1
        )
    
    # 分页控制
    if "cj_page" not in st.session_state:
        st.session_state.cj_page = 1
    
    # 加载商品数据
    products_data = load_cj_products(
        page=st.session_state.cj_page,
        page_size=page_size,
        category=category,
        subcategory=subcategory,
        is_featured_product=is_featured,
        is_amazon_choice=is_amazon_choice,
        have_coupon=have_coupon,
        discount_min=discount_min
    )
    
    # 显示商品列表
    display_cj_products(products_data)
    
    # 分页控制
    if products_data and products_data.get("total", 0) > 0:
        total_pages = (products_data["total"] + page_size - 1) // page_size
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if st.session_state.cj_page > 1:
                if st.button(get_text("prev_page")):
                    st.session_state.cj_page -= 1
                    st.rerun()
        
        with col2:
            st.write(get_text("page_info").format(current=st.session_state.cj_page, total=total_pages))
        
        with col3:
            if st.session_state.cj_page < total_pages:
                if st.button(get_text("next_page")):
                    st.session_state.cj_page += 1
                    st.rerun()

if __name__ == "__main__":
    render_cj_products_page() 