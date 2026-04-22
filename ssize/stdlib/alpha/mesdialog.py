"""
alpha/mesdialog.ssz — shared-string message dialog bridge.

Used by ikemen.ssz to pass control strings between the SSZ fight loop
and the Lua system script:
  mes.SetSharedString(:buf:)   → set the shared string
  mes.GetSharedString(:buf=:) → retrieve it (out parameter)
"""
_shared: str = ""


def _set(s="") -> None:
    global _shared
    _shared = str(s) if s is not None else ""


def _get(s="") -> str:
    """GetSharedString — returns the current shared string."""
    global _shared
    return _shared


def register(env, interpreter) -> None:
    env.define("SetSharedString", _set)
    env.define("GetSharedString", _get)
