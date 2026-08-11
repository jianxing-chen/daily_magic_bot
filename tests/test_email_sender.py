"""email_sender SMTP 发送测试（mock smtplib，不真实发送）

锁定 2026-08 重构后的重试语义：任何 SMTP 失败均退避重试（5s→15s→30s），
重试耗尽返回 False 而非抛异常（保证上层流程可控）。
"""
import smtplib
from unittest.mock import patch, MagicMock

from email_sender import EmailSender


def make_sender(port: int = 587) -> EmailSender:
    return EmailSender('smtp.example.com', port, 'a@example.com', 'pw')


class TestSendEmail:
    def test_send_success_first_attempt(self):
        sender = make_sender()
        server = MagicMock()
        with patch('email_sender.smtplib.SMTP', return_value=server):
            ok = sender.send_email(['r@example.com'], 'subject', '<html></html>')
        assert ok is True
        server.starttls.assert_called_once()
        server.login.assert_called_once_with('a@example.com', 'pw')
        server.send_message.assert_called_once()
        server.quit.assert_called_once()

    def test_retries_then_succeeds(self):
        sender = make_sender()
        bad = MagicMock()
        bad.send_message.side_effect = smtplib.SMTPException('450 busy')
        good = MagicMock()
        with patch('email_sender.smtplib.SMTP', side_effect=[bad, good]), \
             patch('retry.time.sleep') as mock_sleep:
            ok = sender.send_email(['r@example.com'], 's', '<html></html>')
        assert ok is True
        assert mock_sleep.call_count == 1  # 第一次失败后退避一次

    def test_all_retries_exhausted_returns_false(self):
        sender = make_sender()
        bad = MagicMock()
        bad.send_message.side_effect = smtplib.SMTPException('550 fail')
        with patch('email_sender.smtplib.SMTP', return_value=bad), \
             patch('retry.time.sleep'):
            ok = sender.send_email(['r@example.com'], 's', '<html></html>')
        assert ok is False
        assert bad.send_message.call_count == 3  # 默认 max_retries=3

    def test_ssl_port_uses_smtp_ssl(self):
        sender = make_sender(port=465)
        server = MagicMock()
        with patch('email_sender.smtplib.SMTP_SSL', return_value=server) as ssl_cls, \
             patch('email_sender.smtplib.SMTP') as plain_cls:
            ok = sender.send_email(['r@example.com'], 's', '<html></html>')
        assert ok is True
        ssl_cls.assert_called_once()
        plain_cls.assert_not_called()
        server.starttls.assert_not_called()


class TestTestConnection:
    def test_connect_login_quit(self):
        sender = make_sender()
        server = MagicMock()
        with patch('email_sender.smtplib.SMTP', return_value=server):
            sender.test_connection()
        server.login.assert_called_once()
        server.quit.assert_called_once()


class TestCreateTestEmail:
    def test_renders_time_placeholder(self):
        html = make_sender().create_test_email()
        assert '邮件配置正常' in html
        assert '{{' not in html  # 模板变量已被渲染
