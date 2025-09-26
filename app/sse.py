from __future__ import annotations

import json
import threading
from collections import defaultdict
from queue import Queue, Empty
from typing import Any, Dict, Generator, Tuple


SubscriberKey = Tuple[str, str]


class MessageBroker:
    """Simple in-memory pub-sub broker for SSE streaming."""

    def __init__(self) -> None:
        self._subscribers: Dict[SubscriberKey, list[Queue]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, session_id: str, player_id: str) -> Queue:
        queue: Queue = Queue()
        key = (session_id, player_id)
        with self._lock:
            self._subscribers[key].append(queue)
        return queue

    def unsubscribe(self, session_id: str, player_id: str, queue: Queue) -> None:
        key = (session_id, player_id)
        with self._lock:
            if key in self._subscribers and queue in self._subscribers[key]:
                self._subscribers[key].remove(queue)
            if key in self._subscribers and not self._subscribers[key]:
                del self._subscribers[key]

    def publish(self, message: dict[str, Any]) -> None:
        session_id = message.get("session_id")
        player_id = message.get("player_id")
        if not session_id or not player_id:
            return
        key = (session_id, player_id)
        with self._lock:
            queues = list(self._subscribers.get(key, []))
        for queue in queues:
            queue.put_nowait(message)

    @staticmethod
    def format_sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


broker = MessageBroker()