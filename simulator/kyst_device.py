"""
Kyst Simulator — Kyst Device Engine
Processes incoming PLC commands and generates appropriate responses.
Placeholder — response logic to be implemented once protocol details are confirmed.
"""

import logging

logger = logging.getLogger(__name__)


class KystDevice:
    """
    Simulates the behaviour of a Kyst card device.
    Receives raw bytes from the PLC and returns the appropriate response bytes.
    """

    def __init__(self):
        # Device state — toggleable via GUI
        # These will be expanded once protocol details are defined
        self.state = {
            "online": True,
            "simulate_fault": False,
            "auto_respond": True,
        }

    def process(self, data: bytes) -> bytes:
        """
        Process a command received from the PLC.
        :param data: Raw bytes received
        :return: Response bytes to send back, or empty bytes if no response
        """
        logger.debug(f"Processing command: {data.hex()}")

        if not self.state.get("online"):
            logger.debug("Device offline — no response")
            return b""

        if not self.state.get("auto_respond"):
            logger.debug("Auto-respond disabled — no response")
            return b""

        # TODO: Implement Kyst protocol parsing and response generation
        # This will be filled in once the telegram protocol details are provided
        response = self._build_response(data)
        logger.debug(f"Response: {response.hex() if response else 'none'}")
        return response

    def _build_response(self, command: bytes) -> bytes:
        """
        Build a response for a given command.
        Placeholder — to be implemented per Kyst protocol spec.
        """
        # Placeholder: echo back with an ACK byte prepended
        # Replace this with actual Kyst response logic
        if self.state.get("simulate_fault"):
            return b"\x15"  # NAK
        return b"\x06"  # ACK placeholder

    def set_state(self, key: str, value):
        """Update a device state flag."""
        if key in self.state:
            self.state[key] = value
            logger.info(f"Device state updated: {key} = {value}")
