#!/usr/bin/env python3
"""
AC6000 へ Python から接続し、初期化 Write 列を送る。

成功の目安: 通知に ACK (AA05410088)、クロノの Bluetooth マーク点灯。

--protocol aa（既定）: READ_KEY + 初期化列
--protocol v4: 旧バイナリ解析形式（実機では BT マーク未点灯の報告あり）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from bleak.exc import BleakError

import config
from ble_connect import disconnect_ble, release_ble_session
from ble_gatt import open_notify_session
from acetech_protocol import (
    CHAR_NOTIFY,
    CHAR_WRITE,
    KEEPALIVE_PACKET,
    ac6000_connect_packets,
    ac6000_bind_packets,
    manufacturer_key_bytes,
    parse_acetech_notify,
)
from discover import find_device_with_adv, print_device_not_found_help


def _configure_stdio_utf8() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_configure_stdio_utf8()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-unit-bind",
        action="store_true",
        help="UNIT_BIND / SCU_BIND のみ試す",
    )
    parser.add_argument(
        "--protocol",
        choices=("aa", "v4"),
        default="aa",
        help="aa=標準プロトコル（既定）, v4=旧バイナリ解析形式",
    )
    parser.add_argument(
        "--skip-post-init",
        action="store_true",
        help="READ_KEY のみ送り、接続後の初期化列は送らない",
    )
    parser.add_argument(
        "--with-get-key",
        action="store_true",
        help="v4 のみ: GetKey (K) を追加（aa では常に READ_KEY を送る）",
    )
    parser.add_argument(
        "--bind-mode",
        choices=("steps", "events"),
        default="steps",
        help="v4 のみ: steps / events",
    )
    parser.add_argument("--delay", type=float, default=0.35, help="コマンド間隔秒")
    parser.add_argument(
        "--key-p1",
        type=int,
        default=None,
        help="GetKey 第1バイト (未指定時はアドバタイズ manufacturer から)",
    )
    parser.add_argument("--key-p2", type=int, default=None, help="GetKey 第2バイト")
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=60.0,
        help="初期化送信後に同一接続で通知待受する秒数 (既定: 60)",
    )
    parser.add_argument(
        "--listen-forever",
        action="store_true",
        help="初期化送信後、Ctrl+C まで同一接続で待受",
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="BULLET_SPEED 受信時に数値を音声読み上げ（Windows: pyttsx3 / macOS: say）",
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help="OS ペアリングを試行（Windows で初回接続できないとき）",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=None,
        help=f"接続タイムアウト秒 (既定: {config.CONNECT_TIMEOUT})",
    )
    parser.add_argument(
        "--connect-retries",
        type=int,
        default=None,
        help=f"接続リトライ回数 (既定: {config.CONNECT_RETRIES})",
    )
    args = parser.parse_args()

    if args.speak:
        from speech import enqueue_speed, stop_speech_worker
    else:
        enqueue_speed = None  # type: ignore[assignment]
        stop_speech_worker = None  # type: ignore[assignment]

    address = (config.DEVICE_ADDRESS or "").strip()
    dev_name = config.DEVICE_NAME or None
    adv = None

    if address:
        print(
            f"接続先 (固定): {dev_name or '?'} ({address})",
            flush=True,
        )
        print("  初回スキャンを省略し、接続直前にスキャンします。\n", flush=True)
    else:
        device, adv = await find_device_with_adv()
        if device is None:
            print_device_not_found_help()
            sys.exit(1)
        address = device.address
        dev_name = device.name or dev_name

    k1, k2 = manufacturer_key_bytes(adv)
    if (k1, k2) == (0, 0):
        k1, k2 = 0x93, 0x05
    if args.key_p1 is not None:
        k1 = args.key_p1
    if args.key_p2 is not None:
        k2 = args.key_p2

    if args.protocol == "aa":
        packets = ac6000_connect_packets(
            k1, k2, include_post_init=not args.skip_post_init
        )
    else:
        packets = ac6000_bind_packets(
            k1, k2, include_get_key=args.with_get_key, bind_mode=args.bind_mode
        )
        if args.only_unit_bind:
            packets = [(l, p) for l, p in packets if "BIND" in l]

    try:
        await _run_session(args, address, dev_name, adv, k1, k2, packets, enqueue_speed)
    finally:
        if args.speak and stop_speech_worker is not None:
            stop_speech_worker()


async def _reconnect_session(
    client,
    address: str,
    dev_name: str | None,
    args,
    packets,
    callback,
    *,
    connect_timeout: float,
    connect_retries: int,
) -> object:
    print("\n  接続が切れました。再接続中...", flush=True)
    await release_ble_session(client)
    client, _adv = await open_notify_session(
        address,
        callback,
        name=dev_name,
        device=None,
        pair=args.pair,
        connect_timeout=connect_timeout,
        connect_retries=connect_retries,
        scan_timeout=config.CONNECT_SCAN_TIMEOUT,
    )
    await _send_init_packets(client, args, packets)
    print("  再接続完了。\n", flush=True)
    return client


async def _send_init_packets(client, args, packets) -> None:
    print(f"--- 送信 ({args.protocol}) ---\n")
    write_uuid = config.WRITE_CHAR_UUID or CHAR_WRITE
    last_label = ""
    for label, payload in packets:
        if label != last_label:
            print(f"\n## {label}")
            last_label = label
        try:
            await client.write_gatt_char(write_uuid, payload, response=True)
        except Exception:
            await client.write_gatt_char(write_uuid, payload, response=False)
        print(f"  → {payload.hex(' ')}")
        wait = 2.0 if "READ_KEY" in label else args.delay
        await asyncio.sleep(wait)


async def _send_keepalive(client) -> None:
    """リンク維持用の軽い Write（弾速測定には影響しない想定）。"""
    if not client.is_connected or config.KEEPALIVE_SECONDS <= 0:
        return
    write_uuid = config.WRITE_CHAR_UUID or CHAR_WRITE
    try:
        await client.write_gatt_char(write_uuid, KEEPALIVE_PACKET, response=False)
    except Exception:
        pass


async def _listen_forever_loop(
    client,
    address: str,
    dev_name: str | None,
    args,
    packets,
    callback,
    received,
    stats,
    *,
    connect_timeout: float,
    connect_retries: int,
) -> object:
    print(
        "\n--- 同一接続で待受中（Ctrl+C で終了）---\n"
        "このまま BB を撃って BULLET_SPEED 通知を確認してください。\n",
        flush=True,
    )
    elapsed = 0
    last_reconnect_at = 0.0
    last_keepalive_at = time.monotonic()
    while True:
        await asyncio.sleep(5)
        elapsed += 5
        connected = client.is_connected
        print(
            f"  … {elapsed}s | 接続={connected} | 受信={len(received)} | "
            f"ACK={stats['ack']} | BULLET_SPEED={stats['speed']}",
            flush=True,
        )
        if connected:
            if (
                config.KEEPALIVE_SECONDS > 0
                and time.monotonic() - last_keepalive_at >= config.KEEPALIVE_SECONDS
            ):
                await _send_keepalive(client)
                last_keepalive_at = time.monotonic()
            continue
        now = time.monotonic()
        if now - last_reconnect_at < 15.0:
            continue
        last_reconnect_at = now
        try:
            client = await _reconnect_session(
                client,
                address,
                dev_name,
                args,
                packets,
                callback,
                connect_timeout=connect_timeout,
                connect_retries=connect_retries,
            )
        except Exception as exc:
            print(f"  再接続失敗: {exc}", flush=True)
    return client


async def _run_session(
    args: argparse.Namespace,
    address: str,
    dev_name: str | None,
    adv,
    k1: int,
    k2: int,
    packets,
    enqueue_speed,
) -> None:
    received: list[bytes] = []
    stats = {"ack": 0, "speed": 0}

    def on_notify(_h: int, data: bytearray) -> None:
        payload = bytes(data)
        received.append(payload)
        info = parse_acetech_notify(payload)
        if info.get("event") == "ACK":
            stats["ack"] += 1
        if info.get("event") == "BULLET_SPEED":
            stats["speed"] += 1
            display = info.get("speed_display")
            speed_raw = info.get("speed_raw")
            if isinstance(display, str):
                print(f"\n🎯 {display} メートル毎秒\n", flush=True)
                if args.speak and enqueue_speed is not None:
                    if isinstance(speed_raw, int):
                        enqueue_speed(speed_raw)
                    else:
                        enqueue_speed(display)
        print(f"\n<<< 通知 {info}\n", flush=True)

    print(f"接続: {dev_name or '?'} ({address})")
    if args.speak:
        print("Speech: ON (--speak). Readout when BULLET_SPEED is received.\n")
    if adv and adv.manufacturer_data:
        print(f"manufacturer_data: {adv.manufacturer_data}")
    print(f"プロトコル: {args.protocol}")
    print(f"READ_KEY バイト: p1=0x{k1:02x} p2=0x{k2:02x}")
    if args.protocol == "aa":
        expect = bytes([0xAA, 0x06, ord("K"), k1, k2, k1])
        print(f"READ_KEY 送信予定: {expect.hex(' ')}")
        if expect.hex() != "aa064b930593" and (k1, k2) != (0x93, 0x05):
            print(
                "警告: 成功例は aa 06 4b 93 05 93。"
                "不一致なら --key-p1 147 --key-p2 5 を試してください。\n",
                flush=True,
            )
        else:
            print("形式: AA + LEN + cmd。電源ボタン操作は不要。\n")
    elif args.with_get_key:
        print("警告: v4 GetKey 後の電源ボタンでクロノが OFF になる場合があります。\n")

    connect_timeout = (
        float(args.connect_timeout)
        if args.connect_timeout is not None
        else config.CONNECT_TIMEOUT
    )
    connect_retries = (
        int(args.connect_retries)
        if args.connect_retries is not None
        else config.CONNECT_RETRIES
    )

    client, connect_adv = await open_notify_session(
        address,
        on_notify,
        name=dev_name,
        device=None,
        pair=args.pair,
        connect_timeout=connect_timeout,
        connect_retries=connect_retries,
        scan_timeout=config.CONNECT_SCAN_TIMEOUT,
    )
    if connect_adv is not None and connect_adv.manufacturer_data:
        adv = connect_adv
        ck1, ck2 = manufacturer_key_bytes(adv)
        if (ck1, ck2) != (0, 0) and (ck1, ck2) != (k1, k2):
            k1, k2 = ck1, ck2
            print(f"READ_KEY (接続スキャン): p1=0x{k1:02x} p2=0x{k2:02x}", flush=True)
            if args.protocol == "aa":
                packets = ac6000_connect_packets(
                    k1, k2, include_post_init=not args.skip_post_init
                )
            else:
                packets = ac6000_bind_packets(
                    k1, k2, include_get_key=args.with_get_key, bind_mode=args.bind_mode
                )
    try:
        await _send_init_packets(client, args, packets)

        if args.listen_forever:
            client = await _listen_forever_loop(
                client,
                address,
                dev_name,
                args,
                packets,
                on_notify,
                received,
                stats,
                connect_timeout=connect_timeout,
                connect_retries=connect_retries,
            )
        else:
            wait_sec = max(1.0, float(args.listen_seconds))
            print(
                f"\n--- 同一接続で {wait_sec:.0f} 秒待機（撃って通知を確認）---\n",
                flush=True,
            )
            elapsed = 0.0
            step = 5.0
            last_keepalive_at = time.monotonic()
            while elapsed < wait_sec:
                await asyncio.sleep(min(step, wait_sec - elapsed))
                elapsed += step
                if (
                    client.is_connected
                    and config.KEEPALIVE_SECONDS > 0
                    and time.monotonic() - last_keepalive_at >= config.KEEPALIVE_SECONDS
                ):
                    await _send_keepalive(client)
                    last_keepalive_at = time.monotonic()
                print(
                    f"  … {int(min(elapsed, wait_sec))}s | 接続={client.is_connected} | "
                    f"受信={len(received)} | ACK={stats['ack']} | BULLET_SPEED={stats['speed']}",
                    flush=True,
                )
        try:
            if client.is_connected:
                await client.stop_notify(CHAR_NOTIFY)
        except Exception as e:
            print(f"通知停止時の警告: {e}", flush=True)
    finally:
        await disconnect_ble(client)

    print(f"\n受信パケット数: {len(received)}")
    if stats["speed"] > 0:
        print("BULLET_SPEED 通知を受信しました。Python 直結で測定可能です。")
    elif received:
        print(
            "BLE データ受信 OK（ACK/設定応答あり）。"
            "速度通知は未受信なので待受時間を延ばして再試行してください。"
        )
    else:
        print(
            "まだ通知なし / BT マークなし。\n"
            "  1. クロノを OFF → 10 秒 → ON して再実行\n"
            "  2. run.bat scan で AC6000 が見えるか確認\n"
            "  3. v4 再試行: python bind_init.py --protocol v4 --with-get-key"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n終了しました。")
        sys.exit(0)
    except (TimeoutError, BleakError, OSError) as exc:
        print(f"\nエラー: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n予期しないエラー: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
