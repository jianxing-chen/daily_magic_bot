"""
测试邮件模块
"""
import pytest
from email_sender import EmailSender


class TestSourceNameSimplification:
    """测试来源名称简化"""

    def setup_method(self):
        self.sender = EmailSender("smtp.test.com", 587, "test@test.com", "password")

    def test_nature_news_maps_to_nature(self):
        assert self.sender._simplify_source_name("Nature News") == "Nature"

    def test_nature_keeps_nature(self):
        assert self.sender._simplify_source_name("Nature") == "Nature"

    def test_nature_astronomy_abbreviates(self):
        assert self.sender._simplify_source_name("Nature Astronomy") == "Nat Astron"

    def test_sciencedaily_variants(self):
        assert self.sender._simplify_source_name("ScienceDaily Top") == "ScienceDaily"
        assert self.sender._simplify_source_name("ScienceDaily Brain") == "ScienceDaily"

    def test_unknown_source_passthrough(self):
        """未知源名称原样返回"""
        assert self.sender._simplify_source_name("Unknown Source") == "Unknown Source"

    def test_psypost(self):
        assert self.sender._simplify_source_name("PsyPost") == "PsyPost"


class TestCityWeatherHTML:
    """测试城市天气 HTML 生成"""

    def setup_method(self):
        self.sender = EmailSender("smtp.test.com", 587, "test@test.com", "password")

    def test_basic_weather_html(self):
        weather = {
            'weather': '晴',
            'temperature': '5~15°C',
            'wind': '北风3级',
            'sunrise': '06:30',
            'sunset': '17:00',
            'alerts': []
        }
        html = self.sender._generate_city_weather('北京', weather, '注意保暖')
        assert '北京' in html
        assert '晴' in html
        assert '5~15°C' in html
        assert '注意保暖' in html

    def test_weather_with_alerts(self):
        weather = {
            'weather': '雨',
            'temperature': '3~8°C',
            'wind': '东风2级',
            'sunrise': '06:30',
            'sunset': '17:00',
            'alerts': ['暴雨预警', '大风预警']
        }
        html = self.sender._generate_city_weather('济南', weather, '')
        assert '暴雨预警' in html
        assert '大风预警' in html
        assert 'weather-alert' in html


class TestNewsSectionHTML:
    """测试新闻板块 HTML 生成"""

    def setup_method(self):
        self.sender = EmailSender("smtp.test.com", 587, "test@test.com", "password")

    def test_empty_news_returns_empty(self):
        assert self.sender._generate_news_section([]) == ""
        assert self.sender._generate_news_section(None) == ""

    def test_news_with_category(self):
        news = [{
            'title_cn': '测试标题',
            'title_en': 'Test Title',
            'summary': '测试摘要',
            'url': 'https://example.com',
            'date': '2025-12-08',
            'source': 'Nature',
            'category': 'A'
        }]
        html = self.sender._generate_news_section(news)
        assert '天体物理' in html
        assert '测试标题' in html
        assert 'Test Title' in html
