"""
Kyst Simulator — Main Window
Full AE99 channel complement in the Slave panel:
  Inputs:  AIN 0–20, DIN 21–23, CNT 0–15, ENC 0–11, DIG 0–23, TEMP 1–4
  Outputs: PWM 0–23 (read-only display of what PLC sent), APW 0–23
"""

from __future__ import annotations
import customtkinter as ctk
import datetime
import threading
import logging
from typing import Callable

from comms.connection_manager import ConnectionManager, ConnectionState
from comms.serial_server import SerialServer, SUPPORTED_BAUD_RATES
from simulator.protocol import DeviceState
from config import config as cfg_module

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SLAVE_MODE  = "Slave  (PC = Kyst Card)"
MASTER_MODE = "Master (PC = PLC)"

STATUS_COLOURS = {
    ConnectionState.DISCONNECTED: "#e05252",
    ConnectionState.LISTENING:    "#f0a500",
    ConnectionState.CONNECTED:    "#66bb6a",
    ConnectionState.ERROR:        "#ff3333",
}
STATUS_LABELS = {
    ConnectionState.DISCONNECTED: "⬤  Disconnected",
    ConnectionState.LISTENING:    "⬤  Listening…",
    ConnectionState.CONNECTED:    "⬤  Connected",
    ConnectionState.ERROR:        "⬤  Error",
}


class MainWindow:
    def __init__(self):
        self._cfg = cfg_module.load()
        self.device_state = self._make_device_state()
        self._conn_mgr = ConnectionManager(
            device_state=self.device_state,
            on_log=self._on_log,
            on_state_change=self._on_conn_state_change,
        )
        self.root = ctk.CTk()
        self.root.title("Kyst Simulator  v0.4")
        self.root.geometry("1200x760")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self._refresh_available_ports()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        top = ctk.CTkFrame(self.root, height=52, corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="  Kyst Card Simulator",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=10)

        mode_frame = ctk.CTkFrame(top, fg_color="transparent")
        mode_frame.pack(side="right", padx=14)
        ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._sim_mode = ctk.StringVar(value=SLAVE_MODE)
        ctk.CTkOptionMenu(
            mode_frame, variable=self._sim_mode,
            values=[SLAVE_MODE, MASTER_MODE],
            command=self._on_sim_mode_change, width=210,
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            top, text="⬤  Disconnected",
            font=ctk.CTkFont(size=13), text_color="#e05252"
        )
        self._status_label.pack(side="right", padx=16)

        # Main body
        body = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=6)

        self._left = ctk.CTkFrame(body, width=300)
        self._left.pack(side="left", fill="y", padx=(0, 6))
        self._left.pack_propagate(False)

        right = ctk.CTkFrame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_connection_panel(self._left)
        self._build_slave_panel(self._left)
        self._build_master_panel(self._left)
        self._build_log_panel(right)

        self._slave_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ── Connection Panel ───────────────────────────────────────────────────────

    def _build_connection_panel(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 6), padx=4)

        ctk.CTkLabel(frame, text="Connection",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

        tr_row = ctk.CTkFrame(frame, fg_color="transparent")
        tr_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(tr_row, text="Transport:", width=80, anchor="w").pack(side="left")
        self._transport = ctk.StringVar(value=self._cfg.connection.mode)
        ctk.CTkOptionMenu(
            tr_row, variable=self._transport,
            values=["TCP", "Serial (COM)"],
            command=self._on_transport_change, width=140,
        ).pack(side="left", padx=4)

        # TCP
        self._tcp_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self._tcp_frame.pack(fill="x", padx=10, pady=2)
        row = ctk.CTkFrame(self._tcp_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text="Host:", width=80, anchor="w").pack(side="left")
        self._tcp_host = ctk.StringVar(value=self._cfg.connection.tcp.host)
        ctk.CTkEntry(row, textvariable=self._tcp_host, width=130).pack(side="left", padx=4)
        row2 = ctk.CTkFrame(self._tcp_frame, fg_color="transparent")
        row2.pack(fill="x", pady=1)
        ctk.CTkLabel(row2, text="Port:", width=80, anchor="w").pack(side="left")
        self._tcp_port = ctk.StringVar(value=str(self._cfg.connection.tcp.port))
        ctk.CTkEntry(row2, textvariable=self._tcp_port, width=80).pack(side="left", padx=4)

        # Serial
        self._serial_frame = ctk.CTkFrame(frame, fg_color="transparent")
        r1 = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        r1.pack(fill="x", pady=1)
        ctk.CTkLabel(r1, text="COM Port:", width=80, anchor="w").pack(side="left")
        self._serial_port = ctk.StringVar(value=self._cfg.connection.serial.port)
        self._port_menu = ctk.CTkOptionMenu(r1, variable=self._serial_port, values=["COM1"], width=100)
        self._port_menu.pack(side="left", padx=4)
        r2 = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        r2.pack(fill="x", pady=1)
        ctk.CTkLabel(r2, text="Baud Rate:", width=80, anchor="w").pack(side="left")
        self._baud_rate = ctk.StringVar(value=str(self._cfg.connection.serial.baud_rate))
        ctk.CTkOptionMenu(
            r2, variable=self._baud_rate,
            values=[str(b) for b in SUPPORTED_BAUD_RATES], width=100,
        ).pack(side="left", padx=4)
        r3 = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        r3.pack(fill="x", pady=1)
        ctk.CTkLabel(r3, text="Parity:", width=80, anchor="w").pack(side="left")
        self._parity = ctk.StringVar(value=self._cfg.connection.serial.parity)
        ctk.CTkOptionMenu(r3, variable=self._parity, values=["N", "E", "O"], width=60).pack(side="left", padx=4)

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(8, 10))
        self._btn_connect = ctk.CTkButton(
            btn_row, text="Connect", width=110,
            fg_color="#2e7d32", hover_color="#1b5e20", command=self._on_connect,
        )
        self._btn_connect.pack(side="left", padx=(0, 6))
        self._btn_disconnect = ctk.CTkButton(
            btn_row, text="Disconnect", width=110,
            fg_color="#c62828", hover_color="#7f0000",
            state="disabled", command=self._on_disconnect,
        )
        self._btn_disconnect.pack(side="left")

    # ── Slave Panel ────────────────────────────────────────────────────────────

    def _build_slave_panel(self, parent):
        self._slave_panel = ctk.CTkTabview(parent)

        tab_status  = self._slave_panel.add("Status")
        tab_analog  = self._slave_panel.add("Analog In")
        tab_digital = self._slave_panel.add("Digital/Cnt")
        tab_temp    = self._slave_panel.add("Temp/Health")

        self._build_status_tab(tab_status)
        self._build_analog_tab(tab_analog)
        self._build_digital_tab(tab_digital)
        self._build_temp_tab(tab_temp)

    def _build_status_tab(self, parent):
        """Node address, online/fault toggles, reply delay."""
        sf = ctk.CTkScrollableFrame(parent)
        sf.pack(fill="both", expand=True)

        s = self.device_state

        # Node address
        row = ctk.CTkFrame(sf, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=3)
        ctk.CTkLabel(row, text="Node Address:", width=130, anchor="w").pack(side="left")
        self._node_addr = ctk.StringVar(value=str(s.node_address))
        ctk.CTkOptionMenu(
            row, variable=self._node_addr,
            values=[str(i) for i in range(16)],
            command=lambda v: setattr(self.device_state, "node_address", int(v)),
            width=60,
        ).pack(side="left", padx=4)

        # Toggles
        self._toggles: dict[str, ctk.BooleanVar] = {}
        toggle_defs = [
            ("Online",          "online"),
            ("Reset Flag",      "reset_flag"),
            ("Leak 1",          "leak_1"),
            ("Leak 2",          "leak_2"),
            ("PWM Bank 1 OVL",  "pwm_bank1_overload"),
            ("PWM Bank 2 OVL",  "pwm_bank2_overload"),
            ("PWM Bank 3 OVL",  "pwm_bank3_overload"),
            ("Analog Pwr OVL",  "analog_power_overload"),
        ]
        for label, attr in toggle_defs:
            var = ctk.BooleanVar(value=getattr(s, attr, False))
            self._toggles[label] = var
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(r, text=label, anchor="w").pack(side="left", expand=True, fill="x")

            def _cb(a=attr, v=var):
                setattr(self.device_state, a, v.get())

            ctk.CTkSwitch(r, variable=var, text="", width=46,
                          onvalue=True, offvalue=False, command=_cb).pack(side="right")

        # Reply delay
        dr = ctk.CTkFrame(sf, fg_color="transparent")
        dr.pack(fill="x", padx=6, pady=(8, 4))
        ctk.CTkLabel(dr, text="Reply Delay:", width=100, anchor="w").pack(side="left")
        self._delay_var = ctk.StringVar(value=str(s.reply_delay_100us))
        e = ctk.CTkEntry(dr, textvariable=self._delay_var, width=50)
        e.pack(side="left", padx=4)
        ctk.CTkLabel(dr, text="× 100µs", text_color="gray").pack(side="left")
        e.bind("<Return>", self._on_delay_change)
        e.bind("<FocusOut>", self._on_delay_change)

    def _build_analog_tab(self, parent):
        """AIN 0–20 sliders."""
        sf = ctk.CTkScrollableFrame(parent)
        sf.pack(fill="both", expand=True)

        ctk.CTkLabel(sf, text="Analog Inputs — AIN 0–20",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(4, 2))
        ctk.CTkLabel(sf, text="16-bit value (0 = 0V/0mA, 65535 = 10V/20mA)",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=6)

        self._ain_vars: list[ctk.IntVar] = []
        for i in range(21):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(r, text=f"AIN {i:02d}:", width=55, anchor="w").pack(side="left")
            var = ctk.IntVar(value=self.device_state.analog_inputs[i])
            self._ain_vars.append(var)
            slider = ctk.CTkSlider(
                r, from_=0, to=65535, number_of_steps=1000, variable=var, width=130,
                command=lambda v, idx=i: self._on_ain_change(idx, int(v))
            )
            slider.pack(side="left", padx=4)
            lbl = ctk.CTkLabel(r, text="0", width=55, anchor="w")
            lbl.pack(side="left")
            var.trace_add("write", lambda *_, v=var, l=lbl: l.configure(text=str(v.get())))

    def _build_digital_tab(self, parent):
        """DIN 21–23, CNT 0–15, ENC 0–11, DIG 0–23."""
        sf = ctk.CTkScrollableFrame(parent)
        sf.pack(fill="both", expand=True)

        # DIN 21–23
        ctk.CTkLabel(sf, text="Digital Inputs — DIN 21–23",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(4, 2))
        self._din_vars: list[ctk.BooleanVar] = []
        for i in range(3):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(r, text=f"DIN {21+i}:", width=60, anchor="w").pack(side="left")
            var = ctk.BooleanVar(value=self.device_state.digital_inputs[i])
            self._din_vars.append(var)

            def _din_cb(i=i, v=var):
                self.device_state.digital_inputs[i] = v.get()

            ctk.CTkSwitch(r, variable=var, text="", width=46,
                          onvalue=True, offvalue=False, command=_din_cb).pack(side="left", padx=4)

        # CNT 0–15
        ctk.CTkLabel(sf, text="Counter Inputs — CNT 0–15",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(8, 2))
        self._cnt_vars: list[ctk.IntVar] = []
        for i in range(16):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(r, text=f"CNT {i:02d}:", width=55, anchor="w").pack(side="left")
            var = ctk.IntVar(value=self.device_state.counter_inputs[i])
            self._cnt_vars.append(var)
            e = ctk.CTkEntry(r, textvariable=var, width=70)
            e.pack(side="left", padx=4)
            e.bind("<Return>", lambda _e, idx=i, v=var: self._on_cnt_change(idx, v))
            e.bind("<FocusOut>", lambda _e, idx=i, v=var: self._on_cnt_change(idx, v))

        # ENC 0–11
        ctk.CTkLabel(sf, text="Encoder Inputs — ENC 0–11",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(8, 2))
        self._enc_vars: list[ctk.IntVar] = []
        for i in range(12):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(r, text=f"ENC {i:02d}:", width=55, anchor="w").pack(side="left")
            var = ctk.IntVar(value=self.device_state.encoder_inputs[i])
            self._enc_vars.append(var)
            e = ctk.CTkEntry(r, textvariable=var, width=70)
            e.pack(side="left", padx=4)
            e.bind("<Return>", lambda _e, idx=i, v=var: self._on_enc_change(idx, v))
            e.bind("<FocusOut>", lambda _e, idx=i, v=var: self._on_enc_change(idx, v))

        # DIG 0–23
        ctk.CTkLabel(sf, text="Digital Word — DIG 0–23 (3 bytes, hex)",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(8, 2))
        self._dig_vars: list[ctk.StringVar] = []
        for i in range(3):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(r, text=f"DIG {i*8}–{i*8+7}:", width=70, anchor="w").pack(side="left")
            var = ctk.StringVar(value=f"0x{self.device_state.digital_word[i]:02X}")
            self._dig_vars.append(var)
            e = ctk.CTkEntry(r, textvariable=var, width=70)
            e.pack(side="left", padx=4)
            e.bind("<Return>", lambda _e, idx=i, v=var: self._on_dig_change(idx, v))
            e.bind("<FocusOut>", lambda _e, idx=i, v=var: self._on_dig_change(idx, v))

    def _build_temp_tab(self, parent):
        """TEMP 1–4 and board health."""
        sf = ctk.CTkScrollableFrame(parent)
        sf.pack(fill="both", expand=True)

        ctk.CTkLabel(sf, text="Temperature Inputs — TEMP 1–4 (PT100)",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(4, 2))
        ctk.CTkLabel(sf, text="Value in °C  (stored as (°C + 100) × 100 internally)",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=6)

        self._temp_vars: list[ctk.StringVar] = []
        for i in range(4):
            r = ctk.CTkFrame(sf, fg_color="transparent")
            r.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(r, text=f"TEMP {i+1} (°C):", width=90, anchor="w").pack(side="left")
            raw = self.device_state.temperature_inputs[i]
            var = ctk.StringVar(value=f"{(raw / 100) - 100:.1f}")
            self._temp_vars.append(var)
            e = ctk.CTkEntry(r, textvariable=var, width=70)
            e.pack(side="left", padx=4)
            e.bind("<Return>", lambda _e, idx=i, v=var: self._on_temp_input_change(idx, v))
            e.bind("<FocusOut>", lambda _e, idx=i, v=var: self._on_temp_input_change(idx, v))

        ctk.CTkLabel(sf, text="Board Health",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(12, 2))

        s = self.device_state
        tr = ctk.CTkFrame(sf, fg_color="transparent")
        tr.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(tr, text="Board Temp (°C):", width=120, anchor="w").pack(side="left")
        self._board_temp_var = ctk.StringVar(value=f"{(s.board_temp_raw / 100) - 100:.1f}")
        te = ctk.CTkEntry(tr, textvariable=self._board_temp_var, width=70)
        te.pack(side="left", padx=4)
        te.bind("<Return>", self._on_board_temp_change)
        te.bind("<FocusOut>", self._on_board_temp_change)

        vr = ctk.CTkFrame(sf, fg_color="transparent")
        vr.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(vr, text="Board Voltage (V):", width=120, anchor="w").pack(side="left")
        self._volt_var = ctk.StringVar(value=f"{s.board_voltage_raw / 100:.2f}")
        ve = ctk.CTkEntry(vr, textvariable=self._volt_var, width=70)
        ve.pack(side="left", padx=4)
        ve.bind("<Return>", self._on_volt_change)
        ve.bind("<FocusOut>", self._on_volt_change)

    # ── Master Panel ───────────────────────────────────────────────────────────

    def _build_master_panel(self, parent):
        self._master_panel = ctk.CTkScrollableFrame(parent, label_text="Commands (Master)")

        ctk.CTkLabel(self._master_panel, text="Target Node Address:", anchor="w").pack(
            fill="x", padx=6, pady=(6, 2))
        self._master_node = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            self._master_panel, variable=self._master_node,
            values=[str(i) for i in range(16)], width=80,
        ).pack(anchor="w", padx=6, pady=(0, 8))

        ctk.CTkLabel(self._master_panel, text="Type C Commands",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(0, 4))
        for label, cmd in [
            ("Version Info",     self._cmd_version_info),
            ("Reset Flag",       self._cmd_reset_flag),
            ("DIP Switch Query", self._cmd_dip_switch),
            ("Reset Outputs",    self._cmd_reset_outputs),
            ("Status Flags",     self._cmd_status_flags),
        ]:
            ctk.CTkButton(self._master_panel, text=label, command=cmd, height=30
                          ).pack(fill="x", padx=6, pady=2)

        ctk.CTkLabel(self._master_panel, text="Type AB",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(10, 4))
        ctk.CTkButton(self._master_panel, text="Send AB (All OFF)",
                      command=self._cmd_ab_all_off, height=30).pack(fill="x", padx=6, pady=2)
        ctk.CTkButton(self._master_panel, text="Send AB (All ON)",
                      command=self._cmd_ab_all_on, height=30).pack(fill="x", padx=6, pady=2)

    # ── Log Panel ──────────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(header, text="Command / Response Log",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self._stats_label = ctk.CTkLabel(header, text="RX: 0  TX: 0  CRC Err: 0",
                                          font=ctk.CTkFont(size=11), text_color="gray")
        self._stats_label.pack(side="left", padx=16)

        # Decoded toggle
        self._show_decoded = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(header, text="Decoded", variable=self._show_decoded,
                        width=90).pack(side="right", padx=(0, 8))
        ctk.CTkButton(header, text="Save Log", width=80, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._save_log).pack(side="right", padx=(0, 4))
        ctk.CTkButton(header, text="Clear", width=70, height=26,
                      fg_color="transparent", border_width=1,
                      command=self._clear_log).pack(side="right")

        self._log = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled", wrap="none",
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._log._textbox.tag_config("rx",   foreground="#9cdcfe")
        self._log._textbox.tag_config("tx",   foreground="#b5cea8")
        self._log._textbox.tag_config("info", foreground="#ce9178")
        self._log._textbox.tag_config("err",  foreground="#f48771")
        self._log._textbox.tag_config("dec",  foreground="#c586c0")

    # ── Event Handlers ─────────────────────────────────────────────────────────

    def _on_sim_mode_change(self, value):
        if value == SLAVE_MODE:
            self._master_panel.pack_forget()
            self._slave_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        else:
            self._slave_panel.pack_forget()
            self._master_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def _on_transport_change(self, value):
        if value == "TCP":
            self._serial_frame.pack_forget()
            self._tcp_frame.pack(fill="x", padx=10, pady=2)
        else:
            self._tcp_frame.pack_forget()
            self._serial_frame.pack(fill="x", padx=10, pady=2)

    def _on_connect(self):
        if self._transport.get() == "TCP":
            try:
                port = int(self._tcp_port.get())
            except ValueError:
                self.log_message("Invalid port.", "err")
                return
            self._conn_mgr.start_tcp(host=self._tcp_host.get(), port=port)
        else:
            self._conn_mgr.start_serial(
                port=self._serial_port.get(),
                baud_rate=int(self._baud_rate.get()),
                parity=self._parity.get(),
            )
        self._btn_connect.configure(state="disabled")
        self._btn_disconnect.configure(state="normal")

    def _on_disconnect(self):
        self._conn_mgr.stop()
        self._btn_connect.configure(state="normal")
        self._btn_disconnect.configure(state="disabled")

    def _on_ain_change(self, idx, value):
        self.device_state.analog_inputs[idx] = value

    def _on_cnt_change(self, idx, var):
        try:
            self.device_state.counter_inputs[idx] = int(var.get())
        except (ValueError, tk.TclError):
            pass

    def _on_enc_change(self, idx, var):
        try:
            self.device_state.encoder_inputs[idx] = int(var.get())
        except (ValueError, Exception):
            pass

    def _on_dig_change(self, idx, var):
        try:
            self.device_state.digital_word[idx] = int(var.get(), 16)
        except (ValueError, Exception):
            pass

    def _on_temp_input_change(self, idx, var):
        try:
            self.device_state.temperature_inputs[idx] = int((float(var.get()) + 100) * 100)
        except (ValueError, Exception):
            pass

    def _on_board_temp_change(self, _=None):
        try:
            self.device_state.board_temp_raw = int((float(self._board_temp_var.get()) + 100) * 100)
        except (ValueError, Exception):
            pass

    def _on_volt_change(self, _=None):
        try:
            self.device_state.board_voltage_raw = int(float(self._volt_var.get()) * 100)
        except (ValueError, Exception):
            pass

    def _on_delay_change(self, _=None):
        try:
            self.device_state.reply_delay_100us = int(self._delay_var.get())
        except (ValueError, Exception):
            pass

    def _on_conn_state_change(self, state):
        def _update():
            self._status_label.configure(
                text=STATUS_LABELS.get(state, "⬤  Unknown"),
                text_color=STATUS_COLOURS.get(state, "#e05252")
            )
        self.root.after(0, _update)

    def _on_log(self, message, tag):
        self.root.after(0, lambda: self._do_log(message, tag))
        self.root.after(0, self._refresh_stats)

    def _on_close(self):
        self._conn_mgr.stop()
        self._save_config()
        self.root.destroy()

    # ── Master commands ────────────────────────────────────────────────────────

    def _master_send(self, telegram):
        self.log_message(f"MASTER TX  {telegram.hex().upper()}", "tx")
        self.log_message("(Connect to real device for hardware TX)", "info")

    def _cmd_version_info(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        self._master_send(build_master_type_c(int(self._master_node.get()), TypeCCmd.VERSION_INFO))

    def _cmd_reset_flag(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        self._master_send(build_master_type_c(int(self._master_node.get()), TypeCCmd.RESET_FLAG))

    def _cmd_dip_switch(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        self._master_send(build_master_type_c(int(self._master_node.get()), TypeCCmd.DIP_SWITCH))

    def _cmd_reset_outputs(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        self._master_send(build_master_type_c(int(self._master_node.get()), TypeCCmd.RESET_OUTPUTS))

    def _cmd_status_flags(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        self._master_send(build_master_type_c(int(self._master_node.get()), TypeCCmd.STATUS_FLAGS))

    def _cmd_ab_all_off(self):
        from simulator.telegram import build_master_type_ab
        self._master_send(build_master_type_ab(int(self._master_node.get()), 0x80, 0x00, 0x0F, b"\x00\x00\x00"))

    def _cmd_ab_all_on(self):
        from simulator.telegram import build_master_type_ab
        self._master_send(build_master_type_ab(int(self._master_node.get()), 0x80, 0x00, 0x0F, b"\xFF\xFF\xFF"))

    # ── Log helpers ────────────────────────────────────────────────────────────

    def log_message(self, message, tag="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        def _insert():
            self._log.configure(state="normal")
            self._log._textbox.insert("end", f"[{ts}] {message}\n", tag)
            self._log._textbox.see("end")
            self._log.configure(state="disabled")

        self.root.after(0, _insert)

    def _do_log(self, message, tag):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._log.configure(state="normal")
        self._log._textbox.insert("end", f"[{ts}] {message}\n", tag)
        self._log._textbox.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _save_log(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"kyst_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if path:
            try:
                with open(path, "w") as f:
                    f.write(self._log._textbox.get("1.0", "end"))
                self.log_message(f"Log saved: {path}", "info")
            except Exception as e:
                self.log_message(f"Save failed: {e}", "err")

    def _refresh_stats(self):
        m = self._conn_mgr
        self._stats_label.configure(text=f"RX: {m.rx_count}  TX: {m.tx_count}  CRC Err: {m.crc_errors}")

    # ── Config ─────────────────────────────────────────────────────────────────

    def _refresh_available_ports(self):
        ports = SerialServer.list_ports() or [f"COM{i}" for i in range(1, 9)]
        self._port_menu.configure(values=ports)
        if self._serial_port.get() not in ports and ports:
            self._serial_port.set(ports[0])

    def _make_device_state(self) -> DeviceState:
        d = self._cfg.device
        return DeviceState(
            node_address=d.node_address,
            online=d.online,
            reset_flag=d.reset_flag,
            reply_delay_100us=d.reply_delay_100us,
            board_temp_raw=d.board_temp_raw,
            board_voltage_raw=d.board_voltage_raw,
        )

    def _save_config(self):
        self._cfg.connection.mode = self._transport.get().split()[0]
        self._cfg.connection.tcp.host = self._tcp_host.get()
        try: self._cfg.connection.tcp.port = int(self._tcp_port.get())
        except ValueError: pass
        self._cfg.connection.serial.port = self._serial_port.get()
        try: self._cfg.connection.serial.baud_rate = int(self._baud_rate.get())
        except ValueError: pass
        self._cfg.device.node_address = self.device_state.node_address
        self._cfg.device.reply_delay_100us = self.device_state.reply_delay_100us
        cfg_module.save(self._cfg)

    def run(self):
        self.log_message("Kyst Simulator started.", "info")
        self.log_message("Select Slave/Master mode and transport, then click Connect.", "info")
        self.root.mainloop()
