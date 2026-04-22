"""
file.ssz — file I/O library used throughout the IKEMEN engine.

The real engine wraps platform file handles; we use Python's built-in.
"""
import os
import sys
from pathlib import Path
from ssize.runtime import SSZObject, SSZList, SSZArray


class SSZFile:
    """&file.File — an open file handle."""

    def __init__(self):
        self._fh = None
        self._path = ""
        self._mode = "r"

    def open(self, path: str, mode: str = "r") -> "SSZFile":
        self._path = str(path)
        # Translate SSZ modes to Python modes
        py_mode = {"rb": "rb", "wb": "wb", "ab": "ab",
                   "r": "r",  "w": "w",  "a": "a"}.get(str(mode), "r")
        try:
            self._fh = open(self._path, py_mode)
        except OSError:
            self._fh = None
        return self

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def read(self) -> str:
        if not self._fh:
            return ""
        try:
            data = self._fh.read()
            return data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        except OSError:
            return ""

    def readAry(self) -> SSZList:
        data = self.read()
        lst = SSZList("ubyte", [ord(c) & 0xFF for c in data])
        return lst

    def write(self, text) -> int:
        if not self._fh:
            return 0
        try:
            s = str(text)
            self._fh.write(s)
            return len(s)
        except OSError:
            return 0

    def writeAry(self, arr) -> int:
        if not self._fh:
            return 0
        try:
            if isinstance(arr, (SSZArray, SSZList)):
                data = bytes(int(x) & 0xFF for x in arr.data)
            elif isinstance(arr, (bytes, bytearray)):
                data = bytes(arr)
            else:
                data = str(arr).encode("utf-8")
            self._fh.write(data)
            return len(data)
        except OSError:
            return 0

    def seek(self, pos: int) -> None:
        if self._fh:
            try:
                self._fh.seek(int(pos))
            except OSError:
                pass

    def tell(self) -> int:
        if self._fh:
            try:
                return self._fh.tell()
            except OSError:
                pass
        return 0

    def size(self) -> int:
        if not self._path:
            return 0
        try:
            return os.path.getsize(self._path)
        except OSError:
            return 0

    def isOpen(self) -> bool:
        return self._fh is not None


def _make_file(*args) -> SSZFile:
    f = SSZFile()
    if args:
        path = str(args[0])
        mode = str(args[1]) if len(args) > 1 else "r"
        f.open(path, mode)
    return f


def register(env, interpreter) -> None:
    env.define("File",    _make_file)

    # Utility: check if file exists
    env.define("exists",  lambda p: os.path.isfile(str(p)))
    env.define("isDir",   lambda p: os.path.isdir(str(p)))
    env.define("mkdir",   lambda p: os.makedirs(str(p), exist_ok=True))
    env.define("remove",  lambda p: os.remove(str(p)) if os.path.isfile(str(p)) else None)
    env.define("rename",  lambda a, b: os.rename(str(a), str(b)))
    env.define("listDir", lambda p: SSZList("string",
        [x for x in os.listdir(str(p))] if os.path.isdir(str(p)) else []))
    env.define("cwd",     lambda: os.getcwd())
    env.define("sep",     os.sep)
