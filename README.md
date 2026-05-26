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

- 🤖 **AI 处理（Gemini 3 Flash）**：
  - **极速架构**：采用 Unified Request 模式，每次运行仅需 **2 次** AI 调用
  - **智能融合**：哈利波特角色开场白智能融合当日天气与科学大新闻
  - **批量处理**：一次性完成多条新闻的翻译与总结
  - **指数退避重试**：自动处理 503/429 等临时错误（15s → 30s → 60s）
  - **返回值校验**：AI 输出 schema 校验 + 降级兜底，确保邮件始终可发送
  - 筛选结果：15-30 条精选新闻

- ✉️ **简洁邮件**：
  - 响应式 HTML 设计，完美适配移动端
  - CSS 模板独立管理，维护便捷
  - **方正素雅**的设计风格，直线边框，灰色调配色
  - SMTP 发送指数退避重试（5s → 15s → 30s）
  - 运行耗时统计，日志完整可追溯

- 🧪 **测试覆盖**：
  - 配置验证逻辑测试
  - RSS 日期解析多格式测试
  - 邮件 HTML 生成测试

## 项目结构

```
daily_magic_bot/
├── config.py              # 配置管理（环境变量 + 校验）
├── weather_parser.py      # 天气数据解析（容错 + 默认值）
├── news_fetcher.py        # 新闻获取（13源并行抓取 + Session连接池）
├── gemini_processor.py    # Gemini AI处理（指数退避重试 + 校验）
├── email_sender.py        # 邮件发送（指数退避重试 + SSL/TLS）
├── main.py                # 主程序（计时 + 多模式）
├── requirements.txt       # Python依赖（版本范围锁定）
├── pyproject.toml         # 项目元数据（Python >= 3.10）
├── .env.template          # 环境变量模板
├── .github/workflows/     # GitHub Actions 自动化
│   └── daily_report.yml   # 每日定时任务（北京时间 7:32）
├── .gitignore             # Git忽略文件
├── templates/             # 邮件模板
│   ├── email.html         # HTML 邮件模板
│   └── email.css          # 响应式 CSS 样式
├── tests/                 # 单元测试
│   ├── test_config.py     # 配置验证测试
│   ├── test_news_fetcher.py  # 日期解析 + 新闻过滤测试
│   └── test_email_sender.py  # 来源名称映射 + HTML生成测试
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
pip install -r requirements.txt
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

# 邮箱配置（以Gmail为例）
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
# 如果使用国内邮箱（如QQ、163、高校邮箱），通常使用SSL端口 465
# SMTP_PORT=465
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password

# 接收邮箱（用逗号分隔）
RECEIVER_EMAILS=email1@example.com,email2@example.com
```

**重要提示**：
- **Gemini API密钥**：从[Google AI Studio](https://aistudio.google.com/)获取
- **Gmail应用密码**：需要在Google账户中生成[应用专用密码](https://myaccount.google.com/apppasswords)

## 使用方法

### 邮件发送测试（新功能）

快速测试SMTP配置是否正确，发送一封简单的测试邮件（不消耗AI Token）：

```bash
python main.py --email-test
```

### 测试运行（不发送邮件）

生成完整报告的HTML预览，保存在`/tmp`目录，不发送邮件：

```bash
python main.py --test --no-send
```

### 测试发送完整报告

生成并发送包含天气和新闻的完整报告：

```bash
python main.py --test
```

### 正式运行

```bash
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
          pip install -r requirements.txt
      
      - name: Run daily report
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
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

## 测试

### 安装测试依赖

```bash
pip install pytest
```

### 运行全部测试

```bash
python -m pytest tests/ -v
```

### 预期结果

全部 16 个测试用例通过：

```
tests/test_config.py::TestConfigValidate::test_default_values_trigger_errors PASSED
tests/test_config.py::TestConfigValidate::test_valid_config_passes PASSED
tests/test_config.py::TestConfigValidate::test_single_receiver_email_passes PASSED
tests/test_config.py::TestConfigValidate::test_empty_receiver_emails_fails PASSED
tests/test_config.py::TestConfigValidate::test_invalid_email_format_fails PASSED

tests/test_news_fetcher.py::TestDateParsing::test_parse_rss_date_rfc822 PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_rss_date_iso PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_rss_date_empty PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_rss_date_none PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_date_standard PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_date_nature_format PASSED
tests/test_news_fetcher.py::TestDateParsing::test_parse_date_empty PASSED
tests/test_news_fetcher.py::TestDateParsing::test_filter_recent_news PASSED

tests/test_email_sender.py::TestSourceNameSimplification::test_nature_news_maps_to_nature PASSED
tests/test_email_sender.py::TestSourceNameSimplification::test_nature_keeps_nature PASSED
tests/test_email_sender.py::TestSourceNameSimplification::test_nature_astronomy_abbreviates PASSED
tests/test_email_sender.py::TestSourceNameSimplification::test_sciencedaily_variants PASSED
tests/test_email_sender.py::TestSourceNameSimplification::test_unknown_source_passthrough PASSED
tests/test_email_sender.py::TestSourceNameSimplification::test_psypost PASSED
tests/test_email_sender.py::TestCityWeatherHTML::test_basic_weather_html PASSED
tests/test_email_sender.py::TestCityWeatherHTML::test_weather_with_alerts PASSED
tests/test_email_sender.py::TestNewsSectionHTML::test_empty_news_returns_empty PASSED
tests/test_email_sender.py::TestNewsSectionHTML::test_news_with_category PASSED

============================== 23 passed in 0.15s ==============================
```

### 单独运行某个测试模块

```bash
# 仅测试配置验证
python -m pytest tests/test_config.py -v

# 仅测试日期解析
python -m pytest tests/test_news_fetcher.py -v

# 仅测试邮件生成
python -m pytest tests/test_email_sender.py -v
```

## 故障排查

### 1. 邮件发送失败

- 检查SMTP配置是否正确
- Gmail需要开启"允许不够安全的应用访问"或使用应用专用密码
- 检查网络连接

### 2. Gemini API 调用失败

- 确认 API 密钥正确
- 检查 API 配额是否用尽
- 确认网络能访问 Google 服务
- **503/429 错误**：程序会自动重试（15s → 30s → 60s），通常为 Gemini 高峰期临时过载
- 若重试仍失败，会使用降级内容（默认问候语 + 前 15 条新闻），确保邮件可发送

### 3. 天气数据解析失败
- 确认网络可访问 weather.com.cn
- 单个城市解析失败不影响另一个城市（独立容错）
- 查看日志确认具体错误

## 更新日志

### v2.3 (2026-05-26)
- 🧪 **测试体系**：新增 `tests/` 目录，覆盖配置验证、日期解析、邮件 HTML 生成，共 23 个测试用例
- 📐 **工程化**：新增 `pyproject.toml`，声明 Python >= 3.10 及项目元数据
- 🎨 **模板提取**：CSS 和 HTML 模板从代码中分离至 `templates/` 目录，使用 `string.Template` 渲染
- 🔧 **代码质量修复**：
  - 修复 `config.validate()` 接收邮箱验证逻辑：支持单/多收件人，校验 @ 格式
  - 移除废弃方法 `_generate_weather_section()` 和空目录 `.qoder/`
  - 提取重复默认天气字典为模块常量 `DEFAULT_WEATHER`
  - 清理 gemini_processor.py 中函数内部延迟导入和重复 `import time`
- ⚡ **性能优化**：
  - `news_fetcher.py` 和 `weather_parser.py` 使用 `requests.Session()` 连接池复用 TCP 连接
  - 重试策略统一为指数退避（Gemini API: 15s/30s/60s，SMTP: 5s/15s/30s）
- 🛡️ **安全增强**：
  - `.gitignore` 补充 `dist/`、`build/`、`.mypy_cache/`、`.tox/`、`coverage/` 等标准忽略项
  - 修复 `send_email` SMTP 异常处理中的缩进 bug

### v2.2 (2026-02-14)
- 🛡️ **健壮性全面升级**：
  - Gemini API 指数退避重试（15s → 30s → 60s），自动处理 503/429 临时错误
  - AI 返回值 schema 校验，异常格式自动降级兜底
  - 天气解析独立容错，单城市失败不影响另一个
  - 配置校验补全（新增 SMTP 密码、收件人检查）
- ⚡ **性能优化**：
  - 新闻源并行抓取（8 线程 ThreadPoolExecutor），获取速度提升 ~5 倍
  - RSS 抓取增加 15s 超时控制，避免单源阻塞
  - 运行耗时统计，日志可追溯
- 🧹 **代码清理**：
  - 移除 3 个 v1 废弃方法（generate_weather_content 等），减少 ~115 行
  - 统一日志配置（仅 main.py 初始化 logging），修复重复 basicConfig
  - 修复 create_test_email CSS 转义错误、email_sender 测试代码引用错误
  - 步骤编号统一为 [1/4]~[4/4]
- 📦 **运维改善**：
  - requirements.txt 依赖版本范围锁定
  - GitHub Actions 升级至 checkout@v4 + setup-python@v5

### v2.1 (2025-12-31)
- 🧠 **心理学源扩展**：新增 PsyPost、BPS Research Digest、PNAS Psychology 三个专业心理学新闻源
- 🎯 **筛选策略优化**：
  - 关键词相关性成为首要筛选标准（标题/摘要直接匹配优先）
  - 专业源（Nature Astronomy、PsyPost、BPS、PNAS）略微加权
  - 扩充关键词：天文增加双星、恒星振荡、光谱、GAIA/TESS/Kepler；心理学增加信心、不确定性、错误监控、内省、知道感、学习判断、EEG、前额叶等
- 📰 **按领域分组显示**：新闻按 🔭天体物理 → 🧠元认知与心理学 → 📰其他 分类展示
- 🎨 **界面风格调整**：采用方正素雅设计，直线边框，去除圆角和阴影，灰色调配色

### v2.0 (2025-12-04)
- 🚀 **架构重构**：实现 Unified AI Request，将多次 AI 调用合并为 2 次，大幅提升速度并降低成本
- 📰 **新闻源升级**：
  - 从单一 ScienceDaily 扩展至 **10 个顶级新闻源**（Nature News、Nature Research、ScienceDaily × 4）
  - 新闻获取量：去重后约 250 条（最近 2 天内）
  - 智能日期过滤，确保新闻时效性
  - AI 筛选优化：支持白矮星、脉冲星、恒星物理、望远镜、心理学、认知神经科学、元认知等多领域
- 📱 **UI 升级**：
  - 全面优化移动端显示效果，减少页边距，提升阅读体验
  - 天气卡片布局调整（天气状况与温度同行显示），信息密度更高
  - 新闻链接改为简洁的图标按钮
  - 新增日期显示（小字灰色，格式：yyyy-mm-dd）
- 🔍 **能力增强**：
  - 新闻筛选结果：10-25 条精选新闻（可根据重要性动态调整）
  - 哈利波特问候语升级，能够感知并评论当天的科学大新闻
- 🛠 **技术栈**：升级至 `gemini-3-flash-preview` 模型，响应更快
