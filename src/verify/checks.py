"""抽出結果の検証。

すべて **CSV を読み直して** 検証する。抽出時のオブジェクトではなく成果物そのものを
対象にすることで、CSV への書き出し・読み戻しまで含めて確かめる。

検証は4系統:

A. 表内の恒等式（男+女=計、投票総数=有効+無効、都道府県の合計=計 …）
B. 選挙区単位の厳密検証（供託物没収点×10=Σ得票、惜敗率の再計算 …）
C. 独立に印字された表どうしの突合（Σ候補者得票=党派別得票数 …）
D. ドント式の独立再計算
E. 構造アサーション
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extract.common import PR_BLOCKS, PREF_TO_BLOCK, PREFECTURES, name_key
from extract.csvio import dec, flag, num, read_rows
from extract.elections import ElectionConfig

ZERO = Decimal(0)
PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


@dataclass
class Result:
    check_id: str
    category: str
    title: str
    status: str
    subject_count: int = 0
    fail_count: int = 0
    detail: str = ""
    samples: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != FAIL


class Table(dict):
    """CSV1本を ``list[dict[str, str]]`` として持つだけの薄い入れ物。"""


def load(csv_dir: Path) -> dict[str, list[dict[str, str]]]:
    data: dict[str, list[dict[str, str]]] = {}
    for path in sorted(csv_dir.glob("*.csv")):
        data[path.stem] = read_rows(path)
    if not data:
        raise SystemExit(f"CSV が見つかりません: {csv_dir}")
    return data


# ---------------------------------------------------------------------------
# 補助
# ---------------------------------------------------------------------------


def aggregate_party(party: str, certified: bool) -> str:
    """候補者の党派を、集計表（表4・表6）の列に合わせて畳む。

    確認団体はそのまま。「党派」欄が括弧書きの候補者のうち ``無所属`` は無所属、
    それ以外の政治団体は集計表では ``諸派`` にまとめられている。
    """
    if certified:
        return party
    return "無所属" if party == "無所属" else "諸派"


def _mk(check_id: str, category: str, title: str, bad: list[str], total: int, note: str = "") -> Result:
    return Result(
        check_id=check_id,
        category=category,
        title=title,
        status=PASS if not bad else FAIL,
        subject_count=total,
        fail_count=len(bad),
        detail=note,
        samples=bad[:8],
    )


def _close(a: Decimal | None, b: Decimal | None, tol: Decimal) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tol


def _sum(values: Iterable[Decimal | None]) -> Decimal:
    return sum((v for v in values if v is not None), ZERO)


# ---------------------------------------------------------------------------
# A. 表内の恒等式
# ---------------------------------------------------------------------------


def check_a(data, cfg) -> list[Result]:
    out: list[Result] = []

    bad: list[str] = []
    n = 0
    for r in data["electorate"]:
        for label, keys in (
            ("有権者", ("electors_male", "electors_female", "electors_total")),
            ("投票者", ("voters_male", "voters_female", "voters_total")),
            ("棄権者", ("abstainers_male", "abstainers_female", "abstainers_total")),
        ):
            m, f, t = (dec(r[k]) for k in keys)
            n += 1
            if _sum([m, f]) != (t or ZERO):
                bad.append(f"{r['tier']}/{r['scope']}/{r['prefecture']} {label}: {m}+{f}≠{t}")
    out.append(_mk("A1", "A", "有権者数・投票者数・棄権者数の 男+女=計", bad, n))

    bad, n = [], 0
    for r in data["electorate"]:
        e, v, a = dec(r["electors_total"]), dec(r["voters_total"]), dec(r["abstainers_total"])
        n += 1
        if (v or ZERO) + (a or ZERO) != (e or ZERO):
            bad.append(f"{r['tier']}/{r['scope']}/{r['prefecture']}: {v}+{a}≠{e}")
    out.append(_mk("A2", "A", "有権者数 = 投票者数 + 棄権者数", bad, n))

    bad, n = [], 0
    for r in data["ballots_smd_by_pref"] + data["ballots_pr_by_block_pref"]:
        total, valid, invalid = (dec(r[k]) for k in ("total_ballots", "valid_votes", "invalid_votes"))
        n += 1
        if valid + invalid != total:
            bad.append(f"{r['tier']}/{r['block']}/{r['prefecture']}: {valid}+{invalid}≠{total}")
        rate = (invalid / total * 100).quantize(Decimal("0.01"))
        if abs(rate - dec(r["invalid_rate_pct"])) > Decimal("0.01"):
            bad.append(f"{r['tier']}/{r['prefecture']} 無効率: 印字{r['invalid_rate_pct']} 計算{rate}")
    out.append(_mk("A3", "A", "投票総数 = 有効 + 無効、無効投票率の再計算", bad, n))

    bad, n = [], 0
    turnout = {(r["tier"], r["scope"], r["block"], r["prefecture"]): r for r in data["turnout"]}
    for r in data["electorate"]:
        key = (r["tier"], r["scope"], r["block"], r["prefecture"])
        t = turnout.get(key)
        if t is None:
            continue
        n += 1
        e, v = dec(r["electors_total"]), dec(r["voters_total"])
        if not e:
            continue
        calc = (v / e * 100).quantize(Decimal("0.01"))
        printed = dec(t["rate_total"])
        if printed is not None and abs(calc - printed) > Decimal("0.01"):
            bad.append(f"{key} 投票率: 印字{printed} 計算{calc}")
    out.append(_mk("A4", "A", "投票率 = 投票者数 / 有権者数 × 100", bad, n))

    bad, n = [], 0
    for r in data["turnout"]:
        for m, f, t in (("rate_male", "rate_female", "rate_total"),):
            pass
        a, b, d = dec(r["rate_total"]), dec(r["prev_rate_total"]), dec(r["diff_total"])
        if a is None or b is None or d is None:
            continue
        n += 1
        if abs((a - b) - d) > Decimal("0.01"):
            bad.append(f"{r['tier']}/{r['scope']}/{r['prefecture']}: {a}-{b}≠{d}")
    out.append(_mk("A5", "A", "投票率の比較 (A)-(B) の再計算", bad, n))

    # 都道府県行の合計 == 合計行
    bad, n = [], 0
    for tier in ("smd", "pr"):
        for scope in ("all", "overseas"):
            rows = [r for r in data["electorate"] if r["tier"] == tier and r["scope"] == scope]
            prefs = [r for r in rows if r["prefecture"] in PREFECTURES]
            grand = [r for r in rows if r["prefecture"] == "合計"]
            if not grand or len(prefs) != 47:
                bad.append(f"{tier}/{scope}: 都道府県 {len(prefs)} 行 / 合計行 {len(grand)} 件")
                continue
            n += 1
            for key in ("electors_total", "voters_total", "abstainers_total"):
                s = _sum(dec(r[key]) for r in prefs)
                g = dec(grand[0][key])
                if s != g:
                    bad.append(f"{tier}/{scope}/{key}: Σ都道府県={s} 合計行={g}")
    out.append(_mk("A6", "A", "有権者数等: 都道府県の総和 = 合計行", bad, n))

    # 表(7) ブロック内の都道府県合計 == ブロック計行
    bad, n = [], 0
    rows = data["party_votes_by_block_pref"]
    per = defaultdict(Decimal)
    printed = {}
    for r in rows:
        key = (r["block"], r["party"])
        if r["prefecture"] == "計":
            printed[key] = dec(r["votes"])
        elif r["prefecture"] in PREFECTURES:
            per[key] += dec(r["votes"]) or ZERO
    blank = 0
    for key, want in printed.items():
        n += 1
        got = per.get(key, ZERO)
        if want is None:
            # そのブロックに名簿を出していない党派は都道府県欄も計欄も空欄
            blank += 1
            if got != ZERO:
                bad.append(f"{key}: 計行が空欄なのに Σ都道府県={got}")
        elif got != want:
            bad.append(f"{key}: Σ都道府県={got} 計行={want}")
    out.append(
        _mk("A7", "A", "表(7): ブロック内の都道府県総和 = ブロック計行", bad, n,
            f"うち {blank} 件は当該ブロックに名簿がなく空欄（0であることを確認）")
    )

    # 表(6) の 男+女=計
    bad, n = [], 0
    for r in data["party_votes_by_pref_smd"]:
        m, f, t = dec(r["votes_male"]), dec(r["votes_female"]), dec(r["votes_total"])
        n += 1
        if _sum([m, f]) != (t or ZERO):
            bad.append(f"{r['prefecture']}/{r['party']}: {m}+{f}≠{t}")
    out.append(_mk("A8", "A", "表(6) 都道府県別党派別得票数の 男+女=計", bad, n))

    return out


# ---------------------------------------------------------------------------
# B. 選挙区単位の厳密検証（表13）
# ---------------------------------------------------------------------------


def check_b(data, cfg) -> list[Result]:
    out: list[Result] = []
    districts = data["smd_districts"]
    cands = data["smd_candidates"]
    by_d: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_d[f"{c['prefecture']}{c['district_no']}"].append(c)

    # B1: 供託物没収点 × 10 = 有効投票総数
    exact, approx, bad = 0, [], []
    for d in districts:
        did = f"{d['prefecture']}{d['district_no']}"
        rows = by_d[did]
        total = _sum(dec(c["votes"]) for c in rows)
        want = dec(d["deposit_forfeit_point"]) * 10
        has_frac = any(dec(c["votes"]) != dec(c["votes"]).to_integral_value() for c in rows)
        diff = want - total
        if diff == ZERO:
            exact += 1
        elif has_frac and ZERO < diff < Decimal(1):
            # 按分票は小数第3位までで切り捨てられるため、合計は有効投票総数をわずかに下回る
            approx.append(f"{did}: 差 {diff}（按分票あり）")
        else:
            bad.append(f"{did}: Σ得票={total} 没収点×10={want} 差={diff} 按分={has_frac}")
    out.append(
        Result(
            "B1",
            "B",
            "各選挙区: Σ候補者得票 = 供託物没収点 × 10",
            PASS if not bad else FAIL,
            len(districts),
            len(bad),
            f"完全一致 {exact} 区 / 按分票による端数差(0<差<1) {len(approx)} 区: "
            + ", ".join(a.split(":")[0] for a in approx),
            bad[:8],
        )
    )

    # B2: 当選者は各区1名かつ最多得票
    bad = []
    for d in districts:
        did = f"{d['prefecture']}{d['district_no']}"
        rows = by_d[did]
        winners = [c for c in rows if flag(c["elected"])]
        top = max(dec(c["votes"]) for c in rows)
        if len(winners) != 1:
            bad.append(f"{did}: 当選者 {len(winners)} 名")
        elif dec(winners[0]["votes"]) != top:
            bad.append(f"{did}: 当選者の得票 {winners[0]['votes']} が最多 {top} でない")
    out.append(_mk("B2", "B", "各選挙区の当選者は1名かつ最多得票", bad, len(districts)))

    # B3: 惜敗率の再計算
    bad, n = [], 0
    for d in districts:
        did = f"{d['prefecture']}{d['district_no']}"
        rows = by_d[did]
        top = max(dec(c["votes"]) for c in rows)
        for c in rows:
            printed = dec(c["sekihai_rate"])
            if printed is None:
                continue
            n += 1
            calc = (dec(c["votes"]) / top * 100).quantize(Decimal("0.001"))
            if abs(calc - printed) > Decimal("0.001"):
                bad.append(f"{did} {c['name_display']}: 印字{printed} 計算{calc}")
    out.append(_mk("B3", "B", "惜敗率 = 得票 ÷ 区内最多得票 × 100 の再計算", bad, n))

    # B4: 惜敗率「×」の条件
    points = {f"{d['prefecture']}{d['district_no']}": dec(d["deposit_forfeit_point"]) for d in districts}
    bad = []
    for c in cands:
        did = f"{c['prefecture']}{c['district_no']}"
        expect = flag(c["dual_candidacy"]) and dec(c["votes"]) < points[did]
        if expect != flag(c["sekihai_excluded"]):
            bad.append(f"{did} {c['name_display']}: ×={c['sekihai_excluded']} 期待={expect}")
    out.append(_mk("B4", "B", "惜敗率「×」⇔ 重複立候補 かつ 得票 < 供託物没収点", bad, len(cands)))

    # B5: 選挙区の構成
    bad = []
    if len(districts) != cfg.smd_seats:
        bad.append(f"選挙区数 {len(districts)}（期待 {cfg.smd_seats}）")
    by_pref = defaultdict(list)
    for d in districts:
        by_pref[d["prefecture"]].append(int(d["district_no"]))
    if len(by_pref) != 47:
        bad.append(f"都道府県数 {len(by_pref)}（期待 47）")
    seats_printed = {
        r["prefecture"]: num(r["seats"])
        for r in data["candidacy_by_pref_party"]
        if r["prefecture"] in PREFECTURES
    }
    for pref, nos in by_pref.items():
        if sorted(nos) != list(range(1, len(nos) + 1)):
            bad.append(f"{pref}: 区番号が連番でない {sorted(nos)}")
        if seats_printed.get(pref) != len(nos):
            bad.append(f"{pref}: 区数 {len(nos)} ≠ 印字定数 {seats_printed.get(pref)}")
    out.append(_mk("B5", "B", "289選挙区・区番号の連番・都道府県別定数の一致", bad, len(districts)))

    return out


# ---------------------------------------------------------------------------
# C. 表をまたいだ突合
# ---------------------------------------------------------------------------


def check_c(data, cfg) -> list[Result]:
    out: list[Result] = []
    cands = data["smd_candidates"]

    def agg(c) -> str:
        return aggregate_party(c["party"], flag(c["party_is_certified"]))

    # C1: Σ表13 得票（党派別） == 表(4) 今回
    got = defaultdict(Decimal)
    for c in cands:
        got[agg(c)] += dec(c["votes"])
    # 表(4) の「合計」列は全党派の総和。Σ表13 の総和と突き合わせる。
    got["__TOTAL__"] = _sum(v for k, v in got.items() if k != "__TOTAL__")
    want = {
        r["party"]: dec(r["votes"])
        for r in data["party_votes_smd_total"]
        if r["period"] == "current" and r["votes"]
    }
    bad = [
        f"{p}: 表13={got.get(p)} 表4={want.get(p)}"
        for p in sorted(set(got) | set(want))
        if got.get(p) != want.get(p)
    ]
    out.append(
        _mk("C1", "C", "Σ表(13)候補者得票（党派別） = 表(4)党派別得票数（小選挙区）", bad, len(set(got) | set(want)),
            f"全国合計 {sum(got.values())}")
    )

    # C2: Σ表13 得票（都道府県×党派） == 表(6) 計列
    got2 = defaultdict(Decimal)
    for c in cands:
        got2[(c["prefecture"], agg(c))] += dec(c["votes"])
    want2 = {
        (r["prefecture"], r["party"]): dec(r["votes_total"])
        for r in data["party_votes_by_pref_smd"]
        if r["prefecture"] in PREFECTURES and r["party"] != "__TOTAL__"
    }
    keys = {k for k in set(got2) | set(want2)}
    bad = [f"{k}: 表13={got2.get(k)} 表6={want2.get(k)}" for k in sorted(keys) if (got2.get(k) or ZERO) != (want2.get(k) or ZERO)]
    out.append(_mk("C2", "C", "Σ表(13)得票（都道府県×党派） = 表(6)の計列", bad, len(keys)))

    # C3: Σ表13 得票（都道府県） == 表(8) 有効投票数
    got3 = defaultdict(Decimal)
    for c in cands:
        got3[c["prefecture"]] += dec(c["votes"])
    want3 = {r["prefecture"]: dec(r["valid_votes"]) for r in data["ballots_smd_by_pref"]}
    bad = []
    for pref in PREFECTURES:
        # 按分票の切り捨て分だけ Σ得票 が有効投票数を下回りうる（差は1票未満）
        diff = (want3.get(pref) or ZERO) - got3.get(pref, ZERO)
        if not (ZERO <= diff < Decimal(1)):
            bad.append(f"{pref}: 表13={got3.get(pref)} 表8有効={want3.get(pref)} 差={diff}")
    out.append(
        _mk("C3", "C", "Σ表(13)得票（都道府県） = 表(8)有効投票数（按分端数 <1票 を許容）", bad, 47,
            f"全国差 {(_sum(want3.get(p) for p in PREFECTURES)) - _sum(got3.get(p) for p in PREFECTURES)} 票")
    )

    # C4: Σ表(7)（都道府県） == 表(10)
    got4 = defaultdict(Decimal)
    for r in data["party_votes_by_block_pref"]:
        if r["prefecture"] in PREFECTURES:
            got4[(r["block"], r["party"])] += dec(r["votes"]) or ZERO
    want4 = {
        (r["block"], r["party"]): dec(r["votes"])
        for r in data["party_votes_by_block"]
        if r["is_total_row"] == "false"
    }
    # 表(7) には「合計」列（全党派の和）が含まれるので、表(10) の得票総数行と対応づける
    total4 = {
        r["block"]: dec(r["votes"]) for r in data["party_votes_by_block"] if r["is_total_row"] == "true"
    }
    for block, v in total4.items():
        want4[(block, "__TOTAL__")] = v
    keys = set(got4) | set(want4)
    bad = []
    for k in sorted(keys):
        if k in want4:
            if got4.get(k) != want4[k]:
                bad.append(f"{k}: 表7={got4.get(k)} 表10={want4[k]}")
        elif got4[k] != ZERO:
            # 表(7) は全ブロック共通の党派列を持つため、そのブロックに候補者を
            # 立てていない党派は空欄になる。表(10) には行自体が現れない。
            bad.append(f"{k}: 表10に無いのに表7が {got4[k]} 票")
    out.append(
        _mk("C4", "C", "Σ表(7)（ブロック内都道府県） = 表(10)ブロック別党派別得票数", bad, len(keys),
            f"表(10)に行が無い（＝そのブロックに名簿を出していない）組合せ {len(keys) - len(want4)} 件は0票であることを確認")
    )

    # C5: Σ表(10)（党派） == 表(5)
    got5 = defaultdict(Decimal)
    for r in data["party_votes_by_block"]:
        if r["is_total_row"] == "false":
            got5[r["party"]] += dec(r["votes"])
    got5["__TOTAL__"] = _sum(v for k, v in got5.items() if k != "__TOTAL__")
    want5 = {
        r["party"]: dec(r["votes"])
        for r in data["party_votes_pr_total"]
        if r["period"] == "current" and r["votes"]
    }
    keys = set(got5) | set(want5)
    bad = [f"{p}: 表10={got5.get(p)} 表5={want5.get(p)}" for p in sorted(keys) if got5.get(p) != want5.get(p)]
    out.append(_mk("C5", "C", "Σ表(10)（党派別） = 表(5)党派別得票数（比例代表）", bad, len(keys)))

    # C6: 表(10) 得票総数 == 表(9) ブロック計の有効投票数
    want6 = {}
    for r in data["ballots_pr_by_block_pref"]:
        if r["prefecture"] == "計":
            want6[r["block"]] = dec(r["valid_votes"])
        elif r["prefecture"] in PREFECTURES and r["block"] in ("北海道", "東京都"):
            want6.setdefault(r["block"], dec(r["valid_votes"]))
    # 比例代表も按分票が出るため、Σ得票は有効投票数を1票未満だけ下回りうる
    bad = []
    for b in PR_BLOCKS:
        got, want = total4.get(b), want6.get(b)
        if got is None or want is None:
            bad.append(f"{b}: 表10得票総数={got} 表9有効投票数={want}")
        elif not (ZERO <= want - got < Decimal(1)):
            bad.append(f"{b}: 表10得票総数={got} 表9有効投票数={want} 差={want - got}")
    out.append(
        _mk("C6", "C", "表(10)の得票総数 = 表(9)ブロック計の有効投票数（按分端数 <1票 を許容）",
            bad, len(PR_BLOCKS))
    )

    # C7: 表13 当選者数（都道府県） == 表3(2) 都道府県別当選人数
    got7 = defaultdict(int)
    for c in cands:
        if flag(c["elected"]):
            got7[c["prefecture"]] += 1
    # 表3(2) の「合計」列と突き合わせる。党派列の構成は回によって違う
    # （第50回は最終ページが「政党等所属 / 無所属 / 小計」という別建て）ので、
    # 都道府県ごとの総数は合計列を正とし、党派別は存在する列だけ突き合わせる。
    want7 = {
        r["prefecture"]: num(r["total"]) or 0
        for r in data["winners_by_pref_party"]
        if r["prefecture"] in PREFECTURES and r["party"] == "__TOTAL__"
    }
    bad = [
        f"{p}: 表13={got7.get(p, 0)} 表3(2)合計列={want7.get(p)}"
        for p in PREFECTURES
        if got7.get(p, 0) != want7.get(p)
    ]
    out.append(_mk("C7", "C", "表(13)の当選者数（都道府県別） = 表3(2)の合計列", bad, 47,
                   f"合計 {sum(got7.values())} 人"))

    # C7b: 党派別（表3(2)に列がある党派のみ）
    got7b = defaultdict(int)
    for c in cands:
        if flag(c["elected"]):
            got7b[(c["prefecture"], agg(c))] += 1
    want7b = {
        (r["prefecture"], r["party"]): num(r["total"]) or 0
        for r in data["winners_by_pref_party"]
        if r["prefecture"] in PREFECTURES and r["party"] != "__TOTAL__"
    }
    bad = [
        f"{k}: 表13={got7b.get(k, 0)} 表3(2)={v}" for k, v in want7b.items() if got7b.get(k, 0) != v
    ]
    out.append(_mk("C7b", "C", "表(13)の当選者数（都道府県×党派） = 表3(2)の党派列", bad, len(want7b)))

    # C8: 議席数の総計
    bad = []
    smd_elected = sum(1 for c in cands if flag(c["elected"]))
    pr_seats = sum(num(r["seats"]) or 0 for r in data["pr_party_blocks"])
    if smd_elected != cfg.smd_seats:
        bad.append(f"小選挙区当選者 {smd_elected}（期待 {cfg.smd_seats}）")
    if pr_seats != cfg.pr_seats:
        bad.append(f"比例当選者 {pr_seats}（期待 {cfg.pr_seats}）")
    pr_elected_rows = sum(1 for r in data["pr_list_entries"] if flag(r["elected_pr"]))
    if pr_elected_rows != cfg.pr_seats:
        bad.append(f"比例名簿の当選印 {pr_elected_rows}（期待 {cfg.pr_seats}）")
    out.append(_mk("C8", "C", f"議席数 小選挙区{cfg.smd_seats} + 比例{cfg.pr_seats} = {cfg.total_seats}", bad, 3,
                   f"小選挙区 {smd_elected} / 比例 {pr_seats} / 合計 {smd_elected + pr_seats}"))

    # C9: 表(11) の党派別得票数 == 表(10)
    bad = []
    for r in data["pr_party_blocks"]:
        want = want4.get((r["block"], r["party"]))
        if dec(r["votes"]) != want:
            bad.append(f"{r['block']}/{r['party']}: 表11={r['votes']} 表10={want}")
    out.append(_mk("C9", "C", "表(11)の党派別得票数 = 表(10)", bad, len(data["pr_party_blocks"])))

    # C10: 重複立候補の突合（表13 ⇄ 表11）
    #
    # 表(13) は「届出名」、表(11) は「戸籍名」を印字することがある（しもの幸助 / 下野幸助）。
    # 異体字セレクタや小書き仮名の揺れもあるため、name_key で正規化し、
    # 表(13) 側は届出名・戸籍名の両方をキーにする。
    duals = [c for c in cands if flag(c["dual_candidacy"])]
    pr_duals = [r for r in data["pr_list_entries"] if flag(r["dual_candidacy"])]

    pr_by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pr_duals:
        pr_by_name[(r["party"], name_key(r["name"]))].append(r)

    pairs: list[tuple[dict, dict]] = []
    used_pr: set[int] = set()
    unmatched_smd: list[dict] = []

    for c in duals:
        keys = [(c["party"], name_key(c["name_display"]))]
        if c["name_kanji"]:
            keys.append((c["party"], name_key(c["name_kanji"])))
        hit = next(
            (r for k in keys for r in pr_by_name.get(k, []) if id(r) not in used_pr), None
        )
        if hit is None:
            unmatched_smd.append(c)
        else:
            used_pr.add(id(hit))
            pairs.append((c, hit))

    # 残りをブロック×党派ごとに突き合わせる。両側に1人ずつしか残っていなければ
    # その2件は同一人物とみなせる（表記が食い違う例:
    #   表13「やなぎや東三楼」/「稲葉昭義」 ⇄ 表11「柳家東三楼」（高座名）
    #   表13「赤沢りょうせい」 ⇄ 表11「赤澤りょうせい」（旧字体）
    #   表13「たなはし泰文」 ⇄ 表11「たはなし泰文」（かなの誤植））
    # 対応づけたあとで当落・惜敗率が一致するかは通常どおり検証するので、
    # 誤った対応づけがあれば下の突合で FAIL になる。
    residual_smd: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in unmatched_smd:
        residual_smd[(PREF_TO_BLOCK[c["prefecture"]], c["party"])].append(c)
    residual_pr: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pr_duals:
        if id(r) not in used_pr:
            residual_pr[(r["block"], r["party"])].append(r)

    by_residual: list[str] = []
    still_unmatched: list[dict] = []
    for key, group in residual_smd.items():
        others = residual_pr.get(key, [])
        if len(group) == 1 and len(others) == 1:
            used_pr.add(id(others[0]))
            pairs.append((group[0], others[0]))
            by_residual.append(f"{group[0]['name_display']} ⇄ {others[0]['name']}")
        else:
            still_unmatched.extend(group)

    bad = [
        f"表13 {c['prefecture']}{c['district_no']} {c['name_display']}({c['party']}) が表11に無い"
        for c in still_unmatched
    ]
    bad += [
        f"表11 {r['block']} {r['name']}({r['party']}) が表13の重複立候補に無い"
        for r in pr_duals
        if id(r) not in used_pr
    ]
    for c, m in pairs:
        want_mark = "当" if flag(c["elected"]) else "落"
        if m["smd_result"] != want_mark:
            bad.append(f"{c['name_display']}: 小選挙区当落 表13={want_mark} 表11={m['smd_result']}")
        if dec(m["sekihai_rate"]) != dec(c["sekihai_rate"]) or flag(m["sekihai_excluded"]) != flag(
            c["sekihai_excluded"]
        ):
            bad.append(
                f"{c['name_display']} 惜敗率: 表13={c['sekihai_rate']}/×{c['sekihai_excluded']} "
                f"表11={m['sekihai_rate']}/×{m['sekihai_excluded']}"
            )

    note = (
        f"氏名一致 {len(pairs) - len(by_residual)} 件"
        "（異体字セレクタ・小書き仮名を正規化し、届出名／戸籍名の両方で突合）"
    )
    if by_residual:
        note += (
            f" / ブロック×党派の残り1対1で対応づけ {len(by_residual)} 件: "
            + ", ".join(by_residual)
        )
    out.append(_mk("C10", "C", "重複立候補の突合（表13 ⇄ 表11、両方向）", bad, len(duals), note))

    # C11: 表(10) の得票率の再計算
    bad, n = [], 0
    for r in data["party_votes_by_block"]:
        if r["is_total_row"] == "true" or not r["share_pct"]:
            continue
        n += 1
        total = total4.get(r["block"])
        calc = (dec(r["votes"]) / total * 100).quantize(Decimal("0.01"))
        if abs(calc - dec(r["share_pct"])) > Decimal("0.01"):
            bad.append(f"{r['block']}/{r['party']}: 印字{r['share_pct']} 計算{calc}")
    out.append(_mk("C11", "C", "表(10)の得票率 = 得票数 / 得票総数 × 100", bad, n))

    # C12: 候補者数・当選人数の総数
    bad = []
    n_cands = len(cands)
    printed_cands = next(
        (num(r["count"]) for r in data["candidacy_by_pref_age"] if r["prefecture"] == "合計" and r["age_band"] == "計"),
        None,
    )
    if printed_cands != n_cands:
        bad.append(f"候補者数: 表13={n_cands} 表1(3)計={printed_cands}")
    printed_smd_total = next(
        (
            num(r["total"])
            for r in data["candidacy_by_party"]
            if r["section"] == "smd" and r["status"] == "計" and r["party"] == "__TOTAL__"
        ),
        None,
    )
    if printed_smd_total is not None and printed_smd_total != n_cands:
        bad.append(f"候補者数: 表13={n_cands} 表1(1)小選挙区計={printed_smd_total}")
    printed_winners = next(
        (num(r["count"]) for r in data["winners_by_pref_age"] if r["prefecture"] == "合計" and r["age_band"] == "計"),
        None,
    )
    if printed_winners != cfg.smd_seats:
        bad.append(f"当選人数: 表3(3)計={printed_winners}（期待 {cfg.smd_seats}）")
    out.append(_mk("C12", "C", "候補者数・当選人数の総数が各表で一致", bad, 3,
                   f"候補者 {n_cands} 人 / 小選挙区当選 {cfg.smd_seats} 人"))

    return out


# ---------------------------------------------------------------------------
# D. ドント式の独立再計算
# ---------------------------------------------------------------------------


def dhondt(
    votes: dict[str, Decimal], seats: int, capacity: dict[str, int] | None = None
) -> tuple[list[tuple[str, int]], bool]:
    """ドント式で議席を配分し、``[(党派, 除数)]`` を獲得順に返す。

    ``capacity`` は各党派が実際に当選人を出せる名簿登載者数。
    小選挙区で当選済みの者と、供託物没収点に達せず名簿記載なしとみなされた者
    （惜敗率欄が「×」）は当選人になれないため、その党派への配分は打ち切られ、
    残りの議席は他党に回る（公職選挙法95条の2第4項の名簿枯渇）。
    ``None`` を渡すと制約なしの素のドント式になる。

    2つ目の戻り値は、議席の境界で商が同値になった（＝くじ引きが必要な）場合に ``True``。
    """
    used = {p: 0 for p in votes}
    order: list[tuple[str, int]] = []
    tie = False
    for _ in range(seats):
        available = {
            p: v for p, v in votes.items() if capacity is None or used[p] < capacity.get(p, 0)
        }
        if not available:
            break
        quotients = {p: available[p] / (used[p] + 1) for p in available}
        best = max(quotients.values())
        winners = [p for p, q in quotients.items() if q == best]
        if len(winners) > 1:
            tie = True
        winner = sorted(winners, key=lambda p: (-votes[p], p))[0]
        used[winner] += 1
        order.append((winner, used[winner]))
    return order, tie


def check_d(data, cfg) -> list[Result]:
    out: list[Result] = []

    votes_by_block: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for r in data["party_votes_by_block"]:
        if r["is_total_row"] == "false":
            votes_by_block[r["block"]][r["party"]] = dec(r["votes"])
    seats_by_block: dict[str, int] = defaultdict(int)
    printed_seats: dict[tuple[str, str], int] = {}
    for r in data["pr_party_blocks"]:
        seats_by_block[r["block"]] += num(r["seats"]) or 0
        printed_seats[(r["block"], r["party"])] = num(r["seats"]) or 0

    # 当選人になりうる名簿登載者の数（小選挙区で当選済みの者と「×」の者を除く）
    capacity: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in data["pr_list_entries"]:
        if r["smd_result"] != "当" and not flag(r["sekihai_excluded"]):
            capacity[r["block"]][r["party"]] += 1

    # D1: 表(12) の商 = 得票数 / 除数
    bad, n = [], 0
    for r in data["dhondt_quotients"]:
        n += 1
        v = votes_by_block[r["block"]].get(r["party"])
        if v is None:
            bad.append(f"{r['block']}/{r['party']}: 表10に得票が無い")
            continue
        calc = (v / int(r["divisor"])).quantize(Decimal("0.001"))
        if abs(calc - dec(r["quotient"])) > Decimal("0.001"):
            bad.append(f"{r['block']}/{r['party']}/除数{r['divisor']}: 印字{r['quotient']} 計算{calc}")
    out.append(_mk("D1", "D", "表(12)の商 = 得票数 ÷ 除数", bad, n))

    # D2: 自前のドント計算 == 表(11) の当選人数
    bad, ties, n = [], [], 0
    for block, votes in votes_by_block.items():
        n += 1
        order, tie = dhondt(votes, seats_by_block[block], capacity[block])
        if tie:
            ties.append(block)
        got = defaultdict(int)
        for party, _ in order:
            got[party] += 1
        for party in votes:
            if got[party] != printed_seats.get((block, party), 0):
                bad.append(f"{block}/{party}: 再計算={got[party]} 表11={printed_seats.get((block, party))}")
    out.append(
        Result("D2", "D", "ドント式の独立再計算による議席配分 = 表(11)の当選人数",
               PASS if not bad else FAIL, n, len(bad),
               "同値（くじ引き）発生: " + (", ".join(ties) if ties else "なし"), bad[:8])
    )

    # D3: 獲得順位が表(12) の印字と一致
    bad, n = [], 0
    printed_order: dict[str, dict[int, tuple[str, int]]] = defaultdict(dict)
    for r in data["dhondt_quotients"]:
        if r["seat_rank"]:
            printed_order[r["block"]][int(r["seat_rank"])] = (r["party"], int(r["divisor"]))
    for block, votes in votes_by_block.items():
        order, _ = dhondt(votes, seats_by_block[block], capacity[block])
        for i, (party, divisor) in enumerate(order, start=1):
            n += 1
            want = printed_order[block].get(i)
            if want != (party, divisor):
                bad.append(f"{block} 第{i}議席: 再計算={(party, divisor)} 表12={want}")
    out.append(_mk("D3", "D", "議席の獲得順（党派・除数）が表(12)の順位と一致", bad, n))

    return out


# ---------------------------------------------------------------------------
# E. 構造アサーション
# ---------------------------------------------------------------------------


def check_e(data, cfg) -> list[Result]:
    out: list[Result] = []

    bad = []
    prefs = {r["prefecture"] for r in data["smd_districts"]}
    if prefs != set(PREFECTURES):
        bad.append(f"都道府県の集合が違います: 欠 {set(PREFECTURES) - prefs} / 余 {prefs - set(PREFECTURES)}")
    blocks = {r["block"] for r in data["party_votes_by_block"]}
    if blocks != set(PR_BLOCKS):
        bad.append(f"ブロックの集合が違います: 欠 {set(PR_BLOCKS) - blocks} / 余 {blocks - set(PR_BLOCKS)}")
    out.append(_mk("E1", "E", "47都道府県・11比例ブロックが過不足なく揃っている", bad, 58))

    bad = []
    known = set(cfg.parties) | {"__TOTAL__"}
    for name, rows in data.items():
        for r in rows:
            p = r.get("party")
            if p and p not in known:
                bad.append(f"{name}: 未知の党派 {p!r}")
                break
    out.append(_mk("E2", "E", "全CSVの党派名が既知の集合に収まっている", bad, len(data)))

    bad, n = [], 0
    for c in data["smd_candidates"]:
        n += 1
        age = num(c["age"])
        if age is None or not (18 <= age <= 120):
            bad.append(f"{c['name_display']}: 年齢 {c['age']}")
        if not c["name_display"] or not c["party"] or not c["votes"]:
            bad.append(f"{c['prefecture']}{c['district_no']}: 必須項目が空 {c}")
    out.append(_mk("E3", "E", "候補者レコードの必須項目・年齢の妥当性", bad, n))

    bad, n = [], 0
    ranks = defaultdict(list)
    for r in data["pr_list_entries"]:
        ranks[(r["block"], r["party"])].append(num(r["list_rank"]))
    for key, values in ranks.items():
        n += 1
        if min(values) != 1:
            bad.append(f"{key}: 名簿順位が1から始まっていない（最小 {min(values)}）")
        if sorted(values) != values:
            bad.append(f"{key}: 名簿順位が昇順でない")
    out.append(_mk("E4", "E", "比例名簿の順位が1始まりの昇順", bad, n))

    return out


ALL_CHECKS: tuple[Callable, ...] = (check_a, check_b, check_c, check_d, check_e)


def run_all(data, cfg: ElectionConfig) -> list[Result]:
    results: list[Result] = []
    for fn in ALL_CHECKS:
        results.extend(fn(data, cfg))
    return results
