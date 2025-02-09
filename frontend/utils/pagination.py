"""
分页工具模块
"""

import streamlit as st
from frontend.i18n.language import get_text

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
    total_pages = (total_items + page_size - 1) // page_size
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if page > 1:
            if st.button(
                get_text("prev_page"),
                key=f"prev_{key_suffix}"
            ):
                return page - 1
    
    with col2:
        st.write(get_text("page_info").format(current=page, total=total_pages))
    
    with col3:
        if page < total_pages:
            if st.button(
                get_text("next_page"),
                key=f"next_{key_suffix}"
            ):
                return page + 1
    
    return page 