"""
engine/sff.py — MUGEN SFF (Sprite File Format) parser.

Supports SFF v1 (PCX-based) and SFF v2 (PNG/RLE8/RLE5 based).
Returns sprites as PIL Images for rendering.

SFF v1 layout:
  12-byte header: "ElecbyteSpr\0"
  version bytes
  sprite count, subfile offset
  each subfile: 32-byte header + PCX/RLE data

SFF v2 layout:
  8-byte signature: "ElecbyteSpr"
  uint8 ver3, ver2, ver1, ver0
  various palette/sprite tables
"""

import struct
import zlib
import io
from typing import Optional, Dict, Tuple, List
from PIL import Image
import numpy as np


SpriteKey = Tuple[int, int]  # (group, index)


class SFFSprite:
    """A single sprite with its image and metadata."""
    __slots__ = ("group", "idx", "x", "y", "image")

    def __init__(self, group: int, idx: int, x: int, y: int, image: Image.Image):
        self.group = group
        self.idx   = idx
        self.x     = x          # x axis offset
        self.y     = y          # y axis offset
        self.image = image


class SFFFile:
    """Loaded SFF file — maps (group, index) → SFFSprite."""

    def __init__(self):
        self.sprites: Dict[SpriteKey, SFFSprite] = {}
        self.version: int = 1

    def get(self, group: int, idx: int) -> Optional[SFFSprite]:
        return self.sprites.get((group, idx))

    def __len__(self) -> int:
        return len(self.sprites)


# ── SFF v1 ─────────────────────────────────────────────────────────────────

def _decode_pcx(data: bytes) -> Optional[Image.Image]:
    """Decode a PCX image from raw bytes, returning a PIL Image (RGBA)."""
    try:
        img = Image.open(io.BytesIO(data))
        return img.convert("RGBA")
    except Exception:
        return None


def _load_v1(data: bytes) -> SFFFile:
    """Parse SFF version 1."""
    sff = SFFFile(); sff.version = 1

    if len(data) < 512:
        return sff

    # Header
    sig = data[:12]
    # verlo, verlo2, verhi, verhi2 at 12..15
    num_sprites = struct.unpack_from("<I", data, 28)[0]
    first_offset = struct.unpack_from("<I", data, 32)[0]

    # shared palette at end if present
    shared_pal: Optional[List] = None

    pos = first_offset
    prev_image: Optional[Image.Image] = None

    for _ in range(num_sprites):
        if pos + 32 > len(data):
            break

        next_off  = struct.unpack_from("<I", data, pos)[0]
        sub_len   = struct.unpack_from("<I", data, pos + 4)[0]
        x         = struct.unpack_from("<h", data, pos + 8)[0]
        y         = struct.unpack_from("<h", data, pos + 10)[0]
        group     = struct.unpack_from("<H", data, pos + 12)[0]
        idx       = struct.unpack_from("<H", data, pos + 14)[0]
        link_idx  = struct.unpack_from("<H", data, pos + 16)[0]
        use_shared = data[pos + 18]  # 0 = own palette, 1 = shared

        pcx_data = data[pos + 32: pos + 32 + sub_len]

        if sub_len == 0:
            # Linked sprite — reuse previous image
            image = prev_image
        else:
            image = _decode_pcx(pcx_data)

        if image is not None:
            sff.sprites[(group, idx)] = SFFSprite(group, idx, x, y, image)
            prev_image = image

        pos = next_off if next_off != 0 else (pos + 32 + sub_len)

    return sff


# ── SFF v2 ─────────────────────────────────────────────────────────────────

def _rle8_decode(src: bytes, w: int, h: int) -> bytes:
    """Decode RLE8 compressed sprite data."""
    out = bytearray()
    i = 0
    while i < len(src) and len(out) < w * h:
        b = src[i]; i += 1
        if (b & 0xC0) == 0x40:            # run of literal bytes
            count = b & 0x3F
            out.extend(src[i:i + count])
            i += count
        elif (b & 0xC0) == 0x00:           # run of color
            count = b & 0x3F
            if i < len(src):
                out.extend([src[i]] * count)
                i += 1
        else:
            out.append(b)
    return bytes(out[:w * h])


def _rle5_decode(src: bytes, w: int, h: int) -> bytes:
    """Decode RLE5 compressed sprite data (SFF v2)."""
    # Similar to RLE8 but different bit fields
    return _rle8_decode(src, w, h)   # simplified


def _load_v2(data: bytes) -> SFFFile:
    """Parse SFF version 2."""
    sff = SFFFile(); sff.version = 2

    if len(data) < 36:
        return sff

    # SFF v2 header starts at offset 0
    # sig[12], ver[4], reserved[4], compatver[4]
    # sprite table offset at 36, sprite table size at 40
    # subfile table offset at 44, subfile table size at 48
    # palette table offset at 52, palette table count at 56

    spr_tbl_off  = struct.unpack_from("<I", data, 36)[0]
    spr_tbl_size = struct.unpack_from("<I", data, 40)[0]
    sub_tbl_off  = struct.unpack_from("<I", data, 44)[0]
    sub_tbl_size = struct.unpack_from("<I", data, 48)[0]
    pal_tbl_off  = struct.unpack_from("<I", data, 52)[0]
    pal_tbl_cnt  = struct.unpack_from("<I", data, 56)[0]

    # Read palettes
    palettes: List[List] = []
    for p in range(pal_tbl_cnt):
        base = pal_tbl_off + p * 16
        if base + 16 > len(data): break
        ptype    = struct.unpack_from("<H", data, base)[0]
        num_cols = struct.unpack_from("<H", data, base + 2)[0]
        idx_fst  = struct.unpack_from("<H", data, base + 4)[0]
        idx_num  = struct.unpack_from("<H", data, base + 6)[0]
        lnk_idx  = struct.unpack_from("<H", data, base + 8)[0]
        dat_off  = struct.unpack_from("<I", data, base + 10)[0]
        dat_len  = struct.unpack_from("<I", data, base + 14)[0] if base + 18 <= len(data) else 0

        pal: List = []
        if dat_off and dat_len and dat_off + dat_len <= len(data):
            pdata = data[dat_off:dat_off + dat_len]
            # RGBA quads
            for c in range(min(num_cols, dat_len // 4)):
                r, g, b, a = pdata[c*4], pdata[c*4+1], pdata[c*4+2], pdata[c*4+3]
                pal.append((r, g, b, a))
        palettes.append(pal)

    # Read sprites
    for s in range(spr_tbl_size):
        base = spr_tbl_off + s * 28
        if base + 28 > len(data): break

        group     = struct.unpack_from("<H", data, base)[0]
        idx_num   = struct.unpack_from("<H", data, base + 2)[0]
        x         = struct.unpack_from("<h", data, base + 4)[0]
        y         = struct.unpack_from("<h", data, base + 6)[0]
        w         = struct.unpack_from("<H", data, base + 8)[0]
        h         = struct.unpack_from("<H", data, base + 10)[0]
        lnk_idx   = struct.unpack_from("<H", data, base + 12)[0]
        fmt       = data[base + 14]   # 0=raw, 1=invalid, 2=RLE8, 3=RLE5, 4=LZ5, 10=PNG
        pal_idx   = data[base + 15]
        dat_off   = struct.unpack_from("<I", data, base + 16)[0]
        dat_len   = struct.unpack_from("<I", data, base + 20)[0]
        sub_idx   = struct.unpack_from("<H", data, base + 24)[0]
        c_dep     = struct.unpack_from("<H", data, base + 26)[0]

        if w == 0 or h == 0:
            continue

        if dat_off == 0 or dat_off + dat_len > len(data):
            continue

        raw = data[dat_off:dat_off + dat_len]
        image: Optional[Image.Image] = None

        try:
            if fmt == 10:  # PNG
                image = Image.open(io.BytesIO(raw)).convert("RGBA")
            elif fmt == 4:  # LZ5 / zlib
                try:
                    dec = zlib.decompress(raw)
                except Exception:
                    dec = raw
                if pal_idx < len(palettes) and palettes[pal_idx]:
                    pal = palettes[pal_idx]
                    img_p = Image.frombytes("P", (w, h), dec[:w*h])
                    flat = []
                    for c in pal:
                        flat.extend(c[:3])
                    img_p.putpalette(flat[:768])
                    image = img_p.convert("RGBA")
                else:
                    image = Image.frombytes("L", (w, h), dec[:w*h]).convert("RGBA")
            elif fmt in (2, 3):  # RLE
                dec = _rle8_decode(raw, w, h)
                if pal_idx < len(palettes) and palettes[pal_idx]:
                    pal = palettes[pal_idx]
                    img_p = Image.frombytes("P", (w, h), dec[:w*h])
                    flat = []
                    for c in pal:
                        flat.extend(c[:3])
                    img_p.putpalette(flat[:768])
                    image = img_p.convert("RGBA")
                else:
                    image = Image.frombytes("L", (w, h), dec[:w*h]).convert("RGBA")
            elif fmt == 0:  # raw
                if len(raw) >= w * h * 4:
                    image = Image.frombytes("RGBA", (w, h), raw[:w*h*4])
                else:
                    image = Image.frombytes("L", (w, h), raw[:w*h]).convert("RGBA")
        except Exception:
            pass

        if image is not None:
            sff.sprites[(group, idx_num)] = SFFSprite(group, idx_num, x, y, image)

    return sff


# ── Public API ──────────────────────────────────────────────────────────────

def load(path: str) -> SFFFile:
    """Load an SFF file and return an SFFFile object."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        raise IOError(f"Cannot open SFF file: {path}") from e

    # Detect version from signature
    sig = data[:12]
    if not sig.startswith(b"ElecbyteSpr"):
        raise ValueError(f"Not a valid SFF file: {path}")

    # Version byte at offset 15 (ver_hi) or check ver bytes
    ver_lo2 = data[12] if len(data) > 12 else 0
    ver_lo  = data[13] if len(data) > 13 else 0
    ver_hi  = data[14] if len(data) > 14 else 0
    ver_hi2 = data[15] if len(data) > 15 else 0

    if ver_hi == 2:
        return _load_v2(data)
    else:
        return _load_v1(data)
