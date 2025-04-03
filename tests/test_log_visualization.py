"""
测试日志可视化模块的功能。
"""

import os
import json
import pytest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from src.utils.log_analysis import LogQuery
from src.utils.log_visualization import LogChartGenerator, SystemHealthDashboard, LogExporter

@pytest.fixture
def temp_log_file(tmp_path):
    """创建临时日志文件。"""
    log_file = tmp_path / "test.log"
    
    # 创建测试日志记录（包含响应时间数据）
    logs = []
    
    # 添加一些INFO日志
    for i in range(10):
        logs.append({
            "time": f"2025-04-01T{10+i:02d}:00:00Z",
            "level": "INFO",
            "module": "api_service" if i % 2 == 0 else "data_service",
            "message": f"处理请求 {i}",
            "response_time": 100 + i * 10,
            "extra": {"task_id": f"task-{i}"}
        })
    
    # 添加一些ERROR日志
    for i in range(2):
        logs.append({
            "time": f"2025-04-01T{10+i*2:02d}:30:00Z",
            "level": "ERROR",
            "module": "api_service",
            "message": f"请求处理失败 {i}",
            "response_time": 500 + i * 100,
            "extra": {"task_id": f"task-error-{i}"}
        })
    
    # 写入JSON格式的日志
    with open(log_file, 'w', encoding='utf-8') as f:
        for log in logs:
            f.write(json.dumps(log, ensure_ascii=False) + '\n')
    
    return log_file

@pytest.fixture
def output_dir(tmp_path):
    """创建临时输出目录。"""
    path = tmp_path / "output"
    path.mkdir()
    return path

def test_log_chart_generator(temp_log_file, output_dir):
    """测试日志图表生成功能。"""
    # 初始化LogQuery和LogChartGenerator
    query = LogQuery(temp_log_file)
    chart_generator = LogChartGenerator(query)
    
    # 测试错误率图表生成
    error_chart_path = chart_generator.error_rate_chart(
        output_path=str(output_dir / "error_rate.png")
    )
    assert os.path.exists(error_chart_path)
    
    # 测试响应时间图表生成
    response_time_chart_path = chart_generator.response_time_chart(
        output_path=str(output_dir / "response_time.png")
    )
    assert os.path.exists(response_time_chart_path)
    
    # 测试模块活动图表生成
    module_chart_path = chart_generator.module_activity_chart(
        output_path=str(output_dir / "module_activity.png")
    )
    assert os.path.exists(module_chart_path)

def test_system_health_dashboard(temp_log_file, output_dir):
    """测试系统健康状态仪表板生成功能。"""
    dashboard = SystemHealthDashboard(temp_log_file)
    
    # 生成仪表板
    charts = dashboard.generate_dashboard(
        output_dir=str(output_dir / "dashboard")
    )
    
    # 验证生成的文件
    assert 'dashboard' in charts
    assert os.path.exists(charts['dashboard'])
    assert os.path.exists(charts['error_rate'])
    assert os.path.exists(charts['response_time'])
    assert os.path.exists(charts['module_activity'])
    
    # 验证HTML内容
    with open(charts['dashboard'], 'r', encoding='utf-8') as f:
        html_content = f.read()
        assert 'System Health Dashboard' in html_content
        assert 'Error Rate' in html_content
        assert 'Log Count' in html_content

def test_log_exporter(temp_log_file, output_dir):
    """测试日志导出功能。"""
    query = LogQuery(temp_log_file)
    exporter = LogExporter(query)
    
    # 导出为JSON
    json_path = exporter.export_to_json(
        output_path=str(output_dir / "logs.json")
    )
    assert os.path.exists(json_path)
    
    # 验证JSON内容
    with open(json_path, 'r', encoding='utf-8') as f:
        logs = json.load(f)
        assert len(logs) == 12  # 总共12条日志
    
    # 导出为CSV
    csv_path = exporter.export_to_csv(
        output_path=str(output_dir / "logs.csv")
    )
    assert os.path.exists(csv_path)
    
    # 验证CSV内容
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) == 13  # 1个表头 + 12条日志
        
    # 测试按级别过滤导出
    error_json_path = exporter.export_to_json(
        output_path=str(output_dir / "errors.json"),
        level="ERROR"
    )
    
    with open(error_json_path, 'r', encoding='utf-8') as f:
        error_logs = json.load(f)
        assert len(error_logs) == 2  # 2条ERROR日志 