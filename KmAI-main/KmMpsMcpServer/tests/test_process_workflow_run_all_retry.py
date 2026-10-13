# -*- coding: utf-8 -*-
"""一键执行工作流：第 2 步前置检查失败后 fail-fast，避免旧循环复活导致第 3 步被并发触发两次。

对应回归：`runProcessAutoIdentifyAutoStep` 原先 fire-and-forget 触发
`runProcessAutoIdentifySelection()` 后挂在 `waitForProcessWorkflowStepDone('auto_identify_template', 60000)`
上。前置检查失败时 `markAutoIdentifyRetryState()` 会把运行标志清空，允许用户立即点
“一键执行2-5步”；第二次运行把第 2 步置 done 后，第一次（未退出）的循环也会被唤醒，
两条循环并发执行第 3 步，导致 `ai_feature_inference`（自动推理特征加工方法）被调用两次。
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_URI = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").as_uri()
SHARED_URI = (ROOT / "frontend" / "assets" / "modules" / "shared.js").as_uri()

# 与 workflow.js resetProcessWorkflowState 保持一致的初始状态。
INITIAL_WORKFLOW_STATE = {
    "activeStepId": "select_group_template",
    "runningStepId": "",
    "awaitingStepId": "",
    "runningAll": False,
    "waitingUserStepId": "",
    "autoSubmittedRoute": False,
    "autoSubmittingRouteKey": "",
    "autoRouteError": "",
    "autoGeneratingTechnical": False,
    "doneStepIds": {"select_group_template": True},  # 第 1 步已完成，模拟重试场景
    "continueFromStepId": "",
}


def _run_node(script, timeout=30):
    node_executable = shutil.which("node")
    if not node_executable:
        raise unittest.SkipTest("Node.js is required for the frontend behavior test")
    result = subprocess.run(
        [node_executable, "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )
    return result


class ProcessWorkflowRunAllRetryTest(unittest.TestCase):
    def test_run_all_fails_fast_when_auto_identify_precheck_missing(self):
        # 一键执行循环必须在第 2 步前置检查失败时立即停止：
        #   - 不挂 60s，立即让用户看到“一键执行已停止”并可从第 2 步重试；
        #   - 不再触发第 3 步 `ai_feature_inference`（旧代码会因旧循环复活而触发两次）。
        script = """
globalThis.window = { __KMAI_API_TOKEN__: '', setTimeout: setTimeout };
globalThis.document = {
  createElement() {
    return { className: '', innerHTML: '', appendChild() {}, querySelector() { return null; } };
  },
};

const calledFunctions = [];
globalThis.XMLHttpRequest = class {
  constructor() { this.headers = {}; }
  open() {}
  setRequestHeader(k, v) { this.headers[k] = v; }
  send(body) {
    const req = JSON.parse(body);
    calledFunctions.push(req.function);
    setTimeout(() => {
      this.status = 200;
      this.responseText = JSON.stringify({
        status: 'error',
        message: '自动识别前置检查未通过：原点、主方向1 尚未指定。',
        error_code: 'AUTOIDENTIFY_ROOT_PARAMS_MISSING',
      });
      this.onload();
    }, 0);
  }
};

const workflow = await import('""" + WORKFLOW_URI + """');
const shared = await import('""" + SHARED_URI + """');
shared.dom.log = { appendChild() {}, scrollTop: 0, scrollHeight: 0, innerHTML: '' };
shared.dom.status = { innerHTML: '' };
shared.dom.workflowDock = { querySelectorAll() { return []; } };
shared.state.processWorkflowState = """ + json.dumps(INITIAL_WORKFLOW_STATE, ensure_ascii=False) + """;

const startedAt = Date.now();
let completed = false;
try {
  await workflow.runProcessWorkflowAllSteps();
  completed = true;
} catch (e) {
  throw new Error('runProcessWorkflowAllSteps should catch step failures: ' + e.message);
}
const elapsedMs = Date.now() - startedAt;

if (elapsedMs > 10000) {
  throw new Error('run all did not fail fast on pre-check failure: took ' + elapsedMs + 'ms');
}
if (calledFunctions.indexOf('open_and_confirm_autoidentify_dialog') === -1) {
  throw new Error('auto identify dialog was never requested');
}
if (calledFunctions.indexOf('ai_feature_inference') !== -1) {
  throw new Error('ai_feature_inference must not run after step-2 pre-check failure');
}
const ws = shared.state.processWorkflowState;
if (ws.runningAll) {
  throw new Error('runningAll should be false after fail-fast stop');
}
if (!ws.doneStepIds['select_group_template']) {
  throw new Error('step 1 done flag lost; retry should continue from step 2');
}
if (ws.activeStepId !== 'auto_identify_template') {
  throw new Error('active step should be auto_identify_template for retry, got ' + ws.activeStepId);
}
"""

        result = _run_node(script)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_auto_identify_auto_step_awaits_selection_promise(self):
        # 契约：第 2 步的自动执行必须 await 选择 Promise，使前置检查失败直接向上抛，
        # 而不是挂在 waitForProcessWorkflowStepDone 上（这正是旧循环复活并发触发第 3 步的根源）。
        source = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").read_text(encoding="utf-8")

        self.assertIn("await runProcessAutoIdentifySelection();", source)
        self.assertNotIn("waitForProcessWorkflowStepDone('auto_identify_template', 60000)", source)


if __name__ == "__main__":
    unittest.main()
