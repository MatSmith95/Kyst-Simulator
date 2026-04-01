"""
D2-Bus Protocol Handler — Slave Mode

Receives a parsed MasterTelegram and returns the correct slave reply bytes
based on the simulated device state.

This is the core of the simulator — all Kyst card behaviour lives here.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import struct
import logging

from simulator.telegram import (
    MasterTelegram, TelegramKind, TypeCCmd,
    build_slave_reply
)

logger = logging.getLogger(__name__)


# ── Simulated device state ────────────────────────────────────────────────────

@dataclass
class DeviceState:
    """
    Holds the full simulated state of a Kyst AE99 drivercard.
    All values here are what the simulator will report back to the PLC.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    node_address: int = 0x1          # DIP switch node (0x0–0xF)
    fw_version: int = 0x02
    fw_sub_version: int = 0x03
    fw_day: int = 0x01
    fw_month: int = 0x01
    fw_year: int = 0x25              # year 2025 = 25

    # ── Global status flags ───────────────────────────────────────────────────
    online: bool = True              # if False, no response at all
    reset_flag: bool = True          # set after power-on; cleared by Type C 0x01
    leak_1: bool = False             # water leak detect 1
    leak_2: bool = False             # water leak detect 2
    analog_power_overload: bool = False
    pwm_bank1_overload: bool = False
    pwm_bank2_overload: bool = False
    pwm_bank3_overload: bool = False

    # ── Analog inputs (AIN 0–20, 16-bit, little-endian) ─────────────────────
    analog_inputs: list[int] = field(default_factory=lambda: [0] * 21)

    # ── Board health ──────────────────────────────────────────────────────────
    # Temperature: stored as (deg_C + 100) * 100  e.g. 36.15°C = 13615
    board_temp_raw: int = 13615
    # Voltage: stored as voltage * 100  e.g. 24.00V = 2400
    board_voltage_raw: int = 2400

    # ── Reply delay ───────────────────────────────────────────────────────────
    reply_delay_100us: int = 20      # default 20 × 100µs = 2ms

    # ── Analog input mode (0=voltage, 1=current per bit for AIN 0–23) ────────
    ain_mode: int = 0x000000         # 24 bits, 0 = voltage (Hi-Z), 1 = current (Lo-Z)

    # ── PWM driver status (per bank) ─────────────────────────────────────────
    # byte: [global_err, comm_err, chip_reset_n, over_temp, n/a, open_load, stk_on, fail_save]
    pwm1_driver_status: int = 0x04   # chip_reset_n = 1 = normal (active low)
    pwm2_driver_status: int = 0x04
    pwm3_driver_status: int = 0x04
    pwm1_overload: int = 0x00
    pwm2_overload: int = 0x00
    pwm3_overload: int = 0x00

    def global_status_byte(self) -> int:
        """Build the Drivercard Global Status byte."""
        b = 0
        if self.pwm_bank1_overload:    b |= 0x01
        if self.pwm_bank2_overload:    b |= 0x02
        if self.pwm_bank3_overload:    b |= 0x04
        if self.analog_power_overload: b |= 0x08
        if self.leak_1:                b |= 0x10
        if self.leak_2:                b |= 0x20
        # bit 6 = spare
        if self.reset_flag:            b |= 0x80
        return b


# ── Protocol handler ──────────────────────────────────────────────────────────

class ProtocolHandler:
    """
    Processes a MasterTelegram and returns the correct slave reply bytes.
    Instantiate once per simulated device and call handle() for each telegram.
    """

    def __init__(self, state: DeviceState | None = None):
        self.state = state or DeviceState()

    def handle(self, telegram: MasterTelegram) -> bytes | None:
        """
        Process a master telegram and return slave reply bytes.
        Returns None if the device should not respond (offline or address mismatch).
        """
        if not self.state.online:
            logger.debug("Device offline — no response")
            return None

        # Check address matches
        expected_addr = (0x3 << 4) | (self.state.node_address & 0x0F)
        if telegram.address_byte != expected_addr:
            logger.debug(
                f"Address mismatch: got 0x{telegram.address_byte:02X}, "
                f"expected 0x{expected_addr:02X} — ignoring"
            )
            return None

        if not telegram.crc_valid:
            logger.warning(f"CRC invalid on received telegram — ignoring")
            return None

        if telegram.kind == TelegramKind.AB:
            return self._handle_type_ab(telegram)
        elif telegram.kind == TelegramKind.C:
            return self._handle_type_c(telegram)

        logger.warning(f"Unknown telegram kind: {telegram.kind}")
        return None

    # ── Type AB handler ────────────────────────────────────────────────────────

    def _handle_type_ab(self, t: MasterTelegram) -> bytes:
        """
        Build the slave AB reply.
        Structure: 0x52 | Global Status | [optional data banks] | CRC
        """
        payload = bytes([self.state.global_status_byte()])

        # AIN Bank 0 (AIN 0–7, 16-bit little-endian words)
        if t.ain_bank0_enabled:
            for i in range(8):
                payload += struct.pack("<H", self.state.analog_inputs[i])

        # AIN Bank 1 (AIN 8–15)
        if t.ain_bank1_enabled:
            for i in range(8, 16):
                payload += struct.pack("<H", self.state.analog_inputs[i])

        # AIN Bank 2 (AIN 16–20 + DIN 21–23 as 16-bit words)
        if t.ain_bank2_enabled:
            for i in range(16, 21):
                payload += struct.pack("<H", self.state.analog_inputs[i])
            # DIN 21, 22, 23 — simulated as 0
            payload += struct.pack("<H", 0)  # DIN 21
            payload += struct.pack("<H", 0)  # DIN 22
            payload += struct.pack("<H", 0)  # DIN 23

        # Optional B banks — CNT, ENC, DIG, TEMP — return zeros as placeholder
        if t.cnt_bank1_enabled:
            payload += bytes(16)  # CNT 0–7, 2 bytes each
        if t.cnt_bank2_enabled:
            payload += bytes(16)  # CNT 8–15

        if t.enc_bank1_enabled:
            payload += bytes(8)   # ENC 0–3
        if t.enc_bank2_enabled:
            payload += bytes(8)   # ENC 4–7
        if t.enc_bank3_enabled:
            payload += bytes(8)   # ENC 8–11

        if t.dig_25pct_enabled:
            payload += bytes(3)   # DIG 0–23 (3 bytes)

        if t.temp_12_enabled:
            payload += struct.pack("<H", self.state.board_temp_raw)   # TEMP 1
            payload += struct.pack("<H", self.state.board_temp_raw)   # TEMP 2
        if t.temp_34_enabled:
            payload += struct.pack("<H", self.state.board_temp_raw)   # TEMP 3
            payload += struct.pack("<H", self.state.board_temp_raw)   # TEMP 4

        reply = build_slave_reply(payload)
        logger.debug(f"Type AB reply: {reply.hex()}")
        return reply

    # ── Type C handler ─────────────────────────────────────────────────────────

    def _handle_type_c(self, t: MasterTelegram) -> bytes:
        cmd = t.type_c_cmd
        logger.debug(f"Type C command: {cmd}")

        if cmd == TypeCCmd.VERSION_INFO:
            return self._reply_version()

        elif cmd == TypeCCmd.RESET_FLAG:
            self.state.reset_flag = False
            return self._reply_ack()

        elif cmd == TypeCCmd.DIP_SWITCH:
            option = 0x40  # placeholder OPTION nibble
            node  = self.state.node_address & 0x0F
            return build_slave_reply(bytes([(option << 4) | node]))

        elif cmd == TypeCCmd.RESET_OUTPUTS:
            self.state.pwm_bank1_overload = False
            self.state.pwm_bank2_overload = False
            self.state.pwm_bank3_overload = False
            self.state.analog_power_overload = False
            return self._reply_ack()

        elif cmd == TypeCCmd.STATUS_FLAGS:
            return self._reply_status_flags()

        elif cmd == TypeCCmd.ANALOG_INPUT_SETUP:
            # Store the ain_mode from the 3 data bytes
            if len(t.payload) >= 3:
                self.state.ain_mode = (t.payload[2] << 16) | (t.payload[1] << 8) | t.payload[0]
            return self._reply_ack()

        elif cmd == TypeCCmd.REPLY_DELAY:
            if len(t.payload) >= 1:
                self.state.reply_delay_100us = t.payload[0]
            return self._reply_ack()

        else:
            logger.warning(f"Unknown Type C command: 0x{int(t.type_b):02X}")
            return self._reply_ack()

    # ── Reply builders ─────────────────────────────────────────────────────────

    def _reply_ack(self) -> bytes:
        """ACK reply: 0x52 0x06 CRC"""
        return build_slave_reply(bytes([0x06]))

    def _reply_version(self) -> bytes:
        s = self.state
        payload = bytes([
            s.fw_version,
            s.fw_sub_version,
            s.fw_day,
            s.fw_month,
            s.fw_year,
            0x01 if s.reset_flag else 0x00   # RST
        ])
        return build_slave_reply(payload)

    def _reply_status_flags(self) -> bytes:
        s = self.state
        payload = bytes([
            s.pwm1_driver_status,
            s.pwm1_overload,
            s.pwm2_driver_status,
            s.pwm2_overload,
            s.pwm3_driver_status,
            s.pwm3_overload,
            0x00,  # APW 0–7 overload
            0x00,  # APW 8–15 overload
            0x00,  # APW 16–23 overload
        ]) + struct.pack("<H", s.board_temp_raw) + struct.pack("<H", s.board_voltage_raw)
        return build_slave_reply(payload)
