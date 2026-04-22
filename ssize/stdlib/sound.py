"""
ssize/stdlib/sound.py — Sound playback stub.

Maps the sound.ssz API used by the engine. The real engine uses
SDL_mixer for audio. We use the wave+audioop stdlib modules for basic
PCM playback, and stub the rest.
"""
import sys
import os
import threading
import io
from typing import Optional, Dict

# Optional: use simpleaudio if available
try:
    import simpleaudio as _sa
    _HAS_SA = True
except ImportError:
    _HAS_SA = False


class _SoundChannel:
    """A single playback channel."""
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop   = threading.Event()

    def play(self, wav_bytes: bytes, loop: bool = False) -> None:
        self._stop.set()
        self._stop = threading.Event()
        stop = self._stop
        def _run():
            if not _HAS_SA:
                return
            try:
                import wave
                wf = wave.open(io.BytesIO(wav_bytes))
                frames = wf.readframes(wf.getnframes())
                n_ch   = wf.getnchannels()
                w      = wf.getsampwidth()
                fr     = wf.getframerate()
                obj = _sa.WaveObject(frames, n_ch, w, fr)
                p = obj.play()
                while not stop.is_set():
                    if not p.is_playing():
                        if loop:
                            p = obj.play()
                        else:
                            break
                    import time; time.sleep(0.05)
                p.stop()
            except Exception:
                pass
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class _SoundSystem:
    def __init__(self):
        self._bgm   = _SoundChannel()
        self._sfx: Dict[int, _SoundChannel] = {}
        self._vol_bgm = 1.0
        self._vol_sfx = 1.0
        self._vol_gl  = 1.0

    def play_bgm(self, path: str, loop: bool = True) -> None:
        if not path or not os.path.isfile(str(path)):
            return
        try:
            with open(str(path), "rb") as f:
                data = f.read()
            self._bgm.play(data, loop)
        except Exception as e:
            print(f"[snd] BGM error: {e}", file=sys.stderr)

    def stop_bgm(self) -> None:
        self._bgm.stop()

    def fade_in_bgm(self, path: str, ms: int = 1000) -> None:
        self.play_bgm(path)

    def fade_out_bgm(self, ms: int = 1000) -> None:
        self.stop_bgm()

    def play_sfx(self, snd_file, group: int, idx: int,
                 channel: int = 0, loop: bool = False) -> None:
        """Play a sound from an SNDFile object."""
        try:
            from engine.snd import SNDFile
            if isinstance(snd_file, SNDFile):
                wav = snd_file.get(group, idx)
                if wav:
                    ch = self._sfx.setdefault(channel, _SoundChannel())
                    ch.play(wav, loop)
        except Exception:
            pass

    def stop_sfx(self, channel: int = 0) -> None:
        if channel in self._sfx:
            self._sfx[channel].stop()

    def stop_all(self) -> None:
        self._bgm.stop()
        for ch in self._sfx.values():
            ch.stop()

    def set_vol(self, gl: float = 1.0, sfx: float = 1.0,
                bgm: float = 1.0) -> None:
        self._vol_gl  = float(gl)
        self._vol_sfx = float(sfx)
        self._vol_bgm = float(bgm)


_sys = _SoundSystem()


def register(env, interpreter) -> None:
    s = _sys
    env.define("playBGM",    s.play_bgm)
    env.define("stopBGM",    s.stop_bgm)
    env.define("fadeInBGM",  s.fade_in_bgm)
    env.define("fadeOutBGM", s.fade_out_bgm)
    env.define("playSFX",    s.play_sfx)
    env.define("stopSFX",    s.stop_sfx)
    env.define("stopAll",    s.stop_all)
    env.define("setVolume",  s.set_vol)
    env.define("System",     lambda *a: s)
