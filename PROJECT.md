# Kyst Simulator — Project Reference

> **Purpose of this file:** Complete project context for future AI-assisted development sessions.
> Read this file first before making any changes to the codebase.

---

## What Is This?

A Windows desktop GUI application that simulates a **Kyst AE99 Hydraulics Drivercard** — a subsea ROV valve driver card made by Kystdesign AS (Norway).

The simulator allows developers to test PLC software without needing physical Kyst hardware. The PC acts as either:
- **Slave Mode** — PC pretends to be a Kyst card, receiving commands from the PLC and sending back simulated responses
- **Master Mode** — PC pretends to be the PLC, sending commands to a real Kyst card and displaying responses

---

## Background & Context

### The Real Hardware

**Kyst AE99 Proportional Valve Driver & I/O Card**
- Designed for subsea ROV applications (pressure tolerant to 3000 MSW)
- 85 × 85 mm PCB, stackable for redundant operation
- Dual isolated comms: 2 × RS485/RS232
- Node address set by DIP switch on the card (SW1.1–4, nodes 0–15)
- Default baud rate configurable: 9600 / 38400 / 57600 / 115200 (SW1.6–7)
- Default: **57600 / 8-N-1**

**Card I/O:**
- 24 × PWM outputs (proportional valves, 8-bit or 16-bit resolution)
- 24 × Analog power outputs (APW 0–23, on/off enables)
- 21 × Analog inputs AIN 0–20 (0–10VDC or 0–20mA, configurable per channel)
- 3 × Digital inputs DIN 21–23
- 16 × Counter inputs CNT 0–15
- 12 × Encoder inputs ENC 0–11
- 24 × Digital input word DIG 0–23 (3 bytes)
- 4 × Temperature inputs TEMP 1–4 (PT100, degree C = (raw/100) − 100)

### The Protocol — D2-Bus

Custom serial protocol developed by Kystdesign. Master/slave architecture where:
- **PLC = Master** — sends commands
- **Kyst card = Slave** — responds

**Key parameters:**
- Default baud: 57,600 / 8-N-1
- RS-232 or RS-485
- Start byte master: `0x51` (ASCII 'Q')
- Start byte slave: `0x52` (ASCII 'R')
- CRC: 8-bit, polynomial `0x8D` (x⁸+x⁷+x³+x²+x¹)
- Endianness: 16-bit words are **little-endian** (LSB first)
- Device type nibble: `0x3` (fixed for AE99)
- Node address nibble: `0x0`–`0xF` → full address `0x30`–`0x3F`

**Two telegram types:**
1. **Type AB** — normal cyclic communication (PLC sets outputs, card returns inputs)
2. **Type C** — configuration commands (version, reset, status, analog setup, reply delay)

**Reference document:** `Manuals/AE99 Protocol Version 1-00.pdf`

### Connection Path (Production)

The Kyst card communicates via serial (RS-232/RS-485). In the target system, serial cards are being **replaced with Ixys IX-USM-1 Serial Server PCBs** which bridge serial to Ethernet/TCP. This means the PLC connects via TCP rather than a hardware serial card.

```
PLC (TSEND_C / TRCV_C)  ──TCP──►  IX-USM-1 Serial Server  ──RS232/RS485──►  Kyst Card
```

The simulator can connect either via TCP (for IX-USM-1 setup) or direct serial COM port.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| GUI | Python + CustomTkinter | Modern dark UI, no extra dependencies, ships with Python |
| Protocol engine | Pure Python | No dependencies, fully testable |
| TCP comms | Python `socket` stdlib | No dependencies |
| Serial comms | `pyserial` | Standard, well supported |
| Config | JSON (`settings.json`) | Human-readable, easy to edit |
| Tests | `pytest` | Industry standard |
| Build | PyInstaller | Single `.exe` for Windows distribution |
| IDE | VS Code | Easy to adjust, good Python support |

**Python version:** 3.10+
**Platform:** Windows 10/11 (primary), Linux (development/CI)

---

## Repository Structure

```
Kyst-Simulator/
│
├── main.py                         # Entry point
│
├── gui/
│   ├── __init__.py
│   └── main_window.py              # Full CustomTkinter GUI
│                                   # Slave/Master mode, tabbed slave panel,
│                                   # log viewer, connection panel
│
├── comms/
│   ├── __init__.py
│   ├── connection_manager.py       # Central controller — owns TCPServer or SerialServer
│                                   # Wires comms to protocol engine
│                                   # State machine: DISCONNECTED→LISTENING→CONNECTED
│   ├── tcp_server.py               # TCP server (slave mode) — listens for PLC connections
│   ├── tcp_client.py               # TCP client (master mode) — connects to real Kyst card
│   └── serial_server.py            # Serial COM port server, D2-Bus frame detection
│                                   # Configurable baud/parity/stop bits
│
├── simulator/
│   ├── __init__.py
│   ├── crc.py                      # 8-bit D2-Bus CRC engine (polynomial 0x8D)
│                                   # CRC_TABLE[256] generated algorithmically
│                                   # calculate(), verify(), append()
│   ├── telegram.py                 # Telegram parser and builder
│                                   # parse_master(), parse_slave()
│                                   # build_master_type_c(), build_master_type_ab()
│                                   # build_slave_reply()
│                                   # MasterTelegram, SlaveReply dataclasses
│                                   # TelegramKind, TypeCCmd enums
│   ├── protocol.py                 # Protocol handler (slave mode)
│                                   # DeviceState dataclass — all simulated values
│                                   # ProtocolHandler.handle() → reply bytes
│                                   # Handles all Type C commands + Type AB banks
│   └── decoder.py                  # Human-readable telegram decoder for log panel
│                                   # decode_master(), decode_slave()
│
├── config/
│   ├── settings.json               # User configuration (persisted on close)
│   └── config.py                   # Typed config loader/saver
│                                   # AppConfig, ConnectionConfig, DeviceConfig
│
├── tests/
│   ├── __init__.py
│   ├── test_protocol.py            # 40 tests: CRC, parser, builder, protocol handler
│   ├── test_connection.py          # 17 tests: TCP connection manager, config
│   ├── test_gui.py                 # 8 tests: GUI wiring (headless)
│   └── test_master_and_decoder.py  # 18 tests: TCP client, decoder
│
├── Manuals/
│   ├── AE99 Protocol Version 1-00.pdf          # KEY: D2-Bus protocol spec
│   ├── AE99-1000B01_01_Valve Drivercard.pdf    # Hardware pinouts and specs
│   ├── AE99-1100B02_02_Terminalcard.pdf        # Terminal card reference
│   ├── Kystdesign-Proportional-24-ch-Valve-Driver-IO-Card.pdf
│   ├── L99PD08 AMICO 8 Channel Pre Diagnosis Device.pdf
│   ├── L99PD08 General Presentation V1.20.pdf
│   ├── PWM Output 0-7 - Schematic.pdf
│   └── VNQ5160K-E Quad channel high side driver for automotive applications.pdf
│
├── docs/
│   ├── DESIGN.md                   # Architecture design document
│   └── SETUP.md                    # Installation and build instructions
│
├── requirements.txt                # customtkinter, pyserial
├── build.bat                       # Windows build script → dist/KystSimulator.exe
├── run_tests.bat                   # One-click test runner for Windows
└── PROJECT.md                      # This file
```

---

## Protocol Reference

### Master Telegram Structure (PLC → Card)

```
Byte 1: 0x51       Start character ('Q')
Byte 2: 0x3N       Device address (TYPE=3, NODE=0-F → 0x30-0x3F)
Byte 3: Type A     Bit flags (bit7=1 for AB, bit7=0 for C)
Byte 4: Type B     Bit flags (AB) or CMD byte (C)
Byte 5+: Data      Type-dependent
Last:   CRC        8-bit D2-Bus CRC
```

### Type A Byte (AB telegrams)

| Bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
|-----|---|---|---|---|---|---|---|---|
| | TRUE (AB marker) | AIN Bank2 | AIN Bank1 | AIN Bank0 | PWM Bank3 | PWM Bank2 | PWM Bank1 | PWM 8/16bit |

### Type B Byte (AB telegrams)

| Bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
|-----|---|---|---|---|---|---|---|---|
| | TEMP 3-4 | TEMP 1-2 | DIG 25% | ENC Bank3 | ENC Bank2 | ENC Bank1 | CNT Bank2 | CNT Bank1 |

### Slave Reply Structure (Card → PLC)

```
Byte 1: 0x52       Start character ('R')
Byte 2: Status     Global status byte (AB) or reply data (C)
...     Data       Optional banks in order
Last:   CRC        8-bit D2-Bus CRC
```

### Global Status Byte

| Bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
|-----|---|---|---|---|---|---|---|---|
| | Reset Flag | Spare | Leak 2 | Leak 1 | APW OVL | PWM Bank3 OVL | PWM Bank2 OVL | PWM Bank1 OVL |

Note: Leak 1 = inversed value of DIN 23. Leak 2 = inversed value of DIN 22.

### Slave AB Reply — Optional Data Order

```
[Status byte]
[AIN Bank 0]  — AIN 0–7   (8 × 16-bit LE words) if AIN Bank0 enabled
[AIN Bank 1]  — AIN 8–15  (8 × 16-bit LE words) if AIN Bank1 enabled
[AIN Bank 2]  — AIN 16–20 (5 × 16-bit) + DIN 21–23 (3 × 16-bit) if AIN Bank2 enabled
[CNT Bank 1]  — CNT 0–7   (8 × 16-bit LE words) if CNT Bank1 enabled
[CNT Bank 2]  — CNT 8–15  (8 × 16-bit LE words) if CNT Bank2 enabled
[ENC Bank 1]  — ENC 0–3   (4 × 16-bit LE words) if ENC Bank1 enabled
[ENC Bank 2]  — ENC 4–7   (4 × 16-bit LE words) if ENC Bank2 enabled
[ENC Bank 3]  — ENC 8–11  (4 × 16-bit LE words) if ENC Bank3 enabled
[DIG]         — DIG 0–23  (3 bytes, 1 bit per channel) if DIG enabled
[TEMP 1-2]    — TEMP 1+2  (2 × 16-bit LE words) if TEMP 1-2 enabled
[TEMP 3-4]    — TEMP 3+4  (2 × 16-bit LE words) if TEMP 3-4 enabled
[CRC]
```

### Type C Commands

| CMD | Hex | Master data | Slave reply |
|-----|-----|-------------|-------------|
| Version Info | 0x00 | none | FW_VER, SUB_VER, DAY, MONTH, YEAR, RST |
| Reset Flag | 0x01 | none | ACK (0x06) — clears reset flag |
| DIP Switch | 0x02 | none | OPTION\|NODE byte |
| Reset Outputs | 0x03 | none | ACK (0x06) — clears all overloads |
| Status Flags | 0x06 | none | PWM driver status (9 bytes) + temp + volt |
| Analog Input Setup | 0x08 | 3 bytes (1 bit per AIN, 0=voltage, 1=current) | ACK |
| Reply Delay | 0x09 | 1 byte (× 100µs, default=20=2ms) | ACK |

### Manual Examples (verified against code)

```
Version Info:  Master 51 31 00 00 E2  →  Slave 52 02 03 05 04 11 00 43
Reset Flag:    Master 51 31 00 01 6F  →  Slave 52 06 B6
DIP Switch:    Master 51 31 00 02 75  →  Slave 52 41 63
Reset Outputs: Master 51 31 00 03 F8  →  Slave 52 06 B6
Status Flags:  Master 51 31 00 06 D6  →  Slave 52 20 00 20 00 20 00 00 00 00 2F 35 EF 01 30
AB APW OFF:    Master 51 31 80 00 0F 00 00 00 42  →  Slave 52 30 AF
AB APW ON:     Master 51 31 80 00 0F FF FF FF 97  →  Slave 52 30 AF
```

---

## DeviceState — Simulated Values

All values in `simulator/protocol.py → DeviceState`:

```python
node_address: int         # 0–15, matches DIP switch on card
online: bool              # False = no response at all
reset_flag: bool          # Set after power-on, cleared by Type C 0x01
leak_1: bool              # Water leak detect 1 (DIN 23 inverted)
leak_2: bool              # Water leak detect 2 (DIN 22 inverted)
analog_power_overload: bool
pwm_bank1_overload: bool
pwm_bank2_overload: bool
pwm_bank3_overload: bool
analog_inputs: list[int]  # AIN 0–20, 16-bit (0=0V/0mA, 65535=10V/20mA)
digital_inputs: list[bool] # DIN 21–23
counter_inputs: list[int] # CNT 0–15, 16-bit
encoder_inputs: list[int] # ENC 0–11, 16-bit
digital_word: list[int]   # DIG 0–23 as 3 bytes (1 bit per channel)
temperature_inputs: list[int] # TEMP 1–4, raw = (°C + 100) × 100
board_temp_raw: int       # Board temp in status reply
board_voltage_raw: int    # Board voltage in status reply
reply_delay_100us: int    # Delay before responding (default 20 = 2ms)
ain_mode: int             # 24-bit mask: 0=voltage, 1=current per channel
```

---

## GUI Layout

```
┌─────────────────────────────────────────────────────────┐
│  Kyst Card Simulator          [Mode: Slave/Master ▼] ●  │
├──────────────┬──────────────────────────────────────────┤
│ Connection   │                                          │
│  Transport ▼ │  Command / Response Log                  │
│  Host / Port │  [RX blue] [TX green] [Info amber]       │
│  [Connect]   │  [Error red] [Decoded purple]            │
│  [Disconnect]│                                          │
├──────────────┤  RX: 0  TX: 0  CRC Err: 0               │
│ Slave Panel  │  [Clear] [Save Log] [☐ Decoded]          │
│ ┌──────────┐ │                                          │
│ │ Status   │ │                                          │
│ │ Analog In│ │                                          │
│ │Digital/Cn│ │                                          │
│ │Temp/Hlth │ │                                          │
│ └──────────┘ │                                          │
└──────────────┴──────────────────────────────────────────┘
```

**Slave panel tabs:**
- **Status** — Node address (0–F), online/fault toggles, reply delay
- **Analog In** — AIN 0–20 sliders (0–65535)
- **Digital/Cnt** — DIN 21–23 toggles, CNT 0–15, ENC 0–11, DIG hex bytes
- **Temp/Health** — TEMP 1–4 in °C, board temperature, board voltage

---

## Test Suite

**83 tests, all passing.** Run with `python -m pytest tests/ -v` or `run_tests.bat`.

| File | Tests | Covers |
|------|-------|--------|
| `test_protocol.py` | 40 | CRC engine, telegram parser, telegram builder, protocol handler |
| `test_connection.py` | 17 | TCP connection manager lifecycle, config load/save |
| `test_gui.py` | 8 | GUI wiring callbacks (headless) |
| `test_master_and_decoder.py` | 18 | TCP client, decoder output |

All CRC values and telegram examples verified against the AE99 Protocol Version 1-00 manual.

---

## Current Status

**Version:** 0.4
**State:** Complete, protocol-verified, ready for hardware testing

### What works
- Full D2-Bus protocol engine (CRC, parser, builder, handler)
- TCP server mode — listens for PLC connections, responds to all telegram types
- Serial COM port mode — configurable baud rate, parity, stop bits
- All 21 analog inputs + all optional data banks (CNT, ENC, DIG, TEMP)
- All Type C commands (version, reset, status, DIP switch, analog setup, reply delay)
- Fault simulation (leaks, overloads, reset flag)
- Master mode command panel (Type C + Type AB buttons)
- Human-readable log decoder
- Config persists between sessions
- `build.bat` → single `.exe` via PyInstaller

### Awaiting hardware test
- Serial port framing edge cases (real card behaviour on RS-232/RS-485)
- Reply timing at high baud rates
- Any protocol edge cases not covered by the manual examples

---

## Key People & Context

- **Mathew Smith** — Automation engineer, project owner
- **Workplace** — Industrial/marine automation, Siemens PLC systems
- **Existing system** — Siemens PLCs with serial cards communicating to Kyst cards
- **Migration goal** — Replace Siemens serial cards with Ixys IX-USM-1 Serial Servers
- **PLC language** — Siemens SCL, using TSEND_C / TRCV_C blocks for TCP communication
- **IX-USM-1 guide** — See Research Notion page for full Siemens SCL migration guide

---

## Related Projects in Workspace

- **CSV_grapher** — Web app (Express.js + React + SQLite) for data visualisation
- **IHC_LLM** — Air-gapped LLM for Royal IHC document querying (Docker + Ollama)

---

## Quick Start

```bash
# Clone
git clone https://github.com/MatSmith95/Kyst-Simulator.git
cd Kyst-Simulator

# Install
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Run
python main.py

# Test
python -m pytest tests/ -v    # or run_tests.bat on Windows

# Build .exe
build.bat
```

---

*Last updated: 1 April 2026*
