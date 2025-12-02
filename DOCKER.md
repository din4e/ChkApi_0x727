# Docker 容器化部署指南

本项目提供了基于 Python 3.9 的 Docker 镜像，方便在不同环境中部署和运行。

## 快速开始

### 方式一：使用 Docker 命令

#### 1. 构建镜像

```bash
docker build -t chkapi:latest .
```

#### 2. 运行容器

**运行 ChkApi 主工具：**
```bash
docker run --rm -v $(pwd)/js_capture_files:/app/js_capture_files chkapi:latest python3 ChkApi.py -u "http://example.com"
```

**运行 JS Capture 工具：**
```bash
# 首先创建 URL 列表文件
echo "http://example.com" > js_capture_urls.txt

# 运行工具（单线程模式）
docker run --rm \
  -v $(pwd)/js_capture_files:/app/js_capture_files \
  -v $(pwd)/js_capture_urls.txt:/app/js_capture_urls.txt \
  chkapi:latest python3 tools/jsCapture.py

# 运行工具（并发模式）
docker run --rm \
  -v $(pwd)/js_capture_files:/app/js_capture_files \
  -v $(pwd)/js_capture_urls.txt:/app/js_capture_urls.txt \
  chkapi:latest python3 tools/jsCapture.py --concurrent --max-concurrent 3
```

### 方式二：使用 Docker Compose

#### 1. 开发模式（挂载整个项目目录）

**默认配置**：`docker-compose.yml` 已配置为挂载整个项目目录，代码修改后立即生效。

```bash
# 构建并启动
docker-compose build
docker-compose up -d

# 运行特定命令
docker-compose exec chkapi python3 ChkApi.py -u "http://example.com"
docker-compose exec chkapi python3 tools/jsCapture.py --concurrent
```

#### 2. 生产模式（只挂载必要目录）

使用生产环境配置，更安全且性能更好：

```bash
# 使用生产配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 运行命令
docker-compose -f docker-compose.yml -f docker-compose.prod.yml exec chkapi python3 ChkApi.py -u "http://example.com"
```

#### 3. 运行一次性任务

```bash
# 运行 ChkApi
docker-compose run --rm chkapi python3 ChkApi.py -u "http://example.com"

# 运行 JS Capture（单线程）
docker-compose run --rm chkapi python3 tools/jsCapture.py

# 运行 JS Capture（并发模式）
docker-compose run --rm chkapi python3 tools/jsCapture.py --concurrent --max-concurrent 3
```

## 镜像说明

### 基础镜像
- **Python 3.9-slim**：轻量级 Python 3.9 镜像

### 包含的组件
- Python 3.9
- Google Chrome（最新稳定版）
- Chromedriver
- Playwright（含 Chromium 浏览器）
- 所有 Python 依赖包（见 `requirements.txt`）

### 目录结构
```
/app/
├── ChkApi.py              # 主工具
├── tools/
│   └── jsCapture.py       # JS 捕获工具
├── plugins/               # 插件目录
├── js_capture_files/      # JS 文件输出目录
└── js_capture_cache/      # 缓存目录
```

## 挂载卷说明

### 开发模式（默认）

`docker-compose.yml` 默认配置为**挂载整个项目目录**（`.:/app`），这样：
- ✅ 代码修改后立即生效，无需重建镜像
- ✅ 配置文件修改立即生效
- ✅ 方便开发和调试
- ⚠️ 注意：会覆盖容器内的所有文件

### 生产模式

使用 `docker-compose.prod.yml` 时，只挂载必要的目录：

- `./plugins` → `/app/plugins`：插件目录（只读）
- `./tools` → `/app/tools`：工具目录（只读）
- `./js_capture_files` → `/app/js_capture_files`：JS 文件输出目录
- `./js_capture_cache` → `/app/js_capture_cache`：缓存目录
- `./js_capture_log.txt` → `/app/js_capture_log.txt`：日志文件
- `./js_capture_urls.txt` → `/app/js_capture_urls.txt`：URL 列表文件（只读）

### 命名卷（可选）

也可以使用 Docker 命名卷，数据存储在 Docker 管理的卷中，不依赖主机目录：

```yaml
volumes:
  - js_capture_files:/app/js_capture_files
  - js_capture_cache:/app/js_capture_cache
```

查看命名卷：
```bash
docker volume ls
docker volume inspect chkapi_js_capture_files
```

## 环境变量

- `PYTHONUNBUFFERED=1`：确保 Python 输出实时显示
- `DISPLAY=:99`：X11 显示（用于无头浏览器）

## 常见问题

### 1. 权限问题

如果遇到权限问题，可以在运行容器时添加用户映射：

```bash
docker run --rm -u $(id -u):$(id -g) ...
```

### 2. 内存限制

如果处理大量 URL，建议增加容器内存限制：

```bash
docker run --rm --memory="2g" ...
```

### 3. 网络问题

如果需要访问外部网络，确保容器有网络访问权限。

### 4. 查看日志

```bash
# 查看容器日志
docker logs chkapi

# 实时查看日志
docker logs -f chkapi
```

## 构建优化

### 多阶段构建（可选）

如果需要更小的镜像，可以使用多阶段构建，但当前镜像已经使用了 `python:3.9-slim` 基础镜像，已经比较轻量。

### 缓存优化

构建时会自动使用 Docker 层缓存，如果只修改了代码，重新构建会很快。

## 示例脚本

### 批量处理脚本

创建 `docker-run.sh`：

```bash
#!/bin/bash
# 批量运行 JS Capture 工具

docker run --rm \
  -v $(pwd)/js_capture_files:/app/js_capture_files \
  -v $(pwd)/js_capture_urls.txt:/app/js_capture_urls.txt \
  chkapi:latest \
  python3 tools/jsCapture.py --concurrent --max-concurrent 5
```

## 注意事项

1. **首次运行**：首次运行 Playwright 需要下载浏览器，可能需要一些时间
2. **资源消耗**：并发模式会启动多个浏览器实例，注意内存和 CPU 使用
3. **文件权限**：确保挂载的目录有适当的读写权限
4. **网络访问**：容器需要能够访问目标 URL

## 更新镜像

```bash
# 重新构建镜像
docker build -t chkapi:latest .

# 或者使用 docker-compose
docker-compose build --no-cache
```

