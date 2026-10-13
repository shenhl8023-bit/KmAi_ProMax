import unittest
from unittest import mock

from backend.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    def test_get_or_init_preserves_message_list_reference(self):
        store = SessionStore()
        messages = store.get_or_init("a", lambda: [])
        messages.append({"role": "user", "content": "hello"})
        self.assertIs(messages, store.get_or_init("a", lambda: []))
        self.assertEqual(1, len(messages))

    def test_reset_clears_all_sessions(self):
        store = SessionStore()
        first = store.get_or_init("a", lambda: ["old"])
        store.reset()
        second = store.get_or_init("a", lambda: ["new"])
        self.assertIsNot(first, second)
        self.assertEqual(["new"], second)

    def test_lru_limit_evicts_oldest_session(self):
        store = SessionStore()
        store.MAX_SESSIONS = 2
        with mock.patch("backend.session_store.time.monotonic", side_effect=[1, 2, 3, 4]):
            first = store.get_or_init("first", lambda: ["first"])
            store.get_or_init("second", lambda: ["second"])
            store.get_or_init("third", lambda: ["third"])
            reloaded = store.get_or_init("first", lambda: ["reloaded"])
        self.assertIsNot(first, reloaded)
        self.assertEqual(["reloaded"], reloaded)

    def test_set_preserves_supplied_message_list_reference(self):
        store = SessionStore()
        messages = ["first"]

        store.set("a", messages)

        self.assertIs(messages, store.get_or_init("a", lambda: []))

    def test_ttl_evicts_expired_oldest_session(self):
        store = SessionStore()
        store.SESSION_TTL_SEC = 10
        with mock.patch("backend.session_store.time.monotonic", side_effect=[1, 20, 21]):
            first = store.get_or_init("first", lambda: ["first"])
            store.get_or_init("second", lambda: ["second"])
            reloaded = store.get_or_init("first", lambda: ["reloaded"])

        self.assertIsNot(first, reloaded)
        self.assertEqual(["reloaded"], reloaded)


if __name__ == "__main__":
    unittest.main()
