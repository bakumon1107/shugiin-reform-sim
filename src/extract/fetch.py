"""出典PDFを総務省のサイトから取得して ``raw/`` に置く。

PDF原本はリポジトリに含めていない（`raw/*.pdf` は .gitignore）。
URLと sha256 は ``elections.py`` に記録してあるので、そこから取得・照合する。

使い方::

    python -m extract.fetch            # 未取得のものだけ取得
    python -m extract.fetch --all      # 全選挙回
    python -m extract.fetch r03-10-31  # 指定した回だけ
    python -m extract.fetch --check    # 取得はせず、手元のPDFの sha256 だけ照合
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from . import elections
from .elections import ElectionConfig

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "raw"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(cfg: ElectionConfig, *, check_only: bool = False) -> bool:
    """1回分を取得（または照合）する。問題なければ True。"""
    path = RAW_DIR / cfg.pdf_filename
    label = f"{cfg.election_id} 第{cfg.ordinal}回 {cfg.pdf_filename}"

    if not path.exists():
        if check_only:
            print(f"[MISSING] {label} — python -m extract.fetch {cfg.election_id}")
            return False
        print(f"[GET ] {label}\n         {cfg.source_url}")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".pdf.part")
        with urllib.request.urlopen(cfg.source_url) as res, tmp.open("wb") as out:
            out.write(res.read())
        tmp.replace(path)

    got = digest(path)
    if got != cfg.sha256:
        print(f"[NG  ] {label}\n         期待 {cfg.sha256}\n         実際 {got}")
        print("         出典が差し替わった可能性があります。elections.py の定義を確認してください。")
        return False
    print(f"[OK  ] {label}  sha256 {got[:16]}…")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("election_id", nargs="?", help="省略時は未取得のものだけ")
    parser.add_argument("--all", action="store_true", help="取得済みでも sha256 を照合する")
    parser.add_argument("--check", action="store_true", help="取得せず照合だけ行う")
    args = parser.parse_args(argv)

    if args.election_id:
        if args.election_id not in elections.ELECTIONS:
            raise SystemExit(
                f"未知の選挙回: {args.election_id}（既知: {', '.join(elections.ELECTIONS)}）"
            )
        targets = [elections.get(args.election_id)]
    else:
        targets = list(elections.ELECTIONS.values())

    ok = all(fetch(cfg, check_only=args.check) for cfg in targets)
    if not ok:
        return 1
    print(f"\n{len(targets)} 件すべて sha256 が一致しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
