@echo off
chcp 65001 >nul
echo 开始打包 JS 捕获工具...

REM 清理旧的构建文件
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 使用 PyInstaller 打包
echo 正在使用 PyInstaller 打包...
pyinstaller --name=js_capture_tool ^
    --onefile ^
    --console ^
    --clean ^
    --noconfirm ^
    --add-data "js_capture_urls.txt;." ^
    tools\jsCapture.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo 打包成功！
    echo 可执行文件位置: dist\js_capture_tool.exe
    echo ========================================
) else (
    echo.
    echo ========================================
    echo 打包失败！
    echo ========================================
    pause
    exit /b 1
)

pause

