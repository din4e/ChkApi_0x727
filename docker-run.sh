#!/bin/bash
# Docker 容器运行脚本

set -e

# 默认参数
MODE="chkapi"
URL=""
CONCURRENT=false
MAX_CONCURRENT=3

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --url)
            URL="$2"
            shift 2
            ;;
        --concurrent)
            CONCURRENT=true
            shift
            ;;
        --max-concurrent)
            MAX_CONCURRENT="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --mode MODE           运行模式: chkapi 或 jscapture (默认: chkapi)"
            echo "  --url URL             ChkApi 目标 URL (仅 chkapi 模式)"
            echo "  --concurrent         启用并发模式 (仅 jscapture 模式)"
            echo "  --max-concurrent N   最大并发数 (默认: 3)"
            echo "  --help, -h           显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0 --mode chkapi --url \"http://example.com\""
            echo "  $0 --mode jscapture --concurrent --max-concurrent 5"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 创建必要的目录
mkdir -p js_capture_files js_capture_cache

# 准备挂载卷
VOLUMES="-v $(pwd)/js_capture_files:/app/js_capture_files"
VOLUMES="$VOLUMES -v $(pwd)/js_capture_cache:/app/js_capture_cache"
VOLUMES="$VOLUMES -v $(pwd)/js_capture_log.txt:/app/js_capture_log.txt"

if [ -f "js_capture_urls.txt" ]; then
    VOLUMES="$VOLUMES -v $(pwd)/js_capture_urls.txt:/app/js_capture_urls.txt:ro"
fi

# 根据模式运行
if [ "$MODE" = "chkapi" ]; then
    if [ -z "$URL" ]; then
        echo "错误: ChkApi 模式需要 --url 参数"
        exit 1
    fi
    echo "运行 ChkApi: $URL"
    docker run --rm $VOLUMES chkapi:latest python3 ChkApi.py -u "$URL"
    
elif [ "$MODE" = "jscapture" ]; then
    if [ ! -f "js_capture_urls.txt" ]; then
        echo "警告: 未找到 js_capture_urls.txt 文件"
        echo "创建示例文件..."
        cp tools/js_capture_urls.txt.example js_capture_urls.txt 2>/dev/null || echo "请手动创建 js_capture_urls.txt 文件"
    fi
    
    if [ "$CONCURRENT" = true ]; then
        echo "运行 JS Capture (并发模式, 并发数: $MAX_CONCURRENT)"
        docker run --rm $VOLUMES chkapi:latest python3 tools/jsCapture.py --concurrent --max-concurrent $MAX_CONCURRENT
    else
        echo "运行 JS Capture (单线程模式)"
        docker run --rm $VOLUMES chkapi:latest python3 tools/jsCapture.py
    fi
else
    echo "错误: 未知模式: $MODE"
    echo "支持的模式: chkapi, jscapture"
    exit 1
fi

