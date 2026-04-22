"""
engine/snd.py — MUGEN SND (Sound File) parser and playback.

SND format:
  Signature: "ElecbyteSnd\0"  (12 bytes)
  version: 4 bytes
  num_sounds: uint32
  first_offset: uint32
  Each subfile: offset(4) + length(4) + group(2) + idx(2) + 32-byte header
  Data: WAV audio (PCM or MP3)
"""

import struct
import io
import wave
import threading
from typing import Dict, Tuple, Optional

SoundKey = Tuple[int, int]


class SNDFile:
    """Loaded SND file."""

    def __init__(self):
        self.sounds: Dict[SoundKey, bytes] = {}   # (group, idx) → WAV bytes

    def get(self, group: int, idx: int) -> Optional[bytes]:
        return self.sounds.get((group, idx))

    def __len__(self) -> int:
        return len(self.sounds)


def load(path: str) -> SNDFile:
    """Load a MUGEN SND file."""
    snd = SNDFile()
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return snd

    if not data[:12].startswith(b"ElecbyteSnd"):
        return snd

    num_sounds   = struct.unpack_from("<I", data, 16)[0]
    first_offset = struct.unpack_from("<I", data, 20)[0]

    pos = first_offset
    for _ in range(num_sounds):
        if pos + 32 > len(data):
            break
        next_off = struct.unpack_from("<I", data, pos)[0]
        sub_len  = struct.unpack_from("<I", data, pos + 4)[0]
        group    = struct.unpack_from("<H", data, pos + 8)[0]
        idx      = struct.unpack_from("<H", data, pos + 10)[0]

        audio = data[pos + 32: pos + 32 + sub_len]
        snd.sounds[(group, idx)] = audio

        pos = next_off if next_off != 0 else (pos + 32 + sub_len)

    return snd


# ── Simple audio playback (without external deps) ───────────────────────────

_audio_lock = threading.Lock()
_playing: Dict[str, threading.Thread] = {}


def _try_play(wav_bytes: bytes, channel: str = "sfx") -> None:
    """Play WAV bytes in a background thread (best-effort)."""
    try:
        # Try using the `simpleaudio` package if available
        import simpleaudio as sa
        wav_obj = sa.WaveObject.from_wave_read(wave.open(io.BytesIO(wav_bytes)))
        with _audio_lock:
            _playing[channel] = wav_obj.play()
    except ImportError:
        pass  # No audio library — silent mode


def play(snd: SNDFile, group: int, idx: int, channel: str = "sfx") -> None:
    """Play a sound from an SNDFile."""
    audio = snd.get(group, idx)
    if audio is None:
        return
    t = threading.Thread(target=_try_play, args=(audio, channel), daemon=True)
    t.start()


def stop(channel: str = "sfx") -> None:
    """Stop a playing channel."""
    with _audio_lock:
        play_obj = _playing.pop(channel, None)
        if play_obj and hasattr(play_obj, "stop"):
            play_obj.stop()
