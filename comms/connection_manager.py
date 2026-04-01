"""
Kyst Simulator — Connection Manager

Central controller for all connection activity.
Owns either a TCPServer or SerialServer instance depending on mode.
Wires the comms layer to the protocol handler.
Thread-safe — all public methods can be called from the GUI thread.
"""

from __future__ import annotations
import logging
import threading
import time
from enum import Enum, auto
from typing import Callable, Optional

from simulator.protocol import ProtocolHandler, DeviceState
from simulator.telegram import parse_master, ParseError
from comms.tcp_server import TCPServer
from comms.serial_server import SerialServer

logger = logging.getLogger(__name__)


class ConnectionMode(Enum):
    TCP    = auto()
    SERIAL = auto()


class ConnectionState(Enum):
    DISCONNECTED = auto()
    LISTENING    = auto()   # server bound and waiting for a client
    CONNECTED    = auto()   # client actively connected (TCP only; serial = always connected once open)
    ERROR        = auto()


class ConnectionManager:
    """
    Manages the lifecycle of the active connection.

    Usage:
        mgr = ConnectionManager(on_log=my_log_fn, on_state_change=my_state_fn)
        mgr.start_tcp(port=4001)
        # ... later ...
        mgr.stop()
    """

    def __init__(
        self,
        device_state: DeviceState | None = None,
        on_log: Callable[[str, str], None] | None = None,
        on_state_change: Callable[[ConnectionState], None] | None = None,
    ):
        """
        :param device_state:    Shared DeviceState — also read/written by the GUI
        :param on_log:          Callback(message, tag) for the GUI log panel
        :param on_state_change: Callback(ConnectionState) when state changes
        """
        self.device_state     = device_state or DeviceState()
        self._on_log          = on_log
        self._on_state_change = on_state_change

        self._protocol = ProtocolHandler(self.device_state)
        self._server: TCPServer | SerialServer | None = None
        self._mode: ConnectionMode | None = None
        self._state = ConnectionState.DISCONNECTED
        self._lock  = threading.Lock()

        # Stats
        self.rx_count   = 0
        self.tx_count   = 0
        self.crc_errors = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def start_tcp(self, host: str = "0.0.0.0", port: int = 4001) -> None:
        """Start in TCP server mode."""
        with self._lock:
            if self._server is not None:
                self._log("Already connected — stop first.", "err")
                return

            self._mode = ConnectionMode.TCP
            self._server = TCPServer(
                host=host,
                port=port,
                on_receive=self._on_receive,
                on_client_connect=self._on_client_connect,
                on_client_disconnect=self._on_client_disconnect,
            )
            try:
                self._server.start()
                self._set_state(ConnectionState.LISTENING)
                self._log(f"TCP server listening on {host}:{port}", "info")
            except Exception as e:
                self._server = None
                self._set_state(ConnectionState.ERROR)
                self._log(f"Failed to start TCP server: {e}", "err")

    def start_serial(
        self,
        port: str,
        baud_rate: int = 57600,
        data_bits: int = 8,
        parity: str = "N",
        stop_bits: float = 1.0,
    ) -> None:
        """Start in serial server mode."""
        with self._lock:
            if self._server is not None:
                self._log("Already connected — stop first.", "err")
                return

            self._mode = ConnectionMode.SERIAL
            self._server = SerialServer(
                port=port,
                baud_rate=baud_rate,
                data_bits=data_bits,
                parity=parity,
                stop_bits=stop_bits,
                on_receive=self._on_receive,
                on_open=self._on_serial_open,
                on_close=self._on_serial_close,
            )
            try:
                self._server.start()
                # State is set to CONNECTED inside _on_serial_open callback
            except Exception as e:
                self._server = None
                self._set_state(ConnectionState.ERROR)
                self._log(f"Failed to open serial port {port}: {e}", "err")

    def stop(self) -> None:
        """Stop the current connection cleanly."""
        with self._lock:
            if self._server is None:
                return
            try:
                self._server.stop()
            except Exception as e:
                logger.warning(f"Error stopping server: {e}")
            finally:
                self._server = None
                self._mode   = None
                self._set_state(ConnectionState.DISCONNECTED)
                self._log("Disconnected.", "info")

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def mode(self) -> ConnectionMode | None:
        return self._mode

    # ── Internal callbacks (called from comms threads) ─────────────────────────

    def _on_receive(self, data: bytes) -> bytes | None:
        """
        Called by the comms layer when bytes arrive.
        Parses, processes via protocol handler, returns response bytes.
        """
        self.rx_count += 1
        self._log(f"RX  {data.hex().upper()}", "rx")

        try:
            telegram = parse_master(data)
        except ParseError as e:
            self._log(f"Parse error: {e}", "err")
            return None

        if not telegram.crc_valid:
            self.crc_errors += 1
            self._log(f"CRC error (rx={self.rx_count}, crc_errors={self.crc_errors})", "err")
            return None

        # Apply reply delay
        delay_s = (self.device_state.reply_delay_100us * 100) / 1_000_000
        if delay_s > 0:
            time.sleep(delay_s)

        response = self._protocol.handle(telegram)

        if response:
            self.tx_count += 1
            self._log(f"TX  {response.hex().upper()}", "tx")

        return response

    def _on_client_connect(self, addr: tuple) -> None:
        self._set_state(ConnectionState.CONNECTED)
        self._log(f"Client connected: {addr[0]}:{addr[1]}", "info")

    def _on_client_disconnect(self, addr: tuple) -> None:
        self._set_state(ConnectionState.LISTENING)
        self._log(f"Client disconnected: {addr[0]}:{addr[1]}", "info")

    def _on_serial_open(self, port: str, baud: int) -> None:
        self._set_state(ConnectionState.CONNECTED)
        self._log(f"Serial port open: {port} @ {baud} baud", "info")

    def _on_serial_close(self) -> None:
        self._set_state(ConnectionState.DISCONNECTED)
        self._log("Serial port closed.", "info")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_state(self, new_state: ConnectionState) -> None:
        if self._state != new_state:
            self._state = new_state
            if self._on_state_change:
                self._on_state_change(new_state)

    def _log(self, message: str, tag: str = "info") -> None:
        logger.debug(f"[{tag}] {message}")
        if self._on_log:
            self._on_log(message, tag)
