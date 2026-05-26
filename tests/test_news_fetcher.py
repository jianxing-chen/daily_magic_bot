"""
测试新闻抓取模块的日期解析逻辑
"""
import pytest
from datetime import datetime
from news_fetcher import MultiSourceNewsFetcher


class TestDateParsing:
    """测试日期解析功能"""

    def setup_method(self):
        self.fetcher = MultiSourceNewsFetcher()

    def test_parse_rss_date_rfc822(self):
        """解析 RFC 822 格式的 RSS 日期"""
        result = self.fetcher._parse_rss_date("Sun, 08 Dec 2025 05:00:00 GMT")
        assert result == "2025-12-08"

    def test_parse_rss_date_iso(self):
        """解析 ISO 格式的 RSS 日期"""
        result = self.fetcher._parse_rss_date("2025-12-08T05:00:00Z")
        assert result == "2025-12-08"

    def test_parse_rss_date_empty(self):
        """空日期返回今天"""
        result = self.fetcher._parse_rss_date("")
        today = datetime.now().strftime('%Y-%m-%d')
        assert result == today

    def test_parse_rss_date_none(self):
        """None 日期返回今天"""
        result = self.fetcher._parse_rss_date(None)
        today = datetime.now().strftime('%Y-%m-%d')
        assert result == today

    def test_parse_date_standard(self):
        """解析标准 YYYY-MM-DD 格式"""
        result = self.fetcher._parse_date("2025-12-08")
        assert result == "2025-12-08"

    def test_parse_date_nature_format(self):
        """解析 Nature 网站日期格式 (DD MON YYYY)"""
        result = self.fetcher._parse_date("08 Dec 2025")
        assert result == "2025-12-08"

    def test_parse_date_empty(self):
        """空日期返回今天"""
        result = self.fetcher._parse_date("")
        today = datetime.now().strftime('%Y-%m-%d')
        assert result == today

    def test_filter_recent_news(self):
        """测试新闻日期过滤"""
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now().strptime(today, '%Y-%m-%d')).strftime('%Y-%m-%d')  # just use today
        news_list = [
            {'title': 'Recent', 'url': 'http://1', 'date': today},
            {'title': 'Old', 'url': 'http://2', 'date': '2020-01-01'},
        ]
        filtered = self.fetcher._filter_recent_news(news_list, days=1)
        assert len(filtered) == 1
        assert filtered[0]['title'] == 'Recent'
