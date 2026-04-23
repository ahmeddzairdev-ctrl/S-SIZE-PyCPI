"""
math.ssz — Python implementation of the S-SIZE math library.
None-safe and variadic: handles min(x), max(x,y,z), None args, etc.
"""
import math as _math


def _n(x):
    """Coerce a value to float, treating None as 0."""
    return 0.0 if x is None else float(x)


def _safe_min(*args):
    """min(a) or min(a,b,...) — None treated as +inf so real values win."""
    vals = [_math.inf if a is None else float(a) for a in args]
    return min(vals) if vals else 0.0


def _safe_max(*args):
    """max(a) or max(a,b,...) — None treated as -inf so real values win."""
    vals = [-_math.inf if a is None else float(a) for a in args]
    return max(vals) if vals else 0.0


def register(env, interpreter) -> None:
    env.define("sin",    lambda x: _math.sin(_n(x)))
    env.define("cos",    lambda x: _math.cos(_n(x)))
    env.define("tan",    lambda x: _math.tan(_n(x)))
    env.define("asin",   lambda x: _math.asin(max(-1.0, min(1.0, _n(x)))))
    env.define("acos",   lambda x: _math.acos(max(-1.0, min(1.0, _n(x)))))
    env.define("atan",   lambda x: _math.atan(_n(x)))
    env.define("atan2",  lambda y, x: _math.atan2(_n(y), _n(x)))
    env.define("sqrt",   lambda x: _math.sqrt(max(0.0, _n(x))))
    env.define("pow",    lambda b, e: _n(b) ** _n(e))
    env.define("exp",    lambda x: _math.exp(_n(x)))
    env.define("log",    lambda x: _math.log(max(1e-300, _n(x))))
    env.define("log10",  lambda x: _math.log10(max(1e-300, _n(x))))
    env.define("floor",  lambda x: int(_math.floor(_n(x))))
    env.define("ceil",   lambda x: int(_math.ceil(_n(x))))
    env.define("round",  lambda x: int(round(_n(x))))
    env.define("abs",    lambda x: abs(_n(x)))
    env.define("min",    _safe_min)
    env.define("max",    _safe_max)
    env.define("clamp",  lambda x, lo, hi: max(_n(lo), min(_n(hi), _n(x))))
    env.define("sign",   lambda x: (1 if _n(x) > 0 else -1 if _n(x) < 0 else 0))
    env.define("pi",     _math.pi)
    env.define("e",      _math.e)
    env.define("inf",    _math.inf)
    env.define("nan",    _math.nan)
    env.define("isNaN",  lambda x: _math.isnan(_n(x)))
    env.define("isInf",  lambda x: _math.isinf(_n(x)))
