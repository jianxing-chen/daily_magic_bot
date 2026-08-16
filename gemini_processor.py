"""
AI 内容处理编排模块
编排 prompt 构造（prompts.py）→ AI 调用（ai_client.py）→ 响应解析与降级校验
全项目仅 2 次 AI 调用：generate_master_content + process_news_batch
"""
from typing import List, Dict
import asyncio
import random
import logging

from config import config
from async_news_fetcher import fetch_articles_async
from ai_client import AiClient, parse_ai_json
from prompts import build_master_prompt, build_batch_prompt

logger = logging.getLogger(__name__)


class GeminiProcessor:
    """AI 内容处理器：prompt 构造 + 调用 + 解析校验 + 降级兜底"""

    def __init__(
        self,
        api_key: str,
        deepseek_api_key: str = None,
        deepseek_base_url: str = None,
        deepseek_model: str = None
    ):
        """
        初始化AI处理器
        
        Args:
            api_key: Gemini API密钥
            deepseek_api_key: 可选 DeepSeek API密钥（测试注入，默认取 config）
            deepseek_base_url: 可选 DeepSeek base URL（测试注入）
            deepseek_model: 可选 DeepSeek 模型名（测试注入）
        """
        self.ai = AiClient(
            api_key,
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model
        )
        logger.info("AI处理器初始化成功")

    @property
    def deepseek_enabled(self) -> bool:
        """DeepSeek 兜底是否已配置（API key 非占位符）"""
        return self.ai.deepseek_enabled

    def generate_master_content(self, character_name: str, weather_info: Dict, news_list: List[Dict]) -> Dict:
        """
        一次性生成所有AI内容：问候（含新闻综述）、天气建议、新闻筛选
        
        Args:
            character_name: 角色名称
            weather_info: 天气数据
            news_list: 原始新闻列表（包含 title, url, source, date）
            
        Returns:
            JSON字典包含 greeting, advice_beijing, advice_jinan, selected_news
        """
        try:
            prompt = build_master_prompt(character_name, weather_info, news_list)
            response_text = self.ai.call(prompt, use_json=True)

            # 健壮解析：容错代码块围栏/注释/尾逗号，失败时打印原文便于定位
            result = parse_ai_json(response_text, "主内容生成")
            if not isinstance(result, dict):
                raise ValueError(f"返回 JSON 顶层类型异常: {type(result).__name__}")
            
            # 校验必要字段
            required_keys = ['greeting', 'advice_beijing', 'advice_jinan', 'selected_news']
            for key in required_keys:
                if key not in result:
                    logger.warning(f"AI返回缺少字段: {key}，使用默认值")
                    if key == 'selected_news':
                        result[key] = [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
                    else:
                        result[key] = ''
            
            # 校验 selected_news 格式
            if not isinstance(result.get('selected_news'), list):
                logger.warning("selected_news 格式异常，使用默认值")
                result['selected_news'] = [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
            
            # 记录主内容实际使用的 AI 模型（供邮件标签展示）
            self.used_model = self.ai.last_used_model
            return result
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error("⚠️ AI 内容生成彻底失败，本次邮件将使用兜底默认值（无真实 AI 问候/筛选）")
            logger.error(f"最后错误: {e}")
            logger.error("=" * 60)
            self.used_model = 'fallback'
            return {
                "greeting": f"{character_name}祝您早安！今天的天气真不错！",
                "advice_beijing": "请注意天气变化。",
                "advice_jinan": "请注意天气变化。",
                "selected_news": [{"index": i, "category": "C"} for i in range(1, min(16, len(news_list) + 1))]
            }

    def process_news_batch(self, articles: List[Dict]) -> List[Dict]:
        """
        批量处理新闻：一次性完成标题翻译和内容总结
        
        Args:
            articles: 文章列表 [{'title': '...', 'content': '...', 'url': '...'}]
            
        Returns:
            处理后的列表 [{'title_en': '...', 'title_cn': '...', 'summary': '...', 'url': '...'}]
        """
        try:
            prompt = build_batch_prompt(articles)
            response_text = self.ai.call(prompt, use_json=True)

            # 健壮解析：容错代码块围栏/注释/尾逗号，失败时打印原文便于定位
            results = parse_ai_json(response_text, "新闻批量处理")
            
            # 校验返回列表格式
            if not isinstance(results, list):
                logger.warning(f"AI返回非列表格式: {type(results)}，尝试降级处理")
                results = []
            
            # 合并结果
            processed_news = []
            for i, res in enumerate(results):
                if i < len(articles):
                    processed_news.append({
                        'title_en': articles[i]['title'],
                        'title_cn': res.get('title_cn', articles[i]['title']),
                        'summary': res.get('summary', '暂无总结'),
                        'url': articles[i]['url']
                    })
            
            return processed_news
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error("⚠️ 新闻批量处理彻底失败，摘要将显示为占位文本（无真实 AI 翻译/摘要）")
            logger.error(f"最后错误: {e}")
            logger.error("=" * 60)
            # 降级处理：返回原始数据
            return [{
                'title_en': art['title'],
                'title_cn': art['title'],  # 无法翻译
                'summary': 'AI处理失败，请查看原文',
                'url': art['url']
            } for art in articles]


def process_daily_report(
    weather_data: Dict,
    news_list: List[Dict],
    processor: 'GeminiProcessor' = None
) -> Dict:
    """
    统一处理每日报告的所有AI内容

    Args:
        weather_data: 天气数据
        news_list: 原始新闻列表（包含 title, url, source, date）
        processor: 可选的 GeminiProcessor 实例（用于测试时注入 mock）

    Returns:
        包含所有生成内容的字典
    """
    # 使用注入的实例或创建新实例
    processor = processor or GeminiProcessor(config.GEMINI_API_KEY)
    
    result = {
        'greeting': '',
        'weather_advice': {},
        'processed_news': [],
        'character': '',
        'model': ''
    }
    
    try:
        # 1. 选择角色
        character = random.choice(config.HARRY_POTTER_CHARACTERS)
        result['character'] = character
        logger.info(f"选择角色: {character}")
        
        # 2. 生成主要内容（问候、建议、筛选）
        logger.info("正在生成主要内容（问候+建议+筛选）...")
        master_content = processor.generate_master_content(character, weather_data, news_list)
        
        result['greeting'] = master_content.get('greeting', '')
        result['weather_advice'] = {
            'beijing': master_content.get('advice_beijing', ''),
            'jinan': master_content.get('advice_jinan', '')
        }
        # 主内容实际使用的 AI 模型（供邮件开头标签展示）
        result['model'] = getattr(processor, 'used_model', '') or ''
        
        # 3. 处理选中的新闻
        selected_news = master_content.get('selected_news', [])
        logger.info(f"AI选中了 {len(selected_news)} 条新闻")

        # 构建待抓取文章列表
        articles_to_fetch = []
        for item in selected_news:
            idx = item.get('index') if isinstance(item, dict) else item
            category = item.get('category', 'C') if isinstance(item, dict) else 'C'
            if isinstance(idx, int) and 0 <= idx - 1 < len(news_list):
                news = news_list[idx - 1]
                articles_to_fetch.append({
                    'title': news['title'],
                    'url': news['url'],
                    'description': news.get('description', ''),
                    'date': news.get('date', ''),
                    'source': news.get('source', ''),
                    'category': category
                })

        # 异步抓取文章内容
        articles_to_process = []
        if articles_to_fetch:
            logger.info(f"正在异步抓取 {len(articles_to_fetch)} 篇文章详情...")
            articles_to_process = asyncio.run(fetch_articles_async(articles_to_fetch))
            logger.info(f"  - 异步抓取完成，获取 {len(articles_to_process)} 篇")

        # 4. 批量处理新闻内容
        if articles_to_process:
            logger.info("正在批量处理新闻内容...")
            processed = processor.process_news_batch(articles_to_process)

            # 添加日期和来源信息到结果中
            for i, item in enumerate(processed):
                if i < len(articles_to_process):
                    item['date'] = articles_to_process[i].get('date', '')
                    item['source'] = articles_to_process[i].get('source', '')
                    item['category'] = articles_to_process[i].get('category', 'C')

            result['processed_news'] = processed
            
        logger.info("所有AI处理完成")
        
    except Exception as e:
        logger.error(f"处理每日报告失败: {e}")
    
    return result


if __name__ == '__main__':
    # 测试代码（注意：会真实调用 AI API 并消耗 token）
    # 模拟数据
    weather_data = {
        'beijing': {'weather': '晴', 'temperature': '5~15℃', 'wind': '北风3级'},
        'jinan': {'weather': '多云', 'temperature': '8~18℃', 'wind': '南风2级'}
    }
    
    news_list = [
        {'title': 'Scientists discover new planet', 'url': 'http://example.com/1'},
        {'title': 'New study on sleep patterns', 'url': 'http://example.com/2'},
        {'title': 'Breakthrough in quantum computing', 'url': 'http://example.com/3'}
    ]
    
    # AI处理
    processed_data = process_daily_report(weather_data, news_list)
    
    print(f"\n角色: {processed_data['character']}")
    print(f"问候: {processed_data['greeting']}")
    print(f"\n北京建议: {processed_data['weather_advice']['beijing']}")
    print(f"新闻数量: {len(processed_data['processed_news'])}")
