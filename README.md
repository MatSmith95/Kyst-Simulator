# Kyst Simulator

A Windows GUI application that simulates a **Kyst card device**.

The simulator acts as a serial/TCP server — receiving commands from a PLC and generating configurable responses, allowing development and testing of PLC software without physical Kyst hardware.

---

## Overview

```
PLC  ──────────► Kyst Simulator (Windows PC)
     Serial/TCP       GUI + Response Engine
                      ↕
                 Simulated Kyst Card Behaviour
```

- **Input:** Serial commands received from a PLC (via COM port or TCP)
- **Processing:** Configurable response logic mimicking a real Kyst card
- **Output:** Response sent back to the PLC

---

## Features (Planned)

- GUI application — runs on Windows
- Toggle switches for configurable device states
- Serial (COM port) and TCP connection modes
- Real-time command/response log viewer
- Configurable response templates

---

## Project Structure

```
Kyst-Simulator/
├── main.py                 # Entry point
├── gui/                    # GUI components (tkinter/PyQt)
│   └── main_window.py
├── comms/                  # Serial / TCP communication
│   ├── serial_server.py
│   └── tcp_server.py
├── simulator/              # Kyst device simulation logic
│   └── kyst_device.py
├── config/                 # Configuration files
│   └── settings.json
├── docs/                   # Documentation
│   └── DESIGN.md
├── requirements.txt
└── README.md
```

---

## Requirements

- Python 3.10+
- Windows 10/11
- See `requirements.txt` for Python dependencies

---

## Getting Started

```bash
pip install -r requirements.txt
python main.py
```

---

## Status

🚧 **In development** — initial scaffold. Protocol details and response logic to be defined.

---

## Author

Mathew Smith
