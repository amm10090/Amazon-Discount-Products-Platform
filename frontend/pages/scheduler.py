import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz
from i18n import init_language, get_text, language_selector
import pandas as pd
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from main import load_config

# 加载配置
config = load_config()

st.set_page_config(
    page_title=get_text("scheduler_title"),
    page_icon="⏰",
    layout=config["frontend"]["page"]["layout"],
    initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"]
)

# 初始化语言设置
init_language()

# 自定义CSS
st.markdown(f"""
<style>
    .job-card {{
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
        background-color: {config["frontend"]["theme"]["backgroundColor"]};
    }}
    .status-running {{
        color: #28a745;
        font-weight: bold;
    }}
    .status-stopped {{
        color: #dc3545;
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

# 常用时区列表
COMMON_TIMEZONES = [
    "Asia/Shanghai",
    "Asia/Tokyo",
    "America/New_York",
    "Europe/London",
    "UTC"
]

# 侧边栏
with st.sidebar:
    # 语言选择器
    language_selector()
    st.markdown("---")

st.title("⏰ " + get_text("scheduler_title"))

# 添加新任务表单
with st.form("add_job"):
    st.subheader(get_text("add_new_job"))
    
    col1, col2 = st.columns(2)
    
    with col1:
        job_id = st.text_input(
            get_text("job_id"),
            help=get_text("job_id_help")
        )
        
        job_type = st.selectbox(
            get_text("job_type"),
            options=["cron", "interval"],
            help=get_text("job_type_help")
        )
        
        crawler_type = st.selectbox(
            get_text("crawler_type"),
            options=["bestseller", "coupon", "all"],
            format_func=lambda x: get_text(f"crawler_{x}"),
            help=get_text("crawler_type_help")
        )
    
    with col2:
        max_items = st.number_input(
            get_text("max_items"),
            min_value=10,
            max_value=1000,
            value=100,
            step=10
        )
        
        if job_type == "cron":
            hour = st.selectbox(
                get_text("hour"),
                options=["*"] + [str(i) for i in range(24)] + ["*/2", "*/4", "*/6", "*/8", "*/12"],
                help=get_text("hour_help")
            )
            minute = st.selectbox(
                get_text("minute"),
                options=["0", "15", "30", "45"],
                help=get_text("minute_help")
            )
        else:  # interval
            hours = st.number_input(
                get_text("interval_hours"),
                min_value=1,
                max_value=24,
                value=1
            )
            minutes = st.number_input(
                get_text("interval_minutes"),
                min_value=0,
                max_value=59,
                value=0
            )
    
    submitted = st.form_submit_button(get_text("add_job"))
    
    if submitted:
        try:
            # 构建任务配置
            job_config = {
                "id": job_id,
                "type": job_type,
                "crawler_type": crawler_type,
                "max_items": max_items
            }
            
            if job_type == "cron":
                job_config.update({
                    "hour": hour,
                    "minute": minute
                })
            else:
                job_config.update({
                    "hours": hours,
                    "minutes": minutes
                })
            
            # 发送添加任务请求
            api_url = f"http://{config['api']['host']}:{config['api']['port']}"
            response = requests.post(
                f"{api_url}/api/scheduler/jobs",
                json=job_config
            )
            
            if response.status_code == 200:
                st.success(get_text("job_added"))
            else:
                st.error(f"{get_text('add_job_failed')}: {response.json()['detail']}")
                
        except Exception as e:
            st.error(f"{get_text('error')}: {str(e)}")

# 显示现有任务
st.markdown("---")
st.subheader(get_text("existing_jobs"))

# 获取调度器状态和当前时区
try:
    api_url = f"http://{config['api']['host']}:{config['api']['port']}"
    scheduler_status = requests.get(f"{api_url}/api/scheduler/status").json()
    current_timezone = scheduler_status.get('timezone', 'UTC')
except Exception:
    current_timezone = 'UTC'

# 在显示时间时使用选择的时区
def format_datetime(dt, timezone=None):
    if not dt:
        return ""
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt)
    if timezone:
        dt = dt.astimezone(pytz.timezone(timezone))
    return dt.strftime("%Y-%m-%d %H:%M:%S")

try:
    # 获取所有任务
    response = requests.get(f"{api_url}/api/scheduler/jobs")
    
    if response.status_code == 200:
        jobs = response.json()
        
        if not jobs:
            st.info(get_text("no_jobs"))
        else:
            for job in jobs:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.markdown(f"**{get_text('job_id')}:** {job['id']}")
                        st.markdown(
                            f"**{get_text('crawler_type')}:** "
                            f"{get_text(f'crawler_{job['crawler_type']}')}"
                        )
                        st.markdown(f"**{get_text('max_items')}:** {job['max_items']}")
                    
                    with col2:
                        if job['type'] == 'cron':
                            st.markdown(f"**{get_text('schedule')}:** {job['hour']}:{job['minute']}")
                        else:
                            st.markdown(
                                f"**{get_text('interval')}:** "
                                f"{job['hours']}h {job['minutes']}m"
                            )
                        
                        next_run = job['next_run_time']
                        if next_run:
                            st.markdown(
                                f"**{get_text('next_run')}:** "
                                f"{format_datetime(next_run, current_timezone)}"
                            )
                        else:
                            st.markdown(
                                f"**{get_text('status')}:** "
                                f"<span class='status-stopped'>{get_text('status_paused')}</span>",
                                unsafe_allow_html=True
                            )
                    
                    with col3:
                        # 暂停/恢复按钮
                        if job.get('paused', False):
                            if st.button(
                                "▶️ " + get_text("resume"),
                                key=f"resume_{job['id']}"
                            ):
                                try:
                                    response = requests.post(
                                        f"{api_url}/api/scheduler/jobs/{job['id']}/resume"
                                    )
                                    if response.status_code == 200:
                                        st.success(get_text("job_resumed"))
                                        st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                        else:
                            if st.button(
                                "⏸️ " + get_text("pause"),
                                key=f"pause_{job['id']}"
                            ):
                                try:
                                    response = requests.post(
                                        f"{api_url}/api/scheduler/jobs/{job['id']}/pause"
                                    )
                                    if response.status_code == 200:
                                        st.success(get_text("job_paused"))
                                        st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                        
                        # 立即执行按钮
                        if st.button(
                            "⚡ " + get_text("execute_now"),
                            key=f"execute_{job['id']}"
                        ):
                            try:
                                response = requests.post(
                                    f"{api_url}/api/scheduler/jobs/{job['id']}/execute"
                                )
                                if response.status_code == 200:
                                    st.success(get_text("job_started"))
                                    st.rerun()
                            except Exception as e:
                                st.error(str(e))
                        
                        # 删除按钮
                        if st.button(
                            "🗑️ " + get_text("delete"),
                            key=f"delete_{job['id']}"
                        ):
                            try:
                                response = requests.delete(
                                    f"{api_url}/api/scheduler/jobs/{job['id']}"
                                )
                                if response.status_code == 200:
                                    st.success(get_text("job_deleted"))
                                    st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    
                    # 显示最近执行记录
                    if st.checkbox(
                        get_text("show_history"),
                        key=f"history_{job['id']}"
                    ):
                        try:
                            history = requests.get(
                                f"{api_url}/api/scheduler/jobs/{job['id']}/history"
                            ).json()
                            
                            if history:
                                history_df = pd.DataFrame(history)
                                
                                # 转换时间到当前时区
                                for col in ['start_time', 'end_time']:
                                    history_df[col] = pd.to_datetime(history_df[col]).dt.tz_localize('UTC').dt.tz_convert(current_timezone)
                                
                                # 翻译状态
                                history_df['status'] = history_df['status'].apply(
                                    lambda x: get_text(f"status_{x}")
                                )
                                
                                st.dataframe(
                                    history_df[[
                                        'start_time',
                                        'end_time',
                                        'status',
                                        'items_collected',
                                        'error'
                                    ]],
                                    hide_index=True,
                                    column_config={
                                        'start_time': get_text('start_time'),
                                        'end_time': get_text('end_time'),
                                        'status': get_text('status'),
                                        'items_collected': get_text('items_collected'),
                                        'error': get_text('error')
                                    }
                                )
                            else:
                                st.info(get_text("no_history"))
                                
                        except Exception as e:
                            st.error(f"{get_text('loading_failed')}: {str(e)}")
                    
                    st.markdown("---")
    else:
        st.error(f"{get_text('loading_failed')}: {response.json()['detail']}")
        
except Exception as e:
    st.error(f"{get_text('error')}: {str(e)}")

# 显示调度器状态
st.markdown("---")
st.subheader(get_text("scheduler_status"))

try:
    response = requests.get(f"{api_url}/api/scheduler/status")
    
    if response.status_code == 200:
        status = response.json()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                get_text("running_jobs"),
                status['running_jobs']
            )
        
        with col2:
            st.metric(
                get_text("total_jobs"),
                status['total_jobs']
            )
        
        with col3:
            # 显示当前时区并提供修改功能
            current_timezone = status.get('timezone', 'UTC')
            new_timezone = st.selectbox(
                get_text("timezone"),
                options=COMMON_TIMEZONES + sorted(list(set(pytz.all_timezones) - set(COMMON_TIMEZONES))),
                index=([*COMMON_TIMEZONES, *sorted(list(set(pytz.all_timezones) - set(COMMON_TIMEZONES)))].index(current_timezone)
                      if current_timezone in pytz.all_timezones else 0)
            )
            
            if new_timezone != current_timezone:
                if st.button(get_text("update_timezone")):
                    try:
                        response = requests.post(
                            f"{api_url}/api/scheduler/timezone",
                            json={"timezone": new_timezone}
                        )
                        if response.status_code == 200:
                            st.success(get_text("timezone_updated"))
                            st.rerun()
                        else:
                            st.error(f"{get_text('update_timezone_failed')}: {response.json()['detail']}")
                    except Exception as e:
                        st.error(f"{get_text('error')}: {str(e)}")
        
        # 调度器控制按钮
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if status.get('running', False):
                if st.button("⏹️ " + get_text("stop_scheduler")):
                    try:
                        response = requests.post(
                            f"{api_url}/api/scheduler/stop"
                        )
                        if response.status_code == 200:
                            st.success(get_text("scheduler_stopped"))
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                if st.button("▶️ " + get_text("start_scheduler")):
                    try:
                        response = requests.post(
                            f"{api_url}/api/scheduler/start"
                        )
                        if response.status_code == 200:
                            st.success(get_text("scheduler_started"))
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))
        
        with col2:
            if st.button("🔄 " + get_text("reload_scheduler")):
                try:
                    response = requests.post(
                        f"{api_url}/api/scheduler/reload"
                    )
                    if response.status_code == 200:
                        st.success(get_text("scheduler_reloaded"))
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
                    
except Exception as e:
    st.error(f"{get_text('error')}: {str(e)}") 