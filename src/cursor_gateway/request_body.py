"""Decode bounded HTTP request bodies, including Codex's Zstandard compression."""

import zlib
from compression import zstd

from .translate import RequestError


def decode_body(raw: bytes | bytearray, encoding: str, limit: int) -> bytes | bytearray:
    encoding = encoding.strip().lower()
    if encoding in ("", "identity"):
        return raw
    if encoding not in ("gzip", "zstd"):
        raise RequestError(
            "supported Content-Encoding values are identity, gzip and zstd",
            status=415,
            param="Content-Encoding",
            code="unsupported_content_encoding",
        )
    try:
        decoder = zstd.ZstdDecompressor() if encoding == "zstd" else zlib.decompressobj(31)
        decoded = decoder.decompress(raw, limit + 1)
        if len(decoded) > limit:
            raise RequestError("decompressed request body too large", status=413, param="body")
        # A request contains one complete compressed frame, without trailing junk.
        if not decoder.eof or decoder.unused_data:
            raise RequestError(f"invalid or incomplete {encoding} request body", param="body")
        return decoded
    except zlib.error, zstd.ZstdError:
        raise RequestError(f"invalid {encoding} request body", param="body") from None
