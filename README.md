# ChkApiPlus - API安全检测自动化工具

集成精简版，调用执行输出API资产。

## 工具说明

本项目包含两个独立工具，功能互不干扰：

1. **ChkApi** - API安全检测自动化工具（主工具）
2. **JS Capture Tool** - JS文件捕获工具（独立工具，位于 `tools/` 目录）

### JS Capture Tool

JS文件捕获工具用于批量访问URL，捕获并下载JS文件，检测IP地址。详细使用说明请参考 [tools/README_JS_CAPTURE.md](tools/README_JS_CAPTURE.md)。

快速使用：
```bash
python tools/jsCapture.py
```

## ChkApi 调用

1. cmd 调用
```python
python3 ChkApi.py -u "http://example.com"
```
2. 内嵌代码调用
```python
...
run_url(url, cookies, chrome, attackType, noApiScan)
# run_url(url, "", "on", 0, 0)
...
```

主要关注安全和危险的API接口。

## 0x02 安装

为了避免踩坑,建议安装在如下环境中

* python3.8及以上，建议VPS环境是ubuntu20，默认是python3.8。
* 需要安装 Playwright 及其 Chromium 浏览器，build.sh 里内置了安装命令（Mac/Windows 手动执行 `playwright install chromium` 即可）

```
chmod 777 build.sh
./build.sh
```

` python3 ChkApi.py -h`

## 0x03 使用方法 

| 语法                                                    | 功能                                       |
| :------------------------------------------------------ | :----------------------------------------- |
| python3 ChkApi.py -u http://www.aaa.com                 | 对单一url进行扫描                          |
| python3 ChkApi.py -u http://www.aaa.com -c "xxxxxxxxxx" | 携带cookies对单一url进行扫描               |
| python3 ChkApi.py -f url.txt                            | 对文件里的网站进行扫描                     |
| python3 ChkApi.py -u http://www.aaa.com --chrome off    | off关闭Playwright无头浏览器，默认是on      |
| python3 ChkApi.py -u http://www.aaa.com --at 1          | 0 收集+探测、1 收集， 默认是0              |
| python3 ChkApi.py -u http://www.aaa.com --na 1          | 不扫描API接口漏洞，1不扫描，0扫描，默认是0 |
| python3 ChkApi.py -u http://www.aaa.com --dp 5          | 深度抓取：自动点击页面元素并爬取最多5个同源页面抓取API，默认0不开启 |

## 工作原理

自动提取目标网站的 JS 文件和 API 接口，通过正则匹配和智能参数提取技术，全面发现安全风险。

### 浏览器抓取能力（Playwright）

无头浏览器访问目标时，除被动收集 js/no_js URL 外，还默认开启：

- **真实 API 调用捕获**：记录页面实际发出的 xhr/fetch/websocket 请求（方法、完整URL、POST体、响应状态/类型/长度），保存到 `0-浏览器实际调用的API请求列表.txt`
- **API 响应体落盘**：200 的 json/xml 响应存入 `response/` 目录，自动接入第八步的 HAE 规则/敏感信息扫描，直接发现未授权访问和数据泄露
- **source map 探测**：自动请求 JS 文件对应的 `.map`，探测成功则原始源码参与 API 路径匹配，覆盖 webpack 打包站点
- **HAR 全量流量录制**：保存到 `0-浏览器流量.har`，可用 Burp/Curl 等工具直接导入分析

`--dp N` 深度模式额外开启（注意会主动产生点击和访问行为）：

- **自动交互**：点击页面上的按钮/提交类元素触发隐藏 API，危险元素（退出/删除/注销等关键词）自动跳过
- **同源路由爬取**：从 `a[href]` 收集同源页面并逐个访问抓取，覆盖多页面站点的 API

### 输出结果

扫描结果以文本文件（txt）和电子表格（Excel）格式保存，包括：

- **API接口列表** - 所有发现的API接口及其请求方法
- **敏感信息** - 自动识别的敏感数据（JDBC连接、账号密码、私钥、云平台AKSK等）
- **响应结果** - 每个接口的响应状态码、内容长度等
- **参数列表** - 从响应中智能提取的参数名

**漏洞分析建议**：

通过分析输出结果可以发现大量 Web 漏洞：
- **RCE漏洞**：在api_url和parameter字段模糊匹配ping、cmd、command等关键词
- **URL跳转/SSRF漏洞**：模糊匹配url、ip等关键词
- **任意文件上传/读取漏洞**：模糊匹配upload、download、read、file等关键词
- **未授权访问漏洞**：模糊匹配get、config等关键词 

## 反馈

ChkApi 是一个免费且开源的项目，我们欢迎任何人为其开发和进步贡献力量。

* 在使用过程中出现任何问题，可以通过 issues 来反馈。
* Bug 的修复可以直接提交 Pull Request 到 dev 分支。
* 如果是增加新的功能特性，请先创建一个 issue 并做简单描述以及大致的实现方法，提议被采纳后，就可以创建一个实现新特性的 Pull Request。
* 欢迎对说明文档做出改善，帮助更多的人使用 ChkApi。
* 贡献代码请提交 PR 至 dev 分支，master 分支仅用于发布稳定可用版本。

*提醒：和项目相关的问题最好在 issues 中反馈，这样方便其他有类似问题的人可以快速查找解决方法，并且也避免了我们重复回答一些问题。*

## 声明

郑重声明：文中所涉及的技术、思路和工具仅供以安全检测、安全辅助建设为目的的学习交流使用，任何人不得将其用于非法用途以及盈利等目的，否则后果自行承担。

## 致谢

+ [Ske](https://github.com/SkewwG) && Chhyx 
+ [0x727](https://github.com/0x727)
+ [ttstormxx/jjjjjjjjjjjjjs](https://github.com/ttstormxx/jjjjjjjjjjjjjs)
+ [HaE](https://gh0st.cn/HaE/)
+ [wih](https://tophanttechnology.github.io/ARL-doc/function_desc/web_info_hunter/)
  