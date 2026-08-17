"""dataclass のリストを CSV に書き出す / CSV を dict のリストとして読み戻す。

CSV を正（source of truth）とし、JSON はここから組み立てる。
``Decimal`` は指数表記を避けた10進文字列で書く。``None`` は空文字。
"""

from __future__ import annotations

import csv
from dataclasses import fields, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def write_dataclasses(path: Path, rows: Sequence[Any]) -> int:
    """dataclass のリストを CSV に書く。行数を返す。"""
    if not rows:
        raise ValueError(f"{path.name}: 書き出す行がありません")
    first = rows[0]
    if not is_dataclass(first):
        raise TypeError(f"{path.name}: dataclass ではありません: {type(first)}")
    header = [f.name for f in fields(first)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_render(getattr(row, name)) for name in header])
    return len(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def dec(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(value)


def num(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def flag(value: str | None) -> bool:
    return value == "true"
