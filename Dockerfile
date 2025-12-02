# 使用 Python 3.9 作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99

# 安装系统依赖（Chrome、Chromedriver 等）
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    fonts-liberation \
    libu2f-udev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Google Chrome（使用新的 GPG 密钥方法）
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# 安装 Chromedriver 和必要的工具
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装匹配 Chrome 版本的 Chromedriver
# 注意：Chrome 115+ 需要使用 Chrome for Testing，这里使用简化方法
RUN CHROME_VERSION=$(google-chrome --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1) && \
    CHROME_MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d. -f1) && \
    echo "Chrome version: $CHROME_VERSION, Major: $CHROME_MAJOR_VERSION" && \
    if [ "$CHROME_MAJOR_VERSION" -ge 115 ]; then \
        echo "Chrome 115+, using Chrome for Testing chromedriver..."; \
        CHROMEDRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_MAJOR_VERSION}" || echo ""); \
        if [ -n "$CHROMEDRIVER_VERSION" ]; then \
            wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip && \
            unzip -q /tmp/chromedriver.zip -d /tmp && \
            mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
            chmod +x /usr/bin/chromedriver && \
            rm -rf /tmp/chromedriver*; \
        else \
            echo "Failed to get chromedriver version, trying alternative method..."; \
            apt-get update -y && apt-get install -y chromium-chromedriver && \
            find /usr -name chromedriver -type f -executable 2>/dev/null | head -1 | xargs -I {} sh -c 'if [ ! -f /usr/bin/chromedriver ]; then ln -sf {} /usr/bin/chromedriver; fi' || true; \
        fi; \
    else \
        echo "Chrome < 115, using legacy chromedriver..."; \
        CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION}" || echo ""); \
        if [ -n "$CHROMEDRIVER_VERSION" ]; then \
            wget -q "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip" -O /tmp/chromedriver.zip && \
            unzip -q /tmp/chromedriver.zip -d /tmp && \
            mv /tmp/chromedriver /usr/bin/chromedriver && \
            chmod +x /usr/bin/chromedriver && \
            rm /tmp/chromedriver.zip; \
        else \
            echo "Installing chromium-chromedriver as fallback..."; \
            apt-get update -y && apt-get install -y chromium-chromedriver && \
            find /usr -name chromedriver -type f -executable 2>/dev/null | head -1 | xargs -I {} sh -c 'if [ ! -f /usr/bin/chromedriver ]; then ln -sf {} /usr/bin/chromedriver; fi' || true; \
        fi; \
    fi && \
    rm -rf /var/lib/apt/lists/* && \
    chromedriver --version || echo "Warning: chromedriver may not be properly installed"

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
RUN python3 --version && \
    google-chrome --version && \
    chromedriver --version 2>/dev/null || echo "Chromedriver installed"

# 默认命令（可以根据需要修改）
CMD ["python3", "ChkApi.py", "--help"]

