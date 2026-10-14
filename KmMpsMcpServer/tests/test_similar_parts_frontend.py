# -*- coding: utf-8 -*-
from pathlib import Path
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend" / "assets"


class SimilarPartsFrontendTests(unittest.TestCase):
    def test_interrupted_index_query_resumes_when_panel_is_reopened(self):
        source = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        self.assertIn("panel.__resumeQuery = runQuery", source)
        self.assertIn("activePanel.__queryPending", source)
        self.assertIn("activePanel.__resumeQuery()", source)
        self.assertIn("panel.__queryRunning", source)

    def test_camera_fit_keeps_bounding_sphere_inside_narrow_half_viewport(self):
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("node is not available")
        scale_policy = ASSETS / "modules" / "similar_parts_scale.js"
        script = """
const scale = await import(%s);
console.log(JSON.stringify({
  square: scale.cameraFitDistance(10, 1, 60),
  narrow: scale.cameraFitDistance(10, 0.5, 60),
  wide: scale.cameraFitDistance(10, 2, 60),
}));
""" % json.dumps(scale_policy.as_uri())
        result = subprocess.run([node_executable, "--input-type=module", "--eval", script],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertAlmostEqual(payload["square"], 22)
        self.assertEqual(payload["wide"], payload["square"])
        self.assertGreater(payload["narrow"], 36.06)
        self.assertLess(payload["narrow"], 40)

    def test_shape_mode_normalizes_longest_extent_and_actual_mode_preserves_scale(self):
        scale_policy = ASSETS / "modules" / "similar_parts_scale.js"
        self.assertTrue(scale_policy.is_file(), "相似件模型缩放策略模块不存在")
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("node is not available")
        script = """
const scale = await import(%s);
const current = scale.uniformScaleForExtents([200, 40, 40], 'shape');
const candidate = scale.uniformScaleForExtents([50, 20, 20], 'shape');
console.log(JSON.stringify({
  defaultMode: scale.DEFAULT_SCALE_MODE,
  current,
  candidate,
  currentLongest: 200 * current,
  candidateLongest: 50 * candidate,
  actual: scale.uniformScaleForExtents([200, 40, 40], 'actual'),
  shapeLabel: scale.scaleModeLabel('shape'),
  actualLabel: scale.scaleModeLabel('actual'),
}));
""" % json.dumps(scale_policy.as_uri())
        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["defaultMode"], "shape")
        self.assertAlmostEqual(payload["currentLongest"], 100.0)
        self.assertAlmostEqual(payload["candidateLongest"], 100.0)
        self.assertEqual(payload["actual"], 1.0)
        self.assertEqual(payload["shapeLabel"], "形状对比 · 尺寸已归一化")
        self.assertEqual(payload["actualLabel"], "真实尺寸")

    def test_current_and_candidate_share_blue_gray_model_color(self):
        palette = ASSETS / "modules" / "similar_parts_palette.js"
        self.assertTrue(palette.is_file(), "相似件模型调色板模块不存在")
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("node is not available")
        script = """
const palette = await import(%s);
const colors = [
  palette.modelColorForSlot('current'),
  palette.modelColorForSlot('candidate'),
];
console.log(JSON.stringify(colors));
""" % json.dumps(palette.as_uri())
        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        colors = json.loads(result.stdout)
        # Bug修复#1：current（左视口）和 candidate（右视口）应使用不同颜色以便区分
        self.assertEqual(len(colors), 2, "应返回两个颜色值")
        self.assertNotEqual(colors[0], colors[1], "当前零件与候选零件应使用不同颜色")
        # 验证具体颜色值与 palette 定义一致
        self.assertEqual(colors[0], 0x4A7FC1, "当前零件应为蓝色 0x4A7FC1")
        self.assertEqual(colors[1], 0x7C4DBD, "候选零件应为紫色 0x7C4DBD")

    def test_panel_contract_and_local_model_runtime(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        css = (ASSETS / "css" / "similar_parts.css").read_text(encoding="utf-8")
        html = (ASSETS / "index.html").read_text(encoding="utf-8")

        self.assertIn("export function openSimilarPartsPanel", js)
        self.assertNotIn('type="file"', js)
        self.assertNotIn("contentBase64", js)
        self.assertNotIn("/api/similar-parts/upload", js)
        self.assertIn("/api/similar-parts/current", js)
        self.assertIn("stepModel.stp", js)
        self.assertIn("固定目录", js)
        self.assertIn("/api/similar-parts/query", js)
        self.assertIn("/api/similar-parts/apply-template", js)
        self.assertIn("candidateId", js)
        self.assertIn("AbortController", js)
        self.assertIn("requestSequence", js)
        self.assertIn("geometry.dispose()", js)
        self.assertIn("material.dispose()", js)
        self.assertIn("renderer.setScissor", js)
        self.assertIn("normalizePartOrientation", js)
        self.assertIn("setFromUnitVectors", js)
        self.assertIn("CANONICAL_PART_AXIS", js)
        self.assertIn("endpointRadius", js)
        self.assertIn("dom.similarPartsPanel", js)
        self.assertIn("dom.similarPartsPanelBackdrop", js)
        self.assertIn("similarPartsPanelBackdrop", html)
        self.assertIn("similarPartsPanel", html)
        self.assertNotIn("similar-parts-msg", js)
        self.assertIn("上一件", js)
        self.assertIn("下一件", js)
        self.assertIn("应用当前分组模板", js)
        self.assertIn("正在生成当前零件三维预览", js)
        self.assertNotIn("setInterval", js)
        self.assertIn("@media (max-width: 820px)", css)
        self.assertNotIn("color-mix(", css)
        self.assertIn('"three": "/similar-assets/three/build/three.module.js"', html)
        self.assertNotIn("https://", js + css)

    def test_query_uses_backend_configured_candidate_count(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")

        self.assertIn('data-role="candidate-count"', js)
        self.assertIn("result.candidates.length", js)
        self.assertNotIn("topK:", js)
        self.assertNotIn("Top 3 候选", js)
        self.assertNotIn("Top 5 候选", js)

    def test_query_prepares_feature_index_and_polls_public_progress(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        self.assertIn("/api/similar-parts/index/ensure", js)
        self.assertIn("/api/similar-parts/index/status", js)
        self.assertIn("FEATURE_INDEX_BUILDING", js)
        self.assertIn("completed", js)
        self.assertIn("total", js)
        self.assertIn("setTimeout", js)
        self.assertNotIn("setInterval", js)

    def test_recommended_template_row_places_edit_action_next_to_mapped_template(self):
        helper = ASSETS / "modules" / "similar_parts_template_ui.js"
        self.assertTrue(helper.is_file(), "推荐模板交互模块不存在")
        node_executable = shutil.which("node")
        if not node_executable:
            self.skipTest("node is not available")
        script = """
const ui = await import(%s);
const candidate = { candidateId: 'candidate-1', template: { name: '套筒类模板.xml' } };
const edited = { filename: '套筒类模板-已编辑.xml', xml: '<Kmsoft/>' };
console.log(JSON.stringify({
  markup: ui.recommendedTemplateRowMarkup(),
  originalLabel: ui.recommendedTemplateLabel(candidate, null),
  editedLabel: ui.recommendedTemplateLabel(candidate, edited),
  payload: ui.buildTemplateApplyPayload('upload-1', candidate, edited),
}));
""" % json.dumps(helper.as_uri())
        result = subprocess.run(
            [node_executable, "--input-type=module", "--eval", script],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn('class="similar-parts-tmpl-row"', payload["markup"])
        self.assertIn('data-role="template-name"', payload["markup"])
        self.assertIn('data-role="edit-template"', payload["markup"])
        self.assertIn('data-role="template-edited"', payload["markup"])
        self.assertLess(
            payload["markup"].index('data-role="template-name"'),
            payload["markup"].index('data-role="edit-template"'),
        )
        self.assertEqual(payload["originalLabel"], "套筒类模板.xml")
        self.assertEqual(payload["editedLabel"], "套筒类模板-已编辑.xml")
        self.assertEqual(payload["payload"]["candidateId"], "candidate-1")
        self.assertEqual(payload["payload"]["editedTemplate"], {
            "filename": "套筒类模板-已编辑.xml", "xml": "<Kmsoft/>"
        })

    def test_template_edit_handler_survives_repeated_clicks_and_candidate_switches(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        self.assertNotIn("}, { once: true });", js)
        edit_handler = js.split("[data-role=\"edit-template\"]", 1)[-1]
        self.assertIn("candidateId: candidate.candidateId", edit_handler)
        self.assertIn("function editCurrentTemplate", js)

    def test_similar_part_template_editor_hides_irrelevant_confidence_row(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        tool_call = (ASSETS / "modules" / "tool_call.js").read_text(encoding="utf-8")
        self.assertIn("hideConfidence: true", js)
        self.assertIn("data.hideConfidence", tool_call)
        self.assertIn("匹配置信度", tool_call)

    def test_similar_part_template_editor_uses_compact_structure_only_mode(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        tool_call = (ASSETS / "modules" / "tool_call.js").read_text(encoding="utf-8")
        self.assertIn("compactStructureOnly: true", js)
        self.assertIn("data.compactStructureOnly", tool_call)
        self.assertIn("基础信息", tool_call)

    def test_vs_badge_is_centered_by_divider_flex_layout_without_double_shift(self):
        css = (ASSETS / "css" / "similar_parts.css").read_text(encoding="utf-8")
        badge = css.split(".sp-vs-badge", 1)[1].split("}", 1)[0]
        divider = css.split(".similar-parts-divider", 1)[1].split("}", 1)[0]
        self.assertIn("justify-content: center", divider)
        self.assertNotIn("translateX", badge)

    def test_workflow_step_one_opens_similar_parts_and_keeps_existing_step_id(self):
        workflow = (ASSETS / "modules" / "workflow.js").read_text(encoding="utf-8")
        web_page = (ROOT / "frontend" / "web_page.py").read_text(encoding="utf-8")

        self.assertIn("{ id: 'select_group_template', title: '匹配分组模板'", workflow)
        self.assertIn("openSimilarPartsPanel", workflow)
        self.assertIn("step.id === 'select_group_template' && !state.processWorkflowState.runningAll", workflow)
        self.assertIn("从固定目录读取当前零件 XML", workflow)
        self.assertIn("similar_parts.css", web_page)

    def test_template_match_copy_distinguishes_task_title_from_query_action(self):
        workflow = (ASSETS / "modules" / "workflow.js").read_text(encoding="utf-8")
        similar_parts = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")

        self.assertIn("addUserMsg('匹配分组模板')", workflow)
        self.assertNotIn("addUserMsg('查询相似零件')", workflow)
        self.assertIn('aria-label="查询相似零件，匹配分组模板"', similar_parts)
        self.assertIn("<h2>查询相似零件，匹配分组模板</h2>", similar_parts)
        self.assertIn("↻ 重新查询</button>", similar_parts)

    def test_similar_parts_uses_independent_panel_layer(self):
        js = (ASSETS / "modules" / "similar_parts.js").read_text(encoding="utf-8")
        css = (ASSETS / "css" / "similar_parts.css").read_text(encoding="utf-8")
        self.assertIn("showPanel", js)
        self.assertIn("hidePanel", js)
        self.assertIn("markProcessWorkflowStepIdle", js)
        self.assertIn("panel.__closing", js)
        self.assertIn("similar-parts-panel-backdrop", css)
        self.assertIn("similar-parts-panel-overlay", css)


if __name__ == "__main__":
    unittest.main()
