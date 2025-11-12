#!/bin/bash
# JS 捕获工具打包脚本

echo "开始打包 JS 捕获工具..."

# 清理旧的构建文件
rm -rf build dist

# 使用 PyInstaller 打包
echo "正在使用 PyInstaller 打包..."
pyinstaller --name=js_capture_tool \
    --onefile \
    --console \
    --clean \
    --noconfirm \
    --add-data "js_capture_urls.txt:." \
    tools/jsCapture.py

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "打包成功！"
    echo "可执行文件位置: dist/js_capture_tool"
    echo "========================================"
else
    echo ""
    echo "========================================"
    echo "打包失败！"
    echo "========================================"
    exit 1
fi

