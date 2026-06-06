"""
AC6000MKIII BT 用設定。

discover.py でサービス／特性を確認したあと、ここまたは環境変数に UUID を設定してください。
"""

from __future__ import annotations

import os
import platform

# デバイス検索（名前の部分一致。複数指定可）
DEVICE_NAME_KEYWORDS = ("AC6000", "ACETECH", "acetech", "Acetech")

_IS_DARWIN = platform.system() == "Darwin"

# 接続先を固定（scan.py / scan.bat で表示されたアドレスを設定）
# macOS: UUID 形式（例 EBE66AE4-...） / Windows: MAC 形式（例 AA:BB:CC:DD:EE:FF）
_MACOS_DEFAULT_ADDRESS = "EBE66AE4-258C-5EAB-2DD5-F6EAE3784EA5"
# Windows: scan.bat で表示された MAC を設定すると接続が安定しやすい
_WINDOWS_DEFAULT_ADDRESS = "00:A0:50:35:03:AA"
_DEFAULT_ADDRESS = (
    _MACOS_DEFAULT_ADDRESS if _IS_DARWIN else _WINDOWS_DEFAULT_ADDRESS
)

DEVICE_ADDRESS = os.environ.get("CHRONO_ADDRESS", "").strip() or _DEFAULT_ADDRESS

# macOS のみ: scan で UUID アドレスのときは False（実 MAC 形式のとき True）
# 環境変数 CHRONO_MACOS_USE_BDADDR は後方互換のため残す
_use_bdaddr_env = (
    os.environ.get("CHRONO_USE_BDADDR", "")
    or os.environ.get("CHRONO_MACOS_USE_BDADDR", "")
)
USE_BDADDR = _use_bdaddr_env.lower() in ("1", "true", "yes")
# 後方互換エイリアス
MACOS_USE_BDADDR = USE_BDADDR

# デバイス表示名（アドレス検索のフォールバック）
DEVICE_NAME = os.environ.get("CHRONO_DEVICE_NAME", "AC6000 BT-1731").strip()

# AC6000 BT-1731 で確認した GATT UUID
_NOTIFY_DEFAULT = "3337e46e-f79e-4ff5-9a49-77c36d170c62"
_WRITE_DEFAULT = "9c6aa1ee-b4b9-44a1-ba45-1558c9109b4c"
NOTIFY_CHAR_UUID = os.environ.get("CHRONO_NOTIFY_UUID", "").strip() or _NOTIFY_DEFAULT
WRITE_CHAR_UUID = os.environ.get("CHRONO_WRITE_UUID", "").strip() or _WRITE_DEFAULT

# 接続直後に送る初期化コマンド（hex文字列、スペース可）。不要なら空
HANDSHAKE_HEX = os.environ.get("CHRONO_HANDSHAKE_HEX", "").strip()

# スタンバイ開始コマンド（未確認・空なら送信しない）
STANDBY_HEX = os.environ.get("CHRONO_STANDBY_HEX", "").strip()

# BLE 接続（Windows は GATT 取得が遅いことがある）
CONNECT_TIMEOUT = float(
    os.environ.get("CHRONO_CONNECT_TIMEOUT", "45" if not _IS_DARWIN else "30")
)
CONNECT_RETRIES = int(os.environ.get("CHRONO_CONNECT_RETRIES", "3"))
# 接続直前スキャン（MAC 固定時は短くてよい）
CONNECT_SCAN_TIMEOUT = float(
    os.environ.get("CHRONO_CONNECT_SCAN_TIMEOUT", "5" if not _IS_DARWIN else "8")
)

# GATT 接続前に Windows の古いセッションを解放（1 回目失敗対策）
GATT_PRE_RESET = os.environ.get("CHRONO_GATT_PRE_RESET", "1" if not _IS_DARWIN else "0").lower() in (
    "1",
    "true",
    "yes",
)
# GATT 失敗後: Windows が前回セッションを解放するまで待つ
GATT_COOLDOWN_SECONDS = float(
    os.environ.get("CHRONO_GATT_COOLDOWN", "5" if not _IS_DARWIN else "2")
)
GATT_SETUP_CYCLES = int(os.environ.get("CHRONO_GATT_SETUP_CYCLES", "3"))

# BLE スキャン（Windows はアドバタイズ間隔が長いことがある）
SCAN_TIMEOUT = float(os.environ.get("CHRONO_SCAN_TIMEOUT", "15" if not _IS_DARWIN else "12"))
SCAN_RETRIES = int(os.environ.get("CHRONO_SCAN_RETRIES", "2"))

# 待受中のキープアライブ間隔（秒）。0 で無効。Windows BLE のアイドル切断対策
KEEPALIVE_SECONDS = float(os.environ.get("CHRONO_KEEPALIVE_SECONDS", "30"))
