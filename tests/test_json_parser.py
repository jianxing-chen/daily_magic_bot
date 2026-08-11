"""AI 返回健壮解析与 prompt 辅助函数测试

用例来源于 2026-08 实际故障排查中积累的 9 种模型返回畸形形态，
任何一条失败都意味着"AI 返回 200 OK 但整体兜底"的旧 bug 可能回归。
"""
import json

import pytest

from ai_client import parse_ai_json, strip_json_comments
from prompts import clean_text, format_city_weather


class TestParseAiJson:
    """9 种畸形返回形态 + 负例"""

    def test_pure_json(self):
        text = '{"greeting": "hi", "selected_news": [{"index": 1, "category": "A"}]}'
        result = parse_ai_json(text, "测试")
        assert result["greeting"] == "hi"
        assert result["selected_news"][0]["category"] == "A"

    def test_markdown_fence(self):
        text = '```json\n{"greeting": "hi"}\n```'
        assert parse_ai_json(text, "测试") == {"greeting": "hi"}

    def test_trailing_comment(self):
        # prompt 示例曾含 // 注释，模型会模仿回显
        text = '{"greeting": "hi"}  // 选中的新闻'
        assert parse_ai_json(text, "测试") == {"greeting": "hi"}

    def test_inline_comment(self):
        text = '{"greeting": "hi", // 问候语\n"advice_beijing": "a"}'
        result = parse_ai_json(text, "测试")
        assert result == {"greeting": "hi", "advice_beijing": "a"}

    def test_trailing_comma(self):
        text = '{"greeting": "hi", "selected_news": [{"index": 1},],}'
        result = parse_ai_json(text, "测试")
        assert result["selected_news"] == [{"index": 1}]

    def test_prefix_suffix_chatter(self):
        text = '好的，以下是结果：{"greeting": "hi"} 希望有帮助！'
        assert parse_ai_json(text, "测试") == {"greeting": "hi"}

    def test_url_not_stripped_as_comment(self):
        # 字符串内的 https:// 不能被当作注释清掉
        text = '{"url": "https://nature.com/a"}'
        assert parse_ai_json(text, "测试") == {"url": "https://nature.com/a"}

    def test_list_response_for_batch(self):
        text = '[{"title_cn": "测试"}] // 新闻列表'
        assert parse_ai_json(text, "测试") == [{"title_cn": "测试"}]

    def test_fence_and_comment_combined(self):
        text = '```json\n{"a": 1} // 注释\n```'
        assert parse_ai_json(text, "测试") == {"a": 1}

    def test_invalid_input_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_ai_json("完全不是JSON", "负例测试")


class TestStripJsonComments:
    """// 注释清理的边界情况"""

    def test_protects_url_in_string(self):
        text = '{"u": "http://x.com"} // c'
        assert strip_json_comments(text) == '{"u": "http://x.com"} '

    def test_escaped_quote_in_string(self):
        # 转义引号不应破坏字符串内外判断
        text = '{"s": "a\\"b"} // c'
        result = strip_json_comments(text)
        assert json.loads(result) == {"s": 'a"b'}

    def test_no_comment_unchanged(self):
        text = '{"a": 1}'
        assert strip_json_comments(text) == text


class TestCleanText:
    def test_collapses_newlines_and_spaces(self):
        assert clean_text("a\n\nb   c") == "a b c"

    def test_strips_edges(self):
        assert clean_text("  hi  ") == "hi"

    def test_none_and_empty(self):
        assert clean_text(None) == ""
        assert clean_text("") == ""


class TestFormatCityWeather:
    def test_full_fields_without_alerts(self):
        data = {
            'weather': '晴', 'temperature': '23~33°C', 'wind': '南风 <3级',
            'current_temp': '30°C', 'sunrise': '05:22', 'sunset': '19:17',
            'alerts': []
        }
        line = format_city_weather('北京', data)
        assert line.startswith('- 北京：')
        assert '23~33°C' in line
        assert '当前实况 30°C' in line
        assert '日出 05:22' in line
        assert '预警' not in line

    def test_alerts_appended(self):
        data = {'weather': '暴雨', 'alerts': ['暴雨橙色预警']}
        line = format_city_weather('济南', data)
        assert '⚠️预警: 暴雨橙色预警' in line

    def test_missing_fields_default_to_unknown(self):
        line = format_city_weather('北京', {})
        assert line.count('未知') >= 3
