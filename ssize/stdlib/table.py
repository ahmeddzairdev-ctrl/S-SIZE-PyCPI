"""
table.ssz — generic hash table used by the engine.

The real engine implements IntTable as a C++ template class.
Here we provide a Python dict-backed implementation.

Usage in engine:  &tbl.IntTable!int, ^/char? hotkeys;
"""
from ssize.runtime import SSZObject


class SSZTable:
    """IntTable / generic table: int key → any value."""

    def __init__(self):
        self._data: dict = {}

    def get(self, key) -> any:
        k = int(key) if isinstance(key, (int, float)) else key
        result = self._data.get(k)
        # Return a single-element SSZArray-like wrapper if needed
        return result if result is not None else None

    def set(self, key, value) -> None:
        k = int(key) if isinstance(key, (int, float)) else key
        self._data[k] = value

    def has(self, key) -> bool:
        k = int(key) if isinstance(key, (int, float)) else key
        return k in self._data

    def remove(self, key) -> None:
        k = int(key) if isinstance(key, (int, float)) else key
        self._data.pop(k, None)

    def clear(self) -> None:
        self._data.clear()

    def size(self) -> int:
        return len(self._data)

    def keys(self):
        from ssize.runtime import SSZList
        lst = SSZList("int", list(self._data.keys()))
        return lst


def _make_table(*args) -> SSZTable:
    return SSZTable()


def register(env, interpreter) -> None:
    # The engine uses: &tbl.IntTable!int,^/char? hotkeys;
    # We expose IntTable as a constructor function
    env.define("IntTable", _make_table)

    # Also expose a generic Table alias
    env.define("Table", _make_table)
