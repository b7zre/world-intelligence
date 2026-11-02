# World Intelligence v0.2

無料の公開RSSとWorld Bank APIからニュース見出し・年次経済指標を収集し、静的Webダッシュボードに表示します。

## ローカルで試す

Python 3.10以降でリポジトリのルートから実行:

```bash
python scripts/collect.py
python -m http.server 8000
```

ブラウザで http://localhost:8000 を開きます。`index.html`を直接開いた場合はブラウザのセキュリティ制約で自動読込が失敗することがあります。

## GitHubで自動更新・公開

1. このフォルダの**中身**を新規GitHub公開リポジトリにアップロードします。
2. リポジトリの Settings → Actions → General → Workflow permissions を Read and write permissions にします（必要に応じて）。
3. Actions → Collect public news and indicators → Run workflow で初回実行します。
4. Settings → Pages → Deploy from a branch → main / (root) を指定します。
5. Pagesが発行するURLを開きます。更新結果は `data/latest.json` に保存されます。

GitHub Pagesの公開サイトは**URLを知らない人も閲覧可能**です。アクセス制限はありません。公開情報以外は登録しないでください。

## 制約と注意

- GitHub ActionsのスケジュールはUTC 22:00/10:00（JST 07:00/19:00）ですが、GitHub側の混雑で実行が遅れる場合があります。
- RSS提供元の仕様・アクセス制限で取得できないことがあります。`meta.errors` に失敗を記録します。
- Guardianの国別RSSは政治・経済の記事が混在し、網羅的ではありません。RSS本文は概要のみです。
- World Bankの年次GDP成長率、CPI、失業率は速報値ではなく、改訂されることがあります。
- 為替実勢レート、支持率、AI長期分析、詳細レポートの自動生成は未実装です。
- ローカル手動登録記事は端末内保存のため、端末間同期されません。
- GitHub Pagesの公開URLは一般公開です。特定の人だけに限定するアクセス制御はありません。
- 外部CDNのChart.js / SheetJSを利用するため、グラフ・Excel出力にはインターネット接続が必要です。
- 情報源の利用条件を確認し、過剰なアクセスや全文の再配布を避けてください。
