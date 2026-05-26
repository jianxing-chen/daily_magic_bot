"""
Gemini AI处理模块
使用Gemini API进行内容处理和生成
"""
from google import genai
from typing import List, Dict
import random
import logging
import json
import time

from config import config
from news_fetcher import MultiSourceNewsFetcher

logger = logging.getLogger(__name__)


class GeminiProcessor:
    """Gemini AI处理器"""
    
    def __init__(self, api_key: str):
        """
        初始化Gemini处理器
        
        Args:
            api_key: Gemini API密钥
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-3.5-flash'
        self.max_retries = 3
        logger.info("Gemini处理器初始化成功")
    
    def _call_with_retry(self, prompt: str, use_json: bool = True) -> str:
        """
        带指数退避重试的 Gemini API 调用
        
        对 503 (UNAVAILABLE) 和 429 (RESOURCE_EXHAUSTED) 等临时错误自动重试，
        最多重试 self.max_retries 次，退避时间依次为 15s、30s、60s。
        
        Args:
            prompt: 请求内容
            use_json: 是否要求 JSON 格式返回
            
        Returns:
            API 响应文本
        """
        config = {'response_mime_type': 'application/json'} if use_json else {}
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                error_str = str(e)
                is_retryable = any(code in error_str for code in ['503', '429', 'UNAVAILABLE', 'RESOURCE_EXHAUSTED'])
                
                if is_retryable and attempt < self.max_retries - 1:
                    wait_time = [15, 30, 60][attempt]
                    logger.warning(f"API 临时错误 (尝试 {attempt + 1}/{self.max_retries}): {error_str}")
                    logger.warning(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise  # 非临时错误或重试耗尽，抛出异常
    
    def generate_master_content(self, character_name: str, weather_info: Dict, news_list: List[Dict]) -> Dict:
        """
        一次性生成所有AI内容：问候（含新闻综述）、天气建议、新闻筛选
        
        Args:
            character_name: 角色名称
            weather_info: 天气数据
            news_list: 原始新闻列表（包含 title, url, source, date）
            
        Returns:
            JSON字典包含 greeting, advice_beijing, advice_jinan, selected_news_indices
        """
        try:
            beijing = weather_info.get('beijing', {})
            jinan = weather_info.get('jinan', {})
            
            # 构建新闻列表文本（包含来源和日期）
            news_text = ""
            for i, news in enumerate(news_list, 1):
                news_text += f"{i}. [{news.get('source', 'Unknown')}] {news['title']} ({news.get('date', '')})\n"
            
            prompt = f"""你是哈利波特世界中的{character_name}。请完成以下任务（**请全程使用中文回答**）：

1. **角色问候**：以{character_name}的第一人称口吻用中文写一段开场白（100-150字）。
   - 总结今日天气（北京和济南）。
   - **简要提及今日科学界发生的有趣事情**（根据新闻列表）。
   - 语气符合角色性格，清新自然。

2. **天气建议**：分别为北京和济南给出穿衣建议。

3. **新闻筛选与分类**：从列表中选出 15-30 条与以下领域**关键词高度相关**的科学新闻。

   **领域A - 天体物理学**（关键词匹配优先）：
   - 核心：球状星团(globular cluster)、白矮星(white dwarf)、毫秒脉冲星(millisecond pulsar)、脉冲星(pulsar)、中子星(neutron star)
   - 恒星物理：恒星演化(stellar evolution)、星震学(asteroseismology)、变星(variable star)、双星(binary star)、恒星振荡(stellar oscillation)
   - 观测：望远镜(telescope)、X射线天文学(X-ray astronomy)、引力波(gravitational wave)、光谱(spectroscopy)、GAIA、TESS、Kepler
   
   **领域B - 元认知与心理学**（关键词匹配优先）：
   - 核心：元认知(metacognition)、信心(confidence)、不确定性(uncertainty)、错误监控(error monitoring)、内省(introspection)
   - 认知：知道感(feeling of knowing)、学习判断(judgment of learning)、自我意识(self-awareness)、工作记忆(working memory)、注意力(attention)、决策(decision making)
   - 神经科学：fMRI、EEG、脑成像(brain imaging)、前额叶(prefrontal cortex)、认知神经科学(cognitive neuroscience)
   
   **筛选原则**（按重要性排序）：
   1. **关键词相关性最重要**：标题或摘要中直接包含上述关键词的新闻优先级最高
   2. **领域专业源加权**：来自 Nature Astronomy、PsyPost、BPS Research Digest、PNAS Psychology 的相关新闻略微优先
   3. **日期次要**：同等相关性下，优先选择日期更近的新闻
   4. 总量控制在 15-30 条，优先选择 A 和 B 领域，C 领域宁缺毋滥

   **领域C（其他科学发现）的严格筛选标准**：
   C 类只收录满足以下任一条件的新闻，**不满足的坚决不选**：
   - 与日常生活直接相关的科学发现（如：健康医学、公共卫生、营养、睡眠、环境气候、新能源、AI应用、太空探索）
   - 真正改变世界的重大突破（如：诺奖级成果、首次实现/发现、颠覆性技术、改变人类认知的基础科学突破）

   **坚决排除**以下内容（即使来自 Nature/Science）：
   - 常规材料化学研究、催化剂优化、电池微改进等工业化学
   - 某蛋白结构解析、某基因测序、某化合物合成路线等常规分子生物学/化学
   - 某矿床发现、某地质年代划分等纯地质学
   - 纯工程学增量改进（如某合金强度提升 5%）
   - 纯方法论论文（如"一种改进的 XX 算法"）

   **请为每条新闻标注所属领域**：A（天体物理）、B（元认知/心理学）、C（其他重大发现）
输入数据：
【天气】
- 北京：{beijing.get('weather', '未知')}，{beijing.get('temperature', '未知')}，{beijing.get('wind', '未知')}
- 济南：{jinan.get('weather', '未知')}，{jinan.get('temperature', '未知')}，{jinan.get('wind', '未知')}

【新闻列表】
{news_text}

请严格按照以下 JSON 格式返回（不要包含 Markdown 代码块标记）：
{{
    "greeting": "角色开场白内容...",
    "advice_beijing": "北京穿衣建议...",
    "advice_jinan": "济南穿衣建议...",
    "selected_news": [
        {{"index": 1, "category": "A"}},
        {{"index": 3, "category": "B"}},
        ...
    ]  // 选中的新闻，包含编号和领域分类（A/B/C），15-30条
}}
"""
            
            response_text = self._call_with_retry(prompt, use_json=True)
            
            result = json.loads(response_text)
            
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
            
            return result
            
        except Exception as e:
            logger.error(f"生成主要内容失败: {e}")
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
            # 构建Prompt
            articles_text = ""
            for i, art in enumerate(articles, 1):
                # 限制每篇文章长度，避免token过多
                content_preview = art['content'][:5000]
                articles_text += f"""
文章 {i}:
标题: {art['title']}
内容: {content_preview}
---
"""
            
            prompt = f"""请批量处理以下 {len(articles)} 篇科学新闻/论文。

对于每一篇文章，请完成：
1. 将标题翻译成中文（准确、专业，保持学术风格）
2. 用中文总结文章核心内容，采用**倒金字塔结构**（先写最重要的发现/结论，再补充关键细节和背景）。总结应详实、全面且专业，涵盖核心发现、研究方法和科学意义。篇幅可稍长（约200-500字），确保读者无需阅读原文也能掌握文章全貌。

输入文章列表：
{articles_text}

请严格按照以下 JSON 格式返回列表（不要包含 Markdown 代码块标记）：
[
    {{
        "original_title": "原英文标题",
        "title_cn": "中文翻译标题",
        "summary": "中文总结内容（倒金字塔结构，一个小段落）"
    }},
    ...
]
"""
            
            response_text = self._call_with_retry(prompt, use_json=True)
            
            results = json.loads(response_text)
            
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
            logger.error(f"批量处理新闻失败: {e}")
            # 降级处理：返回原始数据
            return [{
                'title_en': art['title'],
                'title_cn': art['title'],  # 无法翻译
                'summary': 'AI处理失败，请查看原文',
                'url': art['url']
            } for art in articles]


def process_daily_report(weather_data: Dict, news_list: List[Dict]) -> Dict:
    """
    统一处理每日报告的所有AI内容
    
    Args:
        weather_data: 天气数据
        news_list: 原始新闻列表（包含 title, url, source, date）
        
    Returns:
        包含所有生成内容的字典
    """
    processor = GeminiProcessor(config.GEMINI_API_KEY)
    fetcher = MultiSourceNewsFetcher()
    
    result = {
        'greeting': '',
        'weather_advice': {},
        'processed_news': [],
        'character': ''
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
        
        # 3. 处理选中的新闻
        selected_news = master_content.get('selected_news', [])
        logger.info(f"AI选中了 {len(selected_news)} 条新闻")
        
        articles_to_process = []
        for item in selected_news:
            idx = item.get('index') if isinstance(item, dict) else item
            category = item.get('category', 'C') if isinstance(item, dict) else 'C'
            if isinstance(idx, int) and 0 <= idx - 1 < len(news_list):
                news = news_list[idx - 1]
                try:
                    # 根据来源决定获取内容的方式
                    # ScienceDaily 和 Science RSS 直接使用 RSS 中的摘要，避免抓取失败
                    source = news.get('source', '')
                    if source == 'Science' or source.startswith('ScienceDaily'):
                        logger.info(f"使用RSS摘要作为内容: {news['title']}")
                        content = news.get('description', '')
                        if not content:
                            content = news['title']  # 如果没有摘要，仅使用标题
                    else:
                        # 其他来源（如 Nature）尝试抓取全文
                        article = fetcher.fetch_article_content(news['url'])
                        content = article['full_text'] or article['abstract'] or "无内容"
                    
                    articles_to_process.append({
                        'title': news['title'],
                        'url': news['url'],
                        'content': content,
                        'date': news.get('date', ''),  # 保留日期
                        'source': source,  # 保留来源
                        'category': category  # 保留领域分类
                    })
                    
                    # 仅在抓取网页时暂停，避免爬虫请求过快
                    if not (source == 'Science' or source.startswith('ScienceDaily')):
                        time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"获取文章内容失败 {news['title']}: {e}")
                    continue
        
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
    # 测试代码
    from config import config
    from weather_parser import parse_weather_files
    
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
