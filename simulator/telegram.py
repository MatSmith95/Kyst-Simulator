"""
D2-Bus Telegram Parser & Builder

Master telegram structure:
  Byte 1:   0x51 ('Q') — start character
  Byte 2:   Device address (TYPE nibble | NODE nibble)
  Byte 3:   Telegram Type A byte  (bit 7 always TRUE for AB, FALSE for C)
  Byte 4:   Telegram Type B byte  (AB only) / Command byte (C only)
  Byte 5+:  Data payload (variable length, type-dependent)
  Last:     CRC byte

Slave reply structure:
  Byte 1:   0x52 ('R') — start character
  Byte 2+:  Reply data (variable length, type-dependent)
  Last:     CRC byte
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
import struct

from simulator import crc as crc_engine


# ── Constants ──────────────────────────────────────────────────────────────────

MASTER_START = 0x51   # ASCII 'Q'
SLAVE_START  = 0x52   # ASCII 'R'

DEVICE_TYPE_AE99 = 0x3  # TYPE nibble for AE99 hydraulics drivercard

# Type C command codes
class TypeCCmd(IntEnum):
    VERSION_INFO      = 0x00
    RESET_FLAG        = 0x01
    DIP_SWITCH        = 0x02
    RESET_OUTPUTS     = 0x03
    STATUS_FLAGS      = 0x06
    ANALOG_INPUT_SETUP = 0x08
    REPLY_DELAY       = 0x09


class TelegramKind(IntEnum):
    AB = 0   # normal master/slave exchange
    C  = 1   # command / configuration


# ── Parsed telegram dataclasses ───────────────────────────────────────────────

@dataclass
class MasterTelegram:
    """Represents a fully parsed master transmit telegram."""
    raw: bytes
    kind: TelegramKind
    device_type: int         # high nibble of address byte
    node_address: int        # low nibble of address byte
    type_a: int              # Type A byte (byte 3)
    type_b: int              # Type B byte (byte 4) — 0 for Type C
    type_c_cmd: Optional[TypeCCmd]   # set for Type C telegrams
    payload: bytes           # data bytes after type bytes, before CRC
    crc_valid: bool

    @property
    def address_byte(self) -> int:
        return (self.device_type << 4) | (self.node_address & 0x0F)

    # ── Type A flag helpers ──────────────────────────────────────────────────
    @property
    def pwm_8_16bit(self) -> bool:
        return bool(self.type_a & 0x01)

    @property
    def pwm_bank1_enabled(self) -> bool:
        return bool(self.type_a & 0x02)

    @property
    def pwm_bank2_enabled(self) -> bool:
        return bool(self.type_a & 0x04)

    @property
    def pwm_bank3_enabled(self) -> bool:
        return bool(self.type_a & 0x08)

    @property
    def ain_bank0_enabled(self) -> bool:
        return bool(self.type_a & 0x10)

    @property
    def ain_bank1_enabled(self) -> bool:
        return bool(self.type_a & 0x20)

    @property
    def ain_bank2_enabled(self) -> bool:
        return bool(self.type_a & 0x40)

    # ── Type B flag helpers ──────────────────────────────────────────────────
    @property
    def cnt_bank1_enabled(self) -> bool:
        return bool(self.type_b & 0x01)

    @property
    def cnt_bank2_enabled(self) -> bool:
        return bool(self.type_b & 0x02)

    @property
    def enc_bank1_enabled(self) -> bool:
        return bool(self.type_b & 0x04)

    @property
    def enc_bank2_enabled(self) -> bool:
        return bool(self.type_b & 0x08)

    @property
    def enc_bank3_enabled(self) -> bool:
        return bool(self.type_b & 0x10)

    @property
    def dig_25pct_enabled(self) -> bool:
        return bool(self.type_b & 0x20)

    @property
    def temp_12_enabled(self) -> bool:
        return bool(self.type_b & 0x40)

    @property
    def temp_34_enabled(self) -> bool:
        return bool(self.type_b & 0x80)

    def __repr__(self) -> str:
        kind_str = "AB" if self.kind == TelegramKind.AB else f"C({self.type_c_cmd!r})"
        return (
            f"MasterTelegram(kind={kind_str}, addr=0x{self.address_byte:02X}, "
            f"crc_valid={self.crc_valid}, payload={self.payload.hex()})"
        )


@dataclass
class SlaveReply:
    """Represents a fully parsed slave reply telegram."""
    raw: bytes
    payload: bytes           # everything between 'R' and CRC
    crc_valid: bool

    def __repr__(self) -> str:
        return f"SlaveReply(crc_valid={self.crc_valid}, payload={self.payload.hex()})"


# ── Parser ─────────────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass


def parse_master(data: bytes) -> MasterTelegram:
    """
    Parse a raw byte sequence into a MasterTelegram.
    Raises ParseError if the data is malformed.
    """
    if len(data) < 5:
        raise ParseError(f"Telegram too short: {len(data)} bytes (minimum 5)")

    if data[0] != MASTER_START:
        raise ParseError(f"Invalid start byte: 0x{data[0]:02X} (expected 0x51)")

    crc_valid = crc_engine.verify(data)

    address_byte = data[1]
    device_type  = (address_byte >> 4) & 0x0F
    node_address = address_byte & 0x0F

    type_a = data[2]
    type_b = data[3]

    # Type C: bit 7 of type_a is FALSE (0)
    # Type AB: bit 7 of type_a is TRUE (1) — the manual says always set TRUE
    is_type_c = not bool(type_a & 0x80)

    payload = data[4:-1]  # everything after type_b and before CRC

    if is_type_c:
        cmd_byte = type_b
        try:
            cmd = TypeCCmd(cmd_byte)
        except ValueError:
            cmd = None  # unknown command — don't crash, just record it
        return MasterTelegram(
            raw=data, kind=TelegramKind.C,
            device_type=device_type, node_address=node_address,
            type_a=type_a, type_b=type_b,
            type_c_cmd=cmd,
            payload=payload, crc_valid=crc_valid
        )
    else:
        return MasterTelegram(
            raw=data, kind=TelegramKind.AB,
            device_type=device_type, node_address=node_address,
            type_a=type_a, type_b=type_b,
            type_c_cmd=None,
            payload=payload, crc_valid=crc_valid
        )


def parse_slave(data: bytes) -> SlaveReply:
    """Parse a raw byte sequence into a SlaveReply."""
    if len(data) < 3:
        raise ParseError(f"Reply too short: {len(data)} bytes (minimum 3)")

    if data[0] != SLAVE_START:
        raise ParseError(f"Invalid reply start byte: 0x{data[0]:02X} (expected 0x52)")

    crc_valid = crc_engine.verify(data)
    payload = data[1:-1]

    return SlaveReply(raw=data, payload=payload, crc_valid=crc_valid)


# ── Builder ────────────────────────────────────────────────────────────────────

def build_master_type_c(node_address: int, cmd: TypeCCmd, data: bytes = b"") -> bytes:
    """
    Build a Type C master telegram.

    :param node_address: 0x0–0xF (DIP switch node address)
    :param cmd: TypeCCmd command code
    :param data: optional data bytes for this command
    :return: complete telegram bytes including CRC
    """
    address_byte = (DEVICE_TYPE_AE99 << 4) | (node_address & 0x0F)
    # Type C: type_a bit 7 = 0 (FALSE), all other bits don't care → use 0x00
    frame = bytes([MASTER_START, address_byte, 0x00, int(cmd)]) + data
    return crc_engine.append(frame)


def build_master_type_ab(
    node_address: int,
    type_a: int,
    type_b: int,
    pwm_freq: int = 0,
    analog_power_outputs: bytes = b"\x00\x00\x00",
    optional_data: bytes = b""
) -> bytes:
    """
    Build a Type AB master telegram.

    :param node_address: 0x0–0xF
    :param type_a: Type A byte (bit 7 must be set TRUE for AB)
    :param type_b: Type B byte
    :param pwm_freq: PWM frequency byte (not yet implemented in firmware, send 0)
    :param analog_power_outputs: 3 bytes for APW 0-23 (enable/disable each output)
    :param optional_data: all optional data banks concatenated in order
    :return: complete telegram bytes including CRC
    """
    # Ensure bit 7 of type_a is set (AB telegram marker)
    type_a = type_a | 0x80
    address_byte = (DEVICE_TYPE_AE99 << 4) | (node_address & 0x0F)
    frame = (
        bytes([MASTER_START, address_byte, type_a, type_b, pwm_freq])
        + analog_power_outputs
        + optional_data
    )
    return crc_engine.append(frame)


def build_slave_reply(payload: bytes) -> bytes:
    """
    Build a slave reply telegram.

    :param payload: reply data bytes (excluding start byte and CRC)
    :return: complete reply bytes including CRC
    """
    frame = bytes([SLAVE_START]) + payload
    return crc_engine.append(frame)
