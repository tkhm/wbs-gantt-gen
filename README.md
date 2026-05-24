# wbsgen

PMBOK 準拠の WBS / ガントチャート ジェネレータ。
TSV を Single Source of Truth として、CPM (Critical Path Method) でスケジュールを計算し、
**1 つの Markdown** に WBS ピラミッド図・ガント・PERT 図・進捗サマリを内包して出力する。

- **MS Project 等の高価ツール無し**で WBS / ガントを運用したい
- **構造の俯瞰** と **時系列** と **依存ネットワーク** を 1 ファイルに同居させたい
- 編集は **Spreadsheet** か **エディタ** どちらでも

---

## クイックスタート

```bash
# 1. 依存インストール (venv 推奨)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. 既存サンプルを試す
wbsgen build examples/home-cooking-curry

# 3. 出力を VS Code で開く (Markdown プレビュー)
code examples/home-cooking-curry/build/wbs.md
```

**プレビューについて**: VS Code 1.86+ は Mermaid を Markdown プレビューに標準搭載。
拡張機能 (`Markdown Preview Mermaid Support`) を別途入れる必要はない (むしろ重複して動かないことがある)。
GitHub も Mermaid をネイティブ描画する。

---

## 複数プロジェクトの運用 (推奨レイアウト)

wbs-gantt-gen は **ツール本体と各プロジェクトを別フォルダで管理する** 設計。
1つのツールで複数プロジェクトを扱える (`wbsgen build <project_dir>` でディレクトリを指定)。

```
~/projects/
├── wbs-gantt-gen/        ← ツール本体 (このリポジトリ。venv 同居)
│   ├── src/wbsgen/
│   ├── examples/
│   └── .venv/
├── my-alpha/             ← 新プロジェクト #1
│   ├── project.toml
│   ├── works.tsv
│   ├── activities.tsv
│   ├── wbs-dictionary.md ← 任意。各 WP の補足説明
│   └── build/wbs.md      ← 出力 (project_dir/build/ がデフォルト)
└── my-beta/              ← 新プロジェクト #2
    └── ...
```

利点:
- 個別プロジェクトの計画 (非公開含む) と ツールリポジトリを混ぜずに済む
- 各プロジェクトを独立 git 管理できる (ツールの履歴と分離)
- ツールを upgrade してもプロジェクト側のファイルは無関係

### 使い方の流れ

```bash
# 1. ツールの venv を activate (1日1回)
cd ~/projects/wbs-gantt-gen
source .venv/bin/activate
# これで `wbsgen` コマンドが PATH に通り、どのディレクトリにいても実行できる

# 2. 任意の場所に雛形を作る (絶対パスでも相対パスでも)
wbsgen init ~/projects/my-alpha

# 3. プロジェクトディレクトリに移って編集
cd ~/projects/my-alpha
# project.toml / works.tsv / activities.tsv を編集

# 4. ビルド (cwd を渡すなら `.`)
wbsgen build .
# 編集中はライブ更新が便利
wbsgen build . --watch

# 5. プレビュー
code build/wbs.md
```

シェル起動時に activate するなら `~/.zshrc` 等に alias を入れておくとラク:

```bash
alias wbsenv='source ~/projects/wbs-gantt-gen/.venv/bin/activate'
```

---

## 新規プロジェクトの始め方

### Step 1 — 雛形作成

```bash
wbsgen init my-project
```

これで以下が生成される:

```
my-project/
├── project.toml         # プロジェクトメタ (名前・開始日・カレンダー)
├── works.tsv            # WBS の階層 (L1 / L2 / ...)
├── activities.tsv       # WP に紐づく作業と依存関係
└── wbs-dictionary.md    # 任意。各 WP の補足説明 (受入基準・責任者など)
```

### Step 2 — `project.toml` を整える

```toml
[project]
name = "新サービス α リリース"
description = "プロジェクトの概要を1〜2行で"
start = 2026-06-01            # 任意。未指定なら Day N 表示
units = "business_days"       # business_days | calendar_days
near_critical_threshold = 2

[project.calendar]
working_days = ["mon", "tue", "wed", "thu", "fri"]
holidays_preset = "jp"        # 日本の祝日を自動取り込み
# holidays = ["2026-08-12"]   # プロジェクト固有の追加休日
```

### Step 3 — `works.tsv` で WBS を組む

| 列 | 役割 | 必須/挙動 |
|---|---|---|
| `id` | 不変ID (`w-` prefix 推奨) | 空欄なら `name` から自動生成 (slug化 + 衝突回避) |
| `parent_id` | 親 work id | 空欄 = トップレベル (L1) |
| `order` | 同 parent 内の表示順 | 空欄 OK — `build --rewrite-order` で行順×10 に正規化 |
| `name` | 表示名 | 必須 |

**ID の文字種**: ASCII 英数字 + `_` / `-` / `.` のみ (例: `w-req-org`、`1.1-a1`、`1.1.1`)。
日本語などの非 ASCII 文字は使えない。自動生成時は `name` から slug 化されるが、
日本語のみの name は `w-x-abc123` のような hash fallback になるため、慣れたら自分で
読みやすい id を付けるとよい。
**注**: id は不変な内部識別子。`1.1.1` のように WBS コード風に付けても OK だが、
WBS 構造が変わると表示上の WBS コードはずれる (id 自体は変わらない設計)。

**WBS 構造の原則** (PMBOK):
- 階層は **成果物 / 作業の塊** で分解する (時系列順ではない)
- **最下層 = ワークパッケージ (WP)** = スコープ・期間を見積もれる単位
- 階層の深さは任意。**小規模なら L2 まで** (= L2 が WP)、**中〜大規模なら L3 まで** (= L3 が WP) が目安
- WP は「成果物名」で名付けると意図が明確 (例: `要件定義書`、`アーキ設計書`、`リリース計画書`)

```tsv
id	parent_id	order	name	note
w-req			要件定義
w-req-interview	w-req		ヒアリング
w-req-interview-record	w-req-interview		ヒアリング報告       ← L3 = WP
w-req-org	w-req		要件整理
w-req-org-doc	w-req-org		要件定義書          ← L3 = WP
w-req-org-confirm	w-req-org		要件承認          ← L3 = WP
```

### Step 4 — `activities.tsv` で作業を定義

| 列 | 役割 | 必須/挙動 |
|---|---|---|
| `work_id` | 所属 WP (リーフ work) の id | **必須** |
| `id` | 不変ID (`a-` prefix 推奨) | 空欄なら `name` から自動生成 |
| `order` | 同 WP 内の表示順 | 空欄 OK |
| `name` | 表示名 | 必須 |
| `duration` | 営業日 (整数) | 必須 / **`0` = マイルストーン** |
| `predecessors` | 先行 activity (DSL) | 任意 |
| `status` | `todo` / `doing` / `done` / `blocked` | 任意、空欄=`todo` |

**列順**: `work_id` を先頭にしている。**計画時はまず WP を思い浮かべ、そこに作業をぶら下げる** ため。

```tsv
work_id	id	order	name	duration	predecessors	status
w-req-interview-record	a-stakeholder-interview		ステークホルダーヒアリング	5		todo
w-req-org-doc	a-req-summary		要件まとめ	4	a-stakeholder-interview	todo
w-req-org-confirm	a-m-req-complete		要件確定	0	a-req-summary	todo
```

### Step 4.5 — `wbs-dictionary.md` で WP 補足を書く (任意)

各 WP の **受入基準・責任者・前提・リスクなど、TSV に収まらない情報** をここに書く。
このファイルがあれば build 時に `wbs.md` の「WBS 辞書」セクションとして取り込まれる。

```markdown
# WBS 辞書

## 1.1.1 ヒアリング報告 (w-req-interview-record)

- **受入基準**: 全ステークホルダーから議事録を取得済み
- **責任者**: PM
- **前提**: ステークホルダーリスト確定済み

## 1.2.1 要件定義書 (w-req-org-doc)

- **受入基準**: 機能要件・非機能要件を整理し、レビュー済み
```

形式は Markdown フリーフォーム。`wbsgen` は中身を構造化しないので、見出しレベルや項目立ては好きに決めてよい。ファイル自体を削除しても build は動く。

### Step 5 — ビルドしてプレビュー

```bash
wbsgen build my-project              # → my-project/build/wbs.md
code my-project/build/wbs.md         # VS Code でプレビュー
```

編集しながら自動再生成するなら:

```bash
wbsgen build my-project --watch
```

ファイル保存ごとに `wbs.md` が再生成され、VS Code Markdown プレビューも自動更新される。

---

## predecessors DSL

通常は FS (Finish-to-Start) で十分。カンマ区切りで先行 activity の id を並べる:

```
a-foo, a-bar
```

複雑な依存タイプを使いたい場合 (推奨度低、PMBOK 上は ADM/PDM の両方ある):

| 表記 | 意味 |
|---|---|
| `<id>` | FS, lag=0 |
| `<id>+N` / `<id>-N` | FS, lag=±N (営業日) |
| `<id>/SS` / `/FF` / `/SF` | 依存タイプ (start-to-start, finish-to-finish, start-to-finish) |
| `<id>/SS+2` / `<id>+2/SS` | 組合せ可 |

**並行作業は「依存なし」で表現するのが簡潔**。例えば「米炊きとラッシー準備を並行に始める」なら、両方 `predecessors` を空にすれば独立起点として並行スタートする (`examples/home-cooking-curry` 参照)。

---

## 出力されるもの (`wbs.md` の構成)

1. **概要** — 期間、件数、進捗統計、クリティカルパス長
2. **WBS ピラミッド図** — Mermaid `flowchart TB`、組織図風
   - L0 (プロジェクト名) → L1 → L2 (= WP の場合は中青で強調)
   - L3 以下は **L2 box 直下の透明箱に WBS 番号付きで箇条書き** (Milosevic 流)
3. **WBS 辞書** (任意) — `wbs-dictionary.md` があれば取り込み
4. **ガントチャート** — Mermaid `gantt` 単一ブロック
   - section は **WP 単位**、ヘッダに WBS code を付与
   - 色は `done` だけグレー化 (完了の視覚化)、その他は通常色
5. **PERT 図 (AOA)** — Mermaid `flowchart LR`
   - **ノード = イベント、矢印 = activity** (アローダイアグラム形式)
   - 実線矢印にWP code + 名前 + duration
   - 破線矢印 = dummy (依存だけを表現)
   - 太線 (`==>`) = クリティカルパス
6. **WP 別 進捗** — 各 WP のステータス集計 + 進捗バー + 全 WP 合計
7. **アクティビティ詳細表** — WP / ID / 名称 / 状態 / 所要 / 先行 / ES / EF / TF / FF / 開始 / 終了 / CP
8. **クリティカルパス要約** — パス上の activity 列
9. **ニア・クリティカル一覧** — `0 < TF <= 閾値` の活動

---

## CLI

```
wbsgen build  <project_dir> [-o <out_dir>] [--watch] [--rewrite-order]
wbsgen check  <project_dir>                  # バリデーションのみ (CI 向け)
wbsgen init   <new_dir>                      # 雛形展開
```

| オプション | 効果 |
|---|---|
| `-o` / `--output` | 出力先 (デフォルト: `<project_dir>/build/`) |
| `--watch` | project.toml / works.tsv / activities.tsv の変更で自動再生成 |
| `--rewrite-order` | 空 id 採番と order 列のリナンバを TSV に書き戻す |

---

## PMBOK 用語対応

| 英語 / 用語 | 日本語 | 説明 |
|---|---|---|
| Work | WBS要素 | 成果物軸の階層ノード |
| **Work Package (WP)** | **ワークパッケージ** | WBS の最下層。スコープ管理の最小単位 |
| Activity | アクティビティ | duration と依存を持つ実行可能な作業 |
| Milestone | マイルストーン | duration=0 |
| Predecessor / Successor | 先行 / 後続 | 依存関係 |
| FS / SS / FF / SF | 終→開 / 開→開 / 終→終 / 開→終 | 依存タイプ |
| Lead / Lag | リード / ラグ | 負ラグ=リード, 正ラグ=ラグ |
| ES / EF / LS / LF | 最早開始 / 最早完了 / 最遅開始 / 最遅完了 | CPM 計算結果 |
| Total Float (TF) | トータルフロート | プロジェクト終了を遅らせない範囲で遅延可能な日数 |
| Free Float (FF) | フリーフロート | 後続の最早開始を遅らせない範囲で遅延可能な日数 |
| Critical Path | クリティカルパス | TF=0 の最長経路 |
| ADM (AOA) | アローダイアグラム | 矢印=活動の表記。本ツールの PERT 図はこの形式 |
| PDM (AON) | ノードダイアグラム | ノード=活動の表記。PMBOK 6/7 の主流 |

---

## 編集 UI の選択肢

- **Spreadsheet** (Google Sheets / LibreOffice / Excel) — TSVをそのまま開ける。一覧・並び替え・フィルタが得意
- **VS Code + Rainbow CSV 拡張** — テキスト編集者向け。列が色分けされて読みやすい
- **直接テキスト編集** — タブ区切りに慣れていれば素のエディタでも

Spreadsheet で行ドラッグして並べ替えた後は `wbsgen build --rewrite-order` で order 列を 10 刻みにリナンバして書き戻せる。

---

## 設計の核

- **TSV 2 ファイル分離**: `works.tsv` (WBS構造) と `activities.tsv` (作業) を別テーブルに。中間ノードと作業の混在ノイズを避け、Spreadsheet編集・フィルタもしやすい
- **WBS と Activity は別概念** (PMBOK): WBS は成果物分解、Activity はスケジュール対象。WBS pyramid 図に activity は描かない (PERT/ガントで管理)
- **WBSコードは表示時算出**: 構造変更で番号が変わっても ID 参照は無傷
- **スケジューラは整数の作業日インデックスで動く**: Calendar 射影層が `index ↔ 日付` 変換。`project.start` 省略時は Day N 表示
- **Mermaid には明示的な日付**: `after`/`excludes weekends` は SS/FF/SF やラグで破綻するため使わない
- **3 種の図 (ピラミッド / ガント / PERT) を 1 ファイルに同居**: それぞれ違う視点 (構造 / 時系列 / 依存) を提供

---

## 内蔵 examples

| ディレクトリ | 規模 | 特徴 |
|---|---|---|
| `examples/home-cooking-curry` | 18 activity | カレー＋ラッシー調理。**並行作業の合流**を示す身近な題材 |
| `examples/dogfood-wbs-gantt-gen` | 18 activity | 本ツール自身の開発計画 (ドッグフード)。**小規模** = L1/L2、L2 が WP |
| `examples/generic-software-project` | 17 activity | 一般的なソフトウェア開発。**中規模** = L1/L2/L3、L3 が WP |

```bash
wbsgen build examples/home-cooking-curry
code examples/home-cooking-curry/build/wbs.md
```

---

## ロードマップ

- **MVP v2 (本リポジトリ)**: TSV SSoT、WBSピラミッド/単一ガント/AOA PERT、CPM、`--watch`
- **Phase 2**: ベースライン管理 + 差分表示 (`wbsgen diff <baseline>`)、ガント単独 SVG 出力
- **Phase 3**: 進捗トラッキング詳細 (実績日付)、TUI 編集、Google Sheets 連携

---

## テスト

```bash
source .venv/bin/activate
pytest
```

依存: Python 3.11+, `jpholiday`, `watchfiles`
