"""retry_with_backoff 通用重试工具单元测试（mock sleep，零等待）"""
from unittest.mock import patch

import pytest

from retry import retry_with_backoff, RetryableError


class TestRetryWithBackoff:
    def test_success_first_attempt(self):
        calls = []

        def fn():
            calls.append(1)
            return 'ok'

        with patch('retry.time.sleep') as mock_sleep:
            assert retry_with_backoff(fn, waits=[1, 2], label='测试') == 'ok'

        assert len(calls) == 1
        assert mock_sleep.call_count == 0

    def test_retryable_error_retries_with_backoff(self):
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RetryableError('临时错误')
            return 'ok'

        with patch('retry.time.sleep') as mock_sleep:
            result = retry_with_backoff(fn, waits=[10, 20], label='测试')

        assert result == 'ok'
        assert len(calls) == 3
        # 两次退避按 waits 顺序执行
        assert [c.args[0] for c in mock_sleep.call_args_list] == [10, 20]

    def test_exhausted_raises_last_error(self):
        calls = []

        def fn():
            calls.append(1)
            raise RetryableError('一直失败')

        with patch('retry.time.sleep'):
            with pytest.raises(RetryableError, match='一直失败'):
                retry_with_backoff(fn, waits=[1, 2], label='测试')

        assert len(calls) == 3  # waits 长度 2 → 共尝试 3 次

    def test_non_retryable_error_raises_immediately(self):
        calls = []

        def fn():
            calls.append(1)
            raise ValueError('永久错误')

        with patch('retry.time.sleep') as mock_sleep:
            with pytest.raises(ValueError, match='永久错误'):
                retry_with_backoff(fn, waits=[1, 2], label='测试')

        assert len(calls) == 1  # 不重试
        assert mock_sleep.call_count == 0

    def test_custom_retryable_predicate(self):
        """自定义谓词：仅特定异常可重试（如 SMTP 的全量重试语义）"""
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 2:
                raise ValueError('任意错误')
            return 'ok'

        with patch('retry.time.sleep'):
            result = retry_with_backoff(
                fn, waits=[5], label='SMTP', retryable=lambda e: True)

        assert result == 'ok'
        assert len(calls) == 2

    def test_empty_waits_single_attempt(self):
        calls = []

        def fn():
            calls.append(1)
            raise RetryableError('失败')

        with pytest.raises(RetryableError):
            retry_with_backoff(fn, waits=[], label='测试')
        assert len(calls) == 1
