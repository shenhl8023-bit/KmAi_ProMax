# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
import sys
import tempfile
import textwrap
import time
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class SkillRunnerStderrPipeTests(unittest.TestCase):
    def test_runner_applies_call_specific_environment_without_mutating_parent(self):
        from skills.runner import SkillRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = os.path.join(temp_dir, "environment_skill.py")
            with open(script_path, "w", encoding="utf-8") as fp:
                fp.write(textwrap.dedent(
                    """
                    import json
                    import os
                    import sys

                    sys.stdin.buffer.read()
                    print(json.dumps({"value": os.environ.get("KMRAG_TEST_VALUE")}))
                    """
                ).lstrip())

            runner = SkillRunner({
                "name": "environment",
                "tool_name": "environment_skill",
                "command": sys.executable,
                "args": [script_path],
            })
            previous = os.environ.pop("KMRAG_TEST_VALUE", None)
            try:
                self.assertEqual(
                    {"value": "call-only"},
                    runner.run({}, env_overrides={"KMRAG_TEST_VALUE": "call-only"}),
                )
                self.assertNotIn("KMRAG_TEST_VALUE", os.environ)
            finally:
                if previous is not None:
                    os.environ["KMRAG_TEST_VALUE"] = previous

    def test_skill_with_large_stderr_still_returns_stdout_json(self):
        from skills.runner import SkillRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = os.path.join(temp_dir, "noisy_skill.py")
            with open(script_path, "w", encoding="utf-8") as fp:
                fp.write(textwrap.dedent(
                    """
                    import json
                    import sys

                    sys.stdin.buffer.read()
                    sys.stderr.buffer.write(b"x" * (1024 * 1024))
                    sys.stderr.buffer.flush()
                    sys.stdout.write(json.dumps({"ok": True, "value": 42}))
                    sys.stdout.flush()
                    """
                ).lstrip())

            runner = SkillRunner({
                "name": "noisy",
                "tool_name": "noisy_skill",
                "command": sys.executable,
                "args": [script_path],
                "timeout": 2,
            })

            self.assertEqual({"ok": True, "value": 42}, runner.run({"payload": "test"}))

    def test_skill_with_oversized_stdout_is_killed_before_timeout(self):
        from skills import runner as runner_module
        from skills.runner import SkillRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = os.path.join(temp_dir, "oversized_stdout_skill.py")
            with open(script_path, "w", encoding="utf-8") as fp:
                fp.write(textwrap.dedent(
                    """
                    import sys
                    import time

                    sys.stdin.buffer.read()
                    while True:
                        sys.stdout.buffer.write(b"x" * 65536)
                        sys.stdout.buffer.flush()
                        time.sleep(0.01)
                    """
                ).lstrip())

            runner = SkillRunner({
                "name": "oversized",
                "tool_name": "oversized_stdout_skill",
                "command": sys.executable,
                "args": [script_path],
                "timeout": 5,
            })

            original_limit = runner_module.MAX_OUTPUT_SIZE
            runner_module.MAX_OUTPUT_SIZE = 128 * 1024
            started_at = time.time()
            try:
                with self.assertRaisesRegex(RuntimeError, "返回数据超过限制"):
                    runner.run({"payload": "test"})
            finally:
                runner_module.MAX_OUTPUT_SIZE = original_limit

            self.assertLess(time.time() - started_at, 3.0)


if __name__ == "__main__":
    unittest.main()
