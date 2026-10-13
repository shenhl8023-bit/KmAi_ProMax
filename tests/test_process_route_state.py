# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import unittest
try:
    from unittest import mock
except ImportError:
    import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class ProcessRouteStateTests(unittest.TestCase):
    def test_process_route_data_dir_expands_literal_home_env_vars(self):
        from backend import http_api

        with mock.patch.dict(os.environ, {
            "USERPROFILE": "",
            "HOME": r"%HOMEDRIVE%%HOMEPATH%",
            "HOMEDRIVE": "C:",
            "HOMEPATH": r"\Users\Administrator",
        }, clear=False):
            self.assertEqual(
                os.path.abspath(r"C:\Users\Administrator\3dmps-path-data"),
                http_api._get_process_route_data_dir(),
            )

    def test_process_route_data_dir_falls_back_to_runtime_dir_for_invalid_home(self):
        from backend import http_api

        with mock.patch.dict(os.environ, {
            "USERPROFILE": "",
            "HOME": "",
            "HOMEDRIVE": "",
            "HOMEPATH": "",
            "LOCALAPPDATA": r"C:\Users\Administrator\AppData\Local",
            "KMAI_RUNTIME_DIR": "",
        }, clear=False):
            with mock.patch("backend.http_api.os.path.expanduser", return_value=r"%HOMEDRIVE%%HOMEPATH%"):
                self.assertEqual(
                    os.path.abspath(r"C:\Users\Administrator\AppData\Local\KmAI\3dmps-path-data"),
                    http_api._get_process_route_data_dir(),
                )

    def test_process_route_data_dir_honors_runtime_dir_when_home_is_invalid(self):
        from backend import http_api

        with mock.patch.dict(os.environ, {
            "USERPROFILE": "",
            "HOME": "",
            "HOMEDRIVE": "",
            "HOMEPATH": "",
            "LOCALAPPDATA": "",
            "KMAI_RUNTIME_DIR": r"D:\Runtime\KmAI",
        }, clear=False):
            with mock.patch("backend.http_api.os.path.expanduser", return_value=r"%HOMEDRIVE%%HOMEPATH%"):
                self.assertEqual(
                    os.path.abspath(r"D:\Runtime\KmAI\3dmps-path-data"),
                    http_api._get_process_route_data_dir(),
                )

    def test_state_accessors_do_not_share_mutable_references(self):
        from backend import http_api

        state = http_api.ProcessRouteState()
        source_input = {"input_json": [{"name": "turning"}]}
        source_result = {"route": [{"process_name": "lathe"}]}

        state.set_input(source_input)
        state.set_result(source_result)
        source_input["input_json"][0]["name"] = "mutated"
        source_result["route"][0]["process_name"] = "mutated"

        first_input = state.get_input()
        first_result = state.get_result()
        self.assertEqual("turning", first_input["input_json"][0]["name"])
        self.assertEqual("lathe", first_result["route"][0]["process_name"])

        first_input["input_json"][0]["name"] = "changed again"
        first_result["route"][0]["process_name"] = "changed again"

        self.assertEqual("turning", state.get_input()["input_json"][0]["name"])
        self.assertEqual("lathe", state.get_result()["route"][0]["process_name"])

    def test_route_rows_helper_does_not_return_internal_state_reference(self):
        from backend import http_api

        original_state = http_api.PROCESS_ROUTE_STATE
        http_api.PROCESS_ROUTE_STATE = http_api.ProcessRouteState()
        try:
            route_rows = [{"process_name": "lathe"}]
            http_api.PROCESS_ROUTE_STATE.set_result({"route": route_rows})
            route_rows[0]["process_name"] = "mutated"

            handler = object.__new__(http_api.AgentRequestHandler)
            rows = handler._get_latest_process_route_rows()
            self.assertEqual([{"process_name": "lathe"}], rows)

            rows[0]["process_name"] = "changed again"
            self.assertEqual(
                [{"process_name": "lathe"}],
                handler._get_latest_process_route_rows(),
            )
        finally:
            http_api.PROCESS_ROUTE_STATE = original_state


if __name__ == "__main__":
    unittest.main()
