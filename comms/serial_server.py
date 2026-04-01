"""
Kyst Simulator — Serial Server (Slave Mode)

Listens on a COM port for incoming D2-Bus commands from the PLC (master).
Configurable baud rate, parity, stop bits, and data bits.

Default D2-Bus settings: 57600 / 8-N-1

Requires: pyserial  (pip install pyserial)
"""

from __future__ import annotations
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Parity constants (mirrors pyserial values for easy use without importing serial everywhere)
PARITY_NONE  = "N"
PARITY_EVEN  = "E"
PARITY_ODD   = "O"
PARITY_MARK  = "M"
PARITY_SPACE = "S"

SUPPORTED_BAUD_RATES = [
    1200, 2400, 4800, 9600, 14400, 19200,
    38400, 57600, 115200, 230400, 460800, 921600
]


class SerialServer:
    def __init__(
        self,
        port: str = "COM1",
        baud_rate: int = 57600,
        data_bits: int = 8,
        parity: str = PARITY_NONE,
        stop_bits: float = 1.0,
        read_timeout: float = 1.0,
        on_receive: Callable[[bytes], bytes | None] | None = None,
        on_open: Callable[[str, int], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ):
        """
        :param port:         COM port name, e.g. "COM3" (Windows) or "/dev/ttyUSB0" (Linux)
        :param baud_rate:    Baud rate — D2-Bus default is 57600
        :param data_bits:    Data bits (5, 6, 7, or 8) — D2-Bus uses 8
        :param parity:       "N"=None, "E"=Even, "O"=Odd — D2-Bus uses N
        :param stop_bits:    Stop bits (1, 1.5, or 2) — D2-Bus uses 1
        :param read_timeout: How long to block waiting for data (seconds)
        :param on_receive:   callback(data: bytes) -> response: bytes | None
        :param on_open:      callback(port, baud_rate) when port opens successfully
        :param on_close:     callback() when port closes
        """
        self.port         = port
        self.baud_rate    = baud_rate
        self.data_bits    = data_bits
        self.parity       = parity
        self.stop_bits    = stop_bits
        self.read_timeout = read_timeout
        self.on_receive   = on_receive
        self.on_open      = on_open
        self.on_close     = on_close

        self._serial      = None
        self._running     = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """
        Open the serial port and start the read loop in a background thread.
        Raises serial.SerialException if the port cannot be opened.
        """
        try:
            import serial
        except ImportError:
            raise RuntimeError(
                "pyserial is not installed. Run: pip install pyserial"
            )

        import serial as _serial

        self._serial = _serial.Serial(
            port     = self.port,
            baudrate = self.baud_rate,
            bytesize = self.data_bits,
            parity   = self.parity,
            stopbits = self.stop_bits,
            timeout  = self.read_timeout,
        )

        self._running = True
        self._thread  = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

        logger.info(
            f"Serial port opened: {self.port} @ {self.baud_rate}/{self.data_bits}"
            f"-{self.parity}-{self.stop_bits}"
        )

        if self.on_open:
            self.on_open(self.port, self.baud_rate)

    def stop(self) -> None:
        """Stop the read loop and close the serial port."""
        self._running = False

        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning(f"Error closing serial port: {e}")

        self._serial = None
        logger.info("Serial port closed")

        if self.on_close:
            self.on_close()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # ── Internal ───────────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        """
        Continuously read from the serial port.

        D2-Bus telegrams are framed by the 0x51 start byte.
        We read until we have a complete telegram by watching for:
          - The start byte 0x51
          - Minimum length (5 bytes)
          - CRC validation (done in connection_manager via on_receive)

        For simplicity we use timeout-based framing: read whatever arrives
        within the read_timeout window and pass it to on_receive. The protocol
        handler will validate the CRC and reject garbage.
        """
        buffer = bytearray()

        while self._running:
            try:
                if self._serial is None or not self._serial.is_open:
                    break

                chunk = self._serial.read(256)
                if not chunk:
                    # Timeout — if we have buffered bytes, pass them up
                    if buffer:
                        self._dispatch(bytes(buffer))
                        buffer.clear()
                    continue

                buffer.extend(chunk)

                # Simple framing: look for 0x51 start byte and dispatch
                # when we've accumulated what looks like a complete telegram
                while len(buffer) >= 5:
                    # Find the start byte
                    start_idx = buffer.find(0x51)
                    if start_idx == -1:
                        # No start byte found — discard everything
                        logger.debug(f"Discarding {len(buffer)} bytes — no start byte")
                        buffer.clear()
                        break
                    if start_idx > 0:
                        # Discard junk before start byte
                        logger.debug(f"Discarding {start_idx} leading junk bytes")
                        del buffer[:start_idx]

                    # We have a potential telegram starting at buffer[0]
                    # Minimum valid telegram is 5 bytes — wait for more if needed
                    if len(buffer) < 5:
                        break

                    # Determine expected length from telegram type and banks
                    # For now dispatch when we have a pause (read returned less than buffer)
                    # A more robust approach is to calculate length from the type bytes
                    expected_len = self._estimate_length(buffer)
                    if expected_len and len(buffer) >= expected_len:
                        telegram_bytes = bytes(buffer[:expected_len])
                        del buffer[:expected_len]
                        self._dispatch(telegram_bytes)
                    else:
                        # Wait for more bytes
                        break

            except Exception as e:
                if self._running:
                    logger.error(f"Serial read error: {e}")
                    self.stop()
                break

    def _estimate_length(self, buf: bytearray) -> int | None:
        """
        Estimate the total telegram length from the type bytes.
        Returns None if more bytes are needed to determine length.

        D2-Bus Type C telegrams have a fixed small size.
        Type AB length depends on which optional banks are enabled.
        """
        if len(buf) < 4:
            return None

        type_a = buf[2]
        type_b = buf[3]

        is_type_c = not bool(type_a & 0x80)

        if is_type_c:
            cmd = buf[3] if len(buf) > 3 else None
            # Type C data lengths (payload bytes after the 4 header bytes, before CRC)
            type_c_data_lengths = {
                0x00: 0,   # Version Info — no extra data
                0x01: 0,   # Reset Flag
                0x02: 0,   # DIP Switch
                0x03: 0,   # Reset Outputs
                0x06: 0,   # Status Flags
                0x08: 3,   # Analog Input Setup — 3 data bytes
                0x09: 1,   # Reply Delay — 1 data byte
            }
            data_len = type_c_data_lengths.get(cmd, 0)
            return 4 + data_len + 1   # header(4) + data + CRC(1)
        else:
            # Type AB — calculate based on enabled banks
            return self._calc_ab_length(type_a, type_b)

    def _calc_ab_length(self, type_a: int, type_b: int) -> int:
        """
        Calculate expected Type AB master telegram length.
        Header: 5 bytes (start, addr, typeA, typeB, pwm_freq)
        Obligatory: 3 bytes (analog power outputs APW 0-23)
        Optional banks add variable bytes.
        CRC: 1 byte
        """
        # Fixed: start(1) + addr(1) + typeA(1) + typeB(1) + pwm_freq(1) + APW(3) = 8
        length = 8

        pwm_16bit = bool(type_a & 0x01)
        pwm_bytes = 2 if pwm_16bit else 1

        if type_a & 0x02: length += 8  * pwm_bytes   # PWM Bank 1 (PWM 0–7)
        if type_a & 0x04: length += 8  * pwm_bytes   # PWM Bank 2 (PWM 8–15)
        if type_a & 0x08: length += 8  * pwm_bytes   # PWM Bank 3 (PWM 16–23)

        # AIN banks are input-only (slave reply) — not in master telegram
        # Type B optional banks — master doesn't send these either

        length += 1   # CRC
        return length

    def _dispatch(self, data: bytes) -> None:
        """Pass received bytes to the on_receive callback and write the response."""
        if not data:
            return
        logger.debug(f"Serial RX: {data.hex()}")

        response = None
        if self.on_receive:
            response = self.on_receive(data)

        if response and self._serial and self._serial.is_open:
            try:
                self._serial.write(response)
                logger.debug(f"Serial TX: {response.hex()}")
            except Exception as e:
                logger.error(f"Serial write error: {e}")

    @staticmethod
    def list_ports() -> list[str]:
        """Return a list of available serial port names on this system."""
        try:
            import serial.tools.list_ports
            return [p.device for p in serial.tools.list_ports.comports()]
        except ImportError:
            return []
