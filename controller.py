def decode_int8(data):
    return int.from_bytes(data[0:1], 'little')

def decode_int16(data):
    return int.from_bytes(data[0:2], 'little')

def encode_int8(i):
    return int.to_bytes(i, 1, 'little')

def encode_int16(i):
    return int.to_bytes(i, 2, 'little')