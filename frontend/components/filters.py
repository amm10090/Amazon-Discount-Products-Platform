"""
筛选组件模块
"""

import streamlit as st
from typing import Dict, List, Optional, Tuple
from frontend.i18n.language import get_text

def render_category_filter(
    category_stats: Dict[str, Dict[str, int]]
) -> Optional[Dict[str, List[str]]]:
    """渲染类别筛选组件
    
    Args:
        category_stats: 类别统计信息
        
    Returns:
        Optional[Dict[str, List[str]]]: 选中的类别
    """
    selected_categories = {
        "main_categories": [],
        "sub_categories": [],
        "bindings": [],
        "product_groups": []
    }
    
    with st.sidebar:
        st.subheader(get_text("filter_conditions"))
        
        # 主要类别多选
        if category_stats["main_categories"]:
            with st.expander(get_text("product_category"), expanded=True):
                for category, count in category_stats["main_categories"].items():
                    if st.checkbox(f"{category} ({count})", key=f"main_{category}"):
                        selected_categories["main_categories"].append(category)
        
        # 子类别多选（按主类别分组显示）
        if category_stats["sub_categories"]:
            with st.expander(get_text("categories"), expanded=True):
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
            with st.expander(get_text("product_binding")):
                for binding, count in category_stats["bindings"].items():
                    if st.checkbox(f"{binding} ({count})", key=f"binding_{binding}"):
                        selected_categories["bindings"].append(binding)
        
        # 商品组多选
        if category_stats["product_groups"]:
            with st.expander(get_text("product_group")):
                for group, count in category_stats["product_groups"].items():
                    if st.checkbox(f"{group} ({count})", key=f"group_{group}"):
                        selected_categories["product_groups"].append(group)
    
    # 如果没有选择任何类别，返回None
    if not any(selected_categories.values()):
        return None
    
    return selected_categories

def render_filter_sidebar() -> Tuple[str, float, float, int, bool, Optional[int], Optional[str], str, int]:
    """渲染侧边栏筛选条件
    
    Returns:
        Tuple[str, float, float, int, bool, Optional[int], Optional[str], str, int]:
            - source_filter: 数据来源筛选
            - min_price: 最低价格
            - max_price: 最高价格
            - min_discount: 最低折扣率
            - is_prime_only: 是否只显示Prime商品
            - min_commission: 最低佣金比例
            - sort_by: 排序方式
            - sort_order: 排序方向
            - page_size: 每页显示数量
    """
    with st.sidebar:
        st.subheader(get_text("filter_conditions"))
        
        # 添加数据源筛选
        source_filter = st.selectbox(
            get_text("source_filter"),
            options=["all", "pa-api", "cj"],
            format_func=lambda x: {
                "all": f"{get_text('all')} (Amazon + CJ)",
                "pa-api": "Amazon API",
                "cj": "CJ API"
            }[x]
        )
        
        col1, col2 = st.columns(2)
        with col1:
            min_price = st.number_input(get_text("min_price"), min_value=0.0, value=0.0)
        with col2:
            max_price = st.number_input(get_text("max_price"), min_value=0.0, value=9999.0)
            
        min_discount = st.slider(get_text("min_discount_rate"), min_value=0, max_value=100, value=0)
        is_prime_only = st.checkbox(get_text("prime_only"))
        
        # 添加CJ佣金筛选
        min_commission = None
        if source_filter in ["all", "cj"]:
            min_commission = st.slider(get_text("min_commission"), min_value=0, max_value=100, value=0)
        
        sort_by = st.selectbox(
            get_text("sort_by"),
            options=[None, "price", "discount", "timestamp", "commission"],
            format_func=lambda x: {
                None: get_text("sort_by"),
                "price": get_text("price_low_to_high"),
                "discount": get_text("discount_low_to_high"),
                "timestamp": get_text("time_old_to_new"),
                "commission": get_text("commission")
            }[x]
        )
        
        sort_order = st.selectbox(
            get_text("sort_order"),
            options=["desc", "asc"],
            format_func=lambda x: get_text("desc") if x == "desc" else get_text("asc")
        )
        
        page_size = st.selectbox(
            get_text("items_per_page"),
            options=[10, 20, 50, 100],
            index=1
        )
        
        return (
            source_filter,
            min_price,
            max_price,
            min_discount,
            is_prime_only,
            min_commission,
            sort_by,
            sort_order,
            page_size
        )