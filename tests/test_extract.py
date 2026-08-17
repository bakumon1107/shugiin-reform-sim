"""目視でPDFと突き合わせて確認した値をゴールデンデータとして固定する回帰テスト。

ここに書いてある数値はすべて、PDFの該当ページを実際に目視して確認したもの。
抽出ロジックを変えたときにここが落ちたら、まずPDFを見て確かめること。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extract.csvio import dec, read_rows  # noqa: E402
from extract.elections import ELECTIONS  # noqa: E402
from verify.checks import FAIL, dhondt, load, run_all  # noqa: E402

CSV = ROOT / "data" / "csv"


def rows(election_id: str, name: str) -> list[dict[str, str]]:
    path = CSV / election_id / f"{name}.csv"
    if not path.exists():
        pytest.skip(f"{path} がありません。先に python -m extract.run_all {election_id} を実行してください")
    return read_rows(path)


# ---------------------------------------------------------------------------
# 検証スイート全体
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("election_id", sorted(ELECTIONS))
def test_all_checks_pass(election_id: str) -> None:
    csv_dir = CSV / election_id
    if not csv_dir.exists():
        pytest.skip(f"{csv_dir} がありません")
    results = run_all(load(csv_dir), ELECTIONS[election_id])
    failures = [f"{r.check_id} {r.title}: {r.samples}" for r in results if r.status == FAIL]
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 目視確認済みのゴールデン値（第51回 / PDF p116 = 文書p114）
# ---------------------------------------------------------------------------

TOKYO_17 = [
    # 当落, 届出名, 戸籍名, 年齢, 党派(生), 新前元, 得票数, 重複, 惜敗率
    ("落", "反田まり", "反田麻理", 45, "中道改革連合", "新", "44594", True, "60.892"),
    ("当", "平沢勝栄", "", 80, "自由民主党", "前", "73234", False, None),
    ("落", "長谷川たかこ", "湯川貴子", 52, "国民民主党", "新", "28282", True, "38.618"),
    ("落", "円より子", "山﨑順子", 78, "（無所属）", "前", "7328", False, None),
    ("落", "杉浦しんいちろう", "杉浦慎一郎", 29, "参政党", "新", "19291", False, None),
    ("落", "鈴木しんじ", "鈴木眞志", 54, "（未来進歩党）", "新", "2068", False, None),
    ("落", "いのくち幸子", "猪口幸子", 69, "日本維新の会", "前", "27630", True, "37.728"),
]


def test_tokyo_17_matches_pdf() -> None:
    """東京都第17区（PDF p116）を1行ずつ目視確認した結果と一致すること。"""
    got = [
        c
        for c in rows("r08-02-08", "smd_candidates")
        if c["prefecture"] == "東京都" and c["district_no"] == "17"
    ]
    assert len(got) == len(TOKYO_17)
    for c, want in zip(got, TOKYO_17):
        mark, display, kanji, age, party_raw, status, votes, dual, sekihai = want
        assert (c["result_mark"], c["name_display"], c["name_kanji"]) == (mark, display, kanji)
        assert int(c["age"]) == age
        assert c["party_raw"] == party_raw
        assert c["status"] == status
        assert dec(c["votes"]) == Decimal(votes)
        assert (c["dual_candidacy"] == "true") is dual
        assert dec(c["sekihai_rate"]) == (Decimal(sekihai) if sekihai else None)


def test_tokyo_17_deposit_point() -> None:
    """供託物没収点は有効投票総数のちょうど1/10（PDF印字 20,242.700）。"""
    d = next(
        d
        for d in rows("r08-02-08", "smd_districts")
        if d["prefecture"] == "東京都" and d["district_no"] == "17"
    )
    assert dec(d["deposit_forfeit_point"]) == Decimal("20242.700")
    total = sum(Decimal(v) for _, _, _, _, _, _, v, _, _ in TOKYO_17)
    assert total == Decimal("202427")


def test_akita_1_matches_pdf() -> None:
    """秋田県第1区（PDF p105）。重複立候補と惜敗率の組合せを含む。"""
    got = {
        c["name_display"]: c
        for c in rows("r08-02-08", "smd_candidates")
        if c["prefecture"] == "秋田県" and c["district_no"] == "1"
    }
    assert len(got) == 6
    assert got["とがし博之"]["name_kanji"] == "冨樫博之"
    assert dec(got["とがし博之"]["votes"]) == Decimal("65940")
    assert got["とがし博之"]["elected"] == "true"
    assert dec(got["木村さちこ"]["sekihai_rate"]) == Decimal("38.686")
    assert dec(got["松浦だいご"]["sekihai_rate"]) == Decimal("22.509")
    assert got["さとうみわこ"]["dual_candidacy"] == "false"


def test_tokyo_18_keeps_surrogate_pair_kanji() -> None:
    """𠮷田綾（U+20BB7）のようなサロゲートペアの漢字が壊れていないこと。"""
    got = next(
        c
        for c in rows("r08-02-08", "smd_candidates")
        if c["prefecture"] == "東京都" and c["district_no"] == "18" and c["name_display"] == "吉田あや"
    )
    assert got["name_kanji"] == "\U00020bb7田綾"
    assert got["party_raw"] == "（再生の道）"
    assert got["party"] == "再生の道"
    assert got["party_is_certified"] == "false"


# ---------------------------------------------------------------------------
# 目視確認済みのゴールデン値（第51回 比例代表 / PDF p53 = 文書p51）
# ---------------------------------------------------------------------------


def test_kitakanto_ldp_pr_block() -> None:
    """北関東ブロック 自由民主党の見出しと名簿（PDF p53）。"""
    head = next(
        h
        for h in rows("r08-02-08", "pr_party_blocks")
        if h["block"] == "北関東" and h["party"] == "自由民主党"
    )
    assert dec(head["votes"]) == Decimal("2256845")
    assert (int(head["seats"]), int(head["seats_male"]), int(head["seats_female"])) == (8, 5, 3)

    entries = sorted(
        (
            e
            for e in rows("r08-02-08", "pr_list_entries")
            if e["block"] == "北関東" and e["party"] == "自由民主党"
        ),
        key=lambda e: (int(e["list_rank"]), int(e["elected_order"] or 9999)),
    )
    assert len(entries) == 38
    elected = [e for e in entries if e["elected_pr"] == "true"]
    assert len(elected) == 8
    assert [e["name"] for e in sorted(elected, key=lambda e: int(e["elected_order"]))] == [
        "やな和生",
        "ながおか桂子",
        "鈴木たくみ",
        "中根かずゆき",
        "西條昌良",
        "石川昭政",
        "尾身朝子",
        "前川恵",
    ]
    yana = next(e for e in entries if e["name"] == "やな和生")
    assert (yana["smd_result"], dec(yana["sekihai_rate"])) == ("落", Decimal("92.291"))


def test_hokkaido_dhondt_first_seats() -> None:
    """北海道ブロックのドント除数表の先頭（PDF p80 = 文書p78）。"""
    qs = {
        (q["party"], int(q["divisor"])): q
        for q in rows("r08-02-08", "dhondt_quotients")
        if q["block"] == "北海道"
    }
    assert dec(qs[("自由民主党", 1)]["quotient"]) == Decimal("911742")
    assert qs[("自由民主党", 1)]["seat_rank"] == "1"
    assert dec(qs[("中道改革連合", 1)]["quotient"]) == Decimal("605889")
    assert qs[("中道改革連合", 1)]["seat_rank"] == "2"
    assert dec(qs[("中道改革連合", 2)]["quotient"]) == Decimal("302944.500")
    assert qs[("国民民主党", 1)]["seat_rank"] == "7"


# ---------------------------------------------------------------------------
# ドント式の実装そのもの
# ---------------------------------------------------------------------------


#: 商: A/1=1000, B/1=600, A/2=500, C/1=350, A/3=333.3, B/2=300, C/2=175, A/4=250
_VOTES = {"A": Decimal(1000), "B": Decimal(600), "C": Decimal(350)}


def test_dhondt_basic() -> None:
    order, tie = dhondt(_VOTES, 5)
    assert [p for p, _ in order] == ["A", "B", "A", "C", "A"]
    assert [d for _, d in order] == [1, 1, 2, 1, 3]
    assert tie is False


def test_dhondt_respects_list_capacity() -> None:
    """名簿が尽きた党派には配分されず、残りは他党に回る（公選法95条の2第4項）。"""
    order, _ = dhondt(_VOTES, 5, {"A": 1, "B": 3, "C": 3})
    assert [p for p, _ in order] == ["A", "B", "C", "B", "B"]


def test_dhondt_flags_tie() -> None:
    _, tie = dhondt({"A": Decimal(100), "B": Decimal(100)}, 1)
    assert tie is True
