"""表 3(12) 党派別議席配分表（比例代表）＝ ドント式の除数表。

列構成: ``除数 | (順位, 商) × 党派数``。
党派名は見出しで2セルに分割されるため連結して読む。
行は除数 01, 02, … 50。商が空のセルは「その除数まで到達していない」ことを表す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from .common import (
    PR_BLOCKS,
    Cell,
    ExtractError,
    normalize_party,
    parse_decimal,
    parse_int,
    read_rows_by_baseline,
    rule_positions,
    squash,
)
from .elections import ElectionConfig

TABLE = "dhondt_table"

#: ブロック見出し。行頭に議席数などが入る回があるので、行全体ではなく部分一致で探す。
_BLOCK_RE = re.compile(r"[＜<](?P<name>[^＜<＞>]+?)選挙区[＞>]")


@dataclass
class DhondtQuotient:
    election_id: str
    block: str
    party: str
    divisor: int
    quotient: Decimal
    seat_rank: int | None
    """このブロック内で何番目に議席を獲得した商か。空なら議席に至っていない。"""
    source_page: int


def extract(pdf_path: str, cfg: ElectionConfig) -> list[DhondtQuotient]:
    out: list[DhondtQuotient] = []
    with pdfplumber.open(pdf_path) as doc:
        block = ""
        parties: list[str] = []
        for pno in cfg.page_range(TABLE):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            if (len(xs) - 2) % 2 != 0:
                raise ExtractError(f"{TABLE} p{pno}: 列数 {len(xs) - 1} が想定外です")
            n_parties = (len(xs) - 2) // 2
            ys = rule_positions(page, "h")
            if len(ys) < 3:
                raise ExtractError(f"{TABLE} p{pno}: 横罫が {len(ys)} 本しかありません")
            head_rows = read_rows_by_baseline(page, xs, ys[0], ys[-1])
            data_rows = read_rows_by_baseline(page, xs, ys[-2], ys[-1])

            found = _find_block(read_rows_by_baseline(page, xs, 0, ys[-2]))
            if found:
                block = found
                parties = []
            if not block:
                raise ExtractError(f"{TABLE} p{pno}: ブロック名が未確定です")

            names = _party_header(head_rows, n_parties, cfg)
            if names:
                parties = names
            if not parties:
                raise ExtractError(f"{TABLE} p{pno}: 党派名の見出しが見つかりません")

            for row in data_rows:
                divisor = parse_int(squash(row[0].text), field_name="除数")
                if divisor is None or divisor < 1:
                    continue
                for i, party in enumerate(parties):
                    rank_c, quot_c = row[1 + i * 2], row[2 + i * 2]
                    quotient = parse_decimal(
                        squash(quot_c.text), field_name=f"{block} {party} 除数{divisor}"
                    )
                    if quotient is None:
                        continue
                    out.append(
                        DhondtQuotient(
                            election_id=cfg.election_id,
                            block=block,
                            party=party,
                            divisor=divisor,
                            quotient=quotient,
                            seat_rank=parse_int(squash(rank_c.text), field_name="獲得順位"),
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{TABLE}: 1件も取れていません")
    return out


def _find_block(rows: list[list[Cell]]) -> str:
    for row in rows:
        joined = squash("".join(c.text for c in row))
        m = _BLOCK_RE.search(joined)
        if m and m.group("name") in PR_BLOCKS:
            return m.group("name")
    return ""


def _party_header(rows: list[list[Cell]], n_parties: int, cfg: ElectionConfig) -> list[str]:
    """党派名見出し行を探す。

    党派名は列幅を超えると2セルに割れる（第51回「自由民」+「主党」）が、
    割れずに1セルに収まる回もある（第50回）。どちらもグループ内を連結すれば同じ。
    先頭セルは空の回と「除数」が入る回があるため、そこには依存しない。
    """
    head = rows[:8]
    for i in range(len(head)):
        # 長い党派名は次の行に折り返されるので、1〜3行を連結しながら試す
        for j in range(i + 1, min(i + 4, len(head)) + 1):
            names = [
                squash(
                    "".join(
                        row[1 + k * 2].text + row[2 + k * 2].text
                        for row in head[i:j]
                        if 2 + k * 2 < len(row)
                    )
                )
                for k in range(n_parties)
            ]
            # 最終ページは後ろの党派列が空になる
            while names and not names[-1]:
                names.pop()
            if not names or not all(names):
                continue
            try:
                return [normalize_party(n, cfg.parties) for n in names]
            except ExtractError:
                continue
    return []
