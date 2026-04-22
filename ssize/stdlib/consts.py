"""
consts.ssz — compile-time integer/float constants used by the SSZ runtime.

In the real engine these are defined in the C++ SSZ runtime.
Provides:  int_t::MIN/MAX,  Signed<T>::MIN/MAX,  Unsigned<T>::MIN/MAX
"""
import sys

# Flat integer limit constants
INT_MIN   = -(2**31)
INT_MAX   =   2**31 - 1
LONG_MIN  = -(2**63)
LONG_MAX  =   2**63 - 1
UINT_MAX  =   2**32 - 1
ULONG_MAX =  2**64 - 1

# Type-limit namespaces (returned as dicts for :: scope access)
int_t   = {"MIN": INT_MIN,   "MAX": INT_MAX}
long_t  = {"MIN": LONG_MIN,  "MAX": LONG_MAX}
uint_t  = {"MIN": 0,         "MAX": UINT_MAX}
ulong_t = {"MIN": 0,         "MAX": ULONG_MAX}
short_t = {"MIN": -32768,    "MAX": 32767}
ushort_t= {"MIN": 0,         "MAX": 65535}
bytes_t = {"MIN": -128,      "MAX": 127}
ubyte_t = {"MIN": 0,         "MAX": 255}
float_t = {"MIN": -3.4e38,   "MAX": 3.4e38}
double_t= {"MIN": -1.8e308,  "MAX": 1.8e308}
index_t = {"MIN": LONG_MIN,  "MAX": LONG_MAX}
bool_t  = {"MIN": 0,         "MAX": 1}
char_t  = {"MIN": 0,         "MAX": 0xFFFF}

def _signed(type_name: str) -> dict:
    m = {"bytes": bytes_t, "short": short_t, "int": int_t,
         "long": long_t,   "index": index_t}
    return m.get(type_name, int_t)

def _unsigned(type_name: str) -> dict:
    m = {"ubyte": ubyte_t, "ushort": ushort_t, "uint": uint_t,
         "ulong": ulong_t, "char": char_t}
    return m.get(type_name, uint_t)


def register(env, interpreter) -> None:
    from ssize.runtime import SSZObject

    # Expose each type namespace as a dict
    for name, ns in [
        ("int_t", int_t), ("long_t", long_t), ("uint_t", uint_t),
        ("ulong_t", ulong_t), ("short_t", short_t), ("ushort_t", ushort_t),
        ("bytes_t", bytes_t), ("ubyte_t", ubyte_t), ("float_t", float_t),
        ("double_t", double_t), ("index_t", index_t), ("bool_t", bool_t),
        ("char_t", char_t),
    ]:
        env.define(name, ns)

    # Signed<T> and Unsigned<T> template-like helpers
    # In SSZ they're used as .consts.Signed!int?::MIN etc.
    # We expose them as callables returning the right dict
    env.define("Signed",   _signed)
    env.define("Unsigned", _unsigned)
