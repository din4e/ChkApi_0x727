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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置
TIMEOUT = 10000  # 10秒超时
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
CACHE_DIR.mkdir(exist_ok=True)


class IPDetector:
    """IP 地址检测器"""
    
    # 内网 IP 段
    INTERNAL_IP_PATTERNS = [
        r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}',
        r'172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}',
        r'192\.168\.\d{1,3}\.\d{1,3}',
        r'127\.\d{1,3}\.\d{1,3}\.\d{1,3}',
        r'0\.0\.0\.0',
        r'localhost',
    ]
    
    @staticmethod
    def is_internal_ip(ip: str) -> bool:
        """判断是否为内网 IP"""
        for pattern in IPDetector.INTERNAL_IP_PATTERNS:
            if re.match(pattern, ip):
                return True
        return False
    
    @staticmethod
    def detect_ips(text: str, max_context: int = 50) -> List[Dict]:
        """检测文本中的 IP 地址"""
        # IP 地址正则表达式
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips_found = []
        seen_ips = set()
        
        for match in re.finditer(ip_pattern, text):
            ip = match.group()
            if ip in seen_ips:
                continue
            seen_ips.add(ip)
            
            # 验证是否为有效 IP
            parts = ip.split('.')
            if not all(0 <= int(p) <= 255 for p in parts):
                continue
            
            # 获取上下文
            start = max(0, match.start() - max_context)
            end = min(len(text), match.end() + max_context)
            context = text[start:end].replace('\n', ' ').replace('\r', ' ')
            
            is_internal = IPDetector.is_internal_ip(ip)
            ip_type = "内网 IP" if is_internal else "公网 IP"
            
            ips_found.append({
                "ip": ip,
                "type": ip_type,
                "is_internal": is_internal,
                "context": context
            })
        
        return ips_found


class JSCaptureTool:
    """JS 文件捕获工具"""
    
    def __init__(self):
        self.cache = {}  # URL -> MD5 缓存
        self.cache_hits = 0
        self.cache_misses = 0
        
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
                        logger.info(f"[+] 缓存命中 {filename} (MD5: {file_hash[:12]}...) - {url}")
                        self.cache_hits += 1
                    else:
                        logger.info(f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) - {url}")
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
        
        logger.info(f"文件将保存到: {save_dir}")
        
        js_files = []
        map_files = []
        other_files = []
        error_msg = None
        
        async with async_playwright() as p:
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
                logger.info(f"正在访问: {url}")
                try:
                    response = await page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                    if response:
                        final_url = response.url
                except PlaywrightTimeoutError:
                    error_msg = f"页面加载超时 ({TIMEOUT//1000}秒): Page.goto: Timeout {TIMEOUT}ms exceeded.\nCall log:\n  - navigating to \"{url}\", waiting until \"networkidle\"\n"
                    logger.warning(error_msg)
                except Exception as e:
                    error_msg = f"访问页面时出错: {str(e)}"
                    logger.error(error_msg)
                
                # 等待一下确保所有资源加载完成
                await asyncio.sleep(2)
                
                # 获取页面 HTML 内容
                try:
                    html_content = await page.content()
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
                    logger.info(f"[+] 已下载: {html_filename} ({len(html_content)} bytes, MD5: {self.get_file_hash(html_content.encode('utf-8'))[:12]}...)  - {url}")
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
                    if self.is_webpack_file(filename):
                        file_info["is_webpack"] = True
                    
                    # 检测 IP 地址（仅对 JS 文件）
                    if filename.endswith('.js'):
                        try:
                            text_content = content.decode('utf-8', errors='ignore')
                            # 大文件可能包含 IP 但未完全检测到
                            if len(content) > 100000:
                                logger.warning(f"[!] 文件 {filename} 很大，可能包含 IP 但未完全检测到")
                            
                            ips = IPDetector.detect_ips(text_content)
                            if ips:
                                file_info["ips"] = ips
                                for ip_info in ips:
                                    logger.info(f"  └─ 文件内容包含 IP:")
                                    logger.info(f"     {ip_info['type']}: {ip_info['ip']}")
                                    logger.info(f"     [{ip_info['ip']}] 上下文: {ip_info['context']}")
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
                    logger.info(f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) [Webpack] [JS] - {url}" if file_info.get("is_webpack") else f"[+] 已下载: {filename} ({len(content)} bytes, MD5: {file_hash}) [JS] - {url}")
                
                # 尝试下载 .map 文件
                logger.info(f"\n检测到 {len(js_files)} 个 JS 文件，尝试访问对应的 .map 文件...")
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
                
                await browser.close()
                
            except Exception as e:
                error_msg = f"处理 URL 时出错: {str(e)}"
                logger.error(error_msg)
        
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
        
        logger.info(f"文件列表已保存到: {json_path}")
        logger.info(f"捕获完成!")
        logger.info(f"JS 文件数量: {len(js_files)}")
        logger.info(f"JS.map 文件数量: {len(map_files)}")
        logger.info(f"其他文件数量: {len(other_files)}")
        logger.info(f"运行时间: {result['run_time']} 秒")
        logger.info(f"缓存统计: 命中 {self.cache_hits} 次，未命中 {self.cache_misses} 次")
        if self.cache_hits > 0:
            logger.info(f"  (通过缓存复用了 {self.cache_hits} 个页面的分析结果，节省了分析时间)")
        logger.info(f"文件已保存到: {save_dir}")
        
        return result
    
    async def batch_process(self, urls: List[str]):
        """批量处理 URL"""
        total = len(urls)
        logger.info(f"\n开始批量处理 {total} 个 URL")
        logger.info("=" * 60)
        
        for idx, url in enumerate(urls, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"[{idx}/{total}] 正在处理: {url}")
            logger.info("=" * 60)
            
            try:
                await self.capture_js_files(url)
                logger.info(f"\n[{idx}/{total}] 完成: {url}")
            except Exception as e:
                logger.error(f"[{idx}/{total}] 处理失败: {url} - {e}")
            
            logger.info("")


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


async def main():
    """主函数"""
    tool = JSCaptureTool()
    
    # 从文件加载 URL
    urls = load_urls_from_file("js_capture_urls.txt")
    
    if not urls:
        logger.warning("未找到 URL 列表，请创建 js_capture_urls.txt 文件并添加 URL")
        return
    
    # 批量处理
    await tool.batch_process(urls)


if __name__ == "__main__":
    asyncio.run(main())

