"""One-shot TTS (Windows: SAPI first, then pyttsx3)."""
from __future__ import annotations

import base64
import sys

LANG_JAPANESE = 0x411


def _pick_japanese_voice(speaker) -> bool:
    try:
        voices = speaker.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = (v.GetDescription() or "").lower()
            try:
                lang = int(v.GetAttribute("Language"))
            except (TypeError, ValueError):
                lang = 0
            if lang == LANG_JAPANESE or "japanese" in desc or "ja-" in desc or "日本" in desc:
                speaker.Voice = v
                return True
    except Exception:
        pass
    return False


def _speak_sapi(text: str) -> bool:
    import win32com.client

    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    _pick_japanese_voice(speaker)
    speaker.Speak(text, 0)
    return True


def _speak_pyttsx3(text: str) -> bool:
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
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    text = base64.b64decode(sys.argv[1].encode("ascii")).decode("utf-8")
    if not text.strip():
        return 1

    errors: list[str] = []
    try:
        if _speak_sapi(text):
            return 0
    except Exception as exc:
        errors.append(f"SAPI: {exc}")

    try:
        if _speak_pyttsx3(text):
            return 0
    except Exception as exc:
        errors.append(f"pyttsx3: {exc}")

    print("TTS failed: " + "; ".join(errors), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
