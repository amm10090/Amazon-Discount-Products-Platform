#!/usr/bin/env python3
"""
验证码断点控制工具

此脚本用于控制优惠券信息抓取过程中的验证码断点。
提供设置断点和清除断点的功能，可让用户在遇到验证码时手动干预。

用法示例:
    # 设置断点（会创建断点标志文件）
    python captcha_control.py --set
    
    # 清除断点（会删除断点标志文件，使暂停的任务继续执行）
    python captcha_control.py --clear
    
    # 检查断点状态
    python captcha_control.py --status
    
    # 查看当前处于断点状态的任务信息
    python captcha_control.py --info
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import time

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入断点控制函数
from src.core.discount_scraper_mt import create_manual_break_flag, remove_manual_break_flag, check_manual_break_flag

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='验证码断点控制工具')
    
    # 创建互斥参数组，确保--set, --clear, --status不会同时使用
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--set', action='store_true', help='设置断点，使任务在遇到验证码时暂停')
    group.add_argument('--clear', action='store_true', help='清除断点，使暂停的任务继续执行')
    group.add_argument('--status', action='store_true', help='检查断点状态')
    group.add_argument('--info', action='store_true', help='显示当前断点状态的任务信息')
    
    return parser.parse_args()

def get_captcha_instructions():
    """获取当前所有验证码处理指南文件"""
    instruction_files = list(Path(project_root).glob("logs/captcha_instructions_worker*.txt"))
    return sorted(instruction_files)

def main():
    """主函数"""
    args = parse_args()
    
    if args.set:
        # 设置断点
        flag_path = create_manual_break_flag()
        print(f"断点已设置: {flag_path}")
        print("当抓取任务遇到验证码时，将暂停执行等待用户操作")
        return 0
    
    elif args.clear:
        # 清除断点
        if remove_manual_break_flag():
            print("断点已清除，暂停的任务将继续执行")
            return 0
        else:
            print("没有发现断点标志")
            return 1
    
    elif args.status:
        # 检查断点状态
        if check_manual_break_flag():
            flag_file = Path(project_root) / "logs" / "manual_break.flag"
            
            # 读取文件内容获取创建时间
            try:
                with open(flag_file, "r") as f:
                    content = f.read()
                print("断点状态: 已设置")
                print(content)
                
                # 检查是否有任务正在等待处理
                instruction_files = get_captcha_instructions()
                if instruction_files:
                    print(f"当前有 {len(instruction_files)} 个工作线程处于等待状态")
                    for file in instruction_files:
                        print(f"- {file.name}")
                else:
                    print("没有工作线程处于等待状态")
            except:
                print("断点状态: 已设置（无法读取详细信息）")
            
            return 0
        else:
            print("断点状态: 未设置")
            return 0
    
    elif args.info:
        # 显示处于断点状态的任务信息
        instruction_files = get_captcha_instructions()
        
        if not instruction_files:
            print("没有找到正在等待处理的验证码任务")
            return 0
        
        print(f"找到 {len(instruction_files)} 个需要处理的验证码任务:")
        
        for file in instruction_files:
            print(f"\n{'='*50}")
            print(f"任务信息文件: {file.name}")
            try:
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()
                    print(content)
            except Exception as e:
                print(f"无法读取文件内容: {e}")
            print(f"{'='*50}")
        
        # 检查断点标志状态
        if check_manual_break_flag():
            print("\n断点已设置 - 任务处于暂停状态")
            print("要恢复任务执行，请使用: python captcha_control.py --clear")
        else:
            print("\n断点未设置 - 但仍有任务指南文件，可能是上次执行中断")
            print("建议清理指南文件或重新运行任务")
        
        return 0

if __name__ == "__main__":
    sys.exit(main()) 