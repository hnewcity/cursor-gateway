"""Connect framing and google.protobuf.Value decoding."""

import json
import math
import zlib
from dataclasses import dataclass
from typing import Any

from google.protobuf.message import DecodeError
from google.protobuf.struct_pb2 import Value

MAX_FRAME_BYTES = 64 * 1024 * 1024


class ProtocolError(Exception):
    pass


def json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def connect_frame(payload: bytes, flags: int = 0) -> bytes:
    return bytes([flags]) + len(payload).to_bytes(4, "big") + payload


@dataclass(slots=True)
class Frame:
    payload: bytes
    end_stream: bool = False


class FrameDecoder:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 5:
            flags, length = self.buffer[0], int.from_bytes(self.buffer[1:5], "big")
            if flags & ~3:
                raise ProtocolError(f"unknown Connect frame flags: {flags}")
            if length > MAX_FRAME_BYTES:
                raise ProtocolError("Connect frame size limit exceeded")
            if len(self.buffer) < length + 5:
                break
            payload = bytes(self.buffer[5 : 5 + length])
            del self.buffer[: 5 + length]
            if flags & 1:
                try:
                    decoder = zlib.decompressobj(wbits=31)
                    payload = decoder.decompress(payload, MAX_FRAME_BYTES + 1)
                    if len(payload) > MAX_FRAME_BYTES or decoder.unconsumed_tail:
                        raise ProtocolError("decompressed Connect frame is too large")
                    if not decoder.eof or decoder.unused_data:
                        raise ProtocolError("invalid gzip Connect frame")
                except zlib.error:
                    raise ProtocolError("invalid gzip Connect frame") from None
            frames.append(Frame(payload, bool(flags & 2)))
        return frames

    def finish(self) -> None:
        if self.buffer:
            raise ProtocolError("upstream ended with an incomplete Connect frame")


def decode_arg_value(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        value = Value.FromString(raw)
    except DecodeError:
        return raw.decode("utf-8", errors="replace")
    return _decode_value(value)


def _decode_value(value: Value) -> Any:
    """Restore JSON integer spelling lost by protobuf's double-only number field."""
    kind = value.WhichOneof("kind")
    if kind in (None, "null_value"):
        return None
    if kind == "number_value":
        number = value.number_value
        if not math.isfinite(number):
            raise ProtocolError("upstream tool argument contains a non-finite number")
        # Rust/serde tools distinguish 180000 from 180000.0, including inside arrays
        # and nested objects. Do not coerce strings or truncate fractional numbers.
        return int(number) if number.is_integer() else number
    if kind == "struct_value":
        return {key: _decode_value(child) for key, child in value.struct_value.fields.items()}
    if kind == "list_value":
        return [_decode_value(child) for child in value.list_value.values]
    return getattr(value, kind)
