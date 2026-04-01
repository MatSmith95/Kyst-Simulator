"""
Kyst Simulator — Main Window (GUI)
Placeholder — full implementation to follow once protocol details are confirmed.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import datetime


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Kyst Simulator")
        self.root.geometry("900x650")
        self.root.resizable(True, True)
        self._build_ui()

    def _build_ui(self):
        # ── Title bar ──────────────────────────────────────────────────────────
        title = tk.Label(
            self.root,
            text="Kyst Card Simulator",
            font=("Segoe UI", 16, "bold"),
            pady=10
        )
        title.pack(fill=tk.X)

        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=10)

        # ── Main layout ────────────────────────────────────────────────────────
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left panel — connection + toggles
        left = tk.Frame(main_frame, width=280)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)

        # Right panel — log
        right = tk.Frame(main_frame)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_connection_panel(left)
        self._build_toggles_panel(left)
        self._build_log_panel(right)
        self._build_status_bar()

    def _build_connection_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Connection", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))

        # Mode selector
        tk.Label(frame, text="Mode:").grid(row=0, column=0, sticky=tk.W)
        self.conn_mode = tk.StringVar(value="TCP")
        mode_combo = ttk.Combobox(
            frame, textvariable=self.conn_mode,
            values=["TCP", "Serial (COM)"], state="readonly", width=14
        )
        mode_combo.grid(row=0, column=1, sticky=tk.W, padx=4)
        mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        # TCP settings
        self.tcp_frame = tk.Frame(frame)
        self.tcp_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=4)

        tk.Label(self.tcp_frame, text="Listen Port:").grid(row=0, column=0, sticky=tk.W)
        self.tcp_port = tk.StringVar(value="4001")
        tk.Entry(self.tcp_frame, textvariable=self.tcp_port, width=8).grid(row=0, column=1, padx=4)

        # Serial settings (hidden by default)
        self.serial_frame = tk.Frame(frame)
        tk.Label(self.serial_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W)
        self.com_port = tk.StringVar(value="COM1")
        tk.Entry(self.serial_frame, textvariable=self.com_port, width=8).grid(row=0, column=1, padx=4)
        tk.Label(self.serial_frame, text="Baud:").grid(row=1, column=0, sticky=tk.W)
        self.baud_rate = tk.StringVar(value="9600")
        ttk.Combobox(
            self.serial_frame, textvariable=self.baud_rate,
            values=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
            state="readonly", width=8
        ).grid(row=1, column=1, padx=4)

        # Connect / Disconnect buttons
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(8, 0))
        self.btn_connect = tk.Button(
            btn_frame, text="Connect", width=10,
            bg="#4CAF50", fg="white", command=self._on_connect
        )
        self.btn_connect.pack(side=tk.LEFT, padx=2)
        self.btn_disconnect = tk.Button(
            btn_frame, text="Disconnect", width=10,
            bg="#f44336", fg="white", state=tk.DISABLED, command=self._on_disconnect
        )
        self.btn_disconnect.pack(side=tk.LEFT, padx=2)

    def _build_toggles_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Device Settings", padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text="Device toggles will appear here\nonce protocol details are defined.",
            fg="grey",
            justify=tk.CENTER
        ).pack(pady=20)

        # Placeholder toggles — to be replaced with real settings
        self.toggles = {}
        placeholder_toggles = [
            ("Device Online", True),
            ("Simulate Fault", False),
            ("Auto Respond", True),
        ]
        for label, default in placeholder_toggles:
            var = tk.BooleanVar(value=default)
            self.toggles[label] = var
            cb = ttk.Checkbutton(frame, text=label, variable=var)
            cb.pack(anchor=tk.W, padx=4, pady=2)

    def _build_log_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Command / Response Log", padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        # Log area
        self.log = scrolledtext.ScrolledText(
            frame, state=tk.DISABLED, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.log.pack(fill=tk.BOTH, expand=True)

        # Tag colours
        self.log.tag_config("rx", foreground="#9cdcfe")   # blue — received from PLC
        self.log.tag_config("tx", foreground="#b5cea8")   # green — sent to PLC
        self.log.tag_config("info", foreground="#ce9178") # orange — system info
        self.log.tag_config("err", foreground="#f48771")  # red — errors

        # Clear button
        tk.Button(frame, text="Clear Log", command=self._clear_log).pack(anchor=tk.E, pady=(4, 0))

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="● Disconnected")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            bd=1, relief=tk.SUNKEN, anchor=tk.W, padx=8,
            font=("Segoe UI", 9)
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def _on_mode_change(self, event=None):
        mode = self.conn_mode.get()
        if mode == "TCP":
            self.serial_frame.grid_remove()
            self.tcp_frame.grid()
        else:
            self.tcp_frame.grid_remove()
            self.serial_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=4)

    def _on_connect(self):
        # Placeholder — real connection logic to be implemented
        mode = self.conn_mode.get()
        self.log_message(f"Connecting in {mode} mode...", "info")
        self.btn_connect.config(state=tk.DISABLED)
        self.btn_disconnect.config(state=tk.NORMAL)
        self.status_var.set(f"● Connected ({mode})")

    def _on_disconnect(self):
        self.log_message("Disconnected.", "info")
        self.btn_connect.config(state=tk.NORMAL)
        self.btn_disconnect.config(state=tk.DISABLED)
        self.status_var.set("● Disconnected")

    def _clear_log(self):
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)

    # ── Public helpers ─────────────────────────────────────────────────────────
    def log_message(self, message: str, tag: str = "info"):
        """Append a timestamped message to the log window."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def run(self):
        self.log_message("Kyst Simulator started. Waiting for connection.", "info")
        self.root.mainloop()
