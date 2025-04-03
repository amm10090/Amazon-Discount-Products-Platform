"""
日志可视化模块，提供日志数据图表生成和系统健康状态展示功能。
集成了Matplotlib和Plotly库，支持静态和交互式图表。
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import numpy as np

from .log_analysis import LogQuery, LogAnalytics

# 定义中英文对照的图表文本
CHART_TEXTS = {
    'error_rate_title': 'Error Rate Statistics',
    'error_rate_x_label': 'Time',
    'error_rate_y_label': 'Error Rate (%)',
    'response_time_title': '{} Trend',
    'response_time_x_label': 'Time',
    'response_time_y_label': '{}',
    'module_activity_title': 'Module Activity Statistics',
    'module_activity_x_label': 'Module',
    'module_activity_y_label': 'Log Count',
    'moving_average': 'Moving Average',
    
    # 仪表板文本
    'dashboard_title': 'System Health Dashboard',
    'generation_time': 'Generation Time',
    'system_status': 'System Status',
    'system_normal': 'Normal',
    'system_warning': 'Warning',
    'system_danger': 'Danger',
    'error_rate': 'Error Rate',
    'log_count': 'Log Count',
    'anomaly_count': 'Anomaly Count',
    'error_rate_trend': 'Error Rate Trend',
    'response_time_trend': 'Response Time Trend',
    'module_activity': 'Module Activity',
    'detected_anomalies': 'Detected Anomalies',
    'time': 'Time',
    'value': 'Value',
    'mean': 'Mean',
    'std': 'Std Dev',
    'deviation': 'Deviation'
}

class LogChartGenerator:
    """
    日志图表生成器，提供各种图表生成功能。
    """
    
    def __init__(self, query: LogQuery):
        self.query = query
        self.analytics = LogAnalytics(query)
    
    def error_rate_chart(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval: str = 'hour',
        output_path: Optional[str] = None
    ) -> str:
        """
        生成错误率图表。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            interval: 时间间隔（hour/day/week）
            output_path: 输出文件路径
            
        Returns:
            图表文件路径
        """
        # 获取错误分布
        error_dist = self.analytics.get_error_distribution(
            start_time=start_time,
            end_time=end_time,
            group_by=interval
        )
        
        # 获取所有日志记录的时间分布
        all_logs = self.query.search(
            start_time=start_time,
            end_time=end_time
        )
        
        # 计算每个时间段的总日志数
        total_dist = {}
        for log in all_logs:
            try:
                log_time = datetime.fromisoformat(log['time'].replace('Z', '+00:00'))
                if interval == 'hour':
                    key = log_time.strftime('%Y-%m-%d %H:00')
                elif interval == 'day':
                    key = log_time.strftime('%Y-%m-%d')
                else:  # week
                    key = f"{log_time.year}-W{log_time.isocalendar()[1]}"
                    
                total_dist[key] = total_dist.get(key, 0) + 1
            except Exception:
                continue
        
        # 计算错误率
        error_rates = {}
        for key in sorted(total_dist.keys()):
            error_count = error_dist.get(key, 0)
            total_count = total_dist.get(key, 0)
            if total_count > 0:
                error_rates[key] = (error_count / total_count) * 100
            else:
                error_rates[key] = 0
        
        # 生成图表
        plt.figure(figsize=(12, 6))
        x = list(error_rates.keys())
        y = list(error_rates.values())
        
        plt.bar(x, y, color='#E57373')
        plt.title(CHART_TEXTS['error_rate_title'])
        plt.xlabel(CHART_TEXTS['error_rate_x_label'])
        plt.ylabel(CHART_TEXTS['error_rate_y_label'])
        
        plt.xticks(rotation=45)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # 保存图表
        if not output_path:
            output_path = f'error_rate_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            
        plt.savefig(output_path)
        plt.close()
        
        return output_path
    
    def response_time_chart(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        metric: str = 'response_time',
        output_path: Optional[str] = None
    ) -> str:
        """
        生成响应时间趋势图。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            metric: 要分析的指标
            output_path: 输出文件路径
            
        Returns:
            图表文件路径
        """
        # 获取响应时间数据
        logs = self.query.search(
            start_time=start_time,
            end_time=end_time
        )
        
        # 提取时间和响应时间
        times = []
        response_times = []
        
        for log in logs:
            try:
                if metric in log:
                    log_time = datetime.fromisoformat(log['time'].replace('Z', '+00:00'))
                    response_time = float(log[metric])
                    
                    times.append(log_time)
                    response_times.append(response_time)
            except Exception:
                continue
        
        if not times:
            raise ValueError(f"没有找到包含 {metric} 指标的日志记录")
        
        # 按时间排序
        sorted_data = sorted(zip(times, response_times), key=lambda x: x[0])
        times, response_times = zip(*sorted_data)
        
        # 生成图表
        plt.figure(figsize=(12, 6))
        plt.plot(times, response_times, marker='o', linestyle='-', markersize=3)
        
        metric_title = metric.replace('_', ' ').title()
        plt.title(CHART_TEXTS['response_time_title'].format(metric_title))
        plt.xlabel(CHART_TEXTS['response_time_x_label'])
        plt.ylabel(CHART_TEXTS['response_time_y_label'].format(metric_title))
        
        plt.xticks(rotation=45)
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 格式化x轴日期
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        
        # 计算移动平均线
        if len(response_times) >= 5:
            window_size = min(5, len(response_times))
            moving_avg = np.convolve(response_times, np.ones(window_size)/window_size, mode='valid')
            plt.plot(times[window_size-1:], moving_avg, 'r--', label=CHART_TEXTS['moving_average'])
            plt.legend()
        
        plt.tight_layout()
        
        # 保存图表
        if not output_path:
            output_path = f'{metric}_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            
        plt.savefig(output_path)
        plt.close()
        
        return output_path
    
    def module_activity_chart(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成模块活动图表。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            output_path: 输出文件路径
            
        Returns:
            图表文件路径
        """
        # 获取日志数据
        logs = self.query.search(
            start_time=start_time,
            end_time=end_time
        )
        
        # 统计各模块的日志数量
        module_counts = {}
        for log in logs:
            module = log.get('module', 'unknown')
            module_counts[module] = module_counts.get(module, 0) + 1
        
        # 按日志数量排序
        sorted_modules = sorted(module_counts.items(), key=lambda x: x[1], reverse=True)
        
        # 取前10个模块
        top_modules = sorted_modules[:10]
        modules, counts = zip(*top_modules) if top_modules else ([], [])
        
        # 生成图表
        plt.figure(figsize=(12, 6))
        plt.bar(modules, counts, color=plt.cm.viridis(np.linspace(0, 0.9, len(modules))))
        
        plt.title(CHART_TEXTS['module_activity_title'])
        plt.xlabel(CHART_TEXTS['module_activity_x_label'])
        plt.ylabel(CHART_TEXTS['module_activity_y_label'])
        
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # 保存图表
        if not output_path:
            output_path = f'module_activity_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            
        plt.savefig(output_path)
        plt.close()
        
        return output_path

class SystemHealthDashboard:
    """
    系统健康状态仪表板，提供系统关键指标的可视化展示。
    """
    
    def __init__(self, log_path: Union[str, Path]):
        self.query = LogQuery(log_path)
        self.analytics = LogAnalytics(self.query)
        self.chart_generator = LogChartGenerator(self.query)
    
    def generate_dashboard(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        生成系统健康状态仪表板。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            output_dir: 输出目录
            
        Returns:
            包含各图表路径的字典
        """
        if not output_dir:
            output_dir = f'dashboard_{datetime.now().strftime("%Y%m%d%H%M%S")}'
            
        Path(output_dir).mkdir(exist_ok=True)
        
        # 生成各类图表
        charts = {}
        
        # 错误率图表
        charts['error_rate'] = self.chart_generator.error_rate_chart(
            start_time=start_time,
            end_time=end_time,
            output_path=f'{output_dir}/error_rate.png'
        )
        
        # 尝试生成响应时间图表
        try:
            charts['response_time'] = self.chart_generator.response_time_chart(
                start_time=start_time,
                end_time=end_time,
                output_path=f'{output_dir}/response_time.png'
            )
        except ValueError:
            # 如果没有响应时间数据，则忽略
            pass
        
        # 模块活动图表
        charts['module_activity'] = self.chart_generator.module_activity_chart(
            start_time=start_time,
            end_time=end_time,
            output_path=f'{output_dir}/module_activity.png'
        )
        
        # 生成仪表板HTML
        html_content = self._generate_html(charts)
        html_path = f'{output_dir}/dashboard.html'
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        charts['dashboard'] = html_path
        
        return charts
    
    def _generate_html(self, charts: Dict[str, str]) -> str:
        """生成仪表板HTML内容。"""
        # 计算系统健康状态指标
        error_logs = self.query.search(level='ERROR')
        all_logs = self.query.search()
        
        # 错误率
        error_rate = (len(error_logs) / len(all_logs)) * 100 if all_logs else 0
        
        # 异常检测
        anomalies = []
        try:
            anomalies = self.analytics.detect_anomalies(metric='response_time')
        except:
            pass
        
        # 根据错误率判断系统状态
        if error_rate < 1:
            status_class = 'good'
            status_text = CHART_TEXTS['system_normal']
        elif error_rate < 5:
            status_class = 'warning'
            status_text = CHART_TEXTS['system_warning']
        else:
            status_class = 'danger'
            status_text = CHART_TEXTS['system_danger']
        
        # 生成HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{CHART_TEXTS['dashboard_title']}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                .header {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }}
                .card {{
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    padding: 15px;
                }}
                .chart-container {{
                    text-align: center;
                    margin-top: 20px;
                }}
                .metrics {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                }}
                .metric-card {{
                    flex: 1;
                    min-width: 200px;
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    padding: 15px;
                }}
                .metric-value {{
                    font-size: 24px;
                    font-weight: bold;
                    margin-top: 10px;
                }}
                .good {{
                    color: #2ecc71;
                }}
                .warning {{
                    color: #f39c12;
                }}
                .danger {{
                    color: #e74c3c;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{CHART_TEXTS['dashboard_title']}</h1>
                    <p>{CHART_TEXTS['generation_time']}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="metrics">
                    <div class="metric-card">
                        <h3>{CHART_TEXTS['system_status']}</h3>
                        <div class="metric-value {status_class}">
                            {status_text}
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <h3>{CHART_TEXTS['error_rate']}</h3>
                        <div class="metric-value {status_class}">
                            {error_rate:.2f}%
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <h3>{CHART_TEXTS['log_count']}</h3>
                        <div class="metric-value">
                            {len(all_logs)}
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <h3>{CHART_TEXTS['anomaly_count']}</h3>
                        <div class="metric-value {'good' if len(anomalies) == 0 else 'danger'}">
                            {len(anomalies)}
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>{CHART_TEXTS['error_rate_trend']}</h2>
                    <div class="chart-container">
                        <img src="{charts.get('error_rate', '').replace(chr(92), '/')}" alt="{CHART_TEXTS['error_rate_trend']}" style="max-width:100%;">
                    </div>
                </div>
        """
        
        if 'response_time' in charts:
            html += f"""
                <div class="card">
                    <h2>{CHART_TEXTS['response_time_trend']}</h2>
                    <div class="chart-container">
                        <img src="{charts.get('response_time', '').replace(chr(92), '/')}" alt="{CHART_TEXTS['response_time_trend']}" style="max-width:100%;">
                    </div>
                </div>
            """
        
        html += f"""
                <div class="card">
                    <h2>{CHART_TEXTS['module_activity']}</h2>
                    <div class="chart-container">
                        <img src="{charts.get('module_activity', '').replace(chr(92), '/')}" alt="{CHART_TEXTS['module_activity']}" style="max-width:100%;">
                    </div>
                </div>
        """
        
        if anomalies:
            html += f"""
                <div class="card">
                    <h2>{CHART_TEXTS['detected_anomalies']}</h2>
                    <table>
                        <tr>
                            <th>{CHART_TEXTS['time']}</th>
                            <th>{CHART_TEXTS['value']}</th>
                            <th>{CHART_TEXTS['mean']}</th>
                            <th>{CHART_TEXTS['std']}</th>
                            <th>{CHART_TEXTS['deviation']}</th>
                        </tr>
            """
            
            for anomaly in anomalies:
                html += f"""
                        <tr>
                            <td>{anomaly['time']}</td>
                            <td>{anomaly['value']}</td>
                            <td>{anomaly['mean']:.2f}</td>
                            <td>{anomaly['std']:.2f}</td>
                            <td>{anomaly['deviation']:.2f}</td>
                        </tr>
                """
                
            html += """
                    </table>
                </div>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html

class LogExporter:
    """
    日志导出工具，提供日志导出和备份功能。
    """
    
    def __init__(self, query: LogQuery):
        self.query = query
    
    def export_to_json(
        self,
        output_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        module: Optional[str] = None
    ) -> str:
        """
        将日志导出为JSON格式。
        
        Args:
            output_path: 输出文件路径
            start_time: 开始时间
            end_time: 结束时间
            level: 日志级别
            module: 模块名称
            
        Returns:
            输出文件路径
        """
        # 搜索符合条件的日志
        logs = self.query.search(
            start_time=start_time,
            end_time=end_time,
            level=level,
            module=module
        )
        
        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
            
        return output_path
    
    def export_to_csv(
        self,
        output_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        module: Optional[str] = None
    ) -> str:
        """
        将日志导出为CSV格式。
        
        Args:
            output_path: 输出文件路径
            start_time: 开始时间
            end_time: 结束时间
            level: 日志级别
            module: 模块名称
            
        Returns:
            输出文件路径
        """
        # 搜索符合条件的日志
        logs = self.query.search(
            start_time=start_time,
            end_time=end_time,
            level=level,
            module=module
        )
        
        if not logs:
            raise ValueError("没有找到符合条件的日志记录")
        
        # 确定CSV列头
        sample = logs[0]
        fields = ['time', 'level', 'module', 'message']
        
        # 添加额外字段
        for key in sample.keys():
            if key not in fields:
                fields.append(key)
        
        # 写入CSV文件
        import csv
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            
            for log in logs:
                row = [log.get(field, '') for field in fields]
                writer.writerow(row)
                
        return output_path 