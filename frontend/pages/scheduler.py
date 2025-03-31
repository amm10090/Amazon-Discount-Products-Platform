import streamlit as st
import requests
from datetime import datetime, timedelta, UTC
import pytz
from frontend.i18n.language import init_language, get_text
import pandas as pd
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from frontend.main import load_config
from frontend.utils.cache_manager import cache_manager
from typing import List, Dict, Optional, Union

# 加载配置
config = load_config()

# 初始化语言设置
init_language()

st.set_page_config(
    page_title=get_text("scheduler_title"),
    page_icon="⏰",
    layout=config["frontend"]["page"]["layout"],
    initial_sidebar_state=config["frontend"]["page"]["initial_sidebar_state"]
)

# 自定义CSS样式
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

@cache_manager.data_cache(
    ttl=60,  # 调度器状态缓存时间较短
    show_spinner="正在获取调度器状态..."
)
def get_scheduler_status(api_url: str) -> Dict:
    """获取调度器状态
    
    Args:
        api_url: API服务地址
        
    Returns:
        Dict: 调度器状态信息
    """
    try:
        response = requests.get(f"{api_url}/api/scheduler/status")
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return {}

@cache_manager.data_cache(
    ttl=60,
    show_spinner="正在加载任务列表..."
)
def load_jobs(api_url: str) -> List[Dict]:
    """加载任务列表
    
    Args:
        api_url: API服务地址
        
    Returns:
        List[Dict]: 任务列表
    """
    try:
        response = requests.get(f"{api_url}/api/scheduler/jobs")
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return []

@cache_manager.data_cache(
    ttl=300,
    show_spinner="正在加载任务历史..."
)
def load_job_history(api_url: str, job_id: str) -> List[Dict]:
    """加载任务执行历史
    
    Args:
        api_url: API服务地址
        job_id: 任务ID
        
    Returns:
        List[Dict]: 任务执行历史
    """
    try:
        response = requests.get(f"{api_url}/api/scheduler/jobs/{job_id}/history")
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"{get_text('loading_failed')}: {str(e)}")
        return []

def add_job(
    api_url: str,
    job_config: Dict
) -> bool:
    """添加新任务
    
    Args:
        api_url: API服务地址
        job_config: 任务配置
        
    Returns:
        bool: 是否添加成功
    """
    try:
        response = requests.post(
            f"{api_url}/api/scheduler/jobs",
            json=job_config
        )
        success = response.status_code == 200
        if success:
            # 清除任务列表缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('add_job_failed')}: {str(e)}")
        return False

def pause_job(api_url: str, job_id: str) -> bool:
    """暂停任务
    
    Args:
        api_url: API服务地址
        job_id: 任务ID
        
    Returns:
        bool: 是否暂停成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/jobs/{job_id}/pause")
        success = response.status_code == 200
        if success:
            # 清除任务列表缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def resume_job(api_url: str, job_id: str) -> bool:
    """恢复任务
    
    Args:
        api_url: API服务地址
        job_id: 任务ID
        
    Returns:
        bool: 是否恢复成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/jobs/{job_id}/resume")
        success = response.status_code == 200
        if success:
            # 清除任务列表缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def delete_job(api_url: str, job_id: str) -> bool:
    """删除任务
    
    Args:
        api_url: API服务地址
        job_id: 任务ID
        
    Returns:
        bool: 是否删除成功
    """
    try:
        response = requests.delete(f"{api_url}/api/scheduler/jobs/{job_id}")
        success = response.status_code == 200
        if success:
            # 清除任务列表缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def execute_job(api_url: str, job_id: str) -> bool:
    """立即执行任务
    
    Args:
        api_url: API服务地址
        job_id: 任务ID
        
    Returns:
        bool: 是否执行成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/jobs/{job_id}/execute")
        success = response.status_code == 200
        if success:
            # 清除任务历史缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def update_timezone(api_url: str, timezone: str) -> bool:
    """更新时区设置
    
    Args:
        api_url: API服务地址
        timezone: 时区
        
    Returns:
        bool: 是否更新成功
    """
    try:
        response = requests.post(
            f"{api_url}/api/scheduler/timezone",
            json={"timezone": timezone}
        )
        success = response.status_code == 200
        if success:
            # 清除调度器状态缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def start_scheduler(api_url: str) -> bool:
    """启动调度器
    
    Args:
        api_url: API服务地址
        
    Returns:
        bool: 是否启动成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/start")
        success = response.status_code == 200
        if success:
            # 清除调度器状态缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def stop_scheduler(api_url: str) -> bool:
    """停止调度器
    
    Args:
        api_url: API服务地址
        
    Returns:
        bool: 是否停止成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/stop")
        success = response.status_code == 200
        if success:
            # 清除调度器状态缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def reload_scheduler(api_url: str) -> bool:
    """重新加载调度器
    
    Args:
        api_url: API服务地址
        
    Returns:
        bool: 是否重新加载成功
    """
    try:
        response = requests.post(f"{api_url}/api/scheduler/reload")
        success = response.status_code == 200
        if success:
            # 清除所有相关缓存
            cache_manager.clear_cache()
        return success
    except Exception as e:
        st.error(f"{get_text('error')}: {str(e)}")
        return False

def format_datetime(dt: Union[str, datetime], timezone: Optional[str] = None) -> str:
    """格式化日期时间
    
    Args:
        dt: 日期时间字符串或datetime对象
        timezone: 时区
        
    Returns:
        str: 格式化后的日期时间字符串
    """
    if not dt:
        return ""
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return dt
    
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt)
    
    if timezone:
        dt = dt.astimezone(pytz.timezone(timezone))
    
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_duration(seconds: float) -> str:
    """格式化持续时间
    
    Args:
        seconds: 持续时间（秒）
        
    Returns:
        str: 格式化后的持续时间字符串
    """
    if seconds < 60:
        return f"{seconds:.2f} {get_text('seconds')}"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} {get_text('minutes')}"
    else:
        hours = int(seconds / 3600)
        return f"{hours} {get_text('hours')}"

def main():
    st.title("⏰ " + get_text("scheduler_title"))
    
    # 初始化状态变量
    show_scheduler_stats = False
    
    # API地址
    api_url = f"http://{config['api']['host']}:{config['api']['port']}"
    
    # 获取调度器状态和当前时区
    scheduler_status = get_scheduler_status(api_url)
    current_timezone = scheduler_status.get('timezone', 'UTC')
    
    # 创建任务类型分类
    task_categories = {
        "crawler": {
            "title": get_text("crawler_tasks"),
            "types": ["bestseller", "coupon", "all"],
            "icon": "🕷️"
        },
        "update": {
            "title": get_text("update_tasks"),
            "types": ["update"],
            "icon": "🔄"
        }
    }
    
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
            
            # 先选择任务分类
            task_category = st.selectbox(
                get_text("task_category"),
                options=list(task_categories.keys()),
                format_func=lambda x: f"{task_categories[x]['icon']} {task_categories[x]['title']}",
                help=get_text("task_category_help")
            )
            
            # 根据分类显示具体任务类型
            task_type = st.selectbox(
                get_text("task_type"),
                options=task_categories[task_category]["types"],
                format_func=lambda x: get_text(f"crawler_{x}"),
                help=get_text("task_type_help")
            )
        
        with col2:
            max_items = st.number_input(
                get_text("max_items"),
                min_value=10,
                max_value=1000,
                value=100,
                step=10,
                help=get_text("max_items_help")
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
            # 构建任务配置
            job_config = {
                "id": job_id,
                "type": job_type,
                "crawler_type": task_type,  # 使用选择的任务类型
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
            
            # 添加任务
            if add_job(api_url, job_config):
                st.success(get_text("job_added"))
                st.rerun()
    
    # 显示现有任务
    st.markdown("---")
    
    # 添加任务过滤选项
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_category = st.selectbox(
            get_text("filter_by_category"),
            options=["all"] + list(task_categories.keys()),
            format_func=lambda x: get_text("all_categories") if x == "all" else f"{task_categories[x]['icon']} {task_categories[x]['title']}"
        )
    
    with col2:
        status_filter = st.selectbox(
            get_text("filter_by_status"),
            options=["all", "running", "paused"],
            format_func=lambda x: get_text(f"status_filter_{x}")
        )
    
    with col3:
        sort_by = st.selectbox(
            get_text("sort_by"),
            options=["next_run", "name", "type"],
            format_func=lambda x: get_text(f"sort_by_{x}")
        )
    
    st.subheader(get_text("existing_jobs"))
    
    jobs = load_jobs(api_url)
    
    # 应用过滤
    if selected_category != "all":
        jobs = [job for job in jobs if job['crawler_type'] in task_categories[selected_category]['types']]
    
    if status_filter != "all":
        jobs = [job for job in jobs if (job.get('paused', False) and status_filter == "paused") or 
                (not job.get('paused', False) and status_filter == "running")]
    
    # 应用排序
    if sort_by == "next_run":
        jobs.sort(key=lambda x: x.get('next_run_time', float('inf')), reverse=True)
    elif sort_by == "name":
        jobs.sort(key=lambda x: x['id'])
    elif sort_by == "type":
        jobs.sort(key=lambda x: x['crawler_type'])
    
    if not jobs:
        st.info(get_text("no_jobs"))
    else:
        # 添加批量操作按钮
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("▶️ " + get_text("resume_all")):
                for job in jobs:
                    if job.get('paused', False):
                        resume_job(api_url, job['id'])
                st.success(get_text("all_jobs_resumed"))
                st.rerun()
        
        with col2:
            if st.button("⏸️ " + get_text("pause_all")):
                for job in jobs:
                    if not job.get('paused', False):
                        pause_job(api_url, job['id'])
                st.success(get_text("all_jobs_paused"))
                st.rerun()
        
        with col3:
            if st.button("🗑️ " + get_text("delete_all")):
                if st.warning(get_text("confirm_delete_all")):
                    for job in jobs:
                        delete_job(api_url, job['id'])
                    st.success(get_text("all_jobs_deleted"))
                    st.rerun()
        
        # 显示任务卡片
        for job in jobs:
            with st.container():
                # 根据任务类型获取图标
                task_icon = next((cat['icon'] for cat_name, cat in task_categories.items() 
                                if job['crawler_type'] in cat['types']), "📋")
                
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"{task_icon} **{get_text('job_id')}:** {job['id']}")
                    st.markdown(
                        f"**{get_text('task_type')}:** "
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
                    # 任务控制按钮
                    button_col1, button_col2 = st.columns(2)
                    
                    with button_col1:
                        # 暂停/恢复按钮
                        if job.get('paused', False):
                            if st.button(
                                "▶️",
                                key=f"resume_{job['id']}",
                                help=get_text("resume_help")
                            ):
                                if resume_job(api_url, job['id']):
                                    st.success(get_text("job_resumed"))
                                    st.rerun()
                        else:
                            if st.button(
                                "⏸️",
                                key=f"pause_{job['id']}",
                                help=get_text("pause_help")
                            ):
                                if pause_job(api_url, job['id']):
                                    st.success(get_text("job_paused"))
                                    st.rerun()
                    
                    with button_col2:
                        # 删除按钮
                        if st.button(
                            "🗑️",
                            key=f"delete_{job['id']}",
                            help=get_text("delete_help")
                        ):
                            if delete_job(api_url, job['id']):
                                st.success(get_text("job_deleted"))
                                st.rerun()
                    
                    # 立即执行按钮
                    if st.button(
                        "⚡",
                        key=f"execute_{job['id']}",
                        help=get_text("execute_now_help")
                    ):
                        if execute_job(api_url, job['id']):
                            st.success(get_text("job_started"))
                            st.rerun()
                
                # 显示最近执行记录
                if st.checkbox(
                    get_text("show_history"),
                    key=f"history_{job['id']}"
                ):
                    history = load_job_history(api_url, job['id'])
                    
                    if history:
                        history_df = pd.DataFrame(history)
                        
                        # 转换时间到当前时区
                        for col in ['start_time', 'end_time']:
                            history_df[col] = pd.to_datetime(history_df[col]).dt.tz_localize('UTC').dt.tz_convert(current_timezone)
                        
                        # 翻译状态
                        history_df['status'] = history_df['status'].apply(
                            lambda x: get_text(f"status_{x}")
                        )
                        
                        # 添加持续时间列
                        def calculate_duration(row):
                            if pd.isna(row['end_time']):
                                if row['status'] == get_text('status_running'):
                                    # 如果任务正在运行，计算从开始到现在的时间
                                    start_time = row['start_time']
                                    # 处理时区问题
                                    now = datetime.now(UTC)
                                    if start_time.tzinfo is None:
                                        # 如果start_time没有时区信息，添加UTC时区
                                        start_time = start_time.replace(tzinfo=UTC)
                                    
                                    duration = (now - start_time).total_seconds()
                                    return f"{int(duration)} {get_text('seconds')} ({get_text('running')})"
                                return get_text('not_finished')
                            
                            # 处理end_time和start_time的时区问题
                            end_time = row['end_time']
                            start_time = row['start_time']
                            
                            # 确保两者都有时区信息
                            if end_time.tzinfo is None:
                                end_time = end_time.replace(tzinfo=UTC)
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=UTC)
                                
                            duration = (end_time - start_time).total_seconds()
                            return f"{int(duration)} {get_text('seconds')}"
                        
                        history_df['duration'] = history_df.apply(calculate_duration, axis=1)
                        
                        st.dataframe(
                            history_df[[
                                'start_time',
                                'end_time',
                                'duration',
                                'status',
                                'items_collected',
                                'error'
                            ]],
                            hide_index=True,
                            column_config={
                                'start_time': get_text('start_time'),
                                'end_time': get_text('end_time'),
                                'duration': get_text('duration'),
                                'status': get_text('status'),
                                'items_collected': get_text('items_collected'),
                                'error': get_text('error')
                            }
                        )
                    else:
                        st.info(get_text("no_history"))
                
                st.markdown("---")
    
    # 显示调度器状态
    st.markdown("---")
    st.subheader(get_text("scheduler_status"))
    
    if scheduler_status:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                get_text("running_jobs"),
                scheduler_status['running_jobs']
            )
        
        with col2:
            st.metric(
                get_text("total_jobs"),
                scheduler_status['total_jobs']
            )
        
        with col3:
            st.metric(
                get_text("scheduler_uptime"),
                format_duration(scheduler_status.get('uptime', 0))
            )
        
        # 调度器控制按钮
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if scheduler_status.get('running', False):
                if st.button("⏹️ " + get_text("stop_scheduler")):
                    if stop_scheduler(api_url):
                        st.success(get_text("scheduler_stopped"))
                        st.rerun()
            else:
                if st.button("▶️ " + get_text("start_scheduler")):
                    if start_scheduler(api_url):
                        st.success(get_text("scheduler_started"))
                        st.rerun()
        
        with col2:
            if st.button("🔄 " + get_text("reload_scheduler")):
                if reload_scheduler(api_url):
                    st.success(get_text("scheduler_reloaded"))
                    st.rerun()
        
        with col3:
            if st.button("📊 " + get_text("view_stats")):
                st.session_state.show_scheduler_stats = not st.session_state.get('show_scheduler_stats', False)
    
    # 显示调度器统计信息
    if st.session_state.get('show_scheduler_stats', False):
        st.markdown("---")
        st.subheader(get_text("scheduler_statistics"))
        
        # 这里可以添加更多统计信息的展示
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**{get_text('total_executions')}:** {scheduler_status.get('total_executions', 0)}")
            st.markdown(f"**{get_text('successful_executions')}:** {scheduler_status.get('successful_executions', 0)}")
            st.markdown(f"**{get_text('failed_executions')}:** {scheduler_status.get('failed_executions', 0)}")
        
        with col2:
            st.markdown(f"**{get_text('avg_execution_time')}:** {format_duration(scheduler_status.get('avg_execution_time', 0))}")
            st.markdown(f"**{get_text('total_items_collected')}:** {scheduler_status.get('total_items_collected', 0)}")
            st.markdown(f"**{get_text('last_execution')}:** {format_datetime(scheduler_status.get('last_execution_time'), current_timezone)}")

if __name__ == "__main__":
    main() 