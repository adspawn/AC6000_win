"""GATT prep and notify subscribe (Windows WinError workaround)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Union
from uuid import UUID

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

import config
from acetech_protocol import CHAR_NOTIFY
from ble_connect import connect_ble, release_ble_session

CharCallback = Callable[..., None]


async def wait_gatt_ready(
    client: BleakClient,
    timeout: float = 30.0,
    *,
    notify_uuid: str = CHAR_NOTIFY,
) -> int:
    """接続後に GATT が使えるまで待つ。"""
    import time

    deadline = time.monotonic() + timeout
    settle = 3.0 if sys.platform == "win32" else 0.5

    while time.monotonic() < deadline:
        if not client.is_connected:
            await asyncio.sleep(0.5)
            continue

        await asyncio.sleep(settle)
        if not client.is_connected:
            continue

        try:
            count = len(client.services.services)
            if count > 0 and client.services.get_characteristic(notify_uuid) is not None:
                return count
        except (BleakError, AttributeError, TypeError):
            pass

        await asyncio.sleep(1.0)

    try:
        count = len(client.services.services)
    except Exception:
        count = 0
    raise BleakError(
        f"GATT services not ready (services={count}, timeout={timeout}s)"
    )


async def start_notify_retry(
    client: BleakClient,
    char_uuid: Union[str, UUID],
    callback: CharCallback,
    *,
    retries: int = 5,
    delay: float = 2.0,
) -> None:
    last_error: Exception | None = None
    uuid_str = str(char_uuid)

    for attempt in range(1, retries + 1):
        if not client.is_connected:
            raise BleakError("BLE disconnected before notify subscribe")

        try:
            _log_notify_target(client, uuid_str)
            await client.start_notify(char_uuid, callback)
            print("Notify subscribed.\n", flush=True)
            return
        except (OSError, BleakError, asyncio.CancelledError) as exc:
            last_error = exc
            print(
                f"  Notify subscribe {attempt}/{retries} failed: {exc}",
                flush=True,
            )
            if attempt < retries:
                await asyncio.sleep(delay * attempt)

    raise BleakError(f"Could not subscribe to notify {uuid_str}") from last_error


async def prepare_notify_session(client: BleakClient, callback: CharCallback) -> None:
    svc_count = await wait_gatt_ready(client)
    print(f"GATT services: {svc_count}", flush=True)
    await start_notify_retry(client, CHAR_NOTIFY, callback)


async def open_notify_session(
    address: str,
    callback: CharCallback,
    *,
    name: str | None = None,
    device: BLEDevice | None = None,
    pair: bool = False,
    connect_timeout: float | None = None,
    connect_retries: int | None = None,
    scan_timeout: float | None = None,
) -> tuple[BleakClient, AdvertisementData | None]:
    """
    接続 + GATT + Notify 購読。

    Windows では前回切断の GATT セッションが残り 1 回目が失敗することがあるため、
    失敗時は完全切断 → クールダウン → 再スキャン → 再接続を自動で行う。
    """
    cycles = config.GATT_SETUP_CYCLES
    client: BleakClient | None = None
    last_adv: AdvertisementData | None = None
    per_cycle_retries = min(connect_retries or config.CONNECT_RETRIES, 3)

    for cycle in range(1, cycles + 1):
        if cycle > 1:
            print(
                f"\nGATT clean retry {cycle}/{cycles} "
                "(reset stale Windows session)...",
                flush=True,
            )
            await release_ble_session(client)

        client, adv = await connect_ble(
            address,
            name=name,
            device=None,
            timeout=connect_timeout,
            retries=per_cycle_retries,
            pair=pair,
            scan_timeout=scan_timeout,
            pre_reset=(cycle == 1),
        )
        if adv is not None:
            last_adv = adv
        try:
            await prepare_notify_session(client, callback)
            return client, last_adv
        except BleakError as exc:
            print(f"  GATT setup failed: {exc}", flush=True)
            if cycle >= cycles:
                raise

    raise BleakError("GATT setup failed")


def _log_notify_target(client: BleakClient, uuid_str: str) -> None:
    try:
        ch = client.services.get_characteristic(uuid_str)
        if ch is not None:
            props = ",".join(ch.properties)
            print(f"  Notify char: {ch.uuid} ({props})", flush=True)
    except Exception:
        pass
