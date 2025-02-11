"""
产品卡片组件
"""

import streamlit as st
from typing import Dict, Optional
from frontend.i18n.language import get_text

def render_product_card(
    product: Dict,
    on_delete: callable,
    key_suffix: str = ""
):
    """渲染产品卡片"""
    
    # 使用container创建卡片容器
    with st.container():
        # 创建卡片背景
        st.markdown("""
            <div style="
                background-color: white;
                border-radius: 20px;
                padding: 24px;
                margin: 16px 0;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
            ">
        """, unsafe_allow_html=True)
        
        # 创建三列布局
        col1, col2, col3 = st.columns([1, 2, 1])
        
        # 左侧列：商品图片
        with col1:
            if product.get("main_image"):
                st.image(
                    product["main_image"],
                    use_container_width=True,
                    caption=None
                )
            else:
                st.markdown(f"""
                    <div style="
                        background-color: #f5f5f7;
                        border-radius: 16px;
                        padding: 16px;
                        text-align: center;
                        color: #86868b;
                    ">
                        🖼️ {get_text("no_image")}
                    </div>
                """, unsafe_allow_html=True)
        
        # 中间列：商品信息
        with col2:
            # 商品标题
            st.markdown(f"""
                <h3 style="
                    color: #1d1d1f;
                    font-size: 1.2em;
                    font-weight: 600;
                    margin: 0 0 12px 0;
                    line-height: 1.4;
                ">{product.get('title', get_text("unknown_product"))}</h3>
            """, unsafe_allow_html=True)
            
            # 分类信息
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
                
                # 显示类别导航
                if categories:
                    st.markdown(f"""
                        <div style="
                            margin: 0 0 16px 0;
                            display: flex;
                            flex-wrap: wrap;
                            gap: 8px;
                            align-items: center;
                        ">
                            <span style="
                                color: #86868b;
                                font-size: 0.9em;
                                margin-right: 8px;
                            ">{get_text("category")}:</span>
                    """, unsafe_allow_html=True)
                    
                    for i, category in enumerate(categories):
                        if i > 0:
                            st.markdown("""
                                <span style="
                                    color: #86868b;
                                    margin: 0 4px;
                                ">></span>
                            """, unsafe_allow_html=True)
                        st.markdown(f"""
                            <span style="
                                background-color: #f5f5f7;
                                padding: 4px 12px;
                                border-radius: 100px;
                                font-size: 0.9em;
                                color: #1d1d1f;
                            ">{category}</span>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
            
            # 标签行
            tag_cols = st.columns(4)
            
            # 来源标签
            with tag_cols[0]:
                if product.get('source') == 'cj':
                    st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #FF6B6B, #FF5252);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                        ">
                            🔄 CJ
                        </div>
                    """, unsafe_allow_html=True)
                elif product.get('source') == 'pa-api':
                    st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #9C27B0, #7B1FA2);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                        ">
                            🛍️ Amazon API
                        </div>
                    """, unsafe_allow_html=True)
            
            # Prime标签
            with tag_cols[1]:
                if product.get("offers") and len(product["offers"]) > 0:
                    if product["offers"][0].get("is_prime"):
                        st.markdown("""
                            <div style="
                                background: linear-gradient(135deg, #00A8E1, #0091EA);
                                color: white;
                                padding: 6px 12px;
                                border-radius: 100px;
                                text-align: center;
                                font-size: 0.85em;
                                font-weight: 500;
                                margin: 4px 0;
                            ">
                                ✓ Prime
                            </div>
                        """, unsafe_allow_html=True)
            
            # 佣金标签
            with tag_cols[2]:
                if product.get("source") == "cj" and product.get("offers"):
                    main_offer = product["offers"][0]
                    if main_offer.get("commission"):
                        st.markdown(f"""
                            <div style="
                                background: linear-gradient(135deg, #4CAF50, #43A047);
                                color: white;
                                padding: 6px 12px;
                                border-radius: 100px;
                                text-align: center;
                                font-size: 0.85em;
                                font-weight: 500;
                                margin: 4px 0;
                            ">
                                💰 {get_text("commission")}: {main_offer['commission']}
                            </div>
                        """, unsafe_allow_html=True)
            
            # 优惠券标签
            with tag_cols[3]:
                if product.get("offers") and product["offers"][0].get("coupon_type"):
                    coupon_type = product["offers"][0]["coupon_type"]
                    coupon_value = product["offers"][0]["coupon_value"]
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #FF5722, #F4511E);
                            color: white;
                            padding: 6px 12px;
                            border-radius: 100px;
                            text-align: center;
                            font-size: 0.85em;
                            font-weight: 500;
                            margin: 4px 0;
                        ">
                            🏷️ {coupon_value}{'%' if coupon_type == 'percentage' else '$'} {get_text("off")}
                        </div>
                    """, unsafe_allow_html=True)
            
            # 品牌信息
            if product.get("brand"):
                st.markdown(f"""
                    <div style="margin: 16px 0;">
                        <span style="color: #86868b;">{get_text("brand")}:</span>
                        <span style="font-weight: 500; margin-left: 8px;">{product['brand']}</span>
                    </div>
                """, unsafe_allow_html=True)
            
            # ASIN信息
            if product.get("asin"):
                st.markdown(f"""
                    <div style="margin: 16px 0;">
                        <span style="color: #86868b;">ASIN:</span>
                        <span style="font-weight: 500; margin-left: 8px;">{product['asin']}</span>
                    </div>
                """, unsafe_allow_html=True)
            
            # 价格信息
            if product.get("offers") and len(product["offers"]) > 0:
                offer = product["offers"][0]
                price = offer.get("price")
                savings = offer.get("savings")
                currency = offer.get("currency", "USD")
                
                price_col, discount_col = st.columns([1, 1])
                with price_col:
                    if price is not None:
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
                            ">
                                {get_text("save_money")} {savings_percentage}%
                            </div>
                        """, unsafe_allow_html=True)
        
        # 右侧列：操作按钮
        with col3:
            # CJ推广链接
            if product.get("cj_url"):
                st.link_button(
                    get_text("CJ affiliate_link"),
                    product["cj_url"],
                    use_container_width=True,
                    type="primary"
                )
            
            # 商品链接
            if product.get("url"):
                st.link_button(
                    get_text("view_details"),
                    product["url"],
                    use_container_width=True
                )
            
            # 删除按钮
            if st.button(
                f"🗑️ {get_text('delete')}",
                key=f"delete_{product['asin']}_{key_suffix}",
                type="secondary",
                use_container_width=True
            ):
                st.markdown(f"""
                    <div style="
                        background-color: #ffebee;
                        color: #c62828;
                        padding: 12px;
                        border-radius: 8px;
                        margin: 8px 0;
                        text-align: center;
                    ">
                        {get_text("confirm_delete")}
                    </div>
                """, unsafe_allow_html=True)
                
                confirm_col1, confirm_col2 = st.columns(2)
                with confirm_col1:
                    if st.button(get_text("cancel"), key=f"cancel_{product['asin']}", use_container_width=True):
                        st.rerun()
                with confirm_col2:
                    if st.button(get_text("confirm"), key=f"confirm_{product['asin']}", type="primary", use_container_width=True):
                        if on_delete(product["asin"]):
                            st.success(get_text("delete_success"))
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
                        {get_text("update_time")} {product['timestamp']}
                    </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True) 