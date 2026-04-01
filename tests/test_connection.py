"""
Connection Layer Tests

Tests the ConnectionManager using a real TCP loopback socket.
No hardware required — client and server both run in-process.

Serial tests are skipped automatically if pyserial is not installed
or no COM ports are available.
"""

import pytest
import socket
import time
import threading
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from comms.connection_manager import ConnectionManager, ConnectionState
from simulator.protocol import DeviceState
from simulator.telegram import build_master_type_c, TypeCCmd, parse_slave
from simulator import crc as crc_engine


# ── Helpers ────────────────────────────────────────────────────────────────────

def _send_recv(host: str, port: int, data: bytes, timeout: float = 2.0) -> bytes:
    """Open a TCP connection, send data, receive response, close."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(data)
        return s.recv(1024)


def _wait_for_state(mgr: ConnectionManager, state: ConnectionState, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if mgr.state == state:
            return True
        time.sleep(0.05)
    return False


# ── TCP ConnectionManager Tests ────────────────────────────────────────────────

class TestTCPConnectionManager:
    _port_counter = 14001   # Each test gets its own port to avoid TIME_WAIT conflicts

    def setup_method(self):
        # Allocate a unique port for this test instance
        self.TEST_PORT = TestTCPConnectionManager._port_counter
        TestTCPConnectionManager._port_counter += 1

        self.logs: list[tuple[str, str]] = []
        self.state_changes: list[ConnectionState] = []

        self.device = DeviceState(node_address=0x1)
        self.mgr = ConnectionManager(
            device_state=self.device,
            on_log=lambda msg, tag: self.logs.append((msg, tag)),
            on_state_change=lambda s: self.state_changes.append(s),
        )

    def teardown_method(self):
        self.mgr.stop()
        time.sleep(0.15)

    def test_initial_state_disconnected(self):
        assert self.mgr.state == ConnectionState.DISCONNECTED

    def test_start_moves_to_listening(self):
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)

    def test_stop_moves_to_disconnected(self):
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        self.mgr.stop()
        assert self.mgr.state == ConnectionState.DISCONNECTED

    def test_client_connect_moves_to_connected(self):
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)

        # Connect a client
        s = socket.socket()
        s.connect(("127.0.0.1", self.TEST_PORT))
        time.sleep(0.1)
        assert self.mgr.state == ConnectionState.CONNECTED
        s.close()

    def test_client_disconnect_returns_to_listening(self):
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)

        s = socket.socket()
        s.connect(("127.0.0.1", self.TEST_PORT))
        time.sleep(0.1)
        s.close()
        time.sleep(0.2)
        assert self.mgr.state == ConnectionState.LISTENING

    def test_version_info_over_tcp(self):
        """Send a real D2-Bus Type C version info telegram over loopback."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO)
        response = _send_recv("127.0.0.1", self.TEST_PORT, telegram)

        assert len(response) > 0
        reply = parse_slave(response)
        assert reply.crc_valid
        assert response[0] == 0x52   # slave start byte 'R'

    def test_reset_flag_over_tcp(self):
        """Type C reset flag — device should ACK and clear the flag."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        assert self.device.reset_flag is True
        telegram = build_master_type_c(node_address=0x1, cmd=TypeCCmd.RESET_FLAG)
        response = _send_recv("127.0.0.1", self.TEST_PORT, telegram)

        reply = parse_slave(response)
        assert reply.crc_valid
        assert reply.payload[0] == 0x06   # ACK
        assert self.device.reset_flag is False

    def test_invalid_crc_no_response(self):
        """A telegram with a bad CRC should produce no response."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = bytearray(build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO))
        telegram[-1] ^= 0xFF   # corrupt CRC

        with socket.socket() as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", self.TEST_PORT))
            s.sendall(bytes(telegram))
            with pytest.raises((socket.timeout, ConnectionResetError)):
                s.recv(1024)

    def test_wrong_address_no_response(self):
        """Telegram for node 0x2 — simulator on node 0x1 should not respond."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=0x2, cmd=TypeCCmd.VERSION_INFO)
        with socket.socket() as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", self.TEST_PORT))
            s.sendall(telegram)
            with pytest.raises((socket.timeout, ConnectionResetError)):
                s.recv(1024)

    def test_rx_tx_counters_increment(self):
        """Stats counters should increment on each transaction."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO)
        _send_recv("127.0.0.1", self.TEST_PORT, telegram)
        time.sleep(0.1)

        assert self.mgr.rx_count >= 1
        assert self.mgr.tx_count >= 1

    def test_log_callbacks_fire(self):
        """Log callback should be called with rx/tx tags during a transaction."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO)
        _send_recv("127.0.0.1", self.TEST_PORT, telegram)
        time.sleep(0.1)

        tags = [tag for _, tag in self.logs]
        assert "rx" in tags
        assert "tx" in tags

    def test_double_start_logs_error(self):
        """Calling start_tcp twice should log an error, not crash."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        self.mgr.start_tcp(port=self.TEST_PORT)

        error_logs = [msg for msg, tag in self.logs if tag == "err"]
        assert len(error_logs) > 0

    def test_multiple_clients_all_receive_response(self):
        """Two simultaneous TCP clients both sending commands should both get responses."""
        self.mgr.start_tcp(port=self.TEST_PORT)
        assert _wait_for_state(self.mgr, ConnectionState.LISTENING)
        time.sleep(0.05)

        telegram = build_master_type_c(node_address=0x1, cmd=TypeCCmd.VERSION_INFO)
        results = []

        def client_task():
            resp = _send_recv("127.0.0.1", self.TEST_PORT, telegram)
            results.append(resp)

        threads = [threading.Thread(target=client_task) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=3.0)

        assert len(results) == 2
        for resp in results:
            reply = parse_slave(resp)
            assert reply.crc_valid


# ── Config Tests ───────────────────────────────────────────────────────────────

class TestConfig:
    def test_load_returns_defaults_when_file_missing(self, tmp_path, monkeypatch):
        import config.config as cfg_module
        monkeypatch.setattr(cfg_module, "_CONFIG_PATH", str(tmp_path / "missing.json"))
        cfg = cfg_module.load()
        assert cfg.connection.tcp.port == 4001
        assert cfg.connection.serial.baud_rate == 57600
        assert cfg.device.node_address == 1

    def test_load_parses_settings_json(self):
        import config.config as cfg_module
        cfg = cfg_module.load()
        assert isinstance(cfg.connection.tcp.port, int)
        assert isinstance(cfg.connection.serial.baud_rate, int)
        assert cfg.connection.serial.baud_rate == 57600

    def test_save_and_reload(self, tmp_path, monkeypatch):
        import config.config as cfg_module
        path = str(tmp_path / "test_settings.json")
        monkeypatch.setattr(cfg_module, "_CONFIG_PATH", path)

        cfg = cfg_module.load()
        cfg.connection.tcp.port = 9999
        cfg.connection.serial.baud_rate = 19200
        cfg.device.node_address = 5
        cfg_module.save(cfg)

        cfg2 = cfg_module.load()
        assert cfg2.connection.tcp.port == 9999
        assert cfg2.connection.serial.baud_rate == 19200
        assert cfg2.device.node_address == 5


# ── Serial port discovery test (skipped if no pyserial) ───────────────────────

class TestSerialPortDiscovery:
    def test_list_ports_returns_list(self):
        from comms.serial_server import SerialServer
        ports = SerialServer.list_ports()
        assert isinstance(ports, list)
        # May be empty on CI — that's fine
