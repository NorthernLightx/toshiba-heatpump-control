import asyncio
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class SSEBroadcaster:
    def __init__(self) -> None:
        self._clients: list[asyncio.Queue[str]] = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._clients.append(queue)
        try:
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self._clients:
                self._clients.remove(queue)

    async def broadcast(self, event: str, data: dict) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        self._send_to_clients(payload)

    async def send_heartbeat(self) -> None:
        self._send_to_clients(": heartbeat\n\n")

    def _send_to_clients(self, payload: str) -> None:
        disconnected = []
        for queue in self._clients:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                disconnected.append(queue)
        for queue in disconnected:
            self._clients.remove(queue)

    @property
    def client_count(self) -> int:
        return len(self._clients)


broadcaster = SSEBroadcaster()
