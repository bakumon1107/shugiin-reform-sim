"""検証済みCSVから、Webシミュレータが読む軽量JSONとゴールデン期待値を書き出す。

このリポジトリの既存モジュール（``extract`` / ``verify``）は読むだけで変更しない。

Webアプリの議席計算エンジンは TypeScript で書くが、正解の源は Python 側にある。
``verify.checks.dhondt`` は第47〜51回の全ブロックで実際の結果を再現できることが
検証済み（検証項目 D2・D3）なので、それを一般化した本モジュールの計算結果を
ゴールデンとして書き出し、TS 側はそれを再現しない限りテストが通らないようにする。

出力:

- ``web/public/data/<election_id>.sim.json``      配信するデータ
- ``web/src/sim/__fixtures__/<election_id>.golden.json``  テスト専用の期待値

使い方::

    python -m export_sim              # 全選挙回
    python -m export_sim r08-02-08    # 1回分
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import elections
from extract.common import PR_BLOCKS, PREF_TO_BLOCK, PREFECTURES, name_key
from extract.csvio import dec, flag, num, read_rows
from extract.elections import ElectionConfig

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "csv"
WEB_DATA_DIR = ROOT / "web" / "public" / "data"
GOLDEN_DIR = ROOT / "web" / "src" / "sim" / "__fixtures__"

#: 得票数は小数第3位まで（同姓同名の按分票）。整数で持ち回るための倍率。
SCALE = 1000


class ExportError(Exception):
    """出力を続けると誤ったデータを配信することになる不整合。"""


def scaled(value: Decimal | None) -> int | None:
    """``Decimal`` を1000倍の整数にする。割り切れなければ例外。"""
    if value is None:
        return None
    shifted = value * SCALE
    if shifted != shifted.to_integral_value():
        raise ExportError(f"得票が小数第3位を超えている: {value}")
    return int(shifted)


# ---------------------------------------------------------------------------
# 制度パラメータ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Params:
    """シミュレータの制度パラメータ。TS 側の ``SimParams`` と1対1に対応する。"""

    #: 比例代表の議席配分方式。``dhondt`` は ÷1,2,3…、``sainteLague`` は ÷1,3,5…、
    #: ``modifiedSainteLague`` は第1除数だけを ``first_divisor_tenths`` にした ÷1.4,3,5…
    divisor_method: str = "dhondt"
    #: 修正サンラグの第1除数を10倍した整数（14 なら 1.4）。他の方式では使わない。
    first_divisor_tenths: int = 14
    #: 比例定数の増減。自民案は −45（176→131）。小選挙区の定数は動かさない。
    pr_seat_delta: int = 0
    #: 重複立候補者が比例名簿から当選するのに必要な、小選挙区での最低得票率。
    #: 現行は有効投票総数の 1/10（＝供託物没収点）。自民案は 1/6。
    dual_min_vote_share: Fraction = Fraction(1, 10)
    #: 重複立候補者に課す惜敗率の下限（％）。``None`` なら課さない。自民案は 30 か 50。
    dual_min_sekihai_rate: Decimal | None = None
    #: 名簿が尽きたときの扱い。``reallocate`` は現行（他党に回す）、
    #: ``vacant`` は自民案（欠員にして他党に回さない）。
    list_exhaustion: str = "reallocate"
    #: 小選挙区と比例代表の連動のさせ方。
    #: ``parallel``（並立制・現行）は互いに独立。
    #: ``renyo``（連用制）は比例の除数を「その党の小選挙区当選者数 + 1」から始める。
    #: ``heiyo``（併用制）は比例得票で総議席を決め、小選挙区当選者をその枠に充てる。
    tier_linkage: str = "parallel"
    #: 併用制で超過議席が出たときの扱い。``truncate`` は総定数を固定して商の低い方から
    #: 打ち切る、``expand`` は超過分だけ定数が増えるのを認める（ドイツの旧制度型）。
    #:
    #: ``truncate`` を選ぶと、併用制は連用制と数学的に同一の制度になる。比例議席の
    #: 候補（各党の除数のうち小選挙区当選者数を超えるもの）から上位を取る操作が
    #: 両者で一致するため。両者が分岐するのは ``expand`` のときだけ。
    heiyo_overhang: str = "truncate"

    def label(self) -> str:
        return f"{self.divisor_method}/Δ{self.pr_seat_delta}/{self.dual_min_vote_share}"


BASELINE = Params()

#: 自民案の惜敗率下限は「30%や50%を例示」（鈴木馨祐座長試案）。既定は30%とし、
#: 50%版も別プリセットとして出す。
LDP = Params(
    divisor_method="sainteLague",
    pr_seat_delta=-45,
    dual_min_vote_share=Fraction(1, 6),
    dual_min_sekihai_rate=Decimal(30),
    list_exhaustion="vacant",
)

#: チームみらい案は小選挙区比例代表並立制を踏襲し、定数・比例復活・重複立候補の
#: ルールは変えない。抜本改革案の RCV は選好順序データが存在しないため試算不能で、
#: 議席配分に効くのはサンラグ方式のみ。結果として抜本案と修正案は同一になる。
MIRAI = Params(divisor_method="sainteLague")

#: 修正サンラグ。どの党の案でもなく、比較のための参考ケース。第1除数だけを大きくして
#: 小政党が1議席目を取る条件を厳しくする方式で、北欧などで使われている値は1.4。
MODIFIED = Params(divisor_method="modifiedSainteLague", first_divisor_tenths=14)

PRESETS: dict[str, Params] = {
    "baseline": BASELINE,
    "ldp": LDP,
    "ldp_sekihai50": replace(LDP, dual_min_sekihai_rate=Decimal(50)),
    "mirai": MIRAI,
    "modified_sainte_lague": MODIFIED,
    # 第1除数を動かしたときに TS 側とずれないことを確かめるための追加ケース
    "modified_sainte_lague_10": replace(MODIFIED, first_divisor_tenths=10),
    "modified_sainte_lague_21": replace(MODIFIED, first_divisor_tenths=21),
    "renyo": replace(BASELINE, tier_linkage="renyo"),
    "heiyo": replace(BASELINE, tier_linkage="heiyo"),
    "heiyo_expand": replace(BASELINE, tier_linkage="heiyo", heiyo_overhang="expand"),
    # 連動方式が他のパラメータと組み合わさっても TS とずれないことを確かめる
    "renyo_sainte_lague": replace(BASELINE, tier_linkage="renyo", divisor_method="sainteLague"),
    "heiyo_vacant_45": replace(
        BASELINE, tier_linkage="heiyo", list_exhaustion="vacant", pr_seat_delta=-45
    ),
}


# ---------------------------------------------------------------------------
# 名簿登載者
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    """比例名簿の登載者1人。重複立候補なら小選挙区側の得票を持つ。"""

    block: str
    party: str
    list_rank: int
    name: str
    dual: bool
    #: 実際の結果（ゴールデン照合用）
    actual_elected: bool
    actual_elected_order: int | None
    #: 以下は重複立候補者のみ
    district_id: str | None = None
    smd_won: bool = False
    smd_votes: int | None = None
    district_valid_votes: int | None = None
    district_top_votes: int | None = None
    printed_sekihai_rate: Decimal | None = None
    printed_excluded: bool = False

    def sekihai_rate(self) -> Decimal | None:
        """惜敗率（％）。分母はその選挙区の最多得票で、区割りを変えない限り不変。"""
        if not self.dual or not self.smd_votes or not self.district_top_votes:
            return None
        return Decimal(self.smd_votes) / Decimal(self.district_top_votes) * 100

    def eligible(self, params: Params) -> bool:
        """このパラメータのもとで比例の当選人になれるか。

        得票率要件・惜敗率要件は**重複立候補者にのみ**適用される。単独の名簿
        登載者には小選挙区の得票が存在しないので、これらで落としてはいけない
        （公職選挙法95条の2第6項は重複立候補者の規定）。
        """
        if not self.dual:
            return True
        if self.smd_won:
            return False
        # 得票率要件: smd_votes / valid_votes >= share。割り算を避けて交差比較する。
        share = params.dual_min_vote_share
        if self.smd_votes * share.denominator < self.district_valid_votes * share.numerator:
            return False
        if params.dual_min_sekihai_rate is not None:
            rate = self.sekihai_rate()
            if rate is None or rate < params.dual_min_sekihai_rate:
                return False
        return True


# ---------------------------------------------------------------------------
# 配分アルゴリズム
# ---------------------------------------------------------------------------


#: 除数を整数で扱うための倍率。修正サンラグは第1除数を 0.1 刻みで動かせるように
#: するので、この方式だけ全ての除数を10倍して持つ（1.4, 3, 5, 7 → 14, 30, 50, 70）。
#: 商の比較は同じブロック内で同じ倍率どうしなので、倍率は結果に影響しない。
DIVISOR_SCALE = {"dhondt": 1, "sainteLague": 1, "modifiedSainteLague": 10}


def divisor_of(method: str, seats_won: int, first_divisor_tenths: int = 14) -> int:
    """獲得済み議席数から次の除数を返す（``DIVISOR_SCALE`` 倍した整数）。

    修正サンラグは第1除数だけを大きくして、得票の少ない党が1議席目を取る条件を
    厳しくする方式。北欧などで使われている値は1.4だが、ここでは0.1刻みで動かせる
    ようにしてある（1.0にすると純粋なサンラグ式と同じになる）。
    """
    if method == "dhondt":
        return seats_won + 1
    if method == "sainteLague":
        return 2 * seats_won + 1
    if method == "modifiedSainteLague":
        return first_divisor_tenths if seats_won == 0 else 10 * (2 * seats_won + 1)
    raise ExportError(f"未知の配分方式: {method}")


def _pick(votes: dict[str, int], used: dict[str, int], params: Params,
          allowed: set[str], head: dict[str, int] | None = None) -> tuple[str, int, bool]:
    """次の1議席を取る党派を選ぶ。商の比較は割り算せず交差乗算で行う。

    ``head`` は除数の起点。連用制では各党の小選挙区当選者数を渡すので、
    小選挙区で勝った党ほど比例が回りにくくなる。
    """
    method, tenths = params.divisor_method, params.first_divisor_tenths
    head = head or {}
    best: str | None = None
    tie = False
    for party in sorted(allowed):
        div = divisor_of(method, head.get(party, 0) + used[party], tenths)
        if best is None:
            best, best_div = party, div
            continue
        # votes[party]/div  vs  votes[best]/best_div
        left = votes[party] * best_div
        right = votes[best] * div
        if left > right:
            best, best_div, tie = party, div, False
        elif left == right:
            tie = True
            # 同値は得票数の多い方、なお同じなら党派名順（checks.py と同じ決め方）
            if (-votes[party], party) < (-votes[best], best):
                best, best_div = party, div
    return best, divisor_of(method, head.get(best, 0) + used[best], tenths), tie


def allocate_heiyo(
    votes: dict[str, int],
    pr_seats: int,
    smd_by_party: dict[str, int],
    smd_total: int,
    capacity: dict[str, int],
    params: Params,
) -> tuple[list[dict], bool]:
    """併用制（総定数固定）でブロックの比例議席を配る。

    ブロックの総議席を比例得票で順に配り、各党への割り当てがその党の小選挙区
    当選者数を超えた分だけを比例議席として取り出す。小選挙区で勝ちすぎた党
    （超過議席）には比例が回らない。

    比例に名簿を出していない当選者（無所属など）はその議席をそのまま得るので、
    比例配分の対象となる総議席から先に差し引く。

    取り出した比例議席が定数を超える場合（＝どこかの党に超過議席が出た場合）は、
    商の低い方から打ち切る。これで総定数は常に固定される。
    """
    independent = sum(n for p, n in smd_by_party.items() if p not in votes)
    pool = smd_total + pr_seats - independent
    if pool <= 0:
        return [], False

    used: dict[str, int] = {p: 0 for p in votes}   # 総議席（小選挙区＋比例）の獲得数
    pr_won: dict[str, int] = {p: 0 for p in votes}
    order: list[dict] = []
    tie_seen = False

    for _ in range(pool):
        if params.heiyo_overhang == "truncate" and len(order) == pr_seats:
            break  # 比例定数に達した。超過分はここで打ち切る。
        allowed = set(votes)
        if params.list_exhaustion == "reallocate":
            # 比例で埋める段階に入っていて名簿が尽きた党は、以後の対象から外す
            allowed = {
                p for p in votes
                if used[p] < smd_by_party.get(p, 0) or pr_won[p] < capacity.get(p, 0)
            }
        if not allowed:
            break
        party, div, tie = _pick(votes, used, params, allowed)
        tie_seen = tie_seen or tie
        used[party] += 1
        if used[party] > smd_by_party.get(party, 0):
            # この議席は小選挙区当選者では埋まらないので、比例名簿から埋める
            pr_won[party] += 1
            order.append(
                {"party": party, "divisor": div,
                 "filled": pr_won[party] <= capacity.get(party, 0)}
            )
    return order, tie_seen


def allocate(
    votes: dict[str, int],
    seats: int,
    capacity: dict[str, int],
    params: Params,
    head_start: dict[str, int] | None = None,
) -> tuple[list[dict], bool]:
    """ブロックの議席を配分し、獲得順の一覧を返す。

    ``head_start`` は各党の除数の起点。連用制では小選挙区当選者数を渡すので、
    小選挙区で勝った党ほど比例が回りにくくなる。

    ``reallocate``（現行）は名簿を使い切った党派を対象から外し、残りの議席を
    他党に回す（公職選挙法95条の2第4項）。``verify.checks.dhondt`` と同じ挙動。

    ``vacant``（自民案④）は、まず名簿の制約を無視して純粋に商の順で配分し、
    自党の名簿人数を超えて回ってきた議席を欠員として確定させる。他党には回さない。
    """
    head = head_start or {}
    used: dict[str, int] = {p: 0 for p in votes}
    order: list[dict] = []
    tie_seen = False

    if params.list_exhaustion == "vacant":
        for _ in range(seats):
            party, div, tie = _pick(votes, used, params, set(votes), head)
            tie_seen = tie_seen or tie
            used[party] += 1
            filled = used[party] <= capacity.get(party, 0)
            order.append({"party": party, "divisor": div, "filled": filled})
        return order, tie_seen

    if params.list_exhaustion != "reallocate":
        raise ExportError(f"未知の名簿枯渇ポリシー: {params.list_exhaustion}")

    for _ in range(seats):
        allowed = {p for p in votes if used[p] < capacity.get(p, 0)}
        if not allowed:
            break  # 全党の名簿が尽きた。現行法でもこの議席は埋まらない。
        party, div, tie = _pick(votes, used, params, allowed, head)
        tie_seen = tie_seen or tie
        used[party] += 1
        order.append({"party": party, "divisor": div, "filled": True})
    return order, tie_seen


def adams(populations: dict[str, int], total: int) -> dict[str, int]:
    """アダムズ方式で ``total`` 議席を配分する。

    アダムズ方式は ``seats = ceil(pop / d)`` となる除数 d を探す方式だが、除数列
    0,1,2,3… の最大平均法としても等価に書ける。逐次配分の形にしておくと、除数の
    二分探索と違って同値のときの挙動が決まり、合計も必ず ``total`` に一致する。
    第1議席の除数は0（＝商が無限大）なので、各ブロックに必ず1議席が行く。

    商の比較は割り算せず交差乗算で行う。同値なら人口の多い方、なお同じなら
    ブロック名の順。
    """
    if total < len(populations):
        raise ExportError(f"議席数({total})がブロック数({len(populations)})を下回る")

    seats = {b: 1 for b in populations}
    for _ in range(total - len(populations)):
        best: str | None = None
        for b in sorted(populations):
            if best is None:
                best = b
                continue
            # populations[b]/seats[b] vs populations[best]/seats[best]
            left = populations[b] * seats[best]
            right = populations[best] * seats[b]
            if left > right or (left == right and populations[b] > populations[best]):
                best = b
        seats[best] += 1
    return seats


# ---------------------------------------------------------------------------
# シミュレーション
# ---------------------------------------------------------------------------


def simulate(payload: dict, params: Params) -> dict:
    """1回分のデータに制度パラメータを当てはめ、比例代表の議席を解く。

    小選挙区の結果は動かさない。第1版が扱う3案はいずれも区割りにも小選挙区の
    投票方式にも手を入れないため（チームみらい抜本案の RCV は選好順序データが
    存在しないので試算対象外）。
    """
    blocks_in = payload["blocks"]
    total_pr = payload["meta"]["pr_seats"] + params.pr_seat_delta
    if total_pr < len(blocks_in):
        raise ExportError(f"比例定数({total_pr})がブロック数を下回る")

    if params.pr_seat_delta == 0:
        seats_by_block = {b["block"]: b["seats"] for b in blocks_in}
    else:
        seats_by_block = adams({b["block"]: b["electors"] for b in blocks_in}, total_pr)

    blocks_out = []
    ties: list[str] = []
    for b in blocks_in:
        by_party: dict[str, list[Entry]] = defaultdict(list)
        for e in b["_entries"]:
            by_party[e.party].append(e)

        votes = {p["party"]: p["votes"] for p in b["parties"]}
        capacity = {
            party: sum(1 for e in by_party.get(party, []) if e.eligible(params))
            for party in votes
        }

        smd_by_party = payload["smd"]["by_block"].get(b["block"], {})
        smd_total = sum(smd_by_party.values())
        pr_seats = seats_by_block[b["block"]]

        if params.tier_linkage == "parallel":
            order, tie = allocate(votes, pr_seats, capacity, params)
        elif params.tier_linkage == "renyo":
            # 除数の起点をその党の小選挙区当選者数にする
            order, tie = allocate(votes, pr_seats, capacity, params, smd_by_party)
        elif params.tier_linkage == "heiyo":
            order, tie = allocate_heiyo(
                votes, pr_seats, smd_by_party, smd_total, capacity, params
            )
        else:
            raise ExportError(f"未知の連動方式: {params.tier_linkage}")
        if tie:
            ties.append(b["block"])

        # 名簿順位順（同一順位内は惜敗率降順）に、当選できる者から詰めていく
        won = defaultdict(int)
        for seat in order:
            if seat["filled"]:
                won[seat["party"]] += 1
        winners: dict[str, list[str]] = {}
        for party, n in won.items():
            pool = sorted(
                (e for e in by_party.get(party, []) if e.eligible(params)),
                key=lambda e: (e.list_rank, -(e.sekihai_rate() or Decimal(0))),
            )
            winners[party] = [e.name for e in pool[:n]]
            if len(winners[party]) != n:
                raise ExportError(f"{b['block']}/{party}: 当選者を{n}人埋められない")

        blocks_out.append(
            {
                "block": b["block"],
                "seats": seats_by_block[b["block"]],
                "order": order,
                "vacancies": sum(1 for s in order if not s["filled"]),
                "seats_by_party": dict(won),
                "capacity": capacity,
                "winners": winners,
            }
        )

    pr_by_party: dict[str, int] = defaultdict(int)
    for b in blocks_out:
        for party, n in b["seats_by_party"].items():
            pr_by_party[party] += n
    total_by_party = defaultdict(int, payload["smd"]["seats_by_party"])
    for party, n in pr_by_party.items():
        total_by_party[party] += n

    return {
        "params": {
            "divisor_method": params.divisor_method,
            "first_divisor_tenths": params.first_divisor_tenths,
            "pr_seat_delta": params.pr_seat_delta,
            "dual_min_vote_share": str(params.dual_min_vote_share),
            "dual_min_sekihai_rate": (
                None if params.dual_min_sekihai_rate is None
                else str(params.dual_min_sekihai_rate)
            ),
            "list_exhaustion": params.list_exhaustion,
            "tier_linkage": params.tier_linkage,
            "heiyo_overhang": params.heiyo_overhang,
        },
        "blocks": blocks_out,
        "pr_seats_by_party": dict(pr_by_party),
        "total_seats_by_party": dict(total_by_party),
        "vacancies": sum(b["vacancies"] for b in blocks_out),
        "tie_blocks": ties,
    }


# ---------------------------------------------------------------------------
# CSV の読み込み
# ---------------------------------------------------------------------------


def match_duals(cands: list[dict], pr_entries: list[dict]) -> list[tuple[dict, dict]]:
    """重複立候補者について 表(13) の候補者行と 表(11) の名簿行を対応づける。

    ``verify.checks`` の C10 と同じ手順。表(13) は届出名、表(11) は戸籍名を印字する
    ことがあり（しもの幸助／下野幸助）、異体字セレクタや小書き仮名の揺れもあるので
    ``name_key`` で正規化し、表(13) 側は届出名・戸籍名の両方をキーにする。
    残りはブロック×党派ごとに、両側1人ずつなら同一人物とみなす。
    """
    duals = [c for c in cands if flag(c["dual_candidacy"])]
    pr_duals = [r for r in pr_entries if flag(r["dual_candidacy"])]

    pr_by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pr_duals:
        pr_by_name[(r["party"], name_key(r["name"]))].append(r)

    pairs: list[tuple[dict, dict]] = []
    used: set[int] = set()
    unmatched: list[dict] = []
    for c in duals:
        keys = [(c["party"], name_key(c["name_display"]))]
        if c["name_kanji"]:
            keys.append((c["party"], name_key(c["name_kanji"])))
        hit = next((r for k in keys for r in pr_by_name.get(k, []) if id(r) not in used), None)
        if hit is None:
            unmatched.append(c)
        else:
            used.add(id(hit))
            pairs.append((c, hit))

    residual_smd: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in unmatched:
        residual_smd[(PREF_TO_BLOCK[c["prefecture"]], c["party"])].append(c)
    residual_pr: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pr_duals:
        if id(r) not in used:
            residual_pr[(r["block"], r["party"])].append(r)

    for key, left in residual_smd.items():
        right = residual_pr.get(key, [])
        if len(left) == 1 and len(right) == 1:
            pairs.append((left[0], right[0]))
        else:
            raise ExportError(
                f"重複立候補の突合に失敗: {key} 表13={[c['name_display'] for c in left]} "
                f"表11={[r['name'] for r in right]}"
            )

    if len(pairs) != len(duals):
        raise ExportError(f"重複立候補の突合数が合わない: {len(pairs)} != {len(duals)}")
    return pairs


def load(cfg: ElectionConfig) -> dict:
    """CSV を読み、シミュレータが必要とする形に組み立てる。"""
    src = CSV_DIR / cfg.election_id
    t = {p.stem: read_rows(p) for p in src.glob("*.csv")}

    # --- 小選挙区 -----------------------------------------------------------
    cands = t["smd_candidates"]
    by_district: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cands:
        by_district[(c["prefecture"], int(c["district_no"]))].append(c)

    districts: dict[str, dict] = {}
    smd_seats_by_party: dict[str, int] = defaultdict(int)
    smd_by_block: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in t["smd_districts"]:
        key = (d["prefecture"], int(d["district_no"]))
        rows = by_district[key]
        district_id = f"{d['prefecture']}{d['district_no']}"
        top = max(dec(c["votes"]) for c in rows)
        winners = [c for c in rows if flag(c["elected"])]
        if len(winners) != 1:
            raise ExportError(f"{district_id}: 当選者が{len(winners)}人")
        smd_seats_by_party[winners[0]["party"]] += 1
        smd_by_block[PREF_TO_BLOCK[d["prefecture"]]][winners[0]["party"]] += 1
        districts[district_id] = {
            "district_id": district_id,
            "prefecture": d["prefecture"],
            "district_no": int(d["district_no"]),
            "block": PREF_TO_BLOCK[d["prefecture"]],
            # 有効投票総数 = 供託物没収点 × 10（検証項目 B1）
            "valid_votes": scaled(dec(d["deposit_forfeit_point"]) * 10),
            "top_votes": scaled(top),
            "winner": winners[0]["name_display"],
            "winner_party": winners[0]["party"],
        }

    # --- 比例代表 -----------------------------------------------------------
    pr_entries = t["pr_list_entries"]
    pair_by_entry: dict[int, dict] = {id(r): c for c, r in match_duals(cands, pr_entries)}

    entries_by_block: dict[str, list[Entry]] = defaultdict(list)
    for r in pr_entries:
        dual = flag(r["dual_candidacy"])
        entry = Entry(
            block=r["block"],
            party=r["party"],
            list_rank=int(r["list_rank"]),
            name=r["name"],
            dual=dual,
            actual_elected=flag(r["elected_pr"]),
            actual_elected_order=num(r["elected_order"]),
        )
        if dual:
            c = pair_by_entry[id(r)]
            district_id = f"{c['prefecture']}{c['district_no']}"
            entry.district_id = district_id
            entry.smd_won = flag(c["elected"])
            entry.smd_votes = scaled(dec(c["votes"]))
            entry.district_valid_votes = districts[district_id]["valid_votes"]
            entry.district_top_votes = districts[district_id]["top_votes"]
            entry.printed_sekihai_rate = dec(c["sekihai_rate"])
            entry.printed_excluded = flag(c["sekihai_excluded"])
        entries_by_block[r["block"]].append(entry)

    # 得票は表(10)から取る（verify.checks の D2・D3 と同じ源）
    votes_by_block: dict[str, dict[str, int]] = defaultdict(dict)
    for r in t["party_votes_by_block"]:
        if r["is_total_row"] == "false":
            votes_by_block[r["block"]][r["party"]] = scaled(dec(r["votes"]))

    actual = {(r["block"], r["party"]): r for r in t["pr_party_blocks"]}

    electors_by_pref = {
        r["prefecture"]: int(dec(r["electors_total"]))
        for r in t["electorate"]
        if r["tier"] == "smd" and r["scope"] == "all" and r["prefecture"] in PREFECTURES
    }

    blocks = []
    for name, prefs in PR_BLOCKS.items():
        votes = votes_by_block[name]
        head = {p: actual.get((name, p)) for p in votes}
        missing = [p for p, h in head.items() if h is None]
        if missing:
            raise ExportError(f"{name}: 表(11)に無い党派 {missing}")
        for party, h in head.items():
            if scaled(dec(h["votes"])) != votes[party]:
                raise ExportError(f"{name}/{party}: 表(10)と表(11)で得票が違う")
        blocks.append(
            {
                "block": name,
                "prefectures": list(prefs),
                "seats": sum(num(h["seats"]) or 0 for h in head.values()),
                "electors": sum(electors_by_pref[p] for p in prefs),
                "parties": [
                    {
                        "party": party,
                        "votes": votes[party],
                        "actual_seats": num(head[party]["seats"]) or 0,
                    }
                    for party in sorted(votes, key=lambda p: -votes[p])
                ],
                "_entries": entries_by_block[name],
            }
        )

    return {
        "meta": {
            "election_id": cfg.election_id,
            "ordinal": cfg.ordinal,
            "election_date": cfg.election_date,
            "source_url": cfg.source_url,
            "source_sha256": cfg.sha256,
            "smd_seats": cfg.smd_seats,
            "pr_seats": cfg.pr_seats,
            "total_seats": cfg.total_seats,
        },
        "smd": {
            "seats_by_party": dict(smd_seats_by_party),
            # 連用制・併用制はブロックごとの小選挙区当選者数を使う
            "by_block": {b: dict(v) for b, v in smd_by_block.items()},
            "districts": list(districts.values()),
        },
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# 自己検証
# ---------------------------------------------------------------------------


def self_check(payload: dict) -> list[str]:
    """出力する前に、このモジュールの計算が実際の結果を再現できるか確かめる。"""
    problems: list[str] = []

    # 1. 現行制度パラメータでの再計算 = 実際の議席配分・当選者
    result = simulate(payload, BASELINE)
    by_block = {b["block"]: b for b in result["blocks"]}
    for b in payload["blocks"]:
        got = by_block[b["block"]]["seats_by_party"]
        for p in b["parties"]:
            if got.get(p["party"], 0) != p["actual_seats"]:
                problems.append(
                    f"{b['block']}/{p['party']}: 再計算={got.get(p['party'], 0)} "
                    f"実際={p['actual_seats']}"
                )
        actual_winners = sorted(
            (e for e in b["_entries"] if e.actual_elected),
            key=lambda e: e.actual_elected_order or 0,
        )
        calc_winners = {n for names in by_block[b["block"]]["winners"].values() for n in names}
        if {e.name for e in actual_winners} != calc_winners:
            problems.append(
                f"{b['block']}: 比例当選者が一致しない "
                f"実際のみ={sorted({e.name for e in actual_winners} - calc_winners)} "
                f"再計算のみ={sorted(calc_winners - {e.name for e in actual_winners})}"
            )
    if result["vacancies"]:
        problems.append(f"現行制度の再計算で欠員が出ている: {result['vacancies']}")

    # 2. 1/10 要件の再計算 = 原典の「×」印（sekihai_excluded 列）
    for b in payload["blocks"]:
        for e in b["_entries"]:
            if not e.dual:
                continue
            recomputed = e.smd_votes * 10 < e.district_valid_votes
            if recomputed != e.printed_excluded:
                problems.append(
                    f"{b['block']}/{e.name}: 1/10要件の再計算={recomputed} 原典={e.printed_excluded}"
                )
            # 3. 惜敗率の再計算 = 原典の印字
            if e.printed_sekihai_rate is not None:
                calc = e.sekihai_rate().quantize(Decimal("0.001"))
                if abs(calc - e.printed_sekihai_rate) > Decimal("0.001"):
                    problems.append(
                        f"{b['block']}/{e.name}: 惜敗率 再計算={calc} 原典={e.printed_sekihai_rate}"
                    )

    # 4. 議席の総数
    smd = sum(payload["smd"]["seats_by_party"].values())
    if smd != payload["meta"]["smd_seats"]:
        problems.append(f"小選挙区議席: {smd} != {payload['meta']['smd_seats']}")
    pr = sum(result["pr_seats_by_party"].values())
    if pr != payload["meta"]["pr_seats"]:
        problems.append(f"比例議席: {pr} != {payload['meta']['pr_seats']}")

    return problems


# ---------------------------------------------------------------------------
# 書き出し
# ---------------------------------------------------------------------------


def web_payload(payload: dict) -> dict:
    """配信用。得票はすべて1000倍の整数で、フロントに文字列を渡さない。"""
    return {
        "meta": payload["meta"],
        "voteScale": SCALE,
        "smd": {
            "seatsByParty": payload["smd"]["seats_by_party"],
            "byBlock": payload["smd"]["by_block"],
            "districts": [
                {
                    "id": d["district_id"],
                    "pref": d["prefecture"],
                    "no": d["district_no"],
                    "block": d["block"],
                    "validVotes": d["valid_votes"],
                    "topVotes": d["top_votes"],
                    "winner": d["winner"],
                    "winnerParty": d["winner_party"],
                }
                for d in payload["smd"]["districts"]
            ],
        },
        "blocks": [
            {
                "block": b["block"],
                "prefectures": b["prefectures"],
                "seats": b["seats"],
                "electors": b["electors"],
                "parties": [
                    {
                        "party": p["party"],
                        "votes": p["votes"],
                        "actualSeats": p["actual_seats"],
                        "list": [
                            {
                                "rank": e.list_rank,
                                "name": e.name,
                                "dual": e.dual,
                                "actualElected": e.actual_elected,
                                "actualElectedOrder": e.actual_elected_order,
                                "districtId": e.district_id,
                                "smdWon": e.smd_won,
                                "smdVotes": e.smd_votes,
                                "districtValidVotes": e.district_valid_votes,
                                "districtTopVotes": e.district_top_votes,
                            }
                            for e in sorted(
                                (x for x in b["_entries"] if x.party == p["party"]),
                                key=lambda e: (e.list_rank, -(e.sekihai_rate() or Decimal(0))),
                            )
                        ],
                    }
                    for p in b["parties"]
                ],
            }
            for b in payload["blocks"]
        ],
    }


def golden_payload(payload: dict) -> dict:
    """TS エンジンが再現すべき期待値。"""
    return {
        "election_id": payload["meta"]["election_id"],
        "presets": {name: simulate(payload, params) for name, params in PRESETS.items()},
    }


def export(cfg: ElectionConfig) -> int:
    payload = load(cfg)
    problems = self_check(payload)
    for p in problems[:20]:
        print(f"[FAIL] {cfg.election_id}: {p}")
    if problems:
        print(f"[FAIL] {cfg.election_id}: 計{len(problems)}件")
        return 1

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    web = WEB_DATA_DIR / f"{cfg.election_id}.sim.json"
    web.write_text(
        json.dumps(web_payload(payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    golden = GOLDEN_DIR / f"{cfg.election_id}.golden.json"
    golden.write_text(
        json.dumps(golden_payload(payload), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    ldp = simulate(payload, LDP)
    print(
        f"[OK] {cfg.election_id}: {web.stat().st_size / 1024:.0f} KB — "
        f"現行制度の再計算が実結果と完全一致。"
        f"自民案は比例{payload['meta']['pr_seats'] + LDP.pr_seat_delta}議席・"
        f"欠員{ldp['vacancies']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", help="省略すると全選挙回")
    args = parser.parse_args(argv)

    ids = [args.election_id] if args.election_id else list(elections.ELECTIONS)
    status = max(export(elections.get(i)) for i in ids)
    if status:
        return status

    # 選挙回の一覧。フロント側に選挙回をハードコードしないためのもの。
    index = [
        {
            "id": cfg.election_id,
            "ordinal": cfg.ordinal,
            "date": cfg.election_date,
            "smdSeats": cfg.smd_seats,
            "prSeats": cfg.pr_seats,
            "totalSeats": cfg.total_seats,
            "sourceUrl": cfg.source_url,
        }
        for cfg in sorted(elections.ELECTIONS.values(), key=lambda c: -c.ordinal)
    ]
    (WEB_DATA_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[OK] index.json — {len(index)}回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
