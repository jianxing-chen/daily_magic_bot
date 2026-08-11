"""
天气数据解析模块
从weather.com.cn获取HTML天气数据
"""
from bs4 import BeautifulSoup
import requests
import logging
from datetime import datetime
from typing import Dict, Optional
import re
import json

logger = logging.getLogger(__name__)

# --- 抓取配置常量 ---
REQUEST_TIMEOUT = 10          # HTTP 请求超时（秒）
TEMP_NUMBER_PATTERN = re.compile(r'-?\d+')  # 温度数值提取正则

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})

DEFAULT_WEATHER = {
    'city': '未知',
    'weather': '未知',
    'temperature': '未知',
    'current_temp': '未知',
    'wind': '未知',
    'sunrise': '未知',
    'sunset': '未知',
    'alerts': []
}

class WeatherParser:
    """weather.com.cn天气解析器"""

    def __init__(self, url: str):
        self.url = url
        self.soup = None
        self._load_data()

    def _load_data(self):
        """从URL加载HTML数据"""
        try:
            logger.info(f"正在获取天气数据: {self.url}")
            response = _session.get(self.url, timeout=REQUEST_TIMEOUT)
            response.encoding = 'utf-8'
            self.soup = BeautifulSoup(response.text, 'lxml')
            logger.info("成功获取并解析HTML数据")
        except Exception as e:
            logger.error(f"获取天气数据失败: {e}")
            raise

    def _safe_extract_text(self, selector: str, default: str = '未知') -> str:
        """安全提取元素文本

        Args:
            selector: CSS 选择器
            default: 元素不存在时的默认值

        Returns:
            元素文本或默认值
        """
        elem = self.soup.select_one(selector)
        return elem.text.strip() if elem else default

    def _extract_wind_direction(self, wind_elem) -> str:
        """从风力元素的前置 <i> 标签或 title 提取风向

        Args:
            wind_elem: 风力 BeautifulSoup 元素

        Returns:
            风向字符串（如 '北风'），未识别返回 ''
        """
        # 风向映射表
        wind_dir_map = {
            'N': '北风', 'NE': '东北风', 'E': '东风', 'SE': '东南风',
            'S': '南风', 'SW': '西南风', 'W': '西风', 'NW': '西北风'
        }

        # 尝试从前置 <i> 标签的 class 提取
        wind_dir_elem = wind_elem.find_previous('i')
        if wind_dir_elem and wind_dir_elem.get('class'):
            wind_dir_class = ' '.join(wind_dir_elem.get('class', []))
            if wind_dir_class in wind_dir_map:
                return wind_dir_map[wind_dir_class]

        # 兜底：从 title 属性获取
        return ''

    def _extract_embedded_json(self, marker: str) -> Optional[Dict]:
        """从页面内嵌 script 变量中提取 JSON 数据

        通过括号配对截取完整对象，避免贪婪正则越界。

        Args:
            marker: script 中的变量名标记（如 'observe24h_data'）

        Returns:
            解析后的 dict，未找到或解析失败返回 None
        """
        script = self.soup.find('script', string=re.compile(marker))
        if not script or not script.string:
            return None

        marker_pos = script.string.find(marker)
        start = script.string.find('{', marker_pos)
        if start == -1:
            return None

        # 括号配对截取完整 JSON 对象
        depth = 0
        for i in range(start, len(script.string)):
            if script.string[i] == '{':
                depth += 1
            elif script.string[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(script.string[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _extract_current_temp(self) -> str:
        """从页面内嵌 observe24h_data 提取实况温度

        页面实况区 div.sk 由 JS 动态注入，静态 HTML 中为空，
        故改从内嵌的 observe24h_data 变量中取最新观测值（od22 为温度）。

        Returns:
            实况温度字符串（如 '30°C'），失败返回 '未知'
        """
        try:
            data = self._extract_embedded_json('observe24h_data')
            if not data:
                return '未知'

            od = data.get('od', {})
            entries = od.get('od2', [])
            if not entries:
                return '未知'

            # od0 为最新观测时间戳（如 202608111500），按小时匹配对应观测条目
            latest_hour = str(od.get('od0', ''))[-4:-2]
            entry = next((e for e in entries if e.get('od21') == latest_hour), entries[-1])
            temp = entry.get('od22', '')
            return f"{round(float(temp))}°C" if temp else '未知'
        except Exception as e:
            logger.warning(f"解析实况温度失败: {e}")
            return '未知'

    def _parse_forecast_blocks(self) -> Dict[str, Optional[tuple]]:
        """按时段标签解析预报区块

        页面 div.t 的区块顺序会随时段切换（白天显示“今日白天+今日夜间”，
        傍晚后显示“今日夜间+明日白天”），故通过 h1 标签（如“11日夜间”）
        识别时段，而非盲取第一/第二个 li，避免温度范围颠倒与跨天串数据。

        Returns:
            {'day': (区块元素, h1标签文本)或None, 'night': 同}
        """
        blocks = {'day': None, 'night': None}
        for li in self.soup.select('div.t ul li'):
            h1 = li.select_one('h1')
            if not h1:
                continue
            label = h1.text.strip()
            if '白天' in label and blocks['day'] is None:
                blocks['day'] = (li, label)
            elif '夜间' in label and blocks['night'] is None:
                blocks['night'] = (li, label)
        return blocks

    def _align_today_blocks(self, blocks: Dict) -> Dict:
        """对齐到今天：选出代表今天的白天/夜间区块

        h1 标签带日期（如“11日夜间”），凌晨/傍晚时页面会混入昨/明区块：
        优先选带今天日期的区块；无法对齐时优先白天区块，夜间兜底取相邻区块。

        Args:
            blocks: _parse_forecast_blocks 的返回值

        Returns:
            {'day': 区块元素或None, 'night': 区块元素或None}
        """
        today_label = f"{datetime.now().day}日"

        def is_today(entry):
            return entry is not None and today_label in entry[1]

        day_entry = blocks['day']
        night_entry = blocks['night']

        # 优先选带今天日期的区块
        today_day = day_entry if is_today(day_entry) else None
        today_night = night_entry if is_today(night_entry) else None

        if today_day:
            day_block = today_day[0]
            # 夜间优先今天的，否则退回相邻（昨夜）区块兜底
            night_block = today_night[0] if today_night else (
                night_entry[0] if night_entry else None
            )
        elif today_night:
            # 凌晨场景：只有今日夜间 + 明日白天，以夜间为代表
            day_block = today_night[0]
            night_block = today_night[0]
        else:
            # 无法对齐日期，退回原顺序兜底
            day_block = day_entry[0] if day_entry else None
            night_block = night_entry[0] if night_entry else None

        return {'day': day_block, 'night': night_block}

    def _extract_wind_from_block(self, block) -> str:
        """从预报区块提取风力风向

        Args:
            block: 预报区块 li 元素

        Returns:
            风力字符串（如 '南风 <3级'），未识别返回 '未知'
        """
        wind_elem = block.select_one('p.win span')
        if not wind_elem:
            return '未知'

        wind_level = wind_elem.text.strip()
        wind_dir = self._extract_wind_direction(wind_elem)
        if wind_dir:
            return f"{wind_dir} {wind_level}"

        # 兜底：从 title 属性获取
        wind_title = wind_elem.get('title', '')
        return wind_title if wind_title else wind_level

    def get_weather_forecast(self) -> Dict:
        """
        获取天气预报

        Returns:
            包含天气信息的字典
        """
        try:
            result = {}

            # 获取城市名称 (从面包屑导航取最后一级，兼容 2/3 级层级差异)
            crumbs = self.soup.select('div.crumbs a')
            result['city'] = crumbs[-1].text.strip() if crumbs else '未知'

            # 获取当前实况温度 (从内嵌 observe24h_data 提取)
            result['current_temp'] = self._extract_current_temp()

            # 按时段标签定位白天/夜间区块（页面布局会随时段切换），并对齐到今天
            blocks = self._align_today_blocks(self._parse_forecast_blocks())
            day_block = blocks['day']
            night_block = blocks['night']

            # 获取白天天气状况
            result['weather'] = (
                day_block.select_one('p.wea').text.strip()
                if day_block and day_block.select_one('p.wea') else '未知'
            )

            # 获取温度范围（按时段取高低温并排序，保证始终 低~高）
            day_tem = day_block.select_one('p.tem').text if day_block and day_block.select_one('p.tem') else ''
            night_tem = night_block.select_one('p.tem').text if night_block and night_block.select_one('p.tem') else ''
            day_nums = TEMP_NUMBER_PATTERN.findall(day_tem)
            night_nums = TEMP_NUMBER_PATTERN.findall(night_tem)
            if day_nums and night_nums:
                high = int(day_nums[0])
                low = int(night_nums[0])
                if high == low:
                    # 凌晨场景白天/夜间为同一区块时，避免显示 23~23°C
                    result['temperature'] = f"{high}°C"
                else:
                    result['temperature'] = f"{min(high, low)}~{max(high, low)}°C"
            elif day_nums or night_nums:
                nums = day_nums or night_nums
                result['temperature'] = f"{nums[0]}°C"
            else:
                result['temperature'] = '未知'

            # 获取白天风力风向
            result['wind'] = self._extract_wind_from_block(day_block) if day_block else '未知'

            # 获取日出日落时间
            sunrise_text = self._safe_extract_text('p.sunUp span', '')
            result['sunrise'] = sunrise_text.replace('日出 ', '') if sunrise_text else '未知'

            sunset_text = self._safe_extract_text('p.sunDown span', '')
            result['sunset'] = sunset_text.replace('日落 ', '') if sunset_text else '未知'

            # 获取天气预警
            # weather.com.cn 通过 inline style 的 display 控制预警显示/隐藏
            alerts = []
            alert_elems = self.soup.select('div.sk_alarm a')
            for alert in alert_elems:
                style = alert.get('style', '')
                # 显示预警的条件：有 style 且 display 不是 none
                if style and 'display' in style and 'none' not in style.lower():
                    alert_text = alert.get('title', alert.text.strip())
                    alerts.append(alert_text)

            result['alerts'] = alerts if alerts else []

            logger.info(f"成功解析天气数据: {result['city']}")
            return result

        except Exception as e:
            logger.error(f"解析天气数据失败: {e}")
            return dict(DEFAULT_WEATHER)

def parse_weather_files(beijing_url: str, jinan_url: str) -> Dict[str, Dict]:
    """
    解析北京和济南的天气
    """
    result = {
        'beijing': dict(DEFAULT_WEATHER),
        'jinan': dict(DEFAULT_WEATHER)
    }

    try:
        beijing = WeatherParser(beijing_url)
        result['beijing'] = beijing.get_weather_forecast()
    except Exception as e:
        logger.error(f"解析北京天气出错: {e}")

    try:
        jinan = WeatherParser(jinan_url)
        result['jinan'] = jinan.get_weather_forecast()
    except Exception as e:
        logger.error(f"解析济南天气出错: {e}")

    return result

if __name__ == '__main__':
    from config import config
    data = parse_weather_files(config.BEIJING_WEATHER_URL, config.JINAN_WEATHER_URL)

    print("\n=== 北京天气 ===")
    for key, value in data['beijing'].items():
        print(f"{key}: {value}")

    print("\n=== 济南天气 ===")
    for key, value in data['jinan'].items():
        print(f"{key}: {value}")
