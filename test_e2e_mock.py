"""
端到端测试脚本：使用 mock 数据生成完整邮件（不消耗 API token）
用途：验证重构不改变输出
"""
import sys
from pathlib import Path

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
    'greeting': '早安！今天北京的天气真不错，阳光明媚。我注意到今天有一条关于球状星团的重要发现，这让我想起了星空的美妙。',
    'character': '邓布利多',
    'weather_advice': {
        'beijing': '建议穿保暖外套，注意防寒。',
        'jinan': '温度适宜，可以穿薄外套。'
    }
}

# Mock 新闻数据
MOCK_NEWS = [
    {
        'title_cn': '球状星团中发现毫秒脉冲星双星系统',
        'title_en': 'Millisecond pulsar binary system discovered in globular cluster',
        'summary': '天文学家在一个古老的球状星团中发现了一个罕见的毫秒脉冲星双星系统。这一发现为研究恒星演化和引力波提供了新的观测窗口。',
        'url': 'https://www.nature.com/articles/test1',
        'date': '2026-07-28',
        'source': 'Nature Astronomy',
        'category': 'A'
    },
    {
        'title_cn': '元认知能力与工作记忆的关系研究',
        'title_en': 'The relationship between metacognitive ability and working memory',
        'summary': '最新研究表明，个体的元认知能力与其工作记忆容量存在显著相关性。这一发现对理解人类认知过程具有重要意义。',
        'url': 'https://www.psypost.org/test2',
        'date': '2026-07-28',
        'source': 'PsyPost',
        'category': 'B'
    },
    {
        'title_cn': '新型疫苗在临床试验中显示出高效性',
        'title_en': 'Novel vaccine shows high efficacy in clinical trials',
        'summary': '一种针对呼吸道病毒的新型疫苗在三期临床试验中显示出 95% 的保护率，为公共卫生带来重大突破。',
        'url': 'https://www.science.org/articles/test3',
        'date': '2026-07-27',
        'source': 'Science',
        'category': 'C'
    }
]


def generate_test_email():
    """使用 mock 数据生成测试邮件"""
    from config import config
    from email_sender import EmailSender

    sender = EmailSender(
        config.SMTP_SERVER,
        config.SMTP_PORT,
        config.SENDER_EMAIL,
        config.SENDER_PASSWORD,
        config.SENDER_NAME
    )

    html = sender.create_html_email(
        MOCK_WEATHER,
        MOCK_PROCESSED,
        MOCK_NEWS
    )

    output_file = Path('/tmp/email_baseline.html')
    output_file.write_text(html, encoding='utf-8')
    print(f"✓ 测试邮件已生成: {output_file}")
    print(f"  文件大小: {len(html)} 字符")
    return output_file


if __name__ == '__main__':
    generate_test_email()
