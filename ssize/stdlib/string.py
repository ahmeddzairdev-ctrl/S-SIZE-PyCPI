"""
string.ssz  –  Python implementation of the S-SIZE string library.

Provides common string utility functions used in .ssz scripts.
"""
import math


def _i_to_s(value) -> str:
    """iToS(n)  –  integer to string."""
    return str(int(value))


def _f_to_s(value, decimals: int = 6) -> str:
    """fToS(n)  –  float to string."""
    return f"{float(value):.{int(decimals)}f}"


def _s_to_i(s: str) -> int:
    """sToI(s)  –  string to integer."""
    try:
        return int(s.strip())
    except ValueError:
        return 0


def _s_to_f(s: str) -> float:
    """sToF(s)  –  string to float."""
    try:
        return float(s.strip())
    except ValueError:
        return 0.0


def _str_len(s: str) -> int:
    """strLen(s)  –  string length."""
    return len(str(s))


def _str_cat(*args) -> str:
    """strCat(a, b, …)  –  concatenate strings."""
    return "".join(str(a) for a in args)


def _substr(s: str, start: int, length: int) -> str:
    """subStr(s, start, length)."""
    s = str(s)
    return s[int(start):int(start) + int(length)]


def _str_find(s: str, sub: str) -> int:
    """strFind(s, sub)  –  index of sub in s, or -1."""
    return str(s).find(str(sub))


def _str_upper(s: str) -> str:
    return str(s).upper()


def _str_lower(s: str) -> str:
    return str(s).lower()


def _str_replace(s: str, old: str, new: str) -> str:
    return str(s).replace(str(old), str(new))


def _bool_to_s(v) -> str:
    return "true" if v else "false"


def register(env, interpreter) -> None:
    """Called by the interpreter when loading this module."""
    env.define("iToS",      _i_to_s)
    env.define("fToS",      _f_to_s)
    env.define("sToI",      _s_to_i)
    env.define("sToF",      _s_to_f)
    env.define("strLen",    _str_len)
    env.define("strCat",    _str_cat)
    env.define("subStr",    _substr)
    env.define("strFind",   _str_find)
    env.define("strUpper",  _str_upper)
    env.define("strLower",  _str_lower)
    env.define("strReplace",_str_replace)
    env.define("boolToS",   _bool_to_s)
