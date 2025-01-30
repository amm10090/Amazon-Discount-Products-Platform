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

st.title("📦 " + get_text("products_title"))

# 侧边栏筛选器
with st.sidebar:
    st.subheader(get_text("filter_conditions"))
    
    # 价格范围
    price_range = st.slider(
        get_text("price_range") + " ($)",
        min_value=0,
        max_value=1000,
        value=(0, 1000),
        step=10
    )
    
    # 最低折扣率
    min_discount = st.slider(
        get_text("min_discount_rate") + " (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=5
    )
    
    # 是否只显示Prime商品
    prime_only = st.checkbox(get_text("prime_only"))
    
    # 排序方式
    sort_by = st.selectbox(
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
        }[x]
    )
    
    # 每页显示数量
    page_size = st.selectbox(
        get_text("items_per_page"),
        options=[10, 20, 50, 100],
        index=1
    )

# 获取商品数据
@st.cache_data(ttl=config["frontend"]["cache"]["ttl"])
def load_products(
    page: int,
    page_size: int,
    min_price: float,
    max_price: float,
    min_discount: int,
    prime_only: bool,
    sort_by: str
):
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
            "sort_order": sort_order
        }
        
        api_url = f"http://{config['api']['host']}:{config['api']['port']}"
        response = requests.get(
            f"{api_url}/api/products/list",
            params=params
        )
        
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return []

# 分页控制
page = st.number_input(get_text("page"), min_value=1, value=1, step=1)

# 加载商品数据
products = load_products(
    page=page,
    page_size=page_size,
    min_price=price_range[0],
    max_price=price_range[1],
    min_discount=min_discount,
    prime_only=prime_only,
    sort_by=sort_by
)

if products:
    # 显示商品列表
    for product in products:
        with st.container():
            col1, col2 = st.columns([1, 3])
            
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
                        # 获取商品价格信息
                        offers = product.get("offers", [])
                        if offers and isinstance(offers, list) and len(offers) > 0:
                            price = float(offers[0].get("price", 0))
                            savings = float(offers[0].get("savings", 0))
                            original_price = price + savings
                            currency = offers[0].get("currency", "USD")
                            
                            if price > 0:
                                # 显示原价（带删除线）和当前价格
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
                        # 获取折扣信息
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
                    except (ValueError, TypeError):
                        pass
                
                with prime_col:
                    try:
                        # 获取Prime信息
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
                
                # 商品链接
                if product.get("url"):
                    st.markdown(f"[🔗 {get_text('view_details')}]({product['url']})")
                
                # 更新时间
                if product.get("timestamp"):
                    st.caption(f"{get_text('update_time')}: {product['timestamp']}")
                
            st.markdown("---")
    
    # 分页控制
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 1:
            if st.button(get_text("prev_page")):
                page -= 1
    
    with col2:
        total_pages = (len(products) + page_size - 1) // page_size
        st.markdown(get_text("page_info").format(current=page, total=total_pages))
    
    with col3:
        if len(products) == page_size:
            if st.button(get_text("next_page")):
                page += 1

else:
    st.info(get_text("no_matching_products"))

# 导出功能
st.markdown("---")
st.subheader(get_text("export_data"))

export_format = st.selectbox(
    get_text("export_format"),
    options=["CSV", "JSON", "Excel"],
    index=0
)

if st.button(get_text("export_button")):
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
                    "text/csv"
                )
            
            elif export_format == "JSON":
                json_str = df.to_json(orient="records", force_ascii=False)
                st.download_button(
                    f"{get_text('save')} JSON",
                    json_str,
                    f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    "application/json"
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
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            st.success(get_text("export_success"))
            
        except Exception as e:
            st.error(f"{get_text('export_failed')}: {str(e)}")
    else:
        st.warning(get_text("no_data")) 