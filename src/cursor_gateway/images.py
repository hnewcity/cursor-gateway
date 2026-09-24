"""Inline image attachments for Cursor's selected-context protobuf."""

import base64
import binascii
import hashlib
import struct

from .proto import agent_pb2 as pb
from .translate_error import RequestError

IMAGE_TYPES = ("input_image", "image_url")
MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
MAX_IMAGE_BYTES = 16 * 1024 * 1024


def image_url(part: dict) -> str:
    url = part.get("image_url")
    if isinstance(url, dict):
        url = url.get("url")
    if not isinstance(url, str) or not url.startswith("data:image/"):
        raise RequestError(
            "images must use an inline base64 data URL; remote image URLs and file IDs "
            "are not supported",
            param="input",
        )
    return url


def selected_image(part: dict) -> pb.SelectedImage:
    url = image_url(part)
    header, separator, data = url.partition(",")
    mime = header.removeprefix("data:").removesuffix(";base64").lower()
    if not separator or not header.endswith(";base64") or mime not in MIME_TYPES:
        raise RequestError("image must be base64 PNG, JPEG, WebP or GIF", param="input")
    if len(data) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise RequestError("image exceeds 16 MiB", status=413, param="input")
    try:
        decoded = base64.b64decode(data, validate=True)
    except ValueError, binascii.Error:
        raise RequestError("invalid base64 image", param="input") from None
    if not decoded:
        raise RequestError("image data is empty", param="input")
    width = height = 0
    if mime == "image/png" and decoded.startswith(b"\x89PNG\r\n\x1a\n") and len(decoded) >= 24:
        width, height = struct.unpack(">II", decoded[16:24])
    elif mime == "image/gif" and decoded[:6] in (b"GIF87a", b"GIF89a") and len(decoded) >= 10:
        width, height = struct.unpack("<HH", decoded[6:10])
    identifier = hashlib.sha256(decoded).hexdigest()
    image = pb.SelectedImage(
        data=decoded,
        uuid=identifier,
        path=f"input-{identifier[:12]}",
        mime_type=mime,
    )
    if 0 < width <= 65535 and 0 < height <= 65535:
        image.dimension.width, image.dimension.height = width, height
    return image
