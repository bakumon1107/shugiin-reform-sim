"""表 2(1)(2) 都道府県別 有権者数・投票者数・棄権者数・投票率。

小選挙区／比例代表それぞれが4ページで構成される。

* 有権者数・投票者数・棄権者数（男/女/計）
* 投票率(A)・前回投票率(B)・比較(A)-(B)（男/女/計）
* 上の2つの「（うち在外）」版

**4ページの並び順は回によって違う**（第51回は 本体/在外/率/在外率、
第47回は 本体/率/在外/在外率）。順序を決め打ちせず、ページの中身で判定する:

* 「うち在外」が表題にあれば ``scope=overseas``
* 「棄権者数」があれば有権者数の表、「投票率」＋「前回」があれば投票率の表

比例代表の表だけ先頭に選挙区（ブロック）列が付く。
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


def extract(
    pdf_path: str, cfg: ElectionConfig, tier: str
) -> tuple[list[Electorate], list[Turnout]]:
    """``electorate_<tier>`` の4ページを読み、内容で振り分けて返す。"""
    table = f"electorate_{tier}"
    electorate: list[Electorate] = []
    turnout: list[Turnout] = []
    seen: set[tuple[str, str]] = set()

    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            text = squash(page.extract_text() or "")
            scope = "overseas" if "うち在外" in text else "all"
            if "棄権者数" in text:
                kind = "electorate"
            elif "投票率" in text and "前回" in text:
                kind = "turnout"
            else:
                raise ExtractError(
                    f"{table} p{pno}: 有権者数の表か投票率の表か判別できません"
                )
            if (kind, scope) in seen:
                raise ExtractError(f"{table} p{pno}: {kind}/{scope} が重複しています")
            seen.add((kind, scope))
            rows = _read_page(page, pno, table, has_block_col=(tier == "pr"))
            if kind == "electorate":
                electorate.extend(_to_electorate(rows, cfg, tier, scope))
            else:
                turnout.extend(_to_turnout(rows, cfg, tier, scope))

    missing = {("electorate", "all"), ("electorate", "overseas"), ("turnout", "all"), ("turnout", "overseas")} - seen
    if missing:
        raise ExtractError(f"{table}: 読めなかった組合せがあります: {sorted(missing)}")
    return electorate, turnout


def _to_electorate(rows, cfg: ElectionConfig, tier: str, scope: str):
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


def _to_turnout(rows, cfg: ElectionConfig, tier: str, scope: str):
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


def _read_page(
    page: pdfplumber.page.Page, pno: int, table: str, *, has_block_col: bool
) -> list[tuple[str, str, list[Decimal | None], int]]:
    """「(選挙区) 都道府県 + 9つの数値列」型の1ページを読む。"""
    out: list[tuple[str, str, list[Decimal | None], int]] = []
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
        raise ExtractError(f"{table} p{pno}: 1件も取れていません")
    return out
