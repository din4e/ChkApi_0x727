# 使用 Python 3.9 作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（用于 jsCapture.py）
RUN playwright install chromium && \
    playwright install-deps chromium

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p js_capture_files js_capture_cache

# 设置权限
RUN chmod +x build.sh 2>/dev/null || true

# 验证安装
RUN python3 --version

# # 默认命令（可以根据需要修改）
# CMD ["python3", "ChkApi.py", "--help"]
