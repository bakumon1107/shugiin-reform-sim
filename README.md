# shugiin-reform-sim — 衆院選 選挙制度改革シミュレータ / データ基盤

各党の選挙制度改革案（定数削減・比例代表の扱い・中選挙区制・連用制／併用制など）を
実際の投票結果に当てはめて比較するためのシミュレータ。

このリポジトリは現在その **データ基盤の部分**。総務省が公表する「衆議院議員総選挙・
最高裁判所裁判官国民審査結果調」PDFを、検証可能な形で構造化データに落とす。
シミュレータの結果は入力データの正確さに完全に依存するので、
「取り込めた」ではなく「取り込んだ値が正しいと検証できた」ところまでを成果物とする。

## 取り込み済みの選挙

| election_id | 回 | 執行日 | 出典 | 状態 |
|---|---:|---|---|---|
| `r08-02-08` | 第51回 | 2026-02-08 | [001061492.pdf](https://www.soumu.go.jp/main_content/001061492.pdf) | 全33チェック PASS ＋ 目視確認済み |
| `r06-10-27` | 第50回 | 2024-10-27 | [000979139.pdf](https://www.soumu.go.jp/main_content/000979139.pdf) | 全33チェック PASS |

出典の詳細（sha256・ページ構成・回ごとのレイアウト差）は [raw/SOURCE.md](raw/SOURCE.md)。

## 使い方

```bash
pip install -r requirements.txt

export PYTHONPATH=src
python3 -m extract.run_all   r08-02-08   # PDF → data/csv/<id>/*.csv
python3 -m verify.run_verify r08-02-08   # 検証 → reports/verification_report_<id>.md
python3 -m build_json        r08-02-08   # CSV → data/json/<id>.json

./run_regression.sh                      # 全選挙回 × 抽出/検証/JSON + pytest
```

新しい選挙回を足すときは Claude Code のスキル
[`soumu-election-ingest`](.claude/skills/soumu-election-ingest/SKILL.md) を使う
（構造プローブ → 設定追加 → 抽出 → 検証 → 目視確認 → リグレッション、の手順と落とし穴が書いてある）。

## 出力データ

### CSV（`data/csv/<election_id>/`）— これが正

PDFの13の表を20本のCSVに分解している。全CSVに `election_id` 列と `source_page` 列がある。

| CSV | 出典表 | 内容 |
|---|---|---|
| `smd_districts` | 3(13) | 289選挙区 × 供託物没収点 |
| `smd_candidates` | 3(13) | **候補者別得票数**（当落・氏名・年齢・党派・新前元・職業・得票数・重複・惜敗率） |
| `party_votes_smd_total` / `party_votes_pr_total` | 3(4)(5) | 党派別得票数（今回・前回・差引） |
| `party_votes_by_pref_smd` | 3(6) | 都道府県 × 党派 × 男女 |
| `party_votes_by_block_pref` | 3(7) | 比例ブロック × 都道府県 × 党派 |
| `party_votes_by_block` | 3(10) | 比例ブロック × 党派（順位・得票率つき） |
| `ballots_smd_by_pref` / `ballots_pr_by_block_pref` | 3(8)(9) | 投票総数・有効・無効・無効率 |
| `electorate` / `turnout` | 2(1)(2) | 有権者数・投票者数・棄権者数 / 投票率（小選挙区・比例、全体・在外） |
| `pr_party_blocks` | 3(11) | ブロック × 党派の得票数・当選人数・男女内訳 |
| `pr_list_entries` | 3(11) | **比例名簿**（名簿順位・氏名・当選順・小選挙区当落・惜敗率） |
| `dhondt_quotients` | 3(12) | ドント除数表（商と獲得順位） |
| `candidacy_by_party` / `_by_pref_party` / `_by_pref_age` | 1(1)(2)(3) | 立候補状況 |
| `winners_by_party` / `_by_pref_party` / `_by_pref_age` | 3(1)(2)(3) | 当選人数 |

第2「最高裁判所裁判官国民審査」は対象外。

### JSON（`data/json/<election_id>.json`）— CSVからの派生物

シミュレータが読む用のネスト構造。

```
meta                          選挙回・出典・定数
smd.districts[]               選挙区（得票降順の候補者配列つき）
pr.blocks[]                   ブロック（定数・党派別得票・名簿・都道府県別得票）
electorate_by_prefecture      有権者数・投票者数・小選挙区定数（定数再配分の検討用）
ballots_by_prefecture         投票総数・有効・無効
```

生成時にJSONを再集計してCSVと突き合わせている（`build_json.roundtrip_check`）。

## 検証

`reports/verification_report_<election_id>.md` に全チェックの結果が出る。FAILが1件でもあれば exit 1。

- **A. 表内の恒等式** — 男+女=計、有権者=投票者+棄権者、投票総数=有効+無効、投票率・無効率の再計算、都道府県の総和=合計行
- **B. 選挙区単位の厳密検証** — **Σ候補者得票 = 供託物没収点 × 10**（全289区）、当選者は1名かつ最多得票、惜敗率の再計算、「×」印の条件、区番号の連番と定数の一致
- **C. 独立した表どうしの突合** — Σ候補者得票 = 党派別得票数（**小数まで完全一致**）、都道府県別・ブロック別の各集計表との相互一致、重複立候補の表(13)⇄表(11)両方向突合、議席数 289+176=465
- **D. ドント式の独立再計算** — 除数表の商、議席配分、獲得順（名簿枯渇ルールを含めて再現）
- **E. 構造アサーション** — 47都道府県・11ブロック、党派名の集合、必須項目、名簿順位の連番

目視確認の記録は [reports/visual_spotcheck_r08-02-08.md](reports/visual_spotcheck_r08-02-08.md)。
確認した値は `tests/test_extract.py` にゴールデンとして固定してある。

### 検証で分かった実データの性質

- **按分票は切り捨てられる**（公選法の同姓同名按分、小数第3位まで）。そのため
  `Σ候補者得票` は `有効投票総数` を最大1票弱下回る。第51回では289区中281区が完全一致し、
  残り8区は差 0.001〜0.020 票 — この8区は小数得票を含む8区とちょうど一致した。
- **比例代表の議席配分は素のドント式では再現できない。** 小選挙区で当選済みの者と、
  惜敗率欄が「×」の者は当選人になれず、名簿が尽きた党派への配分は打ち切られる（公選法95条の2第4項）。
  第51回の南関東・自民は名簿35人中「当選可能」4人で、獲得議席も4だった。
- **同一人物が表によって別表記になる。** 異体字セレクタ（`大塚拓`／`大塚󠄆拓`）、小書き仮名
  （`三ッ林`／`三ツ林`）、届出名と戸籍名（`しもの幸助`／`下野幸助`）、高座名（`やなぎや東三楼`／`柳家東三楼`）など。

## 設計

```
raw/                        PDF原本（sha256を elections.py で照合）
src/extract/
  common.py                 Decimalパーサ / 罫線→グリッド / 氏名突合キー / 定数
  elections.py              選挙回ごとの設定（ページ範囲・党派名・定数）
  probe.py                  新しいPDFの構造を実測する調査ツール
  t_*.py                    表ごとの抽出
  csvio.py                  dataclass ⇄ CSV
  run_all.py
src/verify/
  checks.py                 検証本体（A〜E）
  run_verify.py             レポート生成
  spotcheck.py              目視確認用の抜き出し
src/build_json.py
```

守っていること:

- **数値は `Decimal`。float は使わない。** 按分票の小数で合計一致検証が壊れる。
- **列境界は `page.edges` から取る。** 罫線を `lines` で持つPDFと `rects` で持つPDFがあり、
  `edges` だけが両方を拾える。
- **セルへの割り付けは語ではなく文字単位。** `extract_words` は列をまたいで語を結合する。
- **未知の党派名が出たら例外で止める。** 黙って落とすより止まるほうがよい。
- **ラベル決め打ちで行・列を探さない。** 見出しの語は回ごとに揺れる（党派／届出政党等、都道府県／区分）。
- **共通コードを触ったら全選挙回でリグレッションを回す**（`./run_regression.sh`）。

## これから

シミュレータ本体（制度モデルとUI）は未着手。データ基盤側は
`electorate_by_prefecture`（定数再配分）、`pr_list_entries`（復活当選の再計算）、
`smd_candidates`（選挙区の再編）まで揃っているので、制度モデルはこの上に載せられる。
