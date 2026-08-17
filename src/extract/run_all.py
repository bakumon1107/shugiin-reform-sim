"""PDF から全テーブルを抽出して ``data/csv/*.csv`` に書き出す。

使い方::

    python -m extract.run_all              # 既定の選挙回
    python -m extract.run_all r06-10-27    # 選挙回を指定
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from . import elections, t_ballots, t_counts, t_dhondt, t_party_votes, t_pr_lists, t_smd_candidates, t_turnout
from .csvio import write_dataclasses
from .elections import ElectionConfig

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "raw"
CSV_DIR = ROOT / "data" / "csv"


def verify_source(cfg: ElectionConfig) -> Path:
    path = RAW_DIR / cfg.pdf_filename
    if not path.exists():
        raise SystemExit(f"PDF がありません: {path}\n  {cfg.source_url} から取得してください。")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != cfg.sha256:
        raise SystemExit(
            f"PDF の sha256 が一致しません。\n  期待: {cfg.sha256}\n  実際: {digest}\n"
            "  差し替わった可能性があります。elections.py の定義を確認してください。"
        )
    return path


def run(cfg: ElectionConfig) -> dict[str, int]:
    pdf = str(verify_source(cfg))
    out_dir = CSV_DIR / cfg.election_id
    counts: dict[str, int] = {}

    def emit(name: str, rows) -> None:
        counts[name] = write_dataclasses(out_dir / f"{name}.csv", rows)
        print(f"  {name:32s} {counts[name]:6d} 行")

    print(f"[{cfg.election_id}] 第{cfg.ordinal}回 / {cfg.election_date} / {cfg.pdf_filename}")

    districts, candidates = t_smd_candidates.extract(pdf, cfg)
    emit("smd_districts", districts)
    emit("smd_candidates", candidates)

    emit("party_votes_smd_total", t_party_votes.extract_party_vote_totals(pdf, cfg, "party_votes_smd_total", "smd"))
    emit("party_votes_pr_total", t_party_votes.extract_party_vote_totals(pdf, cfg, "party_votes_pr_total", "pr"))
    emit("party_votes_by_pref_smd", t_party_votes.extract_pref_party_votes_smd(pdf, cfg))
    emit("party_votes_by_block_pref", t_party_votes.extract_block_pref_party_votes(pdf, cfg))
    emit("party_votes_by_block", t_party_votes.extract_block_party_votes(pdf, cfg))

    emit("ballots_smd_by_pref", t_ballots.extract_ballots_smd(pdf, cfg))
    emit("ballots_pr_by_block_pref", t_ballots.extract_ballots_pr(pdf, cfg))

    electorate = []
    turnout = []
    for tier in ("smd", "pr"):
        for scope, suffix in (("all", ""), ("overseas", "_overseas")):
            electorate += t_turnout.extract_electorate(pdf, cfg, f"electorate_{tier}{suffix}", tier, scope)
            turnout += t_turnout.extract_turnout(pdf, cfg, f"turnout_{tier}{suffix}", tier, scope)
    emit("electorate", electorate)
    emit("turnout", turnout)

    pr_blocks, pr_entries = t_pr_lists.extract(pdf, cfg)
    emit("pr_party_blocks", pr_blocks)
    emit("pr_list_entries", pr_entries)
    emit("dhondt_quotients", t_dhondt.extract(pdf, cfg))

    for kind in ("candidacy", "winners"):
        emit(f"{kind}_by_party", t_counts.extract_by_party(pdf, cfg, kind))
        emit(f"{kind}_by_pref_party", t_counts.extract_by_pref_party(pdf, cfg, kind))
        emit(f"{kind}_by_pref_age", t_counts.extract_by_pref_age(pdf, cfg, kind))

    print(f"  → {out_dir} に {len(counts)} 本の CSV / 合計 {sum(counts.values())} 行")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", default=elections.DEFAULT_ELECTION)
    args = parser.parse_args(argv)
    if args.election_id not in elections.ELECTIONS:
        raise SystemExit(f"未知の選挙回: {args.election_id}（既知: {', '.join(elections.ELECTIONS)}）")
    run(elections.get(args.election_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
