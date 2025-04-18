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
        # 检查任务ID
        job_id = job_config.get("id", "")
        if not job_id or job_id.strip() == "":
            st.error("任务ID不能为空")
            return False
            
        # 确保crawler_type存在
        if "crawler_type" not in job_config:
            st.error("任务类型不能为空")
            return False
            
        # 打印提交的配置到控制台以便调试
        print(f"发送任务配置: {job_config}")
            
        # 发送API请求
        response = requests.post(
            f"{api_url}/api/scheduler/jobs",
            json=job_config,
            timeout=10  # 设置超时时间
        )
        
        # 检查响应
        if response.status_code == 200:
            # 清除任务列表缓存
            cache_manager.clear_cache()
            return True
        else:
            # 完整记录错误响应
            print(f"服务器返回错误 - 状态码: {response.status_code}, 响应内容: {response.text}")
            
            # 尝试从响应中获取错误信息
            try:
                error_data = response.json()
                error_message = error_data.get("detail", "未知错误")
                st.error(f"{get_text('add_job_failed')}: {error_message}")
            except Exception as json_error:
                # JSON解析失败，直接显示响应文本
                st.error(f"{get_text('add_job_failed')}: 状态码 {response.status_code}, 响应: {response.text[:200]}")
                print(f"解析响应JSON失败: {str(json_error)}")
            return False
            
    except requests.RequestException as e:
        # 网络请求错误
        st.error(f"{get_text('add_job_failed')}: 网络请求错误 - {str(e)}")
        print(f"请求错误: {str(e)}")
        return False
    except Exception as e:
        # 其他未知错误
        st.error(f"{get_text('add_job_failed')}: {str(e)}")
        print(f"添加任务时发生未知错误: {str(e)}")
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
    if 'show_scheduler_stats' not in st.session_state:
        st.session_state.show_scheduler_stats = False
    if 'task_category' not in st.session_state:
        st.session_state.task_category = "crawler"
    if 'job_type' not in st.session_state:
        st.session_state.job_type = "cron"
    if 'task_type' not in st.session_state:
        st.session_state.task_type = "bestseller"
    if 'show_advanced_config' not in st.session_state:
        st.session_state.show_advanced_config = False
    if 'show_discount_config' not in st.session_state:
        st.session_state.show_discount_config = False
    
    # API地址
    api_url = f"http://{config['api']['host']}:{config['api']['port']}"
    
    # 获取调度器状态和当前时区
    scheduler_status = get_scheduler_status(api_url)
    current_timezone = scheduler_status.get('timezone', 'UTC')
    
    # 预先加载所有任务作为全局变量供验证使用
    existing_jobs = load_jobs(api_url)
    existing_job_ids = [job['id'] for job in existing_jobs] if existing_jobs else []
    
    # 创建任务类型分类
    task_categories = {
        "crawler": {
            "title": get_text("crawler_tasks"),
            "types": ["bestseller", "coupon", "all", "discount"],
            "icon": "🕷️"
        },
        "update": {
            "title": get_text("update_tasks"),
            "types": ["update"],
            "icon": "🔄"
        },
        "cj_crawler": {
            "title": get_text("cj_crawler_tasks"),
            "types": ["cj"],
            "icon": "🛒"
        }
    }
    
    # 定义回调函数用于更新session_state
    def update_task_category():
        st.session_state.task_category = st.session_state.task_category_select
        # 重置任务类型为该分类下的第一个
        st.session_state.task_type = task_categories[st.session_state.task_category]["types"][0]
        
    def update_job_type():
        st.session_state.job_type = st.session_state.job_type_select
        
    def update_task_type():
        st.session_state.task_type = st.session_state.task_type_select
        
    def toggle_advanced_config():
        st.session_state.show_advanced_config = not st.session_state.show_advanced_config
        
    def toggle_discount_config():
        st.session_state.show_discount_config = not st.session_state.show_discount_config
    
    # 表单外选择任务类型和分类，这样可以立即触发UI更新
    st.subheader(get_text("add_new_job"))
    
    # 表单外选择任务类型和分类，这样可以立即触发UI更新
    col1, col2 = st.columns(2)
    
    with col1:
        # 先选择任务分类和类型
        st.selectbox(
            get_text("task_category"),
            options=list(task_categories.keys()),
            key="task_category_select",
            format_func=lambda x: f"{task_categories[x]['icon']} {task_categories[x]['title']}",
            on_change=update_task_category,
            help=get_text("task_category_help")
        )
        
        st.selectbox(
            get_text("task_type"),
            options=task_categories[st.session_state.task_category]["types"],
            key="task_type_select",
            format_func=lambda x: get_text(f"crawler_{x}"),
            on_change=update_task_type,
            help=get_text("task_type_help")
        )
        
        st.selectbox(
            get_text("job_type"),
            options=["cron", "interval"],
            key="job_type_select",
            on_change=update_job_type,
            format_func=lambda x: "定时任务 (Cron)" if x == "cron" else "间隔任务 (Interval)",
            help=get_text("job_type_help")
        )
        
        # 添加清晰的说明
        st.markdown("""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-top: 10px;">
        <strong>📝 任务创建说明:</strong>
        <ul>
          <li>任务ID必须填写且不能重复</li>
          <li>定时任务(Cron)按指定时间执行</li>
          <li>间隔任务(Interval)按固定间隔执行</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # 在表单外显示高级配置选项
    if st.session_state.task_category == "update" and st.session_state.task_type == "update":
        st.markdown("---")
        st.subheader("更新器高级配置")
        show_config = st.checkbox("显示高级配置选项", value=st.session_state.show_advanced_config, on_change=toggle_advanced_config)
        
    elif st.session_state.task_category == "crawler" and st.session_state.task_type == "discount":
        st.markdown("---")
        st.subheader("优惠券更新爬虫高级配置")
        show_config = st.checkbox("显示高级配置选项", value=st.session_state.show_discount_config, on_change=toggle_discount_config)
    
    # 添加CJ爬虫高级配置选项
    elif st.session_state.task_category == "cj_crawler" and st.session_state.task_type == "cj":
        st.markdown("---")
        st.subheader("CJ爬虫高级配置")
        if "show_cj_config" not in st.session_state:
            st.session_state.show_cj_config = False
            
        def toggle_cj_config():
            st.session_state.show_cj_config = not st.session_state.show_cj_config
            
        show_config = st.checkbox("显示高级配置选项", value=st.session_state.show_cj_config, on_change=toggle_cj_config)
    
    # 根据高级配置状态显示相应的配置选项
    updater_config = {}
    discount_config = {}
    cj_config = {}
    
    # 更新器高级配置
    if st.session_state.task_category == "update" and st.session_state.task_type == "update" and st.session_state.show_advanced_config:
        col1, col2 = st.columns(2)
        
        with col1:
            # 优先级配置
            updater_config["urgent_priority_hours"] = st.number_input(
                "紧急优先级更新间隔(小时)",
                min_value=1,
                max_value=24,
                value=1,
                help="紧急优先级商品（价格为0）的更新间隔"
            )
            
            updater_config["high_priority_hours"] = st.number_input(
                "高优先级更新间隔(小时)",
                min_value=1,
                max_value=48,
                value=6,
                help="高优先级商品的更新间隔"
            )
            
            updater_config["medium_priority_hours"] = st.number_input(
                "中优先级更新间隔(小时)",
                min_value=1,
                max_value=72,
                value=24,
                help="中优先级商品的更新间隔"
            )
            
            updater_config["low_priority_hours"] = st.number_input(
                "低优先级更新间隔(小时)",
                min_value=1,
                max_value=168,
                value=72,
                help="低优先级商品的更新间隔"
            )
            
            updater_config["very_low_priority_hours"] = st.number_input(
                "非常低优先级更新间隔(小时)",
                min_value=1,
                max_value=720,
                value=168,
                help="非常低优先级商品的更新间隔"
            )
        
        with col2:
            # 处理配置
            updater_config["batch_size"] = st.number_input(
                "批处理大小",
                min_value=10,
                max_value=1000,
                value=500,
                help="每批处理的商品数量"
            )
            
            updater_config["max_retries"] = st.number_input(
                "最大重试次数",
                min_value=1,
                max_value=10,
                value=3,
                help="API请求失败时的最大重试次数"
            )
            
            updater_config["retry_delay"] = st.number_input(
                "重试延迟(秒)",
                min_value=0.5,
                max_value=10.0,
                value=2.0,
                step=0.5,
                help="重试之间的延迟时间"
            )
            
            updater_config["parallel_requests"] = st.number_input(
                "并行请求数量",
                min_value=1,
                max_value=20,
                value=5,
                help="并行处理的请求数量"
            )
            
            updater_config["update_category_info"] = st.checkbox(
                "更新品类信息",
                value=False,
                help="是否更新商品品类信息（不常变化）"
            )
            
            updater_config["force_cj_check"] = st.checkbox(
                "强制检查CJ平台",
                value=False,
                help="是否强制检查所有商品在CJ平台的可用性"
            )
    
    # 折扣爬虫高级配置
    elif st.session_state.task_category == "crawler" and st.session_state.task_type == "discount" and st.session_state.show_discount_config:
        col1, col2 = st.columns(2)
        
        with col1:
            # 线程和批量配置
            discount_config["num_threads"] = st.number_input(
                "爬虫线程数",
                min_value=1,
                max_value=16,
                value=4,
                help="并行处理的线程数量，根据系统性能调整"
            )
            
            discount_config["update_interval"] = st.number_input(
                "更新间隔(小时)",
                min_value=1,
                max_value=168,
                value=24,
                help="优惠券信息更新间隔，超过该时间的商品将被重新抓取"
            )
            
            discount_config["force_update"] = st.checkbox(
                "强制更新",
                value=False,
                help="强制更新所有商品，忽略更新间隔"
            )
        
        with col2:
            # 抓取配置
            discount_config["headless"] = st.checkbox(
                "无头模式",
                value=True,
                help="启用无头模式，不显示浏览器窗口"
            )
            
            discount_config["min_delay"] = st.number_input(
                "最小延迟(秒)",
                min_value=0.5,
                max_value=10.0,
                value=2.0,
                step=0.5,
                help="请求之间的最小延迟时间"
            )
            
            discount_config["max_delay"] = st.number_input(
                "最大延迟(秒)",
                min_value=1.0,
                max_value=15.0,
                value=4.0,
                step=0.5,
                help="请求之间的最大延迟时间"
            )
            
            discount_config["debug"] = st.checkbox(
                "调试模式",
                value=False,
                help="启用调试模式，输出更详细的日志"
            )
    
    # CJ爬虫高级配置
    elif st.session_state.task_category == "cj_crawler" and st.session_state.task_type == "cj" and st.session_state.show_cj_config:
        col1, col2 = st.columns(2)
        
        with col1:
            # 并行抓取配置
            cj_config["use_parallel"] = st.checkbox(
                "启用并行抓取",
                value=True,
                help="启用多工作进程并行抓取，提高效率"
            )
            
            cj_config["workers"] = st.number_input(
                "工作进程数量",
                min_value=1,
                max_value=10,
                value=3,
                help="并行工作进程数量，根据系统性能调整"
            )
            
            cj_config["skip_existing"] = st.checkbox(
                "跳过已存在商品",
                value=True,
                help="是否跳过数据库中已存在的商品"
            )
        
        with col2:
            # 游标策略配置
            cj_config["use_random_cursor"] = st.checkbox(
                "使用随机游标",
                value=False,
                help="是否使用随机游标策略（当不使用并行抓取时有效）"
            )
            
            cj_config["filter_similar_variants"] = st.checkbox(
                "过滤相似变体",
                value=True,
                help="是否过滤优惠相同的变体商品"
            )
            
            st.info("游标优先级队列已启用，基于成功率、商品密度和时间衰减因子自动选择最优游标")
    
    # 添加新任务表单 - 现在表单只包含基本输入项，其他配置都在外部
    with st.form("add_job"):
        col1, col2 = st.columns(2)
        
        with col1:
            job_id = st.text_input(
                get_text("job_id"),
                help=get_text("job_id_help"),
                placeholder="例如: daily_bestseller_1"
            )
            
            # 添加提示说明
            st.caption("任务ID必须是唯一的，不能与现有任务重复")
        
        with col2:
            max_items = st.number_input(
                get_text("max_items"),
                min_value=10,
                max_value=1000,
                value=100,
                step=10,
                help=get_text("max_items_help")
            )
            
            if st.session_state.job_type == "cron":
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
            # 获取当前输入值并去除空格
            current_job_id = job_id.strip() if job_id else ""
            
            # 验证任务ID
            if not current_job_id:
                st.error("任务ID不能为空")
            elif current_job_id in existing_job_ids:
                # 显示已存在的任务
                matching_job = next((job for job in existing_jobs if job['id'] == current_job_id), None)
                if matching_job:
                    crawler_type = matching_job.get('crawler_type', 'unknown')
                    max_items = matching_job.get('max_items', '未知')
                    st.error(f"任务ID '{current_job_id}' 已存在，请使用其他ID")
                    st.warning(
                        f"已存在的任务信息: "
                        f"类型={get_text(f'crawler_{crawler_type}')}，"
                        f"最大采集数量={max_items}"
                    )
            else:
                try:
                    # 构建任务配置
                    job_config = {
                        "id": current_job_id,
                        "type": st.session_state.job_type,
                        "crawler_type": st.session_state.task_type,
                        "max_items": max_items
                    }
                    
                    if st.session_state.job_type == "cron":
                        job_config.update({
                            "hour": hour,
                            "minute": minute
                        })
                    else:
                        # 确保至少有一个时间参数大于0
                        if hours <= 0 and minutes <= 0:
                            st.error("间隔时间不能全为0")
                            raise ValueError("间隔时间不能全为0")
                            
                        job_config.update({
                            "hours": hours,
                            "minutes": minutes
                        })
                    
                    # 添加更新器配置
                    if st.session_state.task_category == "update" and st.session_state.task_type == "update" and st.session_state.show_advanced_config:
                        job_config["updater_config"] = updater_config
                        
                    # 添加折扣爬虫配置
                    if st.session_state.task_category == "crawler" and st.session_state.task_type == "discount" and st.session_state.show_discount_config:
                        job_config["discount_config"] = discount_config
                    
                    # 添加CJ爬虫配置
                    if st.session_state.task_category == "cj_crawler" and st.session_state.task_type == "cj" and st.session_state.show_cj_config:
                        job_config["cj_config"] = cj_config
                    
                    # 在界面上显示将要提交的配置
                    with st.expander("提交的任务配置", expanded=False):
                        st.json(job_config)
                    
                    # 添加任务
                    if add_job(api_url, job_config):
                        st.success(get_text("job_added"))
                        st.rerun()
                except Exception as e:
                    st.error(f"创建任务出错: {str(e)}")
    
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
                    
                    # 显示更新器配置按钮
                    if job['crawler_type'] == 'update' and ('updater_config' in job):
                        updater_config = job.get('updater_config', {})
                        if updater_config:
                            # 初始化会话状态，如果不存在
                            if f"show_updater_config_{job['id']}" not in st.session_state:
                                st.session_state[f"show_updater_config_{job['id']}"] = False
                                
                            # 定义回调函数来切换状态
                            def toggle_updater_view(job_id=job['id']):
                                st.session_state[f"show_updater_config_{job_id}"] = not st.session_state[f"show_updater_config_{job_id}"]
                                
                            # 使用on_click回调
                            st.button("查看更新器配置", 
                                      key=f"show_updater_btn_{job['id']}", 
                                      on_click=toggle_updater_view, 
                                      args=(job['id'],))
                    
                    # 显示折扣爬虫配置按钮
                    elif job['crawler_type'] == 'discount':
                        # 检查是否有任何配置 - 直接检查discount_config字段
                        if 'discount_config' in job:
                            # 初始化会话状态，如果不存在
                            if f"show_discount_config_{job['id']}" not in st.session_state:
                                st.session_state[f"show_discount_config_{job['id']}"] = False
                                
                            # 定义回调函数来切换状态
                            def toggle_config_view(job_id=job['id']):
                                st.session_state[f"show_discount_config_{job_id}"] = not st.session_state[f"show_discount_config_{job_id}"]
                                
                            # 使用on_click回调，而不是在按钮被点击后修改状态
                            st.button("查看优惠券更新配置", 
                                      key=f"show_config_btn_{job['id']}", 
                                      on_click=toggle_config_view, 
                                      args=(job['id'],))
                
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
                
                # 显示更新器配置详情
                if job['crawler_type'] == 'update' and 'updater_config' in job and \
                   st.session_state.get(f"show_updater_config_{job['id']}", False):
                    st.markdown("---")
                    st.subheader("更新器配置详情")
                    
                    updater_config = job.get('updater_config', {})
                    if updater_config:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**优先级配置**")
                            st.markdown(f"- 紧急优先级更新间隔: {updater_config.get('urgent_priority_hours', 1)}小时")
                            st.markdown(f"- 高优先级更新间隔: {updater_config.get('high_priority_hours', 6)}小时")
                            st.markdown(f"- 中优先级更新间隔: {updater_config.get('medium_priority_hours', 24)}小时")
                            st.markdown(f"- 低优先级更新间隔: {updater_config.get('low_priority_hours', 72)}小时")
                            st.markdown(f"- 非常低优先级更新间隔: {updater_config.get('very_low_priority_hours', 168)}小时")
                        
                        with col2:
                            st.markdown("**处理配置**")
                            st.markdown(f"- 批处理大小: {updater_config.get('batch_size', 500)}")
                            st.markdown(f"- 最大重试次数: {updater_config.get('max_retries', 3)}")
                            st.markdown(f"- 重试延迟: {updater_config.get('retry_delay', 2.0)}秒")
                            st.markdown(f"- 并行请求数量: {updater_config.get('parallel_requests', 5)}")
                            st.markdown(f"- 更新品类信息: {'是' if updater_config.get('update_category_info', False) else '否'}")
                            st.markdown(f"- 强制检查CJ平台: {'是' if updater_config.get('force_cj_check', False) else '否'}")
                    else:
                        st.info("该任务使用默认更新器配置")
                
                # 显示折扣爬虫配置详情
                if job['crawler_type'] == 'discount' and \
                   st.session_state.get(f"show_discount_config_{job['id']}", False):
                    st.markdown("---")
                    st.subheader("优惠券更新配置详情")
                    
                    # 获取配置信息 - 直接从discount_config获取
                    discount_config = job.get('discount_config', {})
                    
                    if discount_config:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**基本配置**")
                            st.markdown(f"- 线程数量: {discount_config.get('num_threads', 4)}")
                            st.markdown(f"- 更新间隔: {discount_config.get('update_interval', 24)}小时")
                            st.markdown(f"- 强制更新: {'是' if discount_config.get('force_update', False) else '否'}")
                        
                        with col2:
                            st.markdown("**抓取配置**")
                            st.markdown(f"- 无头模式: {'是' if discount_config.get('headless', True) else '否'}")
                            st.markdown(f"- 最小延迟: {discount_config.get('min_delay', 2.0)}秒")
                            st.markdown(f"- 最大延迟: {discount_config.get('max_delay', 4.0)}秒")
                            st.markdown(f"- 调试模式: {'是' if discount_config.get('debug', False) else '否'}")
                    else:
                        st.info("该任务使用默认优惠券更新配置")
                
                # 显示CJ爬虫配置详情
                if job['crawler_type'] == 'cj':
                    # 初始化会话状态，如果不存在
                    if f"show_cj_config_{job['id']}" not in st.session_state:
                        st.session_state[f"show_cj_config_{job['id']}"] = False
                        
                    # 定义回调函数来切换状态
                    def toggle_cj_view(job_id=job['id']):
                        st.session_state[f"show_cj_config_{job_id}"] = not st.session_state[f"show_cj_config_{job_id}"]
                        
                    # 显示查看按钮
                    st.button("查看CJ爬虫配置", 
                              key=f"show_cj_btn_{job['id']}", 
                              on_click=toggle_cj_view, 
                              args=(job['id'],))
                    
                    # 显示配置详情
                    if st.session_state.get(f"show_cj_config_{job['id']}", False):
                        st.markdown("---")
                        st.subheader("CJ爬虫配置详情")
                        
                        # 获取配置信息
                        cj_config = job.get('cj_config', {})
                        
                        if cj_config:
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**并行配置**")
                                st.markdown(f"- 并行抓取: {'启用' if cj_config.get('use_parallel', True) else '禁用'}")
                                st.markdown(f"- 工作进程: {cj_config.get('workers', 3)}个")
                                st.markdown(f"- 跳过已存在: {'是' if cj_config.get('skip_existing', True) else '否'}")
                            
                            with col2:
                                st.markdown("**游标策略**")
                                st.markdown(f"- 随机游标: {'启用' if cj_config.get('use_random_cursor', False) else '禁用'}")
                                st.markdown(f"- 过滤变体: {'是' if cj_config.get('filter_similar_variants', True) else '否'}")
                                st.markdown("- 游标优先级队列: 已启用")
                        else:
                            st.info("该任务使用默认CJ爬虫配置")
                
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