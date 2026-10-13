# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import re
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class FrontendAssetsTests(unittest.TestCase):
    def test_release_assets_do_not_ship_legacy_app_bundle(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        modules_dir = os.path.join(assets_dir, "modules")

        self.assertFalse(os.path.exists(os.path.join(assets_dir, "app.js")))
        self.assertTrue(os.path.isfile(os.path.join(modules_dir, "entry.js")))

    def test_build_index_html_uses_only_module_entry_script(self):
        from frontend.web_page import build_index_html

        html = build_index_html(llm_enabled=True)
        script_srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)

        self.assertEqual(["/assets/modules/entry.js"], script_srcs)
        self.assertIn(
            '<script type="module" src="/assets/modules/entry.js"></script>',
            html,
        )
        self.assertNotIn("/assets/app.js", html)
        self.assertNotIn("{{app_js}}", html)

    def test_process_workflow_does_not_render_resize_tip_badge(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        workflow_js_path = os.path.join(assets_dir, "modules", "workflow.js")
        workflow_css_path = os.path.join(assets_dir, "css", "workflow.css")

        with open(workflow_js_path, "r", encoding="utf-8") as f:
            workflow_js = f.read()
        with open(workflow_css_path, "r", encoding="utf-8") as f:
            workflow_css = f.read()

        self.assertNotIn("process-workflow-resize-tip", workflow_js)
        self.assertNotIn("process-workflow-resize-tip", workflow_css)

    def test_process_workflow_reset_clears_current_window_context(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        workflow_js_path = os.path.join(assets_dir, "modules", "workflow.js")

        with open(workflow_js_path, "r", encoding="utf-8") as f:
            workflow_js = f.read()

        self.assertIn("resetSession", workflow_js)
        self.assertIn("clearLog", workflow_js)
        reset_handler_match = re.search(
            r"resetWorkflowBtn\.addEventListener\('click', function\(ev\) \{(?P<body>.*?)\n    \}\s*\);",
            workflow_js,
            re.S,
        )
        self.assertIsNotNone(reset_handler_match)
        reset_handler = reset_handler_match.group("body")
        self.assertIn("resetSession();", reset_handler)
        self.assertIn("clearLog();", reset_handler)

    def test_default_assistant_uses_intro_card_instead_of_process_workflow(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        chat_js_path = os.path.join(assets_dir, "modules", "chat.js")
        entry_js_path = os.path.join(assets_dir, "modules", "entry.js")
        workflow_js_path = os.path.join(assets_dir, "modules", "workflow.js")
        workflow_css_path = os.path.join(assets_dir, "css", "workflow.css")

        with open(chat_js_path, "r", encoding="utf-8") as f:
            chat_js = f.read()
        with open(entry_js_path, "r", encoding="utf-8") as f:
            entry_js = f.read()
        with open(workflow_js_path, "r", encoding="utf-8") as f:
            workflow_js = f.read()
        with open(workflow_css_path, "r", encoding="utf-8") as f:
            workflow_css = f.read()

        self.assertIn("let _showDefaultAssistantIntro = null;", chat_js)
        self.assertIn("_showDefaultAssistantIntro = deps.showDefaultAssistantIntro;", chat_js)
        self.assertIn("_showDefaultAssistantIntro", chat_js)
        self.assertIn("showDefaultAssistantIntro", entry_js)
        self.assertNotIn("showKmragKnowledgeIntro", entry_js)
        self.assertIn("export function showDefaultAssistantIntro", workflow_js)
        self.assertIn("default-assistant-intro", workflow_js)
        self.assertIn(".default-assistant-intro", workflow_css)
        self.assertNotIn("濮嬬粓鏄剧ず鍥哄畾宸ヤ綔娴?dock", chat_js)
        self.assertNotIn("椤甸潰鍔犺浇鏃跺厛鎶婂浐瀹氬伐浣滄祦娓叉煋鍑烘潵", entry_js)


    def test_chat_stream_status_events_update_temporary_bot_bubble(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        chat_js_path = os.path.join(assets_dir, "modules", "chat.js")
        chat_css_path = os.path.join(assets_dir, "css", "chat.css")

        with open(chat_js_path, "r", encoding="utf-8") as f:
            chat_js = f.read()
        with open(chat_css_path, "r", encoding="utf-8") as f:
            chat_css = f.read()

        self.assertIn("function renderStreamStatus(text)", chat_js)
        self.assertIn("obj.type === 'status'", chat_js)
        self.assertIn("renderStreamStatus(obj.text || '正在处理...');", chat_js)
        self.assertIn("setStatus('warn', obj.text || '正在处理...');", chat_js)
        self.assertIn("stream-status", chat_js)
        self.assertIn(".stream-status", chat_css)
        self.assertIn("正在理解问题...", chat_js)
        self.assertIn("let fullText = '';\n\n  function renderStreamStatus(text)", chat_js)
        self.assertNotIn("function renderStreamStatus(text) {\n    const bubble = botDiv.querySelector('.bubble');\n    if (!bubble || fullText) return;", chat_js[:chat_js.find("let fullText = '';")])


    def test_process_route_table_centers_headers_and_shows_feature_context(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        route_js_path = os.path.join(assets_dir, "modules", "process_route.js")
        route_css_path = os.path.join(assets_dir, "css", "process_route.css")

        with open(route_js_path, "r", encoding="utf-8") as f:
            route_js = f.read()
        with open(route_css_path, "r", encoding="utf-8") as f:
            route_css = f.read()

        self.assertIn("formatProcessRouteFeatureText(groupName, featureName)", route_js)
        self.assertIn("pr-feature-group", route_js)
        self.assertIn("pr-feature-name", route_js)
        self.assertIn("pr-index-cell", route_js)
        self.assertIn("pr-name-cell", route_js)
        self.assertIn("pr-type-cell", route_js)
        self.assertIn('style="width:76px;">类型', route_js)
        self.assertIn('style="width:220px;">特征', route_js)
        self.assertIn(".table-card thead th", route_css)
        self.assertIn("text-align: center", route_css)
        self.assertIn(".table-card tbody td:nth-child(-n+3)", route_css)
        self.assertIn(".table-card .tag", route_css)
        self.assertNotIn("background: #f3f6fa", route_css)
        self.assertNotIn("font-weight: 700;\n}", route_css[route_css.find(".table-card .tag"):route_css.find(".table-card .pr-feature-cell")])
        self.assertIn("color: var(--color-primary-strong)", route_css)
        self.assertNotIn(".pr-feature-line {", route_css)
        self.assertNotIn(".pr-requirement-lines .pr-cell-line", route_css)


    def test_process_route_applies_manual_defaults_to_input_form(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        route_js_path = os.path.join(assets_dir, "modules", "process_route.js")

        with open(route_js_path, "r", encoding="utf-8") as f:
            route_js = f.read()

        self.assertIn("function applyManualDefaultsToProcessRouteForm(payload)", route_js)
        self.assertIn("payload.manual_defaults || payload.manual || payload['\\u4eba\\u5de5\\u8865\\u5145']", route_js)
        self.assertIn("const PROCESS_ROUTE_MANUAL_DEFAULTS = {", route_js)
        self.assertIn("material_grade: '9Cr18'", route_js)
        self.assertIn(r"part_type: '\u886c\u5957'", route_js)
        self.assertIn(r"heat_treatment: '\u6dec\u706b'", route_js)
        self.assertIn(r"inspection_items: ['\u88c2\u7eb9\u68c0\u6d4b']", route_js)
        self.assertIn(r"marking_methods: ['\u6807\u5370']", route_js)
        self.assertIn("function applyProcessRouteManualDefaults(manual)", route_js)
        self.assertIn(r"partType === '\u56de\u8f6c\u4f53'", route_js)
        self.assertIn("function setProcessRouteSelectValue(selectEl, value, fallbackValue)", route_js)
        self.assertIn("option.dataset.manualDefault = 'true';", route_js)
        self.assertIn("setProcessRouteSelectValue(dom.processRouteMaterialGrade, manual.material_grade, PROCESS_ROUTE_MANUAL_DEFAULTS.material_grade);", route_js)
        self.assertIn("setProcessRouteSelectValue(dom.processRoutePartType, manual.part_type, PROCESS_ROUTE_MANUAL_DEFAULTS.part_type);", route_js)
        self.assertIn("setProcessRouteSelectValue(dom.processRouteHeatTreatment, manual.heat_treatment, PROCESS_ROUTE_MANUAL_DEFAULTS.heat_treatment);", route_js)
        self.assertIn("setProcessRouteSelectValue(dom.processRouteInspectionItems, manual.inspection_items[0], PROCESS_ROUTE_MANUAL_DEFAULTS.inspection_items[0]);", route_js)
        self.assertIn("setProcessRouteSelectValue(dom.processRouteMarkingMethods, manual.marking_methods[0], PROCESS_ROUTE_MANUAL_DEFAULTS.marking_methods[0]);", route_js)
        self.assertIn("const targetValue = normalized && fallback && !hasOption(normalized) ? fallback : normalized;", route_js)
        self.assertIn("material_grade: materialGrade === '45' ? PROCESS_ROUTE_MANUAL_DEFAULTS.material_grade : materialGrade,", route_js)
        self.assertIn("shaped_hole_or_cut_flat: rawFlags.shaped_hole_or_cut_flat === true || defaultFlags.shaped_hole_or_cut_flat,", route_js)
        self.assertIn("dom.processRouteFlagShapedHole.checked = !!flags.shaped_hole_or_cut_flat;", route_js)
        self.assertIn("dom.processRouteFlagPostStageHole.checked = !!flags.post_stage_added_hole;", route_js)
        self.assertIn("applyManualDefaultsToProcessRouteForm(payload);", route_js)


    def test_process_route_waits_for_user_generate_and_submit_during_run_all(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        route_js_path = os.path.join(assets_dir, "modules", "process_route.js")
        workflow_js_path = os.path.join(assets_dir, "modules", "workflow.js")

        with open(route_js_path, "r", encoding="utf-8") as f:
            route_js = f.read()
        with open(workflow_js_path, "r", encoding="utf-8") as f:
            workflow_js = f.read()

        self.assertNotIn("function autoGenerateAndSubmitProcessRoute()", route_js)
        self.assertIn("function shouldAutoGenerateTechnicalAfterUserRoute()", route_js)
        self.assertIn("function maybeAutoGenerateTechnicalAfterUserRoute()", route_js)
        self.assertIn("maybeAutoGenerateTechnicalAfterUserRoute();", route_js)
        self.assertNotIn("await generateProcessRoute();", route_js)
        self.assertIn("await generateTechnicalRequirements();", route_js)
        self.assertNotIn("await submitLatestProcessRoute();", route_js)
        self.assertIn("state.processWorkflowState.runningAll", route_js)
        self.assertIn("state.processWorkflowState.activeStepId !== 'ai_process_input'", route_js)
        self.assertIn("state.processWorkflowState.waitingUserStepId !== 'ai_process_input'", route_js)
        self.assertIn("state.processWorkflowState.autoSubmittingRouteKey", route_js)
        self.assertIn("state.processWorkflowState.autoRouteError", route_js)
        self.assertIn("请确认参数后点击生成工艺路线", route_js)
        self.assertIn("技术要求已生成，请确认后点击提交工艺数据", route_js)
        self.assertIn("function scrollProcessRoutePanelToResults()", route_js)
        self.assertIn("dom.processRoutePanel.querySelector('.pr-body')", route_js)
        self.assertIn("dom.processRouteResults.querySelector('.table-card')", route_js)
        self.assertIn("target.offsetTop - scroller.offsetTop", route_js)
        self.assertIn("autoSubmittingRouteKey: ''", workflow_js)
        self.assertIn("一键执行时收到 manual_defaults 后等待用户点击生成路线", workflow_js)
        self.assertIn("提交由用户确认", workflow_js)


    def test_process_route_submit_button_feedback_resets_on_new_inputs(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        route_js_path = os.path.join(assets_dir, "modules", "process_route.js")
        shared_js_path = os.path.join(assets_dir, "modules", "shared.js")
        route_css_path = os.path.join(assets_dir, "css", "process_route.css")

        with open(route_js_path, "r", encoding="utf-8") as f:
            route_js = f.read()
        with open(shared_js_path, "r", encoding="utf-8") as f:
            shared_js = f.read()
        with open(route_css_path, "r", encoding="utf-8") as f:
            route_css = f.read()

        self.assertIn("processRouteSubmitState: 'idle'", shared_js)
        self.assertIn("processRouteSubmitMessage: ''", shared_js)
        self.assertIn("function setProcessRouteSubmitButtonState(status, message)", route_js)
        self.assertIn("function resetProcessRouteSubmitButtonState()", route_js)
        self.assertIn("function updateProcessRouteSubmitButton()", route_js)
        self.assertIn("function invalidateProcessRouteResultsAfterManualChange()", route_js)
        self.assertIn("dom.processRouteSubmitBtn.textContent = '\u63d0\u4ea4\u4e2d...';", route_js)
        self.assertIn("dom.processRouteSubmitBtn.textContent = '\u5df2\u63d0\u4ea4 \u2713';", route_js)
        self.assertIn("dom.processRouteSubmitBtn.textContent = '\u63d0\u4ea4\u5931\u8d25\uff0c\u70b9\u51fb\u91cd\u8bd5';", route_js)
        self.assertIn("dom.processRouteSubmitBtn.textContent = '\u63d0\u4ea4\u5de5\u827a\u6570\u636e';", route_js)
        self.assertIn("setProcessRouteSubmitButtonState('submitting'", route_js)
        self.assertIn("setProcessRouteSubmitButtonState('submitted'", route_js)
        self.assertIn("setProcessRouteSubmitButtonState('error'", route_js)
        self.assertIn("resetProcessRouteSubmitButtonState();", route_js)
        self.assertIn("resetProcessRouteResultView('\u53c2\u6570\u5df2\u4fee\u6539\uff0c\u8bf7\u91cd\u65b0\u751f\u6210\u5de5\u827a\u8def\u7ebf\u3002');", route_js)
        self.assertIn("const routeEmptyText = emptyText || '\u5c1a\u672a\u751f\u6210\u5de5\u827a\u8def\u7ebf\u3002';", route_js)
        self.assertIn("dom.processRouteTechnicalView.innerHTML = '<div class=\"pr-empty\">\u5c1a\u672a\u751f\u6210\u6280\u672f\u8981\u6c42\u3002</div>';", route_js)
        self.assertIn("setProcessRouteSubmitButtonState('submitting', '\u6b63\u5728\u56de\u4f20\u5de5\u827a\u8def\u7ebf\u5230 3DMPS...');", route_js)
        self.assertIn("const submitMessage = '\u5df2\u56de\u4f20\u5230 3DMPS\uff0c\u5171 ' + routeCount + ' \u6761\u5de5\u827a\u8def\u7ebf \u00b7 ' + formatProcessRouteSubmitTime();", route_js)
        self.assertIn("setStatus('ok', '\u7b2c 4 \u6b65\u5b8c\u6210\uff1aAI \u5de5\u827a\u8def\u7ebf\u548c\u6280\u672f\u8981\u6c42\u5df2\u751f\u6210\u5e76\u63d0\u4ea4');", route_js)
        self.assertIn("onParamsChange: function() { handleProcessRouteParamsChange(); }", route_js)
        self.assertIn("is-submitting", route_js)
        self.assertIn("is-submitted", route_js)
        self.assertIn("is-error", route_js)
        self.assertIn(".pr-action-row .pr-action-tertiary.is-submitted:disabled", route_css)
        self.assertIn(".pr-action-row .pr-action-tertiary.is-error", route_css)
        self.assertIn(".pr-action-row .pr-action-tertiary.is-submitting:disabled", route_css)

    def test_frontend_closes_when_km3dmps_exits_after_seen_running(self):
        assets_dir = os.path.join(SERVER_ROOT, "frontend", "assets")
        shared_js_path = os.path.join(assets_dir, "modules", "shared.js")
        entry_js_path = os.path.join(assets_dir, "modules", "entry.js")

        with open(shared_js_path, "r", encoding="utf-8") as f:
            shared_js = f.read()
        with open(entry_js_path, "r", encoding="utf-8") as f:
            entry_js = f.read()

        self.assertIn("export function startKm3dmpsExitMonitor()", shared_js)
        self.assertIn("km3dmps && km3dmps.running === true", shared_js)
        self.assertIn("state.km3dmpsExitMonitorSeenRunning", shared_js)
        self.assertIn("state.km3dmpsExitMonitorMisses", shared_js)
        self.assertIn("window.close();", shared_js)
        self.assertIn("3DMPS 已关闭，正在关闭 KMAI", shared_js)
        self.assertIn("startKm3dmpsExitMonitor", entry_js)
        self.assertIn("startKm3dmpsExitMonitor();", entry_js)

if __name__ == "__main__":
    unittest.main()
