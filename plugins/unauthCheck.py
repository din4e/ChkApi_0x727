try:
    from plugins.nodeCommon import *
except Exception as e:
    from nodeCommon import *


# 无认证响应中的鉴权失败标记（HTTP状态码200但业务码拒绝的常见返回），命中则判定为已拦截
# 注意：只在"响应不完全一致"时才生效，避免误杀本身就含token字段的真实数据
AUTH_DENY_MARKERS = [
    'unauthorized', 'forbidden', 'access denied', 'login required', 'not login', 'need login',
    'not logged', 'please login', 'token invalid', 'invalid token', 'token expired', '身份过期',
    '请先登录', '未登录', '没有登录', '登录失效', '登录过期', '重新登录', '请登录',
    '身份验证失败', '鉴权失败', '认证失败', '无权限', '权限不足', '未授权',
]


def normalize_api_url(url):
    """去掉查询串和锚点，返回 scheme://netloc/path，用于跨来源比对"""
    try:
        url_parse = urlparse(url)
        if not url_parse.scheme or not url_parse.netloc:
            return ''
        return f"{url_parse.scheme}://{url_parse.netloc}{url_parse.path}".rstrip('/')
    except Exception as e:
        return ''


def load_json_loose(text):
    try:
        return json.loads(text)
    except Exception as e:
        try:
            return eval(text)
        except Exception as e:
            return None


def _is_denied(text):
    lower = text.lower()
    return any(marker in lower for marker in AUTH_DENY_MARKERS)


def _is_json_or_xml(content_type):
    content_type = (content_type or '').lower()
    return 'json' in content_type or 'xml' in content_type


def _has_data_value(obj):
    """判断JSON响应里是否携带真实数据（数据类字段或非状态码字段非空）"""
    if not isinstance(obj, dict):
        return True
    data_keys = [k for k in ('data', 'rows', 'list', 'records', 'result', 'items') if k in obj]
    if data_keys:
        return any(obj[k] not in ([], {}, '', None, 0) for k in data_keys)
    return any(v not in ([], {}, '', None, 0) for k, v in obj.items() if k not in ('code', 'status', 'msg', 'message', 'success'))


def compare_response(auth_text, unauth_text):
    """
    比较带认证和无认证的响应，返回 (判定, 说明)
    判定: 确认 / 疑似 / 拦截 / 差异
    """
    auth_text = (auth_text or '').strip()
    unauth_text = (unauth_text or '').strip()
    if not auth_text or not unauth_text:
        return '差异', ''

    auth_json, unauth_json = load_json_loose(auth_text), load_json_loose(unauth_text)

    # 1. 完全一致：最强证据。真实数据里可能本来就含token字段，先于鉴权标记判断
    if auth_text == unauth_text:
        # 两侧是同一个鉴权失败壳（如都不带cookie时看到的同一条"请先登录"）
        if _is_denied(unauth_text):
            return '拦截', '两侧响应为相同的鉴权失败信息'
        # 两侧都是空数据（如未登录视角的空列表），没有数据价值
        if isinstance(unauth_json, dict) and not _has_data_value(unauth_json):
            return '拦截', '响应内容一致但数据为空'
        return '确认', '响应内容完全一致'

    # 2. 无认证响应是鉴权失败信息（HTTP 200 + 业务码拒绝），排除误报
    if _is_denied(unauth_text):
        return '拦截', '无认证响应为鉴权失败信息'

    # 3/4. JSON结构比对
    if isinstance(auth_json, dict) and isinstance(unauth_json, dict):
        auth_keys, unauth_keys = set(auth_json.keys()), set(unauth_json.keys())
        if auth_keys and auth_keys == unauth_keys:
            same = sum(1 for k in auth_keys if auth_json.get(k) == unauth_json.get(k))
            if same >= len(auth_keys) * 0.8:
                # 结构一致但无认证侧没有真实数据（如空列表）
                if not _has_data_value(unauth_json):
                    return '拦截', 'JSON键值一致但无认证侧数据为空'
                return '确认', f'JSON键一致且{same}/{len(auth_keys)}个字段值相同'
            return '疑似', f'JSON键一致但仅{same}/{len(auth_keys)}个字段值相同'
        # 无认证响应是错误壳结构（如code+msg），带认证是数据结构
        return '差异', ''

    # 5. 非JSON文本，按长度相似度粗判
    if auth_text and unauth_text:
        ratio = len(unauth_text) / max(len(auth_text), 1)
        if 0.9 <= ratio <= 1.1:
            return '疑似', f'非JSON响应但长度相近({len(auth_text)}B/{len(unauth_text)}B)'
    return '差异', ''


def replay_unauth(api_url):
    """
    无认证重放：不带Cookie请求API，GET优先，失败再POST空JSON
    返回 (响应文本, 方式) 或 ('', '')
    """
    # 复制全局headers并剔除Cookie（第五步会把Cookie写进全局headers）
    req_headers = dict(headers)
    req_headers.pop('Cookie', None)

    try:
        res = requests.get(url=api_url, headers=req_headers, timeout=TIMEOUT, verify=False, allow_redirects=False)
        if res.status_code == 200 and _is_json_or_xml(res.headers.get('Content-Type')):
            return res.text, 'GET'
    except Exception as e:
        pass

    try:
        req_headers['Content-Type'] = 'application/json'
        res = requests.post(url=api_url, json={}, headers=req_headers, timeout=TIMEOUT, verify=False, allow_redirects=False)
        if res.status_code == 200 and _is_json_or_xml(res.headers.get('Content-Type')):
            return res.text, 'POST_JSON'
    except Exception as e:
        pass

    return '', ''


def unauthCheck_api(referer_url, browser_api_requests, folder_path, cookies):
    """
    第八步：未授权访问对比检测
    对浏览器带认证抓到的真实API，剔除Cookie做无认证重放，比对两侧响应，
    命中即为未授权访问的直接证据。

    仅在携带cookies时执行：无登录态时浏览器和重放都是匿名视角，对比无意义。
    """
    findings = []
    if not cookies or not browser_api_requests:
        return findings

    seen = set()
    for b in browser_api_requests:
        try:
            if b.get('resource_type') not in ('xhr', 'fetch'):
                continue
            # 只对比带认证侧已落盘的200 json/xml响应
            if not b.get('response_file') or not os.path.exists(b['response_file']):
                continue
            api_url = normalize_api_url(b['url'])
            if not api_url or api_url in seen:
                continue
            seen.add(api_url)

            # 危险API不重放（退出/删除类）
            if any(dangerApi in urlparse(api_url).path.lower() for dangerApi in dangerApiList):
                logger_print_content(f"[unauth跳过危险API] {api_url}")
                continue

            with open(b['response_file'], 'rt', encoding='utf-8') as f:
                auth_text = f.read()

            unauth_text, replay_way = replay_unauth(api_url)
            if not unauth_text:
                continue

            verdict, detail = compare_response(auth_text, unauth_text)
            if verdict in ('确认', '疑似'):
                # 无认证响应落盘留证
                file_name = re.sub(r'[^a-zA-Z0-9\.]', '_', api_url)
                unauth_file = f'{folder_path}/response/UNAUTH_{replay_way}_{file_name}.txt'
                try:
                    with open(unauth_file, 'at', encoding='utf-8') as f:
                        f.writelines(f"{unauth_text}\n")
                except Exception as e:
                    unauth_file = ''

                finding = {
                    'url': b['url'],
                    'method': b['method'],
                    'verdict': verdict,
                    'detail': detail,
                    'auth': f"{b.get('status')} {str(b.get('content_type', '')).split(';')[0]} {b.get('length', '')}B",
                    'unauth': f"200 {replay_way}重放(无Cookie) {len(unauth_text)}B",
                    'auth_file': b['response_file'],
                    'unauth_file': unauth_file,
                }
                findings.append(finding)
                print(f"[未授权访问-{verdict}] {b['method']}\t{b['url']}")
                print(f"    带认证: {finding['auth']}")
                print(f"    无认证: {finding['unauth']}")
                print(f"    {detail}")
        except Exception as e:
            continue

    # 结果落盘
    try:
        with open(f'{folder_path}/9-未授权访问检测结果.txt', 'at', encoding='utf-8') as f:
            if not findings:
                f.writelines("未发现可确认的未授权访问\n")
            for _ in findings:
                f.writelines(f"[未授权访问-{_['verdict']}] {_['method']}\t{_['url']}\n")
                f.writelines(f"    带认证: {_['auth']}\n    无认证: {_['unauth']}\n    {_['detail']}\n\n")
    except Exception as e:
        pass

    return findings
