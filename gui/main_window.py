"""
Kyst Simulator — Main Window
CustomTkinter GUI wired to ConnectionManager.
Supports Slave Mode (PC = Kyst card) and Master Mode (PC = PLC).
"""

from __future__ import annotations
import customtkinter as ctk
import datetime
import threading
import logging
from typing import Callable

from comms.connection_manager import ConnectionManager, ConnectionState, ConnectionMode
from comms.serial_server import SerialServer, SUPPORTED_BAUD_RATES
from simulator.protocol import DeviceState
from config import config as cfg_module

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Simulator operating mode
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
        self.root.title("Kyst Simulator  v0.3")
        self.root.geometry("1100x720")
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

        # Simulator mode selector (Slave / Master) — top right
        mode_frame = ctk.CTkFrame(top, fg_color="transparent")
        mode_frame.pack(side="right", padx=14)
        ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self._sim_mode = ctk.StringVar(value=SLAVE_MODE)
        ctk.CTkOptionMenu(
            mode_frame, variable=self._sim_mode,
            values=[SLAVE_MODE, MASTER_MODE],
            command=self._on_sim_mode_change,
            width=210,
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            top, text="⬤  Disconnected",
            font=ctk.CTkFont(size=13), text_color="#e05252"
        )
        self._status_label.pack(side="right", padx=16)

        # Main layout
        body = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=6)

        # Left panel
        self._left = ctk.CTkFrame(body, width=270)
        self._left.pack(side="left", fill="y", padx=(0, 6))
        self._left.pack_propagate(False)

        # Right panel (log)
        right = ctk.CTkFrame(body)
        right.pack(side="left", fill="both", expand=True)

        self._build_connection_panel(self._left)
        self._build_slave_panel(self._left)
        self._build_master_panel(self._left)   # hidden initially
        self._build_log_panel(right)

        # Show slave panel by default
        self._slave_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ── Connection Panel ───────────────────────────────────────────────────────

    def _build_connection_panel(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 6), padx=4)

        ctk.CTkLabel(frame, text="Connection",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

        # Transport mode
        tr_row = ctk.CTkFrame(frame, fg_color="transparent")
        tr_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(tr_row, text="Transport:", width=80, anchor="w").pack(side="left")
        self._transport = ctk.StringVar(value=self._cfg.connection.mode)
        ctk.CTkOptionMenu(
            tr_row, variable=self._transport,
            values=["TCP", "Serial (COM)"],
            command=self._on_transport_change,
            width=140,
        ).pack(side="left", padx=4)

        # ── TCP sub-panel ──
        self._tcp_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self._tcp_frame.pack(fill="x", padx=10, pady=2)

        tcp_host_row = ctk.CTkFrame(self._tcp_frame, fg_color="transparent")
        tcp_host_row.pack(fill="x", pady=1)
        ctk.CTkLabel(tcp_host_row, text="Host:", width=80, anchor="w").pack(side="left")
        self._tcp_host = ctk.StringVar(value=self._cfg.connection.tcp.host)
        ctk.CTkEntry(tcp_host_row, textvariable=self._tcp_host, width=130).pack(side="left", padx=4)

        tcp_port_row = ctk.CTkFrame(self._tcp_frame, fg_color="transparent")
        tcp_port_row.pack(fill="x", pady=1)
        ctk.CTkLabel(tcp_port_row, text="Port:", width=80, anchor="w").pack(side="left")
        self._tcp_port = ctk.StringVar(value=str(self._cfg.connection.tcp.port))
        ctk.CTkEntry(tcp_port_row, textvariable=self._tcp_port, width=80).pack(side="left", padx=4)

        # ── Serial sub-panel ──
        self._serial_frame = ctk.CTkFrame(frame, fg_color="transparent")

        ser_port_row = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        ser_port_row.pack(fill="x", pady=1)
        ctk.CTkLabel(ser_port_row, text="COM Port:", width=80, anchor="w").pack(side="left")
        self._serial_port = ctk.StringVar(value=self._cfg.connection.serial.port)
        self._port_menu = ctk.CTkOptionMenu(
            ser_port_row, variable=self._serial_port, values=["COM1"], width=100
        )
        self._port_menu.pack(side="left", padx=4)

        ser_baud_row = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        ser_baud_row.pack(fill="x", pady=1)
        ctk.CTkLabel(ser_baud_row, text="Baud Rate:", width=80, anchor="w").pack(side="left")
        self._baud_rate = ctk.StringVar(value=str(self._cfg.connection.serial.baud_rate))
        ctk.CTkOptionMenu(
            ser_baud_row, variable=self._baud_rate,
            values=[str(b) for b in SUPPORTED_BAUD_RATES],
            width=100,
        ).pack(side="left", padx=4)

        ser_parity_row = ctk.CTkFrame(self._serial_frame, fg_color="transparent")
        ser_parity_row.pack(fill="x", pady=1)
        ctk.CTkLabel(ser_parity_row, text="Parity:", width=80, anchor="w").pack(side="left")
        self._parity = ctk.StringVar(value=self._cfg.connection.serial.parity)
        ctk.CTkOptionMenu(
            ser_parity_row, variable=self._parity,
            values=["N", "E", "O"], width=60,
        ).pack(side="left", padx=4)

        # Buttons
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(8, 10))

        self._btn_connect = ctk.CTkButton(
            btn_row, text="Connect", width=110,
            fg_color="#2e7d32", hover_color="#1b5e20",
            command=self._on_connect,
        )
        self._btn_connect.pack(side="left", padx=(0, 6))

        self._btn_disconnect = ctk.CTkButton(
            btn_row, text="Disconnect", width=110,
            fg_color="#c62828", hover_color="#7f0000",
            state="disabled",
            command=self._on_disconnect,
        )
        self._btn_disconnect.pack(side="left")

    # ── Slave Panel ────────────────────────────────────────────────────────────

    def _build_slave_panel(self, parent):
        self._slave_panel = ctk.CTkScrollableFrame(parent, label_text="Device State (Slave)")
        # packed/hidden in _on_sim_mode_change

        s = self.device_state

        # Node address
        node_row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
        node_row.pack(fill="x", padx=6, pady=3)
        ctk.CTkLabel(node_row, text="Node Address:", width=120, anchor="w").pack(side="left")
        self._node_addr = ctk.StringVar(value=str(s.node_address))
        ctk.CTkOptionMenu(
            node_row, variable=self._node_addr,
            values=[str(i) for i in range(16)],
            command=lambda v: setattr(self.device_state, "node_address", int(v)),
            width=60,
        ).pack(side="left", padx=4)

        # Toggle switches
        self._toggles: dict[str, ctk.BooleanVar] = {}
        toggle_defs = [
            ("Online",           "online"),
            ("Reset Flag",       "reset_flag"),
            ("Simulate Fault",   None),       # handled separately
            ("Leak 1",           "leak_1"),
            ("Leak 2",           "leak_2"),
            ("PWM Bank 1 OVL",   "pwm_bank1_overload"),
            ("PWM Bank 2 OVL",   "pwm_bank2_overload"),
            ("PWM Bank 3 OVL",   "pwm_bank3_overload"),
            ("Analog Pwr OVL",   "analog_power_overload"),
        ]
        for label, attr in toggle_defs:
            var = ctk.BooleanVar(value=getattr(s, attr, False) if attr else False)
            self._toggles[label] = var
            row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(row, text=label, anchor="w").pack(side="left", expand=True, fill="x")
            _attr = attr

            def _make_cb(a, v):
                def cb():
                    if a:
                        setattr(self.device_state, a, v.get())
                return cb

            ctk.CTkSwitch(
                row, variable=var, text="", width=46,
                onvalue=True, offvalue=False,
                command=_make_cb(_attr, var),
            ).pack(side="right")

        ctk.CTkLabel(self._slave_panel, text="Analog Inputs (AIN 0–7)",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(8, 2))

        self._ain_vars: list[ctk.IntVar] = []
        for i in range(8):
            ain_row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
            ain_row.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(ain_row, text=f"AIN {i}:", width=50, anchor="w").pack(side="left")
            var = ctk.IntVar(value=s.analog_inputs[i])
            self._ain_vars.append(var)

            slider = ctk.CTkSlider(
                ain_row, from_=0, to=65535, number_of_steps=1000,
                variable=var, width=120,
                command=lambda v, idx=i: self._on_ain_change(idx, int(v))
            )
            slider.pack(side="left", padx=4)

            val_label = ctk.CTkLabel(ain_row, text="0", width=50)
            val_label.pack(side="left")

            def _bind(v=var, lbl=val_label):
                v.trace_add("write", lambda *_: lbl.configure(text=str(v.get())))

            _bind()

        # Board health
        ctk.CTkLabel(self._slave_panel, text="Board Health",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(8, 2))

        temp_row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
        temp_row.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(temp_row, text="Temp (°C):", width=90, anchor="w").pack(side="left")
        self._temp_var = ctk.StringVar(value=f"{(s.board_temp_raw / 100) - 100:.1f}")
        temp_entry = ctk.CTkEntry(temp_row, textvariable=self._temp_var, width=70)
        temp_entry.pack(side="left", padx=4)
        temp_entry.bind("<Return>", self._on_temp_change)
        temp_entry.bind("<FocusOut>", self._on_temp_change)

        volt_row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
        volt_row.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(volt_row, text="Voltage (V):", width=90, anchor="w").pack(side="left")
        self._volt_var = ctk.StringVar(value=f"{s.board_voltage_raw / 100:.2f}")
        volt_entry = ctk.CTkEntry(volt_row, textvariable=self._volt_var, width=70)
        volt_entry.pack(side="left", padx=4)
        volt_entry.bind("<Return>", self._on_volt_change)
        volt_entry.bind("<FocusOut>", self._on_volt_change)

        # Reply delay
        delay_row = ctk.CTkFrame(self._slave_panel, fg_color="transparent")
        delay_row.pack(fill="x", padx=6, pady=(8, 4))
        ctk.CTkLabel(delay_row, text="Reply Delay:", width=90, anchor="w").pack(side="left")
        self._delay_var = ctk.StringVar(value=str(s.reply_delay_100us))
        delay_entry = ctk.CTkEntry(delay_row, textvariable=self._delay_var, width=50)
        delay_entry.pack(side="left", padx=4)
        ctk.CTkLabel(delay_row, text="× 100µs", text_color="gray").pack(side="left")
        delay_entry.bind("<Return>", self._on_delay_change)
        delay_entry.bind("<FocusOut>", self._on_delay_change)

    # ── Master Panel ───────────────────────────────────────────────────────────

    def _build_master_panel(self, parent):
        self._master_panel = ctk.CTkScrollableFrame(parent, label_text="Commands (Master)")
        # hidden until Master mode selected

        ctk.CTkLabel(self._master_panel, text="Target Node Address:",
                     anchor="w").pack(fill="x", padx=6, pady=(6, 2))
        self._master_node = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            self._master_panel, variable=self._master_node,
            values=[str(i) for i in range(16)], width=80,
        ).pack(anchor="w", padx=6, pady=(0, 8))

        ctk.CTkLabel(self._master_panel, text="Type C Commands",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(0, 4))

        type_c_cmds = [
            ("Version Info",       self._cmd_version_info),
            ("Reset Flag",         self._cmd_reset_flag),
            ("DIP Switch Query",   self._cmd_dip_switch),
            ("Reset Outputs",      self._cmd_reset_outputs),
            ("Status Flags",       self._cmd_status_flags),
        ]
        for label, cmd in type_c_cmds:
            ctk.CTkButton(
                self._master_panel, text=label,
                command=cmd, height=30,
            ).pack(fill="x", padx=6, pady=2)

        ctk.CTkLabel(self._master_panel, text="Type AB (Minimal)",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=6, pady=(10, 4))

        ctk.CTkButton(
            self._master_panel, text="Send AB (All OFF)",
            command=self._cmd_ab_all_off, height=30,
        ).pack(fill="x", padx=6, pady=2)

        ctk.CTkButton(
            self._master_panel, text="Send AB (All ON)",
            command=self._cmd_ab_all_on, height=30,
        ).pack(fill="x", padx=6, pady=2)

    # ── Log Panel ──────────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(header, text="Command / Response Log",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        # Stats label
        self._stats_label = ctk.CTkLabel(header, text="RX: 0  TX: 0  CRC Err: 0",
                                          font=ctk.CTkFont(size=11), text_color="gray")
        self._stats_label.pack(side="left", padx=16)

        ctk.CTkButton(
            header, text="Clear", width=70, height=26,
            fg_color="transparent", border_width=1,
            command=self._clear_log,
        ).pack(side="right")

        ctk.CTkButton(
            header, text="Save Log", width=80, height=26,
            fg_color="transparent", border_width=1,
            command=self._save_log,
        ).pack(side="right", padx=(0, 6))

        self._log = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            wrap="none",
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._log._textbox.tag_config("rx",   foreground="#9cdcfe")
        self._log._textbox.tag_config("tx",   foreground="#b5cea8")
        self._log._textbox.tag_config("info", foreground="#ce9178")
        self._log._textbox.tag_config("err",  foreground="#f48771")

    # ── Event Handlers ─────────────────────────────────────────────────────────

    def _on_sim_mode_change(self, value: str):
        if value == SLAVE_MODE:
            self._master_panel.pack_forget()
            self._slave_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        else:
            self._slave_panel.pack_forget()
            self._master_panel.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def _on_transport_change(self, value: str):
        if value == "TCP":
            self._serial_frame.pack_forget()
            self._tcp_frame.pack(fill="x", padx=10, pady=2)
        else:
            self._tcp_frame.pack_forget()
            self._serial_frame.pack(fill="x", padx=10, pady=2)

    def _on_connect(self):
        transport = self._transport.get()
        if transport == "TCP":
            try:
                port = int(self._tcp_port.get())
            except ValueError:
                self.log_message("Invalid port number.", "err")
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

    def _on_ain_change(self, idx: int, value: int):
        self.device_state.analog_inputs[idx] = value

    def _on_temp_change(self, _event=None):
        try:
            deg_c = float(self._temp_var.get())
            self.device_state.board_temp_raw = int((deg_c + 100) * 100)
        except ValueError:
            pass

    def _on_volt_change(self, _event=None):
        try:
            volts = float(self._volt_var.get())
            self.device_state.board_voltage_raw = int(volts * 100)
        except ValueError:
            pass

    def _on_delay_change(self, _event=None):
        try:
            self.device_state.reply_delay_100us = int(self._delay_var.get())
        except ValueError:
            pass

    def _on_conn_state_change(self, state: ConnectionState):
        """Called from comms thread — must use root.after to update GUI safely."""
        def _update():
            colour = STATUS_COLOURS.get(state, "#e05252")
            label  = STATUS_LABELS.get(state, "⬤  Unknown")
            self._status_label.configure(text=label, text_color=colour)
        self.root.after(0, _update)

    def _on_log(self, message: str, tag: str):
        """Called from comms thread."""
        self.root.after(0, lambda: self._do_log(message, tag))
        self.root.after(0, self._refresh_stats)

    def _on_close(self):
        self._conn_mgr.stop()
        self._save_config()
        self.root.destroy()

    # ── Master Mode Commands ───────────────────────────────────────────────────

    def _master_send(self, telegram: bytes):
        """In master mode send a telegram directly via the connection."""
        # Master mode: the connection manager acts as client, not server.
        # For now log the outgoing bytes — full master TX implementation in Phase 5.
        self.log_message(f"MASTER TX  {telegram.hex().upper()}", "tx")
        self.log_message("(Master TX to hardware — connect via TCP/Serial to target device)", "info")

    def _cmd_version_info(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        node = int(self._master_node.get())
        self._master_send(build_master_type_c(node, TypeCCmd.VERSION_INFO))

    def _cmd_reset_flag(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        node = int(self._master_node.get())
        self._master_send(build_master_type_c(node, TypeCCmd.RESET_FLAG))

    def _cmd_dip_switch(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        node = int(self._master_node.get())
        self._master_send(build_master_type_c(node, TypeCCmd.DIP_SWITCH))

    def _cmd_reset_outputs(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        node = int(self._master_node.get())
        self._master_send(build_master_type_c(node, TypeCCmd.RESET_OUTPUTS))

    def _cmd_status_flags(self):
        from simulator.telegram import build_master_type_c, TypeCCmd
        node = int(self._master_node.get())
        self._master_send(build_master_type_c(node, TypeCCmd.STATUS_FLAGS))

    def _cmd_ab_all_off(self):
        from simulator.telegram import build_master_type_ab
        node = int(self._master_node.get())
        self._master_send(build_master_type_ab(
            node_address=node, type_a=0x80, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\x00\x00\x00"
        ))

    def _cmd_ab_all_on(self):
        from simulator.telegram import build_master_type_ab
        node = int(self._master_node.get())
        self._master_send(build_master_type_ab(
            node_address=node, type_a=0x80, type_b=0x00,
            pwm_freq=0x0F, analog_power_outputs=b"\xFF\xFF\xFF"
        ))

    # ── Log helpers ────────────────────────────────────────────────────────────

    def log_message(self, message: str, tag: str = "info"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"

        def _insert():
            self._log.configure(state="normal")
            self._log._textbox.insert("end", line, tag)
            self._log._textbox.see("end")
            self._log.configure(state="disabled")

        self.root.after(0, _insert)

    def _do_log(self, message: str, tag: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"
        self._log.configure(state="normal")
        self._log._textbox.insert("end", line, tag)
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
                content = self._log._textbox.get("1.0", "end")
                with open(path, "w") as f:
                    f.write(content)
                self.log_message(f"Log saved to {path}", "info")
            except Exception as e:
                self.log_message(f"Failed to save log: {e}", "err")

    def _refresh_stats(self):
        m = self._conn_mgr
        self._stats_label.configure(
            text=f"RX: {m.rx_count}  TX: {m.tx_count}  CRC Err: {m.crc_errors}"
        )

    # ── Config & helpers ───────────────────────────────────────────────────────

    def _refresh_available_ports(self):
        """Populate the COM port dropdown with available ports."""
        ports = SerialServer.list_ports()
        if not ports:
            ports = [f"COM{i}" for i in range(1, 9)]
        self._port_menu.configure(values=ports)
        if self._serial_port.get() not in ports and ports:
            self._serial_port.set(ports[0])

    def _make_device_state(self) -> DeviceState:
        d = self._cfg.device
        state = DeviceState(
            node_address      = d.node_address,
            online            = d.online,
            reset_flag        = d.reset_flag,
            reply_delay_100us = d.reply_delay_100us,
            board_temp_raw    = d.board_temp_raw,
            board_voltage_raw = d.board_voltage_raw,
        )
        return state

    def _save_config(self):
        self._cfg.connection.mode           = self._transport.get().split()[0]
        self._cfg.connection.tcp.host       = self._tcp_host.get()
        try:
            self._cfg.connection.tcp.port   = int(self._tcp_port.get())
        except ValueError:
            pass
        self._cfg.connection.serial.port      = self._serial_port.get()
        try:
            self._cfg.connection.serial.baud_rate = int(self._baud_rate.get())
        except ValueError:
            pass
        self._cfg.device.node_address       = self.device_state.node_address
        self._cfg.device.reply_delay_100us  = self.device_state.reply_delay_100us
        self._cfg.device.board_temp_raw     = self.device_state.board_temp_raw
        self._cfg.device.board_voltage_raw  = self.device_state.board_voltage_raw
        cfg_module.save(self._cfg)

    def run(self):
        self.log_message("Kyst Simulator started.", "info")
        self.log_message("Select mode and transport, then click Connect.", "info")
        self.root.mainloop()
