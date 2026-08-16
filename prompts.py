"""
Prompt 模板构造模块
负责主内容生成与批量处理两个 prompt 的构造，以及输入数据的格式化/清洗
"""
import re
from typing import Dict, List

# --- Prompt 体积控制常量 ---
DESC_PREVIEW_LENGTH = 100    # 新闻列表中每条摘要的截断长度（控制 prompt 体积）
TITLE_MAX_LENGTH = 150       # 新闻标题最大长度（防御异常超长标题）
MAX_CONTENT_PREVIEW = 3000   # 批量处理时发送给 AI 的单篇内容预览长度（字符）


def clean_text(text: str) -> str:
    """清洗文本：合并换行/连续空白为单个空格

    防御 RSS/网页标题中的换行与多余空白破坏 prompt 的编号行格式。

    Args:
        text: 原始文本

    Returns:
        清洗后的单行文本
    """
    return re.sub(r'\s+', ' ', text or '').strip()


def format_city_weather(city_name: str, data: Dict) -> str:
    """格式化单个城市的天气信息（供 prompt 使用）

    除天气状况/温度范围/风力外，补充实况温度、日出日落与预警，
    让 AI 问候与穿衣建议能感知预警等关键信息。

    Args:
        city_name: 城市名称
        data: 该城市的天气数据字典

    Returns:
        单行格式化的天气描述
    """
    parts = [
        f"{data.get('weather', '未知')}",
        f"{data.get('temperature', '未知')}",
        f"{data.get('wind', '未知')}",
        f"当前实况 {data.get('current_temp', '未知')}",
        f"日出 {data.get('sunrise', '未知')} 日落 {data.get('sunset', '未知')}",
    ]
    alerts = data.get('alerts') or []
    if alerts:
        parts.append(f"⚠️预警: {'; '.join(alerts)}")
    return f"- {city_name}：{'，'.join(parts)}"


def _build_news_text(news_list: List[Dict]) -> str:
    """构建新闻列表文本（含来源、日期与截断摘要，标题清洗防御异常空白）"""
    news_text = ""
    for i, news in enumerate(news_list, 1):
        title = clean_text(news.get('title', ''))[:TITLE_MAX_LENGTH]
        desc = clean_text(news.get('description', ''))[:DESC_PREVIEW_LENGTH]
        desc_part = f" 摘要: {desc}" if desc else ""
        news_text += f"{i}. [{news.get('source', 'Unknown')}] {title} ({news.get('date', '')}){desc_part}\n"
    return news_text


def build_master_prompt(character_name: str, weather_info: Dict, news_list: List[Dict]) -> str:
    """构建主内容生成 prompt（问候 + 穿衣建议 + 新闻筛选分类）

    Args:
        character_name: 哈利波特角色名称
        weather_info: 天气数据 {'beijing': {...}, 'jinan': {...}}
        news_list: 原始新闻列表（包含 title, url, source, date, description）

    Returns:
        完整 prompt 文本
    """
    beijing = weather_info.get('beijing', {})
    jinan = weather_info.get('jinan', {})
    news_text = _build_news_text(news_list)

    return f"""你是哈利波特世界中的{character_name}。请完成以下任务（**请全程使用中文回答**）：

1. **角色问候**：以{character_name}的第一人称口吻用中文写一段开场白（100-150字）。
   - 总结今日天气（北京和济南）。
   - **简要提及今日科学界发生的有趣事情**（根据新闻列表）。
   - 语气符合角色性格，清新自然。

2. **天气建议**：分别为北京和济南给出穿衣建议。

3. **新闻筛选与分类**：从列表中选出 15-20 条与以下领域**关键词高度相关**的科学新闻。

   **领域A - 天体物理学**（关键词匹配优先）：
   - 核心：球状星团(globular cluster)、白矮星(white dwarf)、毫秒脉冲星(millisecond pulsar)、脉冲星(pulsar)、中子星(neutron star)
   - 恒星物理：恒星演化(stellar evolution)、星震学(asteroseismology)、变星(variable star)、双星(binary star)、恒星振荡(stellar oscillation)
   - 观测：望远镜(telescope)、X射线天文学(X-ray astronomy)、引力波(gravitational wave)、光谱(spectroscopy)、GAIA、TESS、Kepler
   
   **领域B - 元认知与心理学**（关键词匹配优先）：
   - 核心：元认知(metacognition)、信心(confidence)、不确定性(uncertainty)、错误监控(error monitoring)、内省(introspection)
   - 认知：知道感(feeling of knowing)、学习判断(judgment of learning)、自我意识(self-awareness)、工作记忆(working memory)、注意力(attention)、决策(decision making)
   - 神经科学：fMRI、EEG、脑成像(brain imaging)、前额叶(prefrontal cortex)、认知神经科学(cognitive neuroscience)
   
   **筛选原则**（按重要性排序）：
   1. **关键词相关性最重要**：标题或摘要中直接包含上述关键词的新闻优先级最高
   2. **领域专业源加权**：来自 Nature Astronomy、PsyPost、Neuroscience News、Medical Xpress 的相关新闻略微优先
   3. **日期次要**：同等相关性下，优先选择日期更近的新闻
   4. 总量控制在 15-20 条，优先选择 A 和 B 领域，C 领域宁缺毋滥

   **领域C（其他科学发现）的严格筛选标准**：
   C 类只收录满足以下任一条件的新闻，**不满足的坚决不选**：
   - 与日常生活直接相关的科学发现（如：健康医学、公共卫生、营养、睡眠、环境气候、新能源、AI应用、太空探索）
   - 真正改变世界的重大突破（如：诺奖级成果、首次实现/发现、颠覆性技术、改变人类认知的基础科学突破）

   **坚决排除**以下内容（即使来自 Nature/Science）：
   - 常规材料化学研究、催化剂优化、电池微改进等工业化学
   - 某蛋白结构解析、某基因测序、某化合物合成路线等常规分子生物学/化学
   - 某矿床发现、某地质年代划分等纯地质学
   - 纯工程学增量改进（如某合金强度提升 5%）
   - 纯方法论论文（如"一种改进的 XX 算法"）

   **请为每条新闻标注所属领域**：A（天体物理）、B（元认知/心理学）、C（其他重大发现）
输入数据：
【天气】
{format_city_weather('北京', beijing)}
{format_city_weather('济南', jinan)}

【新闻列表】
{news_text}

请严格按照以下 JSON 格式返回（不要包含 Markdown 代码块标记）：
{{
    "greeting": "角色开场白内容...",
    "advice_beijing": "北京穿衣建议...",
    "advice_jinan": "济南穿衣建议...",
    "selected_news": [
        {{"index": 1, "category": "A"}},
        {{"index": 3, "category": "B"}}
    ]
}}
"""


def build_batch_prompt(articles: List[Dict]) -> str:
    """构建批量处理 prompt（标题翻译 + 倒金字塔摘要）

    Args:
        articles: 文章列表，每项含 title 与 content 字段

    Returns:
        完整 prompt 文本
    """
    articles_text = ""
    for i, art in enumerate(articles, 1):
        content = art['content'] or ''
        content_preview = content[:MAX_CONTENT_PREVIEW]
        content_len = len(content)
        articles_text += f"""
文章 {i}:
标题: {art['title']}
输入长度: {content_len} 字符
内容: {content_preview}
---
"""

    return f"""请批量处理以下 {len(articles)} 篇科学新闻/论文。

对于每一篇文章，请完成：
1. 将标题翻译成中文（准确、专业，保持学术风格）
2. 用中文总结文章核心内容，采用**倒金字塔结构**（先写最重要的发现/结论，再补充关键细节和背景）。总结篇幅根据输入内容长度分层：
   - 输入 < 200 字符：摘要 100-200 字（根据可用信息简要概括，不编造）
   - 输入 ≥ 200 字符：摘要 200-400 字（详实专业，涵盖核心发现、方法和科学意义）

输入文章列表：
{articles_text}

请严格按照以下 JSON 格式返回列表（不要包含 Markdown 代码块标记）：
[
    {{
        "original_title": "原英文标题",
        "title_cn": "中文翻译标题",
        "summary": "中文总结内容（倒金字塔结构，一个小段落）"
    }},
    ...
]
"""
