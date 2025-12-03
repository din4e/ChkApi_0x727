# 使用 Python 3.9 作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 安装 Playwright Chromium 需要的系统依赖
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libexpat1 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxkbcommon0 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（用于 jsCapture.py）
RUN playwright install chromium && \
    playwright install-deps chromium || true

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
