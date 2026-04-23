#!/usr/bin/env python3
"""
ikemen.py — I.K.E.M.E.N Plus Ultra  Python replica launcher
============================================================

Mirrors the real IKEMEN Plus Ultra launch sequence:

  REAL ENGINE:
    main.ssz (root)
      └─ sh.open("Ikemen Plus Ultra.exe", ...)   ← launches compiled binary
           └─ ssz/ikemen.ssz → main()
                └─ sdl.init(...)
                └─ lua.State L
                └─ L.runFile(cfg.system)          ← "script/main.lua"

  THIS REPLICA (Python):
    ikemen.py (this file)
      └─ runs  ssz/ikemen.ssz  directly           ← skip the sh.open step
           └─ sdl.init(...)                       ← engine/window.py
           └─ lua.State L                         ← lupa or Python shim
           └─ L.runFile("script/main.lua")        ← Lua game logic

Directory layout expected:
  <IKEMEN_ROOT>/
    ssz/            ← SSZ engine scripts (ikemen.ssz, common.ssz, ...)
    save/           ← config.ssz, player data
    script/         ← Lua scripts (main.lua, common.lua, ...)
    chars/          ← Character data
    stages/         ← Stage data
    font/           ← Font files
    sound/          ← BGM / SFX
    data/           ← Screenpacks / system.def
    external/       ← Shaders / plugins

Usage:
    python ikemen.py /path/to/Ikemen-Plus-Ultra
    python ikemen.py .                           (if already in IKEMEN folder)

Optional dependencies (highly recommended):
    pip install lupa      ← Full Lua support  (menus, char-select, fight)
    pip install pygame    ← Real window + keyboard/joystick input
    pip install Pillow    ← Required for rendering (usually already installed)
"""

from __future__ import annotations
import sys
import os
import argparse
from pathlib import Path


# ── Locate the entry-point SSZ script ───────────────────────────────────────

def find_entry_script(root: Path) -> Path:
    """
    Find ssz/ikemen.ssz relative to the IKEMEN root directory.
    Falls back to other known locations.
    """
    candidates = [
        root / "ssz"  / "ikemen.ssz",   # standard location
        root / "data" / "ikemen.ssz",    # some builds put it here
        root / "ikemen.ssz",             # flat layout
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]   # return preferred even if missing (for error message)


def find_ikemen_root(hint: str) -> Path:
    """
    Locate the IKEMEN Plus Ultra root.

    Resolution order:
    1. The hint itself (if it looks like the root)
    2. The directory containing ikemen.py (most common: user puts
       our files directly inside the IKEMEN folder)
    3. Walk up from hint looking for the ssz/ + save/ pattern
    4. Fall back to the hint as-is
    """
    # Case 1 & 3: check the hint path and parents
    p = Path(hint).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "ssz" / "ikemen.ssz").exists():
            return candidate
        if (candidate / "ssz").is_dir() and (candidate / "save").is_dir():
            return candidate

    # Case 2: check the directory that contains this script
    #         (user placed ikemen.py inside the IKEMEN folder)
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "ssz" / "ikemen.ssz").exists():
        return script_dir
    if (script_dir / "ssz").is_dir() and (script_dir / "save").is_dir():
        return script_dir

    # Fall back
    return p


# ── Library search paths ─────────────────────────────────────────────────────

def build_lib_dirs(root: Path, ssz_dir: Path) -> list[str]:
    """
    Build the ordered list of directories the SSZ interpreter will
    search when resolving  lib x = "something.ssz"  imports.

    The real engine resolves:
      "common.ssz"         → ssz/common.ssz          (same dir as current script)
      "../save/config.ssz" → save/config.ssz          (relative to ssz/)
      <alpha/sdlplugin.ssz>→ built-in stub            (Python stdlib)
    """
    return [
        str(ssz_dir),                       # ssz/   ← all engine scripts live here
        str(root / "save"),                 # save/  ← config.ssz, player data
        str(root / "script"),               # script/← Lua files  (for loader.ssz refs)
        str(root),                          # root   ← fallback
        str(root / "data"),                 # data/  ← screenpacks
    ]


# ── Run ──────────────────────────────────────────────────────────────────────

def run(root_hint: str = ".", headless: bool = False) -> int:
    # Add this package to sys.path
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    from ssize.lexer       import Lexer, LexError
    from ssize.parser      import Parser, ParseError
    from ssize.interpreter import Interpreter, SSZError

    root    = find_ikemen_root(root_hint)
    ssz_dir = root / "ssz"
    entry   = find_entry_script(root)

    # ── Validate ─────────────────────────────────────────────────────────────
    if not entry.exists():
        print(f"""
[ikemen] ERROR: Cannot find ssz/ikemen.ssz

  Looked for: {entry}
  From root:  {root}

  Make sure you point to the Ikemen-Plus-Ultra root folder.
  Example:
    python ikemen.py ~/Downloads/Ikemen-Plus-Ultra

  The folder should contain:
    ssz/ikemen.ssz
    save/config.ssz
    script/main.lua
""", file=sys.stderr)
        return 1

    print(f"[ikemen] Root:   {root}",  file=sys.stderr)
    print(f"[ikemen] Entry:  {entry}", file=sys.stderr)

    if headless:
        os.environ["SSZ_HEADLESS"] = "1"

    # ── Parse ikemen.ssz ────────────────────────────────────────────────────
    try:
        source  = entry.read_text(encoding="utf-8-sig")
        tokens  = Lexer(source, str(entry)).tokenize()
        program = Parser(tokens).parse()
    except LexError as e:
        print(f"[ikemen] Lex error: {e}", file=sys.stderr)
        return 1
    except ParseError as e:
        print(f"[ikemen] Parse error: {e}", file=sys.stderr)
        return 1

    # ── Set up interpreter ──────────────────────────────────────────────────
    lib_dirs = build_lib_dirs(root, ssz_dir)

    interp = Interpreter(
        source_dir = str(ssz_dir),
        lib_dirs   = lib_dirs,
    )

    # Expose the IKEMEN root path to scripts that need it
    interp.global_env.define("_IKEMEN_ROOT", str(root))

    # ── Pre-init SDL window ──────────────────────────────────────────────────
    # In the real IKEMEN binary, SDL is initialised by the C++ engine BEFORE
    # any SSZ scripts run. The SSZ scripts therefore never call sdl.init().
    # We must open the window here so that sdl.flip() / sdl.event() work when
    # the game loop starts inside ikemen.ssz.
    if not headless:
        try:
            here = Path(__file__).resolve().parent
            if str(here) not in sys.path:
                sys.path.insert(0, str(here))
            from ssize.stdlib.alpha.sdlplugin import _e as _sdl_engine
            # Try to read dimensions from save/config.ssz — fall back to 960×720
            _w, _h = 960, 720
            _title = "I.K.E.M.E.N Plus Ultra"
            try:
                import re as _re
                cfg_path = root / "save" / "config.ssz"
                if cfg_path.exists():
                    cfg_src = cfg_path.read_text(encoding="utf-8-sig", errors="replace")
                    for _line in cfg_src.splitlines():
                        _m = _re.search(r'GameWidth\s*=\s*(\d+)', _line)
                        if _m: _w = int(_m.group(1))
                        _m = _re.search(r'GameHeight\s*=\s*(\d+)', _line)
                        if _m: _h = int(_m.group(1))
            except Exception:
                pass
            _sdl_engine.init(_title, _w, _h)
            print(f"[ikemen] Pre-init SDL: {_w}x{_h}", file=sys.stderr, flush=True)
        except Exception as _e:
            print(f"[ikemen] SDL pre-init failed: {_e}", file=sys.stderr, flush=True)

    # ── Execute ─────────────────────────────────────────────────────────────
    try:
        print("[ikemen] Starting engine...", file=sys.stderr)
        interp.run(program)
        print("[ikemen] Engine exited cleanly.", file=sys.stderr)
    except KeyboardInterrupt:
        print("\n[ikemen] Interrupted by user.", file=sys.stderr)
    except SSZError as e:
        import traceback
        print(f"[ikemen] SSZ runtime error: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        import traceback
        print(f"[ikemen] Fatal error: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()   # always show full traceback
        return 1

    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        prog="ikemen",
        description="I.K.E.M.E.N Plus Ultra — Python cross-platform replica",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python ikemen.py ~/Downloads/Ikemen-Plus-Ultra
  python ikemen.py .               (if already in the IKEMEN folder)
  python ikemen.py . --headless    (no window — server / CI mode)
  SSZ_DEBUG=1 python ikemen.py .   (show full Python tracebacks)

dependencies (install for best experience):
  pip install lupa      ← Full Lua support  (required for menus + fight)
  pip install pygame    ← Real window + keyboard/joystick input
  pip install Pillow    ← 2D rendering  (usually pre-installed)
""",
    )
    p.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Path to the Ikemen-Plus-Ultra root folder (default: current dir)",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode — no window, useful for servers and testing",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Print full Python tracebacks on errors",
    )
    args = p.parse_args()

    if args.debug:
        os.environ["SSZ_DEBUG"] = "1"

    sys.exit(run(args.dir, headless=args.headless))


if __name__ == "__main__":
    main()
