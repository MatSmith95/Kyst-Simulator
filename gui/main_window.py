"""
Kyst Simulator — Main Window
Built with CustomTkinter for a modern Windows look.
"""

import customtkinter as ctk
import datetime
import threading


# ── App appearance ─────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")       # "dark" | "light" | "system"
ctk.set_default_color_theme("blue")


class MainWindow:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Kyst Simulator")
        self.root.geometry("1000x680")
        self.root.resizable(True, True)
        self._connected = False
        self._build_ui()

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self.root, height=50, corner_radius=0)
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)

        ctk.CTkLabel(
            top_bar,
            text="  Kyst Card Simulator",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left", padx=10)

        self.status_label = ctk.CTkLabel(
            top_bar,
            text="⬤  Disconnected",
            font=ctk.CTkFont(size=13),
            text_color="#e05252"
        )
        self.status_label.pack(side="right", padx=16)

        # ── Main layout ───────────────────────────────────────────────────────
        main_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=10, pady=8)

        # Left panel (fixed width)
        left = ctk.CTkFrame(main_frame, width=260)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        # Right panel (log — expands)
        right = ctk.CTkFrame(main_frame)
        right.pack(side="left", fill="both", expand=True)

        self._build_connection_panel(left)
        self._build_toggles_panel(left)
        self._build_log_panel(right)

    # ── Connection panel ───────────────────────────────────────────────────────
    def _build_connection_panel(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 8), padx=4)

        ctk.CTkLabel(frame, text="Connection", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )

        # Mode selector
        mode_row = ctk.CTkFrame(frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(mode_row, text="Mode:", width=70, anchor="w").pack(side="left")
        self.conn_mode = ctk.StringVar(value="TCP")
        mode_menu = ctk.CTkOptionMenu(
            mode_row,
            variable=self.conn_mode,
            values=["TCP", "Serial (COM)"],
            command=self._on_mode_change,
            width=140
        )
        mode_menu.pack(side="left", padx=4)

        # TCP fields
        self.tcp_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.tcp_frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(self.tcp_frame, text="Port:", width=70, anchor="w").pack(side="left")
        self.tcp_port = ctk.StringVar(value="4001")
        ctk.CTkEntry(self.tcp_frame, textvariable=self.tcp_port, width=80).pack(side="left", padx=4)

        # Serial fields (hidden by default)
        self.serial_frame = ctk.CTkFrame(frame, fg_color="transparent")
        com_row = ctk.CTkFrame(self.serial_frame, fg_color="transparent")
        com_row.pack(fill="x", pady=1)
        ctk.CTkLabel(com_row, text="COM Port:", width=70, anchor="w").pack(side="left")
        self.com_port = ctk.StringVar(value="COM1")
        ctk.CTkEntry(com_row, textvariable=self.com_port, width=80).pack(side="left", padx=4)

        baud_row = ctk.CTkFrame(self.serial_frame, fg_color="transparent")
        baud_row.pack(fill="x", pady=1)
        ctk.CTkLabel(baud_row, text="Baud:", width=70, anchor="w").pack(side="left")
        self.baud_rate = ctk.StringVar(value="9600")
        ctk.CTkOptionMenu(
            baud_row,
            variable=self.baud_rate,
            values=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
            width=100
        ).pack(side="left", padx=4)

        # Buttons
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=10)
        self.btn_connect = ctk.CTkButton(
            btn_row, text="Connect", width=110,
            fg_color="#2e7d32", hover_color="#1b5e20",
            command=self._on_connect
        )
        self.btn_connect.pack(side="left", padx=(0, 6))
        self.btn_disconnect = ctk.CTkButton(
            btn_row, text="Disconnect", width=110,
            fg_color="#c62828", hover_color="#7f0000",
            state="disabled",
            command=self._on_disconnect
        )
        self.btn_disconnect.pack(side="left")

    # ── Device settings / toggles panel ───────────────────────────────────────
    def _build_toggles_panel(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="both", expand=True, padx=4)

        ctk.CTkLabel(frame, text="Device Settings", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )

        ctk.CTkLabel(
            frame,
            text="Toggles will be added once\nprotocol details are confirmed.",
            text_color="gray",
            font=ctk.CTkFont(size=11)
        ).pack(pady=8, padx=12)

        # Placeholder toggles
        self.toggles = {}
        placeholder_toggles = [
            ("Device Online", True),
            ("Simulate Fault", False),
            ("Auto Respond", True),
        ]
        for label, default in placeholder_toggles:
            var = ctk.BooleanVar(value=default)
            self.toggles[label] = var
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=label, anchor="w").pack(side="left", expand=True, fill="x")
            ctk.CTkSwitch(row, variable=var, text="", width=46, onvalue=True, offvalue=False).pack(side="right")

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(header, text="Command / Response Log", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(
            header, text="Clear", width=70, height=26,
            fg_color="transparent", border_width=1,
            command=self._clear_log
        ).pack(side="right")

        self.log = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            wrap="none"
        )
        self.log.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Colour tags (CTkTextbox wraps tk.Text underneath)
        self.log._textbox.tag_config("rx",   foreground="#9cdcfe")  # blue  — RX from PLC
        self.log._textbox.tag_config("tx",   foreground="#b5cea8")  # green — TX to PLC
        self.log._textbox.tag_config("info", foreground="#ce9178")  # amber — system
        self.log._textbox.tag_config("err",  foreground="#f48771")  # red   — errors

    # ── Event handlers ─────────────────────────────────────────────────────────
    def _on_mode_change(self, value):
        if value == "TCP":
            self.serial_frame.pack_forget()
            self.tcp_frame.pack(fill="x", padx=12, pady=2)
        else:
            self.tcp_frame.pack_forget()
            self.serial_frame.pack(fill="x", padx=12, pady=2)

    def _on_connect(self):
        mode = self.conn_mode.get()
        self.log_message(f"Connecting in {mode} mode...", "info")
        self.btn_connect.configure(state="disabled")
        self.btn_disconnect.configure(state="normal")
        self._connected = True
        self.status_label.configure(text="⬤  Connected", text_color="#66bb6a")

    def _on_disconnect(self):
        self.log_message("Disconnected.", "info")
        self.btn_connect.configure(state="normal")
        self.btn_disconnect.configure(state="disabled")
        self._connected = False
        self.status_label.configure(text="⬤  Disconnected", text_color="#e05252")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Public helpers ─────────────────────────────────────────────────────────
    def log_message(self, message: str, tag: str = "info"):
        """Thread-safe: append a timestamped message to the log."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"

        def _insert():
            self.log.configure(state="normal")
            self.log._textbox.insert("end", line, tag)
            self.log._textbox.see("end")
            self.log.configure(state="disabled")

        self.root.after(0, _insert)

    def run(self):
        self.log_message("Kyst Simulator started. Waiting for connection.", "info")
        self.root.mainloop()
