"""
科学新闻获取模块
支持多个新闻源：Nature, ScienceDaily (via RSS)
"""
import requests
from bs4 import BeautifulSoup
import feedparser
import logging
from typing import List, Dict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """清洗文本：合并换行/连续空白为单个空格

    RSS/网页标题可能携带换行、多余空白或 HTML 残留，
    在源头统一清洗，避免下游 prompt 编号行被破坏。

    Args:
        text: 原始文本

    Returns:
        清洗后的单行文本
    """
    return re.sub(r'\s+', ' ', text or '').strip()


# --- 抓取配置常量 ---
MAX_WORKERS = 8               # 并行抓取线程数
MAX_NATURE_ARTICLES = 50      # Nature 网页抓取最大条数
MAX_RSS_ITEMS = 60            # Nature/Science RSS 最大条数
MAX_SCIENCEDAILY_ITEMS = 40   # ScienceDaily/心理学源最大条数
REQUEST_TIMEOUT = 15          # HTTP 请求超时（秒）
FETCH_TIMEOUT = 20            # 单源并行任务超时（秒）

NATURE_RSS_URL = 'https://www.nature.com/nature.rss'  # Nature 主刊 RSS（预检抽检也复用此常量）


class MultiSourceNewsFetcher:
    """多源科学新闻获取器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        # Nature 网页抓取（仅 latest-news）
        self.nature_web = {
            'nature_news': 'https://www.nature.com/latest-news',
        }
        # Nature 系列 RSS
        self.nature_rss = {
            'nature': (NATURE_RSS_URL, 'Nature'),
            'nature_astro': ('https://www.nature.com/natastron.rss', 'Nature Astronomy'),
            'nature_psych': ('https://www.nature.com/nrpsychol.rss', 'Nature Reviews Psychology'),
            'nature_comms': ('https://www.nature.com/ncomms.rss', 'Nature Communications'),
        }
        # Science 杂志 RSS
        self.science_rss = {
            'science_news': ('https://www.science.org/rss/news_current.xml', 'Science'),
        }
        # ScienceDaily RSS
        self.sciencedaily_rss = {
            'sd_mind_brain': ('https://www.sciencedaily.com/rss/mind_brain.xml', 'ScienceDaily Brain'),
            'sd_top_science': ('https://www.sciencedaily.com/rss/top/science.xml', 'ScienceDaily Top'),
            'sd_top_news': ('https://www.sciencedaily.com/rss/top.xml', 'ScienceDaily'),
            'sd_space_time': ('https://www.sciencedaily.com/rss/space_time.xml', 'ScienceDaily Space'),
        }
        # 心理学专门源
        self.psychology_rss = {
            'psypost': ('https://www.psypost.org/feed/', 'PsyPost'),
            'neuroscience_news': ('https://neurosciencenews.com/feed/', 'Neuroscience News'),
            'pnas_psych': ('https://www.pnas.org/action/showFeed?type=searchTopic&taxonomyCode=psych-soc', 'PNAS Psychology'),
        }
    
    def fetch_all_news_titles(self) -> List[Dict]:
        """
        获取所有新闻源的标题列表
        
        Returns:
            新闻列表，每条包含 title, url, source, date
        """
        all_news = []
        
        logger.info("开始从多个新闻源并行获取标题...")
        
        # 构建所有抓取任务
        tasks = []
        # Nature 网页抓取
        tasks.append(('nature_web', None, None, None))
        # RSS 源
        for key, (url, source_name) in self.nature_rss.items():
            tasks.append(('rss', url, source_name, MAX_RSS_ITEMS))
        for key, (url, source_name) in self.science_rss.items():
            tasks.append(('rss', url, source_name, MAX_RSS_ITEMS))
        for key, (url, source_name) in self.sciencedaily_rss.items():
            tasks.append(('rss', url, source_name, MAX_SCIENCEDAILY_ITEMS))
        for key, (url, source_name) in self.psychology_rss.items():
            tasks.append(('rss', url, source_name, MAX_SCIENCEDAILY_ITEMS))
        
        # 并行抓取（最多 MAX_WORKERS 个线程）
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for task in tasks:
                if task[0] == 'nature_web':
                    fut = executor.submit(self._fetch_nature_news)
                else:
                    _, url, source_name, max_items = task
                    fut = executor.submit(self._fetch_rss, url, source_name, max_items)
                futures[fut] = task
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=FETCH_TIMEOUT)
                    all_news.extend(result)
                except Exception as e:
                    task_info = futures[future]
                    logger.error(f"获取 {task_info[2] or 'Nature News'} 失败: {e}")
        
        logger.info(f"总共获取 {len(all_news)} 条新闻标题")
        
        # 去重（基于 URL）
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news['url'] not in seen_urls:
                seen_urls.add(news['url'])
                unique_news.append(news)
        
        logger.info(f"去重后: {len(unique_news)} 条")
        
        # 过滤最近1天的新闻
        recent_news = self._filter_recent_news(unique_news, days=1)
        logger.info(f"过滤后保留最近1天的新闻: {len(recent_news)} 条")
        
        return recent_news
    
    def _fetch_nature_news(self) -> List[Dict]:
        """获取 Nature 最新新闻（网页抓取）"""
        try:
            logger.info("正在获取 Nature 最新新闻...")
            response = self.session.get(self.nature_web['nature_news'], timeout=REQUEST_TIMEOUT)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            news_list = []
            # Nature 使用 c-article-item 结构
            articles = soup.select('div.c-article-item__content')
            
            for article in articles[:MAX_NATURE_ARTICLES]:  # 限制获取数量
                title_elem = article.select_one('h3.c-article-item__title')
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                
                # 获取链接
                link_elem = article.select_one('a')
                url = link_elem.get('href', '') if link_elem else ''
                if url and not url.startswith('http'):
                    url = 'https://www.nature.com' + url
                
                # 提取日期 (格式: 03 DEC 2025)
                date_elem = article.select_one('span.c-article-item__date')
                date_str = date_elem.get_text(strip=True) if date_elem else ''
                
                # 提取摘要（如果有）
                summary_elem = article.select_one('div.c-article-item__description, p')
                summary = summary_elem.get_text(strip=True) if summary_elem else ''

                news_list.append({
                    'title': clean_text(title),
                    'url': url,
                    'source': 'Nature News',
                    'date': self._parse_date(date_str),
                    'description': clean_text(summary)
                })
            
            logger.info(f"  - Nature News: {len(news_list)} 条")
            return news_list
            
        except Exception as e:
            logger.error(f"获取 Nature 新闻失败: {e}")
            return []
    
    def _fetch_rss(self, rss_url: str, source_name: str, max_items: int = 50) -> List[Dict]:
        """
        通用 RSS 获取方法
        
        Args:
            rss_url: RSS feed URL
            source_name: 来源名称
            max_items: 最大获取条数
            
        Returns:
            新闻列表
        """
        try:
            logger.info(f"正在获取 {source_name} RSS...")
            # 先用 requests 带超时获取，再交给 feedparser 解析
            rss_response = self.session.get(rss_url, timeout=REQUEST_TIMEOUT)
            feed = feedparser.parse(rss_response.content)
            
            news_list = []
            for entry in feed.entries[:max_items]:
                title = entry.get('title', '').strip()
                url = entry.get('link', '')
                
                if not title or not url:
                    continue
                
                # 解析发布日期
                published = entry.get('published', '') or entry.get('updated', '')
                date_str = self._parse_rss_date(published)
                
                # 获取摘要/描述
                summary = entry.get('summary', '') or entry.get('description', '')
                # 清理HTML标签（简单清理）
                if summary:
                    summary = re.sub(r'<[^>]+>', '', summary)
                
                news_list.append({
                    'title': clean_text(title),
                    'url': url,
                    'source': source_name,
                    'date': date_str,
                    'description': clean_text(summary)
                })
            
            logger.info(f"  - {source_name}: {len(news_list)} 条")
            return news_list
            
        except Exception as e:
            logger.error(f"获取 {source_name} RSS 失败: {e}")
            return []
    
    def _parse_rss_date(self, date_str: str) -> str:
        """解析 RSS 日期格式为 YYYY-MM-DD"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        try:
            # RSS 常见日期格式: "Sun, 08 Dec 2025 05:00:00 GMT" 或 "2025-12-08T05:00:00Z"
            from email.utils import parsedate_tz, mktime_tz
            
            # 尝试 RFC 822 格式 (常见于 RSS)
            parsed = parsedate_tz(date_str)
            if parsed:
                timestamp = mktime_tz(parsed)
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            
            # 尝试 ISO 格式
            for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_str[:19], fmt)
                    return dt.strftime('%Y-%m-%d')
                except:
                    continue
            
            return datetime.now().strftime('%Y-%m-%d')
            
        except Exception as e:
            logger.warning(f"RSS日期解析失败 '{date_str}': {e}")
            return datetime.now().strftime('%Y-%m-%d')
    
    def _parse_date(self, date_str: str) -> str:
        """解析并标准化日期格式为 YYYY-MM-DD"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        try:
            # 尝试多种日期格式
            formats = [
                '%Y-%m-%d',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%d %b %Y',
                '%B %d, %Y'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str[:19] if 'T' in date_str else date_str, fmt)
                    return dt.strftime('%Y-%m-%d')
                except:
                    continue
            
            # 如果所有格式都失败，返回今天的日期
            return datetime.now().strftime('%Y-%m-%d')
            
        except Exception as e:
            logger.warning(f"日期解析失败 '{date_str}': {e}")
            return datetime.now().strftime('%Y-%m-%d')
    
    def _filter_recent_news(self, news_list: List[Dict], days: int = 2) -> List[Dict]:
        """过滤最近几天的新闻"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d')
        
        filtered = []
        for news in news_list:
            if news['date'] >= cutoff_str:
                filtered.append(news)
        
        return filtered
    
def fetch_all_news() -> List[Dict]:
    """
    获取所有新闻源的标题
    
    Returns:
        新闻列表，包含基本信息
    """
    fetcher = MultiSourceNewsFetcher()
    news_list = fetcher.fetch_all_news_titles()
    return news_list


if __name__ == '__main__':
    # 测试
    news = fetch_all_news()
    print(f"\n总共获取 {len(news)} 条新闻")
    for i, item in enumerate(news[:10], 1):
        print(f"\n{i}. [{item['source']}] {item['title']}")
        print(f"   日期: {item['date']}")
        print(f"   URL: {item['url']}")
