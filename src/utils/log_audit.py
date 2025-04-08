"""
日志审计工具

用于比较标准logging和Loguru的日志行为差异，帮助验证迁移是否保持了相同的日志行为。
提供日志比较、审计报告和验证工具。
"""

import io
import sys
import time
import os
import logging
import threading
from typing import Dict, List, Any, Tuple, Set, Optional, Callable
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger as loguru_logger

class LogCapture:
    """
    捕获日志输出的工具类
    
    可以同时捕获标准logging库和Loguru的日志输出
    """
    
    def __init__(self):
        """
        初始化日志捕获器
        """
        self.logging_output = io.StringIO()
        self.loguru_output = io.StringIO()
        
        # 标准logging处理器
        self.logging_handler = logging.StreamHandler(self.logging_output)
        self.logging_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        
        # Loguru处理器ID
        self.loguru_handler_id = None
    
    def start_capture(self):
        """
        开始捕获日志
        """
        # 设置标准logging捕获
        root_logger = logging.getLogger()
        root_logger.addHandler(self.logging_handler)
        
        # 设置Loguru捕获
        self.loguru_handler_id = loguru_logger.add(
            self.loguru_output,
            format="{level}: {message}",
            level="DEBUG"
        )
    
    def stop_capture(self):
        """
        停止捕获日志
        """
        # 移除标准logging捕获
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.logging_handler)
        
        # 移除Loguru捕获
        if self.loguru_handler_id is not None:
            loguru_logger.remove(self.loguru_handler_id)
    
    def get_logging_output(self) -> str:
        """获取标准logging输出"""
        return self.logging_output.getvalue()
    
    def get_loguru_output(self) -> str:
        """获取Loguru输出"""
        return self.loguru_output.getvalue()
    
    def reset(self):
        """重置捕获内容"""
        self.logging_output = io.StringIO()
        self.loguru_output = io.StringIO()
        self.logging_handler.setStream(self.logging_output)

@contextmanager
def capture_logs():
    """
    捕获日志的上下文管理器
    
    用法:
        with capture_logs() as capture:
            # 执行产生日志的代码
            logging.info("测试消息")
            
        logging_output = capture.get_logging_output()
        loguru_output = capture.get_loguru_output()
    """
    capture = LogCapture()
    capture.start_capture()
    try:
        yield capture
    finally:
        capture.stop_capture()

class LogAuditor:
    """
    日志审计工具
    
    用于执行代码并比较标准logging和Loguru的输出差异
    """
    
    def __init__(self):
        """
        初始化审计工具
        """
        self.capture = LogCapture()
        self.results = []
    
    def audit_function(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        审计函数日志输出
        
        Args:
            func: 要审计的函数
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
            
        Returns:
            审计结果
        """
        # 重置并开始捕获
        self.capture.reset()
        self.capture.start_capture()
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行函数
        try:
            result = func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
        
        # 记录结束时间
        end_time = time.time()
        
        # 停止捕获
        self.capture.stop_capture()
        
        # 获取日志输出
        logging_output = self.capture.get_logging_output()
        loguru_output = self.capture.get_loguru_output()
        
        # 分析差异
        has_diff, diff_details = self._analyze_diff(logging_output, loguru_output)
        
        # 创建审计结果
        audit_result = {
            "function": func.__name__,
            "args": args,
            "kwargs": kwargs,
            "success": success,
            "error": error,
            "execution_time": end_time - start_time,
            "logging_output": logging_output,
            "loguru_output": loguru_output,
            "has_diff": has_diff,
            "diff_details": diff_details,
            "timestamp": datetime.now()
        }
        
        # 添加到结果列表
        self.results.append(audit_result)
        
        return audit_result
    
    def audit_code_block(self, code_block: str) -> Dict[str, Any]:
        """
        审计代码块日志输出
        
        Args:
            code_block: 要执行的代码块
            
        Returns:
            审计结果
        """
        # 定义一个包装函数执行代码块
        def execute_code():
            exec(code_block)
        
        return self.audit_function(execute_code)
    
    def _analyze_diff(self, logging_output: str, loguru_output: str) -> Tuple[bool, List[str]]:
        """
        分析日志输出差异
        
        Args:
            logging_output: 标准logging输出
            loguru_output: Loguru输出
            
        Returns:
            是否有差异和差异详情
        """
        # 分割成行并标准化
        logging_lines = [line.strip() for line in logging_output.splitlines() if line.strip()]
        loguru_lines = [line.strip() for line in loguru_output.splitlines() if line.strip()]
        
        # 判断行数是否相同
        if len(logging_lines) != len(loguru_lines):
            return True, [
                f"行数不同: logging={len(logging_lines)}, loguru={len(loguru_lines)}"
            ]
        
        # 比较每一行
        diff_details = []
        for i, (log_line, loguru_line) in enumerate(zip(logging_lines, loguru_lines)):
            if log_line != loguru_line:
                diff_details.append(f"第{i+1}行不同:\n  logging: {log_line}\n  loguru: {loguru_line}")
        
        return bool(diff_details), diff_details
    
    def generate_report(self) -> str:
        """
        生成审计报告
        
        Returns:
            格式化的报告文本
        """
        if not self.results:
            return "无审计结果"
        
        report = "# 日志审计报告\n\n"
        report += f"生成时间: {datetime.now()}\n"
        report += f"审计项目数: {len(self.results)}\n\n"
        
        # 统计信息
        total_diffs = sum(1 for r in self.results if r["has_diff"])
        report += f"差异总数: {total_diffs}/{len(self.results)}\n\n"
        
        # 详细结果
        report += "## 详细结果\n\n"
        
        for i, result in enumerate(self.results, 1):
            report += f"### 项目 {i}: {result['function']}\n\n"
            report += f"- 执行状态: {'成功' if result['success'] else '失败'}\n"
            if result['error']:
                report += f"- 错误信息: {result['error']}\n"
            report += f"- 执行时间: {result['execution_time']:.4f}秒\n"
            report += f"- 是否有差异: {'是' if result['has_diff'] else '否'}\n\n"
            
            if result['has_diff']:
                report += "差异详情:\n```\n"
                for diff in result['diff_details']:
                    report += f"{diff}\n"
                report += "```\n\n"
            
            report += "标准logging输出:\n```\n"
            report += result['logging_output'] or "(无输出)"
            report += "\n```\n\n"
            
            report += "Loguru输出:\n```\n"
            report += result['loguru_output'] or "(无输出)"
            report += "\n```\n\n"
        
        return report

class LogVerifier:
    """
    日志验证工具
    
    用于验证迁移前后日志行为的一致性
    """
    
    def __init__(self, original_module, migrated_module):
        """
        初始化验证工具
        
        Args:
            original_module: 原始模块（使用标准logging）
            migrated_module: 迁移后的模块（使用Loguru）
        """
        self.original_module = original_module
        self.migrated_module = migrated_module
        self.results = []
    
    def verify_function(self, func_name: str, *args, **kwargs) -> Dict[str, Any]:
        """
        验证函数日志行为一致性
        
        Args:
            func_name: 函数名称
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
            
        Returns:
            验证结果
        """
        # 获取原始和迁移后的函数
        original_func = getattr(self.original_module, func_name)
        migrated_func = getattr(self.migrated_module, func_name)
        
        # 创建审计工具
        auditor = LogAuditor()
        
        # 审计原始函数
        original_result = auditor.audit_function(original_func, *args, **kwargs)
        
        # 审计迁移后函数
        migrated_result = auditor.audit_function(migrated_func, *args, **kwargs)
        
        # 比较结果
        is_consistent = (
            original_result['success'] == migrated_result['success'] and
            not self._compare_outputs(
                original_result['logging_output'],
                migrated_result['loguru_output']
            )[0]
        )
        
        # 创建验证结果
        verify_result = {
            "function": func_name,
            "args": args,
            "kwargs": kwargs,
            "is_consistent": is_consistent,
            "original_result": original_result,
            "migrated_result": migrated_result,
            "diff_details": self._compare_outputs(
                original_result['logging_output'],
                migrated_result['loguru_output']
            )[1],
            "timestamp": datetime.now()
        }
        
        # 添加到结果列表
        self.results.append(verify_result)
        
        return verify_result
    
    def _compare_outputs(self, original_output: str, migrated_output: str) -> Tuple[bool, List[str]]:
        """
        比较日志输出
        
        Args:
            original_output: 原始输出
            migrated_output: 迁移后输出
            
        Returns:
            是否有差异和差异详情
        """
        # 标准化输出
        original_lines = [
            self._normalize_line(line) for line in original_output.splitlines() if line.strip()
        ]
        migrated_lines = [
            self._normalize_line(line) for line in migrated_output.splitlines() if line.strip()
        ]
        
        # 判断行数是否相同
        if len(original_lines) != len(migrated_lines):
            return True, [
                f"行数不同: 原始={len(original_lines)}, 迁移后={len(migrated_lines)}"
            ]
        
        # 比较每一行
        diff_details = []
        for i, (orig_line, migr_line) in enumerate(zip(original_lines, migrated_lines)):
            if not self._lines_match(orig_line, migr_line):
                diff_details.append(f"第{i+1}行不同:\n  原始: {orig_line}\n  迁移后: {migr_line}")
        
        return bool(diff_details), diff_details
    
    def _normalize_line(self, line: str) -> str:
        """
        标准化日志行
        
        移除时间戳、简化级别名称等
        
        Args:
            line: 原始日志行
            
        Returns:
            标准化后的日志行
        """
        # 移除时间戳
        line = line.strip()
        
        # 标准化级别名称
        line = line.replace("WARNING", "WARN")
        
        return line
    
    def _lines_match(self, line1: str, line2: str) -> bool:
        """
        判断两行是否匹配
        
        忽略一些非关键差异，如时间戳格式等
        
        Args:
            line1: 第一行
            line2: 第二行
            
        Returns:
            是否匹配
        """
        # 提取关键部分（消息内容）
        msg1 = line1.split(":", 1)[-1].strip() if ":" in line1 else line1
        msg2 = line2.split(":", 1)[-1].strip() if ":" in line2 else line2
        
        return msg1 == msg2
    
    def generate_report(self) -> str:
        """
        生成验证报告
        
        Returns:
            格式化的报告文本
        """
        if not self.results:
            return "无验证结果"
        
        report = "# 日志迁移验证报告\n\n"
        report += f"生成时间: {datetime.now()}\n"
        report += f"验证项目数: {len(self.results)}\n\n"
        
        # 统计信息
        consistent_count = sum(1 for r in self.results if r["is_consistent"])
        inconsistent_count = len(self.results) - consistent_count
        
        report += f"一致项目数: {consistent_count}/{len(self.results)}\n"
        report += f"不一致项目数: {inconsistent_count}/{len(self.results)}\n\n"
        
        # 详细结果
        report += "## 详细结果\n\n"
        
        for i, result in enumerate(self.results, 1):
            report += f"### 项目 {i}: {result['function']}\n\n"
            report += f"- 一致性: {'一致' if result['is_consistent'] else '不一致'}\n"
            
            if not result['is_consistent']:
                report += "\n**差异详情:**\n```\n"
                for diff in result['diff_details']:
                    report += f"{diff}\n"
                report += "```\n\n"
                
                report += "原始输出:\n```\n"
                report += result['original_result']['logging_output'] or "(无输出)"
                report += "\n```\n\n"
                
                report += "迁移后输出:\n```\n"
                report += result['migrated_result']['loguru_output'] or "(无输出)"
                report += "\n```\n\n"
        
        return report

def run_verification_tests(test_cases: List[Dict[str, Any]]) -> str:
    """
    运行一组验证测试
    
    Args:
        test_cases: 测试用例列表，每个测试用例是一个字典，包含:
                    {
                        'module_name': 模块名称,
                        'function_name': 函数名称,
                        'args': 位置参数列表,
                        'kwargs': 关键字参数字典
                    }
                    
    Returns:
        验证报告
    """
    results = []
    
    with capture_logs() as capture:
        for test_case in test_cases:
            module_name = test_case['module_name']
            function_name = test_case['function_name']
            args = test_case.get('args', [])
            kwargs = test_case.get('kwargs', {})
            
            # 导入原始模块（使用标准logging）
            try:
                original_module = __import__(module_name)
                original_func = getattr(original_module, function_name)
            except (ImportError, AttributeError) as e:
                results.append({
                    'test_case': test_case,
                    'status': 'error',
                    'error': f"无法加载原始模块或函数: {e}"
                })
                continue
            
            # 设置使用Loguru的标志
            os.environ['USE_LOGURU'] = '1'
            
            # 重新导入模块（使用Loguru）
            try:
                # 确保重新加载
                if module_name in sys.modules:
                    del sys.modules[module_name]
                migrated_module = __import__(module_name)
                migrated_func = getattr(migrated_module, function_name)
            except (ImportError, AttributeError) as e:
                results.append({
                    'test_case': test_case,
                    'status': 'error',
                    'error': f"无法加载迁移后的模块或函数: {e}"
                })
                os.environ.pop('USE_LOGURU', None)
                continue
            
            # 创建验证器
            verifier = LogVerifier(original_module, migrated_module)
            
            # 执行验证
            try:
                result = verifier.verify_function(function_name, *args, **kwargs)
                results.append({
                    'test_case': test_case,
                    'status': 'success',
                    'result': result
                })
            except Exception as e:
                results.append({
                    'test_case': test_case,
                    'status': 'error',
                    'error': f"验证过程出错: {e}"
                })
            
            # 恢复环境
            os.environ.pop('USE_LOGURU', None)
    
    # 生成报告
    report = "# 日志迁移自动验证报告\n\n"
    report += f"生成时间: {datetime.now()}\n"
    report += f"测试用例数: {len(test_cases)}\n"
    report += f"成功执行: {sum(1 for r in results if r['status'] == 'success')}\n"
    report += f"执行出错: {sum(1 for r in results if r['status'] == 'error')}\n\n"
    
    # 详细结果
    report += "## 详细结果\n\n"
    
    for i, result in enumerate(results, 1):
        test_case = result['test_case']
        report += f"### 测试 {i}: {test_case['module_name']}.{test_case['function_name']}\n\n"
        
        if result['status'] == 'error':
            report += f"状态: 错误\n"
            report += f"错误信息: {result['error']}\n\n"
        else:
            verify_result = result['result']
            report += f"状态: {'一致' if verify_result['is_consistent'] else '不一致'}\n\n"
            
            if not verify_result['is_consistent']:
                report += "差异详情:\n```\n"
                for diff in verify_result['diff_details']:
                    report += f"{diff}\n"
                report += "```\n\n"
    
    return report

# 用于快速测试的辅助函数
def test_logging_compat():
    """
    测试日志兼容层
    
    测试标准logging和Loguru的行为一致性
    """
    # 使用LogCapture捕获输出
    with capture_logs() as capture:
        # 标准logging测试
        logging.debug("这是一条调试信息")
        logging.info("这是一条信息")
        logging.warning("这是一条警告")
        logging.error("这是一条错误")
        logging.critical("这是一条严重错误")
        
        # 使用自定义级别
        logging.log(logging.INFO + 1, "这是一条成功信息")
        
        # 使用异常信息
        try:
            raise ValueError("测试异常")
        except Exception:
            logging.exception("捕获到异常")
    
    # 输出捕获结果
    print("标准logging输出:")
    print(capture.get_logging_output())
    print("\nLoguru输出:")
    print(capture.get_loguru_output())

if __name__ == "__main__":
    # 简单的命令行接口
    import argparse
    
    parser = argparse.ArgumentParser(description="日志审计工具")
    parser.add_argument("--test", action="store_true", help="运行兼容性测试")
    
    args = parser.parse_args()
    
    if args.test:
        test_logging_compat()
    else:
        print("请使用 --test 参数运行测试") 