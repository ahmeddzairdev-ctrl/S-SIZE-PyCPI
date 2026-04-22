"""
engine/renderer.py — PIL-based 2D sprite renderer.

Implements the SDL drawing calls used by the IKEMEN engine:
  GlTexture       class  — GPU texture wrapper (holds PIL Image)
  decodePNG8      func   — decode palette-indexed PNG from file handle
  RenderMugenGl   func   — draw indexed-palette sprite with scale/alpha
  RenderMugenGlFc func   — draw full-colour sprite with colour effects
  renderMugenZoom func   — draw sprite with zoom/rotation
  renderMugenShadow func — draw sprite shadow

All functions composite onto a shared render target (PIL Image).
"""
from __future__ import annotations

import math
import io
import struct
from typing import Optional, Tuple, List, Any
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

# ── Shared render target ─────────────────────────────────────────────────────

class RenderTarget:
    """The global compositing surface."""
    def __init__(self):
        self.surface: Optional[Image.Image] = None
        self.width:   int = 960
        self.height:  int = 720

    def init(self, w: int, h: int) -> None:
        self.width  = w
        self.height = h
        self.surface = Image.new("RGBA", (w, h), (0, 0, 0, 255))

    def clear(self, color: Tuple[int,int,int] = (0, 0, 0)) -> None:
        if self.surface:
            self.surface.paste(Image.new("RGBA", (self.width, self.height),
                                         color + (255,)), (0, 0))

    def get_frame(self) -> Optional[Image.Image]:
        return self.surface


_target = RenderTarget()


def get_render_target() -> RenderTarget:
    return _target


# ── GlTexture — texture / pixel-data handle ──────────────────────────────────

class GlTexture:
    """
    Represents an uploaded texture / sprite pixel buffer.
    In the real engine this is an OpenGL texture ID.
    Here it wraps a PIL Image.
    """
    def __init__(self, image: Optional[Image.Image] = None):
        self._image = image

    @property
    def image(self) -> Optional[Image.Image]:
        return self._image

    @image.setter
    def image(self, img: Optional[Image.Image]) -> None:
        self._image = img

    def __len__(self) -> int:
        return 1 if self._image is not None else 0

    def __bool__(self) -> bool:
        return self._image is not None

    def __repr__(self) -> str:
        if self._image:
            return f"<GlTexture {self._image.width}×{self._image.height}>"
        return "<GlTexture empty>"


def _make_texture(*args) -> GlTexture:
    return GlTexture()


# ── Palette application ───────────────────────────────────────────────────────

def _apply_palette(img_p: Image.Image, pal_data) -> Image.Image:
    """
    Apply a palette to a palette-mode image.
    pal_data may be a list of uint32 ARGB values or a bytes object.
    """
    if isinstance(pal_data, (list, tuple)):
        # List of uint32 ABGR/ARGB values
        flat = []
        for entry in pal_data[:256]:
            if isinstance(entry, int):
                a = (entry >> 24) & 0xFF
                r = (entry >> 16) & 0xFF
                g = (entry >> 8)  & 0xFF
                b =  entry        & 0xFF
                flat.extend([r, g, b])
            else:
                flat.extend([0, 0, 0])
        while len(flat) < 768:
            flat.extend([0, 0, 0])
        img_p.putpalette(flat[:768])
    elif isinstance(pal_data, (bytes, bytearray)):
        img_p.putpalette(pal_data[:768])
    return img_p.convert("RGBA")


# ── Colour/palette effect processing ─────────────────────────────────────────

class PalFX:
    """Palette effect (MUGEN PalFX controller output)."""
    def __init__(self):
        self.enable  = False
        self.add_r   = 0; self.add_g   = 0; self.add_b   = 0
        self.mul_r   = 256; self.mul_g = 256; self.mul_b = 256
        self.invert  = False
        self.color   = 1.0
        self.sintime = 0
        self.cosal   = False

    def apply(self, img: Image.Image) -> Image.Image:
        if not self.enable:
            return img
        arr = np.array(img, dtype=np.int32)
        r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
        r = np.clip(r * self.mul_r // 256 + self.add_r, 0, 255)
        g = np.clip(g * self.mul_g // 256 + self.add_g, 0, 255)
        b = np.clip(b * self.mul_b // 256 + self.add_b, 0, 255)
        if self.invert:
            r, g, b = 255 - r, 255 - g, 255 - b
        result = np.stack([r, g, b, a], axis=-1).astype(np.uint8)
        return Image.fromarray(result, "RGBA")


# ── decodePNG8 ───────────────────────────────────────────────────────────────

def decode_png8(w_ref, h_ref, file_ref) -> GlTexture:
    """
    sdl.decodePNG8(rct.w=, rct.h=, f=)
    Decode a palette-indexed PNG from an open file handle.
    Stores decoded image in a GlTexture; sets w/h as out-params.
    """
    tex = GlTexture()
    try:
        if hasattr(file_ref, "read"):
            data = file_ref.read()
        elif isinstance(file_ref, (bytes, bytearray)):
            data = bytes(file_ref)
        else:
            return tex
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        # w_ref and h_ref are out-param references — just store the image
        tex.image = img
    except Exception:
        pass
    return tex


# ── Alpha mode decoding ───────────────────────────────────────────────────────

def _decode_trans(trans: int) -> Tuple[int, int]:
    """
    Decode MUGEN trans int → (src_alpha, dst_alpha) for blending.
    0    = normal (alpha 255)
    1    = ADD (S1)
    -1   = NONE (fully opaque)
    -2   = sub
    high bits encode alpha pairs
    """
    if trans == 0:
        return (255, 0)       # normal
    if trans == 1:
        return (255, 255)     # additive
    if trans == -2:
        return (128, 0)       # subtractive
    if trans < 0:
        return (255, 0)
    # Packed: (src_alpha << 10) | (dst_alpha << 9) | flags
    src = (trans >> 10) & 0xFF
    dst = (trans >>  9) & 0x01
    if src == 0: src = 255
    return (src, 0)


# ── Core blit to render target ────────────────────────────────────────────────

def _blit_to_target(
        img: Image.Image,
        x: float, y: float,
        xscale: float = 1.0, yscale: float = 1.0,
        angle: float = 0.0,
        alpha: int = 255,
        window: Optional[Any] = None,
        flip_h: bool = False, flip_v: bool = False,
        shadow_color: Optional[Tuple[int,int,int]] = None,
        shadow_alpha: int = 0) -> None:
    """Composite an image onto the global render target."""
    if _target.surface is None:
        return
    if img is None:
        return

    # Flip
    if flip_h: img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_v: img = img.transpose(Image.FLIP_TOP_BOTTOM)

    # Scale
    nw = max(1, abs(int(img.width  * xscale)))
    nh = max(1, abs(int(img.height * yscale)))
    if nw != img.width or nh != img.height:
        img = img.resize((nw, nh), Image.NEAREST)

    # Rotate
    if angle != 0.0:
        degrees = -math.degrees(angle)
        img = img.rotate(degrees, expand=True, resample=Image.BILINEAR)

    # Alpha
    if alpha < 255 and img.mode == "RGBA":
        r, g, b, a = img.split()
        a = a.point(lambda p: int(p * alpha / 255))
        img = Image.merge("RGBA", (r, g, b, a))

    # Clip to window
    if window is not None:
        try:
            wx, wy, ww, wh = int(window.x), int(window.y), int(window.w), int(window.h)
        except Exception:
            wx, wy = 0, 0
            ww, wh = _target.width, _target.height
    else:
        wx, wy = 0, 0
        ww, wh = _target.width, _target.height

    # Destination position
    ix = int(x)
    iy = int(y)

    # Paste with mask
    if img.mode == "RGBA":
        _target.surface.paste(img, (ix, iy), img)
    else:
        _target.surface.paste(img, (ix, iy))


# ── RenderMugenGl ─────────────────────────────────────────────────────────────

def render_mugen_gl(
        pxl, pal, mask,
        rct, x, y, tile, xts, xbs, ys,
        vscale=1.0, rxadd=0.0, agl=0.0, trans=0,
        window=None, rcx=0.0, rcy=0.0,
        *args) -> None:
    """
    sdl.RenderMugenGl(:pxl<>, pal<>=, mask, rct=, x, y, tile=, xts, xbs,
                       ys, 1.0, rxadd, agl, trans, window=, rcx, rcy:)
    Draw an indexed-palette sprite.
    """
    tex = pxl if isinstance(pxl, GlTexture) else GlTexture()
    if not tex:
        return
    img = tex.image
    if img is None:
        return

    # Apply palette if provided
    if img.mode == "P" and pal is not None:
        img = _apply_palette(img, pal)
    elif img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha, _ = _decode_trans(int(trans) if trans else 0)
    xscale = float(xts) if xts else 1.0
    yscale = float(ys)  if ys  else 1.0

    _blit_to_target(img, float(x), float(y),
                    xscale, yscale, float(agl) if agl else 0.0,
                    alpha, window)


# ── RenderMugenGlFc ──────────────────────────────────────────────────────────

def render_mugen_gl_fc(
        pxl, rct, x, y, tile, xts, xbs, ys,
        vscale=1.0, rxadd=0.0, agl=0.0, trans=0,
        window=None, rcx=0.0, rcy=0.0,
        neg=False, color=0.0,
        ar=1.0, ag=1.0, ab=1.0,
        mr=1.0, mg=1.0, mb=1.0,
        *args) -> None:
    """
    sdl.RenderMugenGlFc(: pxl<>, rct=, x, y, tile=, xts, xbs, ys,
                          1.0, rxadd, agl, trans, window=, rcx, rcy,
                          neg, color, ar, ag, ab, mr, mg, mb :)
    Draw a full-colour sprite with colour effects.
    """
    tex = pxl if isinstance(pxl, GlTexture) else GlTexture()
    if not tex:
        return
    img = tex.image
    if img is None:
        return
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Apply colour modulation
    if mr != 1.0 or mg != 1.0 or mb != 1.0:
        arr = np.array(img, dtype=np.float32)
        arr[:,:,0] = np.clip(arr[:,:,0] * float(mr), 0, 255)
        arr[:,:,1] = np.clip(arr[:,:,1] * float(mg), 0, 255)
        arr[:,:,2] = np.clip(arr[:,:,2] * float(mb), 0, 255)
        img = Image.fromarray(arr.astype(np.uint8), "RGBA")

    if neg:
        r, g, b, a = img.split()
        r = r.point(lambda p: 255 - p)
        g = g.point(lambda p: 255 - p)
        b = b.point(lambda p: 255 - p)
        img = Image.merge("RGBA", (r, g, b, a))

    alpha, _ = _decode_trans(int(trans) if trans else 0)
    xscale = float(xts) if xts else 1.0
    yscale = float(ys)  if ys  else 1.0

    _blit_to_target(img, float(x), float(y),
                    xscale, yscale, float(agl) if agl else 0.0,
                    alpha, window)


render_mugen_gl_fc_s = render_mugen_gl_fc  # same call signature


# ── renderMugenZoom ───────────────────────────────────────────────────────────

def render_mugen_zoom(
        window, rcx, rcy,
        pxl, pal, mask,
        rct, x, y, tile,
        xts, xbs, ys,
        rxadd=0.0, agl=0, trans=0,
        rle=0, pluginbuf=None,
        *args) -> None:
    """
    sdl.renderMugenZoom(window=, rcx, rcy, pxl, pal, mask, rct=,
                        x, y, tile=, xts, xbs, ys, rxadd, agl, trans,
                        rle, pluginbuf=)
    Like RenderMugenGl but used for non-OpenGL path with zoom.
    """
    tex = pxl if isinstance(pxl, GlTexture) else GlTexture()
    if not tex:
        return
    img = tex.image
    if img is None:
        return

    if img.mode == "P" and pal is not None:
        img = _apply_palette(img, pal)
    elif img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha, _ = _decode_trans(int(trans) if trans else 0)
    xscale = float(xts) if xts else 1.0
    yscale = float(ys)  if ys  else 1.0

    # Decode angle — MUGEN uses 10-bit unit circle (0x200 = 180°)
    angle = 0.0
    if agl:
        agl_int = int(agl) & 0x3FF
        angle = agl_int * (2 * math.pi / 1024)

    _blit_to_target(img, float(x), float(y),
                    xscale, yscale, angle,
                    alpha, window)


# ── renderMugenShadow ─────────────────────────────────────────────────────────

def render_mugen_shadow(
        window, x, y, pxl, color,
        rct, ox, oy, xscale, yscale, vscale,
        agl=0, alpha=0, rle=0, pluginbuf=None,
        *args) -> None:
    """
    sdl.renderMugenShadow(window=, x, y, pxl, color, rct=, ox, oy,
                          xscale, yscale, vscale, agl, alpha, rle, pluginbuf=)
    Draw a shadow underneath a sprite.
    """
    tex = pxl if isinstance(pxl, GlTexture) else GlTexture()
    if not tex:
        return
    img = tex.image
    if img is None:
        return

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Extract shadow colour
    r = (int(color) >> 16) & 0xFF if color else 0
    g = (int(color) >>  8) & 0xFF if color else 0
    b =  int(color)        & 0xFF if color else 0

    # Tint entire sprite with shadow colour
    arr = np.array(img, dtype=np.uint8)
    arr[:,:,0] = r
    arr[:,:,1] = g
    arr[:,:,2] = b
    shadow = Image.fromarray(arr, "RGBA")

    xscale_f = float(xscale) if xscale else 1.0
    yscale_f = float(yscale) if yscale else 1.0

    _blit_to_target(shadow, float(x), float(y),
                    xscale_f, yscale_f * float(vscale or 1.0),
                    0.0, int(alpha) if alpha else 128, window)
