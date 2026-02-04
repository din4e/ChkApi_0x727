#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
域名检测工具
用于批量检测域名的泛解析情况和子域名存活情况
"""

import subprocess
import re
import csv
import random
import string
import argparse
import ipaddress
import sys
import os
import logging
from pathlib import Path
from multiprocessing import Pool, cpu_count
from functools import partial
from datetime import datetime

# 导入项目公共模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plugins.nodeCommon import headers, is_ip

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
logger = setup_logging("ping_domains")


def logger_print_content(content):
    """日志输出函数"""
    logger.info(content)

# Subdomain prefixes to test
PREFIXES = [
    "www-czbank",
    "www-czbyqy",
    "www-zheyinlesasing",
    "www-zsbank",
    "www-czbank-wm"
]

# 输出目录
OUTPUT_DIR = Path("tools_output")


def generate_random_subdomain(length=12):
    """生成随机子域名用于泛解析检测"""
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"test-{random_str}-check"


def is_valid_ip(ip_str):
    """验证 IP 地址是否有效"""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def is_internal_ip(ip_str):
    """判断是否为内网 IP"""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return ip_obj.is_private or ip_obj.is_loopback or str(ip_obj) == '0.0.0.0'
    except ValueError:
        return False


def is_wildcard_domain(domain, timeout=2):
    """检测域名是否为泛解析

    通过生成一个随机子域名来测试，如果随机子域名能解析到IP，则说明是泛解析

    Args:
        domain: 域名
        timeout: 超时时间

    Returns:
        (是否泛解析, 检测到的IP)
    """
    random_subdomain = f"{generate_random_subdomain()}.{domain}"
    ip = ping_domain(random_subdomain, timeout)

    if ip != "No IP":
        return True, ip

    return False, None


def ping_domain(subdomain, timeout=2):
    """Ping a single subdomain and return IP if resolved"""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout * 1000), subdomain],
            capture_output=True,
            text=True,
            timeout=timeout + 1
        )

        output = result.stdout

        # Extract IP from ping output (Windows format: "Reply from x.x.x.x" or Chinese "来自 x.x.x.x")
        match = re.search(r'from\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})|来自\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
        if match:
            return match.group(1) or match.group(2)
        return "No IP"
    except Exception:
        return "No IP"


def process_domain(domain):
    """Process a single domain: ping all subdomain prefixes"""
    domain = domain.strip()
    if not domain:
        return None

    result = {"domain": domain}

    # 检测是否为泛解析
    is_wildcard, wildcard_ip = is_wildcard_domain(domain)
    result["is_wildcard"] = "Yes" if is_wildcard else "No"
    result["wildcard_ip"] = wildcard_ip if wildcard_ip else ""

    for i, prefix in enumerate(PREFIXES, 1):
        subdomain = f"{prefix}.{domain}"
        ip = ping_domain(subdomain)
        result[f"subdomain_{i}"] = subdomain
        result[f"ip_{i}"] = ip

    return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="域名检测工具 - 批量检测域名的泛解析情况和子域名存活情况",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认输入文件 (domains.txt) 和输出目录 (output/)
  python ping_domains.py

  # 指定输入文件
  python ping_domains.py --input custom_domains.txt

  # 指定输出目录
  python ping_domains.py --output results/

  # 组合使用
  python ping_domains.py --input ioc.txt --output ping/
        """
    )
    parser.add_argument(
        "--input",
        type=str,
        default="domains.txt",
        help="输入文件路径，每行一个域名 (默认: domains.txt)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录路径 (默认: output/ping_results/)"
    )

    args = parser.parse_args()

    # 设置输出目录
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = OUTPUT_DIR / "ping"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 检查输入文件
    input_file = Path(args.input)
    if not input_file.exists():
        logger_print_content(f"错误: 输入文件不存在: {input_file}")
        logger_print_content(f"请创建输入文件，每行一个域名")
        return

    # Read domains from file
    with open(input_file, "r", encoding="utf-8") as f:
        domains = [line.strip() for line in f if line.strip()]

    if not domains:
        logger_print_content(f"错误: 输入文件中没有找到域名")
        return

    logger_print_content(f"开始处理 {len(domains)} 个域名，使用 {cpu_count()} 个 CPU 核心...")

    # Use multiprocessing to ping domains in parallel
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(process_domain, domains)

    # Filter out None results
    results = [r for r in results if r]

    # Write results to CSV
    timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"ping_results_{timestamp}.csv"

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["domain", "is_wildcard", "wildcard_ip"] + \
                    [f"subdomain_{i}" for i in range(1, len(PREFIXES) + 1)] + \
                    [f"ip_{i}" for i in range(1, len(PREFIXES) + 1)]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Calculate statistics
    has_ip = sum(1 for r in results if any(r[f"ip_{i}"] != "No IP" for i in range(1, len(PREFIXES) + 1)))
    wildcard_count = sum(1 for r in results if r["is_wildcard"] == "Yes")

    logger_print_content(f"\n=== 检测完成 ===")
    logger_print_content(f"总域名数: {len(results)}")
    logger_print_content(f"泛解析域名: {wildcard_count}")
    logger_print_content(f"有解析结果的域名: {has_ip}")
    logger_print_content(f"无解析结果的域名: {len(results) - has_ip}")
    logger_print_content(f"\n结果已保存到: {output_file}")

    # Display wildcard domains
    if wildcard_count > 0:
        logger_print_content(f"\n=== 泛解析域名列表 ===")
        for r in results:
            if r["is_wildcard"] == "Yes":
                logger_print_content(f"  {r['domain']} -> {r['wildcard_ip']}")

    # Display domains with resolved IPs
    if has_ip > 0:
        logger_print_content(f"\n=== 有解析结果的域名 ===")
        for r in results:
            if any(r[f"ip_{i}"] != "No IP" for i in range(1, len(PREFIXES) + 1)):
                domain_info = f"\n{r['domain']}:" + (f" [泛解析: {r['wildcard_ip']}]" if r['is_wildcard'] == 'Yes' else "")
                logger_print_content(domain_info)
                for i in range(1, len(PREFIXES) + 1):
                    if r[f"ip_{i}"] != "No IP":
                        logger_print_content(f"  {r[f'subdomain_{i}']} -> {r[f'ip_{i}']}")


if __name__ == "__main__":
    main()
