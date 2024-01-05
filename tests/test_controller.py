import pytest

from controller import decode_int8, decode_int16, encode_int8, encode_int16


def test_int8_round_trip():
    for value in (0, 1, 127, 255):
        assert decode_int8(encode_int8(value)) == value


def test_int16_round_trip_is_little_endian():
    assert encode_int16(0x1234) == b"\x34\x12"
    for value in (0, 1, 255, 256, 65535):
        assert decode_int16(encode_int16(value)) == value


def test_encoders_clamp_out_of_range_values():
    assert encode_int8(-5) == b"\x00"
    assert encode_int8(300) == b"\xff"
    assert encode_int16(70000) == b"\xff\xff"


def test_decoders_reject_short_data():
    with pytest.raises(ValueError):
        decode_int8(b"")
    with pytest.raises(ValueError):
        decode_int16(b"\x01")
