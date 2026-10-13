import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PLACEHOLDER = "例如：读取当前BOF"
OLD_PLACEHOLDER = "例如：读取当前BOF / 生成工艺路线 / 打开模型 D:\\\\test.prt"


class ChatInputPlaceholderTest(unittest.TestCase):
    def test_initial_input_placeholder_keeps_only_read_current_bof_example(self):
        source = (ROOT / "frontend" / "assets" / "index.html").read_text(encoding="utf-8")
        match = re.search(r'<input id="input"[^>]*placeholder="([^"]+)"', source)

        self.assertIsNotNone(match)
        self.assertEqual(EXPECTED_PLACEHOLDER, match.group(1))
        self.assertNotIn(OLD_PLACEHOLDER, source)

    def test_agent_switch_placeholder_keeps_only_read_current_bof_example(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertIn(f"dom.input.placeholder = '{EXPECTED_PLACEHOLDER}';", source)
        self.assertNotIn(OLD_PLACEHOLDER, source)
        self.assertIn("state.currentAgentId === KMRAG_AGENT_ID", source)
        self.assertIn("例如：查询公司的供应商准入流程", source)


if __name__ == "__main__":
    unittest.main()
