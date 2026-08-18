"""全検証を実行し ``reports/verification_report_<election_id>.md`` を書き出す。

FAIL が1件でもあれば終了コード1。

使い方::

    python -m verify.run_verify
    python -m verify.run_verify r06-10-27
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extract import elections
from extract.elections import ElectionConfig
from verify.checks import FAIL, PASS, Result, load, run_all

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / "data" / "csv"
REPORT_DIR = ROOT / "reports"

CATEGORY_TITLES = {
    "A": "A. 表内の恒等式",
    "B": "B. 選挙区単位の厳密検証（表13 候補者別得票数）",
    "C": "C. 独立した表どうしの突合",
    "D": "D. ドント式の独立再計算",
    "E": "E. 構造アサーション",
}


def render(results: list[Result], cfg: ElectionConfig, csv_dir: Path) -> str:
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S %Z")
    n_fail = sum(1 for r in results if r.status == FAIL)
    n_warn = sum(1 for r in results if r.status == "WARN")
    if n_fail:
        verdict = f"**FAIL {n_fail} 件**"
    elif n_warn:
        verdict = f"**FAILなし**（うち {n_warn} 件は出典PDF側の既知の不整合により WARN）"
    else:
        verdict = "**全チェック PASS**"

    lines = [
        f"# 検証レポート — 第{cfg.ordinal}回衆議院議員総選挙（{cfg.election_date}）",
        "",
        f"- 対象データ: `{csv_dir.relative_to(ROOT)}`",
        f"- 出典PDF: `{cfg.pdf_filename}` (sha256 `{cfg.sha256[:16]}…`)",
        f"- 生成日時: {now}",
        f"- 結果: {verdict}（{len(results)} チェック）",
        "",
    ]
    spotcheck = REPORT_DIR / f"visual_spotcheck_{cfg.election_id}.md"
    if spotcheck.exists():
        lines += [
            f"目視でPDFと突き合わせた記録は [{spotcheck.name}]({spotcheck.name}) を参照。",
            "",
        ]
    lines += [
        "## サマリ",
        "",
        "| ID | 分類 | チェック | 対象件数 | 不一致 | 結果 |",
        "|---|---|---|---:|---:|---|",
    ]
    for r in results:
        mark = "✅ PASS" if r.status == PASS else ("⚠️ WARN" if r.status == "WARN" else "❌ FAIL")
        lines.append(
            f"| {r.check_id} | {r.category} | {r.title} | {r.subject_count} | {r.fail_count} | {mark} |"
        )

    for cat, title in CATEGORY_TITLES.items():
        rows = [r for r in results if r.category == cat]
        if not rows:
            continue
        lines += ["", f"## {title}", ""]
        for r in rows:
            mark = "✅" if r.status == PASS else ("⚠️" if r.status == "WARN" else "❌")
            lines.append(f"### {mark} {r.check_id} {r.title}")
            lines.append("")
            lines.append(f"- 対象 {r.subject_count} 件 / 不一致 {r.fail_count} 件")
            if r.detail:
                lines.append(f"- {r.detail}")
            if r.samples:
                lines.append("- 不一致の例:")
                lines += [f"    - `{s}`" for s in r.samples]
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", default=elections.DEFAULT_ELECTION)
    args = parser.parse_args(argv)
    cfg = elections.get(args.election_id)

    csv_dir = CSV_DIR / cfg.election_id
    data = load(csv_dir)
    results = run_all(data, cfg)

    width = max(len(r.title) for r in results)
    for r in results:
        mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[r.status]
        print(f"[{mark}] {r.check_id:4s} {r.title:{width}s}  対象{r.subject_count:6d} 不一致{r.fail_count:5d}")
        for s in r.samples:
            print(f"         └ {s}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"verification_report_{cfg.election_id}.md"
    report.write_text(render(results, cfg, csv_dir), encoding="utf-8")

    n_fail = sum(1 for r in results if r.status == FAIL)
    print()
    print(f"→ {report.relative_to(ROOT)}")
    print(f"{len(results)} チェック中 FAIL {n_fail} 件")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
