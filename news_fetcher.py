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
import time
import re

logger = logging.getLogger(__name__)


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
            'nature': ('https://www.nature.com/nature.rss', 'Nature'),
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
            tasks.append(('rss', url, source_name, 60))
        for key, (url, source_name) in self.science_rss.items():
            tasks.append(('rss', url, source_name, 60))
        for key, (url, source_name) in self.sciencedaily_rss.items():
            tasks.append(('rss', url, source_name, 40))
        for key, (url, source_name) in self.psychology_rss.items():
            tasks.append(('rss', url, source_name, 40))
        
        # 并行抓取（最多 8 个线程）
        with ThreadPoolExecutor(max_workers=8) as executor:
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
                    result = future.result(timeout=20)
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
            response = self.session.get(self.nature_web['nature_news'], timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            news_list = []
            # Nature 使用 c-article-item 结构
            articles = soup.select('div.c-article-item__content')
            
            for article in articles[:50]:  # 增加获取数量
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
                    'title': title,
                    'url': url,
                    'source': 'Nature News',
                    'date': self._parse_date(date_str),
                    'description': summary
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
            rss_response = self.session.get(rss_url, timeout=15)
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
                    summary = re.sub(r'<[^>]+>', '', summary).strip()
                
                news_list.append({
                    'title': title,
                    'url': url,
                    'source': source_name,
                    'date': date_str,
                    'description': summary
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
    
    def fetch_article_content(self, url: str) -> Dict:
        """
        获取文章详细内容
        
        Args:
            url: 文章URL
            
        Returns:
            包含 title, abstract, full_text 的字典
        """
        try:
            logger.info(f"正在获取文章详情: {url}")
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 根据不同网站使用不同的解析策略
            if 'nature.com' in url:
                return self._parse_nature_article(soup, url)
            elif 'sciencedaily.com' in url:
                return self._parse_sciencedaily_article(soup, url)
            elif 'science.org' in url:
                return self._parse_science_article(soup, url)
            else:
                return {'title': '未知', 'abstract': '', 'full_text': '', 'url': url}
                
        except Exception as e:
            logger.error(f"获取文章详情失败 {url}: {e}")
            return {'title': '未知', 'abstract': '', 'full_text': '', 'url': url}
    
    def _parse_nature_article(self, soup: BeautifulSoup, url: str) -> Dict:
        """解析 Nature 文章"""
        title_elem = soup.select_one('h1.c-article-title, h1')
        title = title_elem.get_text(strip=True) if title_elem else '未知'
        
        abstract_elem = soup.select_one('div#Abs1-content, div.c-article-section__content')
        abstract = abstract_elem.get_text(strip=True) if abstract_elem else ''
        
        # 获取文章主体
        body_elem = soup.select_one('div.c-article-body, article')
        if body_elem:
            for script in body_elem(['script', 'style']):
                script.decompose()
            full_text = body_elem.get_text(separator='\n', strip=True)
        else:
            full_text = abstract
        
        return {
            'title': title,
            'abstract': abstract,
            'full_text': full_text[:5000],  # 限制长度
            'url': url
        }
    
    def _parse_sciencedaily_article(self, soup: BeautifulSoup, url: str) -> Dict:
        """解析 ScienceDaily 文章"""
        title_elem = soup.select_one('#headline')
        title = title_elem.get_text(strip=True) if title_elem else '未知'
        
        intro_elem = soup.select_one('#abstract')
        abstract = intro_elem.get_text(strip=True) if intro_elem else ''
        
        story_elem = soup.select_one('#story_text')
        if story_elem:
            for script in story_elem(['script', 'style']):
                script.decompose()
            full_text = story_elem.get_text(separator='\n', strip=True)
        else:
            full_text = abstract
        
        return {
            'title': title,
            'abstract': abstract,
            'full_text': full_text[:5000],
            'url': url
        }
    
    def _parse_science_article(self, soup: BeautifulSoup, url: str) -> Dict:
        """解析 Science 文章"""
        title_elem = soup.select_one('h1.article__headline, h1')
        title = title_elem.get_text(strip=True) if title_elem else '未知'
        
        abstract_elem = soup.select_one('div.article__summary, p.article__teaser')
        abstract = abstract_elem.get_text(strip=True) if abstract_elem else ''
        
        body_elem = soup.select_one('div.article__body, article')
        if body_elem:
            for script in body_elem(['script', 'style']):
                script.decompose()
            full_text = body_elem.get_text(separator='\n', strip=True)
        else:
            full_text = abstract
        
        return {
            'title': title,
            'abstract': abstract,
            'full_text': full_text[:5000],
            'url': url
        }


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
