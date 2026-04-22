"""
thread.ssz — threading primitives.

Used by command.ssz for network input (online play).
The real engine wraps SDL_CreateThread.

We use Python threading here.
"""
import threading
import time
from ssize.runtime import SSZObject


class SSZThread:
    """Represents a running SSZ thread."""

    def __init__(self, fn, args=()):
        self._fn    = fn
        self._args  = args
        self._thread = None
        self._done  = False
        self._result = None

    def start(self) -> None:
        def _run():
            try:
                self._result = self._fn(*self._args)
            except Exception:
                pass
            finally:
                self._done = True

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def join(self, timeout=None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def isAlive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        # Threads can't be forcibly stopped in Python; set done flag
        self._done = True


class SSZMutex:
    """A simple mutex."""

    def __init__(self):
        self._lock = threading.Lock()

    def lock(self) -> None:
        self._lock.acquire()

    def unlock(self) -> None:
        try:
            self._lock.release()
        except RuntimeError:
            pass


def _sleep(ms) -> None:
    time.sleep(float(ms) / 1000.0)


def _create(fn, *args) -> SSZThread:
    t = SSZThread(fn, args)
    t.start()
    return t


def _mutex() -> SSZMutex:
    return SSZMutex()


def register(env, interpreter) -> None:
    env.define("sleep",  _sleep)
    env.define("create", _create)
    env.define("Mutex",  _mutex)
    env.define("Thread", SSZThread)
