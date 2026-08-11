"""
Gemini AI处理模块
使用Gemini API进行内容处理和生成
"""
from google import genai
from google.genai import errors as genai_errors
from typing import List, Dict
import asyncio
import random
import logging
import json
import re
import time

import requests

from config import config
from async_news_fetcher import fetch_articles_async

logger = logging.getLogger(__name__)

# --- 处理配置常量 ---
MAX_CONTENT_LENGTH = 5000      # 单篇文章最大内容长度（字符）
MAX_CONTENT_PREVIEW = 3000     # 发送给 AI 的内容预览长度（字符）
RETRYABLE_STATUS_CODES = {503, 429}  # 可重试的 HTTP 状态码
RETRYABLE_STATUS_NAMES = {'UNAVAILABLE', 'RESOURCE_EXHAUSTED'}  # 可重试的 gRPC 状态名
RAW_TEXT_LOG_LIMIT = 2000    # 解析失败时打印原始返回文本的最大长度
DESC_PREVIEW_LENGTH = 100    # 新闻列表中每条摘要的截断长度（控制 prompt 体积）
TITLE_MAX_LENGTH = 150       # 新闻标题最大长度（防御异常超长标题）

# --- DeepSeek 兜底调用配置 ---
DEEPSEEK_REQUEST_TIMEOUT = 180       # DeepSeek 请求超时（秒）
DEEPSEEK_MAX_RETRIES = 3             # DeepSeek 最大尝试次数
DEEPSEEK_RETRY_WAITS = [15, 30]      # DeepSeek 重试退避等待（秒）
DEEPSEEK_RETRYABLE_CODES = {429, 500, 502, 503, 504}  # 可重试的 HTTP 状态码


def _strip_json_comments(text: str) -> str:
    """移除字符串字面量之外的 // 行注释

    模型常模仿 prompt 示例回显 // 注释导致 JSON 非法；
    字符串内部的 //（如 https:// URL）必须保留，故逐字符区分字符串内外。

    Args:
        text: 待清理的文本

    Returns:
        移除注释后的文本
    """
    result = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
        elif ch == '"':
            in_string = True
            result.append(ch)
            i += 1
        elif ch == '/' and i + 1 < n and text[i + 1] == '/':
            # 跳过注释直到行尾
            while i < n and text[i] != '\n':
                i += 1
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


def _clean_text(text: str) -> str:
    """清洗文本：合并换行/连续空白为单个空格

    防御 RSS/网页标题中的换行与多余空白破坏 prompt 的编号行格式。

    Args:
        text: 原始文本

    Returns:
        清洗后的单行文本
    """
    return re.sub(r'\s+', ' ', text or '').strip()


def _format_city_weather(city_name: str, data: Dict) -> str:
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


def parse_ai_json(response_text: str, context: str):
    """健壮的 AI JSON 返回解析器

    依次容错：Markdown 代码块围栏 → // 注释 → 前后缀多余文本 → 尾逗号。
    全部失败时打印原始返回文本便于定位，并抛出 JSONDecodeError 由上层降级。

    Args:
        response_text: 模型原始返回文本
        context: 调用场景描述（用于日志）

    Returns:
        解析后的 dict / list

    Raises:
        json.JSONDecodeError: 所有容错策略均失败
    """
    text = response_text.strip()

    # 1. 剥离 Markdown 代码块围栏（```json ... ```）
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # 2. 移除字符串外的 // 注释
    text = _strip_json_comments(text)

    # 3. 截取首个 {...} 或 [...] 主体，丢弃前后缀说明文字
    for start_char, end_char in (('{', '}'), ('[', ']')):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            text = text[start:end + 1]
            break

    # 4. 清理尾逗号（{"a": 1,} 非法但模型常见）
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"{context} JSON 解析失败: {e}")
        logger.error(f"原始返回文本（前 {RAW_TEXT_LOG_LIMIT} 字符）: {response_text[:RAW_TEXT_LOG_LIMIT]}")
        raise


class GeminiProcessor:
    """Gemini AI处理器"""
    
    def __init__(
        self,
        api_key: str,
        deepseek_api_key: str = None,
        deepseek_base_url: str = None,
        deepseek_model: str = None
    ):
        """
        初始化Gemini处理器
        
        Args:
            api_key: Gemini API密钥
            deepseek_api_key: 可选 DeepSeek API密钥（测试注入，默认取 config）
            deepseek_base_url: 可选 DeepSeek base URL（测试注入）
            deepseek_model: 可选 DeepSeek 模型名（测试注入）
        """
        self.client = genai.Client(api_key=api_key)
        # 模型回退链：首选 3.5-flash，高峰 503 时依次回退到 3-flash-preview、2.5-pro
        self.models = ['gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-pro']
        self.max_retries = 2
        # DeepSeek 兜底配置（Gemini 链全部失效时启用）
        self.deepseek_api_key = deepseek_api_key if deepseek_api_key is not None else config.DEEPSEEK_API_KEY
        self.deepseek_base_url = deepseek_base_url or config.DEEPSEEK_BASE_URL
        self.deepseek_model = deepseek_model or config.DEEPSEEK_MODEL
        logger.info("Gemini处理器初始化成功")

    @property
    def deepseek_enabled(self) -> bool:
        """DeepSeek 兜底是否已配置（API key 非占位符）"""
        from config import DEEPSEEK_KEY_PLACEHOLDER
        return bool(self.deepseek_api_key) and self.deepseek_api_key != DEEPSEEK_KEY_PLACEHOLDER
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """判断是否为可重试的临时错误

        优先使用结构化的异常属性（code/status），字符串匹配作为兜底。

        Args:
            error: 捕获的异常

        Returns:
            True 表示临时错误（可重试/回退），False 表示永久错误（应立即抛出）
        """
        # 结构化判断：SDK 的 APIError 携带 code（HTTP 状态码）和 status（gRPC 状态名）
        if isinstance(error, genai_errors.APIError):
            if error.code in RETRYABLE_STATUS_CODES:
                return True
            if error.status and error.status in RETRYABLE_STATUS_NAMES:
                return True
            return False

        # 兜底：非 APIError 时退回字符串匹配（网络错误、SDK 内部错误等）
        error_str = str(error)
        return any(code in error_str for code in ['503', '429', 'UNAVAILABLE', 'RESOURCE_EXHAUSTED'])

    def _call_with_retry(self, prompt: str, use_json: bool = True) -> str:
        """
        带指数退避重试 + 多模型回退 + DeepSeek 兜底的 AI 调用

        先走 Gemini 回退链（_call_gemini_chain）；链全部失效（重试耗尽
        或非临时错误）时，若已配置 DeepSeek API key，则兜底调用 DeepSeek；
        DeepSeek 也失败或未配置时，抛出最后一次异常由上层降级处理。

        Args:
            prompt: 请求内容
            use_json: 是否要求 JSON 格式返回

        Returns:
            API 响应文本
        """
        try:
            return self._call_gemini_chain(prompt, use_json)
        except Exception as gemini_error:
            if not self.deepseek_enabled:
                raise
            logger.warning(f"Gemini 回退链全部失效: {gemini_error}")
            logger.warning(f"兜底切换到 DeepSeek ({self.deepseek_model})...")
            try:
                return self._call_deepseek(prompt, use_json)
            except Exception as deepseek_error:
                logger.error(f"DeepSeek 兜底也失败: {deepseek_error}")
                raise

    def _call_deepseek(self, prompt: str, use_json: bool = True) -> str:
        """调用 DeepSeek API（OpenAI 兼容格式，链尾兜底）

        通过 requests 直连 {base_url}/chat/completions，对 429/5xx/网络错误
        按 DEEPSEEK_RETRY_WAITS 退避重试，非临时错误立即抛出。

        Args:
            prompt: 请求内容
            use_json: 是否要求 JSON 格式返回（response_format=json_object）

        Returns:
            API 响应文本

        Raises:
            RuntimeError / requests.RequestException: 重试耗尽或永久错误
        """
        url = f"{self.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.deepseek_api_key}'
        }
        payload = {
            'model': self.deepseek_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False
        }
        if use_json:
            payload['response_format'] = {'type': 'json_object'}

        last_error = None
        for attempt in range(DEEPSEEK_MAX_RETRIES):
            try:
                response = requests.post(
                    url, headers=headers, json=payload,
                    timeout=DEEPSEEK_REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    data = response.json()
                    return data['choices'][0]['message']['content']

                # 非 200：判断是否可重试
                error_text = response.text[:500]
                last_error = RuntimeError(
                    f"DeepSeek HTTP {response.status_code}: {error_text}"
                )
                if response.status_code not in DEEPSEEK_RETRYABLE_CODES:
                    # 非临时错误（如 401 认证失败/400 参数错误）立即抛出
                    raise last_error

            except requests.RequestException as e:
                last_error = e

            # 临时错误：退避后重试
            if attempt < DEEPSEEK_MAX_RETRIES - 1:
                wait_time = DEEPSEEK_RETRY_WAITS[min(attempt, len(DEEPSEEK_RETRY_WAITS) - 1)]
                logger.warning(f"[DeepSeek] 临时错误 (尝试 {attempt + 1}/{DEEPSEEK_MAX_RETRIES}): {last_error}")
                logger.warning(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

        raise last_error

    def _call_gemini_chain(self, prompt: str, use_json: bool = True) -> str:
        """
        Gemini 模型回退链调用（指数退避重试）

        遍历模型回退链，对每个模型重试 self.max_retries 次（退避 30s/60s）。
        临时错误（503/429/UNAVAILABLE/RESOURCE_EXHAUSTED）重试耗尽后切换下一个模型；
        非临时错误（如 400/认证失败/模型不存在）立即抛出，不做无意义回退。
        全部模型重试耗尽后抛出最后一次异常，由 _call_with_retry 兜底处理。

        Args:
            prompt: 请求内容
            use_json: 是否要求 JSON 格式返回

        Returns:
            API 响应文本
        """
        config = {'response_mime_type': 'application/json'} if use_json else {}
        last_error = None

        for model_idx, model_name in enumerate(self.models):
            for attempt in range(self.max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )
                    return response.text
                except Exception as e:
                    error_str = str(e)
                    last_error = e

                    # 非临时错误（400/认证失败/模型不存在等）不回退，直接抛出
                    if not self._is_retryable_error(e):
                        raise

                    # 临时错误：还有重试次数 → 退避后重试当前模型
                    if attempt < self.max_retries - 1:
                        wait_time = [30, 60][attempt]
                        logger.warning(f"[{model_name}] API 临时错误 (尝试 {attempt + 1}/{self.max_retries}): {error_str}")
                        logger.warning(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        # 当前模型重试耗尽
                        if model_idx < len(self.models) - 1:
                            next_model = self.models[model_idx + 1]
                            logger.warning(f"[{model_name}] 重试耗尽，回退到下一个模型: {next_model}")
                        else:
                            logger.error(f"[{model_name}] 所有模型重试耗尽，抛出异常")
                            raise

        # 理论上不会走到这里（上面循环会 return 或 raise）
        raise last_error
    
    def generate_master_content(self, character_name: str, weather_info: Dict, news_list: List[Dict]) -> Dict:
        """
        一次性生成所有AI内容：问候（含新闻综述）、天气建议、新闻筛选
        
        Args:
            character_name: 角色名称
            weather_info: 天气数据
            news_list: 原始新闻列表（包含 title, url, source, date）
            
        Returns:
            JSON字典包含 greeting, advice_beijing, advice_jinan, selected_news_indices
        """
        try:
            beijing = weather_info.get('beijing', {})
            jinan = weather_info.get('jinan', {})
            
            # 构建新闻列表文本（含来源、日期与截断摘要，标题清洗防御异常空白）
            news_text = ""
            for i, news in enumerate(news_list, 1):
                title = _clean_text(news.get('title', ''))[:TITLE_MAX_LENGTH]
                desc = _clean_text(news.get('description', ''))[:DESC_PREVIEW_LENGTH]
                desc_part = f" 摘要: {desc}" if desc else ""
                news_text += f"{i}. [{news.get('source', 'Unknown')}] {title} ({news.get('date', '')}){desc_part}\n"
            
            prompt = f"""你是哈利波特世界中的{character_name}。请完成以下任务（**请全程使用中文回答**）：

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
   2. **领域专业源加权**：来自 Nature Astronomy、PsyPost、Neuroscience News、PNAS Psychology 的相关新闻略微优先
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
{_format_city_weather('北京', beijing)}
{_format_city_weather('济南', jinan)}

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
            
            response_text = self._call_with_retry(prompt, use_json=True)
            
            # 健壮解析：容错代码块围栏/注释/尾逗号，失败时打印原文便于定位
            result = parse_ai_json(response_text, "主内容生成")
            if not isinstance(result, dict):
                raise ValueError(f"返回 JSON 顶层类型异常: {type(result).__name__}")
            
            # 校验必要字段
            required_keys = ['greeting', 'advice_beijing', 'advice_jinan', 'selected_news']
            for key in required_keys:
                if key not in result:
                    logger.warning(f"AI返回缺少字段: {key}，使用默认值")
                    if key == 'selected_news':
                        result[key] = [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
                    else:
                        result[key] = ''
            
            # 校验 selected_news 格式
            if not isinstance(result.get('selected_news'), list):
                logger.warning("selected_news 格式异常，使用默认值")
                result['selected_news'] = [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
            
            return result
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error("⚠️ AI 内容生成彻底失败，本次邮件将使用兜底默认值（无真实 AI 问候/筛选）")
            logger.error(f"最后错误: {e}")
            logger.error("=" * 60)
            return {
                "greeting": f"{character_name}祝您早安！今天的天气真不错！",
                "advice_beijing": "请注意天气变化。",
                "advice_jinan": "请注意天气变化。",
                "selected_news": [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
            }



    def process_news_batch(self, articles: List[Dict]) -> List[Dict]:
        """
        批量处理新闻：一次性完成标题翻译和内容总结
        
        Args:
            articles: 文章列表 [{'title': '...', 'content': '...', 'url': '...'}]
            
        Returns:
            处理后的列表 [{'title_en': '...', 'title_cn': '...', 'summary': '...', 'url': '...'}]
        """
        try:
            # 构建Prompt，标注每篇输入内容的长度
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

            prompt = f"""请批量处理以下 {len(articles)} 篇科学新闻/论文。

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
            
            response_text = self._call_with_retry(prompt, use_json=True)
            
            # 健壮解析：容错代码块围栏/注释/尾逗号，失败时打印原文便于定位
            results = parse_ai_json(response_text, "新闻批量处理")
            
            # 校验返回列表格式
            if not isinstance(results, list):
                logger.warning(f"AI返回非列表格式: {type(results)}，尝试降级处理")
                results = []
            
            # 合并结果
            processed_news = []
            for i, res in enumerate(results):
                if i < len(articles):
                    processed_news.append({
                        'title_en': articles[i]['title'],
                        'title_cn': res.get('title_cn', articles[i]['title']),
                        'summary': res.get('summary', '暂无总结'),
                        'url': articles[i]['url']
                    })
            
            return processed_news
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error("⚠️ 新闻批量处理彻底失败，摘要将显示为占位文本（无真实 AI 翻译/摘要）")
            logger.error(f"最后错误: {e}")
            logger.error("=" * 60)
            # 降级处理：返回原始数据
            return [{
                'title_en': art['title'],
                'title_cn': art['title'],  # 无法翻译
                'summary': 'AI处理失败，请查看原文',
                'url': art['url']
            } for art in articles]


def process_daily_report(
    weather_data: Dict,
    news_list: List[Dict],
    processor: 'GeminiProcessor' = None
) -> Dict:
    """
    统一处理每日报告的所有AI内容

    Args:
        weather_data: 天气数据
        news_list: 原始新闻列表（包含 title, url, source, date）
        processor: 可选的 GeminiProcessor 实例（用于测试时注入 mock）

    Returns:
        包含所有生成内容的字典
    """
    # 使用注入的实例或创建新实例
    processor = processor or GeminiProcessor(config.GEMINI_API_KEY)
    
    result = {
        'greeting': '',
        'weather_advice': {},
        'processed_news': [],
        'character': ''
    }
    
    try:
        # 1. 选择角色
        character = random.choice(config.HARRY_POTTER_CHARACTERS)
        result['character'] = character
        logger.info(f"选择角色: {character}")
        
        # 2. 生成主要内容（问候、建议、筛选）
        logger.info("正在生成主要内容（问候+建议+筛选）...")
        master_content = processor.generate_master_content(character, weather_data, news_list)
        
        result['greeting'] = master_content.get('greeting', '')
        result['weather_advice'] = {
            'beijing': master_content.get('advice_beijing', ''),
            'jinan': master_content.get('advice_jinan', '')
        }
        
        # 3. 处理选中的新闻
        selected_news = master_content.get('selected_news', [])
        logger.info(f"AI选中了 {len(selected_news)} 条新闻")

        # 构建待抓取文章列表
        articles_to_fetch = []
        for item in selected_news:
            idx = item.get('index') if isinstance(item, dict) else item
            category = item.get('category', 'C') if isinstance(item, dict) else 'C'
            if isinstance(idx, int) and 0 <= idx - 1 < len(news_list):
                news = news_list[idx - 1]
                articles_to_fetch.append({
                    'title': news['title'],
                    'url': news['url'],
                    'description': news.get('description', ''),
                    'date': news.get('date', ''),
                    'source': news.get('source', ''),
                    'category': category
                })

        # 异步抓取文章内容
        articles_to_process = []
        if articles_to_fetch:
            logger.info(f"正在异步抓取 {len(articles_to_fetch)} 篇文章详情...")
            articles_to_process = asyncio.run(fetch_articles_async(articles_to_fetch))
            logger.info(f"  - 异步抓取完成，获取 {len(articles_to_process)} 篇")

        # 4. 批量处理新闻内容
        if articles_to_process:
            logger.info("正在批量处理新闻内容...")
            processed = processor.process_news_batch(articles_to_process)

            # 添加日期和来源信息到结果中
            for i, item in enumerate(processed):
                if i < len(articles_to_process):
                    item['date'] = articles_to_process[i].get('date', '')
                    item['source'] = articles_to_process[i].get('source', '')
                    item['category'] = articles_to_process[i].get('category', 'C')

            result['processed_news'] = processed
            
        logger.info("所有AI处理完成")
        
    except Exception as e:
        logger.error(f"处理每日报告失败: {e}")
    
    return result


if __name__ == '__main__':
    # 测试代码
    from config import config
    from weather_parser import parse_weather_files
    
    # 模拟数据
    weather_data = {
        'beijing': {'weather': '晴', 'temperature': '5~15℃', 'wind': '北风3级'},
        'jinan': {'weather': '多云', 'temperature': '8~18℃', 'wind': '南风2级'}
    }
    
    news_list = [
        {'title': 'Scientists discover new planet', 'url': 'http://example.com/1'},
        {'title': 'New study on sleep patterns', 'url': 'http://example.com/2'},
        {'title': 'Breakthrough in quantum computing', 'url': 'http://example.com/3'}
    ]
    
    # AI处理
    processed_data = process_daily_report(weather_data, news_list)
    
    print(f"\n角色: {processed_data['character']}")
    print(f"问候: {processed_data['greeting']}")
    print(f"\n北京建议: {processed_data['weather_advice']['beijing']}")
    print(f"新闻数量: {len(processed_data['processed_news'])}")
