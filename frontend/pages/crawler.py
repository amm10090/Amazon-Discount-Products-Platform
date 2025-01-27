import streamlit as st
import requests
import time
from datetime import datetime
import json
import pandas as pd
from i18n import init_language, get_text, language_selector

# 初始化语言设置
init_language()

st.set_page_config(
    page_title=get_text("crawler_title"),
    page_icon="🔍",
    layout="wide"
)

# 自定义CSS
st.markdown("""
<style>
    .task-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .success-text {
        color: #28a745;
    }
    .error-text {
        color: #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# 侧边栏
with st.sidebar:
    # 语言选择器
    language_selector()
    st.markdown("---")

st.title("🔍 " + get_text("crawler_title"))

# 任务配置表单
with st.form("crawler_config"):
    st.subheader(get_text("crawler_config"))
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        max_items = st.number_input(
            get_text("max_items"),
            min_value=10,
            max_value=1000,
            value=50,
            step=10,
            help=get_text("max_items") + " (10-1000)"
        )
    
    with col2:
        timeout = st.number_input(
            get_text("timeout"),
            min_value=10,
            max_value=300,
            value=30,
            step=10,
            help=get_text("timeout")
        )
    
    with col3:
        output_format = st.selectbox(
            get_text("output_format"),
            options=["json", "csv", "txt"],
            help=get_text("output_format")
        )
    
    headless = st.checkbox(
        get_text("headless_mode"),
        value=True,
        help=get_text("headless_mode")
    )
    
    submitted = st.form_submit_button(get_text("start_crawler"))
    
    if submitted:
        try:
            # 发送爬虫任务请求
            response = requests.post(
                "http://localhost:8000/api/crawl",
                json={
                    "max_items": max_items,
                    "timeout": timeout,
                    "output_format": output_format,
                    "headless": headless
                }
            )
            
            if response.status_code == 200:
                task_data = response.json()
                st.session_state["task_id"] = task_data["task_id"]
                st.success(f"{get_text('start_crawler')}！{get_text('task_id')}: {task_data['task_id']}")
            else:
                st.error(f"{get_text('start_crawler')} {get_text('failed')}")
                
        except Exception as e:
            st.error(f"{get_text('error')}: {str(e)}")

# 任务状态监控
st.markdown("---")
st.subheader(get_text("task_status"))

if "task_id" in st.session_state:
    task_id = st.session_state["task_id"]
    
    # 创建任务状态容器
    status_container = st.empty()
    progress_bar = st.progress(0)
    
    # 轮询任务状态
    try:
        response = requests.get(f"http://localhost:8000/api/status/{task_id}")
        
        if response.status_code == 200:
            task_info = response.json()
            
            # 更新状态显示
            with status_container.container():
                st.markdown(f"**{get_text('task_id')}:** {task_id}")
                st.markdown(f"**{get_text('status')}:** {task_info['status']}")
                
                if task_info["status"] == "completed":
                    st.markdown(f"**{get_text('total_items')}:** {task_info['total_items']}")
                    st.markdown(f"**{get_text('duration')}:** {task_info['duration']:.1f} {get_text('seconds')}")
                    
                    # 显示下载按钮
                    if st.button(get_text("download_results")):
                        try:
                            download_response = requests.get(
                                f"http://localhost:8000/api/download/{task_id}"
                            )
                            
                            if download_response.status_code == 200:
                                # 根据输出格式处理数据
                                if output_format == "json":
                                    result_data = download_response.json()
                                    st.json(result_data)
                                    st.download_button(
                                        f"{get_text('save')} JSON",
                                        data=json.dumps(result_data, indent=2, ensure_ascii=False),
                                        file_name=f"crawler_results_{task_id}.json",
                                        mime="application/json"
                                    )
                                elif output_format == "csv":
                                    df = pd.read_csv(download_response.content)
                                    st.dataframe(df)
                                    st.download_button(
                                        f"{get_text('save')} CSV",
                                        data=df.to_csv(index=False),
                                        file_name=f"crawler_results_{task_id}.csv",
                                        mime="text/csv"
                                    )
                                else:  # txt格式
                                    result_text = download_response.text
                                    st.text_area(get_text("crawler_results"), result_text, height=300)
                                    st.download_button(
                                        f"{get_text('save')} TXT",
                                        data=result_text,
                                        file_name=f"crawler_results_{task_id}.txt",
                                        mime="text/plain"
                                    )
                        except Exception as e:
                            st.error(f"{get_text('download_failed')}: {str(e)}")
                            
                elif task_info["status"] == "running":
                    if "total_items" in task_info and task_info["total_items"] > 0:
                        progress = task_info["total_items"] / max_items
                        progress_bar.progress(min(progress, 1.0))
                        st.markdown(f"**{get_text('crawled')}:** {task_info['total_items']} {get_text('items')}")
                    else:
                        progress_bar.progress(None)
                        st.info(get_text("task_running"))
                        
                elif task_info["status"] == "failed":
                    st.error(f"{get_text('task_failed')}: {task_info.get('error', get_text('unknown_error'))}")
                    progress_bar.empty()
                    
        else:
            st.error(get_text("status_failed"))
            
    except Exception as e:
        st.error(f"{get_text('monitor_error')}: {str(e)}")
        
else:
    st.info(get_text("start_crawler_first")) 