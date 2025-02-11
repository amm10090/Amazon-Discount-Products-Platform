"""
产品列表页面
"""

import streamlit as st
import yaml
from pathlib import Path
import sys

# 添加项目根目录到Python路径
root_dir = Path(__file__).parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

# 使用绝对导入
from frontend.services.product_service import ProductService
from frontend.components.product_card import render_product_card
from frontend.components.filters import render_category_filter, render_filter_sidebar
from frontend.utils.pagination import handle_pagination
from frontend.utils.export_utils import handle_export
from frontend.utils.cache_manager import cache_manager
from frontend.i18n.language import init_language, get_text

# 初始化语言设置（必须在使用任何翻译功能之前）
init_language()

# 设置页面配置
st.set_page_config(
    page_title=get_text("products_title"),
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 加载配置
def load_yaml_config():
    config_path = root_dir / "config" / "production.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_yaml_config()
API_BASE_URL = f"http://{config['api']['host']}:{config['api']['port']}"
product_service = ProductService(API_BASE_URL)

# 页面标题
st.title(get_text("products_title"))

# 创建标签页
tab_discount, tab_coupon = st.tabs([
    f"🏷️ {get_text('discount_products')}",
    f"🎫 {get_text('coupon_products')}"
])

# 跟踪当前活动的标签页
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "discount"

# 渲染侧边栏筛选条件
with st.sidebar:
    st.title(get_text("filter_conditions"))
    
    # 渲染基本筛选条件
    (
        source_filter,
        min_price,
        max_price,
        min_discount,
        is_prime_only,
        min_commission,
        sort_by,
        sort_order,
        page_size
    ) = render_filter_sidebar()

# 处理折扣商品标签页
with tab_discount:
    # 更新当前活动的标签页
    st.session_state.active_tab = "discount"
    
    # 加载折扣商品数据
    discount_products = product_service.load_products(
        product_type="discount",
        page=st.session_state.get("discount_page", 1),
        page_size=page_size,
        min_price=min_price,
        max_price=max_price,
        min_discount=min_discount,
        prime_only=is_prime_only,
        sort_by=sort_by,
        sort_order=sort_order,
        source_filter=source_filter,
        min_commission=min_commission
    )
    
    # 显示折扣商品
    if discount_products and discount_products.get("items"):
        for product in discount_products["items"]:
            render_product_card(
                product,
                product_service.delete_product,
                "discount"
            )
        
        # 处理分页
        st.session_state.discount_page = handle_pagination(
            discount_products["total"],
            st.session_state.get("discount_page", 1),
            page_size,
            "discount"
        )
        
        # 处理导出
        handle_export(discount_products["items"], "discount")
    else:
        st.info(get_text("no_matching_products"))

# 处理优惠券商品标签页
with tab_coupon:
    # 更新当前活动的标签页
    st.session_state.active_tab = "coupon"
    
    # 加载优惠券商品数据
    coupon_products = product_service.load_products(
        product_type="coupon",
        page=st.session_state.get("coupon_page", 1),
        page_size=page_size,
        min_price=min_price,
        max_price=max_price,
        min_discount=min_discount,
        prime_only=is_prime_only,
        sort_by=sort_by,
        sort_order=sort_order,
        source_filter=source_filter,
        min_commission=min_commission
    )
    
    # 显示优惠券商品
    if coupon_products and coupon_products.get("items"):
        for product in coupon_products["items"]:
            render_product_card(
                product,
                product_service.delete_product,
                "coupon"
            )
        
        # 处理分页
        st.session_state.coupon_page = handle_pagination(
            coupon_products["total"],
            st.session_state.get("coupon_page", 1),
            page_size,
            "coupon"
        )
        
        # 处理导出
        handle_export(coupon_products["items"], "coupon")
    else:
        st.info(get_text("no_matching_products")) 