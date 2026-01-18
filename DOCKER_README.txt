====================================
機械台帳 - Docker セットアップ手順
====================================

【起動方法】

1. Docker と Docker Compose がインストールされていることを確認

2. このフォルダで以下のコマンドを実行:
   docker-compose up --build

3. ブラウザで開く:
   http://localhost:8000

【停止方法】
   docker-compose down

【Google Vision API を使う場合】
1. Google Cloud Console でサービスアカウントキー(JSON)を取得
2. data/vision_credentials.json として保存
3. コンテナを再起動

【ローカル画像を処理する場合】
data/images/ フォルダに画像ファイルを配置

【データの永続化】
data/ フォルダがホストにマウントされているため、
コンテナを削除してもデータは保持されます。

====================================
