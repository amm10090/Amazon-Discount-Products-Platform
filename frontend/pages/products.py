import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import json
from i18n import init_language, get_text, language_selector
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from main import load_config
from typing import List, Dict, Optional

# 加载配置
config = load_config()

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
    .product-card {{
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
    }}
    .product-image {{
        max-width: 200px;
        height: auto;
    }}
    .price-tag {{
        color: #B12704;
        font-size: 1.2em;
        font-weight: bold;
    }}
    .discount-tag {{
        color: #067D62;
        font-weight: bold;
    }}
    .prime-tag {{
        color: #00A8E1;
        font-weight: bold;
    }}
    .coupon-tag {{
        background: #FF9900;
        color: white;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
        position: relative;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    .coupon-tag::before,
    .coupon-tag::after {{
        content: '';
        position: absolute;
        top: 0;
        width: 10px;
        height: 100%;
        background: radial-gradient(circle at 0 50%, transparent 8px, white 8px) repeat-y;
        background-size: 10px 16px;
    }}
    .coupon-tag::before {{
        left: -10px;
        transform: translateX(1px);
    }}
    .coupon-tag::after {{
        right: -10px;
        transform: translateX(-1px) scaleX(-1);
    }}
    .coupon-value {{
        font-size: 1.2em;
        display: block;
        margin-top: 4px;
    }}
    .coupon-type {{
        font-size: 0.9em;
        opacity: 0.9;
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
    .stTabs [data-baseweb="tab-list"] {{
        gap: 24px;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        white-space: pre-wrap;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
        border-radius: 4px;
        padding: 10px 20px;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {config["frontend"]["theme"]["primaryColor"]};
        color: white;
    }}
    .coupon-card {{
        display: flex;
        width: 180px;
        height: 28px;
        margin: 5px 0;
        position: relative;
        border-radius: 2px;
        overflow: hidden;
    }}
    
    .coupon-left {{
        width: 70px;
        text-align: center;
        font-size: 15px;
        font-weight: 500;
        color: white;
        background: #FF9900;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
    }}
    
    .coupon-right {{
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 13px;
        font-weight: 400;
        background: #FF5722;
        position: relative;
        margin-left: 1px;
    }}
    
    .coupon-right::before {{
        content: "";
        position: absolute;
        left: -4px;
        top: 0;
        bottom: 0;
        width: 8px;
        background: linear-gradient(90deg, transparent 0%, #FF5722 100%);
    }}
    
    .coupon-left::after {{
        content: "";
        position: absolute;
        right: -4px;
        top: 0;
        bottom: 0;
        width: 8px;
        background: linear-gradient(90deg, #FF9900 0%, transparent 100%);
    }}
</style>
""", unsafe_allow_html=True)

# 侧边栏
with st.sidebar:
    # 语言选择器
    language_selector()
    st.markdown("---")

st.title("📦 " + get_text("products_title"))

# 创建标签页
tab_discount, tab_coupon = st.tabs([
    "🏷️ " + get_text("discount_products"),
    "🎫 " + get_text("coupon_products")
])

def create_filter_sidebar(key_suffix: str = "") -> dict:
    """创建筛选边栏
    
    Args:
        key_suffix: 用于区分不同标签页的状态键后缀
        
    Returns:
        dict: 筛选条件字典
    """
    st.sidebar.subheader(get_text("filter_conditions"))
    
    # 价格范围
    price_range = st.sidebar.slider(
        get_text("price_range") + " ($)",
        min_value=0,
        max_value=1000,
        value=(0, 1000),
        step=10,
        key=f"price_range_{key_suffix}"
    )
    
    # 最低折扣率
    min_discount = st.sidebar.slider(
        get_text("min_discount_rate") + " (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        key=f"min_discount_{key_suffix}"
    )
    
    # 是否只显示Prime商品
    prime_only = st.sidebar.checkbox(
        get_text("prime_only"),
        key=f"prime_only_{key_suffix}"
    )
    
    # 排序方式
    sort_by = st.sidebar.selectbox(
        get_text("sort_by"),
        options=[
            "price_asc", "price_desc",
            "discount_asc", "discount_desc",
            "time_asc", "time_desc"
        ],
        format_func=lambda x: {
            "price_asc": get_text("price_low_to_high"),
            "price_desc": get_text("price_high_to_low"),
            "discount_asc": get_text("discount_low_to_high"),
            "discount_desc": get_text("discount_high_to_low"),
            "time_asc": get_text("time_old_to_new"),
            "time_desc": get_text("time_new_to_old")
        }[x],
        key=f"sort_by_{key_suffix}"
    )
    
    # 每页显示数量
    page_size = st.sidebar.selectbox(
        get_text("items_per_page"),
        options=[10, 20, 50, 100],
        index=1,
        key=f"page_size_{key_suffix}"
    )
    
    return {
        "price_range": price_range,
        "min_discount": min_discount,
        "prime_only": prime_only,
        "sort_by": sort_by,
        "page_size": page_size
    }

@st.cache_data(ttl=config["frontend"]["cache"]["ttl"])
def load_products(
    product_type: str,
    page: int,
    page_size: int,
    min_price: float,
    max_price: float,
    min_discount: int,
    prime_only: bool,
    sort_by: str
) -> List[Dict]:
    """加载商品数据"""
    try:
        # 解析排序参数
        sort_field = sort_by.split("_")[0]
        sort_order = sort_by.split("_")[1]
        
        params = {
            "page": page,
            "page_size": page_size,
            "min_price": min_price,
            "max_price": max_price,
            "min_discount": min_discount,
            "is_prime_only": prime_only,
            "sort_by": sort_field,
            "sort_order": sort_order,
            "product_type": product_type
        }
        
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(
            f"{api_url}/api/products/list",
            params=params
        )
        
        if response.status_code == 200:
            products = response.json()
            
            # 如果是优惠券商品，确保每个商品都有优惠券信息
            if product_type == "coupon":
                products = [p for p in products if any(
                    offer.get("coupon_type") is not None or  # 检查优惠券类型
                    any(ch.get("type") is not None for ch in offer.get("coupon_history", []))  # 检查优惠券历史
                    for offer in p.get("offers", [])
                    if isinstance(offer, dict)
                )]
            return products
            
        st.error(f"API请求失败: {response.status_code}")
        try:
            error_detail = response.json()
            st.error(f"错误详情: {error_detail}")
        except:
            st.error("无法解析错误详情")
        return []
        
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return []

def display_products(products: List[Dict], key_suffix: str = ""):
    """显示商品列表"""
    if not products:
        st.warning(get_text("no_matching_products"))
        return
    
    if len(products) == 0:
        st.info(get_text("no_products"))
        return
        
    # 显示商品总数
    st.success(f"{get_text('total_items')}: {len(products)}")
    
    # 添加批量删除功能
    st.markdown("### " + get_text("product_list"))
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button(
            "🗑️ " + get_text("delete_all"),
            key=f"delete_all_{key_suffix}"
        ):
            if st.warning(get_text("confirm_delete_all")):
                batch_delete_products(products)

    # 显示商品列表
    for product in products:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                if product.get("main_image"):
                    st.image(
                        product["main_image"],
                        caption=product.get("asin"),
                        use_container_width=True
                    )
                else:
                    st.markdown("🖼️ " + get_text("no_image"))
            
            with col2:
                st.markdown(f"### {product.get('title', get_text('unknown_product'))}")
                
                # 品牌信息
                if product.get("brand"):
                    st.markdown(f"**{get_text('brand')}:** {product['brand']}")
                
                # 价格和折扣信息
                price_col, discount_col, prime_col = st.columns(3)
                
                with price_col:
                    try:
                        offers = product.get("offers", [])
                        if offers and isinstance(offers, list) and len(offers) > 0:
                            price = float(offers[0].get("price", 0))
                            savings = float(offers[0].get("savings", 0))
                            original_price = price + savings
                            currency = offers[0].get("currency", "USD")
                            
                            if price > 0:
                                st.markdown(
                                    f'<p class="price-tag">'
                                    f'<span style="text-decoration: line-through; color: #666;">${original_price:.2f}</span><br/>'
                                    f'<span style="color: #B12704; font-size: 1.2em;">${price:.2f}</span> {currency}'
                                    f'</p>',
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f'<p class="price-tag">{get_text("price_unavailable")}</p>',
                                    unsafe_allow_html=True
                                )
                    except (ValueError, TypeError):
                        st.markdown(
                            f'<p class="price-tag">{get_text("price_unavailable")}</p>',
                            unsafe_allow_html=True
                        )
                
                with discount_col:
                    try:
                        offers = product.get("offers", [])
                        if offers and isinstance(offers, list) and len(offers) > 0:
                            savings_percentage = float(offers[0].get("savings_percentage", 0))
                            savings = float(offers[0].get("savings", 0))
                            if savings_percentage > 0:
                                st.markdown(
                                    f'<p class="discount-tag">'
                                    f'{get_text("save_money")} ${savings:.2f} ({savings_percentage:.0f}%)'
                                    f'</p>',
                                    unsafe_allow_html=True
                                )
                            
                            # 显示优惠券信息
                            coupon_type = offers[0].get("coupon_type")
                            coupon_value = offers[0].get("coupon_value")
                            
                            if coupon_type and coupon_value:
                                # 根据优惠券类型构建显示内容
                                if coupon_type.lower() == "percentage":
                                    left_text = f"{coupon_value}%"
                                    right_text = "Percentage"
                                else:
                                    left_text = f"${coupon_value}"
                                    right_text = "Fixed"
                                
                                st.markdown(
                                    f'''
                                    <div class="coupon-card">
                                        <div class="coupon-left">{left_text}</div>
                                        <div class="coupon-right">{right_text}</div>
                                    </div>
                                    ''',
                                    unsafe_allow_html=True
                                )
                    except (ValueError, TypeError):
                        pass
                
                with prime_col:
                    try:
                        offers = product.get("offers", [])
                        if offers and isinstance(offers, list) and len(offers) > 0:
                            is_prime = offers[0].get("is_prime", False)
                            if is_prime:
                                st.markdown(
                                    '<p class="prime-tag">✓ Prime</p>',
                                    unsafe_allow_html=True
                                )
                    except (ValueError, TypeError):
                        pass
            
            with col3:
                # 商品链接和删除按钮
                if product.get("url"):
                    st.markdown(f"[🔗 {get_text('view_details')}]({product['url']})")
                
                # 删除按钮
                if st.button(
                    f"🗑️ {get_text('delete')}",
                    key=f"delete_{product['asin']}_{key_suffix}",
                    type="secondary"
                ):
                    if st.warning(get_text("confirm_delete")):
                        delete_product(product["asin"])
                
                # 更新时间
                if product.get("timestamp"):
                    st.caption(f"{get_text('update_time')}: {product['timestamp']}")
            
            st.markdown("---")

def handle_pagination(total_items: int, page: int, page_size: int, key_suffix: str = ""):
    """处理分页
    
    Args:
        total_items: 总商品数
        page: 当前页码
        page_size: 每页数量
        key_suffix: 用于区分不同标签页的状态键后缀
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

def handle_export(products: List[Dict], key_suffix: str = ""):
    """处理数据导出
    
    Args:
        products: 商品列表
        key_suffix: 用于区分不同标签页的状态键后缀
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

# 处理折扣商品标签页
with tab_discount:
    # 获取折扣商品的筛选条件
    discount_filters = create_filter_sidebar("discount")
    
    # 分页控制
    discount_page = st.number_input(
        get_text("page"),
        min_value=1,
        value=1,
        step=1,
        key="page_discount"
    )
    
    # 加载折扣商品数据
    discount_products = load_products(
        product_type="discount",
        page=discount_page,
        page_size=discount_filters["page_size"],
        min_price=discount_filters["price_range"][0],
        max_price=discount_filters["price_range"][1],
        min_discount=discount_filters["min_discount"],
        prime_only=discount_filters["prime_only"],
        sort_by=discount_filters["sort_by"]
    )
    
    # 显示折扣商品
    display_products(discount_products, "discount")
    
    # 处理分页
    discount_page = handle_pagination(
        len(discount_products),
        discount_page,
        discount_filters["page_size"],
        "discount"
    )
    
    # 处理导出
    handle_export(discount_products, "discount")

# 处理优惠券商品标签页
with tab_coupon:
    # 获取优惠券商品的筛选条件
    coupon_filters = create_filter_sidebar("coupon")
    
    # 分页控制
    coupon_page = st.number_input(
        get_text("page"),
        min_value=1,
        value=1,
        step=1,
        key="page_coupon"
    )
    
    # 加载优惠券商品数据
    coupon_products = load_products(
        product_type="coupon",
        page=coupon_page,
        page_size=coupon_filters["page_size"],
        min_price=coupon_filters["price_range"][0],
        max_price=coupon_filters["price_range"][1],
        min_discount=coupon_filters["min_discount"],
        prime_only=coupon_filters["prime_only"],
        sort_by=coupon_filters["sort_by"]
    )
    
    # 显示优惠券商品
    display_products(coupon_products, "coupon")
    
    # 处理分页
    coupon_page = handle_pagination(
        len(coupon_products),
        coupon_page,
        coupon_filters["page_size"],
        "coupon"
    )
    
    # 处理导出
    handle_export(coupon_products, "coupon")

# 删除商品
def delete_product(asin: str):
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.delete(f"{api_url}/api/products/{asin}")
        
        if response.status_code == 200:
            st.success(get_text("delete_success"))
            # 清除缓存以刷新商品列表
            load_products.clear()
            # 重新加载页面
            st.rerun()
        else:
            st.error(f"{get_text('delete_failed')}: {response.json().get('detail', '')}")
    except Exception as e:
        st.error(f"{get_text('delete_failed')}: {str(e)}")

# 批量删除商品
def batch_delete_products(products: List[Dict]):
    try:
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        asins = [product["asin"] for product in products]
        
        response = requests.post(
            f"{api_url}/api/products/batch-delete",
            json={"asins": asins}
        )
        
        if response.status_code == 200:
            result = response.json()
            success_count = result.get("success_count", 0)
            fail_count = result.get("fail_count", 0)
            
            if success_count > 0:
                st.success(get_text("batch_delete_success").format(success_count=success_count))
            if fail_count > 0:
                st.error(get_text("batch_delete_failed").format(fail_count=fail_count))
                
            # 清除缓存并刷新页面
            load_products.clear()
            st.rerun()
        else:
            st.error(f"{get_text('delete_failed')}: {response.json().get('detail', '')}")
    except Exception as e:
        st.error(f"{get_text('delete_failed')}: {str(e)}") 