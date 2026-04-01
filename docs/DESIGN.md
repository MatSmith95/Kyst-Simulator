# Kyst Simulator — Design Document

## Purpose

The Kyst Simulator is a Windows GUI application that mimics the behaviour of a Kyst card device. It allows PLC developers to test serial communication code without requiring physical Kyst hardware.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Kyst Simulator                      │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  GUI Layer   │◄──►│  Kyst Device Engine      │   │
│  │ (main_window)│    │  (kyst_device.py)        │   │
│  └──────────────┘    └──────────────────────────┘   │
│         ▲                        ▲                   │
│         │                        │                   │
│  ┌──────────────────────────────────────────────┐   │
│  │           Comms Layer                        │   │
│  │   TCPServer  │  SerialServer                 │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
          ▲
          │ TCP or Serial
          ▼
        PLC
```

## Layers

### GUI Layer (`gui/`)
- Built with Python `tkinter` (no external GUI dependencies, ships with Python)
- Displays connection status, device toggles, and command/response log
- Passes toggle state to the device engine

### Comms Layer (`comms/`)
- `TCPServer` — listens on configurable port, handles multiple client connections
- `SerialServer` — reads/writes on a COM port (requires `pyserial`)
- Both call the same `on_receive(data) -> response` callback

### Device Engine (`simulator/`)
- `KystDevice` — holds device state (online, fault flags, etc.)
- Parses incoming command bytes and builds correct response bytes
- Protocol implementation goes here

---

## Communication Flow

```
PLC sends command bytes
        ↓
Comms layer receives (TCP or Serial)
        ↓
KystDevice.process(data) called
        ↓
Command parsed, state checked, response built
        ↓
Response bytes returned to comms layer
        ↓
Comms layer sends response back to PLC
        ↓
Log displayed in GUI
```

---

## Protocol Details

⚠️ **To be defined** — Kyst card telegram specification to be provided.

Items to document:
- Command structure (byte layout, length, addressing)
- Response structure
- Supported command codes
- Error / NAK conditions
- Timing requirements

---

## State Toggles (GUI)

To be finalised once protocol is confirmed. Initial placeholders:

| Toggle | Default | Description |
|--------|---------|-------------|
| Device Online | ON | Whether device responds at all |
| Simulate Fault | OFF | Return fault/NAK response |
| Auto Respond | ON | Automatically respond to all commands |

---

## Future Enhancements

- Configurable response delay (simulate slow device)
- Response templates editor
- Save/load scenario profiles
- Multiple simultaneous device simulation
- Build to .exe with PyInstaller for standalone Windows deployment
