"""
测试日志分析模块的功能。
"""

import json
import pytest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from src.utils.log_analysis import LogQuery, LogAnalytics, LogMonitor

@pytest.fixture
def temp_log_file(tmp_path):
    """创建临时日志文件。"""
    log_file = tmp_path / "test.log"
    
    # 创建测试日志记录
    logs = [
        {
            "time": "2025-04-01T10:00:00Z",
            "level": "INFO",
            "module": "test_module",
            "message": "测试消息1",
            "extra": {"task_id": "123"}
        },
        {
            "time": "2025-04-01T10:01:00Z",
            "level": "ERROR",
            "module": "test_module",
            "message": "错误消息",
            "extra": {"task_id": "123"}
        },
        {
            "time": "2025-04-01T10:02:00Z",
            "level": "INFO",
            "module": "other_module",
            "message": "测试消息2",
            "extra": {"task_id": "456"}
        }
    ]
    
    # 写入JSON格式的日志
    with open(log_file, 'w', encoding='utf-8') as f:
        for log in logs:
            f.write(json.dumps(log, ensure_ascii=False) + '\n')
    
    return log_file

def test_log_query_search(temp_log_file):
    """测试日志查询功能。"""
    query = LogQuery(temp_log_file)
    
    # 测试基本查询
    results = query.search()
    assert len(results) == 3
    
    # 测试按级别过滤
    errors = query.search(level="ERROR")
    assert len(errors) == 1
    assert errors[0]["message"] == "错误消息"
    
    # 测试按模块过滤
    module_logs = query.search(module="test_module")
    assert len(module_logs) == 2
    
    # 测试按消息模式过滤
    pattern_logs = query.search(message_pattern="测试.*")
    assert len(pattern_logs) == 2
    
    # 测试按上下文过滤
    context_logs = query.search(context={"task_id": "123"})
    assert len(context_logs) == 2
    
    # 测试时间范围过滤
    time_logs = query.search(
        start_time=datetime(2025, 4, 1, 10, 1, 0, tzinfo=UTC),
        end_time=datetime(2025, 4, 1, 10, 2, 0, tzinfo=UTC)
    )
    assert len(time_logs) == 2

def test_log_query_aggregate(temp_log_file):
    """测试日志聚合功能。"""
    query = LogQuery(temp_log_file)
    
    # 测试按模块和级别分组
    agg_results = query.aggregate(
        group_by=["module", "level"],
        metrics=["count"]
    )
    
    # 验证聚合结果
    assert agg_results[("test_module", "INFO")]["count"] == 1
    assert agg_results[("test_module", "ERROR")]["count"] == 1
    assert agg_results[("other_module", "INFO")]["count"] == 1

def test_log_analytics_error_distribution(temp_log_file):
    """测试错误分布分析功能。"""
    query = LogQuery(temp_log_file)
    analytics = LogAnalytics(query)
    
    # 获取错误分布
    distribution = analytics.get_error_distribution(
        start_time=datetime(2025, 4, 1, tzinfo=UTC),
        end_time=datetime(2025, 4, 2, tzinfo=UTC),
        group_by="hour"
    )
    
    # 验证分布结果
    assert "2025-04-01 10:00" in distribution
    assert distribution["2025-04-01 10:00"] == 1

def test_log_analytics_anomaly_detection(temp_log_file):
    """测试异常检测功能。"""
    # 创建包含异常值的测试日志
    with open(temp_log_file, 'a', encoding='utf-8') as f:
        anomaly_log = {
            "time": "2025-04-01T10:03:00Z",
            "level": "INFO",
            "module": "test_module",
            "message": "异常值",
            "response_time": 1000  # 异常的响应时间
        }
        f.write(json.dumps(anomaly_log, ensure_ascii=False) + '\n')
        
        # 添加一些正常值
        for i in range(10):
            normal_log = {
                "time": f"2025-04-01T10:{4+i:02d}:00Z",
                "level": "INFO",
                "module": "test_module",
                "message": f"正常值 {i}",
                "response_time": 100  # 正常的响应时间
            }
            f.write(json.dumps(normal_log, ensure_ascii=False) + '\n')
    
    query = LogQuery(temp_log_file)
    analytics = LogAnalytics(query)
    
    # 检测异常
    anomalies = analytics.detect_anomalies(
        metric="response_time",
        window=timedelta(hours=1),
        threshold=2.0
    )
    
    # 验证检测结果
    assert len(anomalies) == 1
    assert anomalies[0]["value"] == 1000

def test_log_monitor(temp_log_file):
    """测试日志监控功能。"""
    monitor = LogMonitor(temp_log_file)
    
    # 用于存储处理的日志记录
    processed_logs = []
    
    def handler(record):
        processed_logs.append(record)
    
    # 添加处理器
    monitor.add_handler(handler)
    
    # 在另一个线程中写入新的日志记录
    import threading
    import time
    
    def write_logs():
        # 增加等待时间，确保监控已经启动
        time.sleep(0.5)
        with open(temp_log_file, 'a', encoding='utf-8') as f:
            new_log = {
                "time": "2025-04-01T10:10:00Z",
                "level": "INFO",
                "module": "test_module",
                "message": "新的日志消息"
            }
            f.write(json.dumps(new_log, ensure_ascii=False) + '\n')
            f.flush()  # 确保写入磁盘
            # 增加等待时间，确保日志被处理
            time.sleep(0.5)
            monitor.stop()
    
    # 启动写入线程
    write_thread = threading.Thread(target=write_logs)
    write_thread.start()
    
    # 启动监控
    monitor.start()
    
    # 等待写入线程完成
    write_thread.join()
    
    # 验证日志是否被处理
    assert len(processed_logs) == 1
    assert processed_logs[0]["message"] == "新的日志消息" 