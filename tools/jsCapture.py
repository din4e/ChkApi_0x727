#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JS 文件捕获工具
用于批量访问 URL，捕获并下载 JS 文件，检测 IP 地址
独立工具，不影响 ChkApi 主功能
"""

import asyncio
import json
import os
import re
import hashlib
import time
import argparse
import ipaddress
import signal
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Optional, Set
import logging

try:
    from playwright.async_api import async_playwright, Page, Response, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("请安装 playwright: pip install playwright")
    print("然后运行: playwright install chromium")
    exit(1)

# 配置日志 - 使用独立的日志文件
LOG_FILE = Path("js_capture_log.txt")
JS_FILES_DIR = Path("js_capture_files")
CACHE_DIR = Path("js_capture_cache")


def setup_logging(log_level: str = "INFO"):
    """
    配置日志系统
    
    Args:
        log_level: 日志等级 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # 将字符串转换为日志等级
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'无效的日志等级: {log_level}')
    
    # 清除现有的处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 配置日志
    # 注意：force 参数在 Python 3.8+ 才支持，这里手动清除后重新配置
    try:
        logging.basicConfig(
            level=numeric_level,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),
                logging.StreamHandler()
            ],
            force=True  # Python 3.8+ 支持强制重新配置
        )
    except TypeError:
        # Python 3.7 及以下不支持 force 参数，手动配置
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        # 设置格式
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # 添加文件处理器
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)


# 默认日志配置
setup_logging("INFO")
logger = logging.getLogger(__name__)

# 日志输出锁（用于并发模式下的日志同步）
_log_lock = asyncio.Lock()


async def safe_log(level: str, message: str, use_lock: bool = False):
    """
    线程安全的日志输出函数
    
    Args:
        level: 日志级别 ('debug', 'info', 'warning', 'error', 'critical')
        message: 日志消息
        use_lock: 是否使用锁（在并发模式下使用）
    """
    if use_lock:
        async with _log_lock:
            if level == 'debug':
                logger.debug(message)
            elif level == 'info':
                logger.info(message)
            elif level == 'warning':
                logger.warning(message)
            elif level == 'error':
                logger.error(message)
            elif level == 'critical':
                logger.critical(message)
    else:
        # 单线程模式直接输出，无需加锁
        if level == 'debug':
            logger.debug(message)
        elif level == 'info':
            logger.info(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)
        elif level == 'critical':
            logger.critical(message)

# 配置
TIMEOUT = 20000  # 20秒超时
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
LARGE_FILE_WARNING_SIZE = 10 * 1024 * 1024  # 10MB，超过此大小的文件会警告可能未完全检测到 IP
CACHE_DIR.mkdir(exist_ok=True)
MIN_CONCURRENT = 1  # 最小并发数
MAX_CONCURRENT = 100  # 最大并发数（建议值：3-100，根据系统性能调整）
DEFAULT_CONCURRENT = 5  # 默认并发数


class IPDetector:
    """IP 地址检测器（使用 Python 标准库 ipaddress 模块）"""
    
    # IP 过滤规则：需要过滤的 IP 段
    FILTERED_IP_PATTERNS = [
        r'^2\.5\.',  # 过滤以 2.5 开头的 IP
    ]
    
    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """使用标准库验证是否为有效的 IP 地址"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_internal_ip(ip: str) -> bool:
        """判断是否为内网 IP（使用标准库）"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            # is_private 判断是否为私有 IP（内网 IP）
            return ip_obj.is_private or ip_obj.is_loopback or str(ip_obj) == '0.0.0.0'
        except ValueError:
            return False
    
    @staticmethod
    def should_filter_ip(ip: str) -> bool:
        """
        判断是否应该过滤该 IP 地址
        
        Args:
            ip: IP 地址字符串
            
        Returns:
            True 表示应该过滤（不显示），False 表示不过滤
        """
        for pattern in IPDetector.FILTERED_IP_PATTERNS:
            if re.match(pattern, ip):
                return True
        return False
    
    @staticmethod
    def detect_ips(text: str, max_context: int = 50) -> List[Dict]:
        """检测文本中的 IP 地址（使用标准库 ipaddress 模块验证）"""
        # IP 地址正则表达式（匹配可能的 IP 格式）
        # 使用标准库 ipaddress 进行最终验证，自动处理前导零、范围验证等
        ip_pattern = r'(?<![.\d])(?:(?:0|[1-9]\d?|1\d{2}|2[0-4]\d|25[0-5])\.){3}(?:0|[1-9]\d?|1\d{2}|2[0-4]\d|25[0-5])(?![.\d])'
        ips_found = []
        seen_ips = set()
        
        for match in re.finditer(ip_pattern, text):
            ip_str = match.group()
            if ip_str in seen_ips:
                continue
            
            # 使用标准库验证 IP 地址（自动处理前导零、范围验证等）
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                # 只处理 IPv4 地址
                if not isinstance(ip_obj, ipaddress.IPv4Address):
                    continue
            except ValueError:
                # 不是有效的 IP 地址（如包含前导零：014.027 等）
                continue
            
            # 获取上下文，用于进一步验证
            start = max(0, match.start() - max_context)
            end = min(len(text), match.end() + max_context)
            context = text[start:end].replace('\n', ' ').replace('\r', ' ')
            
            # 获取更宽的上下文用于判断
            before_ip = text[max(0, match.start() - 50):match.start()].lower()
            after_ip = text[match.end():min(len(text), match.end() + 50)].lower()
            full_context = (before_ip + ' ' + ip_str + ' ' + after_ip).lower()
            
            # 排除明显不是 IP 的常见误报场景
            # 1. 过滤 IP 字符串以 "." 开头或结尾的情况（说明不是完整的 IP 地址）
            if match.start() > 0 and text[match.start() - 1] == '.':
                continue
            if match.end() < len(text) and text[match.end()] == '.':
                continue
            
            # 2. 如果所有段都小于 10 且上下文中有 URL 或 API 相关关键词，可能是真正的 IP
            # 否则很可能是版本号或规范引用
            parts = ip_str.split('.')
            if all(int(p) < 10 for p in parts):
                # 检查是否有真正的 IP 使用场景的关键词
                ip_usage_keywords = ['http://', 'https://', '://', 'api', 'endpoint', 'server', 'host', 'connect', 'socket', 'tcp', 'udp']
                has_ip_keywords = any(keyword in full_context for keyword in ip_usage_keywords)
                if not has_ip_keywords:
                    # 没有 IP 使用场景的关键词，很可能是误报
                    continue
            
            # 3. SVG 路径数据（包含字母和特殊字符）
            if re.search(r'[a-zA-Z][.\d]+|[\d.]+[a-zA-Z]', context, re.IGNORECASE):
                # 检查 IP 前后是否有字母（可能是 SVG 路径、版本号等）
                if re.search(r'[a-zA-Z]', before_ip + after_ip, re.IGNORECASE):
                    continue
            
            # 4. 版本号格式（如 1.2.3.4 在版本字符串中）
            if re.search(r'[vV]\s*\d+\.\d+\.\d+\.\d+|version\s*\d+\.\d+\.\d+\.\d+', context, re.IGNORECASE):
                # 如果上下文明确是版本号，跳过
                continue
            
            # 5. 数学表达式或坐标（如 106.133 67.2a4.797）
            if re.search(r'[\d.]+\s+[\d.]+[a-zA-Z]', context):
                continue
            
            # 6. 应用 IP 过滤规则（如过滤 2.5 开头的 IP）
            if IPDetector.should_filter_ip(ip_str):
                continue
            
            seen_ips.add(ip_str)
            
            # 使用标准库判断是否为内网 IP
            is_internal = ip_obj.is_private or ip_obj.is_loopback or str(ip_obj) == '0.0.0.0'
            ip_type = "内网 IP" if is_internal else "公网 IP"
            
            ips_found.append({
                "ip": ip_str,
                "type": ip_type,
                "is_internal": is_internal,
                "context": context
            })
        
        return ips_found


class JSCaptureTool:
    """JS 文件捕获工具"""
    
    def __init__(self, concurrent_mode: bool = False):
        self.cache = {}  # URL -> MD5 缓存
        self.cache_hits = 0
        self.cache_misses = 0
        self.concurrent_mode = concurrent_mode  # 是否处于并发模式
    
    async def _log_safe(self, level: str, *messages: str):
        """
        线程安全的日志输出（用于并发模式）
        
        Args:
            level: 日志级别 ('debug', 'info', 'warning', 'error', 'critical')
            *messages: 要输出的日志消息（可以是多行）
        """
        if self.concurrent_mode:
            async with _log_lock:
                for msg in messages:
                    if level == 'debug':
                        logger.debug(msg)
                    elif level == 'info':
                        logger.info(msg)
                    elif level == 'warning':
                        logger.warning(msg)
                    elif level == 'error':
                        logger.error(msg)
                    elif level == 'critical':
                        logger.critical(msg)
        else:
            # 单线程模式直接输出
            for msg in messages:
                if level == 'debug':
                    logger.debug(msg)
                elif level == 'info':
                    logger.info(msg)
                elif level == 'warning':
                    logger.warning(msg)
                elif level == 'error':
                    logger.error(msg)
                elif level == 'critical':
                    logger.critical(msg)
        
    def get_file_hash(self, content: bytes) -> str:
        """计算文件 MD5"""
        return hashlib.md5(content).hexdigest()
    
    def is_webpack_file(self, filename: str) -> bool:
        """判断是否为 Webpack 文件"""
        webpack_patterns = [
            r'chunk-.*\.js',
            r'app\..*\.js',
            r'vendor.*\.js',
            r'manifest.*\.js',
        ]
        return any(re.search(pattern, filename, re.IGNORECASE) for pattern in webpack_patterns)
    
    def get_safe_filename(self, url: str, default: str = "file") -> str:
        """从 URL 获取安全的文件名"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if path:
            filename = os.path.basename(path)
            if filename and '.' in filename:
                return filename
        return default
    
    async def download_file(self, url: str, session) -> Optional[Dict]:
        """下载文件"""
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    content = await response.read()
                    if len(content) > MAX_FILE_SIZE:
                        logger.warning(f"[!] 文件 {url} 太大，跳过")
                        return None
                    
                    filename = self.get_safe_filename(url)
                    file_hash = self.get_file_hash(content)
                    
                    # 检查缓存
                    cache_key = f"{url}:{file_hash}"
                    if cache_key in self.cache:
                        logger.debug(f"[+] 缓存命中 {filename} (MD5: {file_hash[:12]}...) - {url}")
                        self.cache_hits += 1
                    else:
                        logger.debug(f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) - {url}")
                        self.cache_misses += 1
                        self.cache[cache_key] = True
                    
                    return {
                        "url": url,
                        "filename": filename,
                        "size": len(content),
                        "hash": file_hash,
                        "status": response.status,
                        "content": content
                    }
        except Exception as e:
            logger.error(f"下载文件失败 {url}: {e}")
            return None
    
    async def capture_js_files(self, url: str) -> Dict:
        """捕获指定 URL 的 JS 文件"""
        start_time = time.time()
        original_url = url
        final_url = url
        
        # 创建保存目录
        parsed = urlparse(url)
        host = parsed.netloc.replace(':', '_')
        save_dir = JS_FILES_DIR / f"{datetime.now().strftime('%Y-%m-%d')}_{host}"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"文件将保存到: {save_dir}")
        
        js_files = []
        map_files = []
        other_files = []
        error_msg = None
        
        async with async_playwright() as p:
            browser = None
            try:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    ignore_https_errors=True,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()
                
                # 监听网络请求
                captured_resources = []
                
                async def handle_response(response: Response):
                    try:
                        url = response.url
                        content_type = response.headers.get('content-type', '')
                        
                        # 只捕获 JS 文件
                        if 'javascript' in content_type or url.endswith('.js'):
                            resource = await response.body()
                            if resource and len(resource) < MAX_FILE_SIZE:
                                captured_resources.append({
                                    "url": url,
                                    "content": resource,
                                    "content_type": content_type
                                })
                    except Exception as e:
                        pass
                
                page.on("response", handle_response)
                
                # 访问页面
                logger.debug(f"正在访问: {url}")
                page_loaded = False
                try:
                    response = await page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                    if response:
                        final_url = response.url
                        page_loaded = True
                except PlaywrightTimeoutError:
                    error_msg = f"Timeout {TIMEOUT//1000} ms exceeded. \"{url}\", waiting until \"networkidle\""
                    logger.warning(error_msg)
                    # 即使超时，也尝试等待页面稳定
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                        page_loaded = True
                    except:
                        pass
                except Exception as e:
                    error_msg = str(e).replace('\n', '.')
                    logger.error(error_msg)
                
                # 获取页面 HTML 内容（确保页面已稳定）
                html_content = None
                if page_loaded:
                    try:
                        # 等待页面完全稳定，不再导航
                        await page.wait_for_load_state("networkidle", timeout=3000)
                    except:
                        # 如果等待失败，至少等待 DOM 加载完成
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=2000)
                        except:
                            pass
                    
                    # 尝试获取页面内容，添加重试机制
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            # 检查页面是否还在导航
                            try:
                                # 尝试等待页面稳定
                                await page.wait_for_load_state("load", timeout=1000)
                            except:
                                pass
                            
                            html_content = await page.content()
                            break  # 成功获取，退出重试循环
                        except Exception as e:
                            error_msg = str(e)
                            # 检查是否是导航相关的错误
                            if "navigating" in error_msg.lower() or "changing" in error_msg.lower():
                                if retry < max_retries - 1:
                                    # 页面还在导航，等待更长时间后重试
                                    await asyncio.sleep(1)
                                    logger.debug(f"页面仍在导航，等待后重试 {retry + 1}/{max_retries}")
                                    continue
                                else:
                                    # 最后一次重试，记录警告但不抛出异常
                                    logger.warning(f"页面仍在导航，无法获取内容: {error_msg}")
                                    html_content = None
                                    break
                            else:
                                # 其他类型的错误
                                if retry < max_retries - 1:
                                    await asyncio.sleep(0.5)
                                    logger.debug(f"获取页面内容失败，重试 {retry + 1}/{max_retries}: {e}")
                                else:
                                    # 最后一次重试失败，记录警告但不抛出异常
                                    logger.warning(f"无法获取页面内容（已重试 {max_retries} 次）: {e}")
                                    html_content = None
                
                if html_content:
                    try:
                        # 保存 HTML 为文本文件
                        html_filename = f"file_{hash(url) % 10000}.txt"
                        html_path = save_dir / html_filename
                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        
                        other_files.append({
                            "url": url,
                            "filename": html_filename,
                            "size": len(html_content.encode('utf-8')),
                            "hash": self.get_file_hash(html_content.encode('utf-8')),
                            "status": 200
                        })
                        logger.debug(f"[+] 已下载: {html_filename} ({len(html_content)} bytes, MD5: {self.get_file_hash(html_content.encode('utf-8'))[:12]}...)  - {url}")
                    except Exception as e:
                        logger.error(f"保存 HTML 失败: {e}")
                
                # 处理捕获的资源
                for resource in captured_resources:
                    url = resource["url"]
                    content = resource["content"]
                    filename = self.get_safe_filename(url, f"file_{hash(url) % 10000}.js")
                    file_hash = self.get_file_hash(content)
                    
                    # 保存文件
                    file_path = save_dir / filename
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    file_info = {
                        "url": url,
                        "filename": filename,
                        "size": len(content),
                        "hash": file_hash,
                        "status": 200
                    }
                    
                    # 检测是否为 Webpack 文件
                    # FIXME: 暂时不使用
                    # if self.is_webpack_file(filename):
                        # file_info["is_webpack"] = True
                    
                    # 检测 IP 地址（仅对 JS 文件）
                    if filename.endswith('.js'):
                        try:
                            text_content = content.decode('utf-8', errors='ignore')
                            # 大文件可能包含 IP 但未完全检测到
                            if len(content) > LARGE_FILE_WARNING_SIZE:
                                logger.debug(f"[!] 文件 {filename} 很大 ({len(content) / 1024:.1f}KB)，可能包含 IP 但未完全检测到")
                            
                            ips = IPDetector.detect_ips(text_content)
                            if ips:
                                file_info["ips"] = ips
                                for ip_info in ips:
                                    # 使用线程安全的日志输出（多行日志需要原子性）
                                    await self._log_safe('info',
                                        f"URL: {url}, 文件内容包含 {ip_info['type']}: {ip_info['ip']}",
                                        f"  └─ [{ip_info['ip']}] 上下文: {ip_info['context']}"
                                    )
                        except Exception as e:
                            pass
                        
                        # 尝试查找 source map
                        try:
                            text_content = content.decode('utf-8', errors='ignore')
                            map_match = re.search(r'//# sourceMappingURL=(.+)', text_content)
                            if map_match:
                                map_url = map_match.group(1).strip()
                                file_info["source_map_url"] = map_url
                        except:
                            pass
                    
                    js_files.append(file_info)
                    logger.debug(f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) [Webpack] [JS] - {url}" if file_info.get("is_webpack") else f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) [JS] - {url}")
                
                # 尝试下载 .map 文件
                logger.debug(f"\n检测到 {len(js_files)} 个 JS 文件，尝试访问对应的 .map 文件...")
                for js_file in js_files:
                    if "source_map_url" in js_file:
                        map_url = js_file["source_map_url"]
                        if not map_url.startswith('http'):
                            map_url = urljoin(js_file["url"], map_url)
                        
                        try:
                            response = await context.request.get(map_url)
                            if response.status == 200:
                                map_content = await response.body()
                                map_filename = os.path.basename(urlparse(map_url).path) or f"{js_file['filename']}.map"
                                map_path = save_dir / map_filename
                                with open(map_path, 'wb') as f:
                                    f.write(map_content)
                                
                                map_files.append({
                                    "url": map_url,
                                    "filename": map_filename,
                                    "size": len(map_content),
                                    "hash": self.get_file_hash(map_content),
                                    "status": 200
                                })
                                logger.info(f"[+] 已下载: {map_filename} ({len(map_content)} bytes) - {map_url}")
                        except Exception as e:
                            pass
                
            except Exception as e:
                error_msg = f"处理 URL 时出错: {str(e)}"
                logger.error(error_msg)
            finally:
                # 确保浏览器总是被关闭
                if browser:
                    try:
                        await browser.close()
                        logger.debug("浏览器已关闭")
                    except Exception as e:
                        logger.warning(f"关闭浏览器时出错: {e}")
        
        # 保存文件列表
        result = {
            "js_files": js_files,
            "map_files": map_files,
            "other_files": other_files,
            "run_time": round(time.time() - start_time, 2),
            "final_url": final_url,
            "original_url": original_url
        }
        if error_msg:
            result["error"] = error_msg
        
        json_path = save_dir / "captured_files.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 使用线程安全的日志输出（多行总结信息需要原子性）
        summary_messages = [
            f"文件列表已保存到: {json_path}",
            f"捕获完成!",
            f"JS 文件数量: {len(js_files)}",
            f"JS.map 文件数量: {len(map_files)}",
            f"其他文件数量: {len(other_files)}",
            f"运行时间: {result['run_time']} 秒",
            f"缓存统计: 命中 {self.cache_hits} 次，未命中 {self.cache_misses} 次"
        ]
        if self.cache_hits > 0:
            summary_messages.append(f"  (通过缓存复用了 {self.cache_hits} 个页面的分析结果，节省了分析时间)")
        summary_messages.append(f"文件已保存到: {save_dir}")
        await self._log_safe('debug', *summary_messages)
        
        return result
    
    async def batch_process(self, urls: List[str], concurrent: bool = False, max_concurrent: int = DEFAULT_CONCURRENT):
        """
        批量处理 URL
        
        Args:
            urls: URL 列表
            concurrent: 是否使用并发模式（默认 False，单线程模式用于调试）
            max_concurrent: 最大并发数（仅在 concurrent=True 时有效，范围：1-20，默认 3）
        """
        # 验证并发数范围
        if concurrent:
            if max_concurrent < MIN_CONCURRENT:
                logger.warning(f"并发数 {max_concurrent} 小于最小值 {MIN_CONCURRENT}，已调整为 {MIN_CONCURRENT}")
                max_concurrent = MIN_CONCURRENT
            elif max_concurrent > MAX_CONCURRENT:
                logger.warning(f"并发数 {max_concurrent} 超过最大值 {MAX_CONCURRENT}，已调整为 {MAX_CONCURRENT}")
                max_concurrent = MAX_CONCURRENT
        
        total = len(urls)
        mode = "并发模式" if concurrent else "单线程模式（调试）"
        logger.info(f"开始批量处理 {total} 个 URL - {mode}")
        if concurrent:
            logger.info(f"最大并发数: {max_concurrent} (范围: {MIN_CONCURRENT}-{MAX_CONCURRENT})")
        
        if concurrent:
            # 并发处理模式
            semaphore = asyncio.Semaphore(max_concurrent)
            self.concurrent_mode = True  # 标记为并发模式
            
            async def process_single_url(idx: int, url: str):
                """处理单个 URL（带信号量控制和日志锁）"""
                async with semaphore:
                    # 使用锁保护日志输出，确保日志消息的原子性
                    async with _log_lock:
                        logger.debug(f"[{idx}/{total}] 正在处理: {url}")              
                    try:
                        # capture_js_files 内部也有日志输出，在并发模式下需要加锁
                        # 为了性能，我们只对关键的多行日志加锁
                        await self.capture_js_files(url)
                        
                        async with _log_lock:
                            logger.debug(f"\n[{idx}/{total}] 完成: {url}")
                        return {"idx": idx, "url": url, "success": True}
                    except Exception as e:
                        async with _log_lock:
                            logger.debug(f"[{idx}/{total}] 处理失败: {url} - {e}")
                        return {"idx": idx, "url": url, "success": False, "error": str(e)}
                    finally:
                        async with _log_lock:
                            logger.debug("")
            
            # 创建所有任务
            tasks = [process_single_url(idx, url) for idx, url in enumerate(urls, 1)]
            
            # 并发执行所有任务
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
            fail_count = total - success_count
            logger.debug(f"批量处理完成: 成功 {success_count} 个，失败 {fail_count} 个")
        else:
            # 单线程模式（用于调试）
            for idx, url in enumerate(urls, 1):
                logger.debug(f"\n{'=' * 60}")
                logger.debug(f"[{idx}/{total}] 正在处理: {url}")
                logger.debug("=" * 60)
                
                try:
                    await self.capture_js_files(url)
                    logger.info(f"\n[{idx}/{total}] 完成: {url}")
                except Exception as e:
                    logger.error(f"[{idx}/{total}] 处理失败: {url} - {e}")
                


def load_urls_from_file(filename: str = "js_capture_urls.txt") -> List[str]:
    """从文件加载 URL 列表"""
    urls = []
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    urls.append(url)
    return urls


def signal_handler(signum, frame):
    """信号处理函数，直接退出程序"""
    print("\n收到退出信号，程序立即退出")
    sys.exit(0)


async def main():
    """主函数"""
    # 记录开始时间
    program_start_time = time.time()
    
    # 注册信号处理（Windows 和 Unix 都支持）
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(
        description="JS 文件捕获工具 - 批量访问 URL，捕获并下载 JS 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
使用示例:
  # 单线程模式（默认，用于调试）
  python jsCapture.py
  
  # 并发模式，使用默认并发数（{DEFAULT_CONCURRENT}）
  python jsCapture.py --concurrent
  
  # 并发模式，指定并发数（范围：{MIN_CONCURRENT}-{MAX_CONCURRENT}）
  python jsCapture.py --concurrent --max-concurrent 5
  
  # 指定 URL 文件
  python jsCapture.py --urls custom_urls.txt
  
  # 设置日志等级为 DEBUG（显示详细调试信息）
  python jsCapture.py --log-level DEBUG
  
  # 设置日志等级为 WARNING（只显示警告和错误）
  python jsCapture.py --log-level WARNING
  
  # 组合使用：并发模式 + 自定义日志等级
  python jsCapture.py --concurrent --max-concurrent 3 --log-level DEBUG

并发数建议:
  - 低配置系统：1-3
  - 中等配置系统：3-5
  - 高配置系统：5-10
  - 最大限制：{MAX_CONCURRENT}（超过此值可能导致资源耗尽）

日志等级说明:
  - DEBUG: 显示所有详细信息，包括调试信息（最详细）
  - INFO: 显示一般信息，包括进度和结果（默认）
  - WARNING: 只显示警告和错误信息
  - ERROR: 只显示错误信息
  - CRITICAL: 只显示严重错误信息（最少）
        """
    )
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="启用并发模式（默认：单线程模式，用于调试）"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=DEFAULT_CONCURRENT,
        help=f"最大并发数（仅在 --concurrent 模式下有效，范围：{MIN_CONCURRENT}-{MAX_CONCURRENT}，默认：{DEFAULT_CONCURRENT}）"
    )
    parser.add_argument(
        "--urls",
        type=str,
        default="js_capture_urls.txt",
        help="URL 列表文件路径（默认：js_capture_urls.txt）"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志输出等级（默认：INFO）。可选值：DEBUG（详细调试信息）、INFO（一般信息）、WARNING（警告）、ERROR（错误）、CRITICAL（严重错误）"
    )
    
    args = parser.parse_args()
    
    # 根据参数设置日志等级
    setup_logging(args.log_level)
    logger.info(f"日志等级设置为: {args.log_level}")
    
    # 验证并发数范围
    if args.concurrent:
        if args.max_concurrent < MIN_CONCURRENT:
            logger.error(f"错误：并发数 {args.max_concurrent} 小于最小值 {MIN_CONCURRENT}")
            parser.print_help()
            return
        elif args.max_concurrent > MAX_CONCURRENT:
            logger.error(f"错误：并发数 {args.max_concurrent} 超过最大值 {MAX_CONCURRENT}")
            parser.print_help()
            return
    
    tool = JSCaptureTool()
    
    # 从文件加载 URL
    urls = load_urls_from_file(args.urls)
    
    if not urls:
        logger.warning(f"未找到 URL 列表，请创建 {args.urls} 文件并添加 URL")
        return
    
    # 批量处理
    await tool.batch_process(
        urls,
        concurrent=args.concurrent,
        max_concurrent=args.max_concurrent
    )
    
    # 计算并输出总运行时间
    total_time = time.time() - program_start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = int(total_time % 60)
    milliseconds = int((total_time % 1) * 1000)
    
    if hours > 0:
        time_str = f"{hours}小时 {minutes}分钟 {seconds}秒"
    elif minutes > 0:
        time_str = f"{minutes}分钟 {seconds}秒"
    else:
        time_str = f"{seconds}.{milliseconds:03d}秒"
    
    logger.info(f"程序运行完成，总运行时间: {time_str} ({total_time:.3f} 秒)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C 直接退出，不输出额外信息（信号处理函数已处理）
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)

