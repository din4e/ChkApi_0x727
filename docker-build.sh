#!/bin/bash
# Docker 镜像构建脚本

set -e

echo "=========================================="
echo "构建 ChkApi Docker 镜像 (Python 3.9)"
echo "=========================================="

# 构建镜像
docker build -t chkapi:latest .

echo ""
echo "=========================================="
echo "构建完成！"
echo "=========================================="
echo ""
echo "使用方法："
echo "  1. 运行 ChkApi:"
echo "     docker run --rm chkapi:latest python3 ChkApi.py -u \"http://example.com\""
echo ""
echo "  2. 运行 JS Capture (单线程):"
echo "     docker run --rm -v \$(pwd)/js_capture_files:/app/js_capture_files chkapi:latest python3 tools/jsCapture.py"
echo ""
echo "  3. 运行 JS Capture (并发):"
echo "     docker run --rm -v \$(pwd)/js_capture_files:/app/js_capture_files chkapi:latest python3 tools/jsCapture.py --concurrent --max-concurrent 3"
echo ""
echo "  4. 查看帮助:"
echo "     docker run --rm chkapi:latest python3 ChkApi.py --help"
echo "     docker run --rm chkapi:latest python3 tools/jsCapture.py --help"
echo ""

