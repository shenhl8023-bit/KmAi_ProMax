# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class RecordingBody(object):
    def __init__(self, body=b"", fail_on_read=False):
        self._body = io.BytesIO(body)
        self.fail_on_read = fail_on_read
        self.read_calls = 0

    def read(self, size=-1):
        self.read_calls += 1
        if self.fail_on_read:
            raise AssertionError("oversized request body should not be read")
        return self._body.read(size)


class RecordingHeaders(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class FakeServer(object):
    server_address = ("127.0.0.1", 9095)


class HttpRequestBodyLimitTests(unittest.TestCase):
    def _make_handler(self, path, body=b"", content_length=None, fail_on_read=False):
        from backend import http_api

        handler = object.__new__(http_api.AgentRequestHandler)
        length = len(body) if content_length is None else content_length
        handler.path = path
        handler.command = "POST"
        handler.server = FakeServer()
        handler.headers = RecordingHeaders({
            "Content-Length": str(length),
            "Origin": "http://127.0.0.1:9095",
            "X-KmAI-Token": http_api.API_AUTH_TOKEN,
        })
        handler.rfile = RecordingBody(body, fail_on_read=fail_on_read)
        handler.sent_json = []
        handler._send_json = lambda status, data: handler.sent_json.append((status, data))
        return handler

    def test_default_api_body_over_two_mb_returns_413_without_reading_body(self):
        handler = self._make_handler(
            "/api/chat",
            content_length=(2 * 1024 * 1024) + 1,
            fail_on_read=True,
        )

        handler.do_POST()

        self.assertEqual(0, handler.rfile.read_calls)
        self.assertEqual(413, handler.sent_json[0][0])
        self.assertEqual("PAYLOAD_TOO_LARGE", handler.sent_json[0][1].get("error_code"))

    def test_process_route_push_body_over_eight_mb_returns_413_without_reading_body(self):
        handler = self._make_handler(
            "/api/process-route/input/push",
            content_length=(8 * 1024 * 1024) + 1,
            fail_on_read=True,
        )

        handler.do_POST()

        self.assertEqual(0, handler.rfile.read_calls)
        self.assertEqual(413, handler.sent_json[0][0])
        self.assertEqual("PAYLOAD_TOO_LARGE", handler.sent_json[0][1].get("error_code"))

    def test_process_route_push_allows_body_above_default_limit(self):
        from backend import http_api

        original_state = http_api.PROCESS_ROUTE_STATE
        http_api.PROCESS_ROUTE_STATE = http_api.ProcessRouteState()
        try:
            large_value = "x" * ((2 * 1024 * 1024) + 1024)
            body = json.dumps({"input_json": [{"name": large_value}]}).encode("utf-8")
            handler = self._make_handler("/api/process-route/input/push", body=body)

            handler.do_POST()

            self.assertEqual(200, handler.sent_json[0][0])
            self.assertEqual(
                large_value,
                http_api.PROCESS_ROUTE_STATE.get_input()["input_json"][0]["name"],
            )
        finally:
            http_api.PROCESS_ROUTE_STATE = original_state

    def test_invalid_content_length_returns_400_without_reading_body(self):
        handler = self._make_handler(
            "/api/chat",
            body=b'{"message":"hello"}',
            content_length="abc",
            fail_on_read=True,
        )

        handler.do_POST()

        self.assertEqual(0, handler.rfile.read_calls)
        self.assertEqual(400, handler.sent_json[0][0])
        payload = handler.sent_json[0][1]
        self.assertEqual("error", payload.get("status"))
        self.assertEqual("INVALID_CONTENT_LENGTH", payload.get("error_code"))
        self.assertNotIn("invalid literal", payload.get("message", ""))

    def test_negative_content_length_returns_400_without_reading_body(self):
        handler = self._make_handler(
            "/api/chat",
            body=b'{"message":"hello"}',
            content_length="-1",
            fail_on_read=True,
        )

        handler.do_POST()

        self.assertEqual(0, handler.rfile.read_calls)
        self.assertEqual(400, handler.sent_json[0][0])
        self.assertEqual("INVALID_CONTENT_LENGTH", handler.sent_json[0][1].get("error_code"))

    def test_invalid_json_returns_400_without_internal_exception_message(self):
        handler = self._make_handler(
            "/api/chat",
            body=b'{"message":',
        )

        handler.do_POST()

        self.assertEqual(400, handler.sent_json[0][0])
        payload = handler.sent_json[0][1]
        self.assertEqual("error", payload.get("status"))
        self.assertEqual("INVALID_JSON", payload.get("error_code"))
        self.assertNotIn("Expecting value", payload.get("message", ""))

    def test_internal_post_error_does_not_return_traceback_to_client(self):
        from backend import http_api

        original_tool = http_api.AGENT.tool
        try:
            http_api.AGENT.tool = lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("forced internal failure")
            )
            body = json.dumps({"function": "force_failure", "params": {}}).encode("utf-8")
            handler = self._make_handler("/api/tool", body=body)

            handler.do_POST()

            self.assertEqual(500, handler.sent_json[0][0])
            payload = handler.sent_json[0][1]
            self.assertEqual("error", payload.get("status"))
            self.assertNotIn("trace", payload)
        finally:
            http_api.AGENT.tool = original_tool


if __name__ == "__main__":
    unittest.main()
