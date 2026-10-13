import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import http_api


class _FakeAgent(object):
    def __init__(self):
        self.calls = []

    def tool(self, function_name, params=None, timeout=None):
        self.calls.append((function_name, params or {}, timeout))
        return {"status": "success"}


class ProcessRouteTraceTest(unittest.TestCase):
    def test_process_route_state_persists_result_by_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(http_api, "PROCESS_ROUTE_RUNS_DIR", temp_dir):
                state = http_api.ProcessRouteState()
                result = {
                    "trace_id": "trace-A",
                    "route": [{"process_name": "A"}],
                }

                state.set_result(result)
                restarted_state = http_api.ProcessRouteState()

                self.assertEqual(result, restarted_state.get_result("trace-A"))

    def test_process_route_state_reads_older_trace_after_newer_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(http_api, "PROCESS_ROUTE_RUNS_DIR", temp_dir):
                state = http_api.ProcessRouteState()
                result_a = {
                    "trace_id": "trace-A",
                    "route": [{"process_name": "A"}],
                }
                result_b = {
                    "trace_id": "trace-B",
                    "route": [{"process_name": "B"}],
                }

                state.set_result(result_a)
                state.set_result(result_b)

                self.assertEqual(result_a, state.get_result("trace-A"))
                self.assertEqual(result_b, state.get_result("trace-B"))

    def test_submit_requires_trace_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = http_api.ProcessRouteState()
            state.set_result({
                "trace_id": "trace-A",
                "route": [{"process_name": "A"}],
            })
            fake_agent = _FakeAgent()
            handler = object.__new__(http_api.AgentRequestHandler)

            with mock.patch.object(http_api, "PROCESS_ROUTE_STATE", state), \
                    mock.patch.object(http_api, "AGENT", fake_agent), \
                    mock.patch.object(http_api, "_get_process_route_data_dir", return_value=temp_dir), \
                    mock.patch.object(http_api, "_get_process_route_output_path", return_value=str(Path(temp_dir) / "output.json")):
                result = handler._handle_submit_process_route({"timeout": 5})

        self.assertEqual("error", result.get("status"))
        self.assertEqual("PROCESS_ROUTE_TRACE_REQUIRED", result.get("error_code"))
        self.assertEqual([], fake_agent.calls)

    def test_submit_rejects_mismatched_trace_before_export_or_tool_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = http_api.ProcessRouteState()
            state.set_result({
                "trace_id": "trace-B",
                "route": [{"process_name": "B"}],
            })
            fake_agent = _FakeAgent()
            handler = object.__new__(http_api.AgentRequestHandler)
            output_path = Path(temp_dir) / "output.json"

            with mock.patch.object(http_api, "PROCESS_ROUTE_STATE", state), \
                    mock.patch.object(http_api, "AGENT", fake_agent), \
                    mock.patch.object(http_api, "_get_process_route_data_dir", return_value=temp_dir), \
                    mock.patch.object(http_api, "_get_process_route_output_path", return_value=str(output_path)):
                result = handler._handle_submit_process_route({"trace_id": "trace-A", "timeout": 5})

        self.assertEqual("error", result.get("status"))
        self.assertEqual("PROCESS_ROUTE_TRACE_MISMATCH", result.get("error_code"))
        self.assertFalse(output_path.exists())
        self.assertEqual([], fake_agent.calls)

    def test_submit_accepts_persisted_trace_after_state_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            output_path = Path(temp_dir) / "output.json"
            state = http_api.ProcessRouteState()
            result_payload = {
                "trace_id": "trace-A",
                "route": [{"process_name": "A"}],
            }
            fake_agent = _FakeAgent()
            handler = object.__new__(http_api.AgentRequestHandler)

            with mock.patch.object(http_api, "PROCESS_ROUTE_RUNS_DIR", str(runs_dir)):
                state.set_result(result_payload)
                restarted_state = http_api.ProcessRouteState()

                with mock.patch.object(http_api, "PROCESS_ROUTE_STATE", restarted_state), \
                        mock.patch.object(http_api, "AGENT", fake_agent), \
                        mock.patch.object(http_api, "_get_process_route_data_dir", return_value=temp_dir), \
                        mock.patch.object(http_api, "_get_process_route_output_path", return_value=str(output_path)):
                    result = handler._handle_submit_process_route({"trace_id": "trace-A", "timeout": 5})

            self.assertEqual("success", result.get("status"))
            self.assertTrue(output_path.exists())
            self.assertEqual([("get_ai_process_route_input", {"cmd_id": 2}, 5)], fake_agent.calls)

    def test_submit_exports_technical_requirements_after_generated_with_missing_input_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            output_path = Path(temp_dir) / "output.json"
            state = http_api.ProcessRouteState()
            state.set_input({"input_json": [{"group_path": "G", "features": []}]})
            state.set_result({
                "trace_id": "trace-A",
                "route": [{
                    "process_name": "Drill",
                    "process_type": "Machining",
                    "precision": "Rough",
                    "technical_requirements": [],
                    "steps": [],
                }],
            })

            class _FakeTechRunner(object):
                def run(self, payload):
                    return {
                        "ok": True,
                        "route": [{
                            "process_name": "Drill",
                            "process_type": "Machining",
                            "precision": "Rough",
                            "technical_requirements": ["Deburr hole edge"],
                            "steps": [],
                        }],
                    }

            fake_agent = _FakeAgent()
            handler = object.__new__(http_api.AgentRequestHandler)

            with mock.patch.object(http_api, "PROCESS_ROUTE_RUNS_DIR", str(runs_dir)), \
                    mock.patch.object(http_api, "PROCESS_ROUTE_STATE", state), \
                    mock.patch.dict(http_api.SKILL_RUNNERS, {"technical_requirements_generate": _FakeTechRunner()}), \
                    mock.patch.object(http_api, "AGENT", fake_agent), \
                    mock.patch.object(http_api, "_get_process_route_data_dir", return_value=temp_dir), \
                    mock.patch.object(http_api, "_get_process_route_output_path", return_value=str(output_path)):
                tech_result = handler._handle_generate_technical_requirements({"manual": {}})
                if tech_result.get("status") == "success":
                    http_api.PROCESS_ROUTE_STATE.set_result(tech_result.get("result") or {})
                submit_result = handler._handle_submit_process_route({"trace_id": "trace-A", "timeout": 5})

            self.assertEqual("success", tech_result.get("status"))
            self.assertEqual("trace-A", tech_result.get("result", {}).get("trace_id"))
            self.assertEqual("success", submit_result.get("status"))
            with output_path.open("r", encoding="utf-8") as handle:
                exported = json.load(handle)
            self.assertEqual(["Deburr hole edge"], exported[0].get("technical_requirements"))

if __name__ == "__main__":
    unittest.main()
