"""
Kyst Simulator — TCP Client (Master Mode)

Connects to a real Kyst card (via IX-USM-1 or direct TCP) as the PLC would.
Sends D2-Bus master telegrams and returns slave replies.
Used in Master Mode where the PC acts as the PLC.
"""

from __future__ import annotations
import socket
import threading
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class TCPClient:
    def __init__(
        self,
        host: str,
        port: int,
        on_log: Callable[[str, str], None] | None = None,
        connect_timeout: float = 5.0,
        recv_timeout: float = 2.0,
    ):
        self.host            = host
        self.port            = port
        self.on_log          = on_log
        self.connect_timeout = connect_timeout
        self.recv_timeout    = recv_timeout

        self._sock: socket.socket | None = None
        self._lock  = threading.Lock()
        self._connected = False

    def connect(self) -> None:
        """Connect to the target device. Raises on failure."""
        with self._lock:
            if self._connected:
                return
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.connect_timeout)
            self._sock.connect((self.host, self.port))
            self._sock.settimeout(self.recv_timeout)
            self._connected = True
            self._log(f"Connected to {self.host}:{self.port}", "info")

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            self._log("Disconnected from target device.", "info")

    def send(self, telegram: bytes) -> bytes | None:
        """
        Send a telegram and wait for a response.
        Returns the raw response bytes, or None on timeout/error.
        """
        with self._lock:
            if not self._connected or self._sock is None:
                self._log("Cannot send — not connected.", "err")
                return None
            try:
                self._sock.sendall(telegram)
                self._log(f"TX  {telegram.hex().upper()}", "tx")
                response = self._sock.recv(1024)
                if response:
                    self._log(f"RX  {response.hex().upper()}", "rx")
                return response if response else None
            except socket.timeout:
                self._log("Timeout waiting for response.", "err")
                return None
            except Exception as e:
                self._log(f"Send error: {e}", "err")
                self._connected = False
                return None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _log(self, msg: str, tag: str) -> None:
        logger.debug(f"[{tag}] {msg}")
        if self.on_log:
            self.on_log(msg, tag)
