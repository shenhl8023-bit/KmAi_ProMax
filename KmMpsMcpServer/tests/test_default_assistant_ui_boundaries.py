import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DefaultAssistantUiBoundaryTest(unittest.TestCase):
    def test_kmrag_agent_does_not_render_an_intro_panel(self):
        chat_source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")
        entry_source = (ROOT / "frontend" / "assets" / "modules" / "entry.js").read_text(encoding="utf-8")
        workflow_source = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").read_text(encoding="utf-8")

        self.assertIn("state.currentAgentId === KMRAG_AGENT_ID", chat_source)
        self.assertNotIn("showKmragKnowledgeIntro", chat_source)
        self.assertNotIn("showKmragKnowledgeIntro", entry_source)
        self.assertNotIn("showKmragKnowledgeIntro", workflow_source)
        self.assertIn(
            "dom.workflowDock.style.display = state.currentAgentId === KMRAG_AGENT_ID ? 'none' : '';",
            chat_source,
        )

    def test_process_workflow_show_restores_hidden_dock(self):
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("Node.js is required for the frontend behavior test")

        workflow_uri = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").as_uri()
        shared_uri = (ROOT / "frontend" / "assets" / "modules" / "shared.js").as_uri()
        script = f"""
const workflow = await import({json.dumps(workflow_uri)});
const shared = await import({json.dumps(shared_uri)});
shared.dom.workflowDock = {{
  style: {{ display: 'none' }},
  querySelector(selector) {{
    return selector === '.process-workflow-msg' ? {{}} : null;
  }},
  querySelectorAll() {{ return []; }},
}};
workflow.showProcessAutoWorkflow();
if (shared.dom.workflowDock.style.display !== '') {{
  throw new Error(`workflow dock remained ${{shared.dom.workflowDock.style.display}}`);
}}
"""

        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_process_auto_agent_disables_manual_chat_input(self):
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("Node.js is required for the frontend behavior test")

        chat_uri = (ROOT / "frontend" / "assets" / "modules" / "chat.js").as_uri()
        shared_uri = (ROOT / "frontend" / "assets" / "modules" / "shared.js").as_uri()
        script = f"""
const chat = await import({json.dumps(chat_uri)});
const shared = await import({json.dumps(shared_uri)});
shared.dom.agentSelect = {{
  options: [
    {{ value: 'default', text: '默认助手' }},
    {{ value: 'process-auto-generate-agent', text: '工艺自动生成智能体' }},
  ],
  selectedIndex: 0,
  get value() {{ return this.options[this.selectedIndex].value; }},
}};
shared.dom.input = {{ disabled: false, placeholder: '', focus() {{}} }};
shared.dom.sendBtn = {{ disabled: false }};
shared.dom.workflowDock = {{ innerHTML: '', style: {{ display: '' }} }};
shared.dom.log = {{ innerHTML: '', scrollTop: 0, scrollHeight: 0 }};

chat.setSelectedAgent('process-auto-generate-agent', true);
if (shared.dom.input.placeholder !== '当前工作流无需输入') {{
  throw new Error(`unexpected process auto placeholder: ${{shared.dom.input.placeholder}}`);
}}
if (!shared.dom.input.disabled) {{
  throw new Error('process auto agent left the input enabled');
}}
if (!shared.dom.sendBtn.disabled) {{
  throw new Error('process auto agent left the send button enabled');
}}

chat.setSelectedAgent('default', true);
if (shared.dom.input.disabled) {{
  throw new Error('default agent left the input disabled');
}}
if (shared.dom.sendBtn.disabled) {{
  throw new Error('default agent left the send button disabled');
}}
"""

        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_process_workflow_send_keeps_manual_send_button_disabled(self):
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("Node.js is required for the frontend behavior test")

        chat_uri = (ROOT / "frontend" / "assets" / "modules" / "chat.js").as_uri()
        shared_uri = (ROOT / "frontend" / "assets" / "modules" / "shared.js").as_uri()
        script = f"""
globalThis.window = {{ __KMAI_API_TOKEN__: '' }};
globalThis.document = {{
  createElement() {{
    const bubble = {{ className: 'bubble', innerHTML: '' }};
    return {{
      className: '',
      innerHTML: '',
      querySelector(selector) {{ return selector === '.bubble' ? bubble : null; }},
    }};
  }},
}};
const chat = await import({json.dumps(chat_uri)});
const shared = await import({json.dumps(shared_uri)});
shared.state.currentAgentId = shared.PROCESS_AUTO_AGENT_ID;
shared.dom.input = {{ disabled: true, value: '', placeholder: '', focus() {{}} }};
shared.dom.sendBtn = {{ disabled: true }};
shared.dom.log = {{ appendChild() {{}}, scrollTop: 0, scrollHeight: 0 }};
shared.dom.status = null;
globalThis.fetch = async function() {{ throw new Error('expected test failure'); }};

await chat.sendProcessWorkflowPrompt('自动工作流提示');
if (!shared.dom.sendBtn.disabled) {{
  throw new Error('workflow send re-enabled the manual send button');
}}
"""

        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_default_intro_only_renders_for_default_agent(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertIn("state.currentAgentId === 'default' && _showDefaultAssistantIntro", source)
        self.assertNotIn("if (_showDefaultAssistantIntro) {\n    _showDefaultAssistantIntro();", source)

    def test_default_intro_survives_agent_reload_with_existing_chat_log(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertIn("const shouldShowDefaultIntro = state.currentAgentId === 'default' && _showDefaultAssistantIntro;", source)
        self.assertIn("if (shouldShowDefaultIntro) {\n      _showDefaultAssistantIntro();", source)
        self.assertNotIn("if (!restoredLog && state.currentAgentId === 'default' && _showDefaultAssistantIntro)", source)

    def test_agent_switch_preserves_page_session_id(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertNotIn("resetSession", source)

    def test_agent_switch_saves_and_restores_log_by_agent(self):
        shared_source = (ROOT / "frontend" / "assets" / "modules" / "shared.js").read_text(encoding="utf-8")
        chat_source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertIn("agentLogSnapshots: {}", shared_source)
        self.assertIn("function saveCurrentAgentLog()", chat_source)
        self.assertIn("function restoreAgentLog(agentId)", chat_source)
        self.assertIn("saveCurrentAgentLog();", chat_source)
        self.assertIn("restoreAgentLog(state.currentAgentId)", chat_source)
        self.assertIn("const agentChanged = selectedAgentId !== previousAgentId;", chat_source)
        self.assertNotIn("if (hadProcessWorkflow || dom.log.querySelector('.process-workflow-msg'))", chat_source)
        self.assertNotIn("clearLog();", chat_source)

    def test_agent_names_use_loaded_agent_map_instead_of_selected_option_first(self):
        shared_source = (ROOT / "frontend" / "assets" / "modules" / "shared.js").read_text(encoding="utf-8")
        chat_source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertIn("agentNamesById: {}", shared_source)
        self.assertIn("state.agentNamesById[agent.id || 'default'] = agent.name || agent.id || 'default';", chat_source)
        self.assertIn("const mappedName = state.agentNamesById[state.currentAgentId];", chat_source)
        self.assertIn("if (mappedName) return mappedName;", chat_source)

    def test_agent_switch_does_not_add_chat_notice(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "chat.js").read_text(encoding="utf-8")

        self.assertNotIn("已切换智能体", source)
        self.assertNotIn("addBotMsg('已切换智能体", source)
        self.assertNotIn("if (_showProcessAutoWorkflow) _showProcessAutoWorkflow();\n    return;", source)

    def test_default_intro_does_not_expose_process_auto_internal_id(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").read_text(encoding="utf-8")

        self.assertIn("请切换到工艺自动生成智能体", source)
        self.assertNotIn("process-auto-generate-agent 智能体", source)


    def test_process_workflow_run_all_button_uses_dynamic_contiguous_progress(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").read_text(encoding="utf-8")

        self.assertIn("function getProcessWorkflowAutoStartIndex()", source)
        self.assertIn("function getProcessWorkflowRunAllLabel()", source)
        self.assertIn("function clearProcessWorkflowDoneStepsFromIndex(startIndex)", source)
        self.assertIn("getProcessWorkflowRunAllLabel()", source)
        self.assertIn("const startIndex = getProcessWorkflowAutoStartIndex();", source)
        self.assertIn("for (let i = startIndex; i < PROCESS_AUTO_WORKFLOW_STEPS.length; i += 1)", source)
        self.assertNotIn("continueFromStepId ? '继续执行2-5步' : '一键执行1-5步'", source)

    def test_ai_process_input_retry_window_allows_slow_inference(self):
        process_route_source = (ROOT / "frontend" / "assets" / "modules" / "process_route.js").read_text(encoding="utf-8")
        workflow_source = (ROOT / "frontend" / "assets" / "modules" / "workflow.js").read_text(encoding="utf-8")

        self.assertIn("maxRetries: 30", process_route_source)
        self.assertIn("retryDelayMs: 3000", process_route_source)
        self.assertIn("waitForProcessWorkflowStepDone(stepId, 900000)", workflow_source)
        self.assertIn("已重试 ' + PROCESS_RETRY_CONFIG.maxRetries + ' 次", process_route_source)

    def test_ai_process_input_json_receipt_forces_route_panel_open(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "process_route.js").read_text(encoding="utf-8")

        self.assertIn("export function unlockProcessRoutePanelForInput(payload)", source)
        self.assertIn("openProcessRoutePanel(true);", source)

    def test_process_route_submit_surfaces_top_level_api_errors(self):
        source = (ROOT / "frontend" / "assets" / "modules" / "process_route.js").read_text(encoding="utf-8")

        self.assertIn("if (data && data.status === 'error')", source)
        self.assertIn("data.message || data.error_code || 'submit process route failed'", source)


if __name__ == "__main__":
    unittest.main()
