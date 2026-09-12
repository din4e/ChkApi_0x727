import json
from urllib.parse import urlparse
from traceback import print_exc
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from plugins.nodeCommon import *
except Exception as e:
    from nodeCommon import *


PAGE_TIMEOUT = 30 * 1000            # 页面加载超时
BODY_TIMEOUT = 20 * 1000            # 等待body渲染超时
NETWORK_IDLE_TIMEOUT = 10 * 1000    # 等待网络空闲超时，让SPA页面把XHR/fetch请求发出来
SETTLE_TIME = 2 * 1000              # 页面加载完成后再等待的时间，捕获延迟触发的API请求
CLICK_TIMEOUT = 1500                # 单个元素点击超时
CLICK_WAIT = 500                    # 每次点击后等待API请求发出的时间
MAX_CLICKS_PER_PAGE = 30            # 每个页面最多点击的元素数量
MAX_RESPONSE_SAVE = 2 * 1024 * 1024   # 保存响应体的最大大小
MAX_SOURCE_MAP_SIZE = 10 * 1024 * 1024  # source map的最大大小

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

# 可点击元素选择器：按钮类 + SPA的hash路由链接（a[href^="#"]不会引起整页跳转）
INTERACT_SELECTOR = 'button, [role="button"], [onclick], input[type="button"], input[type="submit"], a[href^="#"]'

# 点击/路由爬取的危险关键词：命中的元素和路径直接跳过，避免触发退出登录、删除数据等操作
# 注：不使用dangerApiList里的短词(del/stop)，"model"之类会误伤过多；宁可漏点不可误点
INTERACT_DANGER_KEYWORDS = [
    'delete', 'remove', 'drop', 'insert', 'update', 'shutdown', 'restart', 'rewrite',
    'terminate', 'deactivate', 'halt', 'disable', 'poweroff',
    'logout', 'loginout', 'signout', 'sign-out', 'exit', 'quit', 'uninstall',
    '注销', '退出', '登出', '删除', '卸载', '重启', '停用',
]

# 同源路由允许的页面后缀（无后缀的SPA路由也允许）
ROUTE_PAGE_EXTS = ('.html', '.htm', '.jsp', '.php', '.asp', '.aspx')


def check_network_url(url):
    if not url or url.count('?') > 1 or not url.startswith('http'):
        return False, ''
    url_parse = urlparse(url)
    path = url_parse.path
    if path.lower().endswith(".js"):
        return 'js', url
    if url.startswith('data'):
        return False, ''
    if '.' not in path.lower().rsplit('/')[-1]:
        return 'no_js', f"{url_parse.scheme}://{url_parse.netloc}{url_parse.path}"
    return False, ''


def is_same_site(a, b):
    """判断两个url是否属于同一个站点（IP则精确匹配netloc，域名则匹配主域）"""
    na, nb = urlparse(a).netloc, urlparse(b).netloc
    if not na or not nb:
        return False
    if is_ip(na.split(':')[0]) or is_ip(nb.split(':')[0]):
        return na == nb
    ea, eb = tldextract.extract(a), tldextract.extract(b)
    return (ea.domain, ea.suffix) == (eb.domain, eb.suffix)


def is_interact_danger(descriptor):
    descriptor = (descriptor or '').lower()
    return any(kw in descriptor for kw in INTERACT_DANGER_KEYWORDS)


def playwrightFind(url, cookies, folder_path=None, deep_pages=0, filePath_url_info=None):
    """
    使用 Playwright 无头浏览器访问 url，抓取：
    1. 页面加载的 js 和 no_js url（和原 webdriverFind 返回结构一致，供后续流程使用）
    2. 页面实际发起的 API 请求（xhr/fetch/websocket），含请求方法、POST体、响应状态和响应体
    3. js 的 source map 探测（js+.map），探测到的map并入js管线参与API路径匹配
    4. folder_path 存在时：HAR全量流量录制；json/xml的API响应体存入response/目录，接入第八步敏感信息扫描

    deep_pages > 0 时开启深度抓取：自动点击页面安全元素 + 爬取最多N个同源页面

    返回:
    tuple: (all_load_url, api_requests)
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger_print_content("[!] 未安装playwright，请执行: pip install playwright && playwright install chromium")
        return [], []

    if folder_path:
        try:
            os.makedirs(f'{folder_path}/response/', exist_ok=True)
        except Exception as e:
            pass

    all_load_url = []
    api_requests = []
    seen_load = set()
    seen_api = set()
    js_urls_seen = []

    def save_browser_response(method, api_url, body):
        # 响应体存入response/目录，第八步的diff/hae/敏感信息扫描会统一处理
        file_name = re.sub(r'[^a-zA-Z0-9\.]', '_', api_url)
        file_path = f'{folder_path}/response/BROWSER_{method}_{file_name}.txt'
        try:
            save_response_to_file(file_path, body)
            if filePath_url_info is not None:
                filePath_url_info[file_path] = api_url
            return file_path
        except Exception as e:
            return ''

    def on_request(request):
        try:
            referer = request.headers.get('referer', '')

            # 抓取页面实际发起的API请求
            if request.resource_type in ('xhr', 'fetch'):
                api_key = (request.method, request.url)
                if api_key not in seen_api:
                    seen_api.add(api_key)
                    post_data = ''
                    try:
                        post_data = (request.post_data or '')[:200]
                    except Exception as e:
                        pass
                    api_requests.append({'url': request.url, 'method': request.method, 'resource_type': request.resource_type, 'referer': referer,
                                         'post_data': post_data, 'status': None, 'content_type': '', 'length': '', 'response_file': ''})
                    print(f"API: {request.method}\t{request.url}")

            url_type, new_url = check_network_url(request.url)
            if url_type:
                load_key = (new_url, url_type)
                if load_key not in seen_load:
                    seen_load.add(load_key)
                    all_load_url.append({'url': new_url.rstrip('/'), 'referer': referer, 'url_type': url_type})
                    print(f"URL: {new_url}\tReferer: {referer}\t{url_type}")
                    if url_type == 'js':
                        js_urls_seen.append(new_url)
        except Exception as e:
            pass

    def on_response(response):
        try:
            req = response.request
            if req.resource_type not in ('xhr', 'fetch'):
                return
            status = response.status
            content_type = response.headers.get('content-type', '')
            length = ''
            body = None
            try:
                content_length = response.headers.get('content-length', '')
                if content_length.isdigit() and int(content_length) > MAX_RESPONSE_SAVE:
                    length = content_length
                else:
                    body = response.text()
                    length = len(body)
            except Exception as e:
                body = None

            # 回填对应API请求的响应信息
            for api in reversed(api_requests):
                if api['url'] == req.url and api['method'] == req.method and api.get('status') is None:
                    api['status'] = status
                    api['content_type'] = content_type
                    api['length'] = length
                    # 真实API响应体落盘，作为未授权访问/敏感信息的直接证据
                    if body and folder_path and status < 400 and ('json' in content_type or 'xml' in content_type):
                        api['response_file'] = save_browser_response(req.method, req.url, body)
                    break
        except Exception as e:
            pass

    def on_websocket(ws):
        try:
            print(f"WS: {ws.url}")
            api_requests.append({'url': ws.url, 'method': 'WS', 'resource_type': 'websocket', 'referer': ws.url,
                                 'post_data': '', 'status': None, 'content_type': '', 'length': '', 'response_file': ''})
        except Exception as e:
            pass

    def auto_interact(page, max_clicks=MAX_CLICKS_PER_PAGE):
        """自动点击页面上的安全元素，触发的API请求由on_request统一捕获"""
        clicked = 0
        try:
            elements = page.query_selector_all(INTERACT_SELECTOR)
        except Exception as e:
            return
        for el in elements:
            if clicked >= max_clicks:
                break
            try:
                descriptor = ' '.join(filter(None, [
                    el.get_attribute('href') or '',
                    el.get_attribute('id') or '',
                    el.get_attribute('class') or '',
                    el.get_attribute('onclick') or '',
                    (el.inner_text() or '')[:40],
                ]))
                if is_interact_danger(descriptor):
                    logger_print_content(f"[跳过危险元素] {descriptor}")
                    continue
                if not el.is_visible():
                    continue
                el.click(timeout=CLICK_TIMEOUT)
                clicked += 1
                page.wait_for_timeout(CLICK_WAIT)
            except Exception as e:
                continue

    def collect_routes(page, base_url):
        """收集同源的可访问路由（a[href]）"""
        routes = []
        try:
            hrefs = page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
        except Exception as e:
            hrefs = []
        for h in hrefs:
            try:
                if not h.startswith('http') or not is_same_site(h, base_url):
                    continue
                h_parse = urlparse(h)
                if h_parse.path in ('', '/') or is_interact_danger(h_parse.path):
                    continue
                last = h_parse.path.rsplit('/', 1)[-1]
                if '.' in last and not last.lower().endswith(ROUTE_PAGE_EXTS):
                    continue
                route = f"{h_parse.scheme}://{h_parse.netloc}{h_parse.path}"
                if route not in routes:
                    routes.append(route)
            except Exception as e:
                continue
        return routes

    def load_page(page, target, settle=True):
        """访问页面并等待请求发出，即使加载失败也保留已捕获的请求"""
        final_url = target
        try:
            response = page.goto(target, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
            if response:
                final_url = response.url
        except Exception as e:
            logger_print_content(f"[!] 页面加载异常，继续收集已发出的请求 {target} {e.args}")

        try:
            page.wait_for_selector('body', timeout=BODY_TIMEOUT if settle else 5000)
        except Exception as e:
            pass
        try:
            page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT)
        except Exception as e:
            pass
        try:
            page.wait_for_timeout(SETTLE_TIME if settle else 1000)
        except Exception as e:
            pass
        return final_url

    def probe_source_maps(context):
        """探测 js 的 source map（js+.map），探测到的map作为js并入管线，原始源码参与API路径匹配"""
        for js_url in list(dict.fromkeys(js_urls_seen)):
            if not js_url.startswith('http'):
                continue
            map_url = f"{js_url}.map"
            load_key = (map_url, 'js')
            if load_key in seen_load:
                continue
            try:
                res = context.request.get(map_url, timeout=10000, fail_on_status_code=False)
                if not res.ok:
                    continue
                content_type = res.headers.get('content-type', '')
                # SPA会把任意路径都返回index.html，必须排除
                if 'html' in content_type:
                    continue
                body = res.text()
                if not body or len(body) > MAX_SOURCE_MAP_SIZE:
                    continue
                seen_load.add(load_key)
                all_load_url.append({'url': map_url, 'referer': js_url, 'url_type': 'js'})
                print(f"[+] source map: {map_url}\t长度:{len(body)}")
            except Exception as e:
                continue

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                ],
            )

            context_kwargs = {
                'ignore_https_errors': True,
                'user_agent': USER_AGENT,
                'viewport': {'width': 1920, 'height': 1080},
            }
            if cookies:
                # 和原CDP setExtraHTTPHeaders行为一致：所有请求都携带Cookie头
                context_kwargs['extra_http_headers'] = {'Cookie': cookies}
            if folder_path:
                # HAR全量流量录制（含请求响应头和体）
                context_kwargs['record_har_path'] = f'{folder_path}/0-浏览器流量.har'
                context_kwargs['record_har_mode'] = 'full'
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.on('request', on_request)
            page.on('response', on_response)
            page.on('websocket', on_websocket)

            final_url = load_page(page, url)
            logger_print_content(f"最终跳转URL: {final_url}")

            # 深度抓取：自动点击 + 同源路由爬取
            if deep_pages > 0:
                auto_interact(page)
                visited = {final_url.rstrip('/'), url.rstrip('/')}
                for route in collect_routes(page, final_url):
                    if len(visited) - 2 >= deep_pages:
                        break
                    if route.rstrip('/') in visited:
                        continue
                    visited.add(route.rstrip('/'))
                    logger_print_content(f"[deep] 访问同源页面 {route}")
                    load_page(page, route, settle=False)
                    auto_interact(page, max_clicks=10)

            # source map 探测
            if folder_path:
                probe_source_maps(context)
        except Exception as e:
            logger_print_content(f"[!] 启动浏览器失败 {url} {e.args}")
        finally:
            # HAR在context关闭时落盘
            if context:
                try:
                    context.close()
                except Exception as e:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception as e:
                    pass

    return all_load_url, api_requests


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'https://www.baidu.com'
    deep = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    load_urls, apis = playwrightFind(target, '', deep_pages=deep)
    print(f"\n=== 加载的js/no_js url {len(load_urls)} 个 ===")
    for _ in load_urls:
        print(_)
    print(f"\n=== 实际调用的API请求 {len(apis)} 个 ===")
    for _ in apis:
        print(f"{_['method']}\t{_['status']}\t{_['url']}\t{_['post_data']}")
