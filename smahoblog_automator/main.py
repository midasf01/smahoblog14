import os
import logging
import yaml
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Dict, Type
import time

# フェッチャーのインポート
from fetchers import BaseFetcher, AVAILABLE_FETCHERS

# ロギング設定
log_level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, log_level_name, logging.INFO)

# ルートロガーを設定
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ファイルハンドラ
log_file_path = os.path.join('logs', 'app.log')
os.makedirs('logs', exist_ok=True)
file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# コンソールハンドラ
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

# ルートロガーにハンドラを追加
root_logger = logging.getLogger()
root_logger.setLevel(numeric_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)

logger = logging.getLogger(__name__)  # このファイル用のロガー

def load_config() -> Dict:
    """config.yaml ファイルを読み込む"""
    config_path = 'config.yaml'
    try:
        # encoding='utf-8' を指定して開く
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if config is None:
                logger.warning(f"{config_path} が空または無効です。")
                return {}
            logger.info(f"{config_path} を読み込みました。")
            return config
    except FileNotFoundError:
        logger.error(f"設定ファイルが見つかりません: {config_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"設定ファイルの解析エラー: {e}")
        return {}
    except Exception as e:
        logger.error(f"設定ファイルの読み込み中に予期せぬエラーが発生しました: {e}")
        return {}

def get_active_fetchers() -> List[Tuple[BaseFetcher, int]]:
    """
    .env 設定に基づいて有効な Fetcher インスタンスと取得上限数をリストで返す。
    """
    active_fetchers = []
    for key, fetcher_cls in AVAILABLE_FETCHERS.items():
        # 例: key="zol", fetcher_cls=ZolFetcher
        enable_env_var = f"ENABLE_{key.upper()}"
        limit_env_var = f"FETCH_LIMIT_{key.upper()}"

        is_enabled = os.getenv(enable_env_var, 'False').lower() in ('true', '1', 't')
        limit_str = os.getenv(limit_env_var, '10')  # デフォルト10件

        if is_enabled:
            try:
                limit = int(limit_str)
                if limit <= 0:
                    logger.warning(f"{limit_env_var} は正の整数である必要があります。デフォルト値の10を使用します。")
                    limit = 10
                # Fetcher クラスのインスタンスを作成
                fetcher_instance = fetcher_cls()
                active_fetchers.append((fetcher_instance, limit))
                logger.info(f"{fetcher_cls.__name__} が有効です (上限: {limit}件)。")
            except ValueError:
                logger.error(f"{limit_env_var} の値 '{limit_str}' は有効な整数ではありません。{key} の Fetcher をスキップします。")
            except Exception as e:
                 logger.error(f"{fetcher_cls.__name__} の初期化中にエラーが発生しました: {e}")
        else:
            logger.debug(f"{fetcher_cls.__name__} は無効です。")

    if not active_fetchers:
        logger.warning("有効な Fetcher が設定されていません。")

    return active_fetchers

def contains_noise_keyword(text: Optional[str], noise_keywords: List[str]) -> bool:
    """テキストがノイズキーワードを含むかチェック"""
    if not text:
        return False
    # キーワードも比較対象テキストも小文字に変換して比較
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in noise_keywords)

def fetch_and_save_article_links():
    """
    有効なFetcherから記事リンクを取得し、コンソールに表示する（実際のアプリではDBに保存）
    """
    # 設定の読み込み
    config = load_config()
    noise_keywords = config.get('noise_keywords', [])
    logger.info(f"ノイズキーワード: {noise_keywords}")
    
    # 有効なフェッチャーを取得
    active_fetchers = get_active_fetchers()
    
    for fetcher, limit in active_fetchers:
        logger.info(f"{fetcher.__class__.__name__} から記事リンクの取得を開始します (上限: {limit}件)...")
        try:
            article_links = fetcher.fetch_article_links(limit)
            logger.info(f"{fetcher.__class__.__name__}: {len(article_links)} 件のリンク候補を取得しました。")
            
            # ノイズキーワードをフィルタリング
            filtered_links = []
            for url, title in article_links:
                if contains_noise_keyword(url, noise_keywords) or contains_noise_keyword(title, noise_keywords):
                    logger.info(f"ノイズワードが含まれるためスキップ: {url} (タイトル: {title})")
                    continue
                filtered_links.append((url, title))
            
            # 結果表示（実際のアプリではDBに保存）
            logger.info(f"{fetcher.__class__.__name__} フィルタリング後: {len(filtered_links)} 件")
            for url, title in filtered_links:
                logger.info(f"- タイトル: {title} | URL: {url}")
                
            # テスト的に最初の記事の詳細データを取得して表示
            if filtered_links:
                test_url, test_title = filtered_links[0]
                logger.info(f"最初の記事 ({test_title}) の詳細データを取得中...")
                try:
                    article_data = fetcher.fetch_article_data(test_url)
                    if article_data:
                        logger.info(f"記事データ取得成功: {article_data['title']} (画像: {len(article_data['images'])}枚)")
                        # 実際のアプリではDBに保存
                    else:
                        logger.error(f"記事データの取得に失敗しました: {test_url}")
                except Exception as e:
                    logger.error(f"詳細データ取得中にエラー: {e}")
        
        except Exception as e:
            # Fetcherごとのエラーを捕捉し、他のFetcherの処理は継続する
            logger.error(f"{fetcher.__class__.__name__} の処理中にエラーが発生しました: {e}", exc_info=True)

def main():
    """メイン処理"""
    logger.info("=== プログラム開始 ===")

    # .env ファイルの読み込み
    load_dotenv()
    logger.info(".env ファイルを読み込みました。")

    # 記事リンクを取得して保存（デモ版ではコンソール表示）
    fetch_and_save_article_links()

    logger.info("=== プログラム終了 ===")

if __name__ == "__main__":
    main()