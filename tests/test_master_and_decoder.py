"""
Phase 5 & 6 Tests — Master TCP Client + Decoder

Tests the TCP client against a real in-process server (loopback),
and the decoder against known telegram bytes.
"""

import pytest
import socket
import time
import threading
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from comms.tcp_client import TCPClient
from comms.tcp_server import TCPServer
from comms.connection_manager import ConnectionManager, ConnectionState
from simulator.protocol import DeviceState, ProtocolHandler
from simulator.telegram import (
    build_master_type_c, build_master_type_ab,
    TypeCCmd, parse_master, parse_slave
)
from simulator.decoder import decode_master, decode_slave
from simulator import crc as crc_engine


# ── TCP Client Tests ───────────────────────────────────────────────────────────

class TestTCPClient:
    BASE_PORT = 16001

    def setup_method(self):
        self.port = TestTCPClient.BASE_PORT
        TestTCPClient.BASE_PORT += 1

        self.device = DeviceState(node_address=1)
        self.logs = []
        self.mgr = ConnectionManager(
            device_state=self.device,
            on_log=lambda m, t: self.logs.append((m, t)),
        )
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.05)

        self.client = TCPClient(
            host="127.0.0.1",
            port=self.port,
            on_log=lambda m, t: self.logs.append((m, t)),
        )
        self.client.connect()

    def teardown_method(self):
        self.client.disconnect()
        self.mgr.stop()
        time.sleep(0.1)

    def test_client_connects(self):
        assert self.client.is_connected

    def test_send_version_info_gets_reply(self):
        telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO)
        response = self.client.send(telegram)
        assert response is not None
        reply = parse_slave(response)
        assert reply.crc_valid
        assert response[0] == 0x52

    def test_send_reset_flag_acks(self):
        telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.RESET_FLAG)
        response = self.client.send(telegram)
        reply = parse_slave(response)
        assert reply.payload[0] == 0x06

    def test_send_status_flags(self):
        telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.STATUS_FLAGS)
        response = self.client.send(telegram)
        reply = parse_slave(response)
        assert reply.crc_valid
        assert len(response) == 15

    def test_send_type_ab_minimal(self):
        telegram = build_master_type_ab(
            node_address=1, type_a=0x80, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\x00\x00\x00"
        )
        response = self.client.send(telegram)
        reply = parse_slave(response)
        assert reply.crc_valid

    def test_send_wrong_address_no_response(self):
        telegram = build_master_type_c(node_address=2, cmd=TypeCCmd.VERSION_INFO)
        self.client._sock.settimeout(0.3)
        response = self.client.send(telegram)
        assert response is None

    def test_disconnect_sets_not_connected(self):
        self.client.disconnect()
        assert not self.client.is_connected

    def test_send_while_disconnected_logs_error(self):
        self.client.disconnect()
        telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO)
        response = self.client.send(telegram)
        assert response is None
        err_logs = [m for m, t in self.logs if t == "err"]
        assert len(err_logs) > 0

    def test_multiple_sequential_sends(self):
        """Send several commands in sequence — all should get valid replies."""
        cmds = [
            TypeCCmd.VERSION_INFO,
            TypeCCmd.STATUS_FLAGS,
            TypeCCmd.DIP_SWITCH,
            TypeCCmd.RESET_OUTPUTS,
        ]
        for cmd in cmds:
            telegram = build_master_type_c(node_address=1, cmd=cmd)
            response = self.client.send(telegram)
            assert response is not None, f"No response for {cmd}"
            reply = parse_slave(response)
            assert reply.crc_valid, f"Bad CRC for {cmd}"


# ── Decoder Tests ──────────────────────────────────────────────────────────────

class TestDecoder:

    def test_decode_master_type_c_version_info(self):
        raw = build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO)
        t = parse_master(raw)
        result = decode_master(t)
        assert "0x31" in result or "node=1" in result
        assert "VERSION_INFO" in result
        assert "✓" in result   # CRC valid

    def test_decode_master_type_c_bad_crc(self):
        raw = bytearray(build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO))
        raw[-1] ^= 0xFF
        t = parse_master(bytes(raw))
        result = decode_master(t)
        assert "✗" in result or "BAD" in result

    def test_decode_master_type_ab_banks(self):
        # type_a = 0x8E = AB + PWM banks 1,2,3 enabled
        raw = build_master_type_ab(
            node_address=1, type_a=0x8E, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\x00\x00\x00"
        )
        t = parse_master(raw)
        result = decode_master(t)
        assert "PWM1" in result
        assert "PWM2" in result
        assert "PWM3" in result

    def test_decode_slave_ack(self):
        raw = build_master_type_c(node_address=1, cmd=TypeCCmd.RESET_FLAG)
        # Build a handler and get the real response
        handler = ProtocolHandler(DeviceState(node_address=1))
        t = parse_master(raw)
        reply_bytes = handler.handle(t)
        result = decode_slave(reply_bytes, cmd_context=TypeCCmd.RESET_FLAG)
        assert "ACK" in result

    def test_decode_slave_version_info(self):
        handler = ProtocolHandler(DeviceState(node_address=1, fw_version=2, fw_sub_version=3))
        t = parse_master(build_master_type_c(1, TypeCCmd.VERSION_INFO))
        reply_bytes = handler.handle(t)
        result = decode_slave(reply_bytes, cmd_context=TypeCCmd.VERSION_INFO)
        assert "v2.3" in result

    def test_decode_slave_status_flags(self):
        handler = ProtocolHandler(DeviceState(node_address=1, board_temp_raw=13615, board_voltage_raw=495))
        t = parse_master(build_master_type_c(1, TypeCCmd.STATUS_FLAGS))
        reply_bytes = handler.handle(t)
        result = decode_slave(reply_bytes, cmd_context=TypeCCmd.STATUS_FLAGS)
        assert "temp=" in result
        assert "voltage=" in result

    def test_decode_slave_ab_reply_ok_status(self):
        handler = ProtocolHandler(DeviceState(node_address=1))
        t = parse_master(build_master_type_ab(
            1, 0x80, 0x00, 0x0F, b"\x00\x00\x00"
        ))
        reply_bytes = handler.handle(t)
        result = decode_slave(reply_bytes)
        assert "OK" in result or "0x" in result

    def test_decode_slave_ab_reply_with_fault_flags(self):
        state = DeviceState(node_address=1, pwm_bank1_overload=True, leak_1=True)
        handler = ProtocolHandler(state)
        t = parse_master(build_master_type_ab(1, 0x80, 0x00, 0x0F, b"\x00\x00\x00"))
        reply_bytes = handler.handle(t)
        result = decode_slave(reply_bytes)
        assert "PWM1_OVL" in result or "LEAK1" in result

    def test_decode_slave_bad_crc(self):
        raw = bytearray(b"\x52\x06\xB6")
        raw[-1] ^= 0xFF
        result = decode_slave(bytes(raw))
        assert "BAD" in result or "✗" in result
