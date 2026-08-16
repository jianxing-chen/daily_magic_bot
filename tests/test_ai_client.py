"""ai_client 传输层测试（全程 mock，零网络/零 token）

固化 2026-08 DeepSeek 兜底接入时验证过的关键场景：
跨厂商兜底、占位符禁用、Gemini 模型回退链序列、DeepSeek 重试语义。
"""
from unittest.mock import MagicMock, patch

import pytest

from ai_client import AiClient
from config import DEEPSEEK_KEY_PLACEHOLDER
from retry import RetryableError


def make_client(deepseek_key='sk-test-real-key') -> AiClient:
    return AiClient(api_key='dummy', deepseek_api_key=deepseek_key)


def ok_deepseek_response(content='{"ok": 1}'):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {'choices': [{'message': {'content': content}}]}
    return resp


class TestDeepseekEnabled:
    def test_real_key_enables_fallback(self):
        assert make_client().deepseek_enabled is True

    def test_placeholder_disables_fallback(self):
        assert make_client(DEEPSEEK_KEY_PLACEHOLDER).deepseek_enabled is False


class TestCrossVendorFallback:
    def test_gemini_failure_falls_back_to_deepseek(self):
        client = make_client()
        client._call_gemini_chain = MagicMock(side_effect=RuntimeError('Gemini全挂'))

        with patch('ai_client.requests.post', return_value=ok_deepseek_response()) as mock_post:
            result = client.call('测试prompt', use_json=True)

        assert result == '{"ok": 1}'
        # 请求体正确：URL / 模型 / JSON 模式 / Bearer 鉴权
        call = mock_post.call_args
        assert call.args[0] == 'https://api.deepseek.com/chat/completions'
        assert call.kwargs['json']['model'] == 'deepseek-v4-flash'
        assert call.kwargs['json']['response_format'] == {'type': 'json_object'}
        assert call.kwargs['headers']['Authorization'] == 'Bearer sk-test-real-key'

    def test_deepseek_disabled_raises_original_error(self):
        client = make_client(DEEPSEEK_KEY_PLACEHOLDER)
        client._call_gemini_chain = MagicMock(side_effect=RuntimeError('Gemini全挂'))
        with pytest.raises(RuntimeError, match='Gemini全挂'):
            client.call('测试')

    def test_deepseek_failure_also_raises(self):
        client = make_client()
        client._call_gemini_chain = MagicMock(side_effect=RuntimeError('Gemini全挂'))
        resp_500 = MagicMock(status_code=500, text='server error')
        # 跳过退避重试（直接执行单次尝试），500 属可重试错误 → RetryableError 向上抛
        with patch('ai_client.requests.post', return_value=resp_500), \
             patch('ai_client.retry_with_backoff', side_effect=lambda fn, **kw: fn()):
            with pytest.raises(RetryableError):
                client.call('测试')


class TestGeminiChain:
    def _chain_client(self, fail_models=('gemini-3.5-flash',)):
        """构造 mock genai 客户端：指定模型抛 503，其余成功"""
        client = make_client(DEEPSEEK_KEY_PLACEHOLDER)
        calls = []

        def fake_generate(model, contents, config):
            calls.append(model)
            if model in fail_models:
                raise RetryableError('503 overloaded')
            resp = MagicMock()
            resp.text = '成功'
            return resp

        client.client = MagicMock()
        client.client.models.generate_content = fake_generate
        return client, calls

    def test_model_fallback_sequence(self):
        """3.5-flash 重试耗尽（2 次尝试）→ 切换 3-flash-preview 成功"""
        client, calls = self._chain_client()
        with patch('retry.time.sleep') as mock_sleep:
            result = client._call_gemini_chain('测试')

        assert result == '成功'
        assert calls == ['gemini-3.5-flash', 'gemini-3.5-flash', 'gemini-3-flash-preview']
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args.args[0] == 30  # GEMINI_RETRY_WAITS = [30]

    def test_all_models_exhausted_raises(self):
        client, _ = self._chain_client(fail_models=(
            'gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-pro'))
        with patch('retry.time.sleep'):
            with pytest.raises(RetryableError):
                client._call_gemini_chain('测试')

    def test_first_model_success_no_fallback(self):
        client, calls = self._chain_client(fail_models=())
        result = client._call_gemini_chain('测试')
        assert result == '成功'
        assert calls == ['gemini-3.5-flash']


class TestDeepseekRetry:
    def test_retryable_status_retries_then_succeeds(self):
        client = make_client()
        resp_429 = MagicMock(status_code=429, text='rate limit')
        with patch('ai_client.requests.post', side_effect=[resp_429, ok_deepseek_response()]) as mp, \
             patch('retry.time.sleep') as ms:
            result = client._call_deepseek('测试')

        assert result == '{"ok": 1}'
        assert mp.call_count == 2 and ms.call_count == 1
        assert ms.call_args.args[0] == 15  # DEEPSEEK_RETRY_WAITS = [15, 30]

    def test_permanent_error_raises_immediately(self):
        client = make_client()
        resp_401 = MagicMock(status_code=401, text='auth fail')
        with patch('ai_client.requests.post', return_value=resp_401) as mp, \
             patch('retry.time.sleep') as ms:
            with pytest.raises(RuntimeError, match='401'):
                client._call_deepseek('测试')

        assert mp.call_count == 1  # 永久错误不重试
        assert ms.call_count == 0
