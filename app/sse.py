from __future__ import annotations

import json
import threading
from collections import defaultdict
from queue import Queue, Empty
from typing import Any, Dict


class MessageBroker:
    """Simple in-memory pub-sub broker for SSE streaming."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, list[Queue]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, session_id: str) -> Queue:
        queue: Queue = Queue()
        with self._lock:
            self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: Queue) -> None:
        with self._lock:
            if session_id in self._subscribers and queue in self._subscribers[session_id]:
                self._subscribers[session_id].remove(queue)
            if session_id in self._subscribers and not self._subscribers[session_id]:
                del self._subscribers[session_id]

    def publish(self, message: dict[str, Any]) -> None:
        session_id = message.get("session_id")
        if not session_id:
            return
        with self._lock:
            queues = list(self._subscribers.get(session_id, []))
        for queue in queues:
            queue.put_nowait(message)

    @staticmethod
    def format_sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


broker = MessageBroker()