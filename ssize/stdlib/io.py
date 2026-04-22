"""
io.ssz  –  Python implementation of the S-SIZE I/O library.
Provides file reading/writing and console I/O.
"""
import sys
import os
from ssize.runtime import SSZList


def _read_line(prompt: str = "") -> str:
    try:
        return input(str(prompt))
    except EOFError:
        return ""


def _write(text) -> None:
    print(str(text), end="")


def _writeln(text="") -> None:
    print(str(text))


def _read_file(path: str) -> str:
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        return ""


def _write_file(path: str, content: str) -> bool:
    try:
        with open(str(path), "w", encoding="utf-8") as f:
            f.write(str(content))
        return True
    except OSError:
        return False


def _append_file(path: str, content: str) -> bool:
    try:
        with open(str(path), "a", encoding="utf-8") as f:
            f.write(str(content))
        return True
    except OSError:
        return False


def _file_exists(path: str) -> bool:
    return os.path.isfile(str(path))


def _delete_file(path: str) -> bool:
    try:
        os.remove(str(path))
        return True
    except OSError:
        return False


def register(env, interpreter) -> None:
    env.define("readLine",   _read_line)
    env.define("write",      _write)
    env.define("writeln",    _writeln)
    env.define("readFile",   _read_file)
    env.define("writeFile",  _write_file)
    env.define("appendFile", _append_file)
    env.define("fileExists", _file_exists)
    env.define("deleteFile", _delete_file)
