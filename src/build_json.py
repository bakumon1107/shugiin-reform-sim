"""CSV から、シミュレータが読むネスト構造の JSON を組み立てる。

CSV が正（source of truth）。この JSON は派生物なので、生成後に
「JSON を再集計して CSV と一致するか」まで確かめてから書き出す。

使い方::

    python -m build_json
    python -m build_json r06-10-27
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import elections
from extract.common import PR_BLOCKS, PREF_TO_BLOCK, PREFECTURES
from extract.csvio import dec, flag, num, read_rows
from extract.elections import ElectionConfig

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "csv"
JSON_DIR = ROOT / "data" / "json"


def _d(value: Decimal | None):
    """Decimal を JSON に載せる。整数は int、小数は文字列（精度を落とさないため）。"""
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f")


def build(cfg: ElectionConfig) -> dict:
    src = CSV_DIR / cfg.election_id
    t = {p.stem: read_rows(p) for p in src.glob("*.csv")}

    # --- 小選挙区 -----------------------------------------------------------
    cands_by_district = defaultdict(list)
    for c in t["smd_candidates"]:
        cands_by_district[(c["prefecture"], int(c["district_no"]))].append(c)

    districts = []
    for d in t["smd_districts"]:
        key = (d["prefecture"], int(d["district_no"]))
        rows = sorted(cands_by_district[key], key=lambda c: -dec(c["votes"]))
        point = dec(d["deposit_forfeit_point"])
        districts.append(
            {
                "prefecture": d["prefecture"],
                "district_no": int(d["district_no"]),
                "district_id": f"{d['prefecture']}{d['district_no']}",
                "block": PREF_TO_BLOCK[d["prefecture"]],
                "deposit_forfeit_point": _d(point),
                "valid_votes": _d(point * 10),
                "candidates": [
                    {
                        "name": c["name_display"],
                        "name_kanji": c["name_kanji"] or None,
                        "name_kana": c["name_kana"] or None,
                        "age": num(c["age"]),
                        "party": c["party"],
                        "party_raw": c["party_raw"],
                        "party_is_certified": flag(c["party_is_certified"]),
                        "status": c["status"],
                        "occupation": c["occupation"] or None,
                        "votes": _d(dec(c["votes"])),
                        "elected": flag(c["elected"]),
                        "dual_candidacy": flag(c["dual_candidacy"]),
                        "sekihai_rate": _d(dec(c["sekihai_rate"])),
                        "sekihai_excluded": flag(c["sekihai_excluded"]),
                    }
                    for c in rows
                ],
            }
        )
    districts.sort(key=lambda x: (PREFECTURES.index(x["prefecture"]), x["district_no"]))

    # --- 比例代表 -----------------------------------------------------------
    block_votes = defaultdict(list)
    block_total = {}
    for r in t["party_votes_by_block"]:
        if r["is_total_row"] == "true":
            block_total[r["block"]] = dec(r["votes"])
        else:
            block_votes[r["block"]].append(r)

    seats_map = {(r["block"], r["party"]): r for r in t["pr_party_blocks"]}
    entries_by = defaultdict(list)
    for r in t["pr_list_entries"]:
        entries_by[(r["block"], r["party"])].append(r)
    pref_votes = defaultdict(dict)
    for r in t["party_votes_by_block_pref"]:
        if r["prefecture"] in PREFECTURES and r["votes"]:
            pref_votes[(r["block"], r["party"])][r["prefecture"]] = dec(r["votes"])

    blocks = []
    for name, prefs in PR_BLOCKS.items():
        rows = sorted(block_votes[name], key=lambda r: int(r["rank"]) if r["rank"] else 999)
        parties = []
        for r in rows:
            head = seats_map.get((name, r["party"]))
            lst = sorted(
                entries_by[(name, r["party"])],
                key=lambda e: (int(e["list_rank"]), int(e["elected_order"] or 9999)),
            )
            parties.append(
                {
                    "party": r["party"],
                    "rank": num(r["rank"]),
                    "votes": _d(dec(r["votes"])),
                    "share_pct": _d(dec(r["share_pct"])),
                    "seats": num(head["seats"]) if head else 0,
                    "seats_male": num(head["seats_male"]) if head else None,
                    "seats_female": num(head["seats_female"]) if head else None,
                    "votes_by_prefecture": {
                        p: _d(v) for p, v in pref_votes.get((name, r["party"]), {}).items()
                    },
                    "list": [
                        {
                            "list_rank": num(e["list_rank"]),
                            "name": e["name"],
                            "elected_order": num(e["elected_order"]),
                            "elected": flag(e["elected_pr"]),
                            "smd_result": e["smd_result"] or None,
                            "sekihai_rate": _d(dec(e["sekihai_rate"])),
                            "sekihai_excluded": flag(e["sekihai_excluded"]),
                            "dual_candidacy": flag(e["dual_candidacy"]),
                        }
                        for e in lst
                    ],
                }
            )
        blocks.append(
            {
                "block": name,
                "prefectures": list(prefs),
                "seats": sum(p["seats"] for p in parties),
                "total_votes": _d(block_total.get(name)),
                "parties": parties,
            }
        )

    # --- 有権者数（アダムズ方式などの定数再配分に使う） ------------------------
    seats_by_pref = defaultdict(int)
    for d in districts:
        seats_by_pref[d["prefecture"]] += 1
    electorate = {}
    for r in t["electorate"]:
        if r["tier"] == "smd" and r["scope"] == "all" and r["prefecture"] in PREFECTURES:
            electorate[r["prefecture"]] = {
                "electors": _d(dec(r["electors_total"])),
                "voters": _d(dec(r["voters_total"])),
                "smd_seats": seats_by_pref[r["prefecture"]],
                "block": PREF_TO_BLOCK[r["prefecture"]],
            }

    ballots = {
        r["prefecture"]: {
            "total_ballots": _d(dec(r["total_ballots"])),
            "valid_votes": _d(dec(r["valid_votes"])),
            "invalid_votes": _d(dec(r["invalid_votes"])),
        }
        for r in t["ballots_smd_by_pref"]
        if r["prefecture"] in PREFECTURES
    }

    return {
        "meta": {
            "election_id": cfg.election_id,
            "ordinal": cfg.ordinal,
            "election_date": cfg.election_date,
            "source_url": cfg.source_url,
            "source_pdf": cfg.pdf_filename,
            "source_sha256": cfg.sha256,
            "smd_seats": cfg.smd_seats,
            "pr_seats": cfg.pr_seats,
            "total_seats": cfg.total_seats,
        },
        "smd": {"districts": districts},
        "pr": {"blocks": blocks},
        "electorate_by_prefecture": electorate,
        "ballots_by_prefecture": ballots,
    }


def roundtrip_check(payload: dict, cfg: ElectionConfig) -> list[str]:
    """JSON を再集計して CSV 由来の値と突き合わせる。"""
    problems: list[str] = []
    src = CSV_DIR / cfg.election_id

    cands = read_rows(src / "smd_candidates.csv")
    n_json = sum(len(d["candidates"]) for d in payload["smd"]["districts"])
    if n_json != len(cands):
        problems.append(f"候補者数: JSON={n_json} CSV={len(cands)}")
    if len(payload["smd"]["districts"]) != cfg.smd_seats:
        problems.append(f"選挙区数: JSON={len(payload['smd']['districts'])}")

    csv_sum = sum(dec(c["votes"]) for c in cands)
    json_sum = sum(
        Decimal(str(x["votes"])) for d in payload["smd"]["districts"] for x in d["candidates"]
    )
    if csv_sum != json_sum:
        problems.append(f"得票合計: JSON={json_sum} CSV={csv_sum}")

    elected = sum(1 for d in payload["smd"]["districts"] for c in d["candidates"] if c["elected"])
    if elected != cfg.smd_seats:
        problems.append(f"小選挙区当選者: JSON={elected}")

    pr_seats = sum(b["seats"] for b in payload["pr"]["blocks"])
    if pr_seats != cfg.pr_seats:
        problems.append(f"比例議席: JSON={pr_seats}")

    pr_elected = sum(
        1 for b in payload["pr"]["blocks"] for p in b["parties"] for e in p["list"] if e["elected"]
    )
    if pr_elected != cfg.pr_seats:
        problems.append(f"比例当選者: JSON={pr_elected}")

    entries = read_rows(src / "pr_list_entries.csv")
    n_list = sum(len(p["list"]) for b in payload["pr"]["blocks"] for p in b["parties"])
    if n_list != len(entries):
        problems.append(f"比例名簿登載者: JSON={n_list} CSV={len(entries)}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", default=elections.DEFAULT_ELECTION)
    args = parser.parse_args(argv)
    cfg = elections.get(args.election_id)

    payload = build(cfg)
    problems = roundtrip_check(payload, cfg)
    for p in problems:
        print(f"[FAIL] {p}")
    if problems:
        return 1

    JSON_DIR.mkdir(parents=True, exist_ok=True)
    out = JSON_DIR / f"{cfg.election_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    size = out.stat().st_size / 1024 / 1024
    print(
        f"[OK] {out.relative_to(ROOT)} ({size:.1f} MB) — "
        f"{len(payload['smd']['districts'])}選挙区 / "
        f"{sum(len(d['candidates']) for d in payload['smd']['districts'])}候補者 / "
        f"{len(payload['pr']['blocks'])}ブロック"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
