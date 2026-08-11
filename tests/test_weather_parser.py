"""weather_parser 离线测试（不发网络请求）

通过 WeatherParser.__new__ 绕过 __init__ 的网络抓取，直接注入 soup 夹具，
覆盖 2026-08 修复的三个问题：时段布局切换、温度归一、实况温度提取。
"""
from datetime import datetime

import pytest
from bs4 import BeautifulSoup

import weather_parser
from weather_parser import WeatherParser


def make_parser(html: str) -> WeatherParser:
    """构造带夹具 soup 的 WeatherParser（跳过网络抓取）"""
    parser = WeatherParser.__new__(WeatherParser)
    parser.url = 'http://fixture'
    parser.soup = BeautifulSoup(html, 'lxml')
    return parser


def forecast_li(label: str, wea: str, temp: str, wind_class: str = 'S',
                wind_title: str = '南风', wind_level: str = '<3级') -> str:
    """构造单个预报区块 li 的 HTML"""
    return f"""
    <li>
        <h1>{label}</h1>
        <p class="wea" title="{wea}">{wea}</p>
        <p class="tem"><span>{temp}</span><em>°C</em></p>
        <p class="win"><i class="{wind_class}"></i><span title="{wind_title}">{wind_level}</span></p>
    </li>"""


def page_html(*lis: str, crumbs: str = '') -> str:
    return f"""
    <div class="crumbs">{crumbs}</div>
    <div class="t"><ul class="clearfix">{''.join(lis)}</ul></div>"""


class FakeDateTime:
    """固定"今天"为 11 日，使时段对齐逻辑可确定性测试"""
    @staticmethod
    def now():
        class _Now:
            day = 11
        return _Now()


@pytest.fixture
def freeze_today(monkeypatch):
    monkeypatch.setattr(weather_parser, 'datetime', FakeDateTime)


class TestParseForecastBlocks:
    def test_identify_day_night_by_h1_label(self):
        parser = make_parser(page_html(
            forecast_li('11日白天', '晴', '33'),
            forecast_li('11日夜间', '多云', '23'),
        ))
        blocks = parser._parse_forecast_blocks()
        assert blocks['day'] is not None and blocks['night'] is not None
        assert blocks['day'][1] == '11日白天'
        assert blocks['night'][1] == '11日夜间'

    def test_order_independent(self):
        # 傍晚布局：夜间区块在前
        parser = make_parser(page_html(
            forecast_li('11日夜间', '雷阵雨', '23'),
            forecast_li('12日白天', '中雨', '28'),
        ))
        blocks = parser._parse_forecast_blocks()
        assert blocks['night'][1] == '11日夜间'
        assert blocks['day'][1] == '12日白天'


class TestAlignTodayBlocks:
    def test_normal_daytime_layout(self, freeze_today):
        parser = make_parser(page_html(
            forecast_li('11日白天', '晴', '33'),
            forecast_li('11日夜间', '多云', '23'),
        ))
        aligned = parser._align_today_blocks(parser._parse_forecast_blocks())
        # 白天/夜间均取今天的区块
        assert aligned['day'].select_one('h1').text.strip() == '11日白天'
        assert aligned['night'].select_one('h1').text.strip() == '11日夜间'

    def test_evening_layout_falls_back_to_tonight(self, freeze_today):
        # 傍晚：只有今日夜间 + 明日白天，以今日夜间为代表
        parser = make_parser(page_html(
            forecast_li('11日夜间', '雷阵雨', '23'),
            forecast_li('12日白天', '中雨', '28'),
        ))
        aligned = parser._align_today_blocks(parser._parse_forecast_blocks())
        assert aligned['day'].select_one('h1').text.strip() == '11日夜间'
        assert aligned['night'].select_one('h1').text.strip() == '11日夜间'

    def test_early_morning_layout(self, freeze_today):
        # 凌晨：昨夜 + 今日白天，白天取今天的
        parser = make_parser(page_html(
            forecast_li('10日夜间', '晴', '20'),
            forecast_li('11日白天', '多云', '30'),
        ))
        aligned = parser._align_today_blocks(parser._parse_forecast_blocks())
        assert aligned['day'].select_one('h1').text.strip() == '11日白天'
        # 夜间退回相邻（昨夜）区块兜底
        assert aligned['night'].select_one('h1').text.strip() == '10日夜间'


class TestGetWeatherForecast:
    def test_temperature_normalized_low_to_high(self, freeze_today):
        parser = make_parser(page_html(
            forecast_li('11日白天', '晴', '33'),
            forecast_li('11日夜间', '多云', '23'),
        ))
        result = parser.get_weather_forecast()
        # 无论页面顺序如何，始终输出 低~高
        assert result['temperature'] == '23~33°C'
        assert result['weather'] == '晴'

    def test_evening_layout_no_inverted_range(self, freeze_today):
        # 傍晚布局（夜间在前）不能产生 28~23°C 这类颠倒范围
        parser = make_parser(page_html(
            forecast_li('11日夜间', '雷阵雨', '23'),
            forecast_li('12日白天', '中雨', '28'),
        ))
        result = parser.get_weather_forecast()
        assert result['temperature'] == '23°C'  # 今日夜间单值
        assert result['weather'] == '雷阵雨'

    def test_city_from_last_breadcrumb(self):
        # 济南面包屑为 3 级（全国/山东/济南），须取最后一级
        parser = make_parser(page_html(crumbs='<a>全国</a><a>山东</a><a>济南</a>'))
        result = parser.get_weather_forecast()
        assert result['city'] == '济南'

    def test_wind_from_day_block(self, freeze_today):
        parser = make_parser(page_html(
            forecast_li('11日白天', '晴', '33', wind_class='SE',
                        wind_title='东南风', wind_level='<3级'),
            forecast_li('11日夜间', '多云', '23'),
        ))
        result = parser.get_weather_forecast()
        assert result['wind'] == '东南风 <3级'


class TestCurrentTemp:
    SCRIPT = (
        '<script> var observe24h_data = {"od":{"od0":"202608111500",'
        '"od1":"西城","od2":[{"od21":"14","od22":"29.1"},'
        '{"od21":"15","od22":"29.9"}]}}; </script>'
    )

    def test_extract_latest_observation(self):
        parser = make_parser(self.SCRIPT)
        # od0=...1500 → 15 时的观测 29.9 → 四舍五入 30°C
        assert parser._extract_current_temp() == '30°C'

    def test_missing_script_returns_unknown(self):
        parser = make_parser('<div>无脚本</div>')
        assert parser._extract_current_temp() == '未知'

    def test_embedded_json_bracket_matching(self):
        # 括号配对截取，不被脚本后续内容干扰
        parser = make_parser(self.SCRIPT + '<script>var x = 1;</script>')
        data = parser._extract_embedded_json('observe24h_data')
        assert data is not None
        assert data['od']['od1'] == '西城'
