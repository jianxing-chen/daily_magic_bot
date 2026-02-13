"""
天气数据解析模块
从weather.com.cn获取HTML天气数据
"""
from bs4 import BeautifulSoup
import requests
import logging
from typing import Dict
import re

logger = logging.getLogger(__name__)

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
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            self.soup = BeautifulSoup(response.text, 'lxml')
            logger.info("成功获取并解析HTML数据")
        except Exception as e:
            logger.error(f"获取天气数据失败: {e}")
            raise

    def get_weather_forecast(self) -> Dict:
        """
        获取天气预报
        
        Returns:
            包含天气信息的字典
        """
        try:
            result = {}
            
            # 获取城市名称 (从面包屑导航)
            crumbs = self.soup.select('div.crumbs a')
            if len(crumbs) >= 2:
                result['city'] = crumbs[1].text.strip()
            else:
                result['city'] = '未知'
            
            # 获取当前实况温度 (从实况区域)
            current_temp_elem = self.soup.select_one('div.sk div.tem span')
            if current_temp_elem:
                temp_text = current_temp_elem.text.strip()
                result['current_temp'] = temp_text + '°C'
            else:
                result['current_temp'] = '未知'
            
            # 获取白天天气状况
            weather_elem = self.soup.select_one('div.t ul li p.wea')
            if weather_elem:
                result['weather'] = weather_elem.text.strip()
            else:
                result['weather'] = '未知'
            
            # 获取温度范围 (白天和夜间)
            temp_day = self.soup.select_one('div.t ul li:first-child p.tem span')
            temp_night = self.soup.select_one('div.t ul li:nth-child(2) p.tem span')
            
            if temp_day and temp_night:
                high = temp_day.text.strip()
                low = temp_night.text.strip()
                result['temperature'] = f"{low}~{high}°C"
            else:
                result['temperature'] = '未知'
            
            # 获取风力风向
            wind_elem = self.soup.select_one('div.t ul li p.win span')
            if wind_elem:
                wind_level = wind_elem.text.strip()
                # 尝试获取风向（可能在i标签的class里，或者title）
                wind_dir_elem = wind_elem.find_previous('i')
                if wind_dir_elem and wind_dir_elem.get('class'):
                    wind_dir_class = ' '.join(wind_dir_elem.get('class', []))
                    # 从class提取风向，如 "NW" -> "西北风"
                    wind_dir_map = {
                        'N': '北风', 'NE': '东北风', 'E': '东风', 'SE': '东南风',
                        'S': '南风', 'SW': '西南风', 'W': '西风', 'NW': '西北风'
                    }
                    wind_dir = wind_dir_map.get(wind_dir_class, '')
                    result['wind'] = f"{wind_dir} {wind_level}" if wind_dir else wind_level
                else:
                    # 尝试从title获取
                    wind_title = wind_elem.get('title', '')
                    if wind_title:
                        result['wind'] = wind_title
                    else:
                        result['wind'] = wind_level
            else:
                result['wind'] = '未知'
            
            # 获取日出日落时间
            sunrise_elem = self.soup.select_one('p.sunUp span')
            sunset_elem = self.soup.select_one('p.sunDown span')
            
            if sunrise_elem:
                sunrise_text = sunrise_elem.text.strip()
                result['sunrise'] = sunrise_text.replace('日出 ', '')
            else:
                result['sunrise'] = '未知'
                
            if sunset_elem:
                sunset_text = sunset_elem.text.strip()
                result['sunset'] = sunset_text.replace('日落 ', '')
            else:
                result['sunset'] = '未知'
            
            # 获取天气预警
            alerts = []
            alert_elems = self.soup.select('div.sk_alarm a')
            for alert in alert_elems:
                if alert.get('style') and 'display: block' in alert.get('style', ''):
                    alert_text = alert.get('title', alert.text.strip())
                    alerts.append(alert_text)
            
            result['alerts'] = alerts if alerts else []
            
            logger.info(f"成功解析天气数据: {result['city']}")
            return result
            
        except Exception as e:
            logger.error(f"解析天气数据失败: {e}")
            return {
                'city': '未知',
                'weather': '未知',
                'temperature': '未知',
                'current_temp': '未知',
                'wind': '未知',
                'sunrise': '未知',
                'sunset': '未知',
                'alerts': []
            }

def parse_weather_files(beijing_url: str, jinan_url: str) -> Dict[str, Dict]:
    """
    解析北京和济南的天气
    """
    default_weather = {
        'city': '未知', 'weather': '未知', 'temperature': '未知',
        'current_temp': '未知', 'wind': '未知',
        'sunrise': '未知', 'sunset': '未知', 'alerts': []
    }
    result = {
        'beijing': dict(default_weather),
        'jinan': dict(default_weather)
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
