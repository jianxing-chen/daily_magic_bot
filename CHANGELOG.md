# 更新日志 (Changelog)

本文件记录每日魔法报告 (Daily Magic Bot) 的全部版本变更。

### v2.7 (2026-08-16)
- 🎨 **Gmail 渲染兼容性修复**：
  - 天气双卡布局从 `display: flex`（Gmail 网页版不支持）改为邮件标准的表格双列布局，窄屏 `@media` 下纵向堆叠
  - CSS 注入改用 `| safe`，消除 autoescape 转义出的 `&#39;` 导致 Gmail 丢弃字体等样式声明的问题
- 🧪 **测试体系补强**（P2，离线零 token）：
  - 新增 tests/ 目录，AI 返回健壮解析 9 种畸形形态、天气时段对齐/温度归一、SMTP mock、邮件渲染共 50+ 用例
  - CI 新增 pytest 门禁：先测试后发日报，防止坏代码发出错误邮件
- 📦 **依赖单一事实源**（P3）：requirements.txt 为唯一事实源，pyproject 动态读取；新增 requirements-dev.txt
- 🏗️ **AI 模块三层拆分**（P4）：prompts.py（构造）/ ai_client.py（传输+Gemini 回退链+DeepSeek 兑底）/ gemini_processor.py（纯编排）
- 🔁 **重试统一**（P5）：新增 retry.py 统一 Gemini 链/DeepSeek/SMTP 三处重试；EmailSender 新增 test_connection；测试邮件模板化
- 🧹 **代码清理**：移除 gemini_processor 向后兼容 re-export、news_fetcher 死常量；workflow 增加最小权限声明与 Action SHA 固定

### v2.6 (2026-08-11)
- 🛡️ **AI 健壮性修复**：
  - 新增健壮 JSON 解析器 `parse_ai_json`：容错 Markdown 代码块围栏、`//` 注释、尾逗号、前后缀废话，解析失败时打印原始返回文本便于定位
  - 删除 prompt 示例中的非法 `//` 注释（曾诱导模型回显导致解析失败），筛选条数统一为 15-20 条
  - 修复“开头问候与天气建议频繁降级为兜底文案”的主因
- 🔀 **跨厂商兜底**：Gemini 三模型（3.5-flash → 3-flash-preview → 2.5-pro）全部失效时，自动切换 DeepSeek V4 Flash（OpenAI 兼容格式，需配置 `DEEPSEEK_API_KEY`，不配置不影响正常运行）
- 🌤️ **天气解析修复**：
  - 按 h1 时段标签识别白天/夜间区块并对齐今天日期，修复傍晚后页面布局切换导致的温度范围颠倒（如 28~23°C）与跨天串数据问题，温度输出强制 min~max 归一
  - 实况温度恢复提取（改从页面内嵌 observe24h_data 获取，原 CSS 选择器已失效）
  - 修复济南城市名被解析为“山东”的面包屑层级问题
- 📝 **Prompt 增强**：
  - 天气输入从 3 字段扩展为全量（新增实况温度、日出日落，有预警时追加预警行）
  - 新闻列表附加截断摘要（100 字符），解决筛选规则提到摘要却未传入的问题
  - 新闻标题/摘要在抓取源头统一清洗（合并换行/多余空白），防御异常字符破坏 prompt 编号行
- 📄 **文档同步**：CLAUDE.md 修正 4 处过时描述（模板引擎/重试链/文章抓取/环境变量）

### v2.5 (2026-07-29)
- 🔧 **代码质量深度重构**：
  - **常量提取**：所有魔法数字提取为模块级常量（超时/重试/限制值等）
  - **Bug 修复**：
    - 修复 weather_parser 天气预警判断逻辑（支持 display:inline-block 等变体）
    - 修复 gemini_processor 异常检测（优先结构化 code/status 属性，字符串匹配兜底）
  - **代码去重**：weather_parser 添加辅助方法，email_sender 简化重复拼接
- 🏗️ **架构优化**：
  - **配置实例化**：config.py 从类属性改为实例属性，支持依赖注入
  - **依赖注入**：GeminiProcessor/EmailSender/MultiSourceNewsFetcher 支持测试时注入 mock
  - **日志模块化**：新增 logging_config.py 统一日志配置
- 🎨 **模板引擎迁移**：
  - **Jinja2**：替代 string.Template，支持模板继承/组件化/自动 HTML 转义
  - **组件化模板**：email_base.html（骨架）+ weather_card.html（天气卡片）+ news_section.html（新闻列表）
  - **自动转义**：防止 XSS 注入，所有用户输入自动转义
- ⚡ **异步化文章抓取**：
  - **aiohttp 并发**：15-20 篇文章并发抓取，semaphore 限制最大并发数（10）
  - **性能提升**：文章抓取从串行 ~10s 降至并发 ~2s（理论 5x 提升）
  - **智能跳过**：ScienceDaily/Science 来源直接使用 RSS 摘要，无需抓取
- 📦 **依赖更新**：
  - 新增 jinja2>=3.1.0,<4.0.0
  - 新增 aiohttp>=3.9.0,<4.0.0
  - pyproject.toml 版本 2.2.0 → 2.5.0

### v2.4 (2026-05-27)
- 🎯 **筛选精简**：新闻数量上限从 30 条收紧至 20 条，强化质量控制
- 📰 **C 领域严格把关**：新增详细的纳入/排除标准，排除常规材料化学、分子生物学、纯地质学、工程增量改进等枯燥内容，只保留与日常生活相关或改变世界的重大发现
- 🤖 **模型升级**：AI 模型从 `gemini-3-flash-preview` 升级至 `gemini-3.5-flash`
- 📝 **摘要自适应**：翻译 prompt 支持根据输入内容长度分层要求（<200 字符 → 100-200 字，≥200 字符 → 200-400 字），避免短输入硬扩长
- 🎨 **UI 重设计**：邮件样式从方正素雅灰色调升级为暖色魔法主题（深海军蓝 + 金色点缀 + 暖奶油色背景），增强视觉层次和哈利波特氛围感
- 🔧 **代码优化**：移除 weather 内联样式，CSS 类与 HTML 模板解耦

### v2.3 (2026-05-26)
- 🔍 **预检诊断**：新增 `--check` 模式，一键检查 5 个环节（配置 / 天气源 / 新闻源 / Gemini API / SMTP）
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
- 🧠 **心理学源扩展**：新增 PsyPost、Neuroscience News、PNAS Psychology 三个专业心理学新闻源
- 🎯 **筛选策略优化**：
  - 关键词相关性成为首要筛选标准（标题/摘要直接匹配优先）
  - 专业源（Nature Astronomy、PsyPost、Neuroscience News、PNAS）略微加权
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
