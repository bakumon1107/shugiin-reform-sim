"""新しい選挙回のPDFの構造を実測して、``elections.py`` に書く設定の材料を出す。

* 各ページの表タイトルから「表 → 物理ページ範囲」の対応を作る
* 表ごとの罫線本数（縦・横）を報告する
* 全テーブルに現れる党派名を収集する（``parties`` にそのまま貼れる形で出力）

使い方::

    python -m extract.probe raw/000979139.pdf
    python -m extract.probe raw/000979139.pdf --parties r06-10-27
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pdfplumber

from . import common
from .common import rule_positions, squash

_TITLE_RE = re.compile(r"（\s*([0-9０-９]{1,2})\s*）\s*([^\n]{4,60})")


def page_map(pdf_path: str) -> None:
    print(f"## 表タイトル → 物理ページ  ({pdf_path})")
    with pdfplumber.open(pdf_path) as doc:
        print(f"   ページ数 {len(doc.pages)} / 1ページ目 {doc.pages[0].width:.0f}x{doc.pages[0].height:.0f}pt")
        current = None
        for i, page in enumerate(doc.pages, start=1):
            text = page.extract_text(layout=True) or ""
            m = _TITLE_RE.search(text)
            title = squash(m.group(0)) if m else None
            if title and title != current:
                nv, nh = len(rule_positions(page, "v")), len(rule_positions(page, "h"))
                print(f"   p{i:<4} 縦{nv:>3}本 横{nh:>3}本  {title}")
                current = title


def collect_parties(pdf_path: str, election_id: str) -> None:
    """既知の党派名チェックを一時的に無効化して、出現する党派名を全部集める。"""
    from . import elections, t_counts, t_dhondt, t_party_votes, t_pr_lists, t_smd_candidates

    seen: set[str] = set()
    original = common.normalize_party

    def collecting(raw, known=None):
        name = original(raw, None)
        if name != "__TOTAL__":
            seen.add(name)
        return name

    for module in (t_counts, t_dhondt, t_party_votes, t_pr_lists, t_smd_candidates):
        module.normalize_party = collecting  # type: ignore[attr-defined]
    common.normalize_party = collecting  # type: ignore[assignment]

    cfg = elections.get(election_id)
    steps = [
        ("smd_candidates", lambda: t_smd_candidates.extract(pdf_path, cfg)),
        ("party_votes_smd_total", lambda: t_party_votes.extract_party_vote_totals(pdf_path, cfg, "party_votes_smd_total", "smd")),
        ("party_votes_pr_total", lambda: t_party_votes.extract_party_vote_totals(pdf_path, cfg, "party_votes_pr_total", "pr")),
        ("party_votes_by_pref_smd", lambda: t_party_votes.extract_pref_party_votes_smd(pdf_path, cfg)),
        ("party_votes_by_block_pref", lambda: t_party_votes.extract_block_pref_party_votes(pdf_path, cfg)),
        ("party_votes_by_block", lambda: t_party_votes.extract_block_party_votes(pdf_path, cfg)),
        ("pr_lists", lambda: t_pr_lists.extract(pdf_path, cfg)),
        ("dhondt", lambda: t_dhondt.extract(pdf_path, cfg)),
        ("candidacy_by_party", lambda: t_counts.extract_by_party(pdf_path, cfg, "candidacy")),
        ("candidacy_by_pref_party", lambda: t_counts.extract_by_pref_party(pdf_path, cfg, "candidacy")),
        ("winners_by_party", lambda: t_counts.extract_by_party(pdf_path, cfg, "winners")),
        ("winners_by_pref_party", lambda: t_counts.extract_by_pref_party(pdf_path, cfg, "winners")),
    ]
    for label, fn in steps:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — 調査用なので握って続行する
            print(f"   ! {label}: {type(exc).__name__}: {exc}")

    common.normalize_party = original  # type: ignore[assignment]
    print("\n## 出現した党派名（elections.py の parties にそのまま貼れる形）")
    for name in sorted(seen):
        print(f'        "{name}",')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--parties", metavar="ELECTION_ID", help="党派名も収集する（ページ設定が済んでいること）")
    args = parser.parse_args(argv)
    page_map(args.pdf)
    if args.parties:
        collect_parties(args.pdf, args.parties)
    return 0


if __name__ == "__main__":
    sys.exit(main())
