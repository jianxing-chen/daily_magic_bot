"""
邮件发送模块
生成HTML邮件并通过SMTP发送
"""
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from pathlib import Path
from typing import Dict, List
import logging

from jinja2 import Environment, FileSystemLoader, select_autoescape

from retry import retry_with_backoff

logger = logging.getLogger(__name__)

_default_template_dir = Path(__file__).parent / 'templates'

SMTP_RETRY_WAITS = [5, 15, 30]       # SMTP 重试退避等待（秒）


class EmailSender:
    """邮件发送器"""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,
        sender_name: str = "Daily Magic Bot",
        template_dir: Path = None
    ):
        """初始化邮件发送器

        Args:
            smtp_server: SMTP 服务器地址
            smtp_port: SMTP 端口
            sender_email: 发件人邮箱
            sender_password: 发件人密码/授权码
            sender_name: 发件人显示名称
            template_dir: 可选的模板目录路径（用于测试时注入）
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.sender_name = sender_name
        self.template_dir = template_dir or _default_template_dir

        # 初始化 Jinja2 环境
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # 预加载 CSS
        self.css = (self.template_dir / 'email.css').read_text(encoding='utf-8')

    def create_html_email(self, weather_data: Dict, processed_data: Dict, news_data: List[Dict] = None) -> str:
        """创建HTML邮件内容

        Args:
            weather_data: 天气数据
            processed_data: AI处理后的数据
            news_data: 新闻数据（可选）

        Returns:
            HTML邮件内容
        """
        # 准备模板上下文
        context = {
            'css': self.css,
            'character': processed_data.get('character', '神秘来客'),
            'greeting': processed_data.get('greeting', '早安！'),
            'beijing_weather': weather_data.get('beijing', {}),
            'jinan_weather': weather_data.get('jinan', {}),
            'beijing_advice': processed_data.get('weather_advice', {}).get('beijing', ''),
            'jinan_advice': processed_data.get('weather_advice', {}).get('jinan', ''),
            'categories': self._group_news_by_category(news_data) if news_data else []
        }

        # 渲染模板
        template = self.jinja_env.get_template('email.html')
        return template.render(**context)

    def create_test_email(self) -> str:
        """创建简单的测试邮件（不消耗API token）

        Returns:
            测试邮件 HTML 内容
        """
        template = self.jinja_env.get_template('test_email.html')
        return template.render(
            current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def _group_news_by_category(self, news_list: List[Dict]) -> List[Dict]:
        """按领域分组新闻

        Args:
            news_list: 新闻列表

        Returns:
            非空分类列表，按 A、B、C 顺序
        """
        categories = {
            'A': {'title': '🔭 天体物理', 'news_items': []},
            'B': {'title': '🧠 元认知与心理学', 'news_items': []},
            'C': {'title': '📰 其他科学发现', 'news_items': []}
        }

        for news in news_list:
            category = news.get('category', 'C')
            if category not in categories:
                category = 'C'

            # 添加简化后的来源名称
            news['source_short'] = self._simplify_source_name(news.get('source', ''))
            categories[category]['news_items'].append(news)

        # 返回非空分类
        return [cat for cat in categories.values() if cat['news_items']]

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

    def _connect_smtp(self, timeout: int = 30):
        """连接并登录 SMTP 服务器（465 SSL / 其余 STARTTLS）

        Args:
            timeout: 连接超时（秒）

        Returns:
            已登录的 SMTP 服务器对象
        """
        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=timeout)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=timeout)
            server.starttls()
        server.login(self.sender_email, self.sender_password)
        return server

    def test_connection(self, timeout: int = 15) -> None:
        """测试 SMTP 连接与登录（供预检模式使用）

        Args:
            timeout: 连接超时（秒）

        Raises:
            smtplib.SMTPException / OSError: 连接或登录失败
        """
        server = self._connect_smtp(timeout=timeout)
        server.quit()

    def send_email(self, receiver_emails: List[str], subject: str, html_content: str, max_retries: int = 3) -> bool:
        """
        发送HTML邮件（带指数退避重试机制）

        Args:
            receiver_emails: 接收者邮箱列表
            subject: 邮件主题
            html_content: HTML邮件内容
            max_retries: 最大尝试次数

        Returns:
            成功返回True，失败返回False
        """
        # 构建邮件（重试间不变，只需构建一次）
        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((self.sender_name, self.sender_email))
        msg['To'] = ', '.join(receiver_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        def attempt():
            logger.info(f"正在连接SMTP服务器: {self.smtp_server}:{self.smtp_port}")
            server = self._connect_smtp(timeout=30)
            try:
                server.send_message(msg)
            finally:
                server.quit()

        try:
            retry_with_backoff(
                attempt,
                waits=SMTP_RETRY_WAITS[:max(0, max_retries - 1)],
                label='SMTP',
                # SMTP 失败原因多样（网络/限流/临时拒绝），保持原有语义：一律退避重试
                retryable=lambda e: True
            )
            logger.info(f"邮件发送成功，接收者: {', '.join(receiver_emails)}")
            return True

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            logger.error("建议：")
            logger.error("  1. 稍后再试（可能是发送频率限制）")
            logger.error("  2. 检查邮箱设置是否允许发送")
            logger.error("  3. 确认SMTP密码正确")
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
