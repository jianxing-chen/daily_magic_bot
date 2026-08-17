"""gemini_processor 全流程重试与极端保底测试（全程 mock，零网络/零 token）

覆盖 2026-08 的可靠性强化：
1. 主内容/批量处理多轮全流程重试（每轮走 Gemini 链 + DeepSeek），
   临时失败与非法 JSON 可在后续轮次恢复，内容确保由真实 AI 生成
2. 模型标签始终为真实模型名；所有轮次失败时 used_model 为空，不显示虚假名称
3. 极端保底文案基于真实天气数据构造，字段结构与正常返回一致
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

from retry import RetryableError
from gemini_processor import (
    GeminiProcessor, process_daily_report,
    MASTER_RETRY_WAITS, BATCH_RETRY_WAITS
)
from email_sender import EmailSender
from config import config

MOCK_WEATHER = {
    'beijing': {
        'city': '北京', 'weather': '雷阵雨', 'temperature': '23~30°C',
        'wind': '北风3级', 'alerts': ['雷电黄色预警']
    },
    'jinan': {
        'city': '济南', 'weather': '小雨', 'temperature': '2~10°C',
        'wind': '南风5级', 'alerts': []
    }
}

MOCK_NEWS = [
    {'title': f'news{i}', 'url': f'http://example.com/{i}', 'source': 'Nature', 'date': '2026-08-16'}
    for i in range(20)
]

VALID_MASTER_JSON = json.dumps({
    'greeting': '早安！今天北京雷阵雨，出门带伞。',
    'advice_beijing': '带伞防雷。',
    'advice_jinan': '注意保暖。',
    'selected_news': [{'index': 1, 'category': 'A'}]
})

VALID_BATCH_JSON = json.dumps([{'title_cn': '中文标题', 'summary': '总结内容'}])


def make_processor() -> GeminiProcessor:
    """构造 AiClient 被完全 mock 的处理器"""
    proc = GeminiProcessor('dummy')
    proc.ai = MagicMock()
    proc.ai.last_used_model = 'gemini-3.5-flash'
    return proc


class TestMasterContentRetry:
    def test_success_first_round_real_model(self):
        proc = make_processor()
        proc.ai.call.return_value = VALID_MASTER_JSON

        result = proc.generate_master_content('邓布利多', MOCK_WEATHER, MOCK_NEWS)

        assert result['greeting'] == '早安！今天北京雷阵雨，出门带伞。'
        assert proc.used_model == 'gemini-3.5-flash'  # 真实模型名
        assert proc.ai.call.call_count == 1

    def test_retry_recovers_after_transient_failure(self):
        # 第 1 轮临时失败（如 503 高峰），第 2 轮恢复 → 内容由真实 AI 生成
        proc = make_processor()
        proc.ai.call.side_effect = [RuntimeError('503 UNAVAILABLE'), VALID_MASTER_JSON]

        with patch('retry.time.sleep') as mock_sleep:
            result = proc.generate_master_content('邓布利多', MOCK_WEATHER, MOCK_NEWS)

        assert result['advice_beijing'] == '带伞防雷。'
        assert proc.used_model == 'gemini-3.5-flash'
        assert proc.ai.call.call_count == 2
        assert mock_sleep.call_args.args[0] == MASTER_RETRY_WAITS[0]

    def test_retry_recovers_from_bad_json(self):
        # 第 1 轮返回非法 JSON，第 2 轮返回合法 JSON → 解析失败也触发重试
        proc = make_processor()
        proc.ai.call.side_effect = ['这不是JSON', VALID_MASTER_JSON]

        with patch('retry.time.sleep'):
            result = proc.generate_master_content('邓布利多', MOCK_WEATHER, MOCK_NEWS)

        assert result['greeting']
        assert proc.ai.call.call_count == 2

    def test_all_rounds_fail_last_resort_no_fake_model(self):
        # 所有轮次全挂 → 天气感知保底文案，used_model 为空（不显示虚假模型名）
        proc = make_processor()
        proc.ai.call.side_effect = RuntimeError('AI 全挂')

        with patch('retry.time.sleep') as mock_sleep:
            result = proc.generate_master_content('邓布利多', MOCK_WEATHER, MOCK_NEWS)

        assert proc.used_model is None
        assert proc.ai.call.call_count == len(MASTER_RETRY_WAITS) + 1  # 3 轮
        # 保底内容基于真实天气，字段结构与正常返回一致
        assert set(result.keys()) == {'greeting', 'advice_beijing', 'advice_jinan', 'selected_news'}
        assert '雷阵雨' in result['greeting']
        assert '雷电黄色预警' in result['advice_beijing']
        assert '带伞' in result['advice_jinan']

    def test_last_resort_advice_empty_weather_generic(self):
        proc = make_processor()
        assert proc._fallback_advice({}) == '请注意天气变化。'
        assert proc._fallback_advice(None) == '请注意天气变化。'


class TestNewsBatchRetry:
    def test_batch_retry_then_success(self):
        proc = make_processor()
        proc.ai.call.side_effect = [RuntimeError('503'), VALID_BATCH_JSON]

        with patch('retry.time.sleep'):
            result = proc.process_news_batch([{'title': 'T', 'content': 'C', 'url': 'u'}])

        assert result[0]['title_cn'] == '中文标题'
        assert proc.ai.call.call_count == 2

    def test_batch_non_list_triggers_retry_not_silent_drop(self):
        # 非列表返回不再静默丢失全部新闻，而是触发重试
        proc = make_processor()
        proc.ai.call.side_effect = ['{"not": "a list"}', VALID_BATCH_JSON]

        with patch('retry.time.sleep'):
            result = proc.process_news_batch([{'title': 'T', 'content': 'C', 'url': 'u'}])

        assert len(result) == 1
        assert proc.ai.call.call_count == 2

    def test_batch_all_rounds_fail_placeholder(self):
        proc = make_processor()
        proc.ai.call.side_effect = RuntimeError('AI 全挂')

        with patch('retry.time.sleep'):
            result = proc.process_news_batch([{'title': 'T', 'content': 'C', 'url': 'u'}])

        assert proc.ai.call.call_count == len(BATCH_RETRY_WAITS) + 1  # 2 轮
        assert result[0]['summary'] == 'AI处理失败，请查看原文'


class TestProcessDailyReportModel:
    def test_model_is_real_name_on_success(self):
        proc = make_processor()
        proc.ai.call.side_effect = [VALID_MASTER_JSON, VALID_BATCH_JSON]

        with patch('gemini_processor.fetch_articles_async', new=AsyncMock(return_value=[])):
            result = process_daily_report(MOCK_WEATHER, MOCK_NEWS, processor=proc)

        assert result['model'] == 'gemini-3.5-flash'
        assert result['greeting']

    def test_model_empty_on_total_failure_no_fake_label(self):
        # AI 全挂时 model 为空（邮件隐藏标签），绝不显示虚假模型名
        proc = make_processor()
        proc.ai.call.side_effect = RuntimeError('AI 全挂')

        with patch('gemini_processor.fetch_articles_async', new=AsyncMock(return_value=[])), \
             patch('retry.time.sleep'):
            result = process_daily_report(MOCK_WEATHER, MOCK_NEWS, processor=proc)

        assert result['model'] == ''
        assert result['greeting']  # 天气感知保底问候仍存在
        assert result['weather_advice']['beijing']

    def test_used_model_initialized_before_any_call(self):
        proc = GeminiProcessor('dummy')
        assert proc.used_model is None


def render_email(result: dict, weather=None) -> str:
    """用 process_daily_report 结果渲染邮件 HTML"""
    sender = EmailSender(
        config.SMTP_SERVER, config.SMTP_PORT,
        config.SENDER_EMAIL, config.SENDER_PASSWORD, config.SENDER_NAME
    )
    return sender.create_html_email(weather or MOCK_WEATHER, {
        'greeting': result['greeting'],
        'character': result['character'],
        'weather_advice': result['weather_advice'],
        'model': result['model']
    }, None)


class TestModelTagInRealEmail:
    def test_all_ai_fail_email_has_no_fallback_and_tag_hidden(self):
        # ① 全部 AI 失败：邮件 HTML 不得出现 'fallback' 字样，model-tag 隐藏，
        #    天气建议为天气感知文案而非通用套话
        proc = make_processor()
        proc.ai.call.side_effect = RuntimeError('AI 全挂')

        with patch('gemini_processor.fetch_articles_async', new=AsyncMock(return_value=[])), \
             patch('retry.time.sleep'):
            result = process_daily_report(MOCK_WEATHER, MOCK_NEWS, processor=proc)

        html = render_email(result)
        assert 'fallback' not in html
        assert 'class="model-tag"' not in html  # 标签隐藏，不显示虚假名称
        assert '雷阵雨' in result['greeting']  # 天气感知保底问候
        assert '雷电黄色预警' in result['weather_advice']['beijing']
        assert '请注意天气变化' not in result['weather_advice']['beijing']

    def test_gemini_chain_fail_deepseek_success_shows_deepseek_model(self):
        # ② Gemini 三模型全挂、DeepSeek 兜底成功：标签显示 DeepSeek 真实模型名
        proc = GeminiProcessor('dummy', deepseek_api_key='sk-test-real-key')

        def fail_all_models(model, contents, config):
            raise RetryableError('503 UNAVAILABLE')

        proc.ai.client = MagicMock()
        proc.ai.client.models.generate_content = fail_all_models

        deepseek_resp = MagicMock(status_code=200)
        deepseek_resp.json.return_value = {
            'choices': [{'message': {'content': VALID_MASTER_JSON}}]
        }

        with patch('ai_client.requests.post', return_value=deepseek_resp), \
             patch('retry.time.sleep'):
            result = proc.generate_master_content('邓布利多', MOCK_WEATHER, MOCK_NEWS)

        # 真实链路：Gemini 链 3 模型×2 次全 503 → DeepSeek 成功
        assert proc.used_model == 'deepseek-v4-flash'
        assert result['greeting'] == '早安！今天北京雷阵雨，出门带伞。'

        html = render_email({
            'greeting': result['greeting'],
            'character': '邓布利多',
            'weather_advice': {
                'beijing': result['advice_beijing'],
                'jinan': result['advice_jinan']
            },
            'model': proc.used_model
        })
        assert 'class="model-tag"' in html
        assert 'deepseek-v4-flash' in html  # 标签显示 DeepSeek 真实模型名
        assert 'fallback' not in html
