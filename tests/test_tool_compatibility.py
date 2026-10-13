# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class RecordingPipe(object):
    def __init__(self, available=True, responses=None):
        self.available = available
        self.responses = responses or {}
        self.calls = []

    def is_available(self):
        return self.available

    def call(self, name, params, timeout=None):
        self.calls.append((name, params, timeout))
        return self.responses.get(name, {
            "status": "success",
            "function": name,
            "params": params,
        })


class StatusFirstLLM(object):
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, stream=False, include_reasoning=False):
        self.calls.append({
            "messages": list(messages),
            "tools": tools,
            "stream": stream,
            "include_reasoning": include_reasoning,
        })
        if len(self.calls) == 1:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "call-status",
                            "type": "function",
                            "function": {
                                "name": "check_3dmps_status",
                                "arguments": "{}",
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
            }
        return {
            "choices": [{
                "message": {"role": "assistant", "content": "status checked"},
                "finish_reason": "stop",
            }],
        }


class ToolCompatibilityTests(unittest.TestCase):
    def test_socket_process_agent_is_temporarily_disabled(self):
        from backend.agent_profiles import DEFAULT_AGENT_ID, get_agent_profile, list_agent_summaries

        ids = [item.get("id") for item in list_agent_summaries()]

        self.assertNotIn("socket-process-agent", ids)
        self.assertEqual(DEFAULT_AGENT_ID, get_agent_profile("socket-process-agent").get("id"))
    def test_status_check_uses_local_pipe_health_without_calling_pipe_function(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.pipe = RecordingPipe(available=True)

        result = agent.tool("check_3dmps_status", {}, timeout=1)

        self.assertEqual("success", result.get("status"))
        self.assertEqual("check_3dmps_status", result.get("tool"))
        self.assertTrue(result.get("pipe_available"))
        self.assertEqual([], agent.pipe.calls)

    def test_get_features_extracts_names_from_available_bof_tree(self):
        from backend.agent_core import MiniAgent

        bof_result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "sample.prt": {
                            "澶栧渾鏌遍潰1": {"澶栧渾鏌遍潰1": {}},
                            "U褰㈠鐜Ы1": {"U褰㈠鐜Ы1": {}},
                        },
                    },
                },
            },
        }
        agent = MiniAgent()
        agent.pipe = RecordingPipe(responses={"get_all_bof_item": bof_result})

        result = agent.tool("get_features", {}, timeout=1)

        self.assertEqual("success", result.get("status"))
        self.assertEqual("get_features", result.get("tool"))
        self.assertEqual(["澶栧渾鏌遍潰1", "U褰㈠鐜Ы1"], result.get("features"))
        self.assertEqual(2, result.get("count"))
        self.assertEqual([("get_all_bof_item", {}, 1)], agent.pipe.calls)



    def test_get_features_repairs_mojibake_names_from_bof_tree(self):
        from backend.agent_core import MiniAgent

        bof_result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "sample.prt": {
                            "\u00d6\u00d0\u00bc\u00e4\u00cd\u00a8\u00bf\u00d7": {},
                            "A\u00b2\u00e0": {},
                        },
                    },
                },
            },
        }
        agent = MiniAgent()
        agent.pipe = RecordingPipe(responses={"get_all_bof_item": bof_result})

        result = agent.tool("get_features", {}, timeout=1)

        self.assertEqual("success", result.get("status"))
        self.assertEqual(["\u4e2d\u95f4\u901a\u5b54", "A\u4fa7"], result.get("features"))

    def test_default_chat_feature_list_reply_contains_feature_names(self):
        from backend.agent_core import MiniAgent

        bof_result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "sample.prt": {
                            "\u4e2d\u95f4\u901a\u5b54": {},
                            "A\u4fa7": {},
                        },
                    },
                },
            },
        }
        agent = MiniAgent()
        agent.llm = None
        agent.pipe = RecordingPipe(responses={"get_all_bof_item": bof_result})

        result = agent.chat("\u67e5\u8be2\u5f53\u524d\u6a21\u578b\u7279\u5f81\u6570\u636e", session_id="test-features", agent_id="default")

        self.assertEqual("get_features", result.get("tool"))
        self.assertIn("\u5171 2 \u4e2a", result.get("reply"))
        self.assertIn("1. \u4e2d\u95f4\u901a\u5b54", result.get("reply"))
        self.assertIn("2. A\u4fa7", result.get("reply"))


    def test_default_chat_status_reply_contains_pipe_state(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.llm = None
        agent.pipe = RecordingPipe(available=True)

        result = agent.chat("\u68c0\u67e53DMPS\u72b6\u6001", session_id="test-status", agent_id="default")

        self.assertEqual("check_3dmps_status", result.get("tool"))
        self.assertIn("3DMPS", result.get("reply"))
        self.assertIn("\u53ef\u7528", result.get("reply"))
        self.assertEqual([], agent.pipe.calls)

    def test_llm_chat_uses_direct_keyword_before_llm_for_feature_list(self):
        from backend.agent_core import MiniAgent

        bof_result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "sample.prt": {
                            "\u4e2d\u95f4\u901a\u5b54": {},
                            "A\u4fa7": {},
                        },
                    },
                },
            },
        }
        agent = MiniAgent()
        fake_llm = StatusFirstLLM()
        agent.llm = fake_llm
        agent.pipe = RecordingPipe(responses={"get_all_bof_item": bof_result})

        result = agent.chat("\u83b7\u53d6\u7279\u5f81\u5217\u8868", session_id="test-llm-features", agent_id="default")

        self.assertEqual("get_features", result.get("tool"))
        self.assertEqual([], fake_llm.calls)
        self.assertEqual([("get_all_bof_item", {}, 15)], agent.pipe.calls)

    def test_stream_chat_uses_direct_keyword_before_llm_for_group_template_button(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        fake_llm = StatusFirstLLM()
        agent.llm = fake_llm
        agent.pipe = RecordingPipe()

        events = list(agent.stream_chat("\u5e2e\u6211\u6253\u5f00\u5206\u7ec4\u6a21\u677f", session_id="test-llm-group-template", agent_id="default"))

        tool_events = [event for event in events if event.get("type") == "tool_call"]
        self.assertEqual(1, len(tool_events))
        self.assertEqual("click_group_template_button", tool_events[0].get("tool"))
        self.assertEqual([], fake_llm.calls)
        self.assertEqual([("do_cmdResponse_by_python", {"arg1": 52756}, 10)], agent.pipe.calls)

    def test_default_chat_bof_reply_contains_summary_and_names(self):
        from backend.agent_core import MiniAgent

        bof_result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "sample.prt": {
                            "\u4e2d\u95f4\u901a\u5b54": {},
                            "A\u4fa7": {},
                        },
                    },
                },
            },
        }
        agent = MiniAgent()
        agent.llm = None
        agent.pipe = RecordingPipe(responses={"get_all_bof_item": bof_result})

        result = agent.chat("\u83b7\u53d6bof\u6570\u636e", session_id="test-bof", agent_id="default")

        self.assertEqual("get_all_bof_item", result.get("tool"))
        self.assertIn("BOF", result.get("reply"))
        self.assertIn("sample.prt", result.get("reply"))
        self.assertIn("BOF/\u7279\u5f81\u6811\u7ed3\u6784", result.get("reply"))
        self.assertIn("\u2514\u2500 sample.prt", result.get("reply"))
        self.assertIn("\u4e2d\u95f4\u901a\u5b54", result.get("reply"))
        self.assertIn("A\u4fa7", result.get("reply"))


    def test_list_style_tool_replies_are_formatted_for_chat(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()

        group_reply = agent._format_direct_tool_reply(
            "get_all_group_template_list",
            "fallback",
            {"status": "success", "data": {"result": {"template_names": ["tpl_a", "tpl_b"]}}},
        )
        self.assertIn("\u5206\u7ec4\u6a21\u677f\u5217\u8868", group_reply)
        self.assertIn("1. tpl_a", group_reply)

        auto_template_reply = agent._format_direct_tool_reply(
            "get_autoidentify_template_list",
            "fallback",
            {"status": "success", "data": {"result": {"template_names": ["auto_a.ini", "auto_b.ini"]}}},
        )
        self.assertIn("\u81ea\u52a8\u8bc6\u522b\u6a21\u677f\u5217\u8868", auto_template_reply)
        self.assertIn("1. auto_a", auto_template_reply)

        checked_reply = agent._format_direct_tool_reply(
            "get_autoidentify_checkbox_list",
            "fallback",
            {"status": "success", "data": {"result": "[\u5b54,1][\u69fd,0]"}},
        )
        self.assertIn("\u81ea\u52a8\u8bc6\u522b\u5df2\u52fe\u9009\u7279\u5f81", checked_reply)
        self.assertIn("1. \u5b54", checked_reply)

    def test_autoidentify_list_tools_map_to_registered_dialog_functions(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.pipe = RecordingPipe()

        agent.tool("get_autoidentify_template_list", {}, timeout=3)
        agent.tool("get_autoidentify_checkbox_list", {}, timeout=4)

        self.assertEqual([
            ("GetExtractDataList", {}, 3),
            ("GetAutoIdentifyCheckedList", {}, 4),
        ], agent.pipe.calls)

    def test_apply_group_template_expands_bof_tree_after_confirm(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.pipe = RecordingPipe(responses={
            "GetAllGroupTemplateList": {
                "status": "success",
                "data": {
                    "result": {
                        "template_names": ["sample_template"],
                    },
                },
            },
        })
        expand_calls = []
        agent._expand_visible_bof_tree = lambda: expand_calls.append(True) or {"status": "success"}

        result = agent.tool("apply_group_template", {"template_name": "sample_template"}, timeout=1)

        self.assertEqual("success", result.get("status"))
        self.assertEqual([True], expand_calls)
        self.assertIn("expand_bof_tree", [step.get("step") for step in result.get("steps", [])])

    def test_scroll_tree_to_left_sends_horizontal_scroll_left(self):
        from backend.agent_core import MiniAgent

        class FakeUser32(object):
            def __init__(self):
                self.messages = []
                self.invalidated = []
                self.updated = []

            def SendMessageW(self, hwnd, message, wparam, lparam):
                self.messages.append((hwnd, message, getattr(wparam, "value", wparam), lparam))

            def InvalidateRect(self, hwnd, rect, erase):
                self.invalidated.append((hwnd, rect, erase))

            def UpdateWindow(self, hwnd):
                self.updated.append(hwnd)

        user32 = FakeUser32()

        MiniAgent._scroll_tree_to_left(user32, 1234)

        self.assertEqual([(1234, 0x0114, 6, None)], user32.messages)
        self.assertEqual([(1234, None, True)], user32.invalidated)
        self.assertEqual([1234], user32.updated)
    def test_unimplemented_tools_are_hidden_from_public_llm_tool_list(self):
        from backend.tool_runtime import KEYWORD_RULES, TOOLS


        names = [tool["function"]["name"] for tool in TOOLS]
        self.assertNotIn("save_file", names)
        self.assertNotIn("get_cur_model_info", names)
        self.assertNotIn("start_ai_process_route", names)

        rule_tools = [rule.get("tool") for rule in KEYWORD_RULES]
        self.assertNotIn("save_file", rule_tools)
        self.assertNotIn("get_cur_model_info", rule_tools)


if __name__ == "__main__":
    unittest.main()



