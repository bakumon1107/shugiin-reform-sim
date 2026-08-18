# ライセンス

コードとデータで分けています。

| 対象 | ライセンス |
|---|---|
| ソースコード（`src/`, `tests/`, `run_regression.sh`） | [MIT License](LICENSE) |
| 抽出データ（`data/csv/`, `data/json/`） | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja) |
| ドキュメント・検証レポート（`README.md`, `LICENSES.md`, `reports/`, `raw/SOURCE.md`） | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja) |
| 出典PDF原本 | 総務省の著作物。[政府標準利用規約（第2.0版）](https://www.soumu.go.jp/menu_kyotsuu/policy/tyosaku.html)（CC BY 4.0 互換）。**本リポジトリでは再配布せず、総務省のURLから取得する** |

## 出典表示

`data/` を再利用するときは、次のいずれかの形で出典を示してください。

> 出典: 総務省「衆議院議員総選挙・最高裁判所裁判官国民審査結果調」をもとに
> shugiin-reform-sim（https://github.com/bakumon1107/shugiin-reform-sim）が作成

英語の場合:

> Source: Compiled by shugiin-reform-sim from the Ministry of Internal Affairs
> and Communications (Japan), "Results of the General Election of Members of
> the House of Representatives and the National Review of Supreme Court Judges".

回ごとの出典URL・sha256・公表日は [raw/SOURCE.md](raw/SOURCE.md) にあります。

## 出典PDFの扱いについて

総務省のコンテンツは政府標準利用規約（第2.0版）に基づき、出典明示を条件に
商用・非商用を問わず自由に利用・改変・再配布ができます。同規約は CC BY 4.0 と
互換であることが明記されているため、そこから作った抽出データを CC BY 4.0 で提供しています。

PDF原本は再配布せず、リポジトリには含めていません（`raw/*.pdf` は .gitignore）。
出典URLと sha256 を `src/extract/elections.py` と [raw/SOURCE.md](raw/SOURCE.md) に記録してあり、
`python -m extract.fetch` で総務省のサイトから取得・照合できます。
一次情報は常に総務省のものを参照する、という切り分けです。

なお、選挙結果の数値そのものは事実であり著作物性を持たないと考えられますが、
再利用者が出典をたどれるようにするため CC BY 4.0 を明示しています。

## 免責

抽出データは [reports/](reports/) の検証を通していますが、正確性を保証するものでは
ありません。公式な数値が必要な場合は必ず [raw/SOURCE.md](raw/SOURCE.md) に記載の
原本PDFを参照してください。

とくに第48回（2017年）の沖縄県については、出典PDF内で表(6)・表(13)と表(8)が
105票食い違っています。詳細は [reports/verification_report_h29-10-22.md](reports/verification_report_h29-10-22.md) を参照してください。
