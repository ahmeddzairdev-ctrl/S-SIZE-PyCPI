"""
engine/window.py — Cross-platform window and 2D renderer.

Uses PIL to compose frames, then displays them using the best
available backend:
  1. pygame  (if installed)
  2. tkinter (if available)
  3. Headless / file-dump mode (always works)

The rest of the engine only calls the public API:
  Window.create(w, h, title)
  Window.blit(image, x, y, alpha)
  Window.clear(color)
  Window.flip()          ← swap buffers / present frame
  Window.poll_events()   ← returns list of (type, data) events
  Window.destroy()
"""
from __future__ import annotations
import sys
import threading
import queue
import time
from typing import List, Tuple, Optional, Any
from PIL import Image, ImageDraw


Event = Tuple[str, Any]   # ("key_down", key_name), ("quit", None), etc.


class Window:
    """Abstract window — subclassed by backend implementations."""

    def __init__(self, width: int, height: int, title: str):
        self.width  = width
        self.height = height
        self.title  = title
        self.frame  = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        self._events: List[Event] = []
        self._running = True
        self._fps_target = 60
        self._last_flip  = time.time()

    # ── Drawing API ─────────────────────────────────────────────────────────

    def clear(self, color: Tuple[int,int,int] = (0,0,0)) -> None:
        self.frame = Image.new("RGBA", (self.width, self.height),
                               color + (255,))

    def blit(self, image: Image.Image, x: int, y: int,
             alpha: int = 255, scale: float = 1.0) -> None:
        if image is None:
            return
        img = image
        if scale != 1.0:
            w = max(1, int(img.width  * scale))
            h = max(1, int(img.height * scale))
            img = img.resize((w, h), Image.NEAREST)
        if alpha < 255:
            r, g, b, a = img.split() if img.mode == "RGBA" else \
                         (*img.convert("RGB").split(), None)
            if a is not None:
                from PIL import ImageEnhance
                a = a.point(lambda p: int(p * alpha / 255))
                img = Image.merge("RGBA", (r, g, b, a))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        self.frame.paste(img, (int(x), int(y)), img)

    def draw_rect(self, x: int, y: int, w: int, h: int,
                  color: Tuple[int,int,int,int] = (255,255,255,255),
                  fill: bool = False) -> None:
        draw = ImageDraw.Draw(self.frame)
        rect = [x, y, x + w, y + h]
        if fill:
            draw.rectangle(rect, fill=color)
        else:
            draw.rectangle(rect, outline=color)

    def draw_text(self, text: str, x: int, y: int,
                  color: Tuple[int,int,int] = (255,255,255),
                  size: int = 12) -> None:
        draw = ImageDraw.Draw(self.frame)
        draw.text((x, y), text, fill=color)

    def flip(self) -> None:
        """Present the current frame — implemented by each backend."""
        # Frame-rate throttling
        now = time.time()
        wait = (1.0 / self._fps_target) - (now - self._last_flip)
        if wait > 0:
            time.sleep(wait)
        self._last_flip = time.time()
        self._present()

    def _present(self) -> None:
        """Backend-specific: display the frame."""
        pass

    def poll_events(self) -> List[Event]:
        evs = list(self._events)
        self._events.clear()
        return evs

    def destroy(self) -> None:
        self._running = False

    def is_open(self) -> bool:
        return self._running

    def set_fps(self, fps: int) -> None:
        self._fps_target = max(1, fps)

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, width: int = 960, height: int = 720,
               title: str = "I.K.E.M.E.N") -> "Window":
        """Create the best available window."""
        # 1. Try pygame
        try:
            return PygameWindow(width, height, title)
        except Exception:
            pass
        # 2. Try tkinter
        try:
            return TkWindow(width, height, title)
        except Exception:
            pass
        # 3. Headless
        return HeadlessWindow(width, height, title)


# ── Pygame backend ──────────────────────────────────────────────────────────

class PygameWindow(Window):
    def __init__(self, width: int, height: int, title: str):
        super().__init__(width, height, title)
        import pygame, platform, os
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        pygame.init()
        pygame.display.set_caption(title)
        # RESIZABLE helps macOS register the window with the OS compositor
        flags = pygame.RESIZABLE if platform.system() == "Darwin" else 0
        self._screen = pygame.display.set_mode((width, height), flags)
        # Force window to front on macOS
        if platform.system() == "Darwin":
            try:
                import AppKit  # type: ignore
                AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass
        # Initial black flip so the window registers with the OS immediately
        self._screen.fill((0, 0, 0))
        pygame.display.flip()
        self._pygame = pygame
        self._key_map = self._build_key_map(pygame)
        print(f"[sdl] Window opened: {width}x{height} (PygameWindow)",
              file=sys.stderr, flush=True)

    def _build_key_map(self, pg) -> dict:
        return {
            pg.K_UP: "UP", pg.K_DOWN: "DOWN",
            pg.K_LEFT: "LEFT", pg.K_RIGHT: "RIGHT",
            pg.K_RETURN: "RETURN", pg.K_ESCAPE: "ESCAPE",
            pg.K_a: "a", pg.K_s: "s", pg.K_d: "d",
            pg.K_z: "z", pg.K_x: "x", pg.K_c: "c",
            pg.K_q: "q", pg.K_w: "w", pg.K_e: "e",
            pg.K_SPACE: "SPACE", pg.K_LSHIFT: "LSHIFT",
            pg.K_RSHIFT: "RSHIFT", pg.K_F1: "F1", pg.K_F2: "F2",
            pg.K_F3: "F3", pg.K_F4: "F4", pg.K_F5: "F5",
        }

    def _present(self) -> None:
        pg = self._pygame
        data = self.frame.tobytes()
        size = (self.width, self.height)
        # pygame 2.1.3+ prefers frombuffer (zero-copy); fall back for older builds
        try:
            surf = pg.image.frombuffer(data, size, "RGBA")
        except AttributeError:
            try:
                surf = pg.image.frombytes(data, size, "RGBA")
            except AttributeError:
                surf = pg.image.fromstring(data, size, "RGBA")
        self._screen.blit(surf, (0, 0))
        pg.display.flip()

    def poll_events(self) -> List[Event]:
        pg = self._pygame
        evs: List[Event] = []
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self._running = False
                evs.append(("quit", None))
            elif event.type == pg.KEYDOWN:
                key = self._key_map.get(event.key, str(event.key))
                evs.append(("key_down", key))
            elif event.type == pg.KEYUP:
                key = self._key_map.get(event.key, str(event.key))
                evs.append(("key_up", key))
        evs.extend(self._events)
        self._events.clear()
        return evs

    def destroy(self) -> None:
        super().destroy()
        try:
            self._pygame.quit()
        except Exception:
            pass


# ── Tkinter backend ─────────────────────────────────────────────────────────

class TkWindow(Window):
    def __init__(self, width: int, height: int, title: str):
        super().__init__(width, height, title)
        import tkinter as tk
        from PIL import ImageTk

        self._tk = tk
        self._ImageTk = ImageTk
        self._event_q: queue.Queue = queue.Queue()

        # Tkinter must run on the main thread; run it in a thread
        self._ready = threading.Event()
        self._tk_thread = threading.Thread(
            target=self._tk_main, args=(width, height, title), daemon=True)
        self._tk_thread.start()
        self._ready.wait(timeout=5.0)

    def _tk_main(self, w: int, h: int, title: str) -> None:
        tk = self._tk
        root = tk.Tk()
        root.title(title)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        canvas = tk.Canvas(root, width=w, height=h, bg="black",
                           highlightthickness=0)
        canvas.pack()
        self._root   = root
        self._canvas = canvas
        self._photo  = None

        root.bind("<KeyPress>",   self._on_key_down)
        root.bind("<KeyRelease>", self._on_key_up)

        self._ready.set()
        root.mainloop()

    def _on_close(self) -> None:
        self._running = False
        self._event_q.put(("quit", None))
        try:
            self._root.destroy()
        except Exception:
            pass

    def _on_key_down(self, event) -> None:
        self._event_q.put(("key_down", event.keysym))

    def _on_key_up(self, event) -> None:
        self._event_q.put(("key_up", event.keysym))

    def _present(self) -> None:
        try:
            photo = self._ImageTk.PhotoImage(self.frame)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=photo)
            self._photo = photo   # keep reference
            self._root.update()
        except Exception:
            pass

    def poll_events(self) -> List[Event]:
        evs: List[Event] = list(self._events)
        self._events.clear()
        while not self._event_q.empty():
            try:
                evs.append(self._event_q.get_nowait())
            except queue.Empty:
                break
        return evs

    def destroy(self) -> None:
        super().destroy()
        try:
            self._root.destroy()
        except Exception:
            pass


# ── Headless backend ────────────────────────────────────────────────────────

class HeadlessWindow(Window):
    """No-display window — runs the engine loop without showing anything.
    Useful for testing, servers, and CI."""

    def __init__(self, width: int, height: int, title: str):
        super().__init__(width, height, title)
        print(f"[engine] Headless mode: {width}×{height} '{title}'",
              file=sys.stderr)
        self._frame_count = 0
        self._dump_every  = 0  # set > 0 to save PNG frames

    def _present(self) -> None:
        self._frame_count += 1
        if self._dump_every and self._frame_count % self._dump_every == 0:
            self.frame.save(f"frame_{self._frame_count:06d}.png")

    def poll_events(self) -> List[Event]:
        evs = list(self._events)
        self._events.clear()
        return evs
