# -*- coding: utf-8 -*-
import os
import sys
import unittest

from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.agent_core import MiniAgent


class FakePipe(object):
    def __init__(self, root_params_payload):
        self.root_params_payload = root_params_payload
        self.calls = []

    def call(self, function_name, params=None, timeout=None):
        self.calls.append((function_name, params or {}, timeout))
        if function_name == "main.bof_root_params.get":
            return self.root_params_payload
        if function_name == "do_cmdResponse_by_python":
            return {"status": "success"}
        if function_name == "GetExtractDataList":
            return {"status": "success", "data": {"result": ["first.ini", "second.ini"]}}
        if function_name == "OnBnClickedOk":
            return {"status": "success"}
        raise AssertionError("Unexpected pipe call: %s" % function_name)


def legacy_root_params(origin_value, directions):
    return {
        "status": "success",
        "data": {
            "result": {
                "success": True,
                "origin_value": origin_value,
                "main_direction_values": directions,
            }
        },
    }


class AutoIdentifyVerificationTests(unittest.TestCase):
    def test_bof_tree_change_is_detected(self):
        before = {"status": "success", "data": {"part.prt": {"A": {}, "B": {}}}}
        after = {"status": "success", "data": {"part.prt": {"A": {"孔": {}}, "B": {}}}}

        verification = MiniAgent._build_autoidentify_bof_verification(before, after)

        self.assertTrue(verification["changed"])
        self.assertGreater(verification["after_node_count"], verification["before_node_count"])

    def test_unchanged_bof_tree_is_not_detected_as_success(self):
        before = {"status": "success", "data": {"part.prt": {"A": {}, "B": {}}}}
        after = {"status": "success", "data": {"part.prt": {"A": {}, "B": {}}}}

        verification = MiniAgent._build_autoidentify_bof_verification(before, after)

        self.assertFalse(verification["changed"])
        self.assertEqual(verification["after_node_count"], verification["before_node_count"])

    def test_root_param_precheck_reports_missing_origin(self):
        # 原点是必填项；缺失时应在打开 3DMPS 对话框前停止第 2 步。
        verification = MiniAgent._build_autoidentify_root_params_verification(
            legacy_root_params("", {u"\u4e3b\u65b9\u54111": "X"})
        )

        self.assertFalse(verification["all_required_specified"])
        self.assertEqual([u"\u539f\u70b9"], verification["missing_fields"])
        self.assertEqual("missing_required", verification["status"])

    def test_root_param_precheck_reports_any_existing_main_direction_missing(self):
        # 根节点上实际存在的每个主方向字段都必须已指定。
        verification = MiniAgent._build_autoidentify_root_params_verification(
            legacy_root_params(
                "origin-1",
                {
                    u"\u4e3b\u65b9\u54111": "X",
                    u"\u4e3b\u65b9\u54112": u"\u8bf7\u53cc\u51fb\u8fdb\u884c\u6307\u5b9a",
                    u"\u4e3b\u65b9\u54114": "Z",
                },
            )
        )

        self.assertFalse(verification["all_required_specified"])
        self.assertEqual([u"\u4e3b\u65b9\u54112"], verification["missing_fields"])
        self.assertEqual(3, len(verification["main_direction_values"]))

    def test_root_param_precheck_reports_all_missing_existing_main_directions(self):
        # 只要根节点上存在的任一主方向未指定，第 2 步就不能继续。
        verification = MiniAgent._build_autoidentify_root_params_verification(
            legacy_root_params(
                "origin-1",
                {
                    u"\u4e3b\u65b9\u54111": "X",
                    u"\u4e3b\u65b9\u54112": "",
                    u"\u4e3b\u65b9\u54113": u"\u8bf7\u53cc\u51fb\u8fdb\u884c\u6307\u5b9a",
                    u"\u4e3b\u65b9\u54114": "Z",
                },
            )
        )

        self.assertFalse(verification["all_required_specified"])
        self.assertEqual([u"\u4e3b\u65b9\u54112", u"\u4e3b\u65b9\u54113"], verification["missing_fields"])
        self.assertEqual("missing_required", verification["status"])

    def test_root_param_precheck_passes_when_origin_and_all_existing_directions_are_specified(self):
        verification = MiniAgent._build_autoidentify_root_params_verification(
            legacy_root_params(
                "origin-1",
                {u"\u4e3b\u65b9\u54111": "X", u"\u4e3b\u65b9\u54113": "Z"},
            )
        )

        self.assertTrue(verification["all_required_specified"])
        self.assertEqual([], verification["missing_fields"])
        self.assertEqual("ready", verification["status"])

    def test_autoidentify_flow_does_not_open_dialog_when_root_params_are_missing(self):
        # 前置校验快速失败时，应保留可重试的工作流状态，并避免弹窗副作用。
        agent = MiniAgent.__new__(MiniAgent)
        agent.pipe = FakePipe(legacy_root_params("", {u"\u4e3b\u65b9\u54111": "X"}))
        agent._audit = lambda *args, **kwargs: None

        payload = agent._open_and_confirm_autoidentify_dialog({})

        self.assertEqual("error", payload["status"])
        self.assertEqual("AUTOIDENTIFY_ROOT_PARAMS_MISSING", payload["error_code"])
        self.assertNotIn("do_cmdResponse_by_python", [call[0] for call in agent.pipe.calls])

    def test_autoidentify_flow_passes_after_ok_without_bof_tree_polling(self):
        # 根参数有效后，确认自动识别即可继续；不再等待 BOF 树变化。
        agent = MiniAgent.__new__(MiniAgent)
        agent.pipe = FakePipe(
            legacy_root_params("origin-1", {u"\u4e3b\u65b9\u54111": "X"})
        )
        agent._audit = lambda *args, **kwargs: None

        with mock.patch.object(MiniAgent, "_wait_for_autoidentify_result", side_effect=AssertionError("BOF polling called")):
            with mock.patch.object(MiniAgent, "_find_known_autoidentify_failure_dialog", return_value={"found": False}):
                payload = agent._open_and_confirm_autoidentify_dialog({})

        self.assertEqual("success", payload["status"])
        call_names = [call[0] for call in agent.pipe.calls]
        self.assertIn("OnBnClickedOk", call_names)
        self.assertNotIn("get_all_bof_item", call_names)


if __name__ == "__main__":
    unittest.main()
