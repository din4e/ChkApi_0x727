#!/bin/bash
# 快速清理 js_capture 相关文件和缓存（静默执行）

rm -rf js_capture_cache/* js_capture_files/* 2>/dev/null
rm -f tools/js_capture_log.txt js_capture_log.txt 2>/dev/null
