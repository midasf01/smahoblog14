import abc
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class BaseFetcher(abc.ABC):
    """
    ニュース記事を取得するための抽象基底クラス。
    各サイト固有のFetcherはこのクラスを継承して実装する。
    """

    def __init__(self, site_url: str, headers: Optional[Dict[str, str]] = None):
        """
        Args:
            site_url: 対象サイトのベースURLまたは一覧ページのURL。
            headers: requestsで使用するカスタムヘッダー（オプション）。
        """
        self.site_url = site_url
        self.headers = headers or {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        logger.info(f"{self.__class__.__name__} を初期化しました: {site_url}")

    @abc.abstractmethod
    def fetch_article_links(self, limit: int) -> List[Tuple[str, Optional[str]]]:
        """
        記事一覧ページから記事のURLとタイトル（取得できれば）のリストを取得する。

        Args:
            limit: 取得する記事リンク数の上限。

        Returns:
            (URL, タイトル) のタプルのリスト。タイトルが取得できない場合は None。
            例: [("http://example.com/article1", "記事タイトル1"), ("http://example.com/article2", None)]
                 取得に失敗した場合は空リストを返す。
        """
        pass

    @abc.abstractmethod
    def fetch_article_data(self, url: str) -> Optional[Dict[str, any]]:
        """
        指定されたURLから記事の詳細データを取得する。

        Args:
            url: 記事ページのURL。

        Returns:
            記事データの辞書。最低限以下のキーを含む:
                'title': 記事タイトル (str)
                'content_html': 記事本文のHTML (str)
                'original_url': 元記事のURL (str)
                'images': 本文中の画像情報リスト (List[Dict[str, str]]) - 将来的に実装
                          各辞書は 'src', 'order' などのキーを持つ想定。
            取得に失敗した場合は None を返す。
            例: {
                    'title': "記事タイトル",
                    'content_html': "<p>本文...</p><img src='...'>...",
                    'original_url': "http://example.com/article1",
                    'images': [{'src': 'url1', 'order': 0}, {'src': 'url2', 'order': 1}] #現時点では空リストで良い
                }
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}(site_url='{self.site_url}')>"