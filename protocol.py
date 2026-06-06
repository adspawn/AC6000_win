"""
通知ペイロードから弾速らしき値を推定するヘルパー。

公式プロトコルが公開されていないため、複数の解釈を試します。
discover.py で実測した hex と照合して、当てはまる方式を選んでください。
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SpeedReading:
    """推定された弾速。"""

    value: float
    unit: str  # "m/s" または "ft/s" など（推定）
    method: str
    raw_hex: str


def _hex(data: bytes) -> str:
    return data.hex(" ")


def _try_ascii(data: bytes) -> SpeedReading | None:
    text = data.decode("utf-8", errors="ignore").strip()
    if not text:
        return None
    # 例: "85.2", "85.2 m/s", "V=85.2"
    m = re.search(r"(\d{1,3}(?:\.\d{1,2})?)", text)
    if not m:
        return None
    v = float(m.group(1))
    if not (5 <= v <= 500):
        return None
    unit = "ft/s" if re.search(r"ft|fps|feet", text, re.I) else "m/s"
    return SpeedReading(v, unit, "ascii", _hex(data))


def _try_uint16_le_scale(data: bytes, scale: float, unit: str) -> SpeedReading | None:
    if len(data) < 2:
        return None
    raw = struct.unpack_from("<H", data, 0)[0]
    v = raw * scale
    if not (5 <= v <= 500):
        return None
    return SpeedReading(v, unit, f"uint16_le_x{scale}", _hex(data))


def _try_float32_le(data: bytes, unit: str = "m/s") -> SpeedReading | None:
    if len(data) < 4:
        return None
    v = struct.unpack_from("<f", data, 0)[0]
    if not (5 <= v <= 500) or v != v:  # NaN
        return None
    return SpeedReading(v, unit, "float32_le", _hex(data))


def _try_float32_be(data: bytes, unit: str = "m/s") -> SpeedReading | None:
    if len(data) < 4:
        return None
    v = struct.unpack_from(">f", data, 0)[0]
    if not (5 <= v <= 500) or v != v:
        return None
    return SpeedReading(v, unit, "float32_be", _hex(data))


def parse_speed_candidates(data: bytes) -> list[SpeedReading]:
    """ペイロードから plausible な弾速候補をすべて返す。"""
    if not data:
        return []

    candidates: list[SpeedReading] = []
    seen: set[tuple[float, str, str]] = set()

    def add(r: SpeedReading | None) -> None:
        if r is None:
            return
        key = (round(r.value, 3), r.unit, r.method)
        if key in seen:
            return
        seen.add(key)
        candidates.append(r)

    add(_try_ascii(data))
    add(_try_float32_le(data))
    add(_try_float32_be(data))
    # よくある固定小数: 0.1 m/s または 0.01 m/s 単位
    for scale in (0.1, 0.01, 1.0):
        add(_try_uint16_le_scale(data, scale, "m/s"))
    # ft/s 系（×0.1 ft/s など）
    for scale in (0.1, 0.01):
        add(_try_uint16_le_scale(data, scale, "ft/s"))

    return candidates


def format_candidates(candidates: Iterable[SpeedReading]) -> str:
    parts = [f"{c.value:.2f} {c.unit} ({c.method})" for c in candidates]
    return ", ".join(parts) if parts else "(解析候補なし)"
