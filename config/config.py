"""
Kyst Simulator — Configuration Loader

Loads settings.json from the config directory.
Provides typed access to connection and device settings.
Falls back to safe defaults if the file is missing or malformed.
"""

from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "settings.json")


@dataclass
class TCPConfig:
    host: str = "0.0.0.0"
    port: int = 4001


@dataclass
class SerialConfig:
    port: str       = "COM1"
    baud_rate: int  = 57600
    data_bits: int  = 8
    parity: str     = "N"
    stop_bits: float = 1.0
    read_timeout: float = 1.0


@dataclass
class ConnectionConfig:
    mode: str           = "TCP"
    tcp: TCPConfig      = field(default_factory=TCPConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)


@dataclass
class DeviceConfig:
    node_address: int       = 1
    online: bool            = True
    reset_flag: bool        = True
    simulate_fault: bool    = False
    auto_respond: bool      = True
    reply_delay_100us: int  = 20
    board_temp_raw: int     = 13615
    board_voltage_raw: int  = 2400


@dataclass
class AppConfig:
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    device: DeviceConfig         = field(default_factory=DeviceConfig)
    log_level: str               = "INFO"


def load() -> AppConfig:
    """Load and return the application configuration."""
    try:
        with open(_CONFIG_PATH, "r") as f:
            raw = json.load(f)
        return _parse(raw)
    except FileNotFoundError:
        logger.warning(f"Config file not found at {_CONFIG_PATH} — using defaults")
        return AppConfig()
    except json.JSONDecodeError as e:
        logger.error(f"Config file parse error: {e} — using defaults")
        return AppConfig()


def save(cfg: AppConfig) -> None:
    """Save the current configuration back to settings.json."""
    raw = {
        "connection": {
            "mode": cfg.connection.mode,
            "tcp": {
                "host": cfg.connection.tcp.host,
                "port": cfg.connection.tcp.port,
            },
            "serial": {
                "port": cfg.connection.serial.port,
                "baud_rate": cfg.connection.serial.baud_rate,
                "data_bits": cfg.connection.serial.data_bits,
                "parity": cfg.connection.serial.parity,
                "stop_bits": cfg.connection.serial.stop_bits,
                "read_timeout": cfg.connection.serial.read_timeout,
            }
        },
        "device": {
            "node_address": cfg.device.node_address,
            "online": cfg.device.online,
            "reset_flag": cfg.device.reset_flag,
            "simulate_fault": cfg.device.simulate_fault,
            "auto_respond": cfg.device.auto_respond,
            "reply_delay_100us": cfg.device.reply_delay_100us,
            "board_temp_raw": cfg.device.board_temp_raw,
            "board_voltage_raw": cfg.device.board_voltage_raw,
        },
        "logging": {
            "level": cfg.log_level,
        }
    }
    try:
        with open(_CONFIG_PATH, "w") as f:
            json.dump(raw, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def _parse(raw: dict) -> AppConfig:
    conn_raw   = raw.get("connection", {})
    tcp_raw    = conn_raw.get("tcp", {})
    serial_raw = conn_raw.get("serial", {})
    dev_raw    = raw.get("device", {})
    log_raw    = raw.get("logging", {})

    return AppConfig(
        connection=ConnectionConfig(
            mode=conn_raw.get("mode", "TCP"),
            tcp=TCPConfig(
                host=tcp_raw.get("host", "0.0.0.0"),
                port=int(tcp_raw.get("port", 4001)),
            ),
            serial=SerialConfig(
                port=serial_raw.get("port", "COM1"),
                baud_rate=int(serial_raw.get("baud_rate", 57600)),
                data_bits=int(serial_raw.get("data_bits", 8)),
                parity=serial_raw.get("parity", "N"),
                stop_bits=float(serial_raw.get("stop_bits", 1.0)),
                read_timeout=float(serial_raw.get("read_timeout", 1.0)),
            )
        ),
        device=DeviceConfig(
            node_address=int(dev_raw.get("node_address", 1)),
            online=bool(dev_raw.get("online", True)),
            reset_flag=bool(dev_raw.get("reset_flag", True)),
            simulate_fault=bool(dev_raw.get("simulate_fault", False)),
            auto_respond=bool(dev_raw.get("auto_respond", True)),
            reply_delay_100us=int(dev_raw.get("reply_delay_100us", 20)),
            board_temp_raw=int(dev_raw.get("board_temp_raw", 13615)),
            board_voltage_raw=int(dev_raw.get("board_voltage_raw", 2400)),
        ),
        log_level=log_raw.get("level", "INFO"),
    )
