#!/usr/bin/env python3
r"""
提交漏洞到 VulDB（DrissionPage + 浏览器内 fetch POST）

策略：Chromium 浏览器过 Cloudflare + 登录，然后用 JS fetch()
在浏览器上下文内发 POST（保证 TLS 指纹一致）。

用法（Linux）：
    xvfb-run --auto-servernum .venv/bin/python submit_vuln.py --json '{"vendor":"...",...}'

用法（Windows/macOS）：
    .venv\Scripts\python submit_vuln.py --json '{"vendor":"...",...}'
"""

import sys
import json
import time
import argparse
import platform
import io


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from DrissionPage import ChromiumOptions, Chromium
from bs4 import BeautifulSoup

BASE_URL = "https://vuldb.com"
LOGIN_URL = f"{BASE_URL}/login"
VULN_ADD_URL = f"{BASE_URL}/vuln/add"

USERNAME = ""
PASSWORD = ""


def create_browser():
    co = ChromiumOptions()

    # 自动检测浏览器路径
    import os
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in edge_paths + chrome_paths:
        if os.path.exists(p):
            co.set_browser_path(p)
            break

    co.set_argument('--disable-blink-features=AutomationControlled')

    # Linux 无 GUI 环境需要这些参数
    if platform.system() == "Linux":
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')

    # headless=False: 显示浏览器窗口
    #   Linux   → 需要 xvfb-run 包装（无 X Server）
    #   Windows → 正常显示窗口，无需额外工具
    #   macOS   → 正常显示窗口
    co.headless(False)
    return Chromium(co)


def wait_cf(tab, timeout=90):
    cf_titles = ["just a moment", "security check", "attention required"]
    for _ in range(timeout // 2):
        try:
            t = tab.title.lower()
        except Exception:
            time.sleep(2); continue
        if t and not any(x in t for x in cf_titles):
            return True
        time.sleep(2)
    return False


def do_login(tab):
    """登录（如已登录则跳过）"""
    print(f"[*] 访问登录页")
    tab.get(LOGIN_URL, timeout=60)
    wait_cf(tab)

    user_el = tab.ele('tag:input@name=user', timeout=3)
    if user_el:
        print("[+] 登录中...")
        user_el.input(USERNAME)
        tab.ele('tag:input@name=password').input(PASSWORD)
        btn = tab.ele('tag:input@value=Login')
        if btn: btn.click(by_js=True)
        time.sleep(5)
        tab.wait.doc_loaded()
    else:
        print(f"[+] 已登录")
    print(f"[+] 当前: {tab.title}")


def get_csrf_token(tab):
    """GET 提交页拿 CSRF token 和表单"""
    print(f"[*] GET {VULN_ADD_URL}")
    tab.get(VULN_ADD_URL, timeout=30)
    time.sleep(2)
    for _ in range(15):
        time.sleep(1)
        if '401' not in tab.title.lower():
            csrf = tab.ele('tag:input@name=csrftoken', timeout=1)
            if csrf: break

    csrf_el = tab.ele('tag:input@name=csrftoken', timeout=10)
    if not csrf_el:
        raise Exception("未找到 CSRF token")
    return csrf_el.attr('value')


def submit_via_browser_fetch(tab, data, csrf_token):
    """通过浏览器 JS fetch() 发 POST（CF 认可的 TLS 指纹）"""
    # 用 json.dumps 安全传递数据给 JS，避免特殊字符注入
    data_js = json.dumps({
        "vendor": data.get("vendor", ""),
        "product": data.get("product", ""),
        "version": data.get("version", ""),
        "class": data.get("class", ""),
        "desc": data.get("desc", ""),
        "link": data.get("link", ""),
        "reqcve": "1",
        "csrftoken": csrf_token,
    })

    js = f"""
        var data = {data_js};
        var body = new URLSearchParams(data).toString();
        return fetch('{VULN_ADD_URL}', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': '{VULN_ADD_URL}',
                'Origin': '{BASE_URL}',
            }},
            body: body,
            redirect: 'follow',
        }}).then(r => r.text());
    """

    print(f"[*] 浏览器内 fetch POST...")
    try:
        result = tab.run_js(js)
        return result if result else ""
    except Exception as e:
        print(f"[!] JS fetch 异常: {e}")
        return ""


def submit_with_retry(browser, data, max_retries=3):
    tab = browser.latest_tab

    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*40}")
        print(f"[*] 第 {attempt} 次提交尝试")

        csrf_token = get_csrf_token(tab)
        print(f"[*] CSRF token: {csrf_token[:20]}...")

        html = submit_via_browser_fetch(tab, data, csrf_token)
        print(f"[*] 响应长度: {len(html)}")

        if "Thank you for submitting" in html:
            print("\n✅ 漏洞提交成功！")
            return True

        # 分析响应
        soup = BeautifulSoup(html, "html.parser")

        # 检查是否是内容质量问题（不应重试）
        body_text = soup.body.get_text() if soup.body else ""
        if "We need more details" in body_text:
            print("\n⚠️ VulDB 拒绝了提交：描述不够详细，请扩充技术细节。")
            print("   （这不是脚本问题，是漏洞报告内容需要更丰富）")
            return False
        if "duplicate" in body_text.lower() or "already exists" in body_text.lower():
            print("\n⚠️ VulDB 提示可能重复。")
            return False

        # 提取新 CSRF token（提交被拒回显表单时）
        new_csrf_el = soup.find("input", {"name": "csrftoken"})
        new_token = new_csrf_el.get("value") if new_csrf_el else None

        if new_token:
            print(f"[*] CSRF 已刷新，重试...")
            time.sleep(2)
            continue

        if attempt >= max_retries:
            print("\n⚠️ 多次提交未确认成功。")
            return False

    return False


def main():
    parser = argparse.ArgumentParser(description="提交漏洞到 VulDB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--json', help='JSON 字符串')
    group.add_argument('--file', help='JSON 文件路径')
    args = parser.parse_args()

    if args.json:
        data = json.loads(args.json)
    else:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)

    for field in ['vendor', 'product', 'version', 'class', 'desc']:
        if not data.get(field):
            print(f"错误: 缺少必要字段 '{field}'", file=sys.stderr)
            sys.exit(1)

    print("[*] 启动浏览器...")
    browser = create_browser()
    tab = browser.latest_tab

    try:
        do_login(tab)
        submit_with_retry(browser, data)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
