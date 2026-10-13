# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class PromptCapabilityTests(unittest.TestCase):
    def test_system_prompt_does_not_advertise_hidden_tools_as_available(self):
        from backend.prompts import SYSTEM_PROMPT

        unavailable_phrases = [
            "\u5bfc\u51fa PDF/Excel/GXK",
            "\u6a21\u578b\u5bf9\u6bd4",
            "\u6253\u5f00/\u5173\u95ed/\u4fdd\u5b58\u6a21\u578b",
            "\u5de5\u5e8f\u68c0\u67e5",
            "\u8bc6\u522b\u62a5\u544a",
        ]
        for phrase in unavailable_phrases:
            self.assertNotIn(phrase, SYSTEM_PROMPT)

        self.assertIn("\u5df2\u9a8c\u8bc1\u53ef\u7528", SYSTEM_PROMPT)
        self.assertIn("\u6682\u4e0d\u53ef\u7528", SYSTEM_PROMPT)
        self.assertIn("export_pdf", SYSTEM_PROMPT)
        self.assertIn("check_model_compare", SYSTEM_PROMPT)

    def test_keyword_fallback_does_not_list_hidden_tool_categories(self):
        from backend.agent_core import MiniAgent

        agent = MiniAgent()
        result = agent._keyword_match("\u4e0d\u5339\u914d\u4efb\u4f55\u5de5\u5177\u7684\u95ee\u9898")
        reply = result.get("reply", "")

        self.assertNotIn("\u5bfc\u51faPDF/Excel/GXK", reply)
        self.assertNotIn("\u6253\u5f00/\u4fdd\u5b58/\u5173\u95ed\u6a21\u578b", reply)
        self.assertNotIn("\u6a21\u578b\u5bf9\u6bd4", reply)
        self.assertIn("BOF/\u7279\u5f81", reply)
        self.assertIn("\u68c0\u67e53DMPS\u72b6\u6001", reply)


if __name__ == "__main__":
    unittest.main()
