"""目視スポットチェック用に、乱数固定で抽出した選挙区・ブロックの中身を印字する。

出力を PDF の該当ページ（``source_page``）と1行ずつ突き合わせて確認する。
seed を固定しているので、何度実行しても同じ対象が選ばれる。

使い方::

    python -m verify.spotcheck            # 12選挙区 + 4ブロック
    python -m verify.spotcheck --districts 20
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extract import elections
from extract.csvio import read_rows
from extract.elections import ElectionConfig

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / "data" / "csv"
SEED = 20260208


def run(cfg: ElectionConfig, n_districts: int, n_blocks: int) -> None:
    src = CSV_DIR / cfg.election_id
    districts = read_rows(src / "smd_districts.csv")
    cands = read_rows(src / "smd_candidates.csv")
    heads = read_rows(src / "pr_party_blocks.csv")
    entries = read_rows(src / "pr_list_entries.csv")

    by_district = defaultdict(list)
    for c in cands:
        by_district[(c["prefecture"], c["district_no"])].append(c)

    rng = random.Random(SEED)
    picked = rng.sample(districts, n_districts)
    picked.sort(key=lambda d: int(d["source_page"]))

    print("=" * 100)
    print(f"目視スポットチェック  seed={SEED}  {cfg.election_id}  PDF={cfg.pdf_filename}")
    print("=" * 100)
    print("\n### 小選挙区（表13 候補者別得票数）\n")
    for d in picked:
        rows = by_district[(d["prefecture"], d["district_no"])]
        print(
            f"-- PDF p{d['source_page']} | {d['prefecture']}第{d['district_no']}区 "
            f"| 供託物没収点 {d['deposit_forfeit_point']} | 候補者 {len(rows)} 名"
        )
        print(f"   {'当落':<4}{'氏名':<18}{'年齢':>4} {'党派':<14}{'新前元':<4}{'得票数':>12} {'重複':<4}{'惜敗率':>9}")
        for c in rows:
            sek = "×" if c["sekihai_excluded"] == "true" else (c["sekihai_rate"] or "")
            mark = "当" if c["elected"] == "true" else "落"
            dup = "重" if c["dual_candidacy"] == "true" else ""
            name = c["name_display"] + (f"({c['name_kanji']})" if c["name_kanji"] else "")
            print(
                f"   {mark:<4}{name:<18}{c['age']:>4} {c['party_raw']:<14}{c['status']:<4}"
                f"{c['votes']:>12} {dup:<4}{sek:>9}"
            )
        print()

    blocks = sorted({h["block"] for h in heads})
    picked_blocks = random.Random(SEED).sample(blocks, n_blocks)
    print("\n### 比例代表（表11 党派別当選人数・名簿）\n")
    for block in picked_blocks:
        hs = [h for h in heads if h["block"] == block]
        print(f"-- ＜{block}選挙区＞  党派 {len(hs)} / 議席 {sum(int(h['seats']) for h in hs)}")
        for h in hs:
            print(
                f"   PDF p{h['source_page']} | {h['party']}  得票 {h['votes']} 票  "
                f"当選 {h['seats']} 人（男{h['seats_male']}/女{h['seats_female']}）"
            )
            for e in sorted(
                (e for e in entries if e["block"] == block and e["party"] == h["party"]),
                key=lambda e: int(e["list_rank"]),
            ):
                sek = "×" if e["sekihai_excluded"] == "true" else (e["sekihai_rate"] or "")
                print(
                    f"      名簿{e['list_rank']:>3}  {e['name']:<16}"
                    f"順位{e['elected_order'] or '-':>3}  小選挙区{e['smd_result'] or '-':<2} {sek:>8}"
                )
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", default=elections.DEFAULT_ELECTION)
    parser.add_argument("--districts", type=int, default=12)
    parser.add_argument("--blocks", type=int, default=4)
    args = parser.parse_args(argv)
    run(elections.get(args.election_id), args.districts, args.blocks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
