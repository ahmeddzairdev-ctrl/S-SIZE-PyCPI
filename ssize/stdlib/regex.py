"""
regex.ssz — regular expression support (used by font.ssz).
"""
import re as _re


def _match(pattern: str, string: str) -> bool:
    try:
        return bool(_re.search(str(pattern), str(string)))
    except Exception:
        return False


def _find(pattern: str, string: str) -> str:
    try:
        m = _re.search(str(pattern), str(string))
        return m.group(0) if m else ""
    except Exception:
        return ""


def _replace(pattern: str, repl: str, string: str) -> str:
    try:
        return _re.sub(str(pattern), str(repl), str(string))
    except Exception:
        return str(string)


def _split(pattern: str, string: str):
    from ssize.runtime import SSZList
    try:
        parts = _re.split(str(pattern), str(string))
        return SSZList("string", parts)
    except Exception:
        from ssize.runtime import SSZList
        return SSZList("string", [str(string)])


def register(env, interpreter) -> None:
    env.define("match",   _match)
    env.define("find",    _find)
    env.define("replace", _replace)
    env.define("split",   _split)
