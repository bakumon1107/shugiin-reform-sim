"""党派別得票数まわりの表 3(4)(5)(6)(7)(10) の抽出。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from .common import (
    PARTY_COLUMN_LABELS,
    PR_BLOCKS,
    PREFECTURES,
    Cell,
    ExtractError,
    normalize_party,
    parse_decimal,
    parse_int,
    read_rows_by_baseline,
    require_shape,
    rule_positions,
    squash,
)
from .elections import ElectionConfig
from .t_ballots import row_label

_BLOCK_HEADER_RE = re.compile(r"^[＜<](?P<name>.+?)選挙区[＞>]$")
_TOTAL_LABELS = {"計", "合計", "得票総数", "総計"}


# ---------------------------------------------------------------------------
# 3(4) 党派別得票数（小選挙区） / 3(5) 党派別得票数（比例代表）
# ---------------------------------------------------------------------------


@dataclass
class PartyVoteTotal:
    election_id: str
    tier: str
    """``smd`` か ``pr``。"""
    period: str
    """``current`` / ``previous`` / ``diff``。"""
    party: str
    votes: Decimal | None
    share_pct: Decimal | None
    source_page: int


_PERIOD_BY_LABEL = {"今回": "current", "前回": "previous", "差引": "diff"}


def extract_party_vote_totals(
    pdf_path: str, cfg: ElectionConfig, table: str, tier: str
) -> list[PartyVoteTotal]:
    out: list[PartyVoteTotal] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            parties: list[str] = []
            period: str | None = None
            for row in rows:
                label = squash(row[0].text)
                cells = row[1:]
                if label == "区分":
                    parties = [squash(c.text) for c in cells]
                    period = None
                    continue
                if label in _PERIOD_BY_LABEL:
                    period = _PERIOD_BY_LABEL[label]
                    if not parties:
                        raise ExtractError(f"{table} p{pno}: 区分行より前に {label} 行が現れました")
                    for name, cell in zip(parties, cells):
                        if not name:
                            continue
                        out.append(
                            PartyVoteTotal(
                                election_id=cfg.election_id,
                                tier=tier,
                                period=period,
                                party=normalize_party(name, cfg.parties),
                                votes=parse_decimal(cell.compact, field_name=f"{table} {name}"),
                                share_pct=None,
                                source_page=pno,
                            )
                        )
                    continue
                # 直前の period 行に対応する (率) 行
                if period and label == "" and any(c.compact.startswith("(") for c in cells):
                    recent = {r.party: r for r in out if r.period == period and r.source_page == pno}
                    for name, cell in zip(parties, cells):
                        rec = recent.get(normalize_party(name, cfg.parties)) if name else None
                        if rec is None:
                            continue
                        rec.share_pct = parse_decimal(
                            cell.compact.strip("()（）"), field_name=f"{table} {name} 率"
                        )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


# ---------------------------------------------------------------------------
# 3(6) 都道府県別党派別得票数（小選挙区）
# ---------------------------------------------------------------------------


@dataclass
class PrefPartyVote:
    election_id: str
    prefecture: str
    party: str
    votes_male: Decimal | None
    votes_female: Decimal | None
    votes_total: Decimal | None
    source_page: int


def extract_pref_party_votes_smd(pdf_path: str, cfg: ElectionConfig) -> list[PrefPartyVote]:
    table = "party_votes_by_pref_smd"
    out: list[PrefPartyVote] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            parties = _party_groups_from_header(rows, group_size=3, cfg=cfg, where=f"{table} p{pno}")
            for row in rows:
                pref = squash(row[0].text)
                if pref not in PREFECTURES and pref not in _TOTAL_LABELS:
                    continue
                for i, party in enumerate(parties):
                    if party is None:
                        continue
                    m, f, t = (row[1 + i * 3 + k] for k in range(3))
                    out.append(
                        PrefPartyVote(
                            election_id=cfg.election_id,
                            prefecture="合計" if pref in _TOTAL_LABELS else pref,
                            party=party,
                            votes_male=parse_decimal(m.compact, field_name=f"{pref} {party} 男"),
                            votes_female=parse_decimal(f.compact, field_name=f"{pref} {party} 女"),
                            votes_total=parse_decimal(t.compact, field_name=f"{pref} {party} 計"),
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


def _party_groups_from_header(
    rows: list[list[Cell]], *, group_size: int, cfg: ElectionConfig, where: str
) -> list[str | None]:
    """「都道府県 | 党A(男女計) | 党B(男女計) | …」型の見出しから党派名を拾う。

    * 党派名は列幅を超えると複数セルに折り返される（例: ``減税日本・ゆうこ`` + ``く連合``）ため、
      グループ内の全セルを連結してから正規化する。
    * 最終ページは後ろのグループが空になる。その位置は ``None`` を返す。
    """
    sub_idx = next(
        (
            i
            for i, row in enumerate(rows)
            if [squash(c.text) for c in row[1 : 1 + group_size]] == ["男", "女", "計"]
        ),
        None,
    )
    if sub_idx is None:
        raise ExtractError(f"{where}: 「男/女/計」の副見出し行が見つかりません")
    header = next(
        (rows[i] for i in range(sub_idx - 1, -1, -1) if any(squash(c.text) for c in rows[i][1:])),
        None,
    )
    if header is None:
        raise ExtractError(f"{where}: 党派名の見出し行を特定できません")

    names: list[str | None] = []
    cells = header[1:]
    for start in range(0, len(cells), group_size):
        joined = squash("".join(c.text for c in cells[start : start + group_size]))
        names.append(normalize_party(joined, cfg.parties) if joined else None)
    return names


# ---------------------------------------------------------------------------
# 3(7) 比例代表選挙区別都道府県別党派別得票数
# ---------------------------------------------------------------------------


@dataclass
class BlockPrefPartyVote:
    election_id: str
    block: str
    prefecture: str
    """ブロック小計行は ``"計"``。"""
    party: str
    votes: Decimal | None
    source_page: int


def extract_block_pref_party_votes(pdf_path: str, cfg: ElectionConfig) -> list[BlockPrefPartyVote]:
    table = "party_votes_by_block_pref"
    out: list[BlockPrefPartyVote] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            parties = _block_pref_header(rows, cfg, f"{table} p{pno}")
            block: str | None = None
            for row in rows:
                c0, c1 = squash(row[0].text), squash(row[1].text)
                if c0 in PR_BLOCKS:
                    block = c0
                if block is None:
                    continue
                pref = row_label(c1, True, block)
                if pref is None:
                    continue
                if pref == "合計":
                    block = ""
                for party, cell in zip(parties, row[2:]):
                    out.append(
                        BlockPrefPartyVote(
                            election_id=cfg.election_id,
                            block=block,
                            prefecture=pref,
                            party=party,
                            votes=parse_decimal(cell.compact, field_name=f"{block} {pref} {party}"),
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


# ---------------------------------------------------------------------------
# 3(10) 比例代表選挙区別党派別得票数
# ---------------------------------------------------------------------------


@dataclass
class BlockPartyVote:
    election_id: str
    block: str
    rank: int | None
    party: str
    votes: Decimal
    share_pct: Decimal | None
    is_total_row: bool
    source_page: int


def extract_block_party_votes(pdf_path: str, cfg: ElectionConfig) -> list[BlockPartyVote]:
    table = "party_votes_by_block"
    out: list[BlockPartyVote] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            # 「順位/党派名/得票数/得票率」の4列が3組。組の境界は共有される。
            if (len(xs) - 1) % 4 != 0:
                raise ExtractError(f"{table} p{pno}: 列数 {len(xs) - 1} が4の倍数ではありません")
            n_groups = (len(xs) - 1) // 4
            rows = read_rows_by_baseline(page, xs, 0, page.height)
            block = _find_block_header(rows, f"{table} p{pno}")
            # 表題行やブロック見出し行が党派名として拾われないよう、
            # 「順位/党派名/…」の見出し行より後ろだけを見る。
            head = next(
                (
                    i
                    for i, row in enumerate(rows)
                    if squash(row[0].text) == "順位"
                    and squash(row[1].text) in PARTY_COLUMN_LABELS
                ),
                None,
            )
            if head is None:
                raise ExtractError(f"{table} p{pno}: 「順位/党派名」の見出し行が見つかりません")
            for row in rows[head + 1 :]:
                for g in range(n_groups):
                    rank_c, party_c, votes_c, share_c = row[g * 4 : g * 4 + 4]
                    party_raw = squash(party_c.text)
                    if not party_raw or party_raw == "党派名":
                        continue
                    is_total = party_raw in _TOTAL_LABELS
                    votes = parse_decimal(votes_c.compact, field_name=f"{block} {party_raw}")
                    if votes is None:
                        raise ExtractError(f"{table} p{pno}: {party_raw} の得票数が空です")
                    out.append(
                        BlockPartyVote(
                            election_id=cfg.election_id,
                            block=block,
                            rank=parse_int(rank_c.compact, field_name="順位"),
                            party="__TOTAL__" if is_total else normalize_party(party_raw, cfg.parties),
                            votes=votes,
                            share_pct=parse_decimal(share_c.compact, field_name="得票率"),
                            is_total_row=is_total,
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


def _block_pref_header(rows: list[list[Cell]], cfg: ElectionConfig, where: str) -> list[str]:
    """表(7)の党派名見出し行を探す。

    見出しの1・2列目のラベルは回によって揺れる（「選挙区/都道府県」と「比例代表区/区分」）。
    ラベルに依存せず、3列目以降がすべて既知の党派名になる行を見出しとみなす。
    """
    first_data = next(
        (i for i, row in enumerate(rows) if squash(row[1].text) in PREFECTURES), len(rows)
    )
    for row in reversed(rows[:first_data]):
        names = [squash(c.text) for c in row[2:]]
        # 最終ページは「合計」列だけになるなど、後ろの列が余る
        while names and not names[-1]:
            names.pop()
        if not names or not all(names):
            continue
        try:
            return [normalize_party(n, cfg.parties) for n in names]
        except ExtractError:
            continue
    raise ExtractError(f"{where}: 党派名の見出し行を特定できません")


def _find_block_header(rows: list[list[Cell]], where: str) -> str:
    for row in rows:
        joined = squash("".join(c.text for c in row))
        m = _BLOCK_HEADER_RE.match(joined)
        if m and m.group("name") in PR_BLOCKS:
            return m.group("name")
    raise ExtractError(f"{where}: 「＜○○選挙区＞」のブロック見出しが見つかりません")
