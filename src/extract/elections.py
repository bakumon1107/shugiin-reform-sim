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

    #: 表(13)で氏名が画像として埋め込まれているセルの読み値。
    #: キーは (都道府県, 区番号, 得票数の文字列)。値は {"display": ..., "kanji": ...}。
    #: Word由来のPDFでは稀な字形が画像で貼り込まれ、テキストレイヤーから欠落する。
    #: 該当セルに画像があるのにここに登録がなければ抽出は停止する。
    name_overrides: dict[tuple[str, int, str], dict[str, str]] = field(default_factory=dict)

    #: 表(11)の比例名簿で氏名が画像として埋め込まれているセルの読み値。
    #: キーは (ブロック, 党派, そのブロック×党派の中での0始まりの並び順)。
    pr_name_overrides: dict[tuple[str, str, int], str] = field(default_factory=dict)

    #: 出典PDF自体に矛盾がある箇所。``{チェックID: {対象: 理由}}``。
    #: ここに登録した対象だけ FAIL ではなく WARN として報告する。
    #: 抽出ミスと出典の誤りを混同しないよう、理由には突き合わせた根拠を書くこと。
    known_discrepancies: dict[str, dict[str, str]] = field(default_factory=dict)

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
        # 第1 2. 投票結果（本体／投票率／それぞれの「うち在外」の4ページ。
        # 並び順は回によって違うので、抽出側が中身を見て振り分ける）
        "electorate_smd": (9, 12),
        "electorate_pr": (13, 16),
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
        "electorate_smd": (10, 13),
        "electorate_pr": (14, 17),
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


R03_10_31 = ElectionConfig(
    election_id="r03-10-31",
    ordinal=49,
    election_date="2021-10-31",
    pdf_filename="000776985.pdf",
    sha256="224fee3ca2f448ca698a3e0869388435d842de45cbeeba9f5f17a3c20095e29a",
    source_url="https://www.soumu.go.jp/main_content/000776985.pdf",
    n_pages=150,
    smd_seats=289,
    pr_seats=176,
    party_column_label="届出政党等",
    parties=frozenset(
        {
            "自由民主党",
            "立憲民主党",
            "日本維新の会",
            "公明党",
            "日本共産党",
            "国民民主党",
            "れいわ新選組",
            "社会民主党",
            "ＮＨＫと裁判してる党弁護士法７２条違反で",
            "支持政党なし",
            "新党やまと",
            "政権交代によるコロナ対策強化新党",
            "日本第一党",
            "新党くにもり",
            "希望の党",
            "新党日本こころ",
            "改革未来党",
            "愛地球党",
            "日本成功党",
            "改新党",
            "無所属",
            "諸派",
        }
    ),
    # 表(13)で氏名の一部が画像として貼り込まれている13件。
    # 該当セルを300〜900dpiで切り出して目視で読み取った値
    # （reports/visual_spotcheck_r03-10-31.md に切り出し画像の所見を記載）。
    name_overrides={
        ("北海道", 8, "112857"): {"kanji": "逢坂誠二"},
        ("東京都", 2, "119281"): {"display": "辻清人"},
        ("東京都", 7, "37781"): {"kanji": "辻健太郎"},
        ("東京都", 13, "4039"): {"kanji": "橋本孫美"},
        ("東京都", 18, "122091"): {"kanji": "菅直人"},
        ("長野県", 5, "80408"): {"kanji": "曽我逸郎"},
        ("大阪府", 1, "67145"): {"kanji": "大西宏幸"},
        ("大阪府", 2, "47487"): {"display": "尾辻かな子"},
        ("大阪府", 10, "66943"): {"display": "辻元清美"},
        ("兵庫県", 8, "24880"): {"kanji": "辻恵"},
        ("島根県", 1, "4318.908"): {"display": "龜井彰子"},
        ("岡山県", 1, "90939"): {"kanji": "逢沢一郎"},
        ("鹿児島県", 4, "127131"): {"kanji": "森山裕"},
    },
    # 表(11) 東京都ブロック 自民の3人目（名簿順位2）。表(13)の東京都2区と同一人物。
    pr_name_overrides={("東京都", "自由民主党", 2): "辻清人"},
    pages={
        "candidacy_by_party": (3, 6),
        "candidacy_by_pref_party": (7, 9),
        "candidacy_by_pref_age": (10, 10),
        "electorate_smd": (11, 14),
        "electorate_pr": (15, 18),
        "winners_by_party": (19, 22),
        "winners_by_pref_party": (23, 25),
        "winners_by_pref_age": (26, 26),
        "party_votes_smd_total": (27, 28),
        "party_votes_pr_total": (29, 30),
        "party_votes_by_pref_smd": (31, 34),
        "party_votes_by_block_pref": (35, 37),
        "ballots_smd_by_pref": (38, 38),
        "ballots_pr_by_block_pref": (39, 39),
        "party_votes_by_block": (40, 50),
        "pr_lists": (51, 83),
        "dhondt_table": (84, 105),
        "smd_candidates": (106, 141),
    },
)


R29_10_22 = ElectionConfig(
    election_id="h29-10-22",
    ordinal=48,
    election_date="2017-10-22",
    pdf_filename="000516736.pdf",
    sha256="6c5093d7b66dbc8d0158d821f5ce4ee152a184ff48c6781cb5aa4065377e0d6f",
    source_url="https://www.soumu.go.jp/main_content/000516736.pdf",
    n_pages=136,
    smd_seats=289,
    pr_seats=176,
    party_column_label="届出政党等",
    parties=frozenset(
        {
            "自由民主党",
            "立憲民主党",
            "希望の党",
            "公明党",
            "日本共産党",
            "日本維新の会",
            "社会民主党",
            "日本のこころ",
            "幸福実現党",
            "支持政党なし",
            "世界経済共同体党",
            "労働の解放をめざす労働者党",
            "新党大地",
            "フェア党",
            "犬丸勝子と共和党",
            "都政を革新する会",
            "新党憲法９条",
            "議員報酬ゼロを実現する会",
            "長野県を日本一好景気にする会",
            "日本新党",
            "無所属",
            "諸派",
        }
    ),
    known_discrepancies={
        # 沖縄県は、表(6)の合計列と表(13)の候補者得票の総和がともに 636,134.995 で一致する一方、
        # 表(8)の有効投票数は 636,030（105票少ない）。沖縄2区の供託物没収点 15,633.600 も
        # 表(8)側と整合する。表(13)の値は惜敗率（宮崎政久 64,247 / 照屋寛徳 92,194 = 69.686）
        # とも整合しており、抽出誤りではなく出典PDF内の食い違い。
        "B1": {"沖縄県2": "表(13)の得票総和 156,441 に対し供託物没収点は 156,336 相当（出典の不整合、105票）"},
        "C3": {"沖縄県": "表(6)・表(13)は 636,134.995、表(8)有効投票数は 636,030（出典の不整合、105票）"},
    },
    pages={
        "candidacy_by_party": (3, 5),
        "candidacy_by_pref_party": (6, 7),
        "candidacy_by_pref_age": (8, 8),
        "electorate_smd": (9, 12),
        "electorate_pr": (13, 16),
        "winners_by_party": (17, 19),
        "winners_by_pref_party": (20, 21),
        "winners_by_pref_age": (22, 22),
        "party_votes_smd_total": (23, 24),
        "party_votes_pr_total": (25, 25),
        "party_votes_by_pref_smd": (26, 28),
        "party_votes_by_block_pref": (29, 30),
        "ballots_smd_by_pref": (31, 31),
        "ballots_pr_by_block_pref": (32, 32),
        "party_votes_by_block": (33, 43),
        "pr_lists": (44, 68),
        "dhondt_table": (69, 90),
        "smd_candidates": (91, 129),
    },
)


R26_12_14 = ElectionConfig(
    election_id="h26-12-14",
    ordinal=47,
    election_date="2014-12-14",
    pdf_filename="000328960.pdf",
    sha256="343258be57812b680fbea05d8a4e4f4700301cde1f80561959efbef4b10a4792",
    source_url="https://www.soumu.go.jp/main_content/000328960.pdf",
    n_pages=142,
    #: 第47回は 0増5減 前の区割りで小選挙区295・比例180（合計475）
    smd_seats=295,
    pr_seats=180,
    party_column_label="届出政党等",
    parties=frozenset(
        {
            "自由民主党",
            "民主党",
            "維新の党",
            "公明党",
            "日本共産党",
            "次世代の党",
            "生活の党",
            "社会民主党",
            "新党改革",
            "幸福実現党",
            "支持政党なし",
            "減税日本",
            "世界経済共同体党",
            "犬丸勝子と共和党",
            "みらい党",
            "無所属",
            "諸派",
        }
    ),
    pages={
        "candidacy_by_party": (3, 5),
        "candidacy_by_pref_party": (6, 7),
        "candidacy_by_pref_age": (8, 8),
        "electorate_smd": (9, 12),
        "electorate_pr": (13, 16),
        "winners_by_party": (17, 19),
        "winners_by_pref_party": (20, 21),
        "winners_by_pref_age": (22, 22),
        "party_votes_smd_total": (23, 24),
        "party_votes_pr_total": (25, 25),
        "party_votes_by_pref_smd": (26, 28),
        "party_votes_by_block_pref": (29, 30),
        "ballots_smd_by_pref": (31, 31),
        "ballots_pr_by_block_pref": (32, 32),
        "party_votes_by_block": (33, 43),
        "pr_lists": (44, 74),
        "dhondt_table": (75, 96),
        "smd_candidates": (97, 136),
    },
)


ELECTIONS: dict[str, ElectionConfig] = {
    R08_02_08.election_id: R08_02_08,
    R06_10_27.election_id: R06_10_27,
    R03_10_31.election_id: R03_10_31,
    R29_10_22.election_id: R29_10_22,
    R26_12_14.election_id: R26_12_14,
}

DEFAULT_ELECTION = R08_02_08.election_id


def get(election_id: str | None = None) -> ElectionConfig:
    return ELECTIONS[election_id or DEFAULT_ELECTION]
