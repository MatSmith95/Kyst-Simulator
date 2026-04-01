"""
D2-Bus CRC Engine
8-bit CRC, polynomial 0x8D (x8 + x7 + x3 + x2 + x1)
Table generated algorithmically — verified against the lookup table in the AE99 protocol manual.
"""


def _generate_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x8D) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        table.append(crc)
    return table


CRC_TABLE: list[int] = _generate_table()


def calculate(data: bytes) -> int:
    """
    Calculate 8-bit D2-Bus CRC over a sequence of bytes.
    CRC is initialised to 0 and updated byte by byte.

    :param data: bytes to calculate CRC over (must exclude the CRC byte itself)
    :return: calculated CRC byte (0x00–0xFF)
    """
    crc = 0
    for byte in data:
        crc = CRC_TABLE[crc ^ byte]
    return crc


def verify(telegram: bytes) -> bool:
    """
    Verify the CRC of a complete telegram (last byte is the CRC).

    :param telegram: full telegram bytes including trailing CRC byte
    :return: True if CRC is valid
    """
    if len(telegram) < 2:
        return False
    return calculate(telegram[:-1]) == telegram[-1]


def append(data: bytes) -> bytes:
    """Return data with the correct CRC byte appended."""
    return data + bytes([calculate(data)])
