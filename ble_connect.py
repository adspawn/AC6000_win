"""BLE connect with rescan + retry (Windows-friendly)."""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

import config
from acetech_protocol import SERVICE_NOTIFY, SERVICE_WRITE
from discover import scan_fresh_for_connect

_GATT_SERVICES = {SERVICE_NOTIFY, SERVICE_WRITE}


def _bleak_client(
    device: BLEDevice,
    *,
    timeout: float,
    pair: bool,
    use_cached_services: bool | None = None,
) -> BleakClient:
    kwargs: dict = {
        "timeout": timeout,
        "pair": pair,
        "services": set(_GATT_SERVICES),
    }
    if sys.platform == "win32":
        winrt: dict = {"address_type": "public"}
        if use_cached_services is not None:
            winrt["use_cached_services"] = use_cached_services
        kwargs["winrt"] = winrt
    return BleakClient(device, **kwargs)


async def release_ble_session(
    client: BleakClient | None,
    *,
    cooldown: float | None = None,
) -> None:
    if client is not None:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:
            pass

    cd = config.GATT_COOLDOWN_SECONDS if cooldown is None else cooldown
    if cd > 0:
        print(f"  Waiting {cd:.0f}s for BLE/GATT reset...", flush=True)
        await asyncio.sleep(cd)


async def reset_windows_gatt_before_connect(
    address: str,
    name: str | None = None,
    *,
    scan_timeout: float = 3.0,
) -> None:
    """
    Windows: 接続前に古い GATT セッションを解放する。
    2 回目で成功する現象を避けるため、最初の connect の前に実行する。
    """
    if sys.platform != "win32":
        return

    print("  GATT reset before connect (clear Windows session)...", flush=True)

    dev, _adv = await scan_fresh_for_connect(address, name, timeout=scan_timeout)
    if dev is not None:
        probe = _bleak_client(
            dev,
            timeout=12.0,
            pair=False,
            use_cached_services=False,
        )
        try:
            await asyncio.wait_for(probe.connect(), timeout=10.0)
        except Exception:
            pass
        await release_ble_session(probe, cooldown=0)

    await release_ble_session(None, cooldown=config.GATT_COOLDOWN_SECONDS)


async def connect_ble(
    address: str,
    *,
    name: str | None = None,
    device: BLEDevice | None = None,
    timeout: float | None = None,
    retries: int | None = None,
    pair: bool = False,
    scan_timeout: float | None = None,
    use_cached_services: bool | None = None,
    pre_reset: bool = True,
) -> tuple[BleakClient, AdvertisementData | None]:
    if timeout is None:
        timeout = config.CONNECT_TIMEOUT
    if pair:
        timeout = max(timeout, 120.0)
    if retries is None:
        retries = config.CONNECT_RETRIES
    if scan_timeout is None:
        scan_timeout = config.CONNECT_SCAN_TIMEOUT

    last_error: Exception | None = None
    last_adv: AdvertisementData | None = None

    if pre_reset and config.GATT_PRE_RESET and sys.platform == "win32":
        await reset_windows_gatt_before_connect(
            address, name, scan_timeout=min(3.0, scan_timeout)
        )

    for attempt in range(1, retries + 1):
        print(f"\nBLE connect {attempt}/{retries}...", flush=True)

        ble_device, adv = await scan_fresh_for_connect(address, name, timeout=scan_timeout)
        last_adv = adv
        if ble_device is None:
            print(
                "  Not advertising. Chrono power ON?",
                flush=True,
            )
            last_error = RuntimeError("device not advertising")
            await asyncio.sleep(2.0)
            continue

        print(f"  Scan OK: {ble_device.name} ({ble_device.address})", flush=True)

        if sys.platform == "win32":
            cached = False
        elif attempt == 1:
            cached = use_cached_services
        elif attempt == 2:
            cached = False
        else:
            cached = True

        client = _bleak_client(
            ble_device,
            timeout=timeout,
            pair=pair,
            use_cached_services=cached,
        )
        try:
            await client.connect()
            await asyncio.sleep(3.0 if sys.platform == "win32" else 0.5)
            if client.is_connected:
                print(f"  OK: {ble_device.name} ({ble_device.address})\n", flush=True)
                return client, adv
            print("  Failed: disconnected after connect", flush=True)
            last_error = RuntimeError("disconnected after connect")
        except (TimeoutError, asyncio.CancelledError) as exc:
            last_error = TimeoutError(str(exc) or "connect timed out")
            print("  Failed: connection timed out (GATT)", flush=True)
        except Exception as exc:
            last_error = exc
            print(f"  Failed: {type(exc).__name__}: {exc}", flush=True)

        await release_ble_session(client, cooldown=config.GATT_COOLDOWN_SECONDS)

    _print_connect_help()
    raise TimeoutError("BLE connect failed") from last_error


def _print_connect_help() -> None:
    print(
        "\nConnection failed. Try:\n"
        "  1. Power-cycle the chrono (OFF -> wait 10s -> ON)\n"
        "  2. run.bat scan  - confirm AC6000 appears with good RSSI\n"
        "  3. Do NOT pair in Windows Settings - use run.bat only\n"
        "  4. Toggle Windows Bluetooth OFF then ON\n",
        file=sys.stderr,
        flush=True,
    )


async def disconnect_ble(client: BleakClient | None) -> None:
    await release_ble_session(client, cooldown=0)
