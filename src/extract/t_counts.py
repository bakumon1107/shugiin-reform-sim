"""表 1(1)(2)(3) 立候補状況 と 表 3(1)(2)(3) 当選人数。

両者はレイアウトが同一なので ``kind`` (``candidacy`` / ``winners``) で切り替える。

* (1) 党派別男女別新前元別 …… 区分(小選挙区/比例代表/計) × 新前元計 × 党派 × 男女計。
  比例代表の区分では各セルの2行目に重複立候補者数が ``( n )`` の内数で入る。
* (2) 都道府県別党派別新前元別 …… 「新前元計」の4サブ列に罫線がないため、
  党派列を4等分して文字を割り付ける。先頭に「定数」（小選挙区の定数）列がある。
* (3) 都道府県別年齢段階別 …… 5歳刻みの年齢段階 × 都道府県。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pdfplumber

from .common import (
    PREFECTURES,
    Cell,
    ExtractError,
    normalize_party,
    parse_int,
    read_grid,
    read_rows_by_baseline,
    rule_positions,
    squash,
)
from .elections import ElectionConfig

STATUS_ORDER = ("新", "前", "元", "計")
_SECTION_BY_INDEX = ("smd", "pr", "total")
_PAREN_RE = re.compile(r"[（(](?P<n>[\d,]+)[)）]")


# ---------------------------------------------------------------------------
# (1) 党派別男女別新前元別
# ---------------------------------------------------------------------------


@dataclass
class PartyGenderStatusCount:
    election_id: str
    kind: str
    section: str
    """``smd`` / ``pr`` / ``total``。"""
    status: str
    """``新`` / ``前`` / ``元`` / ``計``。"""
    party: str
    male: int | None
    female: int | None
    total: int | None
    dual_male: int | None
    """比例代表区分のみ。重複立候補者数の内数。"""
    dual_female: int | None
    dual_total: int | None
    source_page: int


def extract_by_party(pdf_path: str, cfg: ElectionConfig, kind: str) -> list[PartyGenderStatusCount]:
    table = "candidacy_by_party" if kind == "candidacy" else "winners_by_party"
    out: list[PartyGenderStatusCount] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            ys = rule_positions(page, "h")
            if (len(xs) - 3) % 3 != 0:
                raise ExtractError(f"{table} p{pno}: 列数 {len(xs) - 1} が想定外です")
            n_parties = (len(xs) - 3) // 3
            parties = _party_header(page, xs, ys[2], group_size=3, offset=2, cfg=cfg, where=f"{table} p{pno}")
            # 見出し帯の横罫本数は回によって1本増減するので、行数を決め打ちにせず
            # 「新／前／元／計」が印字された行だけをデータ行として拾う。
            rows = [
                row
                for row in read_grid(page, xs, ys[1:])
                if squash(row[1].text) in STATUS_ORDER
            ]
            if len(rows) != len(STATUS_ORDER) * len(_SECTION_BY_INDEX):
                raise ExtractError(
                    f"{table} p{pno}: データ行が {len(rows)} 行です"
                    f"（期待 {len(STATUS_ORDER) * len(_SECTION_BY_INDEX)}）"
                )
            for r, row in enumerate(rows):
                section = _SECTION_BY_INDEX[r // 4]
                status = STATUS_ORDER[r % 4]
                printed = squash(row[1].text)
                if printed != status:
                    raise ExtractError(
                        f"{table} p{pno}: 行{r} の新前元別が {printed!r}（期待 {status!r}）"
                    )
                for i, party in enumerate(parties):
                    if party is None:
                        continue
                    cells = row[2 + i * 3 : 5 + i * 3]
                    main = [_first_line_int(c, f"{table} {party}") for c in cells]
                    dual = [_paren_int(c) for c in cells]
                    out.append(
                        PartyGenderStatusCount(
                            election_id=cfg.election_id,
                            kind=kind,
                            section=section,
                            status=status,
                            party=party,
                            male=main[0],
                            female=main[1],
                            total=main[2],
                            dual_male=dual[0],
                            dual_female=dual[1],
                            dual_total=dual[2],
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


def _first_line_int(cell: Cell, where: str) -> int | None:
    for _, line in cell.lines:
        text = squash(line)
        if _PAREN_RE.fullmatch(text):
            continue
        return parse_int(text, field_name=where)
    return None


def _paren_int(cell: Cell) -> int | None:
    m = _PAREN_RE.search(squash(cell.text))
    return parse_int(m.group("n"), field_name="重複内数") if m else None


# ---------------------------------------------------------------------------
# (2) 都道府県別党派別新前元別
# ---------------------------------------------------------------------------


@dataclass
class PrefPartyStatusCount:
    election_id: str
    kind: str
    prefecture: str
    seats: int | None
    """都道府県の小選挙区定数。"""
    party: str
    new: int | None
    incumbent: int | None
    former: int | None
    total: int | None
    source_page: int


def extract_by_pref_party(pdf_path: str, cfg: ElectionConfig, kind: str) -> list[PrefPartyStatusCount]:
    table = "candidacy_by_pref_party" if kind == "candidacy" else "winners_by_pref_party"
    out: list[PrefPartyStatusCount] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            # 列: 都道府県 | 定数 | 党派…（各党派列の中に新前元計の4サブ列が罫線なしで並ぶ）
            party_bounds = xs[2:]
            parties = _party_header(page, xs, None, group_size=1, offset=2, cfg=cfg, where=f"{table} p{pno}")
            ys = rule_positions(page, "h")
            sub_xs = _subdivide(party_bounds, 4)
            all_xs = list(xs[:2]) + sub_xs
            for row in read_rows_by_baseline(page, all_xs, ys[0], ys[-1]):
                pref = squash(row[0].text)
                if pref not in PREFECTURES and pref not in ("計", "合計"):
                    continue
                seats = parse_int(squash(row[1].text), field_name=f"{table} {pref} 定数")
                for i, party in enumerate(parties):
                    if party is None:
                        continue
                    n, f, e, t = (
                        parse_int(squash(row[2 + i * 4 + k].text), field_name=f"{table} {pref} {party}")
                        for k in range(4)
                    )
                    out.append(
                        PrefPartyStatusCount(
                            election_id=cfg.election_id,
                            kind=kind,
                            prefecture="合計" if pref in ("計", "合計") else pref,
                            seats=seats,
                            party=party,
                            new=n,
                            incumbent=f,
                            former=e,
                            total=t,
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


def _subdivide(bounds: list[float], n: int) -> list[float]:
    """各列を ``n`` 等分した境界列を作る（罫線のないサブ列を復元するため）。"""
    out: list[float] = [bounds[0]]
    for a, b in zip(bounds, bounds[1:]):
        step = (b - a) / n
        out.extend(a + step * k for k in range(1, n + 1))
    return out


# ---------------------------------------------------------------------------
# (3) 都道府県別年齢段階別
# ---------------------------------------------------------------------------


@dataclass
class PrefAgeCount:
    election_id: str
    kind: str
    prefecture: str
    age_band: str
    count: int | None
    source_page: int


def extract_by_pref_age(pdf_path: str, cfg: ElectionConfig, kind: str) -> list[PrefAgeCount]:
    table = "candidacy_by_pref_age" if kind == "candidacy" else "winners_by_pref_age"
    out: list[PrefAgeCount] = []
    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(table):
            page = doc.pages[pno - 1]
            xs = rule_positions(page, "v")
            ys = rule_positions(page, "h")
            # 表題行やノンブルを見出しとして拾わないよう、罫線の内側だけを読む。
            rows = read_rows_by_baseline(page, xs, ys[0], ys[-1])
            bands = _age_bands(rows, len(xs) - 2, f"{table} p{pno}")
            if len(bands) != len(xs) - 2:
                raise ExtractError(f"{table} p{pno}: 年齢段階の列数が合いません")
            for row in rows:
                pref = squash(row[0].text)
                if pref not in PREFECTURES and pref not in ("計", "合計"):
                    continue
                for i, band in enumerate(bands):
                    out.append(
                        PrefAgeCount(
                            election_id=cfg.election_id,
                            kind=kind,
                            prefecture="合計" if pref in ("計", "合計") else pref,
                            age_band=band,
                            count=parse_int(
                                squash(row[1 + i].text), field_name=f"{table} {pref} {band}"
                            ),
                            source_page=pno,
                        )
                    )
    if not out:
        raise ExtractError(f"{table}: 1件も取れていません")
    return out


#: 行見出し列に入るラベル（回によって「都道府県」「区分」と揺れる）
ROW_HEADER_LABELS = ("", "都道府県", "区分", "比例代表区")

_BAND_RANGE_RE = re.compile(r"^(\d+)歳[~～]?(\d+)歳$")
_BAND_OVER_RE = re.compile(r"^(\d+)歳以上$")


def _age_bands(rows: list[list[Cell]], n: int, where: str) -> list[str]:
    """「25歳 / ～ / 29歳」のように3行に分かれた年齢段階見出しを1つに畳む。

    見出しは必ず最初の都道府県行より上にある。ノンブル等が表の内側に食い込んでいても
    拾わないよう、データ開始位置より下は見ない。
    ラベルは回ごとの表記ゆれ（全角数字・「～」の有無）を正規化して同じ形にそろえる。
    """
    first_data = next(
        (i for i, row in enumerate(rows) if squash(row[0].text) in PREFECTURES), len(rows)
    )
    header_rows = [
        row
        for row in rows[:first_data]
        if squash(row[0].text) in ROW_HEADER_LABELS and len(row) > n
    ]
    parts: list[list[str]] = [[] for _ in range(n)]
    for row in header_rows:
        for i in range(n):
            text = squash(row[1 + i].text)
            if text:
                parts[i].append(text)
    bands = [_canonical_band("".join(p), where) for p in parts]
    if not all(bands) or len(set(bands)) != len(bands):
        raise ExtractError(f"{where}: 年齢段階の見出しを復元できません: {bands}")
    return bands


def _canonical_band(label: str, where: str) -> str:
    text = unicodedata.normalize("NFKC", label)
    if m := _BAND_RANGE_RE.match(text):
        return f"{m.group(1)}歳～{m.group(2)}歳"
    if m := _BAND_OVER_RE.match(text):
        return f"{m.group(1)}歳以上"
    if text in ("計", "合計"):
        return "計"
    if not text:
        return ""
    raise ExtractError(f"{where}: 年齢段階の見出しを解釈できません: {label!r}")


# ---------------------------------------------------------------------------


def _party_header(
    page: pdfplumber.page.Page,
    xs: list[float],
    y_limit: float | None,
    *,
    group_size: int,
    offset: int,
    cfg: ElectionConfig,
    where: str,
) -> list[str | None]:
    """見出し行から党派名を拾う。

    列幅を超えた党派名はグループ内の複数セルに割れるだけでなく、次の行にも折り返される
    （「ＮＨＫと裁判してる党」＋「弁護士法７２条違反で」）。連続する1〜3行を連結しながら試す。
    """
    limit = y_limit if y_limit is not None else page.height
    rows = read_rows_by_baseline(page, xs, 0, limit)
    for i in range(len(rows)):
        for j in range(i + 1, min(i + 4, len(rows)) + 1):
            span = [row[offset:] for row in rows[i:j]]
            width = max(len(cells) for cells in span)
            names: list[str | None] = []
            for start in range(0, width, group_size):
                joined = squash(
                    "".join(
                        c.text
                        for cells in span
                        for c in cells[start : start + group_size]
                    )
                )
                names.append(joined or None)
            if not any(names):
                continue
            try:
                return [normalize_party(n, cfg.parties) if n else None for n in names]
            except ExtractError:
                continue
    raise ExtractError(f"{where}: 党派名の見出し行を特定できません")
