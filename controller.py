"""Binary packet helpers shared by the stream and input sockets.

Every packet starts with a one byte type followed by little-endian fields.
"""

# Packet types
PACKET_FRAME_REQUEST = 0x01  # client -> server (stream socket)
PACKET_FRAME_RESPONSE = 0x02  # server -> client (stream socket)
PACKET_INPUT = 0x03  # client -> server (input socket)

# Frame response body types
FRAME_NOP = 0x00  # nothing changed
FRAME_FULL = 0x01  # whole surface (JPEG)
FRAME_PARTIAL = 0x02  # changed region only (WEBP)


def decode_int8(data):
    if len(data) < 1:
        raise ValueError("not enough data for int8")
    return int.from_bytes(data[0:1], "little")


def decode_int16(data):
    if len(data) < 2:
        raise ValueError("not enough data for int16")
    return int.from_bytes(data[0:2], "little")


def encode_int8(i):
    return int.to_bytes(max(0, min(0xFF, int(i))), 1, "little")


def encode_int16(i):
    return int.to_bytes(max(0, min(0xFFFF, int(i))), 2, "little")
