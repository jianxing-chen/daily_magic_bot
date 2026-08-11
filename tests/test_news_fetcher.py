"""news_fetcher 离线测试（不发网络请求）

覆盖源头文本清洗、日期解析、时效过滤等纯逻辑。
"""
from datetime import datetime, timedelta

from news_fetcher import MultiSourceNewsFetcher, clean_text


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("title\nwith  newlines\t here") == "title with newlines here"

    def test_strips_html_residue_edges(self):
        assert clean_text("  trimmed  ") == "trimmed"

    def test_none_and_empty(self):
        assert clean_text(None) == ""
        assert clean_text("") == ""


class TestDateParsing:
    def setup_method(self):
        self.fetcher = MultiSourceNewsFetcher()

    def test_parse_iso_date(self):
        assert self.fetcher._parse_date('2026-08-11') == '2026-08-11'

    def test_parse_month_name_date(self):
        assert self.fetcher._parse_date('03 DEC 2025') == '2025-12-03'

    def test_unparseable_date_falls_back_to_today(self):
        assert self.fetcher._parse_date('not a date') == datetime.now().strftime('%Y-%m-%d')

    def test_rss_rfc822_date_format(self):
        # RFC 822 日期应解析为 YYYY-MM-DD 格式（具体日期受本地时区影响，只验证格式）
        result = self.fetcher._parse_rss_date('Sun, 08 Dec 2025 05:00:00 GMT')
        parts = result.split('-')
        assert len(parts) == 3 and all(p.isdigit() for p in parts)


class TestFilterRecentNews:
    def setup_method(self):
        self.fetcher = MultiSourceNewsFetcher()

    def test_keeps_recent_and_drops_old(self):
        today = datetime.now().strftime('%Y-%m-%d')
        old = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        news = [
            {'title': 'fresh', 'date': today},
            {'title': 'stale', 'date': old},
        ]
        filtered = self.fetcher._filter_recent_news(news, days=1)
        assert [n['title'] for n in filtered] == ['fresh']
