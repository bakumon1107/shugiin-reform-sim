"""表3(13) 候補者別得票数（小選挙区）の抽出。

ページ構造（第51回・第50回で共通）
-----------------------------------
* 1ページ = 2段組み。各段が 9列 × 16行 の固定グリッド。
* 縦罫19本 / 横罫18本。``xs[0:10]`` が左段、``xs[9:19]`` が右段の列境界。
  ``ys[0]`` は見出し行の上端なので、データ行の境界は ``ys[1:]``。
* 段をまたいだ語の結合を防ぐため、段ごとに ``page.crop`` してから語を取る。
* 読み順は「左段を上から下 → 右段を上から下」。
* 行は「選挙区ヘッダ行」か「候補者行」のいずれか（末尾は空行）。

候補者氏名セルの3行構造
------------------------
    ふりがな          ← 当落のベースラインより上
    届出名            ← 当落と同じベースライン
    (戸籍名)          ← 当落のベースラインより下（届出名が仮名交じりのときだけ現れる）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from .common import (
    PREFECTURES,
    Cell,
    ExtractError,
    normalize_party,
    parse_decimal,
    parse_int,
    read_grid,
    rule_positions,
    squash,
)
from .elections import ElectionConfig

TABLE = "smd_candidates"

N_COLS = 9
N_ROWS = 16
N_VRULES = 19
N_HRULES = 18

COL_RESULT = 0
COL_NAME = 1
COL_AGE = 2
COL_PARTY = 3
COL_STATUS = 4
COL_JOB = 5
COL_VOTES = 6
COL_DUAL = 7
COL_SEKIHAI = 8

_HEADER_RE = re.compile(r"^(?P<pref>.+?)第(?P<no>\d+)区.*?供託物没収点(?P<pt>[\d,]+(?:\.\d+)?)$")
_PARTY_PAREN_RE = re.compile(r"^[（(](?P<inner>.+?)[)）]$")
_KANJI_LINE_RE = re.compile(r"^[（(](?P<inner>.+?)[)）]$")


@dataclass
class District:
    election_id: str
    prefecture: str
    district_no: int
    #: 印字された供託物没収点。有効投票総数のちょうど 1/10。
    deposit_forfeit_point: Decimal
    source_page: int

    @property
    def district_id(self) -> str:
        return f"{self.prefecture}{self.district_no}"

    @property
    def valid_votes_from_point(self) -> Decimal:
        return self.deposit_forfeit_point * 10


@dataclass
class Candidate:
    election_id: str
    prefecture: str
    district_no: int
    order_in_district: int
    elected: bool
    result_mark: str
    name_display: str
    name_kanji: str
    name_kana: str
    age: int
    party_raw: str
    party: str
    party_is_certified: bool
    """「党派」欄が括弧書きでない（＝届出政党等そのもの）か。"""
    status: str
    occupation: str
    votes: Decimal
    dual_candidacy: bool
    sekihai_rate: Decimal | None
    sekihai_excluded: bool
    """惜敗率欄が「×」。重複立候補だが供託物没収点に達せず名簿記載なしとみなされる。"""
    source_page: int

    @property
    def district_id(self) -> str:
        return f"{self.prefecture}{self.district_no}"


def extract(pdf_path: str, cfg: ElectionConfig) -> tuple[list[District], list[Candidate]]:
    districts: list[District] = []
    candidates: list[Candidate] = []
    current: District | None = None
    order = 0

    with pdfplumber.open(pdf_path) as doc:
        for pno in cfg.page_range(TABLE):
            page = doc.pages[pno - 1]
            for row, side in _iter_rows(page, pno):
                joined = squash("".join(c.text for c in row))
                if not joined:
                    continue
                if "供託物没収点" in joined:
                    current = _parse_district_header(joined, cfg, pno)
                    districts.append(current)
                    order = 0
                    continue
                if current is None:
                    raise ExtractError(f"選挙区ヘッダより前に候補者行が現れました (p{pno}, 段{side})")
                order += 1
                candidates.append(_parse_candidate(row, current, order, cfg, pno))

    _sanity(districts, candidates, cfg)
    return districts, candidates


def _iter_rows(page: pdfplumber.page.Page, pno: int):
    xs = rule_positions(page, "v")
    ys = rule_positions(page, "h")
    if len(xs) != N_VRULES or len(ys) != N_HRULES:
        raise ExtractError(
            f"p{pno}: 罫線数が想定と違います (縦{len(xs)}本/期待{N_VRULES}, 横{len(ys)}本/期待{N_HRULES})"
        )
    for side, bounds in enumerate((xs[0:10], xs[9:19])):
        sub = page.crop((bounds[0], 0, bounds[-1], page.height))
        for row in read_grid(sub, bounds, ys[1:]):
            yield row, side


def _parse_district_header(joined: str, cfg: ElectionConfig, pno: int) -> District:
    m = _HEADER_RE.match(joined)
    if not m:
        raise ExtractError(f"p{pno}: 選挙区ヘッダを解釈できません: {joined!r}")
    pref = m.group("pref")
    if pref not in PREFECTURES:
        raise ExtractError(f"p{pno}: 未知の都道府県名 {pref!r} ({joined!r})")
    point = parse_decimal(m.group("pt"), field_name="供託物没収点")
    if point is None:
        raise ExtractError(f"p{pno}: 供託物没収点が空です ({joined!r})")
    return District(
        election_id=cfg.election_id,
        prefecture=pref,
        district_no=int(m.group("no")),
        deposit_forfeit_point=point,
        source_page=pno,
    )


def _parse_candidate(
    row: list[Cell], district: District, order: int, cfg: ElectionConfig, pno: int
) -> Candidate:
    where = f"p{pno} {district.district_id} #{order}"

    result_cell = row[COL_RESULT]
    mark = squash(result_cell.text)
    if mark not in ("当", "落"):
        raise ExtractError(f"{where}: 当落欄が {mark!r} です")
    baseline = result_cell.lines[0][0]

    name_cell = row[COL_NAME]
    display = squash(name_cell.line_at(baseline))
    kana = squash("".join(name_cell.lines_above(baseline)))
    below = squash("".join(name_cell.lines_below(baseline)))
    if not display:
        raise ExtractError(f"{where}: 届出名を特定できません (cell={name_cell.line_texts!r})")
    kanji = ""
    if below:
        km = _KANJI_LINE_RE.match(below)
        if not km:
            raise ExtractError(f"{where}: 戸籍名行の形式が想定外です: {below!r}")
        kanji = km.group("inner")

    age = parse_int(row[COL_AGE].compact, field_name=f"{where} 年齢")
    if age is None or not (18 <= age <= 120):
        raise ExtractError(f"{where}: 年齢が不正です: {row[COL_AGE].compact!r}")

    party_raw = squash(row[COL_PARTY].text)
    pm = _PARTY_PAREN_RE.match(party_raw)
    certified = pm is None
    party = normalize_party(pm.group("inner") if pm else party_raw, cfg.parties)

    status = squash(row[COL_STATUS].text)
    if status not in ("新", "前", "元"):
        raise ExtractError(f"{where}: 新前元別が {status!r} です")

    votes = parse_decimal(row[COL_VOTES].compact, field_name=f"{where} 得票数")
    if votes is None:
        raise ExtractError(f"{where}: 得票数が空です")

    dual_mark = squash(row[COL_DUAL].text)
    if dual_mark not in ("", "重"):
        raise ExtractError(f"{where}: 重複欄が {dual_mark!r} です")
    dual = dual_mark == "重"

    sekihai_raw = squash(row[COL_SEKIHAI].text)
    excluded = sekihai_raw in ("×", "x", "X", "✕")
    sekihai = None if excluded else parse_decimal(sekihai_raw, field_name=f"{where} 惜敗率")
    if not dual and (sekihai is not None or excluded):
        raise ExtractError(f"{where}: 重複でないのに惜敗率 {sekihai_raw!r} が入っています")

    return Candidate(
        election_id=cfg.election_id,
        prefecture=district.prefecture,
        district_no=district.district_no,
        order_in_district=order,
        elected=mark == "当",
        result_mark=mark,
        name_display=display,
        name_kanji=kanji,
        name_kana=kana,
        age=age,
        party_raw=party_raw,
        party=party,
        party_is_certified=certified,
        status=status,
        occupation=squash(row[COL_JOB].text),
        votes=votes,
        dual_candidacy=dual,
        sekihai_rate=sekihai,
        sekihai_excluded=excluded,
        source_page=pno,
    )


def _sanity(districts: list[District], candidates: list[Candidate], cfg: ElectionConfig) -> None:
    """抽出直後に構造の最低限だけ確認する（本検証は src/verify 側）。"""
    if len(districts) != cfg.smd_seats:
        raise ExtractError(f"選挙区数が {len(districts)} 件です（期待 {cfg.smd_seats}）")
    seen = {(d.prefecture, d.district_no) for d in districts}
    if len(seen) != len(districts):
        raise ExtractError("選挙区に重複があります")
    for pref in PREFECTURES:
        nos = sorted(n for p, n in seen if p == pref)
        if nos != list(range(1, len(nos) + 1)):
            raise ExtractError(f"{pref} の区番号が連番ではありません: {nos}")
    if not candidates:
        raise ExtractError("候補者が1件も取れていません")
