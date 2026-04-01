"""
Kyst Simulator — TCP Server (Slave Mode)

Listens for incoming TCP connections from the PLC (master).
Each connected client is handled in its own thread.
Multiple clients are supported — each receives the response from the serial device.
"""

from __future__ import annotations
import socket
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TCPServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4001,
        on_receive: Callable[[bytes], bytes | None] | None = None,
        on_client_connect: Callable[[tuple], None] | None = None,
        on_client_disconnect: Callable[[tuple], None] | None = None,
    ):
        """
        :param host:                 IP address to bind (0.0.0.0 = all interfaces)
        :param port:                 TCP port to listen on
        :param on_receive:           callback(data) -> response | None
        :param on_client_connect:    callback(addr) when a client connects
        :param on_client_disconnect: callback(addr) when a client disconnects
        """
        self.host                  = host
        self.port                  = port
        self.on_receive            = on_receive
        self.on_client_connect     = on_client_connect
        self.on_client_disconnect  = on_client_disconnect

        self._server_socket: socket.socket | None = None
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self._clients: list[socket.socket] = []
        self._clients_lock = threading.Lock()

    def start(self) -> None:
        """Bind and start accepting connections. Raises on bind failure."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)
        self._running = True

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        logger.info(f"TCP server listening on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stop accepting connections and close all active clients."""
        self._running = False

        # Close all client sockets
        with self._clients_lock:
            for client in self._clients:
                try:
                    client.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        logger.info("TCP server stopped")

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                logger.info(f"TCP client connected: {addr}")

                with self._clients_lock:
                    self._clients.append(conn)

                if self.on_client_connect:
                    self.on_client_connect(addr)

                t = threading.Thread(
                    target=self._client_loop,
                    args=(conn, addr),
                    daemon=True
                )
                t.start()

            except socket.timeout:
                continue
            except OSError:
                # Socket was closed — expected during stop()
                break
            except Exception as e:
                if self._running:
                    logger.error(f"Accept error: {e}")

    def _client_loop(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single connected client."""
        conn.settimeout(5.0)
        try:
            while self._running:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break   # client disconnected cleanly

                    response = None
                    if self.on_receive:
                        response = self.on_receive(data)

                    if response:
                        try:
                            conn.sendall(response)
                        except Exception as e:
                            logger.warning(f"Send error to {addr}: {e}")
                            break

                except socket.timeout:
                    continue
                except ConnectionResetError:
                    break
                except Exception as e:
                    if self._running:
                        logger.error(f"Client loop error ({addr}): {e}")
                    break
        finally:
            with self._clients_lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            try:
                conn.close()
            except Exception:
                pass

            logger.info(f"TCP client disconnected: {addr}")
            if self.on_client_disconnect:
                self.on_client_disconnect(addr)
