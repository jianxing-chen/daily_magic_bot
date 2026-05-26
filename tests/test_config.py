"""
测试配置验证逻辑
"""
import os
import pytest
from config import Config


class TestConfigValidate:
    """测试 Config.validate() 方法"""

    def test_default_values_trigger_errors(self, monkeypatch):
        """默认占位符值应该触发验证错误"""
        monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'your_api_key_here')
        monkeypatch.setattr(Config, 'SENDER_EMAIL', 'your_email@gmail.com')
        monkeypatch.setattr(Config, 'SENDER_PASSWORD', 'your_app_password')
        monkeypatch.setattr(Config, 'RECEIVER_EMAILS', ['email1@example.com', 'email2@example.com'])

        errors = Config.validate()
        assert len(errors) == 4

    def test_valid_config_passes(self, monkeypatch):
        """有效配置应该通过验证"""
        monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'AIzaSyTestKey123')
        monkeypatch.setattr(Config, 'SENDER_EMAIL', 'real@qq.com')
        monkeypatch.setattr(Config, 'SENDER_PASSWORD', 'realpassword')
        monkeypatch.setattr(Config, 'RECEIVER_EMAILS', ['real@foxmail.com'])

        errors = Config.validate()
        assert len(errors) == 0

    def test_single_receiver_email_passes(self, monkeypatch):
        """单个收件人邮箱应该通过验证"""
        monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'AIzaSyTestKey123')
        monkeypatch.setattr(Config, 'SENDER_EMAIL', 'real@qq.com')
        monkeypatch.setattr(Config, 'SENDER_PASSWORD', 'realpassword')
        monkeypatch.setattr(Config, 'RECEIVER_EMAILS', ['single@test.com'])

        errors = Config.validate()
        assert not any('RECEIVER_EMAILS' in e for e in errors)

    def test_empty_receiver_emails_fails(self, monkeypatch):
        """空的收件人列表应该触发验证错误"""
        monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'AIzaSyTestKey123')
        monkeypatch.setattr(Config, 'SENDER_EMAIL', 'real@qq.com')
        monkeypatch.setattr(Config, 'SENDER_PASSWORD', 'realpassword')
        monkeypatch.setattr(Config, 'RECEIVER_EMAILS', [])

        errors = Config.validate()
        assert any('RECEIVER_EMAILS' in e for e in errors)

    def test_invalid_email_format_fails(self, monkeypatch):
        """无效邮箱格式应该触发验证错误"""
        monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'AIzaSyTestKey123')
        monkeypatch.setattr(Config, 'SENDER_EMAIL', 'real@qq.com')
        monkeypatch.setattr(Config, 'SENDER_PASSWORD', 'realpassword')
        monkeypatch.setattr(Config, 'RECEIVER_EMAILS', ['not-an-email'])

        errors = Config.validate()
        assert any('格式不正确' in e for e in errors)
