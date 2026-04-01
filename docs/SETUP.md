# Kyst Simulator — Setup Guide

## Requirements

- Python 3.10 or newer
- Windows 10/11
- VS Code (recommended editor)

## VS Code Extensions

Install these from the Extensions panel (`Ctrl+Shift+X`):

- **Python** (Microsoft)
- **Pylance** (Microsoft)

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/MatSmith95/Kyst-Simulator.git
cd Kyst-Simulator

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

## Building a Standalone .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "KystSimulator" main.py
```

Output will be in the `dist/` folder.
