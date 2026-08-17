"""表 3(8)(9) 投票総数・有効投票数・無効投票数。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from .common import (
    PR_BLOCKS,
    PREFECTURES,
    ExtractError,
    locate_pref_column,
    parse_decimal,
    read_rows_by_baseline,
    rule_positions,
    squash,
)
from .elections import ElectionConfig

def row_label(label: str, has_block_col: bool, block: str) -> str | None:
    """行見出しを ``都道府県名`` / ``"計"``（ブロック小計） / ``"合計"``（全国計）に正規化する。

    比例代表の表はブロック小計に「計」、全国計に「合計」を使う。
    小選挙区の表はブロックがないので「計」が全国計。
    """
    if label in PREFECTURES:
        return label
    if label == "合計":
        return "合計"
    if label in ("計", "総計"):
        return "計" if (has_block_col and block) else "合計"
    return None


_row_label = row_label


@dataclass
class Ballots:
    election_id: str
    tier: str
    """``smd`` / ``pr``。"""
    block: str
    """小選挙区の表ではブロック概念がないので空文字。"""
    prefecture: str
    """ブロック小計行は ``"計"``、全国計は ``"合計"``。"""
    total_ballots: Decimal
    valid_votes: Decimal
    invalid_votes: Decimal
    invalid_rate_pct: Decimal
    source_page: int


def extract_ballots_smd(pdf_path: str, cfg: ElectionConfig) -> list[Ballots]:
    """表3(8) 都道府県別 投票総数・有効投票数・無効投票数（小選挙区）。"""
    return _extract(pdf_path, cfg, "ballots_smd_by_pref", tier="smd", has_block_col=False)


def extract_ballots_pr(pdf_path: str, cfg: ElectionConfig) -> list[Ballots]:
    """表3(9) 選挙区別・都道府県別 投票総数等（比例代表）。"""
    return _extract(pdf_path, cfg, "ballots_pr_by_block_pref", tier="pr", has_block_col=True)


def _extract(
    pdf_path: str, cfg: ElectionConfig, table: str, *, tier: str, has_block_col: bool
) -> list[Ballots]:
    out: list[Ballots] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            # 行見出しの前に通し番号列が入る回があるので、都道府県列は実測で決める
            base = locate_pref_column(rows)
            if len(xs) - 1 < base + 5:
                raise ExtractError(
                    f"{table} p{pno}: 都道府県列 {base} の右に必要な4列がありません（全 {len(xs) - 1} 列）"
                )
            block = ""
            for row in rows:
                if has_block_col:
                    c0 = squash(row[base - 1].text) if base >= 1 else ""
                    if c0 in PR_BLOCKS:
                        block = c0
                label = squash(row[base].text)
                pref = _row_label(label, has_block_col, block)
                if pref is None:
                    continue
                if pref == "合計":
                    block = ""
                values = [squash(row[base + 1 + i].text) for i in range(4)]
                if not all(values):
                    raise ExtractError(f"{table} p{pno}: {label} 行に空欄があります: {values}")
                total, valid, invalid, rate = (
                    parse_decimal(v, field_name=f"{table} {label}") for v in values
                )
                out.append(
                    Ballots(
                        election_id=cfg.election_id,
                        tier=tier,
                        block=block if has_block_col else "",
                        prefecture=pref,
                        total_ballots=total,
                        valid_votes=valid,
                        invalid_votes=invalid,
                        invalid_rate_pct=rate,
                        source_page=pno,
                    )
                )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out
