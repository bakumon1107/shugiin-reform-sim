"""表3(13) 候補者別得票数（小選挙区）の抽出。

ページ構造
----------
* 1ページ = 2段組み。各段が固定グリッド（列数は回によって9列か10列）。
  第47回・第48回には「性別」列があり10列、第49回以降は9列。
  **列位置は決め打ちせず、見出し行のラベルから役割を引く。**
* 縦罫は「1段あたりの列数＋1」の2倍から共有境界1本を引いた本数。
  左段は ``xs[:n+1]``、右段は ``xs[n:]``。
  ``ys[0]`` は見出し行の上端なので、データ行の境界は ``ys[1:]``。
* 段をまたいだ語の結合を防ぐため、段ごとに ``page.crop`` してから文字を取る。
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
    normalize,
    normalize_party,
    parse_decimal,
    parse_int,
    read_grid,
    rule_positions,
    squash,
)
from .elections import ElectionConfig

TABLE = "smd_candidates"

N_HRULES = 18

#: 見出しラベル → 役割。ラベルは NFKC 正規化＋空白除去した形で照合する。
COLUMN_ROLES: dict[str, str] = {
    "当落": "result",
    "候補者氏名": "name",
    "性別": "gender",
    "年齢": "age",
    "党派": "party",
    "届出政党等": "party",
    "新前元別": "status",
    "職業": "occupation",
    "得票数": "votes",
    "重複": "dual",
}
#: 「惜敗率(%)」のように付記が付くもの
_PREFIX_ROLES: tuple[tuple[str, str], ...] = (("惜敗率", "sekihai"),)

REQUIRED_ROLES = (
    "result",
    "name",
    "age",
    "party",
    "status",
    "occupation",
    "votes",
    "dual",
    "sekihai",
)

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
    gender: str
    """``男`` / ``女``。「性別」列がない回（第49回以降）は空文字。"""
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
            for row, side, cols, images, bounds in _iter_rows(page, pno):
                joined = squash("".join(c.text for c in row))
                if not joined and not images:
                    continue
                if "供託物没収点" in joined:
                    current = _parse_district_header(joined, cfg, pno)
                    districts.append(current)
                    order = 0
                    continue
                if current is None:
                    raise ExtractError(f"選挙区ヘッダより前に候補者行が現れました (p{pno}, 段{side})")
                order += 1
                candidates.append(
                    _parse_candidate(row, cols, images, bounds, current, order, cfg, pno)
                )

    _sanity(districts, candidates, cfg)
    return districts, candidates


def _iter_rows(page: pdfplumber.page.Page, pno: int):
    xs = rule_positions(page, "v")
    ys = rule_positions(page, "h")
    if len(ys) != N_HRULES:
        raise ExtractError(f"p{pno}: 横罫が{len(ys)}本です（期待{N_HRULES}）")
    if len(xs) % 2 == 0:
        raise ExtractError(f"p{pno}: 縦罫が{len(xs)}本です（2段組みなので奇数本のはず）")
    n_cols = (len(xs) - 1) // 2  # 1段あたりの列数
    cols = _column_roles(page, xs, ys, n_cols, pno)
    for side, bounds in enumerate((xs[: n_cols + 1], xs[n_cols:])):
        sub = page.crop((bounds[0], 0, bounds[-1], page.height))
        for r, row in enumerate(read_grid(sub, bounds, ys[1:])):
            yield row, side, cols, _images_in_row(page, bounds, ys[1 + r], ys[2 + r]), bounds


def _images_in_row(
    page: pdfplumber.page.Page, bounds: list[float], top: float, bottom: float
) -> list[dict]:
    """行の矩形に重なる埋め込み画像。

    Word由来のPDFでは、稀な字形が文字ではなく画像として貼り込まれ、
    テキストレイヤーから丸ごと抜け落ちることがある。黙って欠測にしないため検出する。
    """
    return [
        im
        for im in page.images
        if top <= (im["top"] + im["bottom"]) / 2 < bottom
        and bounds[0] <= (im["x0"] + im["x1"]) / 2 < bounds[-1]
    ]


def _column_roles(
    page: pdfplumber.page.Page, xs: list[float], ys: list[float], n_cols: int, pno: int
) -> dict[str, int]:
    """見出し行のラベルから「役割 → 列番号」を作る。

    「性別」列の有無など、列構成が回によって違うので位置は決め打ちしない。
    """
    bounds = xs[: n_cols + 1]
    sub = page.crop((bounds[0], 0, bounds[-1], page.height))
    header = read_grid(sub, bounds, ys[0:2])[0]
    roles: dict[str, int] = {}
    for i, cell in enumerate(header):
        label = normalize(cell.text)
        role = COLUMN_ROLES.get(label)
        if role is None:
            role = next((r for prefix, r in _PREFIX_ROLES if label.startswith(prefix)), None)
        if role is None:
            continue
        if role in roles:
            raise ExtractError(f"p{pno}: 見出し {label!r} の役割 {role} が重複しています")
        roles[role] = i
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        raise ExtractError(
            f"p{pno}: 見出し行から列を特定できません。不足 {missing} / "
            f"読み取れた見出し {[normalize(c.text) for c in header]}"
        )
    return roles


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
    row: list[Cell],
    cols: dict[str, int],
    images: list[dict],
    bounds: list[float],
    district: District,
    order: int,
    cfg: ElectionConfig,
    pno: int,
) -> Candidate:
    where = f"p{pno} {district.district_id} #{order}"

    result_cell = row[cols["result"]]
    mark = squash(result_cell.text)
    if mark not in ("当", "落"):
        raise ExtractError(f"{where}: 当落欄が {mark!r} です")
    baseline = result_cell.lines[0][0]

    name_cell = row[cols["name"]]
    display = squash(name_cell.line_at(baseline))
    kana = squash("".join(name_cell.lines_above(baseline)))
    below = squash("".join(name_cell.lines_below(baseline)))
    kanji = ""
    if below:
        km = _KANJI_LINE_RE.match(below)
        if not km:
            raise ExtractError(f"{where}: 戸籍名行の形式が想定外です: {below!r}")
        kanji = km.group("inner")

    votes = parse_decimal(row[cols["votes"]].compact, field_name=f"{where} 得票数")
    if votes is None:
        raise ExtractError(f"{where}: 得票数が空です")

    if images:
        display, kanji = _apply_name_override(
            images, bounds, cols, district, votes, display, kanji, cfg, where
        )
    if not display:
        raise ExtractError(f"{where}: 届出名を特定できません (cell={name_cell.line_texts!r})")

    age = parse_int(row[cols["age"]].compact, field_name=f"{where} 年齢")
    if age is None or not (18 <= age <= 120):
        raise ExtractError(f"{where}: 年齢が不正です: {row[cols['age']].compact!r}")

    gender = squash(row[cols["gender"]].text) if "gender" in cols else ""
    if gender not in ("", "男", "女"):
        raise ExtractError(f"{where}: 性別が {gender!r} です")

    party_raw = squash(row[cols["party"]].text)
    pm = _PARTY_PAREN_RE.match(party_raw)
    certified = pm is None
    party = normalize_party(pm.group("inner") if pm else party_raw, cfg.parties)

    status = squash(row[cols["status"]].text)
    if status not in ("新", "前", "元"):
        raise ExtractError(f"{where}: 新前元別が {status!r} です")

    dual_mark = squash(row[cols["dual"]].text)
    if dual_mark not in ("", "重"):
        raise ExtractError(f"{where}: 重複欄が {dual_mark!r} です")
    dual = dual_mark == "重"

    sekihai_raw = squash(row[cols["sekihai"]].text)
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
        gender=gender,
        party_raw=party_raw,
        party=party,
        party_is_certified=certified,
        status=status,
        occupation=squash(row[cols["occupation"]].text),
        votes=votes,
        dual_candidacy=dual,
        sekihai_rate=sekihai,
        sekihai_excluded=excluded,
        source_page=pno,
    )


def _apply_name_override(
    images: list[dict],
    bounds: list[float],
    cols: dict[str, int],
    district: District,
    votes,
    display: str,
    kanji: str,
    cfg: ElectionConfig,
    where: str,
) -> tuple[str, str]:
    """画像として貼り込まれた氏名を、設定に登録した目視読み取り値で補う。"""
    left, right = bounds[cols["name"]], bounds[cols["name"] + 1]
    outside = [im for im in images if not (left <= (im["x0"] + im["x1"]) / 2 < right)]
    if outside:
        raise ExtractError(
            f"{where}: 氏名以外の列に画像が埋め込まれています "
            f"(x={[round(im['x0'], 1) for im in outside]})。個別の手当てが必要です。"
        )

    key = (district.prefecture, district.district_no, format(votes, "f"))
    override = cfg.name_overrides.get(key)
    if override is None:
        raise ExtractError(
            f"{where}: 氏名が画像として埋め込まれておりテキストから読めません。"
            f"該当セルを目視で確認し、elections.py の name_overrides に "
            f"{key!r} を追加してください。"
            f"（テキストから読めた分: 届出名={display!r} 戸籍名={kanji!r}）"
        )
    return override.get("display", display), override.get("kanji", kanji)


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
