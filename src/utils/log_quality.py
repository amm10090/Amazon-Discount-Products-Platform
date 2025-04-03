"""
日志质量评估工具

提供日志质量评估功能，用于检查和评估Loguru日志系统的实现质量。
包括日志格式检查、覆盖率分析、上下文数据使用情况等评估指标。
"""

import re
import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

from loguru import logger

class LogQualityMetrics:
    """
    日志质量评估指标
    
    包含多种日志质量评估指标和得分计算方法
    """
    
    def __init__(self):
        """初始化评估指标"""
        # 日志分类指标
        self.log_count_by_level = {
            "TRACE": 0,
            "DEBUG": 0,
            "INFO": 0,
            "SUCCESS": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0
        }
        
        # 日志内容指标
        self.logs_with_context = 0  # 包含上下文数据的日志数
        self.logs_with_exception = 0  # 包含异常信息的日志数
        self.logs_with_structured_data = 0  # 包含结构化数据的日志数
        
        # 日志格式指标
        self.logs_with_good_format = 0  # 格式良好的日志数
        self.logs_with_poor_format = 0  # 格式不佳的日志数
        
        # 日志分布指标
        self.files_with_logs = 0  # 包含日志的文件数
        self.modules_with_logs = set()  # 包含日志的模块
        
        # 总数统计
        self.total_log_calls = 0  # 总日志调用数
        self.total_files_analyzed = 0  # 分析的文件总数
    
    def calculate_scores(self) -> Dict[str, float]:
        """
        计算各维度得分
        
        Returns:
            各维度得分字典
        """
        scores = {}
        
        # 避免除零错误
        if self.total_log_calls == 0:
            return {
                "level_balance_score": 0.0,
                "context_usage_score": 0.0,
                "format_quality_score": 0.0,
                "exception_handling_score": 0.0,
                "coverage_score": 0.0,
                "overall_score": 0.0
            }
        
        # 1. 日志级别平衡得分 (0-10)
        # 理想情况下，DEBUG > INFO > WARNING > ERROR > CRITICAL
        level_counts = [
            self.log_count_by_level["DEBUG"],
            self.log_count_by_level["INFO"] + self.log_count_by_level["SUCCESS"],
            self.log_count_by_level["WARNING"],
            self.log_count_by_level["ERROR"],
            self.log_count_by_level["CRITICAL"]
        ]
        
        # 检查非零级别数量
        non_zero_levels = sum(1 for c in level_counts if c > 0)
        
        # 计算级别平衡得分
        if non_zero_levels <= 1:
            level_balance_score = 2.0  # 只有一种级别，得分低
        else:
            # 基础得分
            level_balance_score = min(10.0, non_zero_levels * 2.0)
            
            # 检查DEBUG日志比例是否合理 (10-30%)
            debug_ratio = self.log_count_by_level["DEBUG"] / self.total_log_calls
            if debug_ratio < 0.1 or debug_ratio > 0.5:
                level_balance_score -= 2.0
            
            # 检查错误日志比例是否合理 (5-20%)
            error_ratio = (self.log_count_by_level["ERROR"] + self.log_count_by_level["CRITICAL"]) / self.total_log_calls
            if error_ratio < 0.05 or error_ratio > 0.3:
                level_balance_score -= 2.0
        
        scores["level_balance_score"] = max(0.0, level_balance_score)
        
        # 2. 上下文使用得分 (0-10)
        context_ratio = self.logs_with_context / self.total_log_calls
        context_usage_score = context_ratio * 10.0
        scores["context_usage_score"] = context_usage_score
        
        # 3. 日志格式质量得分 (0-10)
        if self.logs_with_good_format + self.logs_with_poor_format > 0:
            format_ratio = self.logs_with_good_format / (self.logs_with_good_format + self.logs_with_poor_format)
            format_quality_score = format_ratio * 10.0
        else:
            format_quality_score = 5.0  # 默认中等得分
        scores["format_quality_score"] = format_quality_score
        
        # 4. 异常处理得分 (0-10)
        # 假设日志中约5-15%应该包含异常信息
        exception_ratio = self.logs_with_exception / self.total_log_calls
        if 0.05 <= exception_ratio <= 0.15:
            exception_handling_score = 10.0
        else:
            # 如果比例过高或过低，降低得分
            exception_handling_score = 10.0 - min(8.0, abs(0.1 - exception_ratio) * 80)
        scores["exception_handling_score"] = max(2.0, exception_handling_score)
        
        # 5. 覆盖率得分 (0-10)
        if self.total_files_analyzed > 0:
            coverage_ratio = self.files_with_logs / self.total_files_analyzed
            coverage_score = coverage_ratio * 10.0
        else:
            coverage_score = 0.0
        scores["coverage_score"] = coverage_score
        
        # 综合得分 (0-10)
        weights = {
            "level_balance_score": 0.2,
            "context_usage_score": 0.25,
            "format_quality_score": 0.2,
            "exception_handling_score": 0.15,
            "coverage_score": 0.2
        }
        
        overall_score = sum(scores[k] * weights[k] for k in weights)
        scores["overall_score"] = overall_score
        
        return scores
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取评估摘要
        
        Returns:
            评估摘要字典
        """
        scores = self.calculate_scores()
        
        return {
            "total_log_calls": self.total_log_calls,
            "total_files_analyzed": self.total_files_analyzed,
            "files_with_logs": self.files_with_logs,
            "modules_with_logs": len(self.modules_with_logs),
            "log_levels": self.log_count_by_level,
            "logs_with_context": self.logs_with_context,
            "logs_with_exception": self.logs_with_exception,
            "logs_with_structured_data": self.logs_with_structured_data,
            "scores": scores,
            "grade": self._get_grade(scores["overall_score"])
        }
    
    def _get_grade(self, score: float) -> str:
        """
        根据得分获取等级
        
        Args:
            score: 评分（0-10）
            
        Returns:
            等级（A+, A, B+, B, C+, C, D, F）
        """
        if score >= 9.5:
            return "A+"
        elif score >= 9.0:
            return "A"
        elif score >= 8.5:
            return "A-"
        elif score >= 8.0:
            return "B+"
        elif score >= 7.5:
            return "B"
        elif score >= 7.0:
            return "B-"
        elif score >= 6.0:
            return "C+"
        elif score >= 5.0:
            return "C"
        elif score >= 4.0:
            return "C-"
        elif score >= 3.0:
            return "D+"
        elif score >= 2.0:
            return "D"
        else:
            return "F"

class LogQualityAnalyzer:
    """
    日志质量分析器
    
    分析代码库中的日志调用，评估日志质量
    """
    
    def __init__(self, base_path: str):
        """
        初始化分析器
        
        Args:
            base_path: 代码库根目录
        """
        self.base_path = Path(base_path)
        self.metrics = LogQualityMetrics()
        
        # 日志模式
        self.logger_pattern = re.compile(r'logger\.(trace|debug|info|success|warning|error|critical)')
        self.log_func_pattern = re.compile(r'log_(debug|info|warning|error|critical|success|progress|section)')
        
        # 格式评估模式
        self.good_format_patterns = [
            re.compile(r'f".*{.*}.*"'),  # f-string
            re.compile(r'".*".format\('),  # str.format()
            re.compile(r'logger\.\w+\([^,]+,[^,]+\)')  # 带额外参数的日志调用
        ]
        self.poor_format_patterns = [
            re.compile(r'".*" \+'),  # 字符串拼接
            re.compile(r'".*" %')  # %-格式化
        ]
    
    def analyze_directory(self, dir_path: Optional[str] = None) -> LogQualityMetrics:
        """
        分析目录中的Python文件
        
        Args:
            dir_path: 要分析的目录，默认为基础路径
            
        Returns:
            日志质量评估指标
        """
        if dir_path is None:
            dir_path = self.base_path
        else:
            dir_path = Path(dir_path)
        
        logger.info(f"分析目录: {dir_path}")
        
        # 重置指标
        self.metrics = LogQualityMetrics()
        
        # 遍历目录中的Python文件
        python_files = list(dir_path.glob("**/*.py"))
        self.metrics.total_files_analyzed = len(python_files)
        
        for file_path in python_files:
            self._analyze_file(file_path)
        
        return self.metrics
    
    def _analyze_file(self, file_path: Path) -> None:
        """
        分析单个文件中的日志调用
        
        Args:
            file_path: 文件路径
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析AST
            tree = ast.parse(content)
            log_calls = []
            
            # 访问AST节点，查找日志调用
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # 检查是否是logger.xxx()调用
                    if (isinstance(node.func, ast.Attribute) and 
                        isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'logger'):
                        log_calls.append(node)
                    
                    # 检查是否是log_xxx()调用
                    elif (isinstance(node.func, ast.Name) and
                          node.func.id.startswith('log_')):
                        log_calls.append(node)
            
            # 如果文件中有日志调用，更新指标
            if log_calls:
                self.metrics.files_with_logs += 1
                # 获取模块名
                module_name = str(file_path).replace(str(self.base_path), '').replace('\\', '.').replace('/', '.').strip('.')
                if module_name.endswith('.py'):
                    module_name = module_name[:-3]
                self.metrics.modules_with_logs.add(module_name)
            
            # 分析日志调用
            for call in log_calls:
                self._analyze_log_call(call, content)
                
        except Exception as e:
            logger.error(f"分析文件 {file_path} 时出错: {e}")
    
    def _analyze_log_call(self, call_node: ast.Call, file_content: str) -> None:
        """
        分析单个日志调用
        
        Args:
            call_node: 调用节点
            file_content: 文件内容
        """
        # 更新总调用数
        self.metrics.total_log_calls += 1
        
        try:
            # 获取日志级别
            level = self._get_log_level(call_node)
            if level:
                self.metrics.log_count_by_level[level] += 1
            
            # 检查是否包含上下文数据
            if self._has_context_data(call_node):
                self.metrics.logs_with_context += 1
            
            # 检查是否包含异常信息
            if self._has_exception_info(call_node):
                self.metrics.logs_with_exception += 1
            
            # 检查是否包含结构化数据
            if self._has_structured_data(call_node):
                self.metrics.logs_with_structured_data += 1
            
            # 检查日志格式质量
            log_line = self._get_source_line(call_node, file_content)
            if log_line:
                if any(pattern.search(log_line) for pattern in self.good_format_patterns):
                    self.metrics.logs_with_good_format += 1
                elif any(pattern.search(log_line) for pattern in self.poor_format_patterns):
                    self.metrics.logs_with_poor_format += 1
                else:
                    # 默认为良好格式
                    self.metrics.logs_with_good_format += 1
        
        except Exception as e:
            logger.error(f"分析日志调用时出错: {e}")
    
    def _get_log_level(self, call_node: ast.Call) -> Optional[str]:
        """
        获取日志级别
        
        Args:
            call_node: 调用节点
            
        Returns:
            日志级别
        """
        if isinstance(call_node.func, ast.Attribute):
            # logger.xxx()
            level = call_node.func.attr.upper()
            if level in self.metrics.log_count_by_level:
                return level
            
        elif isinstance(call_node.func, ast.Name):
            # log_xxx()
            func_name = call_node.func.id
            if func_name.startswith('log_'):
                level = func_name[4:].upper()
                # 特殊处理自定义级别
                if level == 'PROGRESS':
                    return 'INFO'
                elif level == 'SECTION':
                    return 'INFO'
                elif level in self.metrics.log_count_by_level:
                    return level
        
        return None
    
    def _has_context_data(self, call_node: ast.Call) -> bool:
        """
        检查是否包含上下文数据
        
        Args:
            call_node: 调用节点
            
        Returns:
            是否包含上下文数据
        """
        # 检查是否有关键字参数
        if call_node.keywords:
            for keyword in call_node.keywords:
                if keyword.arg not in ('level', 'exception', 'stacklevel'):
                    return True
        
        # 检查参数数量（第一个是消息，额外参数视为上下文）
        return len(call_node.args) > 1
    
    def _has_exception_info(self, call_node: ast.Call) -> bool:
        """
        检查是否包含异常信息
        
        Args:
            call_node: 调用节点
            
        Returns:
            是否包含异常信息
        """
        # 检查是否使用exception关键字参数
        for keyword in call_node.keywords:
            if keyword.arg == 'exception':
                return True
        
        # 检查是否是exception方法调用
        if isinstance(call_node.func, ast.Attribute) and call_node.func.attr == 'exception':
            return True
        
        return False
    
    def _has_structured_data(self, call_node: ast.Call) -> bool:
        """
        检查是否包含结构化数据
        
        Args:
            call_node: 调用节点
            
        Returns:
            是否包含结构化数据
        """
        # 检查关键字参数是否包含字典
        for keyword in call_node.keywords:
            if isinstance(keyword.value, (ast.Dict, ast.Call)):
                return True
        
        # 检查其他参数是否包含字典
        for arg in call_node.args[1:] if call_node.args else []:
            if isinstance(arg, (ast.Dict, ast.Call)):
                return True
        
        return False
    
    def _get_source_line(self, node: ast.AST, content: str) -> Optional[str]:
        """
        获取节点对应的源代码行
        
        Args:
            node: AST节点
            content: 文件内容
            
        Returns:
            源代码行
        """
        if hasattr(node, 'lineno'):
            lines = content.splitlines()
            if 0 <= node.lineno - 1 < len(lines):
                return lines[node.lineno - 1]
        return None
    
    def generate_report(self) -> str:
        """
        生成质量评估报告
        
        Returns:
            格式化的报告文本
        """
        summary = self.metrics.get_summary()
        scores = summary["scores"]
        
        report = "# 日志质量评估报告\n\n"
        
        # 总体评分
        report += f"## 总体评分: {scores['overall_score']:.1f}/10 (等级: {summary['grade']})\n\n"
        
        # 详细得分
        report += "## 详细得分\n\n"
        report += f"- 日志级别平衡: {scores['level_balance_score']:.1f}/10\n"
        report += f"- 上下文使用: {scores['context_usage_score']:.1f}/10\n"
        report += f"- 日志格式质量: {scores['format_quality_score']:.1f}/10\n"
        report += f"- 异常处理: {scores['exception_handling_score']:.1f}/10\n"
        report += f"- 代码覆盖率: {scores['coverage_score']:.1f}/10\n\n"
        
        # 统计数据
        report += "## 统计数据\n\n"
        report += f"- 总日志调用数: {summary['total_log_calls']}\n"
        report += f"- 分析的文件数: {summary['total_files_analyzed']}\n"
        report += f"- 包含日志的文件数: {summary['files_with_logs']}\n"
        report += f"- 包含日志的模块数: {summary['modules_with_logs']}\n\n"
        
        # 日志级别分布
        report += "## 日志级别分布\n\n"
        for level, count in summary["log_levels"].items():
            if count > 0:
                percentage = (count / summary["total_log_calls"]) * 100 if summary["total_log_calls"] > 0 else 0
                report += f"- {level}: {count} ({percentage:.1f}%)\n"
        
        report += "\n"
        
        # 特性使用情况
        report += "## 特性使用情况\n\n"
        ctx_percent = (summary["logs_with_context"] / summary["total_log_calls"]) * 100 if summary["total_log_calls"] > 0 else 0
        exc_percent = (summary["logs_with_exception"] / summary["total_log_calls"]) * 100 if summary["total_log_calls"] > 0 else 0
        str_percent = (summary["logs_with_structured_data"] / summary["total_log_calls"]) * 100 if summary["total_log_calls"] > 0 else 0
        
        report += f"- 使用上下文数据: {summary['logs_with_context']} ({ctx_percent:.1f}%)\n"
        report += f"- 包含异常信息: {summary['logs_with_exception']} ({exc_percent:.1f}%)\n"
        report += f"- 使用结构化数据: {summary['logs_with_structured_data']} ({str_percent:.1f}%)\n\n"
        
        # 建议
        report += "## 改进建议\n\n"
        
        if scores["level_balance_score"] < 7:
            report += "- 改进日志级别分布，确保各级别日志数量合理\n"
        
        if scores["context_usage_score"] < 7:
            report += "- 增加上下文数据的使用，提高日志可追踪性\n"
        
        if scores["format_quality_score"] < 7:
            report += "- 优化日志格式，避免使用字符串拼接和%-格式\n"
        
        if scores["exception_handling_score"] < 7:
            report += "- 改进异常处理日志，确保错误可追踪\n"
        
        if scores["coverage_score"] < 7:
            report += "- 提高日志覆盖率，确保关键模块和功能有充分日志\n"
        
        return report

# 命令行工具
def main(base_path: str = '.', report_file: Optional[str] = None):
    """
    命令行入口函数
    
    Args:
        base_path: 代码库根目录
        report_file: 报告输出文件
    """
    logger.info(f"开始日志质量评估，基础路径: {base_path}")
    
    analyzer = LogQualityAnalyzer(base_path)
    analyzer.analyze_directory()
    
    report = analyzer.generate_report()
    
    if report_file:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.success(f"评估报告已保存到: {report_file}")
    else:
        print("\n" + report)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="日志质量评估工具")
    parser.add_argument("--path", default=".", help="代码库根目录")
    parser.add_argument("--report", help="报告输出文件")
    
    args = parser.parse_args()
    main(args.path, args.report)