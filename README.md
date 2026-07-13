# VulDB 漏洞提交工具

基于 DrissionPage + Claude Code Skill 的 VulDB 漏洞自动化提交工具。

依赖环境由 SKILL.md 引导 AI 自动初始化，用户只需配置账号并触发关键词即可使用。

---

## 背景

VulDB（vuldb.com）是一个漏洞数据库平台。通过其 Web 界面提交漏洞时，需要经过两道关卡：

1. **Cloudflare Turnstile** — 浏览器端人机验证（JS 挑战 + 指纹检测）
2. **VulDB 登录 + CSRF 保护** — 需要有效账号和每次请求的动态 token

本工具解决了这两个问题：

- 使用 **DrissionPage** 驱动真实 Chromium 浏览器，通过 Turnstile 的 JS 挑战和浏览器指纹检测
- 登录后提取 CSRF token，通过浏览器内 `fetch()` 发送 POST（保证 TLS 指纹与浏览器一致，不会被 Cloudflare 拦截）
- 提交失败时自动从响应中提取新 CSRF token 并重试



## 快速开始

### 1. 部署 Skill

将整个 `vuldb-submit` 目录复制到 Claude Code 的 skills 目录：

| 系统 | 路径 |
|------|------|
| **Windows** | `C:\Users\用户\.claude\skills\vuldb-submit` |
| **Linux** | `~/.claude/skills/vuldb-submit` |
| **macOS** | `~/.claude/skills/vuldb-submit` |

### 2. 配置 VulDB 账号

编辑 `scripts/submit_vuln.py`，修改第 25-26 行：

```python
USERNAME = "你的VulDB账号"
PASSWORD = "你的VulDB密码"
```

仅此两步，部署完成。

### 3. 触发关键词

在 Claude Code 中输入：

```
/vuldb-submit
```

AI 会自动读取 SKILL.md，检查并初始化依赖环境，然后引导你完成漏洞提交。

---

## 成功案例

Linux下提交

![1](Screenshot\1.png)

![2](Screenshot\2.jpg)

Windows下提交

![3](Screenshot\3.png)

![4](Screenshot\4.jpg)

## 使用流程

```
用户: /vuldb-submit
  ↓
AI:  请输入漏洞报告文件路径（txt / md / pdf）
  ↓
用户: C:\reports\sql-injection.txt
  ↓
AI:  读取文件 → 提取字段 → 表格回显

      | 字段    | 内容                    |
      |---------|------------------------|
      | vendor  | ExampleCorp             |
      | product | ExampleApp              |
      | version | 1.0.0                   |
      | class   | SQL Injection           |
      | desc    | A SQL injection vuln... |
      | link    | https://example.com     |

      是否确认提交？（确认 / 修改 / 取消）
  ↓
用户: 确认
  ↓
AI:  ✅ 漏洞提交成功！
```

中途可随时输入 `修改 vendor=xxx` 调整字段，或 `取消` 终止。

### 命令行模式（跳过 AI 交互）

```bash
# Windows
.venv\Scripts\python scripts\submit_vuln.py --file data.json

# Linux
xvfb-run --auto-servernum .venv/bin/python scripts/submit_vuln.py --json '{"vendor":"...",...}'
```

---

## 技术架构

```
┌─ Claude Code 交互层 ──────────────────────────────┐
│  /vuldb-submit → AI 读取 SKILL.md → 引导用户        │
│  读取报告文件 → 提取字段 → 确认 → 调用脚本           │
└──────────────────────┬────────────────────────────┘
                       ↓
┌─ 提交引擎 (submit_vuln.py) ───────────────────────┐
│                                                     │
│  ① DrissionPage 启动 Chromium                      │
│     └─ 真实浏览器 TLS 指纹 → Cloudflare 自动通过     │
│                                                     │
│  ② 登录 VulDB                                      │
│     ├─ wait_cf() 等待 Turnstile 挑战完成             │
│     └─ 填写 user/password → 点击 Login              │
│                                                     │
│  ③ GET /vuln/add → 提取 CSRF token                  │
│                                                     │
│  ④ 浏览器内 JS fetch() POST                         │
│     └─ 利用浏览器 TLS 连接 → CF 不拦截              │
│                                                     │
│  ⑤ 响应分析 + 自动重试                              │
│     ├─ "Thank you for submitting" → 成功            │
│     ├─ "We need more details" → 描述太短            │
│     ├─ "duplicate" → 可能重复                       │
│     └─ 新 CSRF token → 刷新重试（最多3次）           │
└─────────────────────────────────────────────────────┘
```

### 为什么这个方案能绕过 Cloudflare

VulDB 使用 **Cloudflare Turnstile** 进行人机验证。经过实测对比：

| 方案                              | 结果                                                 |
| --------------------------------- | ---------------------------------------------------- |
| `requests`                        | ❌ 403 — Cloudflare Turnstile 拦截                    |
| `cloudscraper`                    | ❌ 403 — 只支持旧版 IUAM 挑战，不支持 Turnstile       |
| `curl_cffi`（TLS 指纹伪装）       | GET 有时可通过，POST 仍被 403 — Turnstile 验证更严格 |
| `playwright` headless             | ❌ headless 模式被检测，非 headless 仍需手动交互      |
| **DrissionPage + 浏览器内 fetch** | ✅ 真实浏览器 TLS + JS 环境，Turnstile 自动通过       |

核心原理：Turnstile 对每个 HTTP 连接做 TLS 指纹校验。`requests`/`curl_cffi` 发起的 POST 与浏览器 GET 的 TLS 指纹不同，Cloudflare 会再次拦截 POST 请求。

本工具通过 `tab.run_js(fetch(...))` 在浏览器 JS 上下文内发起 POST——请求复用浏览器的 TLS 连接、cookie 存储和 HTTP 栈，Cloudflare 看到的是同一个浏览器的后续请求，不会二次挑战。

---

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `vendor` | ✅ | 厂商名称 |
| `product` | ✅ | 产品名称 |
| `version` | ✅ | 受影响版本 |
| `class` | ✅ | 漏洞类型（SQL Injection / XSS / RCE 等） |
| `desc` | ✅ | 详细描述（技术细节 + 影响范围，建议 150 字符以上） |
| `link` | ❌ | 参考链接 / Advisory URL |

---

## 脚本配置项

`scripts/submit_vuln.py` 中可修改的配置：

```python
# VulDB 账号（必改）
USERNAME = ""
PASSWORD = ""

# 提交重试次数
max_retries = 3   # 在 submit_with_retry() 函数参数中

# Cloudflare 等待超时
timeout = 90      # 在 wait_cf() 函数参数中
```

---

## 常见问题

### Q: 运行报错 "Missing X server or $DISPLAY"

需要安装 xvfb 并用 `xvfb-run` 包装：

```bash
sudo apt install -y xvfb
xvfb-run --auto-servernum .venv/bin/python scripts/submit_vuln.py ...
```

### Q: 运行报错 "浏览器连接失败"

DrissionPage 无法启动 Chromium。检查：

1. 是否已安装 Chromium：`which chromium`
2. 如未安装：`sudo apt install -y chromium` 或 `python -m playwright install chromium`
3. 是否有 `--no-sandbox` 参数（Docker/root 环境需要）

### Q: 长时间卡在 "Cloudflare 验证中..."

Cloudflare 可能在你的 IP 上触发了更严格的验证。尝试：

1. 等待 1-2 分钟后重试
2. 更换网络/IP
3. 使用代理（编辑脚本中的 `PROXY` 变量）

### Q: "We need more details" — 描述被拒绝

VulDB 要求更详细的技术描述。扩充 `desc` 字段内容即可。

### Q: "可能重复" — 被判定重复

相同的 `vendor + product + version` 组合可能已有待审记录。更换参数。

### Q: 401 Unauthorized

会话过期，需要重新登录或者未认证

### Q:长时间卡在 Cloudflare

等待 1-2 分钟，或更换网络

### Q: 如何调试？

在脚本中的关键位置添加打印语句，或使用 DrissionPage 的截图功能：

```python
tab.screenshot(path="/tmp/debug.png")  # ChromiumPage 可用
```

---

## 项目结构

vuldb-submit/
├── README.md                  # 本文件 — 用户部署指南和技术文档
├── SKILL.md                        # Skill 定义 — AI 操作手册，含依赖初始化流程
├── scripts/
│   └── submit_vuln.py        # 核心提交脚本
├── .vuldb_cookies.json      # （运行时生成）浏览器 cookie 缓存
└── .venv/                              # Python 虚拟依赖环境（AI加载skill时自动初始化生成）

## 许可证

本项目仅供学习研究使用，禁止通过滥用或二次修改对VulDB 平台造成任何不良影响，相关风险由使用者自行承担，请遵守 VulDB 平台的使用条款。

