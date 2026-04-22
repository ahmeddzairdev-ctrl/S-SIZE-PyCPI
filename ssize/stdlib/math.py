"""
math.ssz  –  Python implementation of the S-SIZE math library.
Provides common mathematical functions.
"""
import math as _math


def register(env, interpreter) -> None:
    env.define("sin",   lambda x: _math.sin(float(x)))
    env.define("cos",   lambda x: _math.cos(float(x)))
    env.define("tan",   lambda x: _math.tan(float(x)))
    env.define("asin",  lambda x: _math.asin(float(x)))
    env.define("acos",  lambda x: _math.acos(float(x)))
    env.define("atan",  lambda x: _math.atan(float(x)))
    env.define("atan2", lambda y, x: _math.atan2(float(y), float(x)))
    env.define("sqrt",  lambda x: _math.sqrt(float(x)))
    env.define("pow",   lambda b, e: float(b) ** float(e))
    env.define("exp",   lambda x: _math.exp(float(x)))
    env.define("log",   lambda x: _math.log(float(x)))
    env.define("log10", lambda x: _math.log10(float(x)))
    env.define("floor", lambda x: int(_math.floor(float(x))))
    env.define("ceil",  lambda x: int(_math.ceil(float(x))))
    env.define("round", lambda x: int(round(float(x))))
    env.define("abs",   lambda x: abs(x))
    env.define("min",   lambda a, b: a if a < b else b)
    env.define("max",   lambda a, b: a if a > b else b)
    env.define("pi",    _math.pi)
    env.define("e",     _math.e)
    env.define("inf",   _math.inf)
    env.define("nan",   _math.nan)
    env.define("isNaN", lambda x: _math.isnan(float(x)))
    env.define("isInf", lambda x: _math.isinf(float(x)))
