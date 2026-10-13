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
    def __init__(self):
        self.calls = []

    def call(self, name, params, timeout=None):
        self.calls.append((name, params, timeout))
        return {"status": "success", "function": name, "params": params}


class ToolAllowlistTests(unittest.TestCase):
    def test_kmrag_tool_visibility_and_execution_are_isolated_by_agent(self):
        from backend.agent_core import MiniAgent
        from backend.tool_runtime import get_tools_for_agent

        default_names = [tool["function"]["name"] for tool in get_tools_for_agent("default")]
        kmrag_names = [tool["function"]["name"] for tool in get_tools_for_agent("kmrag-knowledge-agent")]
        self.assertNotIn("kmrag_search", default_names)
        self.assertEqual(["kmrag_search"], kmrag_names)

        agent = MiniAgent()
        agent.pipe = RecordingPipe()
        result = agent._execute_tool(
            "check_3dmps_status", {}, agent_id="kmrag-knowledge-agent"
        )
        self.assertEqual("TOOL_NOT_ALLOWED_FOR_AGENT", result.get("error_code"))
        self.assertEqual([], agent.pipe.calls)
    def test_unregistered_tool_is_rejected_before_pipe_call(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.pipe = RecordingPipe()

        result = agent.tool("unregistered_pipe_function", {"arg1": 123}, timeout=1)

        self.assertEqual("error", result.get("status"))
        self.assertEqual("TOOL_NOT_REGISTERED", result.get("error_code"))
        self.assertEqual("unregistered_pipe_function", result.get("tool"))
        self.assertEqual([], agent.pipe.calls)

    def test_raw_command_response_tool_is_not_public(self):
        from backend.tool_runtime import TOOLS

        names = [tool["function"]["name"] for tool in TOOLS]

        self.assertNotIn("do_cmdResponse_by_python", names)

    def test_fixed_command_alias_still_maps_to_pipe(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        agent.pipe = RecordingPipe()

        result = agent.tool("click_group_template_button", {}, timeout=1)

        self.assertEqual("success", result.get("status"))
        self.assertEqual([("do_cmdResponse_by_python", {"arg1": 52756}, 1)], agent.pipe.calls)


if __name__ == "__main__":
    unittest.main()
