"""
GUI Integration Tests (headless)

Tests that the GUI wiring is correct without rendering a visible window.
We instantiate the ConnectionManager and DeviceState directly and verify
that the GUI callbacks and state bindings behave correctly.
"""

import pytest
import sys, os, time, socket, threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from comms.connection_manager import ConnectionManager, ConnectionState
from simulator.protocol import DeviceState
from simulator.telegram import build_master_type_c, TypeCCmd, parse_slave
from config import config as cfg_module


class TestGUIWiring:
    """
    Tests the ConnectionManager callbacks that the GUI relies on.
    These exercise the same code paths the GUI uses without needing Tk.
    """
    BASE_PORT = 15001

    def setup_method(self):
        self.logs = []
        self.states = []
        self.device = DeviceState(node_address=1)
        self.port = TestGUIWiring.BASE_PORT
        TestGUIWiring.BASE_PORT += 1

        self.mgr = ConnectionManager(
            device_state=self.device,
            on_log=lambda msg, tag: self.logs.append((msg, tag)),
            on_state_change=lambda s: self.states.append(s),
        )

    def teardown_method(self):
        self.mgr.stop()
        time.sleep(0.1)

    def test_on_log_fires_with_info_tag_on_start(self):
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.1)
        tags = [t for _, t in self.logs]
        assert "info" in tags

    def test_on_state_change_fires_listening(self):
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.1)
        assert ConnectionState.LISTENING in self.states

    def test_on_state_change_fires_connected_on_client(self):
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.1)
        s = socket.socket()
        s.connect(("127.0.0.1", self.port))
        time.sleep(0.1)
        assert ConnectionState.CONNECTED in self.states
        s.close()

    def test_on_state_change_fires_disconnected_on_stop(self):
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.1)
        self.mgr.stop()
        time.sleep(0.1)
        assert ConnectionState.DISCONNECTED in self.states

    def test_device_state_online_toggle_affects_responses(self):
        """Toggling device online/offline should start/stop responses."""
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO)

        # Online — should respond
        with socket.socket() as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", self.port))
            s.sendall(telegram)
            resp = s.recv(256)
        assert len(resp) > 0

        # Go offline
        self.device.online = False

        with socket.socket() as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", self.port))
            s.sendall(telegram)
            with pytest.raises((socket.timeout, ConnectionResetError)):
                s.recv(256)

    def test_ain_value_change_reflected_in_response(self):
        """Changing AIN value on device_state should appear in the next reply."""
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.05)

        import struct
        self.device.analog_inputs[0] = 0x1234

        # type_a 0x90 = AB with AIN bank 0 enabled
        from simulator.telegram import build_master_type_ab
        telegram = build_master_type_ab(
            node_address=1, type_a=0x90, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\x00\x00\x00"
        )
        with socket.socket() as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", self.port))
            s.sendall(telegram)
            resp = s.recv(256)

        reply = parse_slave(resp)
        assert reply.crc_valid
        ain0 = struct.unpack_from("<H", reply.payload, 1)[0]
        assert ain0 == 0x1234

    def test_stats_increment_correctly(self):
        self.mgr.start_tcp(port=self.port)
        time.sleep(0.05)

        for _ in range(3):
            telegram = build_master_type_c(node_address=1, cmd=TypeCCmd.VERSION_INFO)
            with socket.socket() as s:
                s.settimeout(1.0)
                s.connect(("127.0.0.1", self.port))
                s.sendall(telegram)
                s.recv(256)
        time.sleep(0.1)

        assert self.mgr.rx_count == 3
        assert self.mgr.tx_count == 3

    def test_config_save_reload_roundtrip(self, tmp_path, monkeypatch):
        """Config save/load should preserve all key fields."""
        path = str(tmp_path / "settings.json")
        monkeypatch.setattr(cfg_module, "_CONFIG_PATH", path)

        cfg = cfg_module.load()
        cfg.connection.tcp.port = 7777
        cfg.device.node_address = 9
        cfg.device.reply_delay_100us = 50
        cfg_module.save(cfg)

        cfg2 = cfg_module.load()
        assert cfg2.connection.tcp.port == 7777
        assert cfg2.device.node_address == 9
        assert cfg2.device.reply_delay_100us == 50
