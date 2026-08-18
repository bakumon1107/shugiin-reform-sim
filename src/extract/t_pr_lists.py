"""表 3(11) 党派別当選人数（比例代表）＝ ブロック×党派の衆議院名簿。

1ページに党派グループが最大4つ並ぶ。各グループは7列:

    名簿 | 氏名(3セル) | 順位 | 小選挙区 | 惜敗率(％)

* ``名簿``  … 衆議院名簿の届出順位（同一順位に複数名が並ぶ＝重複立候補者の同順位グループ）
* ``順位``  … 比例代表での当選順。値が入っている＝比例で当選した者。
* ``小選挙区`` … 重複立候補者の小選挙区での当落（当／落）。
* ``惜敗率`` … 同上。``×`` は供託物没収点に達せず名簿記載なしとみなされた者。

グループ見出しには党派名・得票数・当選人数・男女内訳が入る。
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
    strip_party_label,
)
from .elections import ElectionConfig

TABLE = "pr_lists"
GROUP_COLS = 7

_BLOCK_RE = re.compile(r"^[＜<]?(?P<name>.+?)選挙区[＞>]?$")

#: グループ見出しの各行の始まり。党派名の折り返しと区別するために使う。
_HEADER_LINE_PREFIXES = ("得票数", "当選人数", "男", "名簿")


@dataclass
class PrPartyBlock:
    """ブロック×党派の見出し情報。"""

    election_id: str
    block: str
    party: str
    votes: Decimal
    seats: int
    seats_male: int | None
    seats_female: int | None
    source_page: int


@dataclass
class PrListEntry:
    election_id: str
    block: str
    party: str
    list_rank: int
    """名簿届出順位。"""
    name: str
    elected_order: int | None
    """比例代表での当選順。``None`` なら比例では当選していない。"""
    elected_pr: bool
    smd_result: str
    """``当`` / ``落`` / ``""``（重複立候補でない）。"""
    sekihai_rate: Decimal | None
    sekihai_excluded: bool
    dual_candidacy: bool
    source_page: int


def extract(
    pdf_path: str, cfg: ElectionConfig
) -> tuple[list[PrPartyBlock], list[PrListEntry]]:
    headers: list[PrPartyBlock] = []
    entries: list[PrListEntry] = []

    group_counts: dict[tuple[str, str] | None, int] = {}
    with pdfplumber.open(pdf_path) as doc:
        block = ""
        for pno in cfg.page_range(TABLE):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            if (len(xs) - 1) % GROUP_COLS != 0:
                raise ExtractError(
                    f"{TABLE} p{pno}: 列数 {len(xs) - 1} が {GROUP_COLS} の倍数ではありません"
                )
            n_groups = (len(xs) - 1) // GROUP_COLS
            ys = rule_positions(page, "h")
            if len(ys) < 3:
                raise ExtractError(f"{TABLE} p{pno}: 横罫が {len(ys)} 本しかありません")
            # ページ末尾の脚注（※…）やノンブルを拾わないよう、表の内側だけを見る。
            head_rows = read_rows_by_baseline(page, xs, ys[0], ys[-2])
            data_rows = read_rows_by_baseline(page, xs, ys[-2], ys[-1])

            found = _find_block(read_rows_by_baseline(page, xs, 0, ys[0]))
            if found:
                block = found
            if not block:
                raise ExtractError(f"{TABLE} p{pno}: ブロック名が未確定です")

            by_group = dict(_parse_group_headers(head_rows, n_groups, block, cfg, pno))
            headers.extend(by_group.values())

            for row in data_rows:
                for g in range(n_groups):
                    cells = row[g * GROUP_COLS : (g + 1) * GROUP_COLS]
                    header = by_group.get(g)
                    key = (block, header.party) if header else None
                    entry = _parse_entry(
                        cells,
                        header,
                        block,
                        cfg,
                        pno,
                        index=group_counts.get(key, 0),
                        images=_name_images(page, xs, g, row),
                    )
                    if entry is not None:
                        group_counts[key] = group_counts.get(key, 0) + 1
                        entries.append(entry)

    if not headers or not entries:
        raise ExtractError(f"{TABLE}: 見出しまたは名簿が取れていません")
    return headers, entries


def _find_block(rows: list[list[Cell]]) -> str:
    for row in rows:
        joined = squash("".join(c.text for c in row))
        m = _BLOCK_RE.match(joined)
        if m and m.group("name") in PR_BLOCKS:
            return m.group("name")
    return ""


def _parse_group_headers(
    rows: list[list[Cell]], n_groups: int, block: str, cfg: ElectionConfig, pno: int
) -> list[tuple[int, PrPartyBlock]]:
    """グループ見出し（党派名・得票数・当選人数・男女）をまとめて読む。"""
    out: list[tuple[int, PrPartyBlock]] = []
    for g in range(n_groups):
        texts = [squash("".join(c.text for c in row[g * GROUP_COLS : (g + 1) * GROUP_COLS])) for row in rows]
        party_idx = next(
            (i for i, t in enumerate(texts) if strip_party_label(t) is not None), None
        )
        if party_idx is None:
            continue
        party_raw = strip_party_label(texts[party_idx]) or ""
        # 長い党派名は次の行に折り返される（「ＮＨＫと裁判してる党」＋「弁護士法７２条違反で」）
        for cont in texts[party_idx + 1 :]:
            if not cont or any(cont.startswith(p) for p in _HEADER_LINE_PREFIXES):
                break
            party_raw += cont
        if not party_raw:
            continue
        votes_line = next((t for t in texts if t.startswith("得票数")), "")
        seats_line = next((t for t in texts if t.startswith("当選人数")), "")
        gender_line = next((t for t in texts if t.startswith("男")), "")

        votes = parse_decimal(votes_line[len("得票数") :], field_name=f"{block} {party_raw} 得票数")
        seats = parse_int(seats_line[len("当選人数") :], field_name=f"{block} {party_raw} 当選人数")
        if votes is None or seats is None:
            raise ExtractError(f"{TABLE} p{pno}: {block} {party_raw} の得票数/当選人数が読めません")
        gm = re.match(r"^男(?P<m>\d+)人女(?P<f>\d+)人$", gender_line)
        out.append(
            (
                g,
                PrPartyBlock(
                    election_id=cfg.election_id,
                    block=block,
                    party=normalize_party(party_raw, cfg.parties),
                    votes=votes,
                    seats=seats,
                    seats_male=int(gm.group("m")) if gm else None,
                    seats_female=int(gm.group("f")) if gm else None,
                    source_page=pno,
                ),
            )
        )
    return out


def _name_images(page: pdfplumber.page.Page, xs: list[float], g: int, row: list[Cell]) -> list[dict]:
    """氏名セル（グループ内の2〜4列目）に重なる埋め込み画像。

    Word由来のPDFでは稀な字形が画像で貼り込まれ、テキストレイヤーから欠落する。
    """
    baselines = [t for c in row for t, _ in c.lines]
    if not baselines:
        return []
    base = min(baselines)
    left, right = xs[g * GROUP_COLS + 1], xs[g * GROUP_COLS + 4]
    return [
        im
        for im in page.images
        if left <= (im["x0"] + im["x1"]) / 2 < right and abs(im["top"] - base) <= 6
    ]


def _parse_entry(
    cells: list[Cell],
    header: PrPartyBlock | None,
    block: str,
    cfg: ElectionConfig,
    pno: int,
    *,
    index: int,
    images: list[dict],
) -> PrListEntry | None:
    list_rank_raw = squash(cells[0].text)
    name = squash("".join(c.text for c in cells[1:4]))
    if not list_rank_raw and not name and not images:
        return None
    if header is None:
        raise ExtractError(f"{TABLE} p{pno}: 党派見出しのないグループに名簿行があります: {name!r}")
    list_rank = parse_int(list_rank_raw, field_name=f"{block} {header.party} 名簿順位")
    if list_rank is None:
        return None
    if images:
        key = (block, header.party, index)
        override = cfg.pr_name_overrides.get(key)
        if override is None:
            raise ExtractError(
                f"{TABLE} p{pno}: {block} {header.party} 名簿{list_rank} の氏名が"
                f"画像として埋め込まれておりテキストから読めません。目視で確認し、"
                f"elections.py の pr_name_overrides に {key!r} を追加してください。"
            )
        name = override
    if not name:
        raise ExtractError(f"{TABLE} p{pno}: {block} {header.party} 名簿{list_rank} の氏名が空です")

    elected_order = parse_int(squash(cells[4].text), field_name="当選順")
    smd_result = squash(cells[5].text)
    if smd_result not in ("", "当", "落"):
        raise ExtractError(f"{TABLE} p{pno}: 小選挙区欄が {smd_result!r} です ({name})")
    sekihai_raw = squash(cells[6].text)
    excluded = sekihai_raw in ("×", "x", "X", "✕")
    sekihai = None if excluded else parse_decimal(sekihai_raw, field_name="惜敗率")

    return PrListEntry(
        election_id=cfg.election_id,
        block=block,
        party=header.party,
        list_rank=list_rank,
        name=name,
        elected_order=elected_order,
        elected_pr=elected_order is not None,
        smd_result=smd_result,
        sekihai_rate=sekihai,
        sekihai_excluded=excluded,
        dual_candidacy=smd_result != "",
        source_page=pno,
    )
