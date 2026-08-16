"""
AI 调用传输层
Gemini 模型回退链 + DeepSeek 跨厂商兜底 + 健壮的 JSON 响应解析
"""
from google import genai
from google.genai import errors as genai_errors
import json
import logging
import re

import requests

from config import config
from retry import retry_with_backoff, RetryableError

logger = logging.getLogger(__name__)

# --- Gemini 链配置 ---
RETRYABLE_STATUS_CODES = {503, 429}  # 可重试的 HTTP 状态码
RETRYABLE_STATUS_NAMES = {'UNAVAILABLE', 'RESOURCE_EXHAUSTED'}  # 可重试的 gRPC 状态名
GEMINI_RETRY_WAITS = [30]            # 每个模型重试 1 次（共尝试 2 次），退避 30 秒

# --- DeepSeek 兜底配置 ---
DEEPSEEK_REQUEST_TIMEOUT = 180       # DeepSeek 请求超时（秒）
DEEPSEEK_RETRY_WAITS = [15, 30]      # DeepSeek 重试退避等待（秒）
DEEPSEEK_RETRYABLE_CODES = {429, 500, 502, 503, 504}  # 可重试的 HTTP 状态码

# --- 响应解析配置 ---
RAW_TEXT_LOG_LIMIT = 2000    # 解析失败时打印原始返回文本的最大长度


def strip_json_comments(text: str) -> str:
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


def parse_ai_json(response_text: str, context: str):
    """健壮的 AI JSON 返回解析器

    依次容错：Markdown 代码块围栏 → 截取 JSON 主体 → // 注释 → 尾逗号。
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

    # 2. 截取首个 {...} 或 [...] 主体，丢弃前后缀说明文字
    # （须先于注释清理：否则列表后的 // 注释会干扰首尾定位；
    #  按首个出现的括号类型选主体，避免列表内的 { 被误判为对象起点）
    obj_start = text.find('{')
    arr_start = text.find('[')
    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        start, end = obj_start, text.rfind('}')
    elif arr_start != -1:
        start, end = arr_start, text.rfind(']')
    else:
        start, end = -1, -1
    if start != -1 and end > start:
        text = text[start:end + 1]

    # 3. 移除字符串外的 // 注释
    text = strip_json_comments(text)

    # 4. 清理尾逗号（{"a": 1,} 非法但模型常见）
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"{context} JSON 解析失败: {e}")
        logger.error(f"原始返回文本（前 {RAW_TEXT_LOG_LIMIT} 字符）: {response_text[:RAW_TEXT_LOG_LIMIT]}")
        raise


class AiClient:
    """AI 调用客户端：Gemini 模型回退链 + DeepSeek 跨厂商兜底"""

    def __init__(
        self,
        api_key: str,
        deepseek_api_key: str = None,
        deepseek_base_url: str = None,
        deepseek_model: str = None
    ):
        """
        Args:
            api_key: Gemini API密钥
            deepseek_api_key: 可选 DeepSeek API密钥（测试注入，默认取 config）
            deepseek_base_url: 可选 DeepSeek base URL（测试注入）
            deepseek_model: 可选 DeepSeek 模型名（测试注入）
        """
        self.client = genai.Client(api_key=api_key)
        # 模型回退链：首选 3.7-flash，高峰 503 时依次回退到 3.5-flash、2.5-pro
        self.models = ['gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-2.5-pro']
        # DeepSeek 兜底配置（Gemini 链全部失效时启用）
        self.deepseek_api_key = deepseek_api_key if deepseek_api_key is not None else config.DEEPSEEK_API_KEY
        self.deepseek_base_url = deepseek_base_url or config.DEEPSEEK_BASE_URL
        self.deepseek_model = deepseek_model or config.DEEPSEEK_MODEL
        # 最近一次成功调用使用的模型名（供邮件标签展示）
        self.last_used_model = None

    @property
    def deepseek_enabled(self) -> bool:
        """DeepSeek 兜底是否已配置（API key 非占位符）"""
        from config import DEEPSEEK_KEY_PLACEHOLDER
        return bool(self.deepseek_api_key) and self.deepseek_api_key != DEEPSEEK_KEY_PLACEHOLDER

    def _is_retryable_error(self, error: Exception) -> bool:
        """判断 Gemini 异常是否为可重试的临时错误

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

    def call(self, prompt: str, use_json: bool = True) -> str:
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

    def _call_gemini_chain(self, prompt: str, use_json: bool = True) -> str:
        """
        Gemini 模型回退链调用（指数退避重试）

        遍历模型回退链，对每个模型按 GEMINI_RETRY_WAITS 退避重试。
        临时错误（503/429/UNAVAILABLE/RESOURCE_EXHAUSTED）重试耗尽后切换下一个模型；
        非临时错误（如 400/认证失败/模型不存在）立即抛出，不做无意义回退。
        全部模型重试耗尽后抛出最后一次异常，由 call() 兜底处理。

        Args:
            prompt: 请求内容
            use_json: 是否要求 JSON 格式返回

        Returns:
            API 响应文本
        """
        genai_config = {'response_mime_type': 'application/json'} if use_json else {}

        def attempt_model(model_name: str) -> str:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_config
                )
                return response.text
            except Exception as e:
                # 临时错误包装为 RetryableError 交给退避重试；永久错误原样抛出
                if self._is_retryable_error(e):
                    raise RetryableError(str(e)) from e
                raise

        for model_idx, model_name in enumerate(self.models):
            try:
                text = retry_with_backoff(
                    lambda m=model_name: attempt_model(m),
                    waits=GEMINI_RETRY_WAITS,
                    label=model_name
                )
                self.last_used_model = model_name
                return text
            except RetryableError:
                # 当前模型重试耗尽
                if model_idx < len(self.models) - 1:
                    next_model = self.models[model_idx + 1]
                    logger.warning(f"[{model_name}] 重试耗尽，回退到下一个模型: {next_model}")
                else:
                    logger.error(f"[{model_name}] 所有模型重试耗尽，抛出异常")
                    raise

        # 理论上不会走到这里（上面循环会 return 或 raise）
        raise RuntimeError("Gemini 模型回退链为空")

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

        def attempt() -> str:
            try:
                response = requests.post(
                    url, headers=headers, json=payload,
                    timeout=DEEPSEEK_REQUEST_TIMEOUT
                )
            except requests.RequestException as e:
                # 网络错误视为临时错误
                raise RetryableError(str(e)) from e

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']

            # 非 200：区分临时/永久错误
            msg = f"DeepSeek HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code in DEEPSEEK_RETRYABLE_CODES:
                raise RetryableError(msg)
            raise RuntimeError(msg)

        result = retry_with_backoff(attempt, waits=DEEPSEEK_RETRY_WAITS, label='DeepSeek')
        self.last_used_model = self.deepseek_model
        return result
