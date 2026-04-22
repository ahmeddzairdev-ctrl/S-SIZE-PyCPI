#!/usr/bin/env python3
"""
ssz.py  –  S-SIZE (SSZ) Language Interpreter  (Python replica)
============================================================
Cross-platform command-line entry point.

Usage:
    python ssz.py [script.ssz]           Run a script (default: main.ssz)
    python ssz.py --tokens script.ssz    Dump token stream and exit
    python ssz.py --ast    script.ssz    Dump AST and exit
    python ssz.py --help                 Show this help

The interpreter searches for .ssz library files in:
  1.  The same directory as the script
  2.  ./lib/  relative to the script
  3.  Built-in Python stubs in ssize/stdlib/

S-SIZE was originally created by supersuehiro as the scripting core of
the I.K.E.M.E.N. fighting-game engine (M.U.G.E.N clone).
This Python replica aims for cross-platform compatibility.
"""

import sys
import os
import argparse
import pprint
from pathlib import Path


def _add_package_to_path() -> None:
    """Make sure the ssize package is importable."""
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))


_add_package_to_path()

from ssize.lexer       import Lexer, LexError
from ssize.parser      import Parser, ParseError
from ssize.interpreter import Interpreter, SSZError


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ssz",
        description="S-SIZE (SSZ) language interpreter – Python cross-platform replica",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("script", nargs="?", default="main.ssz",
                   help="Path to the .ssz script to run (default: main.ssz)")
    p.add_argument("--tokens", action="store_true",
                   help="Dump token stream then exit")
    p.add_argument("--ast", action="store_true",
                   help="Dump AST then exit")
    p.add_argument("--lib", action="append", default=[],
                   metavar="DIR",
                   help="Extra library search directory (can repeat)")
    p.add_argument("--version", action="version", version="SSZ Python Replica 1.0.0")
    return p


def run_script(filepath: str, lib_dirs: list, dump_tokens: bool, dump_ast: bool) -> int:
    path = Path(filepath)
    if not path.exists():
        print(f"ssz: error: file not found: {filepath}", file=sys.stderr)
        return 1

    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"ssz: error reading file: {e}", file=sys.stderr)
        return 1

    # --- Lex ---
    try:
        lexer  = Lexer(source, str(path))
        tokens = lexer.tokenize()
    except LexError as e:
        print(f"ssz: {e}", file=sys.stderr)
        return 1

    if dump_tokens:
        for tok in tokens:
            print(tok)
        return 0

    # --- Parse ---
    try:
        parser  = Parser(tokens)
        program = parser.parse()
    except ParseError as e:
        print(f"ssz: {e}", file=sys.stderr)
        return 1

    if dump_ast:
        _pretty_ast(program)
        return 0

    # --- Interpret ---
    src_dir = str(path.parent.resolve())
    search_dirs = [src_dir] + lib_dirs

    interp = Interpreter(source_dir=src_dir, lib_dirs=search_dirs)
    try:
        interp.run(program)
    except SSZError as e:
        print(f"ssz: runtime error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ssz: unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        return 1

    return 0


def _pretty_ast(node, indent: int = 0) -> None:
    prefix = "  " * indent
    name   = type(node).__name__
    from dataclasses import fields as dc_fields, asdict
    try:
        flds = dc_fields(node)
    except TypeError:
        print(f"{prefix}{node!r}")
        return

    print(f"{prefix}{name}(")
    for f in flds:
        val = getattr(node, f.name)
        if f.name == "line":
            continue
        if isinstance(val, list):
            print(f"{prefix}  {f.name}=[")
            for item in val:
                if hasattr(item, "__dataclass_fields__"):
                    _pretty_ast(item, indent + 2)
                else:
                    print(f"{'  '*(indent+2)}{item!r}")
            print(f"{prefix}  ]")
        elif hasattr(val, "__dataclass_fields__"):
            print(f"{prefix}  {f.name}=")
            _pretty_ast(val, indent + 2)
        else:
            print(f"{prefix}  {f.name}={val!r}")
    print(f"{prefix})")


def main() -> None:
    parser = build_arg_parser()
    args   = parser.parse_args()
    sys.exit(run_script(
        filepath    = args.script,
        lib_dirs    = args.lib,
        dump_tokens = args.tokens,
        dump_ast    = args.ast,
    ))


if __name__ == "__main__":
    main()
