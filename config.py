"""
配置管理模块
加载环境变量和应用配置
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# 加载.env文件
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """应用配置类"""
    
    # Gemini API配置
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your_api_key_here')
    
    # 邮箱配置
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your_email@gmail.com')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'your_app_password')
    RECEIVER_EMAILS = os.getenv('RECEIVER_EMAILS', 'email1@example.com,email2@example.com').split(',')
    
    # 天气数据来源（weather.com.cn）
    BEIJING_WEATHER_URL = 'https://www.weather.com.cn/weather1d/101011700.shtml'
    JINAN_WEATHER_URL = 'https://www.weather.com.cn/weather1d/101120107.shtml'
    
    # 哈利波特角色列表
    HARRY_POTTER_CHARACTERS = [
        '多比', '哈利·波特', '麦格教授', '邓布利多', '赫敏·格兰杰',
        '罗恩·韦斯莱', '斯内普教授', '海格', '卢娜·洛夫古德', 
        '纳威·隆巴顿', '金妮·韦斯莱', '小天狼星布莱克', '卢平教授',
        '韦斯莱先生', '韦斯莱夫人', '斯拉格霍恩教授', '西比尔·特里劳妮'
    ]
    
    @classmethod
    def validate(cls):
        """验证配置"""
        errors = []
        
        if cls.GEMINI_API_KEY == 'your_api_key_here':
            errors.append('请配置GEMINI_API_KEY')
        
        if cls.SENDER_EMAIL == 'your_email@gmail.com':
            errors.append('请配置SENDER_EMAIL')
        
        if cls.SENDER_PASSWORD == 'your_app_password':
            errors.append('请配置SENDER_PASSWORD')
        
        if not cls.RECEIVER_EMAILS or cls.RECEIVER_EMAILS == ['email1@example.com', 'email2@example.com']:
            errors.append('请配置RECEIVER_EMAILS')
        
        return errors

# 导出配置实例
config = Config()
