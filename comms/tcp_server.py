"""
Kyst Simulator — TCP Server
Listens for incoming TCP connections from the PLC.
Passes received data to the simulator engine and sends back the response.
"""

import socket
import threading
import logging

logger = logging.getLogger(__name__)


class TCPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 4001, on_receive=None):
        """
        :param host: IP to listen on (0.0.0.0 = all interfaces)
        :param port: TCP port to listen on
        :param on_receive: callback(data: bytes) -> bytes  — called with raw received bytes,
                           should return the response bytes to send back
        """
        self.host = host
        self.port = port
        self.on_receive = on_receive
        self._server_socket = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        logger.info(f"TCP server started on {self.host}:{self.port}")

    def stop(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        logger.info("TCP server stopped")

    def _serve(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        while self._running:
            try:
                conn, addr = self._server_socket.accept()
                logger.info(f"Client connected: {addr}")
                client_thread = threading.Thread(
                    target=self._handle_client, args=(conn, addr), daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Server error: {e}")

    def _handle_client(self, conn: socket.socket, addr):
        with conn:
            conn.settimeout(30.0)
            while self._running:
                try:
                    data = conn.recv(1024)
                    if not data:
                        logger.info(f"Client disconnected: {addr}")
                        break
                    logger.debug(f"RX from {addr}: {data.hex()}")

                    if self.on_receive:
                        response = self.on_receive(data)
                        if response:
                            conn.sendall(response)
                            logger.debug(f"TX to {addr}: {response.hex()}")
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Client handler error ({addr}): {e}")
                    break
