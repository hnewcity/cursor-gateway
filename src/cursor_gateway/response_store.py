"""Bounded, process-local Responses history. Stored snapshots never alias live requests."""

import json
import time
from collections import OrderedDict
from collections.abc import Callable

from .protocol import json_bytes
from .translate import RequestError


class ResponseStore:
    def __init__(
        self,
        *,
        ttl: int = 3600,
        max_entries: int = 256,
        max_bytes: int = 128 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl, self.max_entries, self.max_bytes = ttl, max_entries, max_bytes
        self.clock = clock
        self._entries: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._bytes = 0

    def _remove(self, response_id: str) -> None:
        _, data = self._entries.pop(response_id)
        self._bytes -= len(data)

    def _expire(self) -> None:
        now = self.clock()
        for response_id, (deadline, _) in list(self._entries.items()):
            if deadline <= now:
                self._remove(response_id)

    def put(self, response: dict, input_items: list[dict]) -> None:
        data = json_bytes({"response": response, "input": input_items})
        if len(data) > self.max_bytes:
            raise RequestError(
                "response exceeds the history cache size limit; use store=false "
                "or increase CURSOR_DIRECT_RESPONSE_CACHE_BYTES",
                status=413,
            )
        self._expire()
        response_id = response["id"]
        if response_id in self._entries:
            self._remove(response_id)
        while self._entries and (
            len(self._entries) >= self.max_entries or self._bytes + len(data) > self.max_bytes
        ):
            self._remove(next(iter(self._entries)))
        self._entries[response_id] = (self.clock() + self.ttl, data)
        self._bytes += len(data)

    def get(self, response_id: str, *, param: str = "response_id") -> dict:
        self._expire()
        entry = self._entries.get(response_id)
        if entry is None:
            raise RequestError(
                "response not found; it may be expired, evicted, deleted, "
                "created with store=false, or held by another server process",
                status=404,
                param=param,
                code="response_not_found",
            )
        self._entries.move_to_end(response_id)
        return json.loads(entry[1])

    def delete(self, response_id: str) -> None:
        self.get(response_id)
        self._remove(response_id)
