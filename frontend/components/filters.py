"""
筛选组件模块
"""

import streamlit as st
from typing import Dict, List, Optional, Tuple, Any
from frontend.i18n.language import get_text

def render_category_filter(
    category_stats: Dict[str, Dict[str, Any]],
    product_type: str = "all"  # 添加product_type参数
) -> Optional[Dict[str, List[str]]]:
    """渲染类别筛选组件
    
    Args:
        category_stats: 类别统计信息，包含browse_nodes和browse_tree等
        product_type: 商品类型 ('discount'/'coupon'/'all')
        
    Returns:
        Optional[Dict[str, List[str]]]: 选中的筛选条件
    """
    selected_filters = {
        "browse_node_ids": [],  # 选中的browse node IDs
        "bindings": [],         # 选中的binding类型
        "product_groups": []    # 选中的product group
    }
    
    # Browse Nodes多选
    if category_stats["browse_nodes"]:
        with st.expander(get_text("product_category"), expanded=False):  # 设置默认为关闭
            # 添加搜索框
            search_term = st.text_input(
                get_text("search_category"),
                key=f"category_search_{product_type}"
            ).lower()
            
            # 添加层级显示控制
            max_level = st.slider(
                get_text("category_depth"),
                min_value=1,
                max_value=max(node["level"] for node in category_stats["browse_nodes"].values()) + 1,
                value=2,
                key=f"category_depth_{product_type}"
            )
            
            # 构建并显示层级结构
            def render_node(node_id: str, node_info: Dict, level: int = 0):
                if level >= max_level:
                    return
                    
                node_name = node_info["name"]
                if search_term and search_term not in node_name.lower():
                    return
                    
                # 使用缩进表示层级
                indent = "　" * level
                label = f"{indent}{'▼' if node_info.get('children') else '▶'} {node_name} ({node_info['count']})"
                
                if st.checkbox(
                    label,
                    key=f"node_{product_type}_{node_id}",
                    value=node_id in selected_filters["browse_node_ids"]
                ):
                    selected_filters["browse_node_ids"].append(node_id)
                
                # 递归显示子节点
                if "children" in node_info:
                    for child_id, child_info in node_info["children"].items():
                        render_node(child_id, child_info, level + 1)
            
            # 显示树形结构
            for root_id, root_info in category_stats["browse_tree"].items():
                render_node(root_id, root_info)
            
            # 显示选中的类别路径
            if selected_filters["browse_node_ids"]:
                st.markdown("---")
                st.write(get_text("selected_categories"))
                for node_id in selected_filters["browse_node_ids"]:
                    if node_id in category_stats["browse_nodes"]:
                        node = category_stats["browse_nodes"][node_id]
                        st.write(f"• {node['name']}")
    
    # 商品绑定类型多选
    if category_stats["bindings"]:
        with st.expander(get_text("product_binding"), expanded=False):  # 设置默认为关闭
            # 添加搜索框
            binding_search = st.text_input(
                get_text("search_binding"),
                key=f"binding_search_{product_type}"
            ).lower()
            
            for binding, count in category_stats["bindings"].items():
                if binding_search and binding_search not in binding.lower():
                    continue
                    
                if st.checkbox(
                    f"{binding} ({count})",
                    key=f"binding_{product_type}_{binding}"
                ):
                    selected_filters["bindings"].append(binding)
    
    # 商品组多选
    if category_stats["product_groups"]:
        with st.expander(get_text("product_group"), expanded=False):  # 设置默认为关闭
            # 添加搜索框
            group_search = st.text_input(
                get_text("search_group"),
                key=f"group_search_{product_type}"
            ).lower()
            
            for group, count in category_stats["product_groups"].items():
                if group_search and group_search not in group.lower():
                    continue
                    
                if st.checkbox(
                    f"{group} ({count})",
                    key=f"group_{product_type}_{group}"
                ):
                    selected_filters["product_groups"].append(group)
    
    # 如果没有选择任何筛选条件，返回None
    if not any(selected_filters.values()):
        return None
    
    return selected_filters

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