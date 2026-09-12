echo 1 > /proc/sys/vm/overcommit_memory
apt-get update -y
apt install python3-pip -y
python3 -m pip uninstall urllib3 chardet -y
python3 -m pip install urllib3 chardet

apt --fix-broken install -y

python3 -m pip install -r requirements.txt

# 安装 Playwright Chromium 浏览器及系统依赖（用于抓取页面加载的js和API请求）
python3 -m playwright install chromium
python3 -m playwright install-deps chromium

python3 --version
