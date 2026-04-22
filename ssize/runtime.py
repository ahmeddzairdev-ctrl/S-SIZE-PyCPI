"""
S-SIZE (SSZ) Runtime types and environment.

Provides:
  - SSZValue          wrapped typed value
  - SSZArray          reference type (^T)
  - SSZList           appendable list (%T)
  - SSZObject         class instance
  - SSZEnum           enum value
  - SSZFunction       function closure
  - SSZAnonFunc       anonymous function closure
  - Environment       scope chain (local / member / global)
  - type_coerce()     auto-cast between numeric types
  - ssz_tostr()       '' operator
"""

from __future__ import annotations
import struct, threading
from typing import Any, Optional, Dict, List, Callable


# ---------------------------------------------------------------------------
# Type descriptors (simplified - just names as strings)
# ---------------------------------------------------------------------------

SIGNED_INT_TYPES   = {"bytes", "short", "int", "long", "index"}
UNSIGNED_INT_TYPES = {"ubyte", "ushort", "uint", "ulong"}
FLOAT_TYPES        = {"float", "double"}
INT_TYPES          = SIGNED_INT_TYPES | UNSIGNED_INT_TYPES

# Bit-width limits for clamping
_LIMITS: Dict[str, tuple] = {
    "bytes":  (-128,            127),
    "ubyte":  (0,               255),
    "short":  (-32768,          32767),
    "ushort": (0,               65535),
    "int":    (-2**31,          2**31 - 1),
    "uint":   (0,               2**32 - 1),
    "long":   (-2**63,          2**63 - 1),
    "ulong":  (0,               2**64 - 1),
    "index":  (-2**63,          2**63 - 1),
    "char":   (0,               0xFFFF),
}


def clamp(value: int, type_name: str) -> int:
    lo, hi = _LIMITS[type_name]
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# SSZ Values
# ---------------------------------------------------------------------------

class SSZValue:
    """A typed SSZ value wrapping a Python object."""
    __slots__ = ("type_name", "value")

    def __init__(self, type_name: str, value: Any):
        self.type_name = type_name
        self.value     = value

    def __repr__(self) -> str:
        return f"SSZValue({self.type_name}, {self.value!r})"

    def copy(self) -> "SSZValue":
        return SSZValue(self.type_name, self.value)


class SSZArray:
    """Reference type (^T) – a fixed-size mutable array + mutex."""
    def __init__(self, elem_type: str, data: List[Any]):
        self.elem_type = elem_type
        self.data      = list(data)
        self._mutex    = threading.Lock()
        self.typeid    = id(elem_type)

    @property
    def length(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return f"SSZArray({self.elem_type}[{self.length}])"

    def slice(self, start: int, end: int) -> "SSZArray":
        return SSZArray(self.elem_type, self.data[start:end+1])


class SSZList(SSZArray):
    """Appendable list (%T)."""
    def __init__(self, elem_type: str, data: List[Any] = None):
        super().__init__(elem_type, data or [])

    def append_val(self, val: Any) -> None:
        self.data.append(val)

    def extend_to(self, new_len: int, fill: Any = None) -> None:
        while len(self.data) < new_len:
            self.data.append(fill)

    def __repr__(self) -> str:
        return f"SSZList({self.elem_type}[{self.length}])"


class SSZObject:
    """Instance of a &ClassName."""
    def __init__(self, class_name: str):
        self.class_name = class_name
        self.fields: Dict[str, Any] = {}

    def __repr__(self) -> str:
        return f"<{self.class_name} object>"


class SSZEnum:
    """An enum value."""
    def __init__(self, enum_name: str, member: str, ordinal: int):
        self.enum_name = enum_name
        self.member    = member
        self.ordinal   = ordinal

    def __repr__(self) -> str:
        return f"{self.enum_name}.{self.member}"


class SSZFunction:
    """A declared function (closure over its definition environment)."""
    def __init__(self, name: str, params, body, env: "Environment",
                 ret_type_name: str = "void", is_builtin: bool = False,
                 builtin_fn: Optional[Callable] = None):
        self.name        = name
        self.params      = params      # List[Param] from AST
        self.body        = body        # List[Node] from AST
        self.env         = env         # defining scope
        self.ret_type    = ret_type_name
        self.is_builtin  = is_builtin
        self.builtin_fn  = builtin_fn

    def __repr__(self) -> str:
        return f"<SSZFunction {self.name}>"


class SSZAnonFunc(SSZFunction):
    """Anonymous function (can capture locals)."""
    def __init__(self, params, body, env: "Environment",
                 capture: Dict[str, Any] = None):
        super().__init__("<anon>", params, body, env)
        self.capture = capture or {}

    def __repr__(self) -> str:
        return "<SSZAnonFunc>"


class SSZModule:
    """A loaded library module (result of lib import)."""
    def __init__(self, name: str, env: "Environment"):
        self.name = name
        self.env  = env

    def get(self, attr: str) -> Any:
        # Look in this module's own local vars first
        if attr in self.env._vars:
            return self.env._vars[attr]
        # Fall back to global
        return self.env.get_global(attr)

    def __repr__(self) -> str:
        return f"<SSZModule {self.name}>"


# ---------------------------------------------------------------------------
# Type coercion and auto-casting
# ---------------------------------------------------------------------------

def type_coerce(value: Any, src_type: str, dst_type: str) -> Any:
    """
    Automatically cast value from src_type to dst_type.
    SSZ auto-casts: signed int → unsigned int → float (left-to-right widening).
    """
    if value is None:
        return default_value(dst_type)
    if src_type == dst_type:
        return value

    # to float
    if dst_type in FLOAT_TYPES:
        return float(value)

    # to integer types
    if dst_type in INT_TYPES:
        v = int(value) if isinstance(value, float) else int(value)
        if dst_type in _LIMITS:
            v = clamp(v, dst_type)
        return v

    # to bool
    if dst_type == "bool":
        return bool(value)

    # to char
    if dst_type == "char":
        if isinstance(value, int):
            return chr(clamp(value, "char"))
        if isinstance(value, str) and len(value) == 1:
            return value
        return "\0"

    return value


def explicit_cast(value: Any, src_type: str, dst_type: str) -> Any:
    """Explicit (type) cast.  None is treated as zero/empty/false."""
    # Guard: None casts to the zero-value of the target type
    if value is None:
        return default_value(dst_type)
    if dst_type == "char":
        if isinstance(value, int):
            return chr(value & 0xFFFF)
        if isinstance(value, str):
            return value
        return "\0"
    if dst_type == "bool":
        return bool(value)
    if dst_type in FLOAT_TYPES:
        try:    return float(value)
        except: return 0.0
    if dst_type in INT_TYPES:
        try:
            v = int(float(value)) if isinstance(value, float) else int(value)
        except (TypeError, ValueError):
            v = 0
        if dst_type in _LIMITS:
            v = clamp(v, dst_type)
        return v
    return value


def ssz_tostr(value: Any, type_name: str = "") -> str:
    """'' operator – convert value to string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Match C-style representation where possible
        s = repr(value)
        if "e" not in s and "E" not in s:
            return s
        return s
    if isinstance(value, str):
        return value
    if isinstance(value, SSZObject):
        return repr(value)
    if isinstance(value, (SSZArray, SSZList)):
        return repr(value)
    if isinstance(value, SSZEnum):
        return repr(value)
    return str(value)


def default_value(type_name: str) -> Any:
    """Return the zero/default value for a type."""
    if type_name in INT_TYPES:
        return 0
    if type_name in FLOAT_TYPES:
        return 0.0
    if type_name == "bool":
        return False
    if type_name == "char":
        return "\0"
    if type_name == "void":
        return None
    return None


# ---------------------------------------------------------------------------
# Return / Break / Continue signals (Python exceptions used for control flow)
# ---------------------------------------------------------------------------

class ReturnSignal(Exception):
    def __init__(self, value: Any = None):
        self.value = value

class BreakSignal(Exception):
    pass

class ContinueSignal(Exception):
    pass

class ElseJumpSignal(Exception):
    pass


# ---------------------------------------------------------------------------
# Environment (scope chain)
# ---------------------------------------------------------------------------

class Environment:
    """
    A lexical scope frame.

    SSZ has three levels:
      - local      : regular variable inside a function
      - member     : `varname  (backtick prefix)
      - global     : .varname  (dot prefix)

    The chain is: local → function-scope → ... → global
    """

    def __init__(self, parent: Optional["Environment"] = None,
                 global_env: Optional["Environment"] = None):
        self._vars:   Dict[str, Any] = {}
        self.parent   = parent
        # The root (global) environment. All frames share the same global_env ref.
        self.global_env: "Environment" = global_env if global_env is not None else self

    # --- Variable lookup ---

    def get(self, name: str) -> Any:
        """Look up a local variable (searches up the chain)."""
        if name in self._vars:
            return self._vars[name]
        if self.parent is not None:
            return self.parent.get(name)
        # 'self' is only valid inside class methods; return None instead of crashing
        if name == "self":
            return None
        raise NameError(f"Undefined variable: '{name}'")

    def set(self, name: str, value: Any) -> None:
        """Assign to the nearest enclosing frame that has this variable."""
        if name in self._vars:
            self._vars[name] = value
            return
        if self.parent is not None:
            try:
                self.parent.set(name, value)
                return
            except NameError:
                pass
        # If not found anywhere, define in current scope (first-use define)
        self._vars[name] = value

    def define(self, name: str, value: Any) -> None:
        """Define a new variable in the current (local) scope."""
        self._vars[name] = value

    # --- Global variable access (.varname) ---

    def get_global(self, name: str) -> Any:
        return self.global_env._vars.get(name)

    def set_global(self, name: str, value: Any) -> None:
        self.global_env._vars[name] = value

    def define_global(self, name: str, value: Any) -> None:
        self.global_env._vars[name] = value

    # --- Convenience ---

    def child(self) -> "Environment":
        """Create a new child scope."""
        return Environment(parent=self, global_env=self.global_env)

    def has_local(self, name: str) -> bool:
        return name in self._vars

    def all_names(self) -> list:
        return list(self._vars.keys())
