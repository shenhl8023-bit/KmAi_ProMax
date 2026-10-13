import json
import threading
import unittest
from http.server import HTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError

from backend import http_api


class _FakeAgent(object):
    def __init__(self):
        self.calls = []
        self.result = {"status": "success"}

    def tool(self, function_name, params=None, timeout=None):
        self.calls.append((function_name, params or {}, timeout))
        return dict(self.result) if isinstance(self.result, dict) else self.result


class HttpApiSecurityTest(unittest.TestCase):
    def setUp(self):
        self.original_agent = http_api.AGENT
        self.original_token = getattr(http_api, "API_AUTH_TOKEN", None)
        self.original_allowed_origins = getattr(http_api, "ALLOWED_ORIGINS", None)
        self.fake_agent = _FakeAgent()
        http_api.AGENT = self.fake_agent
        http_api.API_AUTH_TOKEN = "test-token"
        http_api.ALLOWED_ORIGINS = set(["http://127.0.0.1"])
        self.server = HTTPServer(("127.0.0.1", 0), http_api.AgentRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.base_url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()
        http_api.AGENT = self.original_agent
        http_api.API_AUTH_TOKEN = self.original_token
        http_api.ALLOWED_ORIGINS = self.original_allowed_origins

    def _post_tool(self, payload, token=None, origin=None):
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            self.base_url + "/api/tool",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if token is not None:
            req.add_header("X-KmAI-Token", token)
        if origin is not None:
            req.add_header("Origin", origin)
        return urlrequest.urlopen(req, timeout=5)

    def _get_json(self, path, token=None, origin=None):
        req = urlrequest.Request(self.base_url + path, method="GET")
        if token is not None:
            req.add_header("X-KmAI-Token", token)
        if origin is not None:
            req.add_header("Origin", origin)
        return urlrequest.urlopen(req, timeout=5)

    def _options(self, path, token=None, origin=None):
        req = urlrequest.Request(self.base_url + path, method="OPTIONS")
        if token is not None:
            req.add_header("X-KmAI-Token", token)
        if origin is not None:
            req.add_header("Origin", origin)
        return urlrequest.urlopen(req, timeout=5)

    def _read_json_response(self, response):
        return json.loads(response.read().decode("utf-8"))

    def _post_tool_json(self, tool_result):
        self.fake_agent.result = tool_result
        try:
            response = self._post_tool(
                {"function": "test_tool", "params": {}},
                token="test-token",
                origin=self.base_url,
            )
        except HTTPError as exc:
            return exc.code, self._read_json_response(exc)
        return response.status, self._read_json_response(response)

    def test_write_api_rejects_missing_auth_token(self):
        with self.assertRaises(HTTPError) as raised:
            self._post_tool({"function": "check_3dmps_status", "params": {}})

        self.assertEqual(403, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("AUTH_REQUIRED", payload.get("error_code"))
        self.assertEqual([], self.fake_agent.calls)

    def test_write_api_accepts_valid_auth_token(self):
        response = self._post_tool(
            {"function": "check_3dmps_status", "params": {}, "timeout": 5},
            token="test-token",
            origin=self.base_url,
        )

        payload = self._read_json_response(response)
        self.assertEqual("success", payload.get("status"))
        self.assertEqual([("check_3dmps_status", {}, 5)], self.fake_agent.calls)

    def test_tool_success_returns_http_200(self):
        result = {"status": "success", "value": 7}
        status, payload = self._post_tool_json(result)

        self.assertEqual(200, status)
        self.assertEqual("success", payload.get("status"))
        self.assertEqual(result, payload.get("result"))

    def test_tool_failure_shapes_map_to_http_errors(self):
        cases = [
            ({"ok": False, "message": "template missing"}, 422, "TOOL_EXECUTION_FAILED"),
            ({"status": "error", "message": "business failed"}, 422, "TOOL_EXECUTION_FAILED"),
            ({"status": "failed", "message": "failed status"}, 422, "TOOL_EXECUTION_FAILED"),
            ({"status": "failure", "message": "failure status"}, 422, "TOOL_EXECUTION_FAILED"),
            ({"status": "success", "result": {"ok": False, "message": "nested failed"}}, 422, "TOOL_EXECUTION_FAILED"),
            ({"status": "error", "error_code": "TOOL_NOT_REGISTERED", "message": "missing tool"}, 404, "TOOL_NOT_REGISTERED"),
            ({"status": "success", "error_code": "DOWNSTREAM_ERROR", "message": "downstream failed"}, 502, "DOWNSTREAM_ERROR"),
            ({"status": "error", "error_code": "INVALID_PARAMS", "message": "bad params"}, 400, "INVALID_PARAMS"),
            ({"status": "error", "error_code": "MISSING_TEMPLATE_NAME", "message": "missing name"}, 400, "MISSING_TEMPLATE_NAME"),
            ({"status": "error", "error_code": "FUNCTION_NOT_FOUND", "message": "bridge missing"}, 502, "FUNCTION_NOT_FOUND"),
            ({"status": "error", "error_code": "PIPE_UNAVAILABLE", "message": "pipe unavailable"}, 503, "PIPE_UNAVAILABLE"),
            ({"status": "error", "error_code": "TIMEOUT", "message": "timed out"}, 504, "TIMEOUT"),
        ]
        for result, expected_http, expected_code in cases:
            with self.subTest(result=result):
                status, payload = self._post_tool_json(result)
                self.assertEqual(expected_http, status)
                self.assertEqual("error", payload.get("status"))
                self.assertEqual(expected_code, payload.get("error_code"))
                self.assertEqual(result, payload.get("result"))

    def test_real_agent_runner_and_pipe_failures_map_to_http_502(self):
        from backend import tool_dispatcher

        class _FailingRunner(object):
            def run(self, _params):
                raise RuntimeError("runner exploded")

        class _FailingPipe(object):
            def call(self, _function_name, _params, timeout=None):
                raise RuntimeError("pipe exploded")

        class _Dispatcher(tool_dispatcher.ToolDispatcherMixin):
            def __init__(self):
                self.pipe = _FailingPipe()

        dispatcher = _Dispatcher()
        original_runners = tool_dispatcher.SKILL_RUNNERS
        original_tools = tool_dispatcher.TOOLS
        original_builders = tool_dispatcher.TOOL_PIPE_BUILDER
        try:
            tool_dispatcher.SKILL_RUNNERS = {"failing_skill": _FailingRunner()}
            tool_dispatcher.TOOLS = [
                {"function": {"name": "failing_skill"}},
                {"function": {"name": "failing_pipe"}},
            ]
            tool_dispatcher.TOOL_PIPE_BUILDER = {}

            cases = [
                ("failing_skill", "RUN_ERROR"),
                ("failing_pipe", "PIPE_ERROR"),
            ]
            for function_name, expected_code in cases:
                with self.subTest(function_name=function_name):
                    result = dispatcher.tool(function_name, {}, timeout=1)
                    status, payload = self._post_tool_json(result)
                    self.assertEqual(502, status)
                    self.assertEqual(expected_code, payload.get("error_code"))
                    self.assertEqual(expected_code, payload.get("result", {}).get("error_code"))
        finally:
            tool_dispatcher.SKILL_RUNNERS = original_runners
            tool_dispatcher.TOOLS = original_tools
            tool_dispatcher.TOOL_PIPE_BUILDER = original_builders

    def test_nested_failure_message_and_code_are_promoted(self):
        result = {
            "status": "success",
            "result": {
                "status": "error",
                "error_code": "GROUP_TEMPLATE_CONFIRM_FAILED",
                "message": "confirm failed",
            },
        }
        status, payload = self._post_tool_json(result)

        self.assertEqual(422, status)
        self.assertEqual("GROUP_TEMPLATE_CONFIRM_FAILED", payload.get("error_code"))
        self.assertEqual("confirm failed", payload.get("message"))

    def test_real_agent_unregistered_tool_returns_http_404(self):
        fake_agent = self.fake_agent
        http_api.AGENT = self.original_agent
        try:
            with self.assertRaises(HTTPError) as raised:
                self._post_tool(
                    {"function": "definitely_not_registered_p1_04", "params": {}},
                    token="test-token",
                    origin=self.base_url,
                )
        finally:
            http_api.AGENT = fake_agent

        self.assertEqual(404, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("error", payload.get("status"))
        self.assertEqual("TOOL_NOT_REGISTERED", payload.get("error_code"))
        self.assertEqual("error", payload.get("result", {}).get("status"))

    def test_real_agent_missing_template_returns_http_422(self):
        fake_agent = self.fake_agent
        http_api.AGENT = self.original_agent
        try:
            with self.assertRaises(HTTPError) as raised:
                self._post_tool(
                    {
                        "function": "kmsoft_group_template_confirm",
                        "params": {"templateId": "not-exists-p1-04"},
                    },
                    token="test-token",
                    origin=self.base_url,
                )
        finally:
            http_api.AGENT = fake_agent

        self.assertEqual(422, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("error", payload.get("status"))
        self.assertEqual("TOOL_EXECUTION_FAILED", payload.get("error_code"))
        self.assertIs(False, payload.get("result", {}).get("ok"))

    def test_disallowed_origin_is_rejected_before_tool_runs(self):
        with self.assertRaises(HTTPError) as raised:
            self._post_tool(
                {"function": "check_3dmps_status", "params": {}},
                token="test-token",
                origin="https://example.com",
            )

        self.assertEqual(403, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("ORIGIN_FORBIDDEN", payload.get("error_code"))
        self.assertEqual([], self.fake_agent.calls)

    def test_tool_request_missing_function_returns_structured_400(self):
        with self.assertRaises(HTTPError) as raised:
            self._post_tool(
                {"params": {}},
                token="test-token",
                origin=self.base_url,
            )

        self.assertEqual(400, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("error", payload.get("status"))
        self.assertEqual("MISSING_FUNCTION", payload.get("error_code"))
        self.assertEqual([], self.fake_agent.calls)

    def test_tool_timeout_must_be_numeric_and_bounded(self):
        for bad_timeout in ("slow", -1, 999999):
            with self.subTest(timeout=bad_timeout):
                with self.assertRaises(HTTPError) as raised:
                    self._post_tool(
                        {"function": "check_3dmps_status", "params": {}, "timeout": bad_timeout},
                        token="test-token",
                        origin=self.base_url,
                    )
                self.assertEqual(400, raised.exception.code)
                payload = self._read_json_response(raised.exception)
                self.assertEqual("INVALID_TIMEOUT", payload.get("error_code"))

        self.assertEqual([], self.fake_agent.calls)

    def test_get_api_rejects_missing_auth_token(self):
        with self.assertRaises(HTTPError) as raised:
            self._get_json("/api/config/llm")

        self.assertEqual(403, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("AUTH_REQUIRED", payload.get("error_code"))

    def test_health_api_rejects_missing_auth_token(self):
        with self.assertRaises(HTTPError) as raised:
            self._get_json("/api/health")

        self.assertEqual(403, raised.exception.code)
        payload = self._read_json_response(raised.exception)
        self.assertEqual("AUTH_REQUIRED", payload.get("error_code"))

    def test_startup_ping_identifies_agent_without_auth_token(self):
        response = self._get_json("/api/startup-ping")

        payload = self._read_json_response(response)
        self.assertEqual(200, response.status)
        self.assertEqual("ok", payload.get("status"))
        self.assertEqual("KmAI", payload.get("app"))
        self.assertEqual("agent", payload.get("kind"))
        self.assertNotIn("pipe", payload)
        self.assertNotIn("llm", payload)
        self.assertNotIn("skills", payload)

    def test_get_api_accepts_valid_auth_token_from_same_origin_with_port(self):
        response = self._get_json(
            "/api/config/llm",
            token="test-token",
            origin=self.base_url,
        )

        payload = self._read_json_response(response)
        self.assertEqual("success", payload.get("status"))
        self.assertIn("config", payload)

    def test_disallowed_preflight_origin_is_rejected(self):
        with self.assertRaises(HTTPError) as raised:
            self._options(
                "/api/tool",
                token="test-token",
                origin="https://example.com",
            )

        self.assertEqual(403, raised.exception.code)
        self.assertNotEqual(
            "*",
            raised.exception.headers.get("Access-Control-Allow-Origin"),
        )

    def test_public_index_and_assets_do_not_require_auth_token(self):
        index_response = self._get_json("/")
        self.assertEqual(200, index_response.status)

        asset_response = self._get_json("/assets/modules/entry.js")
        self.assertEqual(200, asset_response.status)

    def test_frontend_ping_sends_auth_token_header(self):
        source = http_api._ASSETS_DIR + "/modules/shared.js"
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()

        self.assertIn("window.__KMAI_API_TOKEN__", text)
        self.assertIn("X-KmAI-Token", text)
        self.assertIn("fetch('/api/health'", text)

    def test_index_html_injects_api_token(self):
        old_token = http_api.API_AUTH_TOKEN
        try:
            http_api.API_AUTH_TOKEN = "html-token"
            html = http_api.current_index_html()
        finally:
            http_api.API_AUTH_TOKEN = old_token

        self.assertIn("window.__KMAI_API_TOKEN__", html)
        self.assertIn("html-token", html)


if __name__ == "__main__":
    unittest.main()
