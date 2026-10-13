import os
import tempfile
import unittest
from pathlib import Path

from backend import agent_profiles
from backend.agent_core import MiniAgent


class FakeStreamingLlm(object):
    def __init__(self, first_response, final_chunks=None):
        self.first_response = first_response
        self.final_chunks = final_chunks or []
        self.calls = []

    def chat(self, messages, tools=None, stream=False, include_reasoning=False):
        self.calls.append({
            "tools": tools,
            "stream": stream,
            "include_reasoning": include_reasoning,
        })
        if stream:
            return iter(self.final_chunks)
        return self.first_response


class AgentBoundaryTest(unittest.TestCase):
    def test_kmrag_agent_only_receives_search_tool_and_refuses_without_tool_call(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm({
            "choices": [{
                "message": {"role": "assistant", "content": "未经检索的回答"},
                "finish_reason": "stop",
            }]
        })

        result = agent.chat(
            "读取BOF",
            session_id="kmrag-no-tool",
            agent_id="kmrag-knowledge-agent",
        )

        self.assertEqual(["kmrag_search"], [
            tool["function"]["name"] for tool in agent.llm.calls[0]["tools"]
        ])
        self.assertEqual("未执行知识库检索，无法基于企业知识库回答。", result["reply"])

    def test_kmrag_agent_without_llm_does_not_use_keyword_fallback(self):
        agent = MiniAgent()
        agent.llm = None

        result = agent.chat(
            "读取BOF",
            session_id="kmrag-no-llm",
            agent_id="kmrag-knowledge-agent",
        )

        self.assertEqual("需要先启用 LLM 智能对话。", result["reply"])
        self.assertIsNone(result["tool"])

    def test_kmrag_empty_search_result_stops_before_second_llm_call(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "kmrag-call",
                        "type": "function",
                        "function": {"name": "kmrag_search", "arguments": "{\"query\": \"制度\"}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        })
        calls = []

        def fake_execute_tool(name, args, agent_id=None):
            calls.append((name, args, agent_id))
            return {"ok": True, "records": []}

        agent._execute_tool = fake_execute_tool
        result = agent.chat(
            "查询制度",
            session_id="kmrag-empty",
            agent_id="kmrag-knowledge-agent",
        )

        self.assertEqual([("kmrag_search", {"query": "制度"}, "kmrag-knowledge-agent")], calls)
        self.assertEqual("知识库未检索到相关内容。", result["reply"])
        self.assertEqual(1, len(agent.llm.calls))

    def setUp(self):
        self._old_project_agents_dir = agent_profiles.PROJECT_AGENTS_DIR
        self._old_user_agents_dir = agent_profiles.USER_AGENTS_DIR
        self._old_enable_user_agents = os.environ.pop("KMAI_ENABLE_USER_AGENTS", None)

    def tearDown(self):
        agent_profiles.PROJECT_AGENTS_DIR = self._old_project_agents_dir
        agent_profiles.USER_AGENTS_DIR = self._old_user_agents_dir
        if self._old_enable_user_agents is None:
            os.environ.pop("KMAI_ENABLE_USER_AGENTS", None)
        else:
            os.environ["KMAI_ENABLE_USER_AGENTS"] = self._old_enable_user_agents

    def test_resolve_agent_profile_marks_unknown_agent_without_silent_fallback(self):
        with tempfile.TemporaryDirectory() as project_dir:
            agent_profiles.PROJECT_AGENTS_DIR = project_dir

            profile, found = agent_profiles.resolve_agent_profile("missing-agent")

        self.assertFalse(found)
        self.assertEqual("default", profile["id"])
        self.assertEqual("missing-agent", profile["requested_agent_id"])

    def test_stream_chat_without_llm_uses_process_auto_override_before_keyword_fallback(self):
        with tempfile.TemporaryDirectory() as project_dir:
            Path(project_dir, "process-auto-generate-agent.md").write_text(
                "Process auto prompt", encoding="utf-8"
            )
            agent_profiles.PROJECT_AGENTS_DIR = project_dir
            agent = MiniAgent()
            agent.llm = None
            calls = []

            def fake_execute_tool(name, args):
                calls.append((name, args))
                return {"status": "success", "payload": {"ok": True}}

            agent._execute_tool = fake_execute_tool

            events = list(agent.stream_chat(
                "进行AI工艺推理",
                session_id="test-session",
                agent_id="process-auto-generate-agent",
            ))

        self.assertEqual([("get_ai_process_route_input", {})], calls)
        self.assertEqual("status", events[0]["type"])
        self.assertEqual("正在理解问题...", events[0]["text"])
        self.assertEqual("tool_call", events[1]["type"])
        self.assertEqual("get_ai_process_route_input", events[1]["tool"])
        self.assertEqual("content", events[2]["type"])
        self.assertIn('"ok": true', events[2]["text"])

    def test_default_chat_with_llm_routes_direct_keyword_before_model(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm({
            "choices": [{
                "message": {"role": "assistant", "content": "LLM decided no tool"},
                "finish_reason": "stop",
            }]
        })
        direct_tool_calls = []

        def fake_tool(function_name, params=None, timeout=None):
            direct_tool_calls.append((function_name, params, timeout))
            return {"status": "success", "tool": function_name}

        agent.tool = fake_tool

        result = agent.chat(
            "\u8bfb\u53d6BOF",
            session_id="default-llm-keyword",
            agent_id="default",
        )

        self.assertEqual(0, len(agent.llm.calls))
        self.assertEqual(1, len(direct_tool_calls))
        self.assertEqual("get_all_bof_item", direct_tool_calls[0][0])
        self.assertEqual("get_all_bof_item", result.get("tool"))

    def test_default_stream_chat_with_llm_routes_explicit_bof_tree_question_before_model(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm({
            "choices": [{
                "message": {"role": "assistant", "content": "wrong tool decision"},
                "finish_reason": "stop",
            }]
        })
        direct_tool_calls = []

        def fake_tool(function_name, params=None, timeout=None):
            direct_tool_calls.append((function_name, params, timeout))
            return {
                "status": "success",
                "tool": function_name,
                "data": {
                    "result": {
                        "success": True,
                        "data": {"sample.prt": {"A侧": {"端面": {}}}},
                    }
                },
            }

        agent.tool = fake_tool

        events = list(agent.stream_chat(
            "当前bof树结构是怎样的",
            session_id="default-llm-bof-tree-question",
            agent_id="default",
        ))

        self.assertEqual(0, len(agent.llm.calls))
        self.assertEqual(1, len(direct_tool_calls))
        self.assertEqual("get_all_bof_item", direct_tool_calls[0][0])
        self.assertEqual("tool_call", events[1]["type"])
        self.assertEqual("get_all_bof_item", events[1]["tool"])
        self.assertEqual("content", events[2]["type"])
        self.assertIn("BOF/特征树结构", events[2]["text"])

    def test_default_stream_chat_without_llm_keeps_keyword_fallback(self):
        agent = MiniAgent()
        agent.llm = None
        direct_tool_calls = []

        def fake_tool(function_name, params=None, timeout=None):
            direct_tool_calls.append((function_name, params, timeout))
            return {"status": "success", "tool": function_name, "data": {}}

        agent.tool = fake_tool

        events = list(agent.stream_chat(
            "璇诲彇BOF",
            session_id="default-no-llm-keyword",
            agent_id="default",
        ))

        self.assertEqual(1, len(direct_tool_calls))
        self.assertEqual("get_all_bof_item", direct_tool_calls[0][0])
        self.assertEqual("status", events[0]["type"])
        self.assertEqual("tool_call", events[1]["type"])
        self.assertEqual("get_all_bof_item", events[1]["tool"])
        self.assertEqual("content", events[2]["type"])

    def test_bof_tree_reply_preserves_hierarchy_instead_of_flat_feature_list(self):
        result = {
            "status": "success",
            "data": {
                "result": {
                    "success": True,
                    "data": {
                        "taotong.prt": {
                            "A侧": {
                                "A侧": {
                                    "端面": {
                                        "端面": {
                                            "轴端面2": {
                                                "轴端面2": {
                                                    "粗车": {"粗车": {}},
                                                    "半精车": {"半精车": {}},
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                }
            },
        }

        reply = MiniAgent._format_bof_tree_reply(result)

        self.assertIn("BOF/特征树结构", reply)
        self.assertIn("taotong.prt", reply)
        self.assertIn("└─ taotong.prt", reply)
        self.assertIn("   └─ A侧", reply)
        self.assertIn("      └─ 端面", reply)
        self.assertIn("         └─ 轴端面2", reply)
        self.assertIn("            ├─ 粗车", reply)
        self.assertIn("            └─ 半精车", reply)
        self.assertNotIn("特征节点共", reply)

    def test_process_auto_agent_keeps_existing_bof_keyword_reply_shape(self):
        with tempfile.TemporaryDirectory() as project_dir:
            Path(project_dir, "process-auto-generate-agent.md").write_text(
                "Process auto prompt", encoding="utf-8"
            )
            agent_profiles.PROJECT_AGENTS_DIR = project_dir
            agent = MiniAgent()
            agent.llm = None

            def fake_tool(function_name, params=None, timeout=None):
                return {
                    "status": "success",
                    "tool": function_name,
                    "data": {
                        "result": {
                            "success": True,
                            "data": {
                                "taotong.prt": {
                                    "A侧": {
                                        "A侧": {
                                            "端面": {
                                                "端面": {
                                                    "轴端面2": {
                                                        "轴端面2": {
                                                            "粗车": {"粗车": {}},
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                        }
                    },
                }

            agent.tool = fake_tool

            events = list(agent.stream_chat(
                "读取BOF",
                session_id="process-auto-bof-keyword",
                agent_id="process-auto-generate-agent",
            ))

        self.assertEqual("content", events[2]["type"])
        self.assertIn("特征节点共", events[2]["text"])
        self.assertNotIn("BOF/特征树结构", events[2]["text"])

    def test_stream_chat_reuses_first_pass_answer_in_single_call(self):
        # 普通流式聊天：首轮已判定无需工具，应复用本轮回答，仅发一次模型请求。
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm(
            {
                "choices": [{
                    "message": {"role": "assistant", "content": "你好，有什么可以帮你？"},
                    "finish_reason": "stop",
                }]
            },
            final_chunks=[
                {"content": "第一段", "reasoning_content": ""},
                {"content": "第二段", "reasoning_content": ""},
            ],
        )

        events = list(agent.stream_chat(
            "你好",
            session_id="status-session",
            agent_id="default",
        ))

        self.assertEqual(
            [
                ("status", "正在理解问题..."),
                ("status", "正在判断是否需要调用 3DMPS 工具..."),
                ("content", "你好，有什么可以帮你？"),
            ],
            [(event["type"], event.get("text", "")) for event in events],
        )
        # 普通聊天应只调用模型一次，且为非流式的工具判断轮。
        self.assertEqual(1, len(agent.llm.calls))
        self.assertEqual(False, agent.llm.calls[0]["stream"])

    def test_stream_chat_preserves_first_pass_reasoning_in_history(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm(
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "推理后回答",
                        "reasoning_content": "思考过程",
                    },
                    "finish_reason": "stop",
                }]
            },
        )

        events = list(agent.stream_chat(
            "解释一下",
            session_id="reasoning-session",
            agent_id="default",
        ))

        self.assertEqual(
            [
                ("status", "正在理解问题..."),
                ("status", "正在判断是否需要调用 3DMPS 工具..."),
                ("content", "推理后回答"),
            ],
            [(event["type"], event.get("text", "")) for event in events],
        )
        session_key = agent._make_session_key("reasoning-session", "default")
        history = agent.conversations.get_or_init(
            session_key, lambda: [{"role": "system", "content": ""}]
        )
        assistant_msgs = [m for m in history if m.get("role") == "assistant"]
        self.assertEqual(1, len(assistant_msgs))
        self.assertEqual("推理后回答", assistant_msgs[0].get("content"))
        self.assertEqual("思考过程", assistant_msgs[0].get("reasoning_content"))

    def test_stream_chat_with_tool_call_still_uses_two_calls(self):
        # 工具调用场景仍应发两次请求：首轮非流式工具判断 + 第二轮流式最终回答。
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm(
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "get_bof_tree",
                                "arguments": "{}",
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            },
            final_chunks=[{"content": "读取完成", "reasoning_content": ""}],
        )
        calls = []

        def fake_execute_tool(name, args, agent_id=None):
            calls.append((name, args))
            return {"status": "success", "data": {"items": []}}

        agent._execute_tool = fake_execute_tool

        events = list(agent.stream_chat(
            "请根据当前上下文处理模型数据",
            session_id="tool-two-calls-session",
            agent_id="default",
        ))

        # 仍为双调用：首轮非流式工具判断，第二轮流式最终回答。
        self.assertEqual(2, len(agent.llm.calls))
        self.assertEqual(False, agent.llm.calls[0]["stream"])
        self.assertEqual(True, agent.llm.calls[1]["stream"])
        # 工具被执行，最终回答来自第二轮流式内容。
        self.assertEqual([("get_bof_tree", {})], calls)
        self.assertEqual("tool_call", events[3]["type"])
        self.assertEqual("content", events[5]["type"])
        self.assertEqual("读取完成", events[5]["text"])

    def test_stream_chat_emits_status_before_executing_tool(self):
        agent = MiniAgent()
        agent.llm = FakeStreamingLlm(
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "get_bof_tree",
                                "arguments": "{}",
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            },
            final_chunks=[{"content": "读取完成", "reasoning_content": ""}],
        )
        calls = []

        def fake_execute_tool(name, args, agent_id=None):
            calls.append((name, args))
            return {"status": "success", "data": {"items": []}}

        agent._execute_tool = fake_execute_tool

        events = list(agent.stream_chat(
            "请根据当前上下文处理模型数据",
            session_id="tool-status-session",
            agent_id="default",
        ))

        self.assertEqual([("get_bof_tree", {})], calls)
        self.assertEqual("正在读取 3DMPS 数据...", events[2]["text"])
        self.assertEqual("tool_call", events[3]["type"])
        self.assertEqual("正在组织回复...", events[4]["text"])
        self.assertEqual("content", events[5]["type"])


if __name__ == "__main__":
    unittest.main()
