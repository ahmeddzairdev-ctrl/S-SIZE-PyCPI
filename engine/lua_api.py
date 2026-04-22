"""
engine/lua_api.py — IKEMEN Lua C-function registry.

Registers all the C-side functions that the real IKEMEN engine exposes
to Lua. In the original engine these are registered in Go/C++ code;
here we provide Python implementations that either do real work or
return sensible defaults so the Lua scripts can run.

Usage:
    from engine.lua_api import register_all
    register_all(lua_state, interpreter, ikemen_root)
"""
from __future__ import annotations
import os
import sys
import time
import math
from pathlib import Path
from typing import Any, Optional


def register_all(L, interpreter, ikemen_root: str) -> None:
    """
    Register all IKEMEN C-functions into a LuaState object.
    L is our LuaState (ssize/stdlib/alpha/lua.py).
    """
    root = Path(ikemen_root)
    _reg_count = [0]  # mutable counter so inner helpers can increment it

    def _reg(name, fn):
        L.register(name, fn)
        _reg_count[0] += 1

    # ── Core game loop ──────────────────────────────────────────────────────
    def refresh():
        """Swap frame buffers — main render call."""
        try:
            from ssize.stdlib.alpha.sdlplugin import _e
            _e.flip()
        except Exception:
            time.sleep(1.0 / 60)
    _reg("refresh", lambda ls, r: (refresh(), r.__setitem__(0, 0))[1])

    def esc():
        """Check if ESC was pressed."""
        try:
            from ssize.stdlib.alpha.sdlplugin import _e
            return 1 if _e._key_state.get("ESCAPE", False) else 0
        except Exception:
            return 0
    _reg("esc", lambda ls, r: (ls.pushBoolean(bool(esc())), r.__setitem__(0, 1))[1])

    # ── Input ────────────────────────────────────────────────────────────────
    def cmd_input():
        """Process controller/keyboard input for the current frame."""
        try:
            from ssize.stdlib.alpha.sdlplugin import _e
            _e._pump()
        except Exception:
            pass
    _reg("cmdInput", lambda ls, r: (cmd_input(), r.__setitem__(0, 0))[1])

    # ── Animation system stubs ───────────────────────────────────────────────
    _anims = {}
    _anim_counter = [0]

    def anim_new(group, idx, *args):
        _anim_counter[0] += 1
        _anims[_anim_counter[0]] = {"group": group, "idx": idx, "x": 0, "y": 0,
                                     "scaleX": 1.0, "scaleY": 1.0, "alpha": 255}
        return _anim_counter[0]

    def anim_set_pos(handle, x, y):
        if handle in _anims:
            _anims[handle]["x"] = x; _anims[handle]["y"] = y

    def anim_draw(handle):
        pass  # TODO: actual rendering

    def anim_update(handle):
        pass

    def anim_add_pos(handle, dx, dy):
        if handle in _anims:
            _anims[handle]["x"] += dx; _anims[handle]["y"] += dy

    def anim_set_scale(handle, sx, sy=None):
        if handle in _anims:
            _anims[handle]["scaleX"] = sx
            _anims[handle]["scaleY"] = sy if sy is not None else sx

    def anim_set_alpha(handle, alpha):
        if handle in _anims:
            _anims[handle]["alpha"] = alpha

    def anim_set_tile(handle, tx, ty=None):
        pass

    def anim_set_window(handle, x, y, w, h):
        pass

    def anim_scale_draw(handle):
        pass

    def anim_pos_draw(handle):
        pass

    def anim_reset(handle):
        pass

    for fname, fn in [
        ("animNew", anim_new), ("animSetPos", anim_set_pos),
        ("animDraw", anim_draw), ("animUpdate", anim_update),
        ("animAddPos", anim_add_pos), ("animSetScale", anim_set_scale),
        ("animSetAlpha", anim_set_alpha), ("animSetTile", anim_set_tile),
        ("animSetWindow", anim_set_window), ("animScaleDraw", anim_scale_draw),
        ("animPosDraw", anim_pos_draw), ("animReset", anim_reset),
        ("animSetColorKey", lambda *a: None),
    ]:
        _fn = fn  # capture
        _reg(fname, lambda ls, r, f=_fn: (
            ls.pushNumber(f(*[ls.toNumber(i+1) for i in range(ls.getTop())]) or 0),
            r.__setitem__(0, 1)
        )[1])

    # ── Text / font ──────────────────────────────────────────────────────────
    def create_text_img(font_path, text, r, g, b, *args):
        return 0  # stub handle

    def create_text_img_lite(*args):
        return 0

    _reg("createTextImg",     lambda ls, r: (ls.pushNumber(0), r.__setitem__(0,1))[1])
    _reg("createTextImgLite", lambda ls, r: (ls.pushNumber(0), r.__setitem__(0,1))[1])

    # ── Character / stage data ───────────────────────────────────────────────
    def get_char_name(cel):
        """Return display name for character slot cel."""
        try:
            from engine.defparser import parse_file, get
            # cel is 1-based index; try to read from select.def
            select = root / "data" / "select.def"
            if select.exists():
                sections = parse_file(str(select))
                chars = sections.get("characters", [{}])
                idx = int(cel) - 1
                if idx < len(chars):
                    return str(chars[idx].get("name", ""))
        except Exception:
            pass
        return ""

    def get_char_file_name(cel):
        try:
            from engine.defparser import parse_file, get
            select = root / "data" / "select.def"
            if select.exists():
                sections = parse_file(str(select))
                chars = sections.get("characters", [{}])
                idx = int(cel) - 1
                if idx < len(chars):
                    return str(chars[idx].get("def", ""))
        except Exception:
            pass
        return ""

    def get_char_num():
        """Return total number of selectable characters."""
        try:
            from engine.defparser import parse_file
            select = root / "data" / "select.def"
            if select.exists():
                sections = parse_file(str(select))
                return len(sections.get("characters", []))
        except Exception:
            pass
        return 0

    def get_stage_num():
        try:
            from engine.defparser import parse_file
            select = root / "data" / "select.def"
            if select.exists():
                sections = parse_file(str(select))
                return len(sections.get("extrastages", []))
        except Exception:
            pass
        return 0

    _reg("getCharName",     lambda ls, r: (ls.pushString(get_char_name(ls.toNumber(1))), r.__setitem__(0,1))[1])
    _reg("getCharFileName", lambda ls, r: (ls.pushString(get_char_file_name(ls.toNumber(1))), r.__setitem__(0,1))[1])
    _reg("getCharNum",      lambda ls, r: (ls.pushNumber(get_char_num()), r.__setitem__(0,1))[1])
    _reg("getStageNum",     lambda ls, r: (ls.pushNumber(get_stage_num()), r.__setitem__(0,1))[1])
    _reg("character",       lambda ls, r: (ls.pushNumber(0), r.__setitem__(0,1))[1])
    _reg("addChar",         lambda ls, r: r.__setitem__(0,0))
    _reg("addStage",        lambda ls, r: r.__setitem__(0,0))

    # ── Screen / render dims ─────────────────────────────────────────────────
    def game_width():
        try:
            from ssize.stdlib.alpha.sdlplugin import _e
            return _e.width
        except Exception:
            return 960

    def game_height():
        try:
            from ssize.stdlib.alpha.sdlplugin import _e
            return _e.height
        except Exception:
            return 720

    _reg("gameWidth",  lambda ls, r: (ls.pushNumber(game_width()), r.__setitem__(0,1))[1])
    _reg("gameHeight", lambda ls, r: (ls.pushNumber(game_height()), r.__setitem__(0,1))[1])

    # ── Command / input system ───────────────────────────────────────────────
    _reg("commandNew",      lambda ls, r: (ls.pushNumber(0), r.__setitem__(0,1))[1])
    _reg("commandAdd",      lambda ls, r: r.__setitem__(0,0))
    _reg("commandInput",    lambda ls, r: r.__setitem__(0,0))
    _reg("commandGetState", lambda ls, r: (ls.pushNumber(0), r.__setitem__(0,1))[1])

    # ── Audio ────────────────────────────────────────────────────────────────
    def play_bgm(path, loop=True):
        try:
            p = str(path)
            if not os.path.isabs(p):
                p = str(root / p)
            if os.path.isfile(p):
                print(f"[bgm] Playing: {p}", file=sys.stderr)
        except Exception:
            pass

    _reg("playBGM",    lambda ls, r: (play_bgm(ls.toString(1)), r.__setitem__(0,0))[1])
    _reg("stopBGM",    lambda ls, r: r.__setitem__(0,0))
    _reg("fadeInBGM",  lambda ls, r: r.__setitem__(0,0))
    _reg("fadeOutBGM", lambda ls, r: r.__setitem__(0,0))
    _reg("setVolume",  lambda ls, r: r.__setitem__(0,0))

    # ── File I/O (used by save/load) ─────────────────────────────────────────
    def bat_open(path):
        p = str(path)
        if not os.path.isabs(p):
            p = str(root / p)
        try:
            return open(p, "r", encoding="utf-8", errors="replace")
        except OSError:
            return None

    _reg("batOpen", lambda ls, r: (ls.pushRef(bat_open(ls.toString(1))), r.__setitem__(0,1))[1])

    # ── UI draw stubs (screenpack) ───────────────────────────────────────────
    # These are drawn by screenpack.lua using the anim system — stubs are fine
    for fn_name in [
        "drawBottomMenuSP", "drawMiddleMenuSP", "drawTopMenuSP",
        "drawInputHintsP1", "drawInputHintsP2",
        "drawMenuInputHints", "drawListInputHints", "drawConfirmInputHints",
        "drawPauseInputHints", "drawPauseInputHints2", "drawOrderInputHints",
        "drawSelectInputHints", "drawContinueInputHints", "drawEventInputHints",
        "drawArtInputHints", "drawAttractInputHints", "drawGalleryInputHints",
        "drawInfoInputHints", "drawInfoEventInputHints", "drawLicenseInputHints",
        "drawMissionInputHints", "drawCrudHostInputHints",
        "drawVNInputHints", "drawVNInputHints2", "drawVNInputHints3",
        "drawQuickSpr", "drawQuickText",
    ]:
        _reg(fn_name, lambda ls, r: r.__setitem__(0,0))

    # ── Palette / button ─────────────────────────────────────────────────────
    _reg("btnPalNo",   lambda ls, r: (ls.pushNumber(1), r.__setitem__(0,1))[1])
    _reg("attributes", lambda ls, r: (ls.pushString(""), r.__setitem__(0,1))[1])

    # ── Misc engine functions ─────────────────────────────────────────────────
    _reg("puts",      lambda ls, r: (print(ls.toString(1)), r.__setitem__(0,0))[1])
    _reg("CANCEL",    lambda ls, r: r.__setitem__(0,0))
    _reg("Refresh",   lambda ls, r: (refresh(), r.__setitem__(0,0))[1])

    # ── Discord (no-op stubs) ────────────────────────────────────────────────
    for fn_name in ["discordInit", "discordEnd", "discordUpdate",
                    "setDiscordDetails", "setDiscordState",
                    "setDiscordBigImg", "setDiscordBigTxt",
                    "setDiscordMiniImg", "setDiscordMiniTxt"]:
        _reg(fn_name, lambda ls, r: r.__setitem__(0,0))

    print(f"[lua_api] Registered {_reg_count[0]} C-functions into Lua state",
          file=sys.stderr)
