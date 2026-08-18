"""拒否政党の調査から、比例投票先ごとの政党の選好順序を組み立てる。

優先順位付投票（RCV）や単記移譲式（STV）を試算するには、有権者が候補者にどう順位を
つけたかが要る。実際の投票用紙に残るのは第1希望だけなので、そのデータは存在しない。
ここでは調査から得られる「どの政党を拒否しているか」を手がかりに順序を組み立てる。

考え方はごく単純で、**拒否されていない順に並べる**。ある政党に比例票を投じた人たちに
ついて、各政党の拒否率を低い順に並べれば、それがその集団の選好順序になる。自分が
投じた政党は先頭に固定する。

    例（日本共産党に投じた人）
      社民 6% → れいわ 9% → みらい 13% → 国民 16% → 中道 17%
      → 保守 32% → 維新 35% → 参政 45% → 自民 58%

順序を決めるのに調査以外の仮定を持ち込まないのが利点。ただし調査は第51回（2026年）の
政党構成で行われているため、そこに出てこない政党（立憲民主党・公明党・減税日本・無所属）
は ``DERIVED`` の規則で補っている。**そこだけは調査から出る値ではなく、こちらで置いた
想定である。**

入力（``rejection_matrix.json``）はコミットしない。出力は拒否率の数値を捨てて順序だけを
残すので、そこから元の調査結果を復元することはできない。

使い方::

    python research/personas/build_personas.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / "rejection_matrix.json"
#: Vercel は web/ をルートに置いてビルドするので、その外のファイルは参照できない。
#: 同じ内容を web 側にも書き出す。
OUTPUTS = (HERE / "personas.json", ROOT / "web" / "public" / "data" / "personas.json")

#: 調査の党名 → 選挙データ（総務省の結果調）側の党名
NAME = {
    "自民党": "自由民主党",
    "中道改革連合": "中道改革連合",
    "国民民主党": "国民民主党",
    "日本維新の会": "日本維新の会",
    "参政党": "参政党",
    "チームみらい": "チームみらい",
    "日本共産党": "日本共産党",
    "れいわ新選組": "れいわ新選組",
    "日本保守党": "日本保守党",
    "社民党": "社会民主党",
}

#: 調査に出てこない政党を、隣に置く政党から派生させる。
#:
#: ``beside`` この政党のすぐ隣にあるものとして扱う。自分の順序はこの政党の順序を
#:            下敷きにし、他党の順序へはこの政党の直後に挿し込む。
#:
#: 立憲民主党と中道改革連合、公明党と自由民主党のように、同時に存在しない政党も
#: あるが（中道改革連合は第51回のみ、立憲民主党と公明党は第50回以前）、順序は
#: 全政党をまたいで1本持ち、選挙回ごとに存在する政党だけを見る。
DERIVED: dict[str, dict] = {
    "立憲民主党": {
        "beside": "中道改革連合",
        "why": "中道改革連合と同じ位置にあるものとして扱う",
    },
    "公明党": {
        "beside": "自由民主党",
        "why": "自民党の隣にあるものとして扱う。長く連立を組んでいた",
    },
    "減税日本・ゆうこく連合": {
        "beside": "日本保守党",
        "why": "日本保守党に近い位置にあるものとして扱う",
    },
}

INDEPENDENT = "無所属"

#: 拒否率を丸める刻み。
#:
#: 元の値は公開されたグラフから目視で読んでおり ±2 ポイント程度の誤差がある。
#: 出典は判明したが、こちらが読み取った値が正確になるわけではない。1%刻みで出すと
#: 原典の数値そのものだと誤解されるので、誤差幅に合わせて丸める。丸めた値は原典の
#: 再現ではなく、そこから出発するための概算値として扱う。
ROUND_TO = 5


#: 他党の順序の中で無所属をどこに置くか。0.0 が先頭、0.5 が中間、1.0 が最下位。
#:
#: 無所属は政党ではなく、保守系から革新系まで人によって位置が違うので、一律に置くと
#: どちらかに必ず偏る。中間（0.5）に置くと「誰からも受け入れられる妥協候補」になり、
#: 優先順位付投票では万人に許容される候補が勝ち上がるため、無所属に有利に出すぎる。
#: かといって最下位に落とすと、移譲をまったく受け取れず不利に振れる。
#:
#: 中間より少しだけ下に置いて、有利になりすぎないようにしている。
#:
#: **この値には崖がある。** 0.75 と 0.8 の間で、無所属が立憲民主党／中道改革連合より
#: 上か下かが切り替わる。立憲・中道はどの陣営からも最も拒否される位置にいるため、
#: それより上にあるうちは、自民候補が落ちた選挙区の票がまとめて無所属へ流れる。
#: 第50回（2024年）の無所属の議席は、0.75 で +3、0.8 で −6 と反転する。中立な値は
#: 無いので、この一点が結果を左右することを承知のうえで使うこと。
INDEPENDENT_POSITION = 0.75


class BuildError(Exception):
    """出力すると誤ったデータを配ることになる不整合。"""


def base_ordering(voted: str, rates: dict[str, int]) -> list[str]:
    """拒否率の低い順に政党を並べる。投じた政党は先頭に固定する。

    同率のときは党名順にして、実行するたびに結果が変わらないようにする。
    """
    others = sorted((p for p in rates if p != voted), key=lambda p: (rates[p], p))
    return [NAME[voted]] + [NAME[p] for p in others]


def insert_beside(order: list[str], party: str, beside: str) -> list[str]:
    """``party`` を ``beside`` の直後に置く。"""
    out = list(order)
    if party in out:
        return out
    if beside not in out:
        out.append(party)
        return out
    out.insert(out.index(beside) + 1, party)
    return out


def build() -> dict:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    columns: list[str] = raw["_columns"]
    if sorted(columns) != sorted(NAME):
        raise BuildError(f"列と党名対応が食い違う: {set(columns) ^ set(NAME)}")

    # --- 調査から直に出る10党の順序 ---
    surveyed: dict[str, list[str]] = {}
    rounded_rows: dict[str, list[int]] = {}
    mean_rate: dict[str, float] = {c: 0.0 for c in columns}
    n_rows = 0
    for voted, values in raw["rows"].items():
        if len(values) != len(columns):
            raise BuildError(f"{voted}: 値の数が列数と合わない")
        rates = {c: round(v / ROUND_TO) * ROUND_TO for c, v in zip(columns, values)}
        # 平均の拒否率は、比例票を持たない区分も含めた全回答から取る
        for c in columns:
            mean_rate[c] += rates[c]
        rounded_rows[voted] = [rates[c] for c in columns]
        n_rows += 1
        if voted in NAME:
            surveyed[NAME[voted]] = base_ordering(voted, rates)
    for c in mean_rate:
        mean_rate[c] /= n_rows

    # --- 派生させる政党の、自分自身の順序 ---
    # 隣に置く政党の順序をそのまま下敷きにし、自党を先頭に足す。
    orderings: dict[str, list[str]] = dict(surveyed)
    for party, rule in DERIVED.items():
        orderings[party] = [party] + list(surveyed[rule["beside"]])

    # 無所属は、全体を通して拒否されにくい順
    orderings[INDEPENDENT] = [INDEPENDENT] + [
        NAME[c] for c in sorted(columns, key=lambda c: (mean_rate[c], c))
    ]

    # --- すべての順序に、派生させた政党を挿し込む ---
    for party in list(orderings):
        order = orderings[party]
        for derived, rule in DERIVED.items():
            if derived == party:
                continue
            order = insert_beside(order, derived, rule["beside"])
        if party != INDEPENDENT:
            # 先頭（自党）を除いた並びの、指定した割合の位置に置く
            rest = len(order) - 1
            at = 1 + round(rest * INDEPENDENT_POSITION)
            order = order[:at] + [INDEPENDENT] + order[at:]
        orderings[party] = order

    universe = set(orderings)
    for party, order in orderings.items():
        if order[0] != party:
            raise BuildError(f"{party}: 先頭が自党でない")
        if set(order) != universe or len(order) != len(universe):
            raise BuildError(f"{party}: 順序に重複か欠落がある（{len(order)}件）")

    # 派生させる政党の拒否率も作る。層を組むのに要る。
    #
    # 派生元と**完全に同じ**に揃える。行（その党に投じた人が誰を拒否するか）だけでなく
    # 列（他党の支持層からどう見られるか）も同じにしないと表が正方にならず、拒否率を
    # 画面で編集するときに空欄が出る。
    COPY = {
        "立憲民主党": "中道改革連合",
        "公明党": "自由民主党",
        "減税日本・ゆうこく連合": "日本保守党",
    }

    rates_out: dict[str, dict[str, int]] = {
        NAME[row]: dict(zip((NAME[c] for c in columns), vals))
        for row, vals in rounded_rows.items()
        if row in NAME
    }
    # 列を足す（どの支持層から見ても、派生元と同じに見える）
    for derived, base in COPY.items():
        for row in rates_out.values():
            row[derived] = row[base]
    # 行を足す（派生元の行をそのまま複製する）
    for derived, base in COPY.items():
        rates_out[derived] = dict(rates_out[base])

    square = set(rates_out)
    for party, row in rates_out.items():
        if set(row) != square:
            raise BuildError(f"{party}: 拒否率の表が正方でない（{len(row)}列）")

    return {
        "method": (
            "比例投票先ごとに、各政党の拒否率が低い順に並べたもの。投じた政党を先頭に"
            f"固定し、以降は拒否されていない順。同率は党名順。拒否率は目視の誤差に合わせて"
            f"{ROUND_TO}%刻みに丸めてあり、調査の再現ではなく出発点としての概算値。"
            "調査に出てこない政党は derived の規則で近い政党から派生させた。"
        ),
        "source": (
            "選挙ドットコム × JX通信社の合同調査（2026年2月26日公開）。設問は"
            "「絶対投票したくない政党を選んでください」（複数選択可）。"
            "ここでの数値は公開されたグラフから目視で読み取ったうえ、誤差に合わせて"
            f"{ROUND_TO}%刻みに丸めた概算値であり、原典の数値そのものではない。"
            "実施時期・標本数・調査方法は公開情報に記載がなく未確認。"
            "調査は第51回（2026年2月8日）の政党構成による。"
        ),
        "sourceUrls": [
            "https://go2senkyo.com/articles/2026/02/28/130298.html",
            "https://www.youtube.com/watch?v=rZUJwFl6-PU",
        ],
        "derived": {
            "立憲民主党": "中道改革連合と完全に同じものとして扱う（拒否率の行も列も同一）",
            "公明党": "自由民主党と完全に同じものとして扱う（拒否率の行も列も同一）。"
                      "長く連立を組んでおり、支持層の見え方が近いとみなす",
            "減税日本・ゆうこく連合":
                "日本保守党と完全に同じものとして扱う（拒否率の行も列も同一）",
        } | {
            INDEPENDENT: "特定の位置を持たないので、どの順序でも中間に置く。"
                         "自身の順序は全体を通して拒否されにくい順",
        },
        "caveats": [
            "拒否率は知名度と混ざっている。新しい政党や小さい政党は、判断材料を持つ人が"
            "少ないぶん拒否率が低く出るため、実際より上位に並びやすい。",
            "調査は現行制度のもとでの投票行動を尋ねたもの。制度が変われば有権者も政党も"
            "行動を変えるので、この順序がそのまま当てはまるわけではない。",
            "政党単位の順序であって、候補者単位ではない。小選挙区では現職かどうかや"
            "知名度が効くが、それは反映されていない。",
            "拒否している政党にも順位をつける前提になっている。実際には順位をつけずに"
            "投票用紙を打ち切る人がいるはずで、その場合は票が移譲されずに死票になる。",
            "立憲民主党・公明党・減税日本は調査に出てこないため、それぞれ中道改革連合・"
            "自由民主党・日本保守党と完全に同じ拒否率を割り当てている。実際には差が"
            "あるはずで、これらを含む試算は仮定がさらに重い。無所属は手がかりが無いため"
            "拒否率を持たせず、落ちた票は残る候補へ均等に割っている。",
            "設問は「絶対投票したくない政党」を選ぶ形式なので、拒否した政党には順位を"
            "つけないものとして扱っている。残る候補を全部拒否している層の票は死票になる。",
        ],
        "orderings": orderings,
        # 各政党の拒否率（%）。画面から編集できるようにするための初期値。
        # 無所属は手がかりが無いので持たせない（落ちた票は残る候補へ均等に割る）。
        "rejectionRates": rates_out,
        "roundedTo": ROUND_TO,
    }


def main() -> int:
    if not SOURCE.exists():
        print(f"[FAIL] 入力がない: {SOURCE.relative_to(HERE.parents[1])}")
        print("       この調査データはコミットしていないので、手元に置いてから実行する。")
        return 1

    payload = build()
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    for out in OUTPUTS:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[OK] {out.relative_to(ROOT)}")
    print(f"     {len(payload['orderings'])}政党\n")
    derived = set(payload["derived"])
    for party, order in payload["orderings"].items():
        mark = "（派生）" if party in derived else ""
        print(f"{party}{mark} に投じた人の選好順序")
        shown = [f"*{p}*" if p in derived else p for p in order]
        print("  " + " → ".join(shown) + "\n")
    print("* を付けた政党は、調査に出てこないため想定で置いたもの。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
