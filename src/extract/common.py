"""総務省「衆議院議員総選挙結果調」PDF から表を読み出すための共通処理。

設計方針
--------
* 数値は必ず ``Decimal``。按分票で小数が出るため float を使うと合計一致検証が壊れる。
* 表の列境界は ``page.edges`` から取る。罫線を ``lines`` で持つPDF（第51回）と
  ``rects`` で持つPDF（第50回）があり、``edges`` はその両方を含む唯一の共通経路。
* セルはテキストを1本の文字列に潰さず、物理行（``top`` でクラスタした単位）を保持する。
  候補者氏名セルは「ふりがな行 / 届出名行 / (戸籍名) 行」の3行構造を持つため。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Sequence

import pdfplumber

# --------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------

PREFECTURES: tuple[str, ...] = (
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)

PREF_INDEX: dict[str, int] = {p: i + 1 for i, p in enumerate(PREFECTURES)}

#: 比例代表ブロック名 -> 構成都道府県
PR_BLOCKS: dict[str, tuple[str, ...]] = {
    "北海道": ("北海道",),
    "東北": ("青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"),
    "北関東": ("茨城県", "栃木県", "群馬県", "埼玉県"),
    "南関東": ("千葉県", "神奈川県", "山梨県"),
    "東京都": ("東京都",),
    "北陸信越": ("新潟県", "富山県", "石川県", "福井県", "長野県"),
    "東海": ("岐阜県", "静岡県", "愛知県", "三重県"),
    "近畿": ("滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"),
    "中国": ("鳥取県", "島根県", "岡山県", "広島県", "山口県"),
    "四国": ("徳島県", "香川県", "愛媛県", "高知県"),
    "九州": ("福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"),
}

PREF_TO_BLOCK: dict[str, str] = {
    pref: block for block, prefs in PR_BLOCKS.items() for pref in prefs
}

STATUS_NEW = "新"
STATUS_INCUMBENT = "前"
STATUS_FORMER = "元"
STATUSES = (STATUS_NEW, STATUS_INCUMBENT, STATUS_FORMER)


class ExtractError(RuntimeError):
    """抽出中に想定外の構造・値に遭遇したことを示す。黙って握りつぶさない。"""


# --------------------------------------------------------------------------
# テキスト・数値の正規化
# --------------------------------------------------------------------------

_SPACES = re.compile(r"[\s　 ]+")
#: セルが「値なし」を意味するときに現れる表記
_NULL_TOKENS = {"", "-", "‐", "－", "―", "ー", "△", "‐", "−"}


def squash(text: str) -> str:
    """全角スペースを含むあらゆる空白を除去する。"""
    return _SPACES.sub("", text or "")


def normalize(text: str) -> str:
    """NFKC 正規化したうえで空白を除去する（比較・突合用のキー）。"""
    return squash(unicodedata.normalize("NFKC", text or ""))


#: 小書き仮名 → 並字。氏名の表記ゆれ（三ッ林 / 三ツ林）を吸収するため、突合キーでのみ使う。
_SMALL_KANA = str.maketrans(
    "ァィゥェォヵヶッャュョヮぁぃぅぇぉっゃゅょゎ",
    "アイウエオカケツヤユヨワあいうえおつやゆよわ",
)


def _strip_variation_selectors(text: str) -> str:
    """異体字セレクタ（IVS）を取り除く。

    同じ人物が表によって ``大塚拓`` と ``大塚󠄆拓``（U+E0106 付き）で印字されるため、
    そのままでは突合できない。
    """
    return "".join(
        ch
        for ch in text
        if not (0xFE00 <= ord(ch) <= 0xFE0F or 0xE0100 <= ord(ch) <= 0xE01EF)
    )


def name_key(text: str) -> str:
    """氏名の突合キー。IVS・空白・小書き仮名の揺れを吸収する。

    表(13) と表(11) では同一人物が異体字セレクタの有無や小書き仮名の違いで
    別文字列になることがある。表記そのものは各CSVに原文のまま残し、
    突合のときだけこのキーを使う。
    """
    return squash(unicodedata.normalize("NFKC", _strip_variation_selectors(text or ""))).translate(
        _SMALL_KANA
    )


def parse_decimal(text: str | None, *, field_name: str = "") -> Decimal | None:
    """``"1,234.567"`` → ``Decimal("1234.567")``。空・``-`` は ``None``。

    数値として解釈できない文字列は握りつぶさず ``ExtractError`` を送出する。
    """
    if text is None:
        return None
    raw = squash(unicodedata.normalize("NFKC", text))
    if raw in _NULL_TOKENS:
        return None
    # 括弧付きは内数（重複立候補者数など）。呼び出し側で剥がす想定だがここでも許容。
    negative = raw.startswith("△") or raw.startswith("▲")
    raw = raw.lstrip("△▲")
    raw = raw.replace(",", "").replace("%", "").replace("人", "").replace("票", "")
    if raw in _NULL_TOKENS:
        return None
    if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
        raise ExtractError(f"数値として解釈できません: {field_name!r} = {text!r}")
    value = Decimal(raw)
    return -value if negative else value


def parse_int(text: str | None, *, field_name: str = "") -> int | None:
    value = parse_decimal(text, field_name=field_name)
    if value is None:
        return None
    if value != value.to_integral_value():
        raise ExtractError(f"整数のはずが小数です: {field_name!r} = {text!r}")
    return int(value)


def dec_str(value: Decimal | None) -> str:
    """CSV 出力用。``None`` は空文字、それ以外は指数表記を避けた10進表記。"""
    if value is None:
        return ""
    return format(value.normalize(), "f") if value == value.to_integral_value() else format(value, "f")


# --------------------------------------------------------------------------
# 罫線からのグリッド検出
# --------------------------------------------------------------------------


def cluster(values: Iterable[float], tol: float) -> list[float]:
    """近接する座標値をまとめて代表値（クラスタ平均）の昇順リストにする。"""
    ordered = sorted(values)
    if not ordered:
        return []
    groups: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def rule_positions(page: pdfplumber.page.Page, orientation: str, tol: float = 2.0) -> list[float]:
    """罫線位置を返す。``orientation`` は ``"v"``（縦罫→x）か ``"h"``（横罫→y）。

    ``page.lines`` と ``page.rects`` のどちらで罫線が表現されていても
    ``page.edges`` には現れるため、常に ``edges`` を見る。
    """
    if orientation not in ("v", "h"):
        raise ValueError(orientation)
    key = "x0" if orientation == "v" else "top"
    return cluster((e[key] for e in page.edges if e["orientation"] == orientation), tol)


@dataclass
class Cell:
    """表の1セル。物理行の並びを保持する。"""

    lines: list[tuple[float, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        """全行を連結した素のテキスト（空白除去なし）。"""
        return "".join(t for _, t in self.lines)

    @property
    def line_texts(self) -> list[str]:
        return [t for _, t in self.lines]

    @property
    def compact(self) -> str:
        """空白を除去して連結したテキスト。"""
        return squash(self.text)

    def line_at(self, top: float, tol: float = 3.0) -> str:
        """指定ベースライン上の行テキスト（無ければ空文字）。"""
        for t, s in self.lines:
            if abs(t - top) <= tol:
                return s
        return ""

    def lines_above(self, top: float, tol: float = 3.0) -> list[str]:
        return [s for t, s in self.lines if t < top - tol]

    def lines_below(self, top: float, tol: float = 3.0) -> list[str]:
        return [s for t, s in self.lines if t > top + tol]

    def __bool__(self) -> bool:
        return bool(self.compact)


def _visible_chars(page: pdfplumber.page.Page) -> list[dict]:
    """空白文字を除いた文字のリスト。

    語（``extract_words``）ではなく文字を単位にするのは、隣接する列の値が
    語として結合されてしまう事故（例: 順位「1」＋党派名「自由民主党」→「1自由民主党」）を
    構造的に防ぐため。文字は必ずどこか1つのセルに属する。
    """
    return [c for c in page.chars if (c.get("text") or "").strip()]


def _cell_from_chars(chars: list[dict], line_tol: float) -> Cell:
    """文字群を ``top`` でクラスタして物理行に復元する。"""
    if not chars:
        return Cell()
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    groups: list[tuple[float, list[dict]]] = []
    for ch in chars:
        if groups and abs(ch["top"] - groups[-1][0]) <= line_tol:
            groups[-1][1].append(ch)
        else:
            groups.append((ch["top"], [ch]))
    out = Cell()
    for top, group in groups:
        group.sort(key=lambda c: c["x0"])
        out.lines.append((top, "".join(c["text"] for c in group)))
    return out


def _bin_row(chars: list[dict], x_bounds: Sequence[float], line_tol: float) -> list[Cell]:
    row: list[Cell] = []
    for c in range(len(x_bounds) - 1):
        left, right = x_bounds[c], x_bounds[c + 1]
        row.append(
            _cell_from_chars(
                [ch for ch in chars if left <= (ch["x0"] + ch["x1"]) / 2 < right], line_tol
            )
        )
    return row


def read_grid(
    page: pdfplumber.page.Page,
    x_bounds: Sequence[float],
    y_bounds: Sequence[float],
    *,
    line_tol: float = 3.0,
    edge_slack: float = 1.0,
) -> list[list[Cell]]:
    """``x_bounds`` × ``y_bounds`` で切ったグリッドに文字を割り付ける。

    横罫がデータ行ごとに引かれている表（表13など）向け。
    """
    chars = _visible_chars(page)
    rows: list[list[Cell]] = []
    for r in range(len(y_bounds) - 1):
        top, bottom = y_bounds[r] - edge_slack, y_bounds[r + 1] - edge_slack
        in_row = [ch for ch in chars if top <= ch["top"] < bottom]
        rows.append(_bin_row(in_row, x_bounds, line_tol))
    return rows


def read_rows_by_baseline(
    page: pdfplumber.page.Page,
    x_bounds: Sequence[float],
    y_top: float,
    y_bottom: float,
    *,
    line_tol: float = 3.5,
) -> list[list[Cell]]:
    """横罫がデータ行ごとに引かれていない表を、文字のベースラインで行に切る。

    都道府県別の表は47行あるのに横罫は外枠と見出しだけ、という構造が多い。
    列境界は縦罫から取れるので、行だけをベースラインのクラスタで復元する。
    """
    chars = [
        ch
        for ch in _visible_chars(page)
        if y_top <= ch["top"] < y_bottom and x_bounds[0] <= (ch["x0"] + ch["x1"]) / 2 < x_bounds[-1]
    ]
    if not chars:
        return []
    chars.sort(key=lambda c: (c["top"], c["x0"]))
    bands: list[list[dict]] = [[chars[0]]]
    for ch in chars[1:]:
        if ch["top"] - bands[-1][-1]["top"] <= line_tol:
            bands[-1].append(ch)
        else:
            bands.append([ch])
    return [_bin_row(band, x_bounds, line_tol) for band in bands]


def locate_pref_column(rows: list[list[Cell]]) -> int:
    """都道府県名が並ぶ列の位置を実測で突き止める。

    先頭に通し番号列があるかどうかなど、行見出しまわりの列構成は回によって違う
    （第50回の表(8)には「1 北海道」のように番号列がある）。
    列位置を決め打ちせず、都道府県名が最も多く現れる列を採用する。
    """
    scores: dict[int, int] = {}
    for row in rows:
        for i, cell in enumerate(row):
            if squash(cell.text) in PREFECTURES:
                scores[i] = scores.get(i, 0) + 1
    if not scores:
        raise ExtractError("都道府県名の列を特定できません")
    return max(scores, key=lambda i: scores[i])


def require_shape(
    page: pdfplumber.page.Page, pno: int, n_v: int, n_h: int, *, table: str
) -> tuple[list[float], list[float]]:
    """縦罫・横罫の本数が想定どおりであることを確かめて位置を返す。"""
    xs = rule_positions(page, "v")
    ys = rule_positions(page, "h")
    if len(xs) != n_v or len(ys) != n_h:
        raise ExtractError(
            f"{table} p{pno}: 罫線数が想定と違います "
            f"(縦{len(xs)}/期待{n_v}, 横{len(ys)}/期待{n_h})"
        )
    return xs, ys


def page_text(page: pdfplumber.page.Page) -> str:
    return page.extract_text(layout=True) or ""


# --------------------------------------------------------------------------
# 党派名
# --------------------------------------------------------------------------

#: 「党派名」欄の見出しに使われる語。回によって揺れる
#: （第51回=党派名／第50回=政党等名・届出政党等）。長い順に並べる。
PARTY_COLUMN_LABELS: tuple[str, ...] = ("届出政党等", "政党等名", "党派名", "党派")


def strip_party_label(text: str) -> str | None:
    """「党派名自由民主党」のような見出し＋値の連結から、値の部分だけを取り出す。

    見出しで始まっていなければ ``None``。
    """
    for label in PARTY_COLUMN_LABELS:
        if text.startswith(label):
            return text[len(label) :]
    return None


#: 表ごとの表記ゆれを吸収する。値は正規形。
PARTY_ALIASES: dict[str, str] = {
    "無所属": "無所属",
    "（無所属）": "無所属",
    "(無所属)": "無所属",
    "諸派": "諸派",
    "得票総数": "__TOTAL__",
    "合計": "__TOTAL__",
    "計": "__TOTAL__",
}


#: 党派名に付く脚注記号（「立憲民主党※１」のように印字される回がある）
_FOOTNOTE_MARK_RE = re.compile(r"[※＊*][0-9０-９]*$")


def normalize_party(raw: str, known: set[str] | None = None) -> str:
    """党派名を正規化する。``known`` を渡した場合、未知の党派名で例外を送出する。"""
    name = _FOOTNOTE_MARK_RE.sub("", squash(raw))
    name = PARTY_ALIASES.get(name, name)
    if known is not None and name not in known and name != "__TOTAL__":
        raise ExtractError(
            f"未知の党派名です: {raw!r} → {name!r}。"
            "elections 設定の parties に追加するか、表記ゆれを PARTY_ALIASES に登録してください。"
        )
    return name
