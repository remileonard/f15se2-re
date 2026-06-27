def _read_bytes(data: bytes, offset: int, size: int, *, name: str) -> bytes:
    if offset + size > len(data):
        raise ValueError(f"Unexpected end of file while reading {name}")
    return data[offset : offset + size]

def _read_u8(data: bytes, offset: int) -> int:
    return int(_read_bytes(data, offset, 1, name="u8")[0])

def _read_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(_read_bytes(data, offset, 2, name="u16"), "little")

def _read_i16(data: bytes, offset: int) -> int:
    return int.from_bytes(_read_bytes(data, offset, 2, name="i16"), "little", signed=True)

def _is_printable(s: str) -> bool:
    """True when s is a non-empty string containing only printable ASCII."""
    return bool(s) and all(32 <= ord(c) <= 126 for c in s)