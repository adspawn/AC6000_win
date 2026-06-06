"""
AC6000 BT BLE プロトコル。

実機で確認した送受信形式（推奨）:
  - AA + LEN + [ASCII cmd] + payload + 末尾1バイト（シーケンス／鍵バイト）
  - 例: READ_KEY  AA064B930593  →  K + key1 + key2 + key1
  - 例: ACK       AA05410088

旧バイナリ解析の v4 形式 ([0x85/0xAA][0x01] + [0xFF] + 16B + cmd) は bind_init --protocol v4 でのみ使用。
"""

from __future__ import annotations

import enum
import struct
from typing import Iterable

from bleak.backends.scanner import AdvertisementData


# GATT (実機 discover 済み)
SERVICE_NOTIFY = "5cde0c3d-7b1d-4352-94bb-02269c9f42b5"
SERVICE_WRITE = "53c47fe1-6c22-4ea6-99c7-7b6325ec75b9"
CHAR_NOTIFY = "3337e46e-f79e-4ff5-9a49-77c36d170c62"
CHAR_WRITE = "9c6aa1ee-b4b9-44a1-ba45-1558c9109b4c"

# writeCmd2 前の 16 バイト定数 (0x1000fb0f50)
_HEADER_16 = bytes([0x10, 0, 0, 0, 0, 0, 0, 0, 0x18, 0, 0, 0, 0, 0, 0, 0])
# SCU_BIND 等で使う別テンプレ (0x1000fa0190)
_HEADER_16_S = bytes([0x05, 0, 0, 0, 0, 0, 0, 0, 0x06, 0, 0, 0, 0, 0, 0, 0])
_LEAD_FF = bytes([0xFF])

STX_NORMAL = 0xAA
STX_ENABLE_KEY = 0x85


class BleEvent(enum.IntEnum):
    """AC6000 BLE イベント列挙。"""

    DEVICE_NOT_CONNECTED = 1
    LOW_BATT = 2
    FW_CUR_IS_LATEST = 3
    NEW_FW_AVALIBLE = 4
    FAIL = 5
    TIMEOUT = 6
    CONNECTION_ESTABLISHED = 7
    DISCONNECTED = 8
    CMD_R = 9
    CMD_ACK = 10
    CMD_NAK = 11
    CMD_KEY_ACK = 12
    VERSION_GOT = 13
    VERSION_GOT_2 = 14
    VERSION_COMPLETE = 15
    FW_DOWNLOADING = 16
    FW_DOWNLOAD_COMPLETE = 17
    UNIT_BIND = 18
    SCU_BIND = 19
    GET_RECORD_INDEX = 20
    READ_KEY_DONE = 21
    CONNECTED = 22
    CONNECTING = 23
    SHOW_KEY_CHECKING = 24
    CMD_KEY_FAIL = 25
    SERIAL_GOT = 26
    GAME_MODE_READY = 27
    BULLET_EVENT = 28
    BATTERY_EVENT = 29
    LOW_BATTERY = 30
    ONLINE_STATUS = 31
    ITARGET_GAME_STATUS = 32
    SET_TARGET_ID_ACK = 33
    GET_ACCESSORIES_STATUS = 34
    GET_RECORD_COUNT = 35
    SHOT_LOG_READY = 36
    AMMO_SETTING_UPDATE = 37
    SPEED_TEST_RECORD_READY = 38
    SELF_TEST_DONE = 39
    GET_BATT = 40
    MOVING_TARGET_MILEAGE = 41
    TARGET_UPDATE_STATUS = 42
    READ_STATUS = 43
    SELF_TEST = 44
    COIN_NUMBER = 45
    SYSTEM_MODE = 46
    BLEDATA = 47
    ALARM = 48


class GDataCmd(enum.IntEnum):
    CLEAR_SPEED_TEST_RECORD = 0
    GET_AMMO_INDEX = 1
    FW_UPDATE_SEND_SIZE = 2
    GAME_STATUS_REPORT = 3
    FW_UPDATE_SEND_FILE = 4
    READ_BULLET_SETTING = 5
    READ_G_MODE = 6


# 接続直後の Write 列（実機で確認済み）
CONNECT_INIT_AFTER_KEY_HEX: tuple[str, ...] = (
    "AA0647000190",
    "AA0647000291",
    "AA0647000392",
    "AA0647000493",
    "AA0647000594",
    "AA0647010191",
    "AA095300000000019F",
    "AA0647010292",
    "AA0647010393",
    "AA0647010494",
    "AA0647010595",
    "AA055A00A1",
    "AA04498F",
    "AA0462A8",
    "AA0556009D",
)

# 待受中のキープアライブ（初期化列の末尾と同じ）
KEEPALIVE_PACKET = bytes.fromhex("AA0556009D")


def encode_read_key_aa(key_p1: int, key_p2: int) -> bytes:
    """READ_KEY。ログ: AA064B930593（末尾=key_p1）。"""
    k1, k2 = key_p1 & 0xFF, key_p2 & 0xFF
    return bytes([0xAA, 0x06, ord("K"), k1, k2, k1])


def ac6000_connect_packets(
    key_p1: int,
    key_p2: int,
    *,
    include_post_init: bool = True,
) -> list[tuple[str, bytes]]:
    """READ_KEY → (任意) 接続後初期化 Write 列。"""
    steps: list[tuple[str, bytes]] = [
        ("READ_KEY (K)", encode_read_key_aa(key_p1, key_p2)),
    ]
    if include_post_init:
        for hx in CONNECT_INIT_AFTER_KEY_HEX:
            steps.append((f"INIT {hx[:8]}…", bytes.fromhex(hx)))
    return steps


def manufacturer_key_bytes(adv: AdvertisementData | None) -> tuple[int, int]:
    """
    READ_KEY (AA064B930593) 用の 2 バイト。

    AC6000 実機アドバタイズ {1280: 08 93 05 00 00} では blob[1], blob[2] = 93, 05。
    （blob[3:5]=05,00 を key にすると ACK なし）
    """
    if adv is None or not adv.manufacturer_data:
        return 0, 0
    blob = b"".join(adv.manufacturer_data.values())
    if len(blob) >= 4 and blob[0] == 0x08:
        return blob[1], blob[2]
    if len(blob) >= 4 and (blob[2] or blob[3]):
        return blob[2], blob[3]
    if len(blob) >= 5:
        chunk = blob[3:8]
        if chunk[0] or chunk[1]:
            return chunk[0], chunk[1]
    if len(blob) >= 2:
        return blob[-2], blob[-1]
    return 0, 0


def build_cmd_body(
    cmd_char: str,
    p1: int,
    p2: int,
    *,
    header: bytes = _HEADER_16,
    with_ff: bool = True,
) -> bytes:
    """[0xFF] + header + [cmd][p1][p2]"""
    body = header + bytes([ord(cmd_char), p1 & 0xFF, p2 & 0xFF])
    return (_LEAD_FF + body) if with_ff else body


def write_cmd2_frame(payload: bytes, *, enable_key: bool = True) -> bytes:
    """writeCmd2: STX + 0x01 + payload"""
    stx = STX_ENABLE_KEY if enable_key else STX_NORMAL
    return bytes([stx, 0x01]) + payload


def encode_get_key(p1: int, p2: int) -> bytes:
    """validateKey / GetKey 相当 ('K')。enableKey=False, delay=500ms がバイナリ既定。"""
    return write_cmd2_frame(build_cmd_body("K", p1, p2), enable_key=False)


def encode_event_y(
    event: BleEvent | int,
    p1: int = 0,
    *,
    enable_key: bool = True,
) -> bytes:
    """イベント送信 ('Y')。第3バイト = p2（従来は BleEvent ID を想定）。"""
    return write_cmd2_frame(
        build_cmd_body("Y", p1, int(event)),
        enable_key=enable_key,
    )


def encode_bind_step_y(step: int, p1: int = 0) -> bytes:
    """
    unitBind 内部テーブル用の 'Y' 送信（バイナリ: 0x10004dba0 に w0=1..5 で呼び出し）。

    BleEvent.UNIT_BIND(18) とは別のインデックスの可能性が高い。
    """
    return encode_event_y(step, p1, enable_key=True)


def encode_gdata(cmd: GDataCmd | int, unit: int = 0) -> bytes:
    """parseGData / ac6000PostInit ('G')。byte3 = cmd + 1。"""
    return write_cmd2_frame(
        build_cmd_body("G", unit, int(cmd) + 1),
        enable_key=True,
    )


def encode_scu_bind(p1: int, p2: int) -> bytes:
    """SCU_BIND ('S') 用テンプレート。"""
    return write_cmd2_frame(
        build_cmd_body("S", p1, p2, header=_HEADER_16_S),
        enable_key=True,
    )


def ac6000_bind_packets(
    key_p1: int = 0,
    key_p2: int = 0,
    *,
    include_get_key: bool = False,
    bind_mode: str = "steps",
) -> list[tuple[str, bytes]]:
    """
    純正 ac6000_bind / ac6000PostInit 相当の送信列（解析版 v4）。

    bind_mode:
      - "steps" (既定): unitBind 解析どおり Y コマンド p2=1..5
      - "events": 旧想定 BleEvent ID (18,19,22…) — 実機では BT マーク未点灯の報告あり
    """
    steps: list[tuple[str, bytes]] = []
    if include_get_key:
        steps.append(("GET_KEY (K)", encode_get_key(key_p1, key_p2)))

    if bind_mode == "events":
        steps.extend(
            [
                ("UNIT_BIND (Y ev18)", encode_event_y(BleEvent.UNIT_BIND)),
                ("SCU_BIND (Y ev19)", encode_event_y(BleEvent.SCU_BIND)),
                ("CONNECTED (Y ev22)", encode_event_y(BleEvent.CONNECTED)),
            ]
        )
    else:
        for n in range(1, 6):
            steps.append((f"BIND_STEP (Y p2={n})", encode_bind_step_y(n)))

    steps.extend(
        [
            ("SCU_BIND (S)", encode_scu_bind(0, 0)),
            ("GET_BATT (Y ev40)", encode_event_y(BleEvent.GET_BATT)),
            ("READ_STATUS (Y ev43)", encode_event_y(BleEvent.READ_STATUS)),
            ("READ_BULLET_SETTING (G)", encode_gdata(GDataCmd.READ_BULLET_SETTING)),
            ("READ_G_MODE (G)", encode_gdata(GDataCmd.READ_G_MODE)),
        ]
    )
    return steps


# --- 旧候補（互換・デバッグ用） ---


def encode_write_cmd_v1(
    event: BleEvent | int,
    *,
    enable_key: bool = True,
    delay: int = 0,
) -> bytes:
    ev = int(event)
    return bytes([ev & 0xFF, 1 if enable_key else 0, delay & 0xFF])


def encode_write_cmd_v2(
    event: BleEvent | int,
    *,
    enable_key: bool = True,
    delay: int = 0,
) -> bytes:
    return bytes([0x52, int(event) & 0xFF, 1 if enable_key else 0, delay & 0xFF])


def encode_write_cmd_v3(event: BleEvent | int) -> bytes:
    return bytes([int(event) & 0xFF])


def encode_gdata_v1(cmd: GDataCmd | int, unit: int = 0) -> bytes:
    return bytes([0x47, int(cmd) & 0xFF, unit & 0xFF])


def decode_speed_display(speed_raw: int) -> str:
    """
    BLE の速度 raw（0.01 m/s 単位）をクロノ画面と同じ 0.1 m/s 表示へ。

    実測: float の四捨五入 (.1f) だと 63.59 m/s が 63.6 になり、
    クロノの 63.5 とずれる。整数の切り捨て (raw // 10) が一致する。
    """
    tenths = speed_raw // 10
    return f"{tenths // 10}.{tenths % 10}"


def parse_acetech_notify(data: bytes) -> dict:
    """通知ペイロードの簡易解析。"""
    out: dict = {"raw_hex": data.hex(" "), "len": len(data)}
    if not data:
        return out

    out["byte0"] = data[0]
    if data[0] == 0xAA and len(data) >= 3:
        out["format"] = "aa"
        out["len_field"] = data[1]
        ch = data[2]
        if 0x41 <= ch <= 0x5A:
            out["cmd_char"] = chr(ch)
        if ch == 0x41:
            out["event"] = "ACK"
        elif ch == 0x52:
            out["event"] = "BULLET_SPEED"
            if len(data) >= 7:
                speed_raw = int.from_bytes(data[5:7], "little")
                out["speed_raw"] = speed_raw
                out["speed_ms"] = speed_raw / 100.0
                out["speed_display"] = decode_speed_display(speed_raw)
        elif ch == 0x4E:
            out["event"] = "CMD_NAK"
    elif len(data) >= 3:
        ch = data[2]
        if 0x41 <= ch <= 0x5A:
            out["cmd_char"] = chr(ch)

    if data[0] == BleEvent.BLEDATA:
        out["event"] = "BLEDATA"
    elif data[0] == BleEvent.CMD_ACK:
        out["event"] = "CMD_ACK"
    elif data[0] == BleEvent.CMD_R:
        out["event"] = "CMD_R"
    elif data[0] == BleEvent.BULLET_EVENT:
        out["event"] = "BULLET_EVENT"

    if len(data) >= 3:
        u16 = struct.unpack_from("<H", data, 1)[0]
        out["u16_le@1"] = u16
        out["speed_guess_ms_v1"] = u16 * 0.1

    if len(data) >= 4:
        f = struct.unpack_from("<f", data, 0)[0]
        if 5 < f < 500:
            out["float32_le@0"] = f

    if len(data) >= 4:
        f = struct.unpack_from("<f", data, 1)[0]
        if 5 < f < 500:
            out["float32_le@1"] = f

    return out
