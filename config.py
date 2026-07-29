"""
配置管理模块
加载环境变量和应用配置
"""
import os
import re
from dotenv import load_dotenv
from pathlib import Path
from typing import List

# 加载.env文件
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 邮箱格式正则（RFC 5322 简化版）
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class Config:
    """应用配置类"""

    def __init__(self):
        """从环境变量加载配置"""
        # Gemini API配置
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your_api_key_here')

        # 邮箱配置
        self.SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
        self.SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your_email@gmail.com')
        self.SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'your_app_password')
        self.SENDER_NAME = os.getenv('SENDER_NAME', 'Daily Magic Bot')
        self.RECEIVER_EMAILS = [
            e.strip()
            for e in os.getenv('RECEIVER_EMAILS', 'email1@example.com,email2@example.com').split(',')
            if e.strip()
        ]

        # 天气数据来源（weather.com.cn）
        self.BEIJING_WEATHER_URL = 'https://www.weather.com.cn/weather1d/101011700.shtml'
        self.JINAN_WEATHER_URL = 'https://www.weather.com.cn/weather1d/101120107.shtml'

        # 哈利波特角色列表
        self.HARRY_POTTER_CHARACTERS = [
            '多比', '哈利·波特', '麦格教授', '邓布利多', '赫敏·格兰杰',
            '罗恩·韦斯莱', '斯内普教授', '海格', '卢娜·洛夫古德',
            '纳威·隆巴顿', '金妮·韦斯莱', '小天狼星布莱克', '卢平教授',
            '韦斯莱先生', '韦斯莱夫人', '斯拉格霍恩教授', '西比尔·特里劳妮'
        ]

    def validate(self) -> List[str]:
        """验证配置

        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []

        if self.GEMINI_API_KEY == 'your_api_key_here':
            errors.append('请配置GEMINI_API_KEY')

        if self.SENDER_EMAIL == 'your_email@gmail.com':
            errors.append('请配置SENDER_EMAIL')
        elif not EMAIL_PATTERN.match(self.SENDER_EMAIL):
            errors.append(f'SENDER_EMAIL 格式不正确: {self.SENDER_EMAIL}')

        if self.SENDER_PASSWORD == 'your_app_password':
            errors.append('请配置SENDER_PASSWORD')

        if not self.RECEIVER_EMAILS or all(e.endswith('@example.com') for e in self.RECEIVER_EMAILS):
            errors.append('请配置RECEIVER_EMAILS')
        else:
            invalid = [e for e in self.RECEIVER_EMAILS if not EMAIL_PATTERN.match(e)]
            if invalid:
                errors.append(f'RECEIVER_EMAILS 包含无效邮箱: {", ".join(invalid)}')

        return errors


# 导出配置单例
config = Config()
