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
# 第47回（2014）— 「性別」列がある回。PDF p113 を目視確認
# ---------------------------------------------------------------------------

KANAGAWA_13_2014 = [
    ("当", "甘利明", "", "男", 65, "自由民主党", "142201", True, "100.000"),
    ("落", "たかく良美", "髙久良美", "男", 60, "日本共産党", "34014", False, None),
    ("落", "伊藤ゆうた", "伊藤優太", "男", 29, "維新の党", "58941", True, "41.449"),
]


def test_kanagawa_13_2014_has_gender_column() -> None:
    got = [
        c
        for c in rows("h26-12-14", "smd_candidates")
        if c["prefecture"] == "神奈川県" and c["district_no"] == "13"
    ]
    assert len(got) == len(KANAGAWA_13_2014)
    for c, want in zip(got, KANAGAWA_13_2014):
        mark, display, kanji, gender, age, party, votes, dual, sekihai = want
        assert (c["result_mark"], c["name_display"], c["name_kanji"]) == (mark, display, kanji)
        assert c["gender"] == gender
        assert int(c["age"]) == age
        assert c["party_raw"] == party
        assert dec(c["votes"]) == Decimal(votes)
        assert (c["dual_candidacy"] == "true") is dual
        assert dec(c["sekihai_rate"]) == (Decimal(sekihai) if sekihai else None)
    assert sum(dec(c["votes"]) for c in got) == Decimal("23515.600") * 10


def test_2014_seat_counts_differ_from_later_elections() -> None:
    """第47回は 0増5減 前の区割りで小選挙区295・比例180（合計475）。"""
    cfg = ELECTIONS["h26-12-14"]
    assert (cfg.smd_seats, cfg.pr_seats, cfg.total_seats) == (295, 180, 475)
    assert len(rows("h26-12-14", "smd_districts")) == 295
    assert sum(1 for c in rows("h26-12-14", "smd_candidates") if c["elected"] == "true") == 295


def test_gender_column_absent_in_recent_elections() -> None:
    """第49回以降は「性別」列がないので空文字になる。"""
    assert {c["gender"] for c in rows("r08-02-08", "smd_candidates")} == {""}
    assert {c["gender"] for c in rows("h26-12-14", "smd_candidates")} == {"男", "女"}


# ---------------------------------------------------------------------------
# 第49回（2021）— 氏名が画像として埋め込まれているセルの補正
# ---------------------------------------------------------------------------

IMAGE_NAME_CASES_2021 = [
    ("北海道", "8", "112857", "おおさか誠二", "逢坂誠二"),
    ("東京都", "2", "119281", "辻清人", ""),
    ("東京都", "7", "37781", "つじ健太郎", "辻健太郎"),
    ("東京都", "13", "4039", "はしもとまごみ", "橋本孫美"),
    ("東京都", "18", "122091", "菅直人", "菅直人"),
    ("長野県", "5", "80408", "そが逸郎", "曽我逸郎"),
    ("大阪府", "1", "67145", "大西ひろゆき", "大西宏幸"),
    ("大阪府", "2", "47487", "尾辻かな子", ""),
    ("大阪府", "10", "66943", "辻元清美", ""),
    ("兵庫県", "8", "24880", "つじ恵", "辻恵"),
    ("島根県", "1", "4318.908", "龜井彰子", ""),
    ("岡山県", "1", "90939", "あいさわ一郎", "逢沢一郎"),
    ("鹿児島県", "4", "127131", "森山ひろし", "森山裕"),
]


@pytest.mark.parametrize("pref,district,votes,display,kanji", IMAGE_NAME_CASES_2021)
def test_2021_image_embedded_names(pref, district, votes, display, kanji) -> None:
    """テキストレイヤーから欠落した氏名が、目視確認値で補われていること。"""
    got = [
        c
        for c in rows("r03-10-31", "smd_candidates")
        if c["prefecture"] == pref and c["district_no"] == district and c["votes"] == votes
    ]
    assert len(got) == 1, f"{pref}{district}区 得票{votes} が一意に定まりません"
    assert (got[0]["name_display"], got[0]["name_kanji"]) == (display, kanji)


def test_2021_pr_list_image_name() -> None:
    """表(11)で画像化されていた東京都・自民の名簿2「辻清人」。"""
    entries = [
        e
        for e in rows("r03-10-31", "pr_list_entries")
        if e["block"] == "東京都" and e["party"] == "自由民主党"
    ]
    tsuji = [e for e in entries if e["name"] == "辻清人"]
    assert len(tsuji) == 1
    assert (tsuji[0]["list_rank"], tsuji[0]["smd_result"]) == ("2", "当")


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
