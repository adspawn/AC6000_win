#!/usr/bin/env python3
"""AC6000MKIII BT device discovery (Windows-friendly)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import sys
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

import config
from protocol import format_candidates, parse_speed_candidates

logger = logging.getLogger(__name__)

NOTIFY_PROPS = frozenset({"notify", "indicate"})
_ACETECH_MANUFACTURER_IDS = frozenset({1280, 0x0500})


def _normalize_address(addr: str) -> str:
    return addr.upper().replace("-", ":")


def _name_matches(name: str | None) -> bool:
    if not name:
        return False
    upper = name.upper()
    return any(k.upper() in upper for k in config.DEVICE_NAME_KEYWORDS)


def _address_matches(device_address: str, target: str | None = None) -> bool:
    target = (target or config.DEVICE_ADDRESS or "").strip()
    if not target:
        return False
    return _normalize_address(device_address) == _normalize_address(target)


def _acetech_manufacturer(adv: AdvertisementData | None) -> bool:
    if adv is None or not adv.manufacturer_data:
        return False
    return any(mid in _ACETECH_MANUFACTURER_IDS for mid in adv.manufacturer_data)


def _device_matches(device: BLEDevice, adv: AdvertisementData | None) -> bool:
    name = device.name or (adv.local_name if adv else None)
    if config.DEVICE_NAME and name and name.strip() == config.DEVICE_NAME.strip():
        return True
    if _name_matches(name) or _name_matches(adv.local_name if adv else None):
        return True
    if _address_matches(device.address):
        return True
    if _acetech_manufacturer(adv):
        return True
    return False


def _pick_best_match(
    discovered: dict,
) -> tuple[BLEDevice | None, AdvertisementData | None]:
    """scan.py と同じ discover 結果から最も RSSI の高い AC6000 を選ぶ。"""
    best_dev: BLEDevice | None = None
    best_adv: AdvertisementData | None = None
    best_rssi = -9999

    for device, adv in discovered.values():
        if not _device_matches(device, adv):
            continue
        rssi = adv.rssi if adv.rssi is not None else -999
        if best_dev is None or rssi > best_rssi:
            best_dev = device
            best_adv = adv
            best_rssi = rssi

    return best_dev, best_adv


def _pick_best_match_for(
    address: str,
    name: str | None,
    discovered: dict,
) -> tuple[BLEDevice | None, AdvertisementData | None]:
    """指定 address / name に合うデバイスを RSSI 最大で選ぶ。"""
    best_dev: BLEDevice | None = None
    best_adv: AdvertisementData | None = None
    best_rssi = -9999
    target_addr = address.strip() if address else ""
    target_name = (name or "").strip()

    for device, adv in discovered.values():
        dev_name = device.name or (adv.local_name if adv else None)
        matched = False
        if target_addr and _address_matches(device.address, target_addr):
            matched = True
        elif target_name and dev_name and dev_name.strip() == target_name:
            matched = True
        elif not target_addr and not target_name and _device_matches(device, adv):
            matched = True

        if not matched:
            continue

        rssi = adv.rssi if adv.rssi is not None else -999
        if best_dev is None or rssi > best_rssi:
            best_dev = device
            best_adv = adv
            best_rssi = rssi

    return best_dev, best_adv


async def scan_fresh_for_connect(
    address: str,
    name: str | None = None,
    timeout: float = 5.0,
) -> tuple[BLEDevice | None, AdvertisementData | None]:
    """接続直前の discover。MAC 固定時は find_by_address を優先（高速）。"""
    lookup = _address_lookup_kwargs()
    short = min(5.0, timeout)

    if address:
        dev = await BleakScanner.find_device_by_address(
            address, timeout=short, **lookup
        )
        if dev is not None:
            return dev, None

    if name:
        dev = await BleakScanner.find_device_by_name(
            name, timeout=short, **lookup
        )
        if dev is not None:
            return dev, None

    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    dev, adv = _pick_best_match_for(address, name, discovered)
    if dev is not None:
        return dev, adv

    return None, None


def _address_lookup_kwargs() -> dict:
    if platform.system() != "Darwin":
        return {}
    return {"cb": {"use_bdaddr": config.USE_BDADDR}}


async def _scan_with_discover(
    timeout: float,
) -> tuple[BLEDevice | None, AdvertisementData | None]:
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return _pick_best_match(discovered)


async def find_device_with_adv(
    timeout: float | None = None,
) -> tuple[BLEDevice | None, AdvertisementData | None]:
    """scan.py と同じ discover を優先（Windows で最も安定）。"""
    scan_timeout = timeout if timeout is not None else config.SCAN_TIMEOUT
    retries = config.SCAN_RETRIES

    for attempt in range(1, retries + 1):
        print(
            f"BLE scan {attempt}/{retries} ({scan_timeout:.0f}s)... Chrono power ON.",
            flush=True,
        )

        found_dev, found_adv = await _scan_with_discover(scan_timeout)
        if found_dev is not None:
            name = found_dev.name or (
                found_adv.local_name if found_adv else None
            )
            print(
                f"  Found: {name or '?'} ({found_dev.address})",
                flush=True,
            )
            return found_dev, found_adv

        if attempt < retries:
            print("  Not found. Retry in 3s...", flush=True)
            await asyncio.sleep(3.0)

    return None, None


async def find_device(timeout: float | None = None) -> BLEDevice | None:
    device, _adv = await find_device_with_adv(timeout=timeout)
    return device


def _parse_handshake(hex_str: str) -> bytes | None:
    if not hex_str:
        return None
    cleaned = hex_str.replace(" ", "").replace(":", "")
    if len(cleaned) % 2:
        raise ValueError("HANDSHAKE hex length invalid")
    return bytes.fromhex(cleaned)


async def explore_and_sniff(device: BLEDevice, sniff_seconds: float, pair: bool) -> None:
    notifications: dict[str, int] = {}

    def make_handler(uuid: str) -> Callable[[int, bytearray], None]:
        def handler(_handle: int, data: bytearray) -> None:
            payload = bytes(data)
            notifications[uuid] = notifications.get(uuid, 0) + 1
            candidates = parse_speed_candidates(payload)
            cand = format_candidates(candidates)
            print(
                f"\n[notify] char={uuid}\n"
                f"  hex: {payload.hex(' ')}\n"
                f"  candidates: {cand}",
                flush=True,
            )

        return handler

    print(f"\nConnecting: {device.name} ({device.address})", flush=True)

    async with BleakClient(
        device,
        pair=pair,
        timeout=90 if pair else 30,
    ) as client:
        if not client.is_connected:
            print("Connection failed.", file=sys.stderr)
            return

        print(f"Connected: {client.name} ({client.address})\n", flush=True)
        notify_chars: list[tuple[str, str]] = []

        for service in client.services:
            for char in service.characteristics:
                if NOTIFY_PROPS.intersection(char.properties):
                    notify_chars.append((service.uuid, char.uuid))

        handshake = _parse_handshake(config.HANDSHAKE_HEX)
        if handshake and config.WRITE_CHAR_UUID:
            await client.write_gatt_char(config.WRITE_CHAR_UUID, handshake, response=False)

        if not notify_chars:
            print("\nNo notify characteristics found.", flush=True)
            return

        for _svc_uuid, char_uuid in notify_chars:
            await client.start_notify(char_uuid, make_handler(char_uuid))

        try:
            await asyncio.sleep(sniff_seconds)
        finally:
            for _svc_uuid, char_uuid in notify_chars:
                try:
                    await client.stop_notify(char_uuid)
                except Exception:
                    pass


def print_device_not_found_help() -> None:
    print(
        "\nChrono not found. Check:\n"
        "  1. Chrono power ON (Bluetooth icon on screen)\n"
        "  2. run.bat scan  - confirm AC6000 appears with star mark\n"
        "  3. Power-cycle chrono (OFF -> wait 5s -> ON), then retry\n"
        "  4. Windows Bluetooth: remove AC6000 pairing if stuck, run run_pair.bat\n",
        file=sys.stderr,
        flush=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="AC6000 BT GATT explorer")
    parser.add_argument("--sniff-seconds", type=float, default=60.0)
    parser.add_argument("--pair", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    device = await find_device()
    if device is None:
        print_device_not_found_help()
        sys.exit(1)

    await explore_and_sniff(device, args.sniff_seconds, args.pair)


if __name__ == "__main__":
    asyncio.run(main())
