# JS 文件捕获工具

用于批量访问 URL，捕获并下载 JS 文件，检测 IP 地址的独立工具。

## 功能特性

- ✅ 批量处理多个 URL
- ✅ 自动捕获页面中的 JS 文件
- ✅ 检测 JS 文件中的 IP 地址（内网/公网）
- ✅ 自动下载 Source Map 文件
- ✅ 缓存机制，避免重复下载
- ✅ 支持 Webpack 文件识别
- ✅ 详细的日志记录

## 安装依赖

```bash
pip install playwright
playwright install chromium
```

## 使用方法

1. 在项目根目录创建 `js_capture_urls.txt` 文件，添加要处理的 URL（每行一个）
2. 运行程序：
   ```bash
   python tools/jsCapture.py
   ```
3. 结果会保存在 `js_capture_files/` 目录下，每个 URL 对应一个子目录

## 打包为可执行文件

### Windows
```bash
tools\build_js_capture.bat
```

### Linux/Mac
```bash
chmod +x tools/build_js_capture.sh
./tools/build_js_capture.sh
```

打包前需要安装 PyInstaller：
```bash
pip install pyinstaller
```

打包后的可执行文件位于 `dist/` 目录。

## 输出格式

每个 URL 的处理结果会保存在对应的目录中：
- `captured_files.json`: 文件列表和元数据
- `*.js`: 捕获的 JS 文件
- `*.map`: Source Map 文件（如果存在）
- `file_*.txt`: 页面 HTML 内容

## 日志

所有操作日志会记录在 `js_capture_log.txt` 文件中。

## 注意事项

- 此工具与 ChkApi 主功能完全独立，互不干扰
- 使用独立的日志文件（js_capture_log.txt）和输出目录（js_capture_files/）
- URL 列表文件名为 `js_capture_urls.txt`，与 ChkApi 的 URL 文件不冲突

