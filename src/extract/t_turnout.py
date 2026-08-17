"""表 2(1)(2) 都道府県別 有権者数・投票者数・棄権者数・投票率。

各段（小選挙区／比例代表）が4ページで構成される。

* 有権者数・投票者数・棄権者数（男/女/計）        … ``electorate_*``
* 同（うち在外）                                  … ``electorate_*_overseas``
* 投票率(A)・前回投票率(B)・比較(A)-(B)（男/女/計） … ``turnout_*``
* 同（うち在外）                                  … ``turnout_*_overseas``

比例代表の表だけ先頭に「選挙区」列が付く。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from .common import (
    PR_BLOCKS,
    ExtractError,
    locate_pref_column,
    parse_decimal,
    read_rows_by_baseline,
    rule_positions,
    squash,
)
from .elections import ElectionConfig
from .t_ballots import row_label


@dataclass
class Electorate:
    election_id: str
    tier: str
    scope: str
    """``all``（全体）か ``overseas``（うち在外）。"""
    block: str
    prefecture: str
    electors_male: Decimal | None
    electors_female: Decimal | None
    electors_total: Decimal | None
    voters_male: Decimal | None
    voters_female: Decimal | None
    voters_total: Decimal | None
    abstainers_male: Decimal | None
    abstainers_female: Decimal | None
    abstainers_total: Decimal | None
    source_page: int


@dataclass
class Turnout:
    election_id: str
    tier: str
    scope: str
    block: str
    prefecture: str
    rate_male: Decimal | None
    rate_female: Decimal | None
    rate_total: Decimal | None
    prev_rate_male: Decimal | None
    prev_rate_female: Decimal | None
    prev_rate_total: Decimal | None
    diff_male: Decimal | None
    diff_female: Decimal | None
    diff_total: Decimal | None
    source_page: int


def extract_electorate(pdf_path: str, cfg: ElectionConfig, table: str, tier: str, scope: str):
    rows = _read(pdf_path, cfg, table, has_block_col=(tier == "pr"))
    return [
        Electorate(
            election_id=cfg.election_id,
            tier=tier,
            scope=scope,
            block=block,
            prefecture=pref,
            electors_male=v[0],
            electors_female=v[1],
            electors_total=v[2],
            voters_male=v[3],
            voters_female=v[4],
            voters_total=v[5],
            abstainers_male=v[6],
            abstainers_female=v[7],
            abstainers_total=v[8],
            source_page=pno,
        )
        for block, pref, v, pno in rows
    ]


def extract_turnout(pdf_path: str, cfg: ElectionConfig, table: str, tier: str, scope: str):
    rows = _read(pdf_path, cfg, table, has_block_col=(tier == "pr"))
    return [
        Turnout(
            election_id=cfg.election_id,
            tier=tier,
            scope=scope,
            block=block,
            prefecture=pref,
            rate_male=v[0],
            rate_female=v[1],
            rate_total=v[2],
            prev_rate_male=v[3],
            prev_rate_female=v[4],
            prev_rate_total=v[5],
            diff_male=v[6],
            diff_female=v[7],
            diff_total=v[8],
            source_page=pno,
        )
        for block, pref, v, pno in rows
    ]


def _read(
    pdf_path: str, cfg: ElectionConfig, table: str, *, has_block_col: bool
) -> list[tuple[str, str, list[Decimal | None], int]]:
    """「(選挙区) 都道府県 + 9つの数値列」型の表を共通で読む。"""
    out: list[tuple[str, str, list[Decimal | None], int]] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            base = locate_pref_column(rows)
            if len(xs) - 1 < base + 10:
                raise ExtractError(
                    f"{table} p{pno}: 都道府県列 {base} の右に必要な9列がありません（全 {len(xs) - 1} 列）"
                )
            block = ""
            for row in rows:
                if has_block_col:
                    c0 = squash(row[base - 1].text) if base >= 1 else ""
                    if c0 in PR_BLOCKS:
                        block = c0
                label = squash(row[base].text)
                pref = row_label(label, has_block_col, block)
                if pref is None:
                    continue
                if pref == "合計":
                    block = ""
                values = [
                    parse_decimal(squash(row[base + 1 + i].text), field_name=f"{table} {label}")
                    for i in range(9)
                ]
                out.append((block, pref, values, pno))
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out
