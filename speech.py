"""Speed TTS: Windows subprocess (SAPI), macOS say, else pyttsx3."""

from __future__ import annotations

import base64
import platform
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from acetech_protocol import decode_speed_display

_q: queue.Queue[Optional[str]] = queue.Queue()
_worker: Optional[threading.Thread] = None
_darwin_voice: Optional[str] = None

_SPEAK_ONCE = Path(__file__).resolve().with_name("_speak_once.py")


def format_speed_ja(speed_raw: int | str) -> str:
    if isinstance(speed_raw, int):
        return f"{decode_speed_display(speed_raw)} メートル毎秒"
    return f"{speed_raw} メートル毎秒"


def speak_test_message() -> bool:
    """起動時テスト用。成功なら True。"""
    return _speak("音声テスト。弾速を読み上げます。")


def _find_darwin_japanese_voice() -> Optional[str]:
    import subprocess as sp

    preferred = ("Kyoko", "Otoya", "Hattori", "Sara", "Yuna")
    try:
        out = sp.check_output(["say", "-v", "?"], text=True, timeout=10)
    except (sp.SubprocessError, OSError):
        return None

    by_name: dict[str, str] = {}
    ja_names: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split()[0]
        by_name[name.lower()] = name
        if "ja_" in line.lower() or " ja " in f" {line.lower()} ":
            ja_names.append(name)

    for key in preferred:
        if key.lower() in by_name:
            return by_name[key.lower()]
    if ja_names:
        return ja_names[0]
    return None


def _speak_darwin(text: str) -> None:
    global _darwin_voice
    if _darwin_voice is None:
        _darwin_voice = _find_darwin_japanese_voice()
    cmd = ["say", text]
    if _darwin_voice:
        cmd = ["say", "-v", _darwin_voice, text]
    subprocess.run(cmd, check=False)


def _speak_windows_subprocess(text: str) -> bool:
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [sys.executable, str(_SPEAK_ONCE), b64],
            check=False,
            timeout=45,
            creationflags=flags,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            return True
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            print(f"[TTS] {err}", flush=True)
        return False
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[TTS] subprocess error: {exc}", flush=True)
        return False


def _speak_pyttsx3_inline(text: str) -> bool:
    import pyttsx3

    try:
        engine = pyttsx3.init(driverName="sapi5")
    except Exception:
        engine = pyttsx3.init()
    try:
        for voice in engine.getProperty("voices"):
            vid = (getattr(voice, "id", None) or "").lower()
            name = getattr(voice, "name", None) or ""
            if "ja" in vid or "japanese" in name.lower() or "日本" in name:
                engine.setProperty("voice", voice.id)
                break
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as exc:
        print(f"[TTS] pyttsx3 error: {exc}", flush=True)
        return False
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def _speak(text: str) -> bool:
    print(f"[TTS] {text}", flush=True)
    if platform.system() == "Darwin":
        _speak_darwin(text)
        return True
    if platform.system() == "Windows":
        if _speak_windows_subprocess(text):
            return True
        return _speak_pyttsx3_inline(text)
    return _speak_pyttsx3_inline(text)


def _worker_loop() -> None:
    while True:
        text = _q.get()
        if text is None:
            _q.task_done()
            break
        try:
            if not _speak(text):
                print("[TTS] Readout failed.", flush=True)
        except Exception as exc:
            print(f"[TTS] warning: {exc}", flush=True)
        finally:
            _q.task_done()


def start_speech_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _worker = threading.Thread(target=_worker_loop, name="tts-worker", daemon=True)
    _worker.start()


def stop_speech_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        return
    _q.put(None)
    _worker.join(timeout=90)
    _worker = None


def enqueue_speed(speed_raw: int | str) -> None:
    start_speech_worker()
    _q.put(format_speed_ja(speed_raw))
