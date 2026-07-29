"""
异步新闻文章内容抓取模块
使用 aiohttp 并发抓取多篇文章详情
"""
import aiohttp
import asyncio
from typing import List, Dict
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# --- 抓取配置常量 ---
MAX_CONCURRENT_REQUESTS = 10      # 最大并发请求数
REQUEST_TIMEOUT = 15               # 单请求超时（秒）
MAX_CONTENT_LENGTH = 5000          # 单篇文章最大内容长度（字符）


class AsyncArticleFetcher:
    """异步文章抓取器"""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_REQUESTS):
        """
        Args:
            max_concurrent: 最大并发请求数
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    async def fetch_articles(self, articles: List[Dict]) -> List[Dict]:
        """异步抓取多篇文章

        Args:
            articles: 文章列表，每项包含 url, source, title, description 等字段

        Returns:
            包含 content 字段的文章列表（原始字典被修改）
        """
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [
                self._fetch_one(session, article)
                for article in articles
            ]
            return await asyncio.gather(*tasks)

    async def _fetch_one(self, session: aiohttp.ClientSession, article: Dict) -> Dict:
        """抓取单篇文章（带并发控制）

        Args:
            session: aiohttp 会话
            article: 文章数据字典

        Returns:
            更新后的文章字典
        """
        async with self.semaphore:  # 限制并发数
            url = article.get('url', '')
            source = article.get('source', '')

            # ScienceDaily 和 Science 直接使用 RSS 摘要，无需抓取
            if source == 'Science' or source.startswith('ScienceDaily'):
                article['content'] = article.get('description', article.get('title', ''))
                return article

            # Nature 等需要抓取全文
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        html = await response.text()
                        article['content'] = self._parse_article(html, url)
                    else:
                        logger.warning(f"抓取文章返回 {response.status}: {url}")
                        article['content'] = article.get('description', '抓取失败')
            except asyncio.TimeoutError:
                logger.warning(f"抓取文章超时: {url}")
                article['content'] = article.get('description', '抓取超时')
            except Exception as e:
                logger.error(f"抓取文章失败 {url}: {e}")
                article['content'] = article.get('description', '抓取失败')

            return article

    def _parse_article(self, html: str, url: str) -> str:
        """解析文章 HTML

        Args:
            html: 文章 HTML 内容
            url: 文章 URL（用于判断解析策略）

        Returns:
            提取的纯文本内容
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Nature 文章专用解析
        if 'nature.com' in url:
            return self._parse_nature(soup)

        # 通用解析：移除 script/style，提取所有文本
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        return soup.get_text(separator='\n', strip=True)[:MAX_CONTENT_LENGTH]

    def _parse_nature(self, soup: BeautifulSoup) -> str:
        """解析 Nature 文章

        Args:
            soup: BeautifulSoup 对象

        Returns:
            文章正文纯文本
        """
        # 优先提取摘要
        abstract_elem = soup.select_one('div#Abs1-content, div.c-article-section__content')
        abstract = abstract_elem.get_text(strip=True) if abstract_elem else ''

        # 提取正文
        body_elem = soup.select_one('div.c-article-body, article')
        if body_elem:
            for script in body_elem(['script', 'style']):
                script.decompose()
            full_text = body_elem.get_text(separator='\n', strip=True)
        else:
            full_text = abstract

        return full_text[:MAX_CONTENT_LENGTH]


async def fetch_articles_async(articles: List[Dict], max_concurrent: int = MAX_CONCURRENT_REQUESTS) -> List[Dict]:
    """异步抓取文章的便捷函数

    Args:
        articles: 文章列表
        max_concurrent: 最大并发请求数

    Returns:
        包含 content 字段的文章列表

    示例：
        >>> articles = [{'url': 'https://...', 'source': 'Nature', 'title': '...'}]
        >>> result = asyncio.run(fetch_articles_async(articles))
    """
    fetcher = AsyncArticleFetcher(max_concurrent=max_concurrent)
    return await fetcher.fetch_articles(articles)
