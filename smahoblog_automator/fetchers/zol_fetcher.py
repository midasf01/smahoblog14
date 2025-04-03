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

    def fetch_article_data(self, url: str) -> Optional[Dict[str, any]]:
        """指定されたURLからZOLの記事データを取得"""
        retry_count = 0
        
        # URLがPC版の場合はモバイル版に変換
        if "news.zol.com.cn" in url:
            url = url.replace("news.zol.com.cn", "m.zol.com.cn")
            logger.debug(f"PC版URLをモバイル版に変換: {url}")
        
        while retry_count < self.max_retries:
            try:
                # モバイル版URLでアクセス
                response = requests.get(url, headers=self.headers, timeout=20, allow_redirects=True)
                response.raise_for_status()
                response.encoding = response.apparent_encoding
                
                # 成功したらループを抜ける
                break
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"{self.__class__.__name__}: 記事データ取得中にエラー発生、リトライ {retry_count}/{self.max_retries}: {e}")
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"{self.__class__.__name__}: 記事データの取得に失敗しました ({url}): {e}")
                    return None
        
        try:
            # リダイレクト後のURLを確認
            final_url = response.url
            logger.debug(f"最終アクセスURL: {final_url} (リダイレクト元: {url})")
            
            # リダイレクト先がPC版の場合は再度モバイル版にアクセス
            if "news.zol.com.cn" in final_url:
                mobile_url = final_url.replace("news.zol.com.cn", "m.zol.com.cn")
                logger.debug(f"PC版にリダイレクトされたため、モバイル版に再アクセス: {mobile_url}")
                try:
                    response = requests.get(mobile_url, headers=self.headers, timeout=20)
                    if response.status_code == 200:
                        response.encoding = response.apparent_encoding
                        final_url = mobile_url
                    else:
                        logger.warning(f"モバイル版への再アクセスが失敗しました: {mobile_url}")
                except Exception as e:
                    logger.warning(f"モバイル版への再アクセス中にエラー: {e}")
            
            # モバイル版のHTMLを解析
            mobile_soup = BeautifulSoup(response.text, 'html.parser')

            # --- タイトル取得 ---
            # 様々なセレクタを試す
            title_selectors = [
                'h1.title', 'h3.title', 'h1.article-title', 'h1.article-header', 
                '.article-header h1', '.article-title', '.news-title',
                'header h1', '.news-header h1', 'article h1',
                'div.detail-text h3.title', '.article-info h1', '.title'
            ]
            
            title_tag = None
            for selector in title_selectors:
                title_tag = mobile_soup.select_one(selector)
                if title_tag:
                    break
            
            # タイトルタグが見つからない場合、メタデータを確認
            if not title_tag:
                meta_title = mobile_soup.select_one('meta[property="og:title"]')
                if meta_title:
                    title = meta_title.get('content', '').strip()
                else:
                    title_tag = mobile_soup.select_one('title')
                    title = title_tag.get_text().split('-')[0].strip() if title_tag else "取得できませんでした"
            else:
                title = title_tag.get_text(strip=True)
                
            if title == "取得できませんでした":
                logger.warning(f"タイトルが見つかりませんでした: {final_url}")

            # --- 本文HTML取得 ---
            # 記事本文コンテナを特定 - より具体的なセレクタを優先
            content_selectors = [
                'div.article-cont', 
                'div.detail-text', 
                'div.article-content', 
                'div.article__content', 
                '.article-cont.clearfix',
                '#article-content',
                '.news-content',
                'article .content',
                '.article .content',
                '.content-detail',
                'div.article',
                'div.content'
            ]
            
            content_div = None
            for selector in content_selectors:
                content_div = mobile_soup.select_one(selector)
                if content_div:
                    logger.debug(f"本文コンテナ発見: {selector}")
                    break
                    
            if not content_div:
                # より柔軟なアプローチでの本文取得を試みる
                # ヒューリスティックス: 記事本文は通常、多くのテキストを含むdiv要素
                possible_content_divs = []
                for div in mobile_soup.find_all('div'):
                    # クラス名に'article'または'content'を含む要素を探す
                    has_content_class = any(cls and ('article' in cls.lower() or 'content' in cls.lower()) 
                                          for cls in div.get('class', []))
                    
                    # テキスト量が十分あるか確認
                    text_length = len(div.get_text(strip=True))
                    has_paragraph = div.find('p') is not None
                    
                    if (has_content_class and text_length > 100) or (text_length > 300 and has_paragraph):
                        possible_content_divs.append((div, text_length))
                
                # テキスト量でソートして最も内容量の多いdivを選択
                if possible_content_divs:
                    possible_content_divs.sort(key=lambda x: x[1], reverse=True)
                    content_div = possible_content_divs[0][0]
                    logger.debug(f"ヒューリスティック分析で本文コンテナを発見: {content_div.get('class', '')}")
            
            # それでも取得できなかった場合はフォールバック
            if not content_div:
                logger.error(f"本文コンテナが見つかりませんでした: {final_url}")
                content_html = "<div>本文を取得できませんでした</div>"
            else:
                # 不要な要素（広告、関連リンク、コメント欄など）を除外
                for ad_div in content_div.select('div.recommend-box, div.ad-box, div.article-topic, div.article-footer, .recommend, .article-related, .article-foot, .article-footer, .related-content'):
                    if ad_div:
                        ad_div.decompose()
                
                # 本文HTMLを取得
                content_html = str(content_div)

            # --- 画像情報 ---
            images = []
            
            # 1. メタデータからOGP画像を探す（最優先）
            og_image = mobile_soup.select_one('meta[property="og:image"]')
            if og_image and og_image.get('content'):
                src = og_image.get('content')
                src = self._normalize_url(src, final_url)
                if self._is_content_image(src) and not any(i['src'] == src for i in images):
                    images.append({
                        'src': src,
                        'order': len(images),
                        'alt': title
                    })
                    logger.debug(f"OGP画像を取得: {src}")
            
            # 2. 本文内の画像を取得（記事本文の直接の子要素から）- 高品質なものを優先
            if content_div:
                # 本文内のメイン画像を優先的に取得
                main_img_selectors = [
                    'img.content-top-img-yh', 'img.content-top-img', 'img.origin-img', 
                    'img.article-top-img', 'img.big-img', 'img.big-pic', 'img.pic-large'
                ]
                
                for selector in main_img_selectors:
                    for img in content_div.select(selector):
                        # 画像のサイズ属性を確認
                        width = img.get('width')
                        height = img.get('height')
                        
                        # 小さすぎる画像や正方形の画像（アイコンの可能性）は無視
                        if width and height:
                            try:
                                w, h = int(width), int(height)
                                # 小さすぎる画像は除外
                                if w < 100 or h < 100:
                                    continue
                                # 極端に正方形に近い小さい画像はアイコンの可能性が高いので除外
                                ratio = max(w, h) / min(w, h)
                                if 0.9 <= ratio <= 1.1 and max(w, h) < 200:
                                    continue
                            except (ValueError, TypeError):
                                pass
                        
                        src = self._get_valid_image_src(img)
                        if src:
                            src = self._normalize_url(src, final_url)
                            if self._is_content_image(src) and self._is_high_quality_image(src) and not any(i['src'] == src for i in images):
                                images.append({
                                    'src': src,
                                    'order': len(images),
                                    'alt': img.get('alt', '') or title
                                })
                                logger.debug(f"本文内の主要画像を取得: {src}")
                
                # 本文内のその他の画像 - 高品質なものだけをフィルタリング
                for img in content_div.find_all('img'):
                    # すでに処理済みのclass属性を持つ画像はスキップ
                    if img.get('class') and any(cls in ['content-top-img-yh', 'content-top-img', 'origin-img', 'article-top-img'] 
                                               for cls in img.get('class')):
                        continue
                    
                    # スキップする画像パターン
                    skip_patterns = ['icon', 'logo', 'avatar', 'face', 'user', 'btn', 'banner', 'ad-', 'recommend']
                    if any(pattern in str(img).lower() for pattern in skip_patterns):
                        continue
                    
                    # 画像のサイズ属性を確認
                    width = img.get('width')
                    height = img.get('height')
                    
                    # 小さすぎる画像や正方形の画像（アイコンの可能性）は無視
                    if width and height:
                        try:
                            w, h = int(width), int(height)
                            # 小さすぎる画像は除外
                            if w < 100 or h < 100:
                                continue
                            # 極端に正方形に近い小さい画像はアイコンの可能性が高いので除外
                            ratio = max(w, h) / min(w, h)
                            if 0.9 <= ratio <= 1.1 and max(w, h) < 200:
                                continue
                        except (ValueError, TypeError):
                            pass
                    
                    src = self._get_valid_image_src(img)
                    if src:
                        src = self._normalize_url(src, final_url)
                        # 高品質な画像のみを受け入れる
                        if self._is_content_image(src) and self._is_high_quality_image(src) and not any(i['src'] == src for i in images):
                            images.append({
                                'src': src,
                                'order': len(images),
                                'alt': img.get('alt', '') or title
                            })
                            logger.debug(f"本文内の高品質画像を取得: {src}")
            
            # 3. 記事本文の#src=リンクから画像を取得 - 高品質を確認
            if content_div:
                for a_tag in content_div.find_all('a', href=True):
                    href = a_tag.get('href', '')
                    if '#src=' in href:
                        try:
                            src_part = href.split('#src=')[1]
                            if src_part:
                                src = unquote(src_part)
                                if src.startswith('/'):
                                    src = 'https:' + src
                                if self._is_content_image(src) and self._is_high_quality_image(src) and not any(i['src'] == src for i in images):
                                    images.append({
                                        'src': src,
                                        'order': len(images),
                                        'alt': a_tag.get_text(strip=True) or title
                                    })
                                    logger.debug(f"本文リンクから高品質画像を取得: {src}")
                        except Exception as e:
                            logger.debug(f"画像リンク解析エラー: {e}")
            
            # 4. モバイルページ内のJavaScriptデータからの画像抽出を試みる
            script_data = None
            for script in mobile_soup.find_all('script'):
                script_text = script.string
                if script_text and 'var page = ' in script_text:
                    try:
                        # JavaScriptデータから画像URLを抽出
                        img_matches = re.findall(r'(https?:)?//[^\s"\']+?\.(jpg|jpeg|png|webp)[^\s"\']*', script_text)
                        for img_match in img_matches:
                            img_url = img_match[0] + img_match[1] if img_match[0] else 'https:' + img_match[1]
                            img_url = img_url.replace('\\', '')
                            if self._is_content_image(img_url) and self._is_high_quality_image(img_url) and not any(i['src'] == img_url for i in images):
                                images.append({
                                    'src': img_url,
                                    'order': len(images),
                                    'alt': title
                                })
                                logger.debug(f"スクリプトデータから画像を取得: {img_url}")
                    except Exception as e:
                        logger.debug(f"スクリプトデータの解析エラー: {e}")
            
            # 5. それでも画像が見つからない場合は、ページ全体から適切な画像を探す
            if not images:
                logger.debug("画像が見つからないため、ページ全体から探索します")
                # ZOLの特定の画像パターンに合致する画像を探す
                zol_img_patterns = [
                    'zol-img.com.cn/t_s', 
                    'zol-img.com.cn/product', 
                    'zol-img.com.cn/g', 
                    '/ChMk', 
                    'origin-img', 
                    'big-img'
                ]
                
                # ページ全体から画像を探索
                for img in mobile_soup.find_all('img'):
                    # 画像サイズ属性の確認
                    width = img.get('width')
                    height = img.get('height')
                    
                    if width and height:
                        try:
                            w, h = int(width), int(height)
                            if w < 100 or h < 100:
                                continue
                            ratio = max(w, h) / min(w, h)
                            if 0.9 <= ratio <= 1.1 and max(w, h) < 200:
                                continue
                        except (ValueError, TypeError):
                            pass
                    
                    src = self._get_valid_image_src(img)
                    if src:
                        src = self._normalize_url(src, final_url)
                        # ZOLの一般的パターンを確認
                        if any(pattern in src for pattern in zol_img_patterns) and self._is_high_quality_image(src):
                            if not any(i['src'] == src for i in images):
                                images.append({
                                    'src': src,
                                    'order': len(images),
                                    'alt': img.get('alt', '') or title
                                })
                                logger.debug(f"ページ全体からZOLパターン画像を取得: {src}")
                                if len(images) >= 1:  # 1枚見つかれば十分
                                    break
                                
                # どうしても見つからない場合は、サイズが小さくても画像を追加する
                if not images:
                    logger.debug("高品質な画像が見つからないため、小さい画像も許容します")
                    for img in mobile_soup.find_all('img'):
                        src = self._get_valid_image_src(img)
                        if src and not any(pattern in src.lower() for pattern in ['icon', 'logo', 'avatar']):
                            src = self._normalize_url(src, final_url)
                            if not any(i['src'] == src for i in images):
                                images.append({
                                    'src': src,
                                    'order': len(images),
                                    'alt': img.get('alt', '') or title
                                })
                                logger.debug(f"代替画像を取得: {src}")
                                break

            # データベース用に画像数を最適化 - 高品質な画像を優先して保持（上位5枚まで）
            if len(images) > 5:
                logger.debug(f"画像が多すぎるため、上位5枚に制限します: {len(images)} -> 5")
                # 既に順序付けられているため、単純に上位5枚を保持
                images = images[:5]
                # 順序を更新
                for i, img in enumerate(images):
                    img['order'] = i

            article_data = {
                'title': title,
                'content_html': content_html,
                'original_url': url,
                'final_url': final_url,
                'images': images
            }
            logger.info(f"記事データを取得しました: {final_url} (タイトル: {title[:30]}...), 画像数: {len(images)}")
            return article_data

        except requests.exceptions.RequestException as e:
            logger.error(f"{self.__class__.__name__}: 記事データの取得中にエラーが発生しました ({url}): {e}")
            return None
        except Exception as e:
            logger.error(f"{self.__class__.__name__}: 記事データの解析中に予期せぬエラーが発生しました ({url}): {e}")
            return None 

    def _extract_article_id(self, url: str) -> Optional[str]:
        """URLから記事IDを抽出"""
        article_id = None
        patterns = [
            r'/(\d+)\.html',
            r'/article/(\d+)\.html',
            r'/news/(\d+)\.html'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                article_id = match.group(1)
                break
                
        return article_id
    
    def _extract_keywords(self, title: str) -> List[str]:
        """タイトルから重要なキーワードを抽出"""
        # 中国語のタイトルから不要な単語を除去して重要な単語を抽出
        stopwords = ['：', '的', '是', '在', '了', '和', '与', '或', '将', '从', '到', '为', '对', '由', '有']
        words = []
        
        # 記号で分割して単語を抽出
        raw_words = re.split(r'[：，。？！；：\s]', title)
        for word in raw_words:
            if word and word not in stopwords and len(word) >= 2:
                words.append(word.lower())
        
        return words
    
    def _is_high_quality_image(self, url: str) -> bool:
        """高品質な画像かどうかを判定"""
        # ZOLの高品質画像はt_sの後に大きなサイズを持つことが多い
        size_patterns = [
            't_s2000x', 't_s1000x', 't_s800x', 't_s600x',
            's240x', 's180x', 's300x', 's800x', 's600x',
            'origin-img', 'big-img', 'large'
        ]
        
        # URLから推定されるアスペクト比が極端に正方形に近い場合は除外（アイコンの可能性が高い）
        aspect_ratio_patterns = [
            'x150c', 'x180c', 'c2/', 'c4/', 'c8/',  # cはcropの意味で正方形にトリミングされた画像
            's50x50', 's60x60', 's80x80', 's100x100', 's120x120', 's150x150', 's180x180'
        ]
        
        for pattern in aspect_ratio_patterns:
            if pattern in url:
                return False
        
        # 小さい画像サイズは除外
        small_size_patterns = ['s50x', 's60x', 's100x', '_50x', '_60x', '_80x', '_100x', 'icon']
        if any(pattern in url for pattern in small_size_patterns):
            return False
        
        # 低品質や装飾画像を除外
        low_quality_patterns = ['banner', 'icon', 'btn', 'nav', 'logo', 'avatar', 'ico-', 'ico_', 'ico.']
        if any(pattern in url.lower() for pattern in low_quality_patterns):
            return False
        
        # ZOL特有の高品質画像パターン
        if 'ChMk' in url or '/M00/' in url:
            return True
        
        # 画像URLからサイズ情報を抽出して判定
        # t_s800x600, s800x600のような形式
        size_match = re.search(r'[st]_?s?(\d+)x(\d+)', url)
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            
            # 小さすぎる画像は除外
            if width < 120 or height < 120:
                return False
            
            # 極端に正方形に近い画像はアイコンの可能性が高いので除外
            # ただし十分な大きさがある場合は許容
            ratio = max(width, height) / min(width, height)
            if 0.9 <= ratio <= 1.1 and width < 200:
                return False
            
            # サイズが十分大きい場合は高品質とみなす
            if width >= 300 or height >= 300:
                return True
        
        return any(pattern in url for pattern in size_patterns)

    def _is_content_image(self, url: str) -> bool:
        """本文関連の画像かどうかを判定"""
        # 小さなアイコン、ロゴ、バナーなどを除外
        exclude_patterns = [
            'icon', 'logo', 'avatar', 'face', 'user', 'btn', 'banner',
            'share', 'footer', 'header', 'nav', 'qrcode', 'qrimg',
            'adload', 'sprite', 'recommend', 'mypp-fd', '_50.jpg',
            'default_', 'app/qrimg', 'zol-img.com.cn/group', 'lazy-icon',
            'ico-', 'ico_', 'ico.', 'head.', 'head-'
        ]
        
        for pattern in exclude_patterns:
            if pattern in url.lower():
                return False
            
        # アスペクト比に基づくフィルタリング（正方形の小さい画像は除外）
        square_patterns = ['50x50', '60x60', '80x80', '100x100', '120x120', 'x150c', 'x180c']
        if any(pattern in url for pattern in square_patterns):
            return False
            
        # ファイルサイズの小さいパターンを除外
        small_size_patterns = ['_50x', '_80x', '_50.', '_60.', '_80.', 'micro']
        for pattern in small_size_patterns:
            if pattern in url.lower():
                return False
        
        # ZOLの一般的な画像パターンに合致するか確認 - 優先度の高いものから
        high_quality_patterns = [
            '/t_s2000x', '/t_s1000x', '/g7/M00', 'ChMk', 
            'doc-fd.zol-img.com.cn/t_s', 'product/gallery',
            'content-top-img', 'origin-img', 'big-img', 'pic-large',
            'mobile', 'cell_phone', 'smartphone'  # モバイル関連の画像を優先
        ]
        
        for pattern in high_quality_patterns:
            if pattern in url:
                return True
            
        # 一般的な画像パターン
        general_patterns = [
            '/t_s', '/g7/', '/g5/', '/M00/', 'zol-img', 'article',
            'content', 'news', 'pic', 'photo', 'image'
        ]
        
        for pattern in general_patterns:
            if pattern in url:
                return True
            
        # 画像ファイル拡張子を確認
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        for ext in image_extensions:
            if url.lower().endswith(ext):
                return True
            
        return False

    def _get_valid_image_src(self, img_tag) -> Optional[str]:
        """画像タグから有効なsrcを取得とサイズ情報を元に高品質な画像を優先"""
        src = None
        # 複数の可能性のある属性をチェック
        for attr in ['src', 'data-src', 'data-original', 'data-lazy-src', 'data-lazysrc', 'data-original-src']:
            if img_tag.get(attr) and not self._is_invalid_url(img_tag.get(attr)):
                src = img_tag.get(attr)
                break
                
        # 画像URLが見つからなかった場合はbackground-imageも確認
        if not src and img_tag.get('style'):
            style = img_tag.get('style')
            if 'background-image:' in style:
                bg_match = re.search(r'background-image:\s*url\([\'"]?(.*?)[\'"]?\)', style)
                if bg_match:
                    bg_url = bg_match.group(1)
                    if bg_url and bg_url != 'none' and not self._is_invalid_url(bg_url):
                        src = bg_url
        
        if src:
            # 画像サイズ情報が含まれているか確認し、高品質版を優先
            if 't_s' in src and not ('t_s800' in src or 't_s1000' in src or 't_s2000' in src):
                # 小さい画像のURLを大きい画像のURLに置き換え
                for size in ['t_s1000x', 't_s800x', 't_s600x']:
                    potential_high_res = re.sub(r't_s\d+x\d+', size, src)
                    if potential_high_res != src:
                        src = potential_high_res
                        break
        
        return src

    def _is_invalid_url(self, url: str) -> bool:
        """画像URLが無効かどうかをチェック"""
        if not url:
            return True
        # データURLやプレースホルダー画像を除外
        if url.startswith('data:'):
            return True
        # テンプレート変数を含むURLを除外
        if '{{' in url or '}}' in url:
            return True
        # 空の値や無効なURLを除外
        if url == 'none' or url == 'undefined' or url == 'null':
            return True
        return False

    def _normalize_url(self, url: str, base_url: str) -> str:
        """画像URLを正規化"""
        if url.startswith('//'):
            return 'https:' + url
        elif not url.startswith(('http://', 'https://')):
            return urljoin(base_url, url)
        return url