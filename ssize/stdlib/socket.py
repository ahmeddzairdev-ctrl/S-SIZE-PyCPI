"""
socket.ssz — TCP socket wrapper for online multiplayer.

The real engine uses raw BSD sockets for peer-to-peer fight sync.
This stub provides just enough for the scripts to load.
"""
import socket as _socket
import sys


class SSZSocket:
    """A TCP socket wrapper."""

    def __init__(self):
        self._sock = None
        self._connected = False

    def connect(self, host: str, port: int) -> bool:
        try:
            self._sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            self._sock.connect((str(host), int(port)))
            self._connected = True
            return True
        except Exception as e:
            print(f"[ssz/socket] connect failed: {e}", file=sys.stderr)
            return False

    def listen(self, port: int) -> bool:
        try:
            self._sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            self._sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            self._sock.bind(("", int(port)))
            self._sock.listen(1)
            return True
        except Exception as e:
            print(f"[ssz/socket] listen failed: {e}", file=sys.stderr)
            return False

    def accept(self) -> "SSZSocket":
        if not self._sock:
            return SSZSocket()
        try:
            conn, _ = self._sock.accept()
            s = SSZSocket()
            s._sock = conn
            s._connected = True
            return s
        except Exception:
            return SSZSocket()

    def send(self, data) -> int:
        if not self._sock:
            return 0
        try:
            if isinstance(data, str):
                data = data.encode("utf-8")
            return self._sock.send(bytes(data))
        except Exception:
            return 0

    def recv(self, size: int = 1024) -> bytes:
        if not self._sock:
            return b""
        try:
            return self._sock.recv(int(size))
        except Exception:
            return b""

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._connected = False

    def isConnected(self) -> bool:
        return self._connected


def register(env, interpreter) -> None:
    env.define("Socket", lambda: SSZSocket())
    env.define("connect", lambda h, p: SSZSocket().connect(h, p))
