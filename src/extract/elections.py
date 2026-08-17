"""選挙回ごとの設定（PDFの物理ページ範囲・党派名・列名の揺れ）。

新しい回を追加するときは ``python -m extract.probe <pdf>`` で構造を実測してから
ここに1エントリ足す。抽出ロジック本体は選挙回に依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ElectionConfig:
    election_id: str
    ordinal: int
    """第N回。"""
    election_date: str
    """執行日 (ISO)。"""
    pdf_filename: str
    sha256: str
    source_url: str
    n_pages: int
    smd_seats: int
    pr_seats: int

    #: 表 -> PDF物理ページ範囲 (1始まり, 両端含む)
    pages: dict[str, tuple[int, int]] = field(default_factory=dict)

    #: 「党派」欄に現れる確認団体（届出政党等）の正規名
    parties: frozenset[str] = frozenset()

    #: 表の列見出しに使われる語（回によって揺れる）
    party_column_label: str = "党派"

    @property
    def total_seats(self) -> int:
        return self.smd_seats + self.pr_seats

    def page_range(self, table: str) -> range:
        first, last = self.pages[table]
        return range(first, last + 1)


R08_PARTIES = frozenset(
    {
        "自由民主党",
        "中道改革連合",
        "日本維新の会",
        "国民民主党",
        "参政党",
        "日本共産党",
        "れいわ新選組",
        "減税日本・ゆうこく連合",
        "日本保守党",
        "社会民主党",
        "チームみらい",
        "安楽死制度を考える会",
        # 過去回との比較欄にのみ現れる
        "立憲民主党",
        "公明党",
        # 「党派」欄に括弧付きで現れる無所属・諸派
        "無所属",
        "再生の道",
        "無所属連合",
        "日本大和党",
        "世界平和党",
        "一番星",
        "核融合党",
        "未来進歩党",
        "日本自由党",
        "心の党",
        "諸派",
    }
)


R08_02_08 = ElectionConfig(
    election_id="r08-02-08",
    ordinal=51,
    election_date="2026-02-08",
    pdf_filename="001061492.pdf",
    sha256="db8239c0ee4d2e4dae14ffb7e874872663ceffef0b6e947248173d970938256e",
    source_url="https://www.soumu.go.jp/main_content/001061492.pdf",
    n_pages=151,
    smd_seats=289,
    pr_seats=176,
    party_column_label="党派",
    parties=R08_PARTIES,
    pages={
        # 第1 1. 立候補状況
        "candidacy_by_party": (3, 5),
        "candidacy_by_pref_party": (6, 7),
        "candidacy_by_pref_age": (8, 8),
        # 第1 2. 投票結果
        "electorate_smd": (9, 9),
        "electorate_smd_overseas": (10, 10),
        "turnout_smd": (11, 11),
        "turnout_smd_overseas": (12, 12),
        "electorate_pr": (13, 13),
        "electorate_pr_overseas": (14, 14),
        "turnout_pr": (15, 15),
        "turnout_pr_overseas": (16, 16),
        # 第1 3. 開票結果
        "winners_by_party": (17, 19),
        "winners_by_pref_party": (20, 21),
        "winners_by_pref_age": (22, 22),
        "party_votes_smd_total": (23, 24),
        "party_votes_pr_total": (25, 26),
        "party_votes_by_pref_smd": (27, 30),
        "party_votes_by_block_pref": (31, 33),
        "ballots_smd_by_pref": (34, 34),
        "ballots_pr_by_block_pref": (35, 35),
        "party_votes_by_block": (36, 46),
        "pr_lists": (47, 79),
        "dhondt_table": (80, 101),
        "smd_candidates": (102, 145),
    },
)


R06_PARTIES = frozenset(
    {
        "自由民主党",
        "立憲民主党",
        "日本維新の会",
        "公明党",
        "日本共産党",
        "国民民主党",
        "れいわ新選組",
        "社会民主党",
        "参政党",
        "日本保守党",
        "みんなでつくる党",
        "安楽死制度を考える会",
        # 「党派」欄に括弧付きで現れる無所属・諸派
        "無所属",
        "諸派",
        "お金をみんなへシン独立党",
        "川口自警団",
        "自民党を終わらせる党",
        "お金をみんなへシン独立党",
        "心の党",
        "鼎立の党",
    }
)

#: 第50回。ページ範囲は probe で実測したタイトル位置に基づく。
R06_10_27 = ElectionConfig(
    election_id="r06-10-27",
    ordinal=50,
    election_date="2024-10-27",
    pdf_filename="000979139.pdf",
    sha256="e80d90dc6d6acd15a77cd97a705d37f8dab6470b758fd3665f6bd9d626806c9e",
    source_url="https://www.soumu.go.jp/main_content/000979139.pdf",
    n_pages=154,
    smd_seats=289,
    pr_seats=176,
    party_column_label="届出政党等",
    parties=R06_PARTIES,
    pages={
        "candidacy_by_party": (3, 5),
        "candidacy_by_pref_party": (6, 8),
        "candidacy_by_pref_age": (9, 9),
        "electorate_smd": (10, 10),
        "electorate_smd_overseas": (11, 11),
        "turnout_smd": (12, 12),
        "turnout_smd_overseas": (13, 13),
        "electorate_pr": (14, 14),
        "electorate_pr_overseas": (15, 15),
        "turnout_pr": (16, 16),
        "turnout_pr_overseas": (17, 17),
        "winners_by_party": (18, 20),
        "winners_by_pref_party": (21, 23),
        "winners_by_pref_age": (24, 24),
        "party_votes_smd_total": (25, 26),
        "party_votes_pr_total": (27, 27),
        "party_votes_by_pref_smd": (28, 31),
        "party_votes_by_block_pref": (32, 34),
        "ballots_smd_by_pref": (35, 35),
        "ballots_pr_by_block_pref": (36, 36),
        "party_votes_by_block": (37, 47),
        "pr_lists": (48, 80),
        "dhondt_table": (81, 102),
        "smd_candidates": (103, 146),
    },
)


ELECTIONS: dict[str, ElectionConfig] = {
    R08_02_08.election_id: R08_02_08,
    R06_10_27.election_id: R06_10_27,
}

DEFAULT_ELECTION = R08_02_08.election_id


def get(election_id: str | None = None) -> ElectionConfig:
    return ELECTIONS[election_id or DEFAULT_ELECTION]
