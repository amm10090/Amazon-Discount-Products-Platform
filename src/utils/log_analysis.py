"""
日志分析模块，提供日志查询、聚合和分析功能。
集成了Loguru的日志系统，支持实时监控和统计分析。
"""

import json
import re
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from collections import defaultdict

from loguru import logger

class LogQuery:
    """
    结构化日志查询工具，支持复杂的日志搜索和过滤。
    """
    
    def __init__(self, log_path: Union[str, Path]):
        self.log_path = Path(log_path)
        if not self.log_path.exists():
            raise FileNotFoundError(f"日志路径不存在: {log_path}")
    
    def search(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        module: Optional[str] = None,
        message_pattern: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        搜索符合条件的日志记录。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            level: 日志级别
            module: 模块名称
            message_pattern: 消息匹配模式
            context: 上下文过滤条件
            limit: 返回结果数量限制
            
        Returns:
            符合条件的日志记录列表
        """
        results = []
        message_regex = re.compile(message_pattern) if message_pattern else None
        
        for log_file in self._get_log_files():
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = self._parse_log_record(line)
                        if not record:
                            continue
                            
                        if not self._match_filters(
                            record,
                            start_time,
                            end_time,
                            level,
                            module,
                            message_regex,
                            context
                        ):
                            continue
                            
                        results.append(record)
                        if len(results) >= limit:
                            return results
                            
                    except Exception as e:
                        logger.warning(f"解析日志记录时出错: {e}")
                        continue
        
        return results
    
    def aggregate(
        self,
        group_by: List[str],
        metrics: List[str],
        filters: Optional[Dict[str, Any]] = None,
        interval: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        聚合日志数据，支持多维度分组和指标计算。
        
        Args:
            group_by: 分组字段列表
            metrics: 需要计算的指标列表
            filters: 过滤条件
            interval: 时间间隔（用于时间序列聚合）
            
        Returns:
            聚合结果
        """
        results = defaultdict(lambda: defaultdict(int))
        
        for log_file in self._get_log_files():
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = self._parse_log_record(line)
                        if not record or not self._match_filters_dict(record, filters or {}):
                            continue
                            
                        group_key = tuple(str(record.get(field, '')) for field in group_by)
                        
                        for metric in metrics:
                            if metric == 'count':
                                results[group_key]['count'] += 1
                            elif metric in record:
                                results[group_key][metric] += 1
                                
                    except Exception as e:
                        logger.warning(f"处理日志聚合时出错: {e}")
                        continue
        
        return dict(results)
    
    def _get_log_files(self) -> List[Path]:
        """获取所有日志文件。"""
        if self.log_path.is_file():
            return [self.log_path]
        return sorted(self.log_path.glob('*.log'))
    
    def _parse_log_record(self, line: str) -> Optional[Dict[str, Any]]:
        """解析单条日志记录。"""
        try:
            if line.strip():
                # 处理JSON格式日志
                if line.strip().startswith('{'):
                    return json.loads(line)
                    
                # 处理文本格式日志
                parts = line.split('|')
                if len(parts) >= 4:
                    return {
                        'time': parts[0].strip(),
                        'level': parts[1].strip(),
                        'module': parts[2].strip(),
                        'message': '|'.join(parts[3:]).strip()
                    }
        except Exception:
            pass
        return None
    
    def _match_filters(
        self,
        record: Dict[str, Any],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        level: Optional[str],
        module: Optional[str],
        message_pattern: Optional[re.Pattern],
        context: Optional[Dict[str, Any]]
    ) -> bool:
        """检查日志记录是否匹配过滤条件。"""
        try:
            # 检查时间范围
            if start_time or end_time:
                record_time = datetime.fromisoformat(record['time'].replace('Z', '+00:00'))
                if start_time and record_time < start_time:
                    return False
                if end_time and record_time > end_time:
                    return False
            
            # 检查日志级别
            if level and record.get('level', '').upper() != level.upper():
                return False
            
            # 检查模块
            if module and record.get('module', '') != module:
                return False
            
            # 检查消息模式
            if message_pattern and not message_pattern.search(record.get('message', '')):
                return False
            
            # 检查上下文
            if context:
                record_context = record.get('extra', {})
                for key, value in context.items():
                    if record_context.get(key) != value:
                        return False
            
            return True
            
        except Exception:
            return False
    
    def _match_filters_dict(self, record: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """检查日志记录是否匹配字典形式的过滤条件。"""
        try:
            for key, value in filters.items():
                if record.get(key) != value:
                    return False
            return True
        except Exception:
            return False

class LogAnalytics:
    """
    日志分析工具，提供统计分析和异常检测功能。
    """
    
    def __init__(self, query: LogQuery):
        self.query = query
    
    def get_error_distribution(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        group_by: str = 'hour'
    ) -> Dict[str, int]:
        """
        分析错误分布情况。
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            group_by: 分组间隔（hour/day/week）
            
        Returns:
            各时间段的错误数量统计
        """
        errors = self.query.search(
            start_time=start_time,
            end_time=end_time,
            level='ERROR'
        )
        
        distribution = defaultdict(int)
        for error in errors:
            try:
                time = datetime.fromisoformat(error['time'].replace('Z', '+00:00'))
                if group_by == 'hour':
                    key = time.strftime('%Y-%m-%d %H:00')
                elif group_by == 'day':
                    key = time.strftime('%Y-%m-%d')
                else:  # week
                    key = f"{time.year}-W{time.isocalendar()[1]}"
                distribution[key] += 1
            except Exception:
                continue
        
        return dict(distribution)
    
    def detect_anomalies(
        self,
        metric: str,
        window: timedelta = timedelta(hours=1),
        threshold: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        检测异常模式。
        
        Args:
            metric: 要监控的指标
            window: 时间窗口
            threshold: 异常阈值（标准差的倍数）
            
        Returns:
            检测到的异常列表
        """
        # 获取所有记录
        records = self.query.search()
        
        if not records:
            return []
        
        # 计算指标的均值和标准差
        values = []
        for record in records:
            try:
                if metric in record:
                    value = float(record.get(metric, 0))
                    values.append(value)
            except (ValueError, TypeError):
                continue
        
        if not values:
            return []
        
        mean = sum(values) / len(values)
        std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
        
        # 检测异常值
        anomalies = []
        for record in records:
            try:
                if metric in record:
                    value = float(record.get(metric, 0))
                    if abs(value - mean) > threshold * std:
                        anomalies.append({
                            'time': record['time'],
                            'value': value,
                            'mean': mean,
                            'std': std,
                            'deviation': abs(value - mean) / std
                        })
            except (ValueError, TypeError):
                continue
        
        return anomalies

class LogMonitor:
    """
    实时日志监控工具，支持日志流处理和告警。
    """
    
    def __init__(self, log_path: Union[str, Path]):
        self.log_path = Path(log_path)
        self.handlers = []
        self._stop = False
    
    def add_handler(self, handler: callable):
        """添加日志处理器。"""
        self.handlers.append(handler)
    
    def start(self):
        """启动监控。"""
        self._stop = False
        try:
            # 打开文件并移动到文件末尾
            with open(self.log_path, 'r', encoding='utf-8') as f:
                f.seek(0, 2)  # 移动到文件末尾
                
                while not self._stop:
                    # 读取新行
                    line = f.readline()
                    if not line:
                        # 没有新行时，等待一会儿再重试
                        import time
                        time.sleep(0.1)
                        continue
                    
                    # 处理日志行
                    try:
                        record = self._parse_log_record(line)
                        if record:
                            # 调用所有处理器
                            for handler in self.handlers:
                                try:
                                    handler(record)
                                except Exception as e:
                                    logger.error(f"处理日志记录时出错: {e}")
                    except Exception as e:
                        logger.error(f"解析日志记录时出错: {e}")
                        continue
        except Exception as e:
            logger.error(f"监控日志文件时出错: {e}")
    
    def stop(self):
        """停止监控。"""
        self._stop = True
    
    def _parse_log_record(self, line: str) -> Optional[Dict[str, Any]]:
        """解析日志记录。"""
        try:
            if line.strip():
                if line.strip().startswith('{'):
                    return json.loads(line)
                
                parts = line.split('|')
                if len(parts) >= 4:
                    return {
                        'time': parts[0].strip(),
                        'level': parts[1].strip(),
                        'module': parts[2].strip(),
                        'message': '|'.join(parts[3:]).strip()
                    }
        except Exception:
            pass
        return None 