---
name: vuldb-submit
description: "提交漏洞到 VulDB，自动从报告文件中提取信息并交互式确认"
version: 1.0.0
author: GeekerA
---

# VulDB 漏洞提交技能

## 描述

此技能可帮助你快速将漏洞报告提交到 VulDB 平台（https://vuldb.com）。

它会读取你指定的漏洞报告文件（支持 txt、md、pdf 等文本格式），利用 AI 提取关键信息，
填充到提交表单中，并回显供你确认，确认后才会实际提交。

提交引擎基于 DrissionPage 驱动真实浏览器，自动绕过 Cloudflare Turnstile 人机验证。

---

## 首次使用 — 环境初始化

AI 在首次执行提交前，需要检查并安装依赖环境。按以下步骤操作：

### 第一步：检查 Python 版本

```bash
python3 --version
```
要求 Python 3.8+，如不满足请先升级。

### 第二步：创建虚拟环境并安装依赖

```bash
cd /path/to/vuldb-submit
python3 -m venv .venv
```

激活虚拟环境：

| 系统 | 命令 |
|------|------|
| Linux / macOS | `source .venv/bin/activate` |
| Windows | `.venv\Scripts\activate` |

安装 Python 依赖：

```bash
pip install DrissionPage beautifulsoup4
```

如果安装极慢（中国网络环境），可通过镜像源加速：
```bash
pip install DrissionPage beautifulsoup4 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第三步：检查/安装 Chromium 浏览器

DrissionPage 会自动查找系统中的 Chrome/Edge/Chromium。如果系统中没有，安装方式：

| 系统 | 安装命令 |
|------|----------|
| **Linux (Debian/Kali)** | `sudo apt install -y chromium` |
| **Linux (CentOS/RHEL)** | `sudo yum install -y chromium` |
| **Windows** | 通常已安装 Chrome/Edge，无需额外操作 |
| **macOS** | 通常已安装 Chrome，无需额外操作 |

或者通过 Playwright 安装 Chromium（所有平台通用）：
```bash
pip install playwright
python -m playwright install chromium
```

### 第四步：检查/安装 xvfb（仅 Linux 无 GUI 环境需要）

```bash
# Debian/Kali
sudo apt install -y xvfb

# CentOS/RHEL
sudo yum install -y xorg-x11-server-Xvfb
```

Windows 和 macOS 不需要 xvfb，直接运行即可。

### 第五步：配置 VulDB 账号

编辑 `scripts/submit_vuln.py`，修改以下两行：

```python
USERNAME = "你的VulDB账号"
PASSWORD = "你的VulDB密码"
```

### 环境验证

运行以下命令测试环境是否就绪：

```bash
# Linux 无 GUI
xvfb-run --auto-servernum .venv/bin/python -c "from DrissionPage import ChromiumOptions,Chromium;print('OK')"

# Windows / macOS
.venv\Scripts\python -c "from DrissionPage import ChromiumOptions,Chromium;print('OK')"
```

输出 `OK` 即表示环境就绪。

> **给 AI 的提示**：上述初始化步骤只需执行一次。如果 `.venv/` 目录已存在且 `pip list` 输出包含 `DrissionPage` 和 `beautifulsoup4`，说明已安装，跳过第二步和第三步。如果 `chromium` 或 `google-chrome` 命令已存在，跳过浏览器安装。

---

## 使用流程

### 交互式提交流程（推荐，适合小白）

1. 用户在 Claude Code 中输入 `/vuldb-submit`。

2. AI 提示用户提供漏洞报告文件的路径（相对或绝对路径）：
   ```
   请输入漏洞报告文件路径（支持 txt、md、pdf 等格式）：
   ```

3. 用户提供路径后，AI 读取文件内容，分析并提取以下字段：

   | 字段 | 说明 | 示例 |
   |------|------|------|
   | **vendor** | 厂商名称 | `Microsoft`, `Apache` |
   | **product** | 产品名称 | `Windows`, `Log4j` |
   | **version** | 受影响版本 | `10.0.19041`, `2.14.1` |
   | **class** | 漏洞类型 | `SQL Injection`, `XSS`, `RCE` |
   | **desc** | 漏洞详细描述（需足够详细） | 见下方要求 |
   | **link** | 参考链接（可选） | `https://example.com/advisory` |

4. AI 将提取到的信息以表格形式回显，并询问用户确认：

   ```
   📋 提取到的漏洞信息：

   | 字段 | 内容 |
   |--------|------|
   | vendor | xxx |
   | product | xxx |
   | version | xxx |
   | class | xxx |
   | desc | xxx |
   | link | xxx |

   是否确认提交？（确认 / 修改 / 取消）
   ```

5. 用户可以选择：
   - **确认** → AI 调用 Python 脚本提交漏洞
   - **修改** → 指定要修改的字段和新值，例如 `vendor=Microsoft` 或 `desc=更详细的描述...`，AI 更新后重新展示
   - **取消** → 终止流程

6. 提交完成后，AI 反馈结果：
   - ✅ 漏洞提交成功！
   - ⚠️ 被拒绝（附原因，如描述不够详细、可能重复等）

### 直接命令行提交（适合脚本/批量）

```bash
# Linux 无 GUI
xvfb-run --auto-servernum .venv/bin/python scripts/submit_vuln.py \
  --json '{"vendor":"...","product":"...","version":"...","class":"...","desc":"..."}'

# Windows
.venv\Scripts\python scripts\submit_vuln.py --json "{...}"

# 或用 JSON 文件
xvfb-run --auto-servernum .venv/bin/python scripts/submit_vuln.py --file data.json
```

---

## 描述（desc）字段要求

VulDB 对描述质量有最低要求，太短或缺乏技术细节会被拒绝并提示：

> "We need more details about your vulnerability to do a proper validation."

**撰写建议**：
- 包含漏洞发现方式、影响范围、技术原理
- 如有 PoC 或复现步骤一并附上
- 描述长度建议 150 字符以上
- 避免无实质内容的测试文本

**AI 从报告文件中提取 desc 时**，应尽可能保留原文中的技术细节，不要过度精简。

---

## 依赖汇总

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python 3.8+ | 运行环境 | 系统包管理器 |
| DrissionPage | 驱动浏览器绕过 Cloudflare | `pip install DrissionPage` |
| beautifulsoup4 | 解析 HTML 响应 | `pip install beautifulsoup4` |
| Chromium/Chrome | 浏览器内核 | 系统安装或 `playwright install chromium` |
| xvfb（仅 Linux） | 无 GUI 环境的虚拟显示 | `apt install xvfb` |

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `Missing X server or $DISPLAY` | Linux 无 GUI | 使用 `xvfb-run` 包装命令 |
| 长时间卡在 "Just a moment..." | Cloudflare 挑战未通过 | 等待 1-2 分钟或更换 IP |
| "We need more details" | 描述不够详细 | 扩充 desc 字段的技术内容 |
| "可能重复" | 同厂商/产品/版本组合已存在 | 更换参数或确认是否真的重复 |
| 登录失败 | 账号密码错误 | 检查 `USERNAME`/`PASSWORD` 配置 |
| 401 Unauthorized | 未登录或 session 过期 | 检查账号权限，确认是否为付费账号 |

---

## 项目结构

```
vuldb-submit/
├── SKILL.md                   # 本文件 — Skill 定义（含完整使用流程）
├── README.md                  # 项目技术文档（架构原理、开发细节）
├── requirements.txt           # Python 依赖清单
├── scripts/
│   └── submit_vuln.py         # 核心提交脚本
├── .vuldb_cookies.json        # （运行时生成）浏览器 cookie
└── .venv/                     # Python 虚拟环境（需初始化）
```
