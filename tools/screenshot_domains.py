#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
域名截图工具
用于批量访问域名并截图，保存网页截图和基本信息
"""

import asyncio
import csv
import argparse
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("请安装 playwright: pip install playwright")
    print("然后运行: playwright install chromium")
    sys.exit(1)

# 导入项目公共模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plugins.nodeCommon import headers

# 输出目录
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 日志目录
LOGS_DIR = OUTPUT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def setup_logging(log_name: str):
    """配置日志系统，输出到 output/logs 目录"""
    log_file = LOGS_DIR / f"{log_name}.log"

    # 清除现有的处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8', mode='a'),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger(__name__)


# 初始化日志
logger = setup_logging("screenshot_domains")


def logger_print_content(content):
    """日志输出函数"""
    logger.info(content)

# 配置
TIMEOUT = 30000  # 30秒超时
SCREENSHOT_WIDTH = 1920
SCREENSHOT_HEIGHT = 1080
MIN_CONCURRENT = 1
MAX_CONCURRENT = 10
DEFAULT_CONCURRENT = 3


class ScreenshotTool:
    """域名截图工具"""

    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.success_count = 0
        self.fail_count = 0

    async def capture_screenshot(self, url: str, idx: int, total: int) -> dict:
        """对单个 URL 进行截图

        Args:
            url: 要截图的 URL
            idx: 当前索引
            total: 总数

        Returns:
            截图结果字典
        """
        result = {
            "url": url,
            "success": False,
            "screenshot_path": "",
            "error": "",
            "final_url": "",
            "title": "",
            "load_time": 0
        }

        # 确保 URL 包含协议
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        parsed = urlparse(url)
        domain = parsed.netloc.replace(':', '_')

        # 创建域名专用目录
        domain_dir = self.output_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        # 截图文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = domain_dir / f"screenshot_{timestamp}.png"

        logger_print_content(f"[{idx}/{total}] 正在处理: {url}")

        start_time = asyncio.get_event_loop().time()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={'width': SCREENSHOT_WIDTH, 'height': SCREENSHOT_HEIGHT},
                        user_agent=headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                        ignore_https_errors=True
                    )
                    page = await context.new_page()

                    # 访问页面
                    try:
                        response = await page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                        if response:
                            result["final_url"] = response.url
                    except PlaywrightTimeoutError:
                        logger_print_content(f"[{idx}/{total}] 警告: {url} 加载超时，尝试截图当前状态")
                        result["error"] = "加载超时"

                    # 获取页面标题
                    try:
                        result["title"] = await page.title()
                    except:
                        result["title"] = ""

                    # 截图
                    await page.screenshot(path=str(screenshot_path), full_page=False)

                    result["success"] = True
                    result["screenshot_path"] = str(screenshot_path)
                    result["load_time"] = round(asyncio.get_event_loop().time() - start_time, 2)

                    logger_print_content(f"[{idx}/{total}] 成功: {url} -> {screenshot_path.name}")

                finally:
                    await browser.close()

        except Exception as e:
            result["error"] = str(e)
            logger_print_content(f"[{idx}/{total}] 失败: {url} - {e}")

        return result

    async def batch_process(self, urls: list, concurrent: int = DEFAULT_CONCURRENT):
        """批量处理 URL 列表

        Args:
            urls: URL 列表
            concurrent: 并发数
        """
        # 验证并发数范围
        if concurrent < MIN_CONCURRENT:
            logger_print_content(f"并发数 {concurrent} 小于最小值 {MIN_CONCURRENT}，已调整为 {MIN_CONCURRENT}")
            concurrent = MIN_CONCURRENT
        elif concurrent > MAX_CONCURRENT:
            logger_print_content(f"并发数 {concurrent} 超过最大值 {MAX_CONCURRENT}，已调整为 {MAX_CONCURRENT}")
            concurrent = MAX_CONCURRENT

        total = len(urls)
        logger_print_content(f"开始批量处理 {total} 个 URL，并发数: {concurrent}")

        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrent)

        async def process_with_lock(idx, url):
            async with semaphore:
                return await self.capture_screenshot(url, idx + 1, total)

        # 创建所有任务
        tasks = [process_with_lock(idx, url) for idx, url in enumerate(urls)]

        # 并发执行
        results = await asyncio.gather(*tasks)

        # 统计结果
        self.success_count = sum(1 for r in results if r["success"])
        self.fail_count = total - self.success_count

        # 保存结果到 CSV
        self.save_results(results)

        # 输出总结
        logger_print_content(f"\n=== 截图完成 ===")
        logger_print_content(f"总数: {total}")
        logger_print_content(f"成功: {self.success_count}")
        logger_print_content(f"失败: {self.fail_count}")
        logger_print_content(f"截图已保存到: {self.output_dir}")

        return results

    def save_results(self, results: list):
        """保存结果到 CSV 文件

        Args:
            results: 结果列表
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = self.output_dir / f"screenshot_results_{timestamp}.csv"

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['url', 'final_url', 'success', 'screenshot_path', 'title', 'load_time', 'error']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                writer.writerow(result)

        logger_print_content(f"结果已保存到: {csv_path}")


def load_urls_from_file(filename: str) -> list:
    """从文件加载 URL 列表

    Args:
        filename: 文件路径

    Returns:
        URL 列表
    """
    urls = []
    file_path = Path(filename)

    if not file_path.exists():
        logger_print_content(f"错误: 文件不存在: {file_path}")
        return urls

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            url = line.strip()
            # 跳过空行和注释行
            if url and not url.startswith('#'):
                urls.append(url)

    return urls


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="域名截图工具 - 批量访问域名并截图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
使用示例:
  # 使用默认输入文件 (domains.txt) 和输出目录 (output/screenshots/)
  python screenshot_domains.py

  # 指定输入文件
  python screenshot_domains.py --input custom_domains.txt

  # 指定输出目录
  python screenshot_domains.py --output shots/

  # 使用并发模式，指定并发数
  python screenshot_domains.py --concurrent --max-concurrent 5

  # 设置截图超时时间（秒）
  python screenshot_domains.py --timeout 20

  # 设置截图尺寸
  python screenshot_domains.py --width 2560 --height 1440

并发数建议:
  - 低配置系统：1-2
  - 中等配置系统：3-5
  - 高配置系统：5-10
        """
    )
    parser.add_argument(
        "--input",
        type=str,
        default="domains.txt",
        help="输入文件路径，每行一个域名或 URL (默认: domains.txt)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录路径 (默认: output/screenshots/)"
    )
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="启用并发模式（默认启用）"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=DEFAULT_CONCURRENT,
        help=f"最大并发数 (范围: {MIN_CONCURRENT}-{MAX_CONCURRENT}, 默认: {DEFAULT_CONCURRENT})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT // 1000,
        help=f"页面加载超时时间（秒，默认: {TIMEOUT // 1000}）"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=SCREENSHOT_WIDTH,
        help=f"截图宽度（像素，默认: {SCREENSHOT_WIDTH}）"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=SCREENSHOT_HEIGHT,
        help=f"截图高度（像素，默认: {SCREENSHOT_HEIGHT}）"
    )

    args = parser.parse_args()

    # 设置全局超时和尺寸
    global TIMEOUT, SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT
    TIMEOUT = args.timeout * 1000
    SCREENSHOT_WIDTH = args.width
    SCREENSHOT_HEIGHT = args.height

    # 设置输出目录
    output_dir = Path(args.output) if args.output else OUTPUT_DIR / "screenshots"

    # 从文件加载 URL
    urls = load_urls_from_file(args.input)

    if not urls:
        logger_print_content(f"错误: 未找到 URL 列表，请创建 {args.input} 文件并添加域名或 URL")
        return

    # 创建截图工具
    tool = ScreenshotTool(output_dir=output_dir)

    # 批量处理
    await tool.batch_process(urls, concurrent=args.max_concurrent)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger_print_content("\n用户中断，程序退出")
        sys.exit(0)
    except Exception as e:
        logger_print_content(f"程序异常退出: {e}")
        sys.exit(1)
