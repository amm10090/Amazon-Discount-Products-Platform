"""
日志迁移策略模块

提供从标准logging库到Loguru的迁移工具和策略。
包括代码扫描、迁移计划生成和迁移执行功能。
"""

import os
import re
import ast
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass

from loguru import logger

@dataclass
class LogUsage:
    """记录日志调用的位置和方式"""
    file_path: str
    line_number: int
    method_name: str
    import_type: str  # 'logging', 'logger_manager', 'mixed'
    log_call: str

@dataclass
class MigrationPlan:
    """日志迁移计划"""
    file_path: str
    priority: int  # 1-5, 1最高
    complexity: int  # 1-5, 5最复杂
    usages: List[LogUsage]
    status: str = "pending"  # pending, in_progress, completed, failed

class LogMigrationScanner:
    """
    扫描代码库中的日志用法
    
    识别标准logging库和旧版LoggerManager使用情况
    """
    
    def __init__(self, base_path: str):
        """
        初始化扫描器
        
        Args:
            base_path: 代码库根目录
        """
        self.base_path = Path(base_path)
        self.log_usages: List[LogUsage] = []
        
        # 日志导入模式
        self.logging_import_pattern = re.compile(r'import\s+logging|from\s+logging')
        self.logger_manager_pattern = re.compile(
            r'from\s+src\.utils\.logger_manager\s+import|'
            r'import\s+src\.utils\.logger_manager|'
            r'from\s+utils\.logger_manager\s+import|'
            r'import\s+utils\.logger_manager'
        )
        
        # 日志调用模式
        self.logging_call_pattern = re.compile(
            r'logging\.(debug|info|warning|error|critical|exception)'
        )
        self.logger_call_pattern = re.compile(
            r'logger\.(debug|info|warning|error|critical|success|progress|section)'
        )
        self.log_func_pattern = re.compile(
            r'log_(debug|info|warning|error|critical|success|progress|section)'
        )
    
    def scan_directory(self, dir_path: Optional[str] = None) -> List[LogUsage]:
        """
        扫描目录中的Python文件
        
        Args:
            dir_path: 要扫描的目录，默认为基础路径
            
        Returns:
            日志用法列表
        """
        if dir_path is None:
            dir_path = self.base_path
        else:
            dir_path = Path(dir_path)
        
        logger.info(f"扫描目录: {dir_path}")
        
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    self._scan_file(file_path)
        
        return self.log_usages
    
    def _scan_file(self, file_path: Path) -> None:
        """
        扫描单个文件中的日志用法
        
        Args:
            file_path: 文件路径
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查导入
            has_logging = bool(self.logging_import_pattern.search(content))
            has_logger_manager = bool(self.logger_manager_pattern.search(content))
            
            if not (has_logging or has_logger_manager):
                return  # 文件不使用日志
            
            import_type = "logging" if has_logging and not has_logger_manager else \
                         "logger_manager" if has_logger_manager and not has_logging else \
                         "mixed"
            
            # 查找日志调用
            for i, line in enumerate(content.splitlines(), 1):
                self._check_log_call(str(file_path), i, line, import_type)
        
        except Exception as e:
            logger.error(f"扫描文件 {file_path} 时出错: {e}")
    
    def _check_log_call(self, file_path: str, line_number: int, line: str, import_type: str) -> None:
        """
        检查行中的日志调用
        
        Args:
            file_path: 文件路径
            line_number: 行号
            line: 行内容
            import_type: 导入类型
        """
        # 检查标准logging调用
        logging_matches = self.logging_call_pattern.findall(line)
        for method in logging_matches:
            self.log_usages.append(LogUsage(
                file_path=file_path,
                line_number=line_number,
                method_name=method,
                import_type=import_type,
                log_call=line.strip()
            ))
        
        # 检查logger调用
        logger_matches = self.logger_call_pattern.findall(line)
        for method in logger_matches:
            self.log_usages.append(LogUsage(
                file_path=file_path,
                line_number=line_number,
                method_name=method,
                import_type=import_type,
                log_call=line.strip()
            ))
        
        # 检查log_xxx函数调用
        log_func_matches = self.log_func_pattern.findall(line)
        for method in log_func_matches:
            self.log_usages.append(LogUsage(
                file_path=file_path,
                line_number=line_number,
                method_name=method,
                import_type=import_type,
                log_call=line.strip()
            ))

class LogMigrationPlanner:
    """
    创建日志迁移计划
    
    基于扫描结果生成迁移计划，按优先级和复杂度排序
    """
    
    def __init__(self, log_usages: List[LogUsage]):
        """
        初始化计划器
        
        Args:
            log_usages: 日志用法列表
        """
        self.log_usages = log_usages
        self.migration_plans: List[MigrationPlan] = []
    
    def create_plan(self) -> List[MigrationPlan]:
        """
        创建迁移计划
        
        Returns:
            迁移计划列表
        """
        # 按文件分组
        file_usages: Dict[str, List[LogUsage]] = {}
        for usage in self.log_usages:
            if usage.file_path not in file_usages:
                file_usages[usage.file_path] = []
            file_usages[usage.file_path].append(usage)
        
        # 为每个文件创建计划
        for file_path, usages in file_usages.items():
            # 计算复杂度（基于日志调用数量和类型混合程度）
            complexity = min(5, 1 + len(usages) // 10)
            
            # 有混合导入的更复杂
            if any(u.import_type == "mixed" for u in usages):
                complexity = min(5, complexity + 1)
            
            # 计算优先级（优先处理核心模块和低复杂度）
            priority = 3  # 默认中等优先级
            
            # 核心模块优先级更高
            if "core" in file_path:
                priority -= 1
            if "utils" in file_path:
                priority -= 1
            if "run.py" in file_path or "main.py" in file_path:
                priority = 1  # 最高优先级
            
            # 非常复杂的文件优先级降低
            if complexity >= 4:
                priority = min(5, priority + 1)
            
            self.migration_plans.append(MigrationPlan(
                file_path=file_path,
                priority=priority,
                complexity=complexity,
                usages=usages
            ))
        
        # 按优先级排序
        self.migration_plans.sort(key=lambda p: (p.priority, p.complexity))
        
        return self.migration_plans
    
    def generate_report(self) -> str:
        """
        生成迁移计划报告
        
        Returns:
            格式化的报告文本
        """
        if not self.migration_plans:
            self.create_plan()
        
        report = "# 日志迁移计划报告\n\n"
        
        # 总体统计
        total_files = len(self.migration_plans)
        total_usages = sum(len(plan.usages) for plan in self.migration_plans)
        complexity_distribution = {i: 0 for i in range(1, 6)}
        priority_distribution = {i: 0 for i in range(1, 6)}
        
        for plan in self.migration_plans:
            complexity_distribution[plan.complexity] += 1
            priority_distribution[plan.priority] += 1
        
        report += f"## 总体统计\n\n"
        report += f"- 需要迁移的文件总数: {total_files}\n"
        report += f"- 日志调用总数: {total_usages}\n"
        report += f"- 复杂度分布: {complexity_distribution}\n"
        report += f"- 优先级分布: {priority_distribution}\n\n"
        
        # 优先级分组
        report += "## 迁移计划（按优先级）\n\n"
        
        for priority in range(1, 6):
            plans = [p for p in self.migration_plans if p.priority == priority]
            if not plans:
                continue
                
            report += f"### 优先级 {priority}\n\n"
            report += "| 文件 | 复杂度 | 日志调用数 |\n"
            report += "|------|--------|------------|\n"
            
            for plan in plans:
                report += f"| {plan.file_path} | {plan.complexity} | {len(plan.usages)} |\n"
            
            report += "\n"
        
        return report

class LogMigrationExecutor:
    """
    执行日志迁移操作
    
    基于迁移计划执行实际的代码修改
    """
    
    def __init__(self, plan: MigrationPlan):
        """
        初始化执行器
        
        Args:
            plan: 迁移计划
        """
        self.plan = plan
        self.backup_path = None
    
    def execute(self, create_backup: bool = True) -> bool:
        """
        执行迁移
        
        Args:
            create_backup: 是否创建备份
            
        Returns:
            是否成功
        """
        file_path = self.plan.file_path
        logger.info(f"开始迁移文件: {file_path}")
        
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 创建备份
            if create_backup:
                backup_path = f"{file_path}.bak"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.backup_path = backup_path
                logger.info(f"创建备份: {backup_path}")
            
            # 执行迁移
            modified_content = self._migrate_content(content)
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            logger.success(f"成功迁移文件: {file_path}")
            self.plan.status = "completed"
            return True
            
        except Exception as e:
            logger.error(f"迁移文件 {file_path} 失败: {e}")
            self.plan.status = "failed"
            return False
    
    def _migrate_content(self, content: str) -> str:
        """
        迁移文件内容
        
        Args:
            content: 原始文件内容
            
        Returns:
            迁移后的内容
        """
        # 修改导入语句
        content = self._migrate_imports(content)
        
        # 修改日志调用
        content = self._migrate_log_calls(content)
        
        return content
    
    def _migrate_imports(self, content: str) -> str:
        """
        迁移导入语句
        
        Args:
            content: 原始文件内容
            
        Returns:
            修改后的内容
        """
        # 检查导入类型
        has_logging = bool(re.search(r'import\s+logging|from\s+logging', content))
        has_logger_manager = bool(re.search(
            r'from\s+src\.utils\.logger_manager\s+import|'
            r'import\s+src\.utils\.logger_manager|'
            r'from\s+utils\.logger_manager\s+import|'
            r'import\s+utils\.logger_manager',
            content
        ))
        
        # 替换导入语句
        if has_logging and has_logger_manager:
            # 混合导入情况
            content = re.sub(
                r'import\s+logging.*?\n',
                '# 迁移到Loguru\nfrom src.utils.logging_compat import getLogger, log_debug, log_info, log_warning, log_error, log_critical, log_success, log_progress, log_section\n',
                content
            )
            content = re.sub(
                r'from\s+logging.*?\n',
                '',
                content
            )
            # 移除logger_manager导入
            content = re.sub(
                r'from\s+(?:src\.)?utils\.logger_manager\s+import.*?\n',
                '',
                content
            )
            content = re.sub(
                r'import\s+(?:src\.)?utils\.logger_manager.*?\n',
                '',
                content
            )
            
        elif has_logging:
            content = re.sub(
                r'import\s+logging.*?\n',
                '# 迁移到Loguru\nfrom src.utils.logging_compat import getLogger\n',
                content
            )
            content = re.sub(
                r'from\s+logging.*?\n',
                '',
                content
            )
            
        elif has_logger_manager:
            # 替换logger_manager导入
            content = re.sub(
                r'from\s+(?:src\.)?utils\.logger_manager\s+import.*?\n',
                '# 迁移到Loguru\nfrom src.utils.logging_compat import log_debug, log_info, log_warning, log_error, log_critical, log_success, log_progress, log_section\n',
                content
            )
            content = re.sub(
                r'import\s+(?:src\.)?utils\.logger_manager.*?\n',
                '# 迁移到Loguru\nfrom src.utils.logging_compat import log_debug, log_info, log_warning, log_error, log_critical, log_success, log_progress, log_section\n',
                content
            )
        
        return content
    
    def _migrate_log_calls(self, content: str) -> str:
        """
        迁移日志调用
        
        Args:
            content: 原始文件内容
            
        Returns:
            修改后的内容
        """
        # 对文件进行行处理
        lines = content.splitlines()
        for i, line in enumerate(lines):
            # 检查当前行是否有日志调用
            for usage in self.plan.usages:
                if usage.line_number - 1 == i:  # 行号从1开始，索引从0开始
                    lines[i] = self._migrate_log_line(line, usage)
        
        return '\n'.join(lines)
    
    def _migrate_log_line(self, line: str, usage: LogUsage) -> str:
        """
        迁移单行日志调用
        
        Args:
            line: 原始行内容
            usage: 日志用法信息
            
        Returns:
            修改后的行
        """
        # 标准logging调用替换
        if 'logging.' in line:
            # 替换logging.debug等调用
            line = re.sub(
                r'logging\.(debug|info|warning|error|critical|exception)',
                r'getLogger().__name__.\1',
                line
            )
            
            # 替换自定义级别
            line = re.sub(
                r'logging\.(log)\s*\(\s*logging\.INFO\s*\+\s*1\s*,',
                r'getLogger().__name__.success(',
                line
            )
            line = re.sub(
                r'logging\.(log)\s*\(\s*logging\.INFO\s*\+\s*2\s*,',
                r'getLogger().__name__.info("→',
                line
            )
            line = re.sub(
                r'logging\.(log)\s*\(\s*logging\.INFO\s*\+\s*3\s*,',
                r'getLogger().__name__.info("\n=============\n',
                line
            )
            
        # 替换logger实例调用
        elif 'logger.' in line:
            # 无需修改，兼容层会处理
            pass
        
        # log_xxx函数调用和其他未处理的情况
        # 无需修改，兼容层会处理
        
        return line

def scan_and_plan(base_path: str) -> Tuple[List[LogUsage], List[MigrationPlan], str]:
    """
    扫描代码库并创建迁移计划
    
    Args:
        base_path: 代码库根目录
        
    Returns:
        日志用法列表、迁移计划列表和报告文本
    """
    scanner = LogMigrationScanner(base_path)
    log_usages = scanner.scan_directory()
    
    planner = LogMigrationPlanner(log_usages)
    migration_plans = planner.create_plan()
    report = planner.generate_report()
    
    return log_usages, migration_plans, report

def execute_batch_migration(
    migration_plans: List[MigrationPlan],
    batch_size: int = 5,
    create_backup: bool = True
) -> Dict[str, int]:
    """
    批量执行迁移计划
    
    Args:
        migration_plans: 迁移计划列表
        batch_size: 每批处理的文件数
        create_backup: 是否创建备份
        
    Returns:
        包含成功、失败和跳过计数的字典
    """
    total = len(migration_plans)
    success = 0
    failure = 0
    skipped = 0
    
    logger.info(f"开始批量迁移，共 {total} 个文件，每批 {batch_size} 个")
    
    for i in range(0, total, batch_size):
        batch = migration_plans[i:i+batch_size]
        logger.info(f"处理批次 {i//batch_size + 1}/{(total+batch_size-1)//batch_size}")
        
        for plan in batch:
            if plan.status != "pending":
                logger.info(f"跳过文件 {plan.file_path}，状态: {plan.status}")
                skipped += 1
                continue
                
            executor = LogMigrationExecutor(plan)
            result = executor.execute(create_backup)
            
            if result:
                success += 1
            else:
                failure += 1
    
    logger.success(f"批量迁移完成: 成功={success}, 失败={failure}, 跳过={skipped}")
    return {
        "total": total,
        "success": success,
        "failure": failure,
        "skipped": skipped
    }

# 方便命令行使用的主函数
def main(base_path: str = '.', batch_size: int = 5, execute: bool = False, report_file: str = None):
    """
    命令行入口函数
    
    Args:
        base_path: 代码库根目录
        batch_size: 每批处理的文件数
        execute: 是否执行迁移
        report_file: 报告输出文件
    """
    logger.info(f"开始日志迁移工具，基础路径: {base_path}")
    
    # 扫描并创建计划
    log_usages, migration_plans, report = scan_and_plan(base_path)
    
    logger.info(f"扫描完成，发现 {len(log_usages)} 个日志调用，涉及 {len(migration_plans)} 个文件")
    
    # 保存报告
    if report_file:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"报告已保存到: {report_file}")
    else:
        logger.info("\n" + report)
    
    # 执行迁移
    if execute:
        execute_batch_migration(migration_plans, batch_size)
    else:
        logger.info("未指定执行迁移，仅生成报告")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="日志迁移工具")
    parser.add_argument("--path", default=".", help="代码库根目录")
    parser.add_argument("--batch-size", type=int, default=5, help="每批处理的文件数")
    parser.add_argument("--execute", action="store_true", help="执行迁移")
    parser.add_argument("--report", help="报告输出文件")
    
    args = parser.parse_args()
    main(args.path, args.batch_size, args.execute, args.report) 