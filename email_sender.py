"""
邮件发送模块
生成HTML邮件并通过SMTP发送
"""
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from string import Template
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

_template_dir = Path(__file__).parent / 'templates'
_css = (_template_dir / 'email.css').read_text(encoding='utf-8')
_html_template = Template((_template_dir / 'email.html').read_text(encoding='utf-8'))


class EmailSender:
    """邮件发送器"""
    
    def __init__(self, smtp_server: str, smtp_port: int, sender_email: str, sender_password: str):
        """
        初始化邮件发送器
        
        Args:
            smtp_server: SMTP服务器地址
            smtp_port: SMTP端口
            sender_email: 发件人邮箱
            sender_password: 发件人密码
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
    
    def create_html_email(self, weather_data: Dict, processed_data: Dict, news_data: List[Dict] = None) -> str:
        """
        创建HTML邮件内容

        Args:
            weather_data: 天气数据
            processed_data: AI处理后的数据
            news_data: 新闻数据（可选）

        Returns:
            HTML邮件内容
        """
        beijing_weather = self._generate_city_weather(
            '北京', weather_data.get('beijing', {}),
            processed_data.get('weather_advice', {}).get('beijing', '')
        )
        jinan_weather = self._generate_city_weather(
            '济南', weather_data.get('jinan', {}),
            processed_data.get('weather_advice', {}).get('jinan', '')
        )
        news_section = self._generate_news_section(news_data) if news_data else ""

        return _html_template.substitute(
            css=_css,
            character=processed_data.get('character', '神秘来客'),
            greeting=processed_data.get('greeting', '早安！'),
            beijing_weather=beijing_weather,
            jinan_weather=jinan_weather,
            news_section=news_section,
        )
    
    def _generate_city_weather(self, city_name: str, weather: Dict, advice: str) -> str:
        """生成单个城市的天气HTML"""
        alerts = weather.get('alerts', [])
        
        html = f'''
        <div class="weather-card">
            <div class="weather-city">{city_name}</div>
            <table style="width:100%; border-collapse:collapse;">
                <tr>
                    <td style="text-align:center; padding:8px 0;">
                        <span class="weather-condition">{weather.get("weather", "未知")}</span>
                        <span class="weather-divider">|</span>
                        <span class="weather-temp">{weather.get("temperature", "未知")}</span>
                    </td>
                </tr>
            </table>
            <div class="weather-detail">{weather.get("wind", "未知")}</div>
            <div class="weather-detail">🌅 {weather.get("sunrise", "未知")} | 🌇 {weather.get("sunset", "未知")}</div>
            '''
        
        # 添加天气预警
        if alerts:
            html += '<div class="weather-alert">'
            for alert in alerts:
                html += f'<div class="alert-item">⚠️ {alert}</div>'
            html += '</div>'
        
        # 添加穿衣建议
        if advice:
            html += f'<div class="weather-advice">💡 {advice}</div>'
        
        html += '</div>'
        return html
    
    def _generate_news_section(self, news_list: List[Dict]) -> str:
        """生成新闻部分的HTML（按领域分组）"""
        if not news_list:
            return ""
        
        # 按领域分组
        categories = {
            'A': {'title': '🔭 天体物理', 'items': []},
            'B': {'title': '🧠 元认知与心理学', 'items': []},
            'C': {'title': '📰 其他科学发现', 'items': []}
        }
        
        for news in news_list:
            category = news.get('category', 'C')
            if category not in categories:
                category = 'C'
            categories[category]['items'].append(news)
        
        html = '<h2 class="section-title">科学新闻</h2>\n'
        
        # 按 A、B、C 顺序输出
        for cat_key in ['A', 'B', 'C']:
            cat_data = categories[cat_key]
            if not cat_data['items']:
                continue
            
            html += f'<div class="category-section">\n'
            html += f'<div class="category-title">{cat_data["title"]} ({len(cat_data["items"])})</div>\n'
            
            for news in cat_data['items']:
                title_cn = news.get('title_cn', news.get('title', '未知标题'))
                title_en = news.get('title_en', news.get('title', ''))
                url = news.get('url', '#')
                summary = news.get('summary', '')
                date = news.get('date', '')
                source = news.get('source', '')
                
                source_short = self._simplify_source_name(source)
                
                html += f'''
            <div class="news-item">
                <div class="news-title">
                    {title_cn}
                    <a href="{url}" class="news-link-btn" target="_blank">🔗</a>
                    <span class="news-date">{date}</span>
                </div>
                <div class="news-title-en">{title_en}{', ' + source_short if source_short else ''}</div>
                <div class="news-summary">{summary}</div>
            </div>
            '''
            
            html += '</div>\n'
        
        return html
    
    def _simplify_source_name(self, source: str) -> str:
        """简化新闻来源名称"""
        source_map = {
            # Nature 系列
            'Nature News': 'Nature',
            'Nature': 'Nature',
            'Nature Astronomy': 'Nat Astron',
            'Nature Reviews Psychology': 'Nat Rev Psych',
            'Nature Communications': 'Nat Commun',
            # Science
            'Science': 'Science',
            # ScienceDaily
            'ScienceDaily': 'ScienceDaily',
            'ScienceDaily Top': 'ScienceDaily',
            'ScienceDaily Brain': 'ScienceDaily',
            'ScienceDaily Space': 'ScienceDaily',
            # 心理学专门源
            'PsyPost': 'PsyPost',
            'Neuroscience News': 'Neuro News',
            'PNAS Psychology': 'PNAS',
        }
        return source_map.get(source, source)

    
    def send_email(self, receiver_emails: List[str], subject: str, html_content: str, max_retries: int = 3) -> bool:
        """
        发送HTML邮件（带重试机制）

        Args:
            receiver_emails: 接收者邮箱列表
            subject: 邮件主题
            html_content: HTML邮件内容
            max_retries: 最大重试次数

        Returns:
            成功返回True，失败返回False
        """
        for attempt in range(max_retries):
            try:
                # 创建邮件
                msg = MIMEMultipart('alternative')
                msg['From'] = self.sender_email
                msg['To'] = ', '.join(receiver_emails)
                msg['Subject'] = subject
                
                # 添加HTML内容
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
                
                # 连接SMTP服务器并发送
                if attempt > 0:
                    wait_time = [5, 15, 30][attempt - 1]
                    logger.info(f"重试第 {attempt} 次，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                
                logger.info(f"正在连接SMTP服务器: {self.smtp_server}:{self.smtp_port}")
                
                if self.smtp_port == 465:
                    # 使用SSL连接 (Port 465)
                    server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30)
                else:
                    # 使用STARTTLS连接 (Port 587等)
                    server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                    server.starttls()
                
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                server.quit()
                
                logger.info(f"邮件发送成功，接收者: {', '.join(receiver_emails)}")
                return True
                
            except smtplib.SMTPException as e:
                error_msg = str(e)
                logger.error(f"SMTP错误 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                
                # 450错误通常是临时性的，可以重试
                if '450' in error_msg and attempt < max_retries - 1:
                    logger.info(f"检测到临时错误(450)，将重试...")
                    continue
                elif attempt == max_retries - 1:
                    logger.error(f"邮件发送失败: {e}")
                    logger.error("建议：")
                    logger.error("  1. 稍后再试（可能是发送频率限制）")
                    logger.error("  2. 检查邮箱设置是否允许发送")
                    logger.error("  3. 确认SMTP密码正确")
                    return False
                    
            except Exception as e:
                logger.error(f"邮件发送失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return False
        
        return False


if __name__ == '__main__':
    # 测试代码
    from config import config
    from weather_parser import parse_weather_files
    
    # 获取天气数据
    weather_data = parse_weather_files(
        config.BEIJING_WEATHER_URL,
        config.JINAN_WEATHER_URL
    )
    
    # 使用模拟数据测试邮件生成（不消耗 API token）
    processed_data = {
        'greeting': '早安！今天天气不错哦～',
        'character': '邓布利多',
        'weather_advice': {
            'beijing': '建议穿保暖外套。',
            'jinan': '建议携带雨伞。'
        }
    }
    mock_news = [
        {
            'title_cn': '测试新闻标题',
            'title_en': 'Test News Title',
            'summary': '这是一条测试新闻的摘要。',
            'url': 'https://example.com',
            'date': '2026-02-13',
            'source': 'Nature',
            'category': 'A'
        }
    ]
    
    # 创建邮件
    sender = EmailSender(
        config.SMTP_SERVER,
        config.SMTP_PORT,
        config.SENDER_EMAIL,
        config.SENDER_PASSWORD
    )
    
    html = sender.create_html_email(weather_data, processed_data, mock_news)
    
    # 保存HTML用于预览
    with open('/tmp/email_preview.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("邮件HTML已保存到 /tmp/email_preview.html")
