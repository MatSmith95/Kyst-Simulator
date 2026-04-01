"""
D2-Bus Human-Readable Decoder (Phase 6 — Log Polish)

Converts raw telegram bytes into a human-readable description
for the decoded log view.
"""

from __future__ import annotations
import struct
from simulator.telegram import (
    MasterTelegram, SlaveReply, TelegramKind, TypeCCmd,
    parse_master, parse_slave
)


def decode_master(t: MasterTelegram) -> str:
    lines = []
    lines.append(f"▶ MASTER  addr=0x{t.address_byte:02X}  node={t.node_address}  crc={'✓' if t.crc_valid else '✗ BAD'}")

    if t.kind == TelegramKind.C:
        cmd_name = t.type_c_cmd.name if t.type_c_cmd is not None else f"0x{t.type_b:02X}"
        lines.append(f"  Type C  cmd={cmd_name}")
        if t.type_c_cmd == TypeCCmd.REPLY_DELAY and t.payload:
            lines.append(f"  delay={t.payload[0]} × 100µs = {t.payload[0] * 0.1:.1f}ms")
        elif t.type_c_cmd == TypeCCmd.ANALOG_INPUT_SETUP and len(t.payload) >= 3:
            mode = (t.payload[2] << 16) | (t.payload[1] << 8) | t.payload[0]
            lines.append(f"  ain_mode=0x{mode:06X}  (0=voltage, 1=current per bit)")
    else:
        lines.append(f"  Type AB  typeA=0x{t.type_a:02X}  typeB=0x{t.type_b:02X}")
        flags = []
        if t.pwm_bank1_enabled: flags.append("PWM1")
        if t.pwm_bank2_enabled: flags.append("PWM2")
        if t.pwm_bank3_enabled: flags.append("PWM3")
        if t.ain_bank0_enabled: flags.append("AIN0")
        if t.ain_bank1_enabled: flags.append("AIN1")
        if t.ain_bank2_enabled: flags.append("AIN2")
        if t.pwm_8_16bit:       flags.append("16-bit PWM")
        lines.append(f"  banks=[{', '.join(flags) if flags else 'none'}]")

    return "\n".join(lines)


def decode_slave(raw: bytes, cmd_context: TypeCCmd | None = None) -> str:
    try:
        r = parse_slave(raw)
    except Exception:
        return f"◀ SLAVE  (parse error)  raw={raw.hex().upper()}"

    lines = []
    lines.append(f"◀ SLAVE  crc={'✓' if r.crc_valid else '✗ BAD'}  payload_len={len(r.payload)}")
    p = r.payload

    if not p:
        lines.append("  (empty payload)")
        return "\n".join(lines)

    # ACK
    if len(p) == 1 and p[0] == 0x06:
        lines.append("  ACK")
        return "\n".join(lines)

    # Version info reply
    if cmd_context == TypeCCmd.VERSION_INFO and len(p) >= 6:
        lines.append(f"  FW v{p[0]}.{p[1]}  released {p[2]:02d}/{p[3]:02d}/20{p[4]:02d}")
        lines.append(f"  reset_flag={'SET' if p[5] else 'clear'}")
        return "\n".join(lines)

    # Status flags reply
    if cmd_context == TypeCCmd.STATUS_FLAGS and len(p) >= 13:
        def driver_status(b: int) -> str:
            flags = []
            if b & 0x80: flags.append("GLOBAL_ERR")
            if b & 0x40: flags.append("COMM_ERR")
            if not (b & 0x20): flags.append("CHIP_RESET")
            if b & 0x10: flags.append("OVER_TEMP")
            if b & 0x04: flags.append("OPEN_LOAD")
            if b & 0x02: flags.append("STK_ON")
            if b & 0x01: flags.append("FAIL_SAFE")
            return ", ".join(flags) if flags else "OK"

        lines.append(f"  PWM Bank1: status={driver_status(p[0])}  overload={p[1]:08b}")
        lines.append(f"  PWM Bank2: status={driver_status(p[2])}  overload={p[3]:08b}")
        lines.append(f"  PWM Bank3: status={driver_status(p[4])}  overload={p[5]:08b}")
        lines.append(f"  APW overloads: [{p[6]:08b}] [{p[7]:08b}] [{p[8]:08b}]")
        if len(p) >= 13:
            temp_raw  = struct.unpack_from("<H", p, 9)[0]
            volt_raw  = struct.unpack_from("<H", p, 11)[0]
            temp_c    = (temp_raw / 100) - 100
            volt_v    = volt_raw / 100
            lines.append(f"  temp={temp_c:.2f}°C  voltage={volt_v:.2f}V")
        return "\n".join(lines)

    # AB reply — global status byte
    status = p[0]
    status_flags = []
    if status & 0x80: status_flags.append("RESET")
    if status & 0x20: status_flags.append("LEAK2")
    if status & 0x10: status_flags.append("LEAK1")
    if status & 0x08: status_flags.append("APW_OVL")
    if status & 0x04: status_flags.append("PWM3_OVL")
    if status & 0x02: status_flags.append("PWM2_OVL")
    if status & 0x01: status_flags.append("PWM1_OVL")
    lines.append(f"  status=0x{status:02X}  [{', '.join(status_flags) if status_flags else 'OK'}]")

    # Remaining bytes as AIN values if present
    if len(p) > 1:
        ain_bytes = p[1:]
        ain_count = len(ain_bytes) // 2
        ains = struct.unpack_from(f"<{ain_count}H", ain_bytes)
        lines.append(f"  AIN[0:{ain_count}] = {list(ains)}")

    return "\n".join(lines)
