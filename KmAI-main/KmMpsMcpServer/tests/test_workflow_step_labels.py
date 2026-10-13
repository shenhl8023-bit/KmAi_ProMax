# -*- coding: utf-8 -*-
from pathlib import Path
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_MODULE = ROOT / "frontend" / "assets" / "modules" / "workflow.js"


class WorkflowStepLabelTests(unittest.TestCase):
    def test_workflow_exposes_the_five_user_facing_step_names(self):
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("node is not available")

        script = """
const workflow = await import(%s);
const stepIds = [
  'select_group_template',
  'auto_identify_template',
  'feature_reasoning',
  'ai_process_input',
  'generate_all_model',
];
console.log(JSON.stringify(stepIds.map((stepId) => workflow.getProcessWorkflowStep(stepId).title)));
""" % json.dumps(WORKFLOW_MODULE.as_uri())
        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                "匹配分组模板",
                "自动特征识别",
                "加工方法推理",
                "工艺路线生成",
                "工序模型生成",
            ],
        )


if __name__ == "__main__":
    unittest.main()
