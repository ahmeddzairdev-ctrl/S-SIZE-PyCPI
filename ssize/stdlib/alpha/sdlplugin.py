"""
ssize/stdlib/alpha/sdlplugin.py — Full SDL backend (engine/window.py backed).
"""
from __future__ import annotations
import sys, os, time, threading
from typing import Optional

SDLKey = {
    "UP":273,"DOWN":274,"LEFT":276,"RIGHT":275,"RETURN":13,"ESCAPE":27,
    "SPACE":32,"BACKSPACE":8,"LSHIFT":304,"RSHIFT":303,"LCTRL":306,
    "RCTRL":305,"LALT":308,"RALT":307,"TAB":9,"DELETE":127,
    "F1":282,"F2":283,"F3":284,"F4":285,"F5":286,"F6":287,
    "F7":288,"F8":289,"F9":290,"F10":291,"F11":292,"F12":293,
    "HOME":278,"END":279,"PAGEUP":280,"PAGEDOWN":281,"INSERT":277,
    "SCROLLLOCK":302,"PRINTSCREEN":316,"PAUSE":19,
    "a":97,"b":98,"c":99,"d":100,"e":101,"f":102,"g":103,"h":104,
    "i":105,"j":106,"k":107,"l":108,"m":109,"n":110,"o":111,"p":112,
    "q":113,"r":114,"s":115,"t":116,"u":117,"v":118,"w":119,"x":120,
    "y":121,"z":122,"0":48,"1":49,"2":50,"3":51,"4":52,
    "5":53,"6":54,"7":55,"8":56,"9":57,
    "APOSTROPHE":39,"COMMA":44,"PERIOD":46,"SLASH":47,"SEMICOLON":59,
    "BACKSLASH":92,"LEFTBRACKET":91,"RIGHTBRACKET":93,"MINUS":45,"EQUALS":61,
}
_KEY_NAMES = {v:k for k,v in SDLKey.items()}

class Rect:
    def __init__(self,x=0,y=0,w=0,h=0): self.x=x;self.y=y;self.w=w;self.h=h
    def copy(self): return Rect(self.x,self.y,self.w,self.h)
    def __repr__(self): return f"Rect({self.x},{self.y},{self.w},{self.h})"

class _SDLEngine:
    def __init__(self):
        self.window=None; self.width=960; self.height=720
        self.title="I.K.E.M.E.N"; self.fullscreen=False
        self.aspect=False; self.bordered=True; self.resizable=False
        self.vol_global=0.8; self.vol_se=0.8; self.vol_bgm=0.6
        self._key_state={}; self._last_char=""; self._quit=False

    def init(self,title,w,h,opengl=False,audio=True):
        self.title=str(title) if title else "IKEMEN"
        self.width=int(w) if w else 960; self.height=int(h) if h else 720
        engine_root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        sys.path.insert(0,engine_root)
        try:
            from engine.window import Window
            self.window=Window.create(self.width,self.height,self.title)
            # window.py prints its own "[sdl] Window opened" per backend
        except Exception as e:
            print(f"[sdl] Window failed: {e}, using headless",file=sys.stderr, flush=True)
            try:
                from engine.window import HeadlessWindow
                self.window=HeadlessWindow(self.width,self.height,self.title)
            except Exception as e2:
                print(f"[sdl] Headless also failed: {e2}",file=sys.stderr, flush=True)
                self.window=None
        # Pass IKEMEN root to the Lua state so it can find scripts
        try:
            # Find the actual IKEMEN root (2 levels up from ssz_interpreter)
            # The ikemen root is stored as _IKEMEN_ROOT global if set
            pass  # done via global env
        except Exception:
            pass
        return True  # always return True — lenient mode

    def end(self,*a):
        self._quit=True
        if self.window: self.window.destroy(); self.window=None

    def flip(self):
        if self.window: self.window.flip(); self._pump()
        else: time.sleep(1/60)

    def _pump(self):
        if not self.window: return
        for t,d in self.window.poll_events():
            if t=="quit": self._quit=True
            elif t=="key_down": self._key_state[str(d).upper()]=True; self._last_char=str(d)
            elif t=="key_up":   self._key_state[str(d).upper()]=False

    def event(self,fps=60):
        if self.window: self.window.set_fps(int(fps) if fps else 60)
        self._pump(); return not self._quit

    def key_state(self,sc):
        n=_KEY_NAMES.get(int(sc) if isinstance(sc,int) else sc,"").upper()
        return self._key_state.get(n,False)

    def get_last_char(self): c=self._last_char; self._last_char=""; return c
    def full_screen(self,e): self.fullscreen=bool(e); return self.fullscreen
    def full_screen_mode(self,r): pass
    def keep_aspect(self,k): self.aspect=bool(k)
    def borders(self,b): self.bordered=bool(b)
    def resiz(self,r): self.resizable=bool(r)
    def cursor(self,s): pass
    def window_size(self,w,h): self.width=int(w); self.height=int(h)
    def get_width(self): return self.width
    def get_height(self): return self.height
    def swap(self,*a): pass
    def init_gl(self,*a): return True
    def screenshot(self,p=""):
        if self.window and self.window.frame:
            q=str(p) if p else f"shot_{int(time.time())}.png"
            os.makedirs(os.path.dirname(q) or ".",exist_ok=True)
            self.window.frame.save(q); return True
        return False
    def set_vol(self,gl=0.8,se=0.8,bgm=0.6):
        self.vol_global=float(gl); self.vol_se=float(se); self.vol_bgm=float(bgm)
    def noop(self,*a): pass
    def joybtn(self,*a): return False

_e=_SDLEngine()

def register(env,interpreter):
    env.define("init",_e.init); env.define("End",_e.end)
    env.define("flip",_e.flip); env.define("event",_e.event)
    env.define("InitMugenGl",_e.init_gl); env.define("GlSwapBuffers",_e.swap)
    env.define("KeyState",_e.key_state)
    env.define("JoystickButtonState",_e.joybtn)
    env.define("getLastChar",_e.get_last_char)
    env.define("fullScreen",_e.full_screen)
    env.define("fullScreenMode",_e.full_screen_mode)
    env.define("keepAspectRatio",_e.keep_aspect)
    env.define("windowBorders",_e.borders)
    env.define("windowResizable",_e.resiz)
    env.define("showCursor",_e.cursor)
    env.define("windowSize",_e.window_size)
    env.define("getWidth",_e.get_width); env.define("getHeight",_e.get_height)
    env.define("takeScreenShot",_e.screenshot)
    env.define("setVolume",_e.set_vol)
    env.define("fadeInBGM",_e.noop); env.define("fadeOutBGM",_e.noop)
    env.define("playVideo",_e.noop)
    for n in ["discordInit","discordEnd","discordUpdate","setDiscordDetails",
              "setDiscordState","setDiscordBigImg","setDiscordBigTxt",
              "setDiscordMiniImg","setDiscordMiniTxt","setDiscordPartyID",
              "setDiscordPartySize","setDiscordPartyMax","setDiscordSecretID",
              "setDiscordInstance","setDiscordSecretJoin","setDiscordSecretWatch"]:
        env.define(n,_e.noop)
    env.define("SDLKey",SDLKey)
    env.define("Rect",lambda *a:Rect(*[int(x) for x in a[:4]]))
    env.define("_engine",_e)

# ── Rendering calls (wired from engine/renderer.py) ──────────────────────────
def _register_rendering(env):
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, root)
    try:
        from engine.renderer import (
            GlTexture, decode_png8, render_mugen_gl,
            render_mugen_gl_fc, render_mugen_gl_fc_s,
            render_mugen_zoom, render_mugen_shadow,
            get_render_target, _make_texture,
        )
        env.define("GlTexture",          _make_texture)
        env.define("decodePNG8",         decode_png8)
        env.define("RenderMugenGl",      render_mugen_gl)
        env.define("RenderMugenGlFc",    render_mugen_gl_fc)
        env.define("RenderMugenGlFcS",   render_mugen_gl_fc_s)
        env.define("renderMugenZoom",    render_mugen_zoom)
        env.define("renderMugenShadow",  render_mugen_shadow)
        env.define("_render_target",     get_render_target())
    except Exception as ex:
        import sys as _sys
        print(f"[sdl] renderer not available: {ex}", file=_sys.stderr)
        # Stub everything
        for n in ["GlTexture","decodePNG8","RenderMugenGl","RenderMugenGlFc",
                  "RenderMugenGlFcS","renderMugenZoom","renderMugenShadow"]:
            env.define(n, lambda *a, **kw: None)

# Patch register to also add rendering
_orig_register = register
def register(env, interpreter):
    _orig_register(env, interpreter)
    _register_rendering(env)
    # Wire flip() to also present the renderer frame to window
    rt = env._vars.get("_render_target")
    eng = env._vars.get("_engine")
    if rt and eng and eng.window:
        _orig_flip = eng.flip
        def _flip_with_render():
            if rt.surface and eng.window:
                eng.window.frame = rt.surface.copy()
            _orig_flip()
        eng.flip = _flip_with_render
