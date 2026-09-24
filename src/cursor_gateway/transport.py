"""One HTTP/2 stream per connection, with full duplex writes and SOCKS5 support.

Run keeps the request body open while receiving replies. A dedicated reader drives
HTTP/2 flow control even while the caller is waiting to send a large history blob.
"""

import asyncio
import contextlib
import ipaddress
import ssl
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import h2.config
import h2.connection
import h2.events
import h2.exceptions

MAX_BUFFER_BYTES = 64 * 1024 * 1024


class TransportError(Exception):
    """An upstream connection could not complete the protocol exchange."""


async def _socks_handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    host: str,
    port: int,
    proxy_url: str,
) -> None:
    proxy = urlsplit(proxy_url)
    authenticated = proxy.username is not None
    writer.write(b"\x05\x02\x00\x02" if authenticated else b"\x05\x01\x00")
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != 5 or method not in ({0, 2} if authenticated else {0}):
        raise TransportError("SOCKS5 proxy rejected authentication methods")
    if method == 2:
        username = unquote(proxy.username or "").encode()
        password = unquote(proxy.password or "").encode()
        if not (0 < len(username) <= 255 and 0 < len(password) <= 255):
            raise TransportError("SOCKS5 username/password must contain 1–255 bytes")
        writer.write(
            b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password
        )
        await writer.drain()
        if await reader.readexactly(2) != b"\x01\x00":
            raise TransportError("SOCKS5 authentication failed")
    try:
        ip = ipaddress.ip_address(host)
        address = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
    except ValueError:
        hostname = host.encode("idna")
        if len(hostname) > 255:
            raise TransportError("SOCKS5 destination hostname is too long") from None
        # Hostnames are resolved by the proxy for both socks5 and socks5h.
        address = b"\x03" + bytes([len(hostname)]) + hostname
    writer.write(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    await writer.drain()
    version, status, reserved, kind = await reader.readexactly(4)
    if version != 5 or reserved != 0 or status != 0:
        raise TransportError(f"SOCKS5 CONNECT rejected (status {status})")
    if kind == 1:
        length = 4
    elif kind == 4:
        length = 16
    elif kind == 3:
        length = (await reader.readexactly(1))[0]
    else:
        raise TransportError("SOCKS5 proxy returned an invalid address type")
    await reader.readexactly(length + 2)


class H2Stream:
    def __init__(
        self,
        base_url: str,
        path: str,
        headers: dict[str, str],
        *,
        method: str = "POST",
        proxy_url: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.path = path
        self.headers = headers
        self.method = method
        self.proxy_url = proxy_url
        self.connection = h2.connection.H2Connection(
            config=h2.config.H2Configuration(client_side=True, header_encoding="utf-8")
        )
        self.stream_id = 1
        self.writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._headers: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
        self._incoming: asyncio.Queue[bytes | Exception | None] = asyncio.Queue()
        self._window = asyncio.Event()
        self._failure: Exception | None = None
        self._ended = False
        self._buffered = 0
        self.trailers: dict[str, str] = {}

    async def __aenter__(self) -> H2Stream:
        url = urlsplit(self.base_url)
        if url.scheme not in {"https", "http"} or not url.hostname:
            raise TransportError("invalid HTTP/2 origin")
        host = url.hostname
        port = url.port or (443 if url.scheme == "https" else 80)
        tls = ssl.create_default_context() if url.scheme == "https" else None
        if tls:
            tls.set_alpn_protocols(["h2"])
        try:
            if self.proxy_url:
                proxy = urlsplit(self.proxy_url)
                if proxy.scheme not in {"socks5", "socks5h"} or not proxy.hostname:
                    raise TransportError("expected a SOCKS5 proxy URL")
                reader, self.writer = await asyncio.open_connection(
                    proxy.hostname, proxy.port or 1080
                )
                await _socks_handshake(reader, self.writer, host, port, self.proxy_url)
                if tls:
                    await self.writer.start_tls(tls, server_hostname=host)
            else:
                reader, self.writer = await asyncio.open_connection(
                    host,
                    port,
                    ssl=tls,
                    server_hostname=host if tls else None,
                )
            if tls:
                secured = self.writer.get_extra_info("ssl_object")
                if not secured or secured.selected_alpn_protocol() != "h2":
                    raise TransportError("upstream did not negotiate HTTP/2 via ALPN")
            self.connection.initiate_connection()
            self.connection.send_headers(
                self.stream_id,
                [
                    (":method", self.method),
                    (":scheme", url.scheme),
                    (":authority", url.netloc),
                    (":path", self.path),
                    *[(key.lower(), value) for key, value in self.headers.items()],
                ],
            )
            self._flush()
            await self.writer.drain()
            self._reader_task = asyncio.create_task(self._read(reader), name="cursor-h2-reader")
            return self
        except BaseException:
            await self.aclose()
            raise

    def _flush(self) -> None:
        data = self.connection.data_to_send()
        if data and self.writer:
            self.writer.write(data)

    async def _read(self, reader: asyncio.StreamReader) -> None:
        try:
            while not self._ended:
                data = await reader.read(65536)
                if not data:
                    raise TransportError("upstream closed the HTTP/2 connection prematurely")
                for event in self.connection.receive_data(data):
                    if isinstance(event, h2.events.ResponseReceived):
                        if not self._headers.done():
                            self._headers.set_result(dict(event.headers))
                    elif isinstance(event, h2.events.TrailersReceived):
                        self.trailers.update(event.headers)
                    elif isinstance(event, h2.events.DataReceived):
                        self.connection.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                        self._buffered += len(event.data)
                        if self._buffered > MAX_BUFFER_BYTES:
                            raise TransportError("upstream response buffer limit exceeded")
                        self._incoming.put_nowait(event.data)
                    elif isinstance(event, h2.events.WindowUpdated):
                        self._window.set()
                    elif isinstance(event, h2.events.RemoteSettingsChanged):
                        self._window.set()
                    elif isinstance(event, h2.events.StreamEnded):
                        self._ended = True
                        self._window.set()
                        self._incoming.put_nowait(None)
                    elif isinstance(event, h2.events.StreamReset):
                        raise TransportError(f"upstream reset HTTP/2 stream ({event.error_code})")
                    elif isinstance(event, h2.events.ConnectionTerminated) and not self._ended:
                        raise TransportError(
                            f"upstream closed HTTP/2 connection ({event.error_code})"
                        )
                self._flush()
                if not self._ended and self.writer:
                    await self.writer.drain()
        except Exception as exc:
            self._failure = exc
            self._incoming.put_nowait(exc)
            # Store the exception separately to avoid unobserved Future exceptions
            # when cancellation happens before response_headers() is awaited.
            if not self._headers.done():
                self._headers.set_result({})
        finally:
            self._window.set()

    async def send(self, data: bytes, *, end_stream: bool = False) -> None:
        if not self.writer:
            raise TransportError("HTTP/2 stream is not open")
        offset = 0
        while offset < len(data):
            self._window.clear()
            if self._failure:
                raise self._failure
            if self._ended:
                raise TransportError("upstream ended the stream while sending")
            size = min(
                self.connection.local_flow_control_window(self.stream_id),
                self.connection.max_outbound_frame_size,
                len(data) - offset,
            )
            if size <= 0:
                await self._window.wait()
                continue
            self.connection.send_data(
                self.stream_id,
                data[offset : offset + size],
                end_stream=end_stream and offset + size == len(data),
            )
            offset += size
            self._flush()
            await self.writer.drain()
        if not data and end_stream:
            self.connection.end_stream(self.stream_id)
            self._flush()
            await self.writer.drain()

    async def response_headers(self) -> dict[str, str]:
        headers = await self._headers
        if not headers and self._failure:
            raise self._failure
        return headers

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        item = await self._incoming.get()
        if item is None:
            raise StopAsyncIteration
        if isinstance(item, Exception):
            raise item
        self._buffered -= len(item)
        return item

    async def aclose(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self.writer:
            with contextlib.suppress(Exception):
                if not self._ended:
                    self.connection.reset_stream(self.stream_id, error_code=8)
                self.connection.close_connection()
                self._flush()
            self.writer.close()
            with contextlib.suppress(Exception):
                async with asyncio.timeout(1):
                    await self.writer.wait_closed()

    async def __aexit__(self, *args) -> None:
        await self.aclose()


@dataclass(slots=True)
class H2Response:
    status: int
    headers: dict[str, str]
    body: bytes


async def h2_request(
    base_url: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    method: str = "POST",
    proxy_url: str | None = None,
    timeout: float = 20,
) -> H2Response:
    async with asyncio.timeout(timeout):
        async with H2Stream(
            base_url,
            path,
            headers or {},
            method=method,
            proxy_url=proxy_url,
        ) as stream:
            await stream.send(body, end_stream=True)
            response_headers = await stream.response_headers()
            chunks = bytearray()
            async for chunk in stream:
                chunks.extend(chunk)
                if len(chunks) > MAX_BUFFER_BYTES:
                    raise TransportError("upstream response is too large")
            return H2Response(
                status=int(response_headers.get(":status", 0)),
                headers=response_headers,
                body=bytes(chunks),
            )
