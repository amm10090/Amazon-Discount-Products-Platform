"""
语言管理工具
"""
import streamlit as st
from .translations import TRANSLATIONS

def init_language():
    """初始化语言设置"""
    # 确保在使用session_state之前先初始化它
    if "global_language" not in st.session_state:
        st.session_state["global_language"] = "zh"

def get_current_language():
    """获取当前语言"""
    init_language()  # 确保语言已初始化
    return st.session_state.global_language

def switch_language():
    """切换语言"""
    init_language()  # 确保语言已初始化
    if st.session_state.global_language == "zh":
        st.session_state.global_language = "en"
    else:
        st.session_state.global_language = "zh"

def get_text(key):
    """获取翻译文本"""
    init_language()  # 确保语言已初始化
    return TRANSLATIONS[st.session_state.global_language].get(key, key)

def language_selector():
    """创建一个更紧凑的语言选择器"""
    init_language()  # 确保语言已初始化
    
    st.markdown("""
    <style>
    div.language-selector {
        display: flex;
        gap: 4px;
        margin-bottom: 0.5rem;
    }
    
    div.language-selector button {
        flex: 1;
        font-size: 0.8rem !important;
        padding: 0.3rem !important;
        min-height: unset !important;
        height: auto !important;
        line-height: 1.2 !important;
    }
    
    div.language-selector button div {
        font-size: 0.8rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    current_lang = st.session_state.global_language
    
    with st.container():
        st.markdown('<div class="language-selector">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(
                "🇨🇳 中文", 
                use_container_width=True,
                type="primary" if current_lang == "zh" else "secondary",
                key="global_zh_btn"
            ):
                st.session_state.global_language = "zh"
                st.rerun()
                
        with col2:
            if st.button(
                "🇺🇸 EN",
                use_container_width=True,
                type="primary" if current_lang == "en" else "secondary",
                key="global_en_btn"
            ):
                st.session_state.global_language = "en"
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True) 