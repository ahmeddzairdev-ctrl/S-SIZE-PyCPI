"""
ssize/stdlib/alpha/lua.py — Full Lua bridge with IKEMEN API registration.
Uses lupa (LuaJIT) if installed. Registers all C-functions Lua scripts expect.
"""
from __future__ import annotations
import sys, os
from typing import Any, Dict, List, Optional

try:
    import lupa
    _LUPA = True
except ImportError:
    _LUPA = False


class LuaState:
    def __init__(self):
        self._stack: List[Any] = []
        self._globals: Dict[str, Any] = {}
        self._lua = None
        self._ikemen_root: str = "."
        if _LUPA:
            try:
                self._lua = lupa.LuaRuntime(unpack_returned_tuples=True)
            except Exception as e:
                print(f"[lua] lupa init failed: {e}", file=sys.stderr)

    # ── Stack operations ────────────────────────────────────────────────────
    def isNumber(self, i):  return isinstance(self._at(i), (int, float))
    def isString(self, i):  return isinstance(self._at(i), str)
    def isBoolean(self, i): return isinstance(self._at(i), bool)
    def isNil(self, i):     return self._at(i) is None
    def isTable(self, i):   return isinstance(self._at(i), dict)
    def toNumber(self, i):
        try:    return float(self._at(i) or 0)
        except: return 0.0
    def toString(self, i):  v = self._at(i); return str(v) if v is not None else ""
    def toBoolean(self, i): return bool(self._at(i))
    def toRef(self, i):     return self._at(i)
    def getTop(self):       return len(self._stack)
    def pushNumber(self, n): self._stack.append(float(n) if n is not None else 0.0)
    def pushString(self, s): self._stack.append(str(s) if s is not None else "")
    def pushBoolean(self, b): self._stack.append(bool(b))
    def pushRef(self, r):   self._stack.append(r)
    def pushNil(self):      self._stack.append(None)
    def _at(self, idx):
        if not self._stack: return None
        try:    return self._stack[idx-1] if idx > 0 else self._stack[idx]
        except: return None

    # ── Function registration ───────────────────────────────────────────────
    def register(self, name: str, func) -> None:
        """Register a Python callable as a Lua global function."""
        self._globals[str(name)] = func
        if self._lua:
            try:
                fn = func
                def lua_wrapper(*args):
                    sub = LuaState()
                    for a in args:
                        if isinstance(a, bool):     sub._stack.append(a)
                        elif isinstance(a, (int,float)): sub._stack.append(a)
                        elif isinstance(a, str):    sub._stack.append(a)
                        elif a is None:             sub._stack.append(None)
                        else:                       sub._stack.append(a)
                    ret = [0]
                    result = None
                    try:
                        fn(sub, ret)
                        if ret[0] > 0 and sub._stack:
                            result = sub._stack[-ret[0]]
                    except Exception as e:
                        pass
                    return result
                self._lua.globals()[str(name)] = lua_wrapper
            except Exception:
                pass

    def setIkemenRoot(self, root: str) -> None:
        self._ikemen_root = root
        # Register all IKEMEN C-functions now that we know the root
        self._register_ikemen_api()

    def _register_ikemen_api(self) -> None:
        """Register all IKEMEN engine C-functions into this Lua state."""
        try:
            engine_dir = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            if engine_dir not in sys.path:
                sys.path.insert(0, engine_dir)
            from engine.lua_api import register_all
            register_all(self, None, self._ikemen_root)
        except Exception as e:
            print(f"[lua] API registration failed: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()

    # ── Script execution ────────────────────────────────────────────────────
    def runFile(self, path: str) -> bool:
        p = str(path) if path else ""
        # Resolve relative to ikemen root
        if not os.path.isabs(p):
            p = os.path.join(self._ikemen_root, p)
        if not os.path.isfile(p):
            print(f"[lua] File not found: {p}", file=sys.stderr)
            self.pushString(f"cannot open '{p}': No such file")
            return False
        print(f"[lua] Running: {p}", file=sys.stderr)
        if self._lua:
            try:
                src = open(p, "r", encoding="utf-8", errors="replace").read()
                self._lua.execute(src)
                return True
            except Exception as e:
                print(f"[lua] Error in {p}: {e}", file=sys.stderr)
                self.pushString(str(e))
                return False
        else:
            print(f"[lua] No Lua runtime — lupa not installed", file=sys.stderr)
            self.pushString("lupa not available")
            return False

    def runString(self, code: str) -> bool:
        if self._lua:
            try:
                self._lua.execute(str(code))
                return True
            except Exception as e:
                self.pushString(str(e))
                return False
        return False


def register(env, interpreter) -> None:
    env.define("State", lambda *a: LuaState())
