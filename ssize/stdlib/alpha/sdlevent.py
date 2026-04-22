"""ssize/stdlib/alpha/sdlevent.py — SDL event state, backed by sdlplugin engine."""
import sys
from .sdlplugin import SDLKey, _e as _sdl_engine

class _SEState:
    def __init__(self):
        self.end=False; self.full=False; self.fullReal=False
        self.aspect=False; self.borders=True; self.resizable=False
        self.fskip=False; self.Key=SDLKey
        # Per-key state properties (accessed as se.escKey, se.upKey, etc.)
        self._props={
            "escKey":"ESCAPE","upKey":"UP","downKey":"DOWN",
            "leftKey":"LEFT","rightKey":"RIGHT","returnKey":"RETURN",
            "spaceKey":"SPACE","backspaceKey":"BACKSPACE",
            "aKey":"a","bKey":"b","cKey":"c","dKey":"d","eKey":"e",
            "fKey":"f","gKey":"g","hKey":"h","iKey":"i","jKey":"j",
            "kKey":"k","lKey":"l","mKey":"m","nKey":"n","oKey":"o",
            "pKey":"p","qKey":"q","rKey":"r","sKey":"s","tKey":"t",
            "uKey":"u","vKey":"v","wKey":"w","xKey":"x","yKey":"y",
            "zKey":"z","apostropheKey":"APOSTROPHE","commaKey":"COMMA",
            "periodKey":"PERIOD","slashKey":"SLASH","semicolonKey":"SEMICOLON",
            "backslashKey":"BACKSLASH","leftbracketKey":"LEFTBRACKET",
            "rightbracketKey":"RIGHTBRACKET","minusKey":"MINUS","equalsKey":"EQUALS",
            "f1Key":"F1","f2Key":"F2","f3Key":"F3","f4Key":"F4","f5Key":"F5",
            "f6Key":"F6","f7Key":"F7","f8Key":"F8","f9Key":"F9","f10Key":"F10",
            "f11Key":"F11","f12Key":"F12","deleteKey":"DELETE","insertKey":"INSERT",
            "homeKey":"HOME","endKey":"END","pageupKey":"PAGEUP","pagedownKey":"PAGEDOWN",
            "debugkey":"F9","tabKey":"TAB","lshiftKey":"LSHIFT","rshiftKey":"RSHIFT",
        }

    def __getattr__(self,name):
        # For se.xKey style accesses
        if name in self.__dict__.get("_props",{}):
            return _sdl_engine._key_state.get(self._props[name].upper(),False)
        raise AttributeError(name)

    def event(self,fps=60):
        self.end = _sdl_engine._quit or self.end
        return _sdl_engine.event(fps) and not self.end

    def eventKeys(self): return []

_se=_SEState()

def register(env,interpreter):
    env.define("end",False); env.define("full",False)
    env.define("fullReal",False); env.define("aspect",False)
    env.define("borders",True); env.define("resizable",False)
    env.define("fskip",False); env.define("Key",SDLKey)
    env.define("event",_se.event); env.define("eventKeys",_se.eventKeys)
    # Register all key state properties
    for k,v in _se._props.items():
        kname=v.upper()
        env.define(k, lambda kk=kname: _sdl_engine._key_state.get(kk,False))
    env.define("_state",_se)
