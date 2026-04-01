"""
Kyst Simulator — Serial Server
Listens on a COM port for commands from the PLC.
Placeholder — implementation to follow once protocol details are confirmed.
"""

import threading
import logging

logger = logging.getLogger(__name__)


class SerialServer:
    def __init__(self, port: str = "COM1", baud_rate: int = 9600, on_receive=None):
        """
        :param port: COM port (e.g. 'COM1', 'COM3')
        :param baud_rate: Serial baud rate
        :param on_receive: callback(data: bytes) -> bytes
        """
        self.port = port
        self.baud_rate = baud_rate
        self.on_receive = on_receive
        self._serial = None
        self._running = False
        self._thread = None

    def start(self):
        try:
            import serial
        except ImportError:
            logger.error("pyserial not installed. Run: pip install pyserial")
            return

        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        logger.info(f"Serial server started on {self.port} @ {self.baud_rate} baud")

    def stop(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("Serial server stopped")

    def _serve(self):
        import serial

        try:
            self._serial = serial.Serial(
                self.port, self.baud_rate, timeout=1.0
            )
        except serial.SerialException as e:
            logger.error(f"Could not open {self.port}: {e}")
            return

        while self._running:
            try:
                data = self._serial.read(1024)
                if data:
                    logger.debug(f"RX serial: {data.hex()}")
                    if self.on_receive:
                        response = self.on_receive(data)
                        if response:
                            self._serial.write(response)
                            logger.debug(f"TX serial: {response.hex()}")
            except Exception as e:
                if self._running:
                    logger.error(f"Serial error: {e}")
                break
