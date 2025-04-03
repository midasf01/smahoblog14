import logging
import requests
import re
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from typing import List, Dict, Optional, Tuple

from .base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)

class ZolFetcher(BaseFetcher):
    """ZOL.com.cn用のFetcher - モバイル端末専用セクションから記事を取得"""

    # モバイルブラウザのユーザーエージェントリスト
    MOBILE_USER_AGENTS = [
        # iPhone
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/96.0.4664.53 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 15_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Safari/605.1.15',
        # Android
        'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36',
        # ファーウェイ
        'Mozilla/5.0 (Linux; Android 10; VOG-L29) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
        # シャオミ
        'Mozilla/5.0 (Linux; Android 11; M2102K1G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Mobile Safari/537.36'
    ]

    def __init__(self, headers: Optional[Dict[str, str]] = None):
        # モバイル版サイトをターゲットにします
        if headers is None:
            # ランダムなモバイル用ユーザーエージェントを選択
            mobile_ua = random.choice(self.MOBILE_USER_AGENTS)
            headers = {
                'User-Agent': mobile_ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,ja;q=0.8,en-US;q=0.7,en;q=0.6',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
                'Referer': 'https://m.zol.com.cn/mobile/'
            }
            logger.debug(f"モバイル用ユーザーエージェントを使用: {mobile_ua}")
        
        # URLをモバイル専用セクションに変更
        super().__init__(site_url="https://m.zol.com.cn/mobile/", headers=headers)
        # 最大リトライ回数
        self.max_retries = 3
        # リトライ間の待機時間（秒）
        self.retry_delay = 1

    def fetch_article_links(self, limit: int) -> List[Tuple[str, Optional[str]]]:
        """ZOLのモバイルセクションから記事リンクを取得"""
        article_links = []
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                response = requests.get(self.site_url, headers=self.headers, timeout=15)
                response.raise_for_status()
                response.encoding = response.apparent_encoding  # 文字化け対策
                
                # 成功したらループを抜ける
                break
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"{self.__class__.__name__}: 記事リスト取得中にエラー発生、リトライ {retry_count}/{self.max_retries}: {e}")
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"{self.__class__.__name__}: 記事リスト取得に失敗しました: {e}")
                    return []
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')

            # モバイルセクションの記事リスト - 様々なセレクタを試す
            list_items = []
            
            # モバイルページの記事リストセレクタ
            selectors = [
                '.news-list a', # 一般的なニュース記事のセレクタ
                '.list-item a',  # リスト項目
                '.item-news a',  # ニュース項目
                'ul li a',       # リストアイテム
                'a[href*="/article/"]',  # /article/を含むリンク
                'a[href*="/index"]',     # /indexを含むリンク
                'div > a'        # 汎用セレクタ
            ]
            
            # 複数のセレクタを順番に試す
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    list_items.extend(items)
                    logger.debug(f"セレクタ '{selector}' で {len(items)} 個の記事リンクが見つかりました")
            
            # 重複を排除
            unique_items = {}
            for item in list_items:
                href = item.get('href')
                if href and href not in unique_items:
                    unique_items[href] = item
            
            list_items = list(unique_items.values())
            
            if not list_items:
                logger.warning(f"{self.__class__.__name__}: 記事リスト要素が見つかりませんでした。サイト構造が変更された可能性があります。")
                return []

            for item in list_items:
                if len(article_links) >= limit:
                    break

                href = item.get('href')
                
                # タイトル取得 - 複数のセレクタを試す
                title_tag = None
                title_selectors = ['h3', '.title', 'h4', '.item-title', 'p', 'div.text']
                for selector in title_selectors:
                    title_tag = item.select_one(selector)
                    if title_tag:
                        break
                    
                title = title_tag.get_text(strip=True) if title_tag else None

                # タイトルが見つからない場合は、親要素またはitem自体のテキストを確認
                if not title and item.get_text(strip=True):
                    title = item.get_text(strip=True)

                if href:
                    # 相対URLを絶対URLに変換
                    if href.startswith('//'):
                        full_url = urljoin("https:", href)
                    elif not href.startswith(('http://', 'https://')):
                        full_url = urljoin(self.site_url, href)
                    else:
                        full_url = href

                    # モバイル関連の記事に絞る
                    # ZOLのモバイル関連記事は以下のパターンを含むことが多い
                    mobile_patterns = ['/mobile/', '/article/', '/news/', '/index', '/cell_phone/']
                    if "zol.com.cn" in full_url and any(pattern in full_url for pattern in mobile_patterns):
                        # PC版URLをモバイル版に変換
                        if "news.zol.com.cn" in full_url:
                            full_url = full_url.replace("news.zol.com.cn", "m.zol.com.cn")
                        article_links.append((full_url, title))
                        logger.debug(f"記事リンク発見: {full_url} (タイトル: {title})")

        except Exception as e:
            logger.error(f"{self.__class__.__name__}: 記事リストの解析中に予期せぬエラーが発生しました: {e}")

        if not article_links:
            logger.warning(f"{self.__class__.__name__}: 有効な記事リンクが見つかりませんでした。")

        logger.info(f"{self.__class__.__name__}: {len(article_links)} 件の記事リンクを取得しました。")
        return article_links