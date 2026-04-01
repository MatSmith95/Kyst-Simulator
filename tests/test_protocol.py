"""
D2-Bus Protocol Unit Tests

All test vectors taken directly from the AE99 Protocol Version 1-00 manual examples.
If any of these fail, the CRC, parser, or builder has a bug.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from simulator import crc as crc_engine
from simulator.telegram import (
    parse_master, parse_slave, build_slave_reply,
    build_master_type_c, build_master_type_ab,
    TelegramKind, TypeCCmd, MASTER_START, SLAVE_START
)
from simulator.protocol import ProtocolHandler, DeviceState


# ─────────────────────────────────────────────────────────────────────────────
# CRC Tests — verified against the manual's 256-entry lookup table
# ─────────────────────────────────────────────────────────────────────────────

class TestCRC:

    def test_table_spot_checks(self):
        """
        The manual provides a full 256-entry CRC table.
        Spot-check key entries: CRC_TABLE[0]=0x00, CRC_TABLE[1]=0x8D
        """
        assert crc_engine.CRC_TABLE[0]   == 0x00
        assert crc_engine.CRC_TABLE[1]   == 0x8D
        assert crc_engine.CRC_TABLE[2]   == 0x97
        assert crc_engine.CRC_TABLE[3]   == 0x1A
        assert crc_engine.CRC_TABLE[255] == 0xEB

    def test_crc_type_c_version_info(self):
        """
        Manual example — Version info master telegram:
        5131 0000 E2
        """
        data = bytes.fromhex("513100 00")
        assert crc_engine.calculate(data) == 0xE2

    def test_crc_type_c_reset_flag(self):
        """
        Manual example — Reset Flag:
        5131 0001 6F
        """
        data = bytes.fromhex("51310001")
        assert crc_engine.calculate(data) == 0x6F

    def test_crc_type_c_dip_switch(self):
        """
        Manual example — DIP Switch Settings:
        5131 0002 75
        """
        data = bytes.fromhex("51310002")
        assert crc_engine.calculate(data) == 0x75

    def test_crc_type_c_reset_outputs(self):
        """
        Manual example — Reset Outputs:
        5131 0003 F8
        """
        data = bytes.fromhex("51310003")
        assert crc_engine.calculate(data) == 0xF8

    def test_crc_type_c_status_flags(self):
        """
        Manual example — Status Flags:
        5131 0006 D6
        """
        data = bytes.fromhex("51310006")
        assert crc_engine.calculate(data) == 0xD6

    def test_crc_type_ab_analog_power_off(self):
        """
        Manual example — Analog Power Outputs OFF:
        5131 8000 0F00 0000 42
        """
        data = bytes.fromhex("5131800 00F000000".replace(" ", ""))
        assert crc_engine.calculate(data) == 0x42

    def test_crc_type_ab_analog_power_on(self):
        """
        Manual example — Analog Power Outputs ON:
        5131 8000 0FFF FFFF 97
        """
        data = bytes.fromhex("51318000 0FFFFFFF".replace(" ", ""))
        assert crc_engine.calculate(data) == 0x97

    def test_verify_valid(self):
        """verify() should return True for a valid telegram."""
        telegram = bytes.fromhex("5131000042")  # last byte is CRC — actually recalculate
        # Build a valid one
        payload = bytes([0x51, 0x31, 0x00, 0x00])
        valid = crc_engine.append(payload)
        assert crc_engine.verify(valid) is True

    def test_verify_corrupted(self):
        """verify() should return False when a byte is flipped."""
        payload = bytes([0x51, 0x31, 0x00, 0x00])
        valid = crc_engine.append(payload)
        corrupted = bytearray(valid)
        corrupted[2] ^= 0xFF   # flip byte 3
        assert crc_engine.verify(bytes(corrupted)) is False

    def test_append_roundtrip(self):
        """append() + verify() should always return True."""
        for data in [b"\x51\x31\x00\x00", b"\x51\x31\x80\x00\x0F\xFF\xFF\xFF"]:
            assert crc_engine.verify(crc_engine.append(data)) is True


# ─────────────────────────────────────────────────────────────────────────────
# Parser Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestParser:

    def test_parse_type_c_version_info(self):
        """Parse the version info master telegram from the manual."""
        raw = bytes.fromhex("513100 00E2".replace(" ", ""))
        t = parse_master(raw)
        assert t.kind == TelegramKind.C
        assert t.device_type == 0x3
        assert t.node_address == 0x1
        assert t.type_c_cmd == TypeCCmd.VERSION_INFO
        assert t.crc_valid is True

    def test_parse_type_c_reset_flag(self):
        raw = bytes.fromhex("5131000 16F".replace(" ", ""))
        t = parse_master(raw)
        assert t.kind == TelegramKind.C
        assert t.type_c_cmd == TypeCCmd.RESET_FLAG
        assert t.crc_valid is True

    def test_parse_type_c_status_flags(self):
        raw = bytes.fromhex("513100 06D6".replace(" ", ""))
        t = parse_master(raw)
        assert t.kind == TelegramKind.C
        assert t.type_c_cmd == TypeCCmd.STATUS_FLAGS
        assert t.crc_valid is True

    def test_parse_type_ab_analog_power_off(self):
        """
        Manual example: 5131 8000 0F00 0000 42
        Type AB, analog power outputs disabled.
        """
        raw = bytes.fromhex("5131 8000 0F00 0000 42".replace(" ", ""))
        t = parse_master(raw)
        assert t.kind == TelegramKind.AB
        assert t.device_type == 0x3
        assert t.node_address == 0x1
        assert t.crc_valid is True
        # type_a = 0x80 — bit 7 set (AB), no banks enabled
        assert t.pwm_bank1_enabled is False
        assert t.pwm_bank2_enabled is False
        assert t.ain_bank0_enabled is False

    def test_parse_type_ab_pwm_banks_enabled_8bit(self):
        """
        Manual example: 5131 8E00 0F... (PWM Banks 1+2+3 enabled, 8-bit)
        type_a = 0x8E = 1000_1110 → PWM bank1, bank2, bank3 enabled; 8-bit (bit0=0)
        """
        raw_hex = "51318E000F000000" + "00" * 24 + "4E"
        raw = bytes.fromhex(raw_hex)
        t = parse_master(raw)
        assert t.kind == TelegramKind.AB
        assert t.crc_valid is True
        assert t.pwm_bank1_enabled is True
        assert t.pwm_bank2_enabled is True
        assert t.pwm_bank3_enabled is True
        assert t.pwm_8_16bit is False  # 8-bit mode

    def test_parse_invalid_start_byte(self):
        from simulator.telegram import ParseError
        with pytest.raises(ParseError):
            parse_master(bytes([0x00, 0x31, 0x00, 0x00, 0x00]))

    def test_parse_too_short(self):
        from simulator.telegram import ParseError
        with pytest.raises(ParseError):
            parse_master(bytes([0x51, 0x31]))

    def test_parse_slave_reply(self):
        """
        Manual example slave reply to AB telegram: 5230 AF
        """
        raw = bytes.fromhex("5230AF")
        r = parse_slave(raw)
        assert r.crc_valid is True
        assert r.payload == bytes([0x30])

    def test_parse_slave_version_reply(self):
        """
        Manual example: 5202 0305 0411 0043
        Version 02.03, Day 05, Month 04, Year 17 (2017)
        """
        raw = bytes.fromhex("52020305041100 43".replace(" ", ""))
        r = parse_slave(raw)
        assert r.crc_valid is True
        assert r.payload[0] == 0x02   # firmware version
        assert r.payload[1] == 0x03   # sub version


# ─────────────────────────────────────────────────────────────────────────────
# Builder Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBuilder:

    def test_build_type_c_version_info(self):
        """Built telegram must match manual example: 5131 0000 E2"""
        result = build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO)
        assert result == bytes.fromhex("51310000E2")

    def test_build_type_c_reset_flag(self):
        """Must match: 5131 0001 6F"""
        result = build_master_type_c(node_address=0x1, cmd=TypeCCmd.RESET_FLAG)
        assert result == bytes.fromhex("5131000 16F".replace(" ", ""))

    def test_build_type_c_reset_outputs(self):
        """Must match: 5131 0003 F8"""
        result = build_master_type_c(node_address=0x1, cmd=TypeCCmd.RESET_OUTPUTS)
        assert result == bytes.fromhex("513100 03F8".replace(" ", ""))

    def test_build_type_c_status_flags(self):
        """Must match: 5131 0006 D6"""
        result = build_master_type_c(node_address=0x1, cmd=TypeCCmd.STATUS_FLAGS)
        assert result == bytes.fromhex("513100 06D6".replace(" ", ""))

    def test_build_type_c_reply_delay_default(self):
        """Must match: 5131 0009 14F5  (reply delay = 20 = 0x14)"""
        result = build_master_type_c(
            node_address=0x1,
            cmd=TypeCCmd.REPLY_DELAY,
            data=bytes([0x14])
        )
        assert result == bytes.fromhex("51310009 14F5".replace(" ", ""))

    def test_build_type_ab_analog_power_off(self):
        """Must match: 5131 8000 0F00 0000 42"""
        result = build_master_type_ab(
            node_address=0x1,
            type_a=0x80,
            type_b=0x00,
            pwm_freq=0x0F,
            analog_power_outputs=bytes([0x00, 0x00, 0x00])
        )
        assert result == bytes.fromhex("5131 8000 0F00 0000 42".replace(" ", ""))

    def test_build_type_ab_analog_power_on(self):
        """Must match: 5131 8000 0FFF FFFF 97"""
        result = build_master_type_ab(
            node_address=0x1,
            type_a=0x80,
            type_b=0x00,
            pwm_freq=0x0F,
            analog_power_outputs=bytes([0xFF, 0xFF, 0xFF])
        )
        assert result == bytes.fromhex("5131 8000 0FFF FFFF 97".replace(" ", ""))

    def test_build_slave_reply_ack(self):
        """ACK reply: 52 06 B6"""
        result = build_slave_reply(bytes([0x06]))
        assert result == bytes.fromhex("5206B6")

    def test_built_telegrams_always_have_valid_crc(self):
        """Any built telegram must pass CRC verify."""
        telegrams = [
            build_master_type_c(0x1, TypeCCmd.VERSION_INFO),
            build_master_type_c(0x1, TypeCCmd.STATUS_FLAGS),
            build_master_type_ab(0x1, 0x80, 0x00, 0x0F, b"\xFF\xFF\xFF"),
            build_slave_reply(bytes([0x06])),
        ]
        for t in telegrams:
            assert crc_engine.verify(t), f"CRC failed for: {t.hex()}"


# ─────────────────────────────────────────────────────────────────────────────
# Protocol Handler Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProtocolHandler:

    def _make_handler(self, **kwargs) -> ProtocolHandler:
        state = DeviceState(node_address=0x1, **kwargs)
        return ProtocolHandler(state)

    def _send(self, handler, raw_hex: str) -> bytes | None:
        t = parse_master(bytes.fromhex(raw_hex.replace(" ", "")))
        return handler.handle(t)

    def test_version_info_response(self):
        """Type C version info → 52 | fw_ver | sub | day | month | year | rst | CRC"""
        h = self._make_handler(fw_version=2, fw_sub_version=3, reset_flag=True)
        reply = self._send(h, "5131 0000 E2")
        assert reply is not None
        r = parse_slave(reply)
        assert r.crc_valid
        assert r.payload[0] == 0x02   # fw version
        assert r.payload[1] == 0x03   # sub version
        assert r.payload[5] == 0x01   # reset flag set

    def test_reset_flag_clears(self):
        """After Type C reset flag command, reset_flag should be False."""
        h = self._make_handler(reset_flag=True)
        reply = self._send(h, "5131 0001 6F")
        assert reply is not None
        r = parse_slave(reply)
        assert r.crc_valid
        assert r.payload[0] == 0x06   # ACK
        assert h.state.reset_flag is False

    def test_reset_outputs_acks(self):
        h = self._make_handler(pwm_bank1_overload=True)
        reply = self._send(h, "5131 0003 F8")
        r = parse_slave(reply)
        assert r.payload[0] == 0x06
        assert h.state.pwm_bank1_overload is False

    def test_status_flags_response_structure(self):
        """
        Status flags reply structure:
          1 start + 9 PWM/APW bytes + 2 temp + 2 volt + 1 CRC = 15 bytes
        """
        h = self._make_handler()
        reply = self._send(h, "5131 0006 D6")
        assert reply is not None
        assert len(reply) == 15

    def test_type_ab_minimal_reply(self):
        """
        Minimal AB with no optional banks: 5131 8000 0F00 0000 42
        Reply should be: 52 | global_status | CRC = 3 bytes
        """
        h = self._make_handler()
        reply = self._send(h, "5131 8000 0F00 0000 42")
        assert reply is not None
        r = parse_slave(reply)
        assert r.crc_valid
        assert len(reply) == 3  # start + 1 status byte + CRC

    def test_address_mismatch_no_response(self):
        """Telegram addressed to node 0x2 should not get a response from node 0x1."""
        h = self._make_handler()
        # Build a valid telegram for node 0x2 — handler is on node 0x1
        raw = build_master_type_c(node_address=0x2, cmd=TypeCCmd.VERSION_INFO)
        t = parse_master(raw)
        result = h.handle(t)
        assert result is None

    def test_offline_device_no_response(self):
        """Offline device should never respond."""
        h = self._make_handler(online=False)
        reply = self._send(h, "5131 0000 E2")
        assert reply is None

    def test_invalid_crc_no_response(self):
        """Corrupted CRC should produce no response."""
        raw = bytearray(bytes.fromhex("51310000E2"))
        raw[-1] ^= 0xFF  # corrupt the CRC
        h = self._make_handler()
        t = parse_master(bytes(raw))
        result = h.handle(t)
        assert result is None

    def test_analog_input_setup_ack(self):
        """Analog input setup should ACK."""
        h = self._make_handler()
        raw = build_master_type_c(
            node_address=0x1,
            cmd=TypeCCmd.ANALOG_INPUT_SETUP,
            data=bytes([0xFF, 0xFF, 0xFF])
        )
        t = parse_master(raw)
        reply = h.handle(t)
        r = parse_slave(reply)
        assert r.payload[0] == 0x06  # ACK
        assert h.state.ain_mode == 0xFFFFFF

    def test_reply_delay_set(self):
        """Reply delay command stores the value."""
        h = self._make_handler()
        raw = build_master_type_c(
            node_address=0x1,
            cmd=TypeCCmd.REPLY_DELAY,
            data=bytes([0x32])  # 50 × 100µs = 5ms
        )
        t = parse_master(raw)
        h.handle(t)
        assert h.state.reply_delay_100us == 0x32

    def test_type_ab_with_ain_bank0(self):
        """
        AB telegram with AIN Bank 0 enabled — reply should include 8×2 = 16 extra bytes.
        total reply = 1 start + 1 status + 16 ain + 1 CRC = 19 bytes
        """
        h = self._make_handler()
        h.state.analog_inputs[0] = 0x1234
        h.state.analog_inputs[3] = 0xABCD

        # type_a = 0x80 | 0x10 (AIN bank 0) = 0x90
        raw = build_master_type_ab(
            node_address=0x1, type_a=0x90, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\x00\x00\x00"
        )
        t = parse_master(raw)
        reply = h.handle(t)
        r = parse_slave(reply)
        assert r.crc_valid
        assert len(reply) == 19   # 1+1+16+1

        # Check AIN 0 = 0x1234 (little-endian at bytes 1-2 of payload)
        import struct
        ain0 = struct.unpack_from("<H", r.payload, 1)[0]
        assert ain0 == 0x1234
