# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "KmMpsMcpServer" / "skills" / "kmsoft-group-template" / "scripts"
SELECT_SCRIPT = SCRIPT_DIR / "select_group_template.js"


def _node12_exe():
    candidate = os.environ.get("KMAI_NODE12_EXE", "").strip()
    if not candidate or not Path(candidate).is_file():
        return None
    try:
        result = subprocess.run(
            [candidate, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return None
    version = (result.stdout or "").strip().lstrip("v")
    return candidate if result.returncode == 0 and version.startswith("12.") else None


class NodeSkillCompatibilityTests(unittest.TestCase):
    def test_all_node_skill_scripts_use_node12_module_specifiers(self):
        scripts = sorted(SCRIPT_DIR.glob("*.js"))
        self.assertTrue(scripts)
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("require('node:", text, msg=str(script))
            self.assertNotIn('require("node:', text, msg=str(script))
            self.assertNotIn("??", text, msg=str(script))

    def test_group_template_encoding_tempfiles_use_writable_runtime_directory(self):
        source = (SCRIPT_DIR / "template_core.js").read_text(encoding="utf-8")
        self.assertIn("process.env.KMAI_RUNTIME_DIR", source)
        self.assertNotIn(".codex-runtime", source)

    def test_operations_preserve_zero_and_false_values_on_node12_syntax(self):
        node_exe = os.environ.get("KMAI_NODE_EXE") or "node"
        operations = {
            "operations": [
                {"type": "set_part_param", "field": "数量", "value": 0},
                {"type": "set_part_param", "field": "启用", "value": False},
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            ops_path = Path(temp_dir) / "operations.json"
            ops_path.write_text(json.dumps(operations, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    node_exe,
                    str(SCRIPT_DIR / "apply_operations.js"),
                    "--ops",
                    str(ops_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=str(SCRIPT_DIR.parent.parent),
                check=False,
            )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        draft = json.loads(result.stdout)["draft"]
        self.assertEqual("0", draft["partParams"]["数量"])
        self.assertEqual("false", draft["partParams"]["启用"])

    @unittest.skipUnless(_node12_exe(), "Node 12.22.12 is required for the compatibility gate")
    def test_all_node_skill_scripts_parse_with_selected_runtime(self):
        node_exe = _node12_exe()
        for script in sorted(SCRIPT_DIR.glob("*.js")):
            result = subprocess.run(
                [node_exe, "--check", str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, result.returncode, msg="%s: %s" % (script, result.stderr))

    @unittest.skipUnless(_node12_exe(), "CPython host has no explicit Node 12.22.12 input")
    def test_node12_propose_and_confirm_keep_chinese_contract(self):
        node_exe = _node12_exe()
        payload = {
            "action": "propose",
            "text": "衬套类回转体零件，A侧和B侧，包含端面、外圆、孔和外环槽",
            "limit": 3,
            "browseAll": True,
        }
        proposed = self._run_node_skill("propose", payload, node_exe)
        self.assertTrue(proposed["ok"])
        self.assertTrue(proposed["candidates"])
        template_id = proposed["candidates"][0]["templateId"]
        confirmed = self._run_node_skill(
            "confirm", {"action": "confirm", "templateId": template_id}, node_exe
        )
        self.assertTrue(confirmed["ok"])
        self.assertIn("encoding=\"GB2312\"", confirmed["xml"])
        self.assertTrue(confirmed["handoff"]["completed"])

    def _run_node_skill(self, action, payload, node_exe=None):
        node_exe = node_exe or os.environ.get("KMAI_NODE_EXE") or "node"
        result = subprocess.run(
            [node_exe, str(SELECT_SCRIPT), action, "--stdin"],
            input=json.dumps(payload, ensure_ascii=False),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(SELECT_SCRIPT.parent.parent),
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual("", result.stderr)
        return json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main()
