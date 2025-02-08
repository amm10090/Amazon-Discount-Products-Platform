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
from utils.cache_manager import cache_manager
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
    .category-breadcrumb {{
        font-size: 0.9em;
        color: #666;
        margin-bottom: 10px;
        padding: 5px 10px;
        background-color: #f8f9fa;
        border-radius: 4px;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 4px;
    }}
    .category-breadcrumb .category-link {{
        color: #0066c0;
        text-decoration: none;
        padding: 2px 8px;
        background-color: #fff;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s ease;
    }}
    .category-breadcrumb .category-link:hover {{
        text-decoration: none;
        background-color: #f0f2f6;
        border-color: #0066c0;
    }}
    .category-breadcrumb .category-separator {{
        color: #666;
        margin: 0 4px;
    }}
    .category-tag {{
        display: inline-block;
        background-color: #f0f2f6;
        color: #666;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85em;
        margin: 4px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s ease;
    }}
    .category-tag:hover {{
        background-color: #e9ecef;
        border-color: #0066c0;
        color: #0066c0;
    }}
    .category-section {{
        margin: 10px 0;
        padding: 15px;
        background-color: #f8f9fa;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
    }}
    .category-title {{
        font-size: 0.95em;
        color: #333;
        margin-bottom: 10px;
        font-weight: 500;
    }}
    .category-content {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: flex-start;
    }}
    .price-tag {{
        color: #B12704;
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 8px;
    }}
    .original-price {{
        color: #666;
        text-decoration: line-through;
        font-size: 0.9em;
    }}
    .current-price {{
        color: #B12704;
        font-size: 1.3em;
        font-weight: bold;
    }}
    .discount-tag {{
        color: #067D62;
        font-weight: bold;
        background-color: #E3F4F4;
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
        margin-top: 4px;
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

@cache_manager.data_cache(
    ttl=300,
    show_spinner="正在加载商品数据..."
)
def load_products(
    api_url: str,
    product_type: str = "all",
    page: int = 1,
    page_size: int = 20,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_discount: Optional[int] = None,
    prime_only: bool = False,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    selected_categories: Optional[Dict[str, List[str]]] = None
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
        
        # 移除None值的参数
        params = {k: v for k, v in params.items() if v is not None}
        
        # 根据商品类型选择不同的API端点
        if product_type == "discount":
            endpoint = "/api/products/discount"
        elif product_type == "coupon":
            endpoint = "/api/products/coupon"
        else:
            endpoint = "/api/products/list"
        
        response = requests.get(f"{api_url}{endpoint}", params=params)
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
    """显示商品列表
    
    Args:
        products_data: 包含商品列表和分页信息的字典
        api_url: API服务地址
        key_suffix: 状态键后缀
    """
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
    
    # 添加批量删除功能
    st.markdown("### " + get_text("product_list"))
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button(
            "🗑️ " + get_text("delete_all"),
            key=f"delete_all_{key_suffix}"
        ):
            if st.warning(get_text("confirm_delete_all")):
                result = batch_delete_products(api_url, products)
                if result["success_count"] > 0:
                    st.success(
                        get_text("batch_delete_success").format(
                            success_count=result["success_count"]
                        )
                    )
                if result["fail_count"] > 0:
                    st.error(
                        get_text("batch_delete_failed").format(
                            fail_count=result["fail_count"]
                        )
                    )
                st.rerun()
    
    # 显示商品列表
    for product in products:
        with st.container():
            # 显示分类导航
            breadcrumb_html = '<div class="category-breadcrumb">'
            
            # 优先使用browse_nodes，因为它包含完整的层级结构
            if product.get("browse_nodes") and len(product.get("browse_nodes", [])) > 0:
                # 获取第一个浏览节点
                browse_node = product["browse_nodes"][0]
                breadcrumb_categories = []
                
                # 递归获取祖先节点
                def get_ancestors(node):
                    if not node:
                        return
                    # 检查不同的名称字段
                    node_name = (
                        node.get("display_name") or 
                        node.get("DisplayName") or 
                        node.get("context_free_name") or 
                        node.get("ContextFreeName") or 
                        node.get("name")
                    )
                    if node_name:
                        breadcrumb_categories.insert(0, node_name)
                    # 检查祖先节点
                    ancestor = node.get("ancestor") or node.get("Ancestor")
                    if ancestor:
                        get_ancestors(ancestor)
                
                # 添加当前节点
                current_name = (
                    browse_node.get("display_name") or 
                    browse_node.get("DisplayName") or 
                    browse_node.get("context_free_name") or 
                    browse_node.get("ContextFreeName") or 
                    browse_node.get("name")
                )
                if current_name:
                    breadcrumb_categories.append(current_name)
                
                # 获取所有祖先节点
                ancestor = browse_node.get("ancestor") or browse_node.get("Ancestor")
                if ancestor:
                    get_ancestors(ancestor)
                
                # 生成面包屑导航
                if breadcrumb_categories:
                    for i, cat in enumerate(breadcrumb_categories):
                        breadcrumb_html += f'<span class="category-link">{cat.strip()}</span>'
                        if i < len(breadcrumb_categories) - 1:
                            breadcrumb_html += '<span class="category-separator">›</span>'
            
            # 如果没有browse_nodes，使用categories字段
            elif product.get("categories") and len(product["categories"]) > 0:
                categories = product["categories"][0].split(" > ") if isinstance(product["categories"][0], str) else []
                if categories:
                    for i, cat in enumerate(categories):
                        breadcrumb_html += f'<span class="category-link">{cat.strip()}</span>'
                        if i < len(categories) - 1:
                            breadcrumb_html += '<span class="category-separator">›</span>'
            
            # 如果前两者都没有，使用binding和product_group组合
            elif product.get("binding") or product.get("product_group"):
                if product.get("product_group"):
                    breadcrumb_html += f'<span class="category-link">{product["product_group"]}</span>'
                    if product.get("binding"):
                        breadcrumb_html += '<span class="category-separator">›</span>'
                if product.get("binding"):
                    breadcrumb_html += f'<span class="category-link">{product["binding"]}</span>'
            
            breadcrumb_html += '</div>'
            
            # 只有当有分类信息时才显示面包屑
            if '>' in breadcrumb_html or 'category-link' in breadcrumb_html:
                st.markdown(breadcrumb_html, unsafe_allow_html=True)
            
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
                
                # 商品变体信息
                if product.get("variants") and len(product["variants"]) > 0:
                    with st.expander("查看商品变体"):
                        for variant in product["variants"]:
                            st.markdown("---")
                            cols = st.columns([1, 2, 1])
                            
                            with cols[0]:
                                if variant.get("image"):
                                    st.image(
                                        variant["image"],
                                        caption=variant.get("asin"),
                                        use_container_width=True
                                    )
                            
                            with cols[1]:
                                st.markdown(f"**{variant.get('product_name', '未知变体')}**")
                                
                                # 变体价格信息
                                if variant.get("original_price") and variant.get("discount_price"):
                                    original_price = float(variant["original_price"].replace("$", "")) if isinstance(variant["original_price"], str) else variant["original_price"]
                                    discount_price = float(variant["discount_price"].replace("$", "")) if isinstance(variant["discount_price"], str) else variant["discount_price"]
                                    
                                    if original_price > discount_price:
                                        discount_percentage = ((original_price - discount_price) / original_price) * 100
                                        st.markdown(
                                            f'''
                                            <div class="price-tag">
                                                <div class="original-price">${original_price:.2f}</div>
                                                <div class="current-price">${discount_price:.2f}</div>
                                                <div class="discount-tag">-{discount_percentage:.0f}% OFF</div>
                                            </div>
                                            ''',
                                            unsafe_allow_html=True
                                        )
                                    else:
                                        st.markdown(
                                            f'<div class="current-price">${discount_price:.2f}</div>',
                                            unsafe_allow_html=True
                                        )
                            
                            with cols[2]:
                                if variant.get("url"):
                                    st.markdown(f"[🔗 查看详情]({variant['url']})")
                                if variant.get("affiliate_url"):
                                    st.markdown(f"[🔗 推广链接]({variant['affiliate_url']})")
                
                # 商品分类信息
                with st.expander(get_text("product_category")):
                    st.markdown('<div class="category-section">', unsafe_allow_html=True)
                    
                    # 显示绑定类型和产品组
                    if product.get("binding") or product.get("product_group"):
                        st.markdown('<div class="category-title">基本分类</div>', unsafe_allow_html=True)
                        st.markdown('<div class="category-content">', unsafe_allow_html=True)
                        if product.get("binding"):
                            st.markdown(f'<span class="category-tag">📦 {product["binding"]}</span>', unsafe_allow_html=True)
                        if product.get("product_group"):
                            st.markdown(f'<span class="category-tag">🏷️ {product["product_group"]}</span>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    # 显示分类路径
                    if product.get("categories") and len(product["categories"]) > 0:
                        st.markdown('<div class="category-title">详细分类</div>', unsafe_allow_html=True)
                        st.markdown('<div class="category-content">', unsafe_allow_html=True)
                        for category_path in product["categories"]:
                            categories = category_path.split(" > ") if isinstance(category_path, str) else []
                            for category in categories:
                                st.markdown(f'<span class="category-tag">📑 {category.strip()}</span>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    # 显示浏览节点信息
                    if product.get("browse_nodes"):
                        st.markdown('<div class="category-title">浏览节点</div>', unsafe_allow_html=True)
                        st.markdown('<div class="category-content">', unsafe_allow_html=True)
                        for node in product["browse_nodes"]:
                            node_name = node.get('name', '')
                            node_id = node.get('id', '')
                            if node_name and node_id:
                                st.markdown(
                                    f'<span class="category-tag">🔍 {node_name} ({node_id})</span>',
                                    unsafe_allow_html=True
                                )
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # 价格和折扣信息
                price_col, discount_col, prime_col = st.columns(3)
                
                with price_col:
                    try:
                        # 获取价格信息
                        if isinstance(product.get("offers"), list) and len(product["offers"]) > 0:
                            offer = product["offers"][0]
                            price = offer.get("price")
                            savings = offer.get("savings")
                            savings_percentage = offer.get("savings_percentage")
                            currency = offer.get("currency", "USD")
                            
                            if price is not None and price != "":
                                try:
                                    price = float(price)
                                    savings = float(savings) if savings is not None else 0
                                    savings_percentage = float(savings_percentage) if savings_percentage is not None else 0
                                    
                                    # 计算原价
                                    original_price = price + savings if savings > 0 else price
                                    
                                    # 显示价格信息
                                    if savings > 0 and savings_percentage > 0:
                                        st.markdown(
                                            f'''
                                            <div class="price-tag">
                                                <div class="original-price">${original_price:.2f} {currency}</div>
                                                <div class="current-price">${price:.2f} {currency}</div>
                                                <div class="discount-tag">-{savings_percentage:.0f}% OFF</div>
                                            </div>
                                            ''',
                                            unsafe_allow_html=True
                                        )
                                    else:
                                        st.markdown(
                                            f'''
                                            <div class="price-tag">
                                                <div class="current-price">${price:.2f} {currency}</div>
                                            </div>
                                            ''',
                                            unsafe_allow_html=True
                                        )
                                except (ValueError, TypeError):
                                    st.markdown(
                                        f'<p class="price-tag">{get_text("price_unavailable")}</p>',
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
                    except Exception as e:
                        st.markdown(
                            f'<p class="price-tag">{get_text("price_unavailable")}</p>',
                            unsafe_allow_html=True
                        )
                
                with discount_col:
                    try:
                        # 获取优惠券信息
                        if isinstance(product.get("offers"), list) and len(product["offers"]) > 0:
                            offer = product["offers"][0]
                            coupon_type = offer.get("coupon_type")
                            coupon_value = offer.get("coupon_value")
                            
                            if coupon_type and coupon_value:
                                # 计算折扣金额和百分比
                                price = float(offer.get("price", 0))
                                if coupon_type == "percentage":
                                    savings = price * (float(coupon_value) / 100)
                                    savings_percentage = float(coupon_value)
                                else:  # fixed
                                    savings = float(coupon_value)
                                    savings_percentage = (savings / price) * 100 if price > 0 else 0
                                
                                # 显示折扣信息
                                if savings > 0:
                                    st.markdown(
                                        f'<p class="discount-tag">'
                                        f'{get_text("save_money")} ${savings:.2f} ({savings_percentage:.0f}%)'
                                        f'</p>',
                                        unsafe_allow_html=True
                                    )
                                
                                # 显示优惠券信息
                                left_text = (
                                    f"{coupon_value}%" 
                                    if coupon_type.lower() == "percentage" 
                                    else f"${coupon_value}"
                                )
                                right_text = (
                                    "OFF" 
                                    if coupon_type.lower() == "percentage" 
                                    else "COUPON"
                                )
                                
                                st.markdown(
                                    f'''
                                    <div class="coupon-card">
                                        <div class="coupon-left">{left_text}</div>
                                        <div class="coupon-right">{right_text}</div>
                                    </div>
                                    ''',
                                    unsafe_allow_html=True
                                )
                    except (ValueError, TypeError, AttributeError) as e:
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
                        if delete_product(api_url, product["asin"]):
                            st.success(get_text("delete_success"))
                            st.rerun()
                
                # 更新时间
                if product.get("timestamp"):
                    st.caption(f"{get_text('update_time')}: {product['timestamp']}")
            
            st.markdown("---")

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

def delete_product(api_url: str, asin: str) -> bool:
    """删除商品
    
    Args:
        api_url: API服务地址
        asin: 商品ASIN
        
    Returns:
        bool: 是否删除成功
    """
    try:
        response = requests.delete(f"{api_url}/api/products/{asin}")
        success = response.status_code == 200
        if success:
            # 清除相关缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('delete_failed')}: {str(e)}")
        return False

def batch_delete_products(api_url: str, products: List[Dict]) -> Dict[str, int]:
    """批量删除商品
    
    Args:
        api_url: API服务地址
        products: 商品列表
        
    Returns:
        Dict[str, int]: 删除结果统计
    """
    try:
        asins = [product["asin"] for product in products]
        response = requests.post(
            f"{api_url}/api/products/batch-delete",
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
        response = requests.get("http://localhost:8000/api/categories/stats")
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
        
        col1, col2 = st.columns(2)
        with col1:
            min_price = st.number_input("最低价格", min_value=0.0, value=0.0)
        with col2:
            max_price = st.number_input("最高价格", min_value=0.0, value=1000.0)
            
        min_discount = st.slider("最低折扣率", min_value=0, max_value=100, value=0)
        is_prime_only = st.checkbox("只显示Prime商品")
        
        sort_by = st.selectbox(
            "排序方式",
            options=[None, "price", "discount", "timestamp"],
            format_func=lambda x: {
                None: "默认排序",
                "price": "按价格",
                "discount": "按折扣",
                "timestamp": "按时间"
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
            api_url="http://localhost:8000",
            product_type="discount",  # 指定为折扣商品
            page=st.session_state.discount_page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            prime_only=is_prime_only,
            sort_by=sort_by,
            sort_order=sort_order,
            selected_categories=selected_categories
        )
        
        # 显示折扣商品
        display_products(discount_products, "http://localhost:8000", "discount")
        
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
            api_url="http://localhost:8000",
            product_type="coupon",  # 指定为优惠券商品
            page=st.session_state.coupon_page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            prime_only=is_prime_only,
            sort_by=sort_by,
            sort_order=sort_order,
            selected_categories=selected_categories
        )
        
        # 显示优惠券商品
        display_products(coupon_products, "http://localhost:8000", "coupon")
        
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