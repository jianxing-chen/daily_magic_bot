# 每日魔法报告 (Daily Magic Bot)

每日自动生成包含天气预报和科学新闻摘要的邮件报告，使用 Gemini AI 进行智能筛选与内容生成。专为天文学与元认知/心理学方向的科研人员设计。

## 功能特点

- 📊 **天气播报**：
  - 实时解析北京和济南的天气数据（weather.com.cn）
  - 天气状况与温度同行显示，信息密度更高
  - 提供日出日落时间、风力等级及天气预警信息
  - 城市天气解析独立容错，单个城市失败不影响另一个
  - 包含湿度、日出日落时间、风力等级及天气预警信息

- 🔬 **科学新闻（13 个专业新闻源，并行抓取）**：
  - **Nature 系列**：Nature News (网页) + Nature / Nature Astronomy / Nature Reviews Psychology / Nature Communications (RSS)
  - **Science** 杂志 (RSS)
  - **ScienceDaily RSS**：Mind & Brain / Top Science / Top News / Space & Time
  - **心理学专门源**：PsyPost / Neuroscience News / PNAS Psychology
  - 覆盖范围：去重后约 **300+ 条**新闻，过滤后保留最近 1 天内
  - ⚡ **多线程并行抓取**（8 线程），新闻获取速度提升 ~5 倍
  
- 🎯 **智能筛选（关键词相关性优先）**：
  - **天体物理**：球状星团、白矮星、毫秒脉冲星、中子星、脉冲星、恒星演化、星震学、变星、双星、恒星振荡、望远镜、X射线天文学、引力波、光谱、GAIA、TESS、Kepler
  - **元认知与心理学**：元认知、信心、不确定性、错误监控、内省、知道感、学习判断、自我意识、工作记忆、注意力、决策、fMRI、EEG、脑成像、前额叶、认知神经科学
  - **筛选原则**：关键词匹配 > 专业源加权 > 日期
  - **按领域分组显示**：🔭 天体物理 → 🧠 元认知与心理学 → 📰 其他
  - 提供中英双语标题和 AI 生成的**倒金字塔结构**中文摘要

- 🤖 **AI 处理（Gemini 3.5 Flash）**：
  - **极速架构**：采用 Unified Request 模式，每次运行仅需 **2 次** AI 调用
  - **智能融合**：哈利波特角色开场白智能融合当日天气与科学大新闻
  - **批量处理**：一次性完成多条新闻的翻译与总结，摘要长度根据输入内容自适应（100-400 字）
  - **指数退避重试**：自动处理 503/429 等临时错误（Gemini 链 30s → 60s）
  - **多模型回退 + 跨厂商兜底**：gemini-3.5-flash → 3-flash-preview → 2.5-pro → DeepSeek V4 Flash（需配置 DEEPSEEK_API_KEY）
  - **返回值校验**：AI 输出 schema 校验 + 降级兜底，确保邮件始终可发送
  - 筛选结果：15-20 条精选新闻（A/B/C 三领域，C 领域严格把关宁缺毋滥）

- ✉️ **简洁邮件**：
  - 响应式 HTML 设计，完美适配移动端
  - CSS 模板独立管理，维护便捷
  - **暖色魔法主题**设计风格，深海军蓝 + 金色点缀，暖奶油色背景
  - SMTP 发送指数退避重试（5s → 15s → 30s）
  - 运行耗时统计，日志完整可追溯

- 🔍 **预检诊断**：`--check` 一键检查配置/网络/API/SMTP

## 项目结构

```
daily_magic_bot/
├── config.py              # 配置管理（环境变量 + 校验）
├── weather_parser.py      # 天气数据解析（容错 + 默认值）
├── news_fetcher.py        # 新闻获取（13源并行抓取 + Session连接池）
├── async_news_fetcher.py  # 异步文章详情抓取（aiohttp 并发）
├── gemini_processor.py    # Gemini AI处理（指数退避重试 + 校验）
├── email_sender.py        # 邮件发送（Jinja2模板 + 指数退避重试）
├── logging_config.py      # 日志配置模块
├── main.py                # 主程序（计时 + 多模式）
├── requirements.txt       # Python运行依赖（唯一事实源，版本范围锁定）
├── requirements-dev.txt   # 开发/测试依赖（含 pytest）
├── pyproject.toml         # 项目元数据（Python >= 3.10，依赖动态读取 requirements.txt）
├── .env.template          # 环境变量模板
├── .github/workflows/     # GitHub Actions 自动化
│   └── daily_report.yml   # 每日定时任务（北京时间 7:32）
├── .gitignore               # Git忽略文件
├── templates/               # 邮件模板（Jinja2）
│   ├── email_base.html    # 基础模板（HTML骨架）
│   ├── email.html         # 主邮件模板
│   ├── weather_card.html  # 天气卡片组件
│   ├── news_section.html  # 新闻列表组件
│   └── email.css          # 响应式 CSS 样式
├── tests/                   # pytest 离线单元测试（无网络/零 token）
│   ├── test_json_parser.py    # AI 返回健壮解析（9 种畸形形态回归）
│   ├── test_weather_parser.py # 时段对齐/温度归一/实况温度
│   ├── test_news_fetcher.py   # 文本清洗/日期解析/时效过滤
│   └── test_email_rendering.py# 邮件渲染端到端（mock 数据）
└── README.md              # 本文件
```

## 安装步骤

### 1. 克隆或下载项目

```bash
cd /Your/1_DailyReportBot
```

### 2. 创建Conda环境（推荐）

```bash
conda create -n daily_report python=3.10
conda activate daily_report
```

### 3. 安装依赖

```bash
# 运行依赖
pip install -r requirements.txt

# 开发/测试依赖（含 pytest，开发者使用）
pip install -r requirements-dev.txt
```

### 4. 配置环境变量

复制模板文件并填写配置：

```bash
cp .env.template .env
```

编辑`.env`文件，填写以下信息：

```bash
# Gemini API配置
GEMINI_API_KEY=your_actual_api_key_here

# DeepSeek API配置（可选，Gemini 全部失效时的兜底模型）
DEEPSEEK_API_KEY=your_deepseek_key_here

# 邮箱配置（以Gmail为例）
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
# 如果使用国内邮箱（如QQ、163、高校邮箱），通常使用SSL端口 465
# SMTP_PORT=465
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
SENDER_NAME=Daily Magic Bot  # 可选，发件人显示名称

# 接收邮箱（用逗号分隔）
RECEIVER_EMAILS=email1@example.com,email2@example.com
```

**重要提示**：
- **Gemini API密钥**：从[Google AI Studio](https://aistudio.google.com/)获取
- **DeepSeek API密钥**（可选兜底）：从[DeepSeek 开放平台](https://platform.deepseek.com/)获取
- **Gmail应用密码**：需要在Google账户中生成[应用专用密码](https://myaccount.google.com/apppasswords)

## 使用方法

| 命令 | API token | 发送邮件 | 保存 HTML | 用途 |
|------|:--:|:--:|:--:|------|
| `python main.py --check` | ~10 | 否 | 否 | 预检：检查配置/网络/API/SMTP 是否正常 |
| `python main.py --email-test` | 0 | 是 | 否 | 发送简单测试邮件，验证 SMTP 配置 |
| `python main.py --test --no-send` | ~5k | 否 | 是 | 生成完整报告 HTML 保存到 /tmp，不发送 |
| `python main.py --test` | ~5k | 是 | 是 | 生成完整报告并发送，同时保存 HTML 到 /tmp |
| `python main.py` | ~5k | 是 | 否 | 正式运行，生成并发送（GitHub Actions 默认模式） |

### 典型工作流

```bash
# 首次配置后：预检环境
python main.py --check

# 运行离线单元测试（无网络/零 token）
pytest

# 验证邮件能收到
python main.py --email-test

# 预览报告内容（不发送）
python main.py --test --no-send

# 确认无误，正式运行
python main.py
```

## GitHub Actions 部署

本项目设计为在 GitHub Actions 中运行。配置文件位于 `.github/workflows/daily_report.yml`：

```yaml
name: Daily Report

on:
  schedule:
    # 每天北京时间早上7:32运行 (UTC 23:32 前一天)
    - cron: '32 23 * * *'
  workflow_dispatch:  # 允许手动触发

jobs:
  send-report:
    runs-on: ubuntu-latest
    
    env:
      TZ: Asia/Shanghai  # 设置东8区时区，确保日期正确
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt
      
      - name: Run daily report
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          SMTP_SERVER: ${{ secrets.SMTP_SERVER }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
          RECEIVER_EMAILS: ${{ secrets.RECEIVER_EMAILS }}
        run: |
          python main.py
```

**在GitHub仓库中设置Secrets**：
- Settings → Secrets and variables → Actions → New repository secret
- 添加所有环境变量（`GEMINI_API_KEY`、`SENDER_EMAIL`等）

需要添加的 Secrets 列表（建议直接复制 Name）：

| Name (变量名) | Secret (值/占位符) |
| :--- | :--- |
| `GEMINI_API_KEY` | `your_api_key_here` |
| `DEEPSEEK_API_KEY` | `your_deepseek_key_here`（可选兜底） |
| `SMTP_SERVER` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SENDER_EMAIL` | `your_email@gmail.com` |
| `SENDER_PASSWORD` | `your_app_password` |
| `RECEIVER_EMAILS` | `email1@example.com,email2@example.com` |

## 天气数据来源

程序会自动从以下 URL 实时获取最新天气数据：
- 北京：https://www.weather.com.cn/weather1d/101011700.shtml
- 济南：https://www.weather.com.cn/weather1d/101120107.shtml

程序运行时会直接从 URL 获取最新数据，无需本地缓存。

## 故障排查

### 1. 邮件发送失败

- 检查SMTP配置是否正确
- Gmail需要开启"允许不够安全的应用访问"或使用应用专用密码
- 检查网络连接

### 2. Gemini API 调用失败

- 确认 API 密钥正确
- 检查 API 配额是否用尽
- 确认网络能访问 Google 服务
- **503/429 错误**：程序会自动重试（Gemini 链 30s → 60s，逐模型回退），通常为 Gemini 高峰期临时过载
- Gemini 三个模型全部失效时，若配置了 `DEEPSEEK_API_KEY` 会自动兜底切换到 DeepSeek V4 Flash
- 若所有模型均失败，会使用降级内容（默认问候语 + 前 15 条新闻），确保邮件可发送

### 3. 天气数据解析失败
- 确认网络可访问 weather.com.cn
- 单个城市解析失败不影响另一个城市（独立容错）
- 查看日志确认具体错误

## 更新日志

完整更新日志已迁至 [CHANGELOG.md](CHANGELOG.md)。

**最新版本 v2.7 (2026-08-16)**：Gmail 渲染兼容性修复（天气双卡 flex→表格布局、CSS 注入去转义）、测试体系补强（tests/ 目录 + CI pytest 门禁）、依赖单一事实源、AI 模块三层拆分、重试统一、workflow 安全加固。
