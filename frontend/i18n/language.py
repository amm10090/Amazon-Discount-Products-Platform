"""
语言管理工具
"""
import streamlit as st
from .translations import TRANSLATIONS

def init_language():
    """初始化语言设置"""
    if "language" not in st.session_state:
        st.session_state.language = "zh"

def get_current_language():
    """获取当前语言"""
    return st.session_state.language

def switch_language():
    """切换语言"""
    if st.session_state.language == "zh":
        st.session_state.language = "en"
    else:
        st.session_state.language = "zh"

def get_text(key):
    """获取翻译文本"""
    return TRANSLATIONS[st.session_state.language].get(key, key)

def language_selector():
    """创建一个更直观的语言选择器"""
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        text-align: center;
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 10px;
        margin: 5px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:hover {
        background-color: #FFF5E6;
    }
    
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"].active {
        background-color: #FF9900;
        color: white;
    }
    
    .lang-text {
        font-size: 1rem;
        font-weight: 500;
        margin: 0;
    }
    
    .lang-flag {
        font-size: 1.5rem;
        margin-bottom: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

    current_lang = st.session_state.language
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button(
            "🇨🇳\n中文", 
            use_container_width=True,
            type="primary" if current_lang == "zh" else "secondary"
        ):
            st.session_state.language = "zh"
            st.rerun()
            
    with col2:
        if st.button(
            "🇺🇸\nEnglish",
            use_container_width=True,
            type="primary" if current_lang == "en" else "secondary"
        ):
            st.session_state.language = "en"
            st.rerun() 