# -*- coding: utf-8 -*-
from __future__ import print_function

import threading
import time
from collections import OrderedDict


class SessionStore(object):
    """线程安全的会话 LRU/TTL 存储，保留消息列表引用语义。"""

    MAX_SESSIONS = 50
    SESSION_TTL_SEC = 30 * 60

    def __init__(self):
        self._lock = threading.Lock()
        self._data = OrderedDict()

    def get_or_init(self, key, init_fn):
        now = time.monotonic()
        with self._lock:
            if key in self._data:
                messages, _ = self._data[key]
                self._data[key] = (messages, now)
            else:
                messages = init_fn()
                self._data[key] = (messages, now)
            self._data.move_to_end(key)
            self._evict_locked(now)
            return messages

    def set(self, key, messages):
        now = time.monotonic()
        with self._lock:
            self._data[key] = (messages, now)
            self._data.move_to_end(key)
            self._evict_locked(now)

    def reset(self):
        with self._lock:
            self._data.clear()

    def _evict_locked(self, now):
        while self._data:
            _, (_, last_access) = next(iter(self._data.items()))
            if now - last_access <= self.SESSION_TTL_SEC:
                break
            self._data.popitem(last=False)
        while len(self._data) > self.MAX_SESSIONS:
            self._data.popitem(last=False)
