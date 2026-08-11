"""邮件渲染端到端测试（原 test_e2e_mock.py 迁入，改为 pytest 可发现）

使用固定 mock 数据渲染完整邮件 HTML，不消耗 API token、不发送邮件。
用途：锁定模板渲染行为，防止重构破坏输出。
"""
from email_sender import EmailSender
from config import config

# Mock 天气数据（固定值）
MOCK_WEATHER = {
    'beijing': {
        'city': '北京',
        'weather': '晴',
        'temperature': '5~15°C',
        'current_temp': '8°C',
        'wind': '北风 3级',
        'sunrise': '07:15',
        'sunset': '17:05',
        'alerts': ['寒潮蓝色预警：预计未来48小时气温将下降8℃以上']
    },
    'jinan': {
        'city': '济南',
        'weather': '多云',
        'temperature': '8~18°C',
        'current_temp': '12°C',
        'wind': '南风 2级',
        'sunrise': '06:50',
        'sunset': '17:30',
        'alerts': []
    }
}

# Mock AI 处理后的数据
MOCK_PROCESSED = {
    'greeting': '早安！今天北京的天气真不错，阳光明媚。',
    'character': '邓布利多',
    'weather_advice': {
        'beijing': '建议穿保暖外套，注意防寒。',
        'jinan': '温度适宜，可以穿薄外套。'
    }
}

# Mock 新闻数据（覆盖 A/B/C 三分类）
MOCK_NEWS = [
    {
        'title_cn': '球状星团中发现毫秒脉冲星双星系统',
        'title_en': 'Millisecond pulsar binary system discovered in globular cluster',
        'summary': '天文学家在一个古老的球状星团中发现了一个罕见的毫秒脉冲星双星系统。',
        'url': 'https://www.nature.com/articles/test1',
        'date': '2026-07-28',
        'source': 'Nature Astronomy',
        'category': 'A'
    },
    {
        'title_cn': '元认知能力与工作记忆的关系研究',
        'title_en': 'The relationship between metacognitive ability and working memory',
        'summary': '最新研究表明，个体的元认知能力与其工作记忆容量存在显著相关性。',
        'url': 'https://www.psypost.org/test2',
        'date': '2026-07-28',
        'source': 'PsyPost',
        'category': 'B'
    },
    {
        'title_cn': '新型疫苗在临床试验中显示出高效性',
        'title_en': 'Novel vaccine shows high efficacy in clinical trials',
        'summary': '一种针对呼吸道病毒的新型疫苗在三期临床试验中显示出 95% 的保护率。',
        'url': 'https://www.science.org/articles/test3',
        'date': '2026-07-27',
        'source': 'Science',
        'category': 'C'
    }
]


def make_sender() -> EmailSender:
    return EmailSender(
        config.SMTP_SERVER,
        config.SMTP_PORT,
        config.SENDER_EMAIL,
        config.SENDER_PASSWORD,
        config.SENDER_NAME
    )


def test_email_renders_full_html():
    html = make_sender().create_html_email(MOCK_WEATHER, MOCK_PROCESSED, MOCK_NEWS)

    # HTML 骨架与 CSS 内联
    assert html.startswith('<!DOCTYPE html>')
    assert '<style>' in html

    # 问候与角色
    assert '邓布利多' in html
    assert '早安！' in html

    # 天气卡片（双城 + 预警 + 建议）
    assert '北京' in html and '济南' in html
    assert '5~15°C' in html
    assert '寒潮蓝色预警' in html
    assert '建议穿保暖外套' in html

    # 三分类新闻分组
    assert '🔭 天体物理' in html
    assert '🧠 元认知与心理学' in html
    assert '📰 其他科学发现' in html
    assert '球状星团中发现毫秒脉冲星双星系统' in html

    # 来源名简化
    assert 'Nat Astron' in html


def test_email_renders_without_news():
    html = make_sender().create_html_email(MOCK_WEATHER, MOCK_PROCESSED, None)
    assert '邓布利多' in html
    assert '科学新闻' not in html  # 无新闻时不渲染新闻区


def test_html_autoescape():
    # XSS 防御：注入内容应被转义
    processed = dict(MOCK_PROCESSED, greeting='<script>alert(1)</script>')
    html = make_sender().create_html_email(MOCK_WEATHER, processed, None)
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
