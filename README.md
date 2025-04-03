# smahoblog14

中国のテックニュースサイトから記事を取得し、翻訳・加工するためのオートメーションツール

## 概要

smahoblog14は、ZOLなどの中国テックニュースサイトから記事を自動で取得し、翻訳して日本語のブログ記事として公開するためのツールです。

## 主な機能

- 様々なニュースサイトから記事リンクの取得
- 記事本文のスクレイピングと整形
- GPT APIを利用した記事の翻訳
- WordPress APIを介したブログへの投稿

## ZOLフェッチャーの特徴

- モバイル版サイトから記事を取得（PC版へのリダイレクト防止機能付き）
- モバイルブラウザのユーザーエージェントをランダムに選択して偽装
- 画像取得ロジックの強化（アイコンやバナーなどの除外、高品質な記事関連画像の優先取得）
- アスペクト比チェックによる画像フィルタリング

## 必要条件

- Python 3.8以上
- 必要なライブラリ（requirements.txtを参照）

## セットアップ

```bash
# 仮想環境の作成（任意）
python -m venv venv
source venv/bin/activate  # Linuxの場合
venv\Scripts\activate  # Windowsの場合

# 依存関係のインストール
pip install -r requirements.txt
```

## 設定

.envファイルを作成して以下の環境変数を設定してください：

```
# データベース設定
DB_PATH=./database/smahoblog.db

# ログレベル設定
LOG_LEVEL=INFO

# フェッチャー設定
ENABLE_ZOL=True
FETCH_LIMIT_ZOL=10

# 翻訳設定
OPENAI_API_KEY=your_openai_api_key_here

# WordPress設定
WP_URL=https://your-wordpress-site.com
WP_USERNAME=your_username
WP_PASSWORD=your_application_password
```

## 使用方法

```bash
python -m smahoblog_automator.main
```

## ライセンス

MIT