# WBS 辞書 (dogfood example)

本ツール wbsgen 自身の開発 MVP を WP で分解したもの。
各 WP の意図と完了基準を以下に整理する。

## 1.1 基盤整備 (w-setup-base)

- pyproject.toml、ディレクトリ構成、Python 仮想環境
- 完了基準: `pip install -e .` が通る

## 2.1 データモデル (w-engine-data)

- Work / Activity / Dependency などの dataclass
- ID slug 生成、TSV loader、依存 DSL パーサ、validator
- 完了基準: TSV を読み込んで Project オブジェクトを構築できる

## 2.2 スケジューリング (w-engine-sched)

- 営業日カレンダー (jpholiday 連携)
- CPM 前進パス・後退パス・float 計算
- 完了基準: ES/EF/LS/LF/TF/FF/Critical が全活動について算出される

## 3.1 Markdown 統合 (w-render-md)

- render/markdown.py: 全セクションを1ファイルに統合
- 完了基準: build/wbs.md が生成され、VS Code Markdown プレビューで読める

## 3.2 図表 (w-render-vis)

- WBS pyramid (flowchart TB) / Gantt (gantt) / PERT (AOA flowchart)
- 完了基準: 3 図ともプレビューで描画される

## 4.1 コマンド (w-cli-cmd)

- `wbsgen build / check / init` + `--watch` + `--rewrite-order`
- 完了基準: 雛形展開からビルドまで CLI 1行で完結

## 5.1 サンプル整備 (w-finish-ex)

- examples 3つ (generic / dogfood / home-cooking) を整備
- 完了基準: 各 example が `wbsgen check` を通り、build できる

## 5.2 テスト (w-finish-test)

- pytest による回帰テスト
- 完了基準: 70+ テストが green

## 5.3 ドキュメント (w-finish-doc)

- README / CLAUDE.md
- 完了基準: 新規ユーザーが README を読んで自分のプロジェクトを立ち上げられる
