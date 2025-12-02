#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志过滤脚本 - 只保留包含 INFO 的行
"""

import sys
import os
from pathlib import Path


def filter_log_info(input_file: str, output_file: str = None, in_place: bool = False):
    """
    过滤日志文件，只保留包含 [INFO] 的行
    
    Args:
        input_file: 输入日志文件路径
        output_file: 输出文件路径（如果为 None 且 in_place=False，则输出到 stdout）
        in_place: 是否直接修改原文件（默认 False）
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_file}")
        return False
    
    # 读取所有行
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 过滤只保留包含 [INFO] 的行
    info_lines = [line for line in lines if '[INFO]' in line]
    
    # 确定输出方式
    if in_place:
        # 直接覆盖原文件
        output_path = input_path
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(info_lines)
        print(f"已过滤日志文件: {input_file}")
        print(f"  原始行数: {len(lines)}")
        print(f"  保留行数: {len(info_lines)}")
        print(f"  已保存到: {input_file}")
    elif output_file:
        # 保存到新文件
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(info_lines)
        print(f"已过滤日志文件: {input_file}")
        print(f"  原始行数: {len(lines)}")
        print(f"  保留行数: {len(info_lines)}")
        print(f"  已保存到: {output_file}")
    else:
        # 输出到标准输出
        sys.stdout.writelines(info_lines)
    
    return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="过滤日志文件，只保留包含 [INFO] 的行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 过滤日志并输出到新文件
  python filter_log_info.py js_capture_log.txt -o js_capture_log_info_only.txt
  
  # 直接修改原文件（覆盖）
  python filter_log_info.py js_capture_log.txt -i
  
  # 输出到标准输出
  python filter_log_info.py js_capture_log.txt
  
  # 过滤多个文件
  python filter_log_info.py *.txt -o filtered/
        """
    )
    parser.add_argument(
        "input_file",
        help="输入日志文件路径"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出文件路径（如果不指定，输出到标准输出）"
    )
    parser.add_argument(
        "-i", "--in-place",
        action="store_true",
        help="直接修改原文件（覆盖）"
    )
    
    args = parser.parse_args()
    
    # 检查参数冲突
    if args.in_place and args.output:
        print("错误: 不能同时使用 -i 和 -o 参数")
        parser.print_help()
        return 1
    
    # 执行过滤
    success = filter_log_info(
        args.input_file,
        output_file=args.output,
        in_place=args.in_place
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

