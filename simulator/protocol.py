"""
D2-Bus Protocol Handler — Slave Mode

Full AE99 channel complement:
  Inputs  (slave → master):
    AIN  0–20   21 analog inputs     (16-bit, 3 banks)
    DIN  21–23   3 digital inputs     (in AIN bank 2)
    CNT  0–15   16 counter inputs    (2 banks × 8, 16-bit)
    ENC  0–11   12 encoder inputs    (3 banks × 4, 16-bit)
    DIG  0–23   24 digital inputs    (3 bytes, 1 bit per channel)
    TEMP 1–4     4 temperature inputs (16-bit, degree C = (raw/100)−100)

  Outputs (master → slave):
    PWM  0–23   24 PWM outputs       (8-bit or 16-bit, 3 banks)
    APW  0–23   24 analog power enables (1 bit per output)
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


@dataclass
class DeviceState:
    """Complete simulated state of an AE99 Kyst card."""

    # ── Identity ──────────────────────────────────────────────────────────────
    node_address:    int = 0x1
    fw_version:      int = 0x02
    fw_sub_version:  int = 0x03
    fw_day:          int = 0x01
    fw_month:        int = 0x01
    fw_year:         int = 0x25

    # ── Global status ──────────────────────────────────────────────────────────
    online:                  bool = True
    reset_flag:              bool = True
    leak_1:                  bool = False
    leak_2:                  bool = False
    analog_power_overload:   bool = False
    pwm_bank1_overload:      bool = False
    pwm_bank2_overload:      bool = False
    pwm_bank3_overload:      bool = False

    # ── Analog inputs: AIN 0–20 (21 channels, 16-bit) ────────────────────────
    analog_inputs: list[int] = field(default_factory=lambda: [0] * 21)

    # ── Digital inputs: DIN 21–23 (returned alongside AIN bank 2) ────────────
    digital_inputs: list[bool] = field(default_factory=lambda: [False] * 3)

    # ── Counter inputs: CNT 0–15 (16 channels, 16-bit) ───────────────────────
    counter_inputs: list[int] = field(default_factory=lambda: [0] * 16)

    # ── Encoder inputs: ENC 0–11 (12 channels, 16-bit) ───────────────────────
    encoder_inputs: list[int] = field(default_factory=lambda: [0] * 12)

    # ── Digital inputs word: DIG 0–23 (3 bytes, 8 channels per byte) ─────────
    digital_word: list[int] = field(default_factory=lambda: [0] * 3)  # [DIG0-7, DIG8-15, DIG16-23]

    # ── Temperature inputs: TEMP 1–4 — raw = (deg_C + 100) × 100 ─────────────
    # e.g. 36.15°C → 13615
    temperature_inputs: list[int] = field(default_factory=lambda: [13615] * 4)

    # ── Board health ───────────────────────────────────────────────────────────
    board_temp_raw:    int = 13615    # (deg_C + 100) × 100
    board_voltage_raw: int = 2400     # voltage × 100

    # ── Reply delay ────────────────────────────────────────────────────────────
    reply_delay_100us: int = 20       # default 2ms

    # ── Analog input mode: 1 bit per AIN channel (0=voltage, 1=current) ───────
    ain_mode: int = 0x000000

    # ── PWM driver status (per bank) ──────────────────────────────────────────
    pwm1_driver_status: int = 0x04
    pwm2_driver_status: int = 0x04
    pwm3_driver_status: int = 0x04
    pwm1_overload:      int = 0x00
    pwm2_overload:      int = 0x00
    pwm3_overload:      int = 0x00

    def global_status_byte(self) -> int:
        b = 0
        if self.pwm_bank1_overload:    b |= 0x01
        if self.pwm_bank2_overload:    b |= 0x02
        if self.pwm_bank3_overload:    b |= 0x04
        if self.analog_power_overload: b |= 0x08
        if self.leak_1:                b |= 0x10
        if self.leak_2:                b |= 0x20
        if self.reset_flag:            b |= 0x80
        return b


class ProtocolHandler:
    def __init__(self, state: DeviceState | None = None):
        self.state = state or DeviceState()

    def handle(self, telegram: MasterTelegram) -> bytes | None:
        if not self.state.online:
            return None

        expected_addr = (0x3 << 4) | (self.state.node_address & 0x0F)
        if telegram.address_byte != expected_addr:
            return None

        if not telegram.crc_valid:
            logger.warning("CRC invalid — ignoring telegram")
            return None

        if telegram.kind == TelegramKind.AB:
            return self._handle_type_ab(telegram)
        elif telegram.kind == TelegramKind.C:
            return self._handle_type_c(telegram)
        return None

    # ── Type AB ────────────────────────────────────────────────────────────────

    def _handle_type_ab(self, t: MasterTelegram) -> bytes:
        s = self.state
        payload = bytes([s.global_status_byte()])

        # ── Optional A banks (AIN) ─────────────────────────────────────────────
        if t.ain_bank0_enabled:       # AIN 0–7
            for i in range(8):
                payload += struct.pack("<H", s.analog_inputs[i])

        if t.ain_bank1_enabled:       # AIN 8–15
            for i in range(8, 16):
                payload += struct.pack("<H", s.analog_inputs[i])

        if t.ain_bank2_enabled:       # AIN 16–20 + DIN 21–23
            for i in range(16, 21):
                payload += struct.pack("<H", s.analog_inputs[i])
            for din in s.digital_inputs:   # DIN 21, 22, 23 as 16-bit words
                payload += struct.pack("<H", 1 if din else 0)

        # ── Optional B banks ──────────────────────────────────────────────────
        if t.cnt_bank1_enabled:       # CNT 0–7
            for i in range(8):
                payload += struct.pack("<H", s.counter_inputs[i])

        if t.cnt_bank2_enabled:       # CNT 8–15
            for i in range(8, 16):
                payload += struct.pack("<H", s.counter_inputs[i])

        if t.enc_bank1_enabled:       # ENC 0–3
            for i in range(4):
                payload += struct.pack("<H", s.encoder_inputs[i])

        if t.enc_bank2_enabled:       # ENC 4–7
            for i in range(4, 8):
                payload += struct.pack("<H", s.encoder_inputs[i])

        if t.enc_bank3_enabled:       # ENC 8–11
            for i in range(8, 12):
                payload += struct.pack("<H", s.encoder_inputs[i])

        if t.dig_25pct_enabled:       # DIG 0–23 (3 bytes)
            for byte_val in s.digital_word:
                payload += bytes([byte_val])

        if t.temp_12_enabled:         # TEMP 1–2
            payload += struct.pack("<H", s.temperature_inputs[0])
            payload += struct.pack("<H", s.temperature_inputs[1])

        if t.temp_34_enabled:         # TEMP 3–4
            payload += struct.pack("<H", s.temperature_inputs[2])
            payload += struct.pack("<H", s.temperature_inputs[3])

        return build_slave_reply(payload)

    # ── Type C ────────────────────────────────────────────────────────────────

    def _handle_type_c(self, t: MasterTelegram) -> bytes:
        cmd = t.type_c_cmd

        if cmd == TypeCCmd.VERSION_INFO:
            return self._reply_version()

        elif cmd == TypeCCmd.RESET_FLAG:
            self.state.reset_flag = False
            return self._reply_ack()

        elif cmd == TypeCCmd.DIP_SWITCH:
            option = 0x4
            node   = self.state.node_address & 0x0F
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
        return build_slave_reply(bytes([0x06]))

    def _reply_version(self) -> bytes:
        s = self.state
        return build_slave_reply(bytes([
            s.fw_version, s.fw_sub_version,
            s.fw_day, s.fw_month, s.fw_year,
            0x01 if s.reset_flag else 0x00
        ]))

    def _reply_status_flags(self) -> bytes:
        s = self.state
        payload = bytes([
            s.pwm1_driver_status, s.pwm1_overload,
            s.pwm2_driver_status, s.pwm2_overload,
            s.pwm3_driver_status, s.pwm3_overload,
            0x00, 0x00, 0x00,   # APW overloads 0–7, 8–15, 16–23
        ]) + struct.pack("<H", s.board_temp_raw) + struct.pack("<H", s.board_voltage_raw)
        return build_slave_reply(payload)
