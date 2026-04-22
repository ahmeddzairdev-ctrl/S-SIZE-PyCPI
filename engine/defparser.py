"""
engine/defparser.py — Parser for MUGEN INI-style definition files.

Handles .def, .cns, .air, .cmd, .st files.

Format:
  ; comment
  [SectionName]
  key = value
  key = value1, value2, ...
"""

import re
import os
from typing import Dict, List, Optional, Any


Section = Dict[str, Any]
FileSections = Dict[str, List[Section]]   # name → list of section dicts


def parse_file(path: str) -> FileSections:
    """Parse a MUGEN def/cns/air/cmd file and return sections."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return parse_text(fh.read())
    except OSError:
        return {}


def parse_text(text: str) -> FileSections:
    """Parse the text of a MUGEN def/cns file."""
    result: FileSections = {}
    current_name: str = ""
    current_section: Section = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Strip comments
        if ";" in line:
            line = line[:line.index(";")].strip()
        if not line:
            continue

        # Section header
        m = re.match(r"^\[(.+?)\]$", line)
        if m:
            # Save old section
            if current_name or current_section:
                result.setdefault(current_name.lower(), []).append(current_section)
            current_name = m.group(1).strip()
            current_section = {"_name": current_name}
            continue

        # Key = value
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()

            # Try to parse as number(s)
            parsed = _parse_value(val)
            current_section[key] = parsed

    # Save last section
    if current_name or current_section:
        result.setdefault(current_name.lower(), []).append(current_section)

    return result


def get(sections: FileSections, section: str, key: str,
        default: Any = None) -> Any:
    """Get a value from a specific section."""
    sec_list = sections.get(section.lower(), [])
    if not sec_list:
        return default
    return sec_list[0].get(key.lower(), default)


def get_all(sections: FileSections, section: str) -> List[Section]:
    """Get all instances of a section (e.g. multiple [State X] blocks)."""
    return sections.get(section.lower(), [])


def _parse_value(val: str) -> Any:
    """Parse a value string into Python types."""
    val = val.strip()

    # Boolean
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False

    # Comma-separated list
    if "," in val:
        parts = [_parse_single(p.strip()) for p in val.split(",")]
        return parts

    return _parse_single(val)


def _parse_single(val: str) -> Any:
    """Try to parse a single value."""
    val = val.strip().strip('"').strip("'")
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ── Convenience: load a character's files from its .def ────────────────────

class CharDef:
    """Parsed character definition."""

    def __init__(self, def_path: str):
        self.def_path = def_path
        self.dir      = os.path.dirname(def_path)
        self._data    = parse_file(def_path)

        info   = get(self._data, "info", "name",    "Unknown")
        self.name        = str(info)
        self.displayname = str(get(self._data, "info",  "displayname", self.name))
        self.author      = str(get(self._data, "info",  "author",      "Unknown"))
        self.sff_file    = self._resolve("files", "sprite",  ".sff")
        self.snd_file    = self._resolve("files", "sound",   ".snd")
        self.cns_file    = self._resolve("files", "cns",     ".cns")
        self.air_file    = self._resolve("files", "anim",    ".air")
        self.cmd_file    = self._resolve("files", "cmd",     ".cmd")
        self.stcommon    = self._resolve("files", "stcommon","")

    def _resolve(self, section: str, key: str, fallback: str) -> str:
        raw = get(self._data, section, key, "")
        if not raw:
            return ""
        p = os.path.join(self.dir, str(raw))
        return p if os.path.exists(p) else ""


class StageDef:
    """Parsed stage definition."""

    def __init__(self, def_path: str):
        self.def_path = def_path
        self.dir      = os.path.dirname(def_path)
        self._data    = parse_file(def_path)

        self.name     = str(get(self._data, "info", "name",   "Unknown Stage"))
        self.sff_file = self._resolve("bgdef", "spr", ".sff")
        self.snd_file = self._resolve("music", "bgmusic", "")
        # Background elements
        self.bgs: List[Section] = []
        for key in self._data:
            if key.startswith("bg ") or key == "bg":
                self.bgs.extend(self._data[key])

    def _resolve(self, section: str, key: str, fallback: str) -> str:
        raw = get(self._data, section, key, "")
        if not raw:
            return ""
        p = os.path.join(self.dir, str(raw))
        return p if os.path.exists(p) else ""
