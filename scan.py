#!/usr/bin/env python3
"""周辺の BLE デバイスを一覧表示（ACETECH 関連を強調）。"""

import asyncio

from bleak import BleakScanner

import config


async def main() -> None:
    print("スキャン中 (10秒)…\n")
    # Bleak 0.19+: RSSI は AdvertisementData にある（BLEDevice.rssi は廃止）
    discovered = await BleakScanner.discover(timeout=10.0, return_adv=True)
    keywords = tuple(k.upper() for k in config.DEVICE_NAME_KEYWORDS)

    rows: list[tuple[int, str, str, str]] = []
    for device, adv in discovered.values():
        name = device.name or adv.local_name or "(名前なし)"
        hit = any(k in name.upper() for k in keywords)
        mark = " ★ ACETECH候補" if hit else ""
        rows.append((adv.rssi, name, device.address, mark))

    for rssi, name, address, mark in sorted(rows, key=lambda x: x[0], reverse=True):
        print(f"{name:24} {address:20} RSSI={rssi}{mark}")


if __name__ == "__main__":
    asyncio.run(main())
