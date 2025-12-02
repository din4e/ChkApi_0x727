#!/bin/bash
# 日志过滤脚本 - 只保留包含 INFO 的行（Shell 版本）

# 使用方法: ./filter_log_info.sh <输入文件> [输出文件]
# 如果不指定输出文件，会覆盖原文件（自动备份）

INPUT_FILE="$1"
OUTPUT_FILE="$2"

if [ -z "$INPUT_FILE" ]; then
    echo "用法: $0 <输入文件> [输出文件]"
    echo "示例: $0 js_capture_log.txt js_capture_log_info_only.txt"
    echo "      $0 js_capture_log.txt  # 直接覆盖原文件（会创建备份）"
    exit 1
fi

if [ ! -f "$INPUT_FILE" ]; then
    echo "错误: 文件不存在: $INPUT_FILE"
    exit 1
fi

# 如果没有指定输出文件，创建备份并覆盖原文件
if [ -z "$OUTPUT_FILE" ]; then
    BACKUP_FILE="${INPUT_FILE}.backup"
    cp "$INPUT_FILE" "$BACKUP_FILE"
    echo "已创建备份: $BACKUP_FILE"
    OUTPUT_FILE="$INPUT_FILE"
fi

# 统计行数
TOTAL_LINES=$(wc -l < "$INPUT_FILE")
INFO_LINES=$(grep -c "\[INFO\]" "$INPUT_FILE" || echo "0")

# 过滤只保留包含 [INFO] 的行
grep "\[INFO\]" "$INPUT_FILE" > "$OUTPUT_FILE"

echo "已过滤日志文件: $INPUT_FILE"
echo "  原始行数: $TOTAL_LINES"
echo "  保留行数: $INFO_LINES"
echo "  已保存到: $OUTPUT_FILE"

