from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TemplateCardEditorUiTest(unittest.TestCase):
    def run_group_template_skill(self, payload):
        script = ROOT / "skills" / "kmsoft-group-template" / "scripts" / "select_group_template.js"
        proc = subprocess.run(
            ["node", str(script), "propose", "--stdin"],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(script.parents[1]),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return json.loads(proc.stdout)

    def assert_file_omits_removed_editor_fields(self, relative_path):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        removed_markers = [
            "备注说明",
            "特征标签",
            'id="ed-desc"',
            'id="ed-tags"',
            'data-fld="desc"',
            'data-fld="tags"',
            "输入标签后回车",
            "回车 / 逗号添加标签",
        ]
        for marker in removed_markers:
            with self.subTest(file=relative_path, marker=marker):
                self.assertNotIn(marker, source)

    def test_template_card_editor_omits_note_and_tag_editor(self):
        for relative_path in [
            "frontend/assets/modules/tool_call.js",
            "frontend/preview-helper.js",
            "frontend/preview_edit_standalone.html",
        ]:
            self.assert_file_omits_removed_editor_fields(relative_path)

    def test_template_card_editor_uses_filename_as_only_basic_field(self):
        removed_title_markers = [
            "显示名",
            'id="ed-title"',
            'data-fld="title"',
        ]
        for relative_path in [
            "frontend/assets/modules/tool_call.js",
            "frontend/preview-helper.js",
            "frontend/preview_edit_standalone.html",
        ]:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            for marker in removed_title_markers:
                with self.subTest(file=relative_path, marker=marker):
                    self.assertNotIn(marker, source)

    def test_template_filename_input_is_normalized_before_save(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertRegex(source, r"function\s+normalizeTemplateFilenameInput\(value\)")
        self.assertRegex(source, r"trimmed\.toLowerCase\(\)\.endsWith\('\.xml'\)")
        self.assertRegex(source, r"return\s+trimmed\s+\+\s+'\.xml'")
        self.assertRegex(source, r"function\s+deriveDisplayNameFromFilename\(filename\)")
        self.assertRegex(source, r"\.replace\(/\\\.xml\$/i,\s*''\)")
        self.assertRegex(
            source,
            r"const\s+savedFilename\s*=\s*normalizeTemplateFilenameInput\(form\.filename\)",
        )
        self.assertRegex(source, r"filename:\s*savedFilename")
        self.assertRegex(source, r"title:\s*deriveDisplayNameFromFilename\(savedFilename\)")

    def test_option_card_editor_save_is_temporary_until_apply(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        editor_body = source.split("export function openOptionCardEditor", 1)[1].split(
            "/** 从模板接口响应里把 XML 内容抽出来", 1
        )[0]
        self.assertIn("'保存'", editor_body)
        self.assertNotIn("'保存到模板库'", editor_body)
        self.assertNotIn("'/api/template/save'", editor_body)
        self.assertIn("sourceCard.__kmaiEditedTemplate", editor_body)
        self.assertRegex(
            editor_body,
            r"sourceCard\.__kmaiEditedTemplate\s*=\s*\{\s*filename:\s*savedFilename,\s*xml:\s*form\.xml\s*\}",
        )
        self.assertIn("临时保存", editor_body)

    def test_apply_group_template_sends_temporary_xml_when_present(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertRegex(source, r"function\s+getEditedTemplatePayload\(opt,\s*card\)")
        self.assertRegex(source, r"card\.__kmaiEditedTemplate")
        self.assertRegex(source, r"getTemplateCardRawName\(opt,\s*card\)")
        self.assertRegex(source, r"buildApplyGroupTemplateParams\(opt,\s*templateName,\s*card\)")
        self.assertRegex(source, r"const\s+edited\s*=\s*getEditedTemplatePayload\(opt,\s*card\)")
        self.assertRegex(source, r"params\.filename\s*=\s*edited\.filename")
        self.assertRegex(source, r"params\.xml\s*=\s*edited\.xml")

    def test_edit_button_stays_enabled_after_template_apply(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertRegex(source, r"function\s+setOptionCardEditLocked\(card,\s*locked\)")
        self.assertNotRegex(source, r"editBtn\.disabled\s*=\s*Boolean\(locked\)")
        self.assertRegex(source, r"editBtn\.classList\.toggle\('is-disabled',\s*Boolean\(locked\)\)")
        self.assertRegex(source, r"setOptionCardEditLocked\(c,\s*false\)")
        self.assertNotRegex(source, r"if\s*\(editBtn\.disabled\)\s*return")

    def test_editor_save_resets_loaded_card_to_pending_reload(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertRegex(source, r"function\s+resetOptionCardForTemplateEdit\(card\)")
        self.assertRegex(source, r"card\.classList\.remove\('is-selected'\)")
        self.assertRegex(source, r"button\.disabled\s*=\s*false")
        self.assertRegex(
            source,
            r"button\.textContent\s*=\s*getOptionCardActionText\(false,\s*card\.getAttribute\('data-group-template-only'\)\s*===\s*'1'\)",
        )
        self.assertRegex(
            source,
            r"syncOptionCardFromEditor\(sourceCard,[\s\S]*?\);\s*resetOptionCardForTemplateEdit\(sourceCard\);",
        )

    def assert_tree_toggle_arrows_use_expected_directions(self, relative_path):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"\.edit-tree-toggle svg\s*\{[^}]*transform:\s*rotate\(90deg\)",
            msg=f"{relative_path} should render the expanded tree arrow pointing down",
        )
        self.assertRegex(
            source,
            r"\.edit-tree-node\.is-collapsed\s*>\s*\.edit-tree-row\s*>\s*"
            r"(?:\.edit-tree-row-main\s*>\s*)?\.edit-tree-toggle svg\s*\{[^}]*transform:\s*rotate\(0deg\)",
            msg=f"{relative_path} should render the collapsed tree arrow pointing right",
        )

    def test_tree_toggle_arrows_point_right_when_collapsed_and_down_when_expanded(self):
        for relative_path in [
            "frontend/assets/css/cards.css",
            "frontend/preview_edit_standalone.html",
        ]:
            with self.subTest(file=relative_path):
                self.assert_tree_toggle_arrows_use_expected_directions(relative_path)

    def assert_inline_editor_uses_stable_tree_row_box(self, relative_path):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        style_checks = {
            ".edit-tree-row": [
                r"min-height:\s*32px",
            ],
            ".edit-tree-name": [
                r"line-height:\s*20px",
            ],
            ".edit-tree-name.is-editable": [
                r"box-sizing:\s*border-box",
                r"height:\s*22px",
                r"line-height:\s*20px",
            ],
            ".edit-tree-name-input": [
                r"box-sizing:\s*border-box",
                r"height:\s*22px",
                r"line-height:\s*20px",
            ],
            ".edit-tree-chip-v": [
                r"line-height:\s*16px",
            ],
            ".edit-tree-chip-v-input": [
                r"box-sizing:\s*border-box",
                r"height:\s*18px",
                r"line-height:\s*16px",
            ],
        }
        for selector, required_patterns in style_checks.items():
            match = re.search(re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}", source)
            self.assertIsNotNone(match, msg=f"{relative_path} is missing {selector}")
            body = match.group("body")
            for pattern in required_patterns:
                with self.subTest(file=relative_path, selector=selector, pattern=pattern):
                    self.assertRegex(body, pattern)

    def test_inline_tree_editors_keep_row_height_stable(self):
        for relative_path in [
            "frontend/assets/css/cards.css",
            "frontend/preview_edit_standalone.html",
        ]:
            with self.subTest(file=relative_path):
                self.assert_inline_editor_uses_stable_tree_row_box(relative_path)

    def css_rule_body(self, source, selector):
        match = re.search(re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}", source)
        self.assertIsNotNone(match, msg=f"Missing CSS selector: {selector}")
        return match.group("body")

    def test_option_cards_group_meta_and_actions_in_bottom_footer(self):
        for relative_path in [
            "frontend/assets/modules/tool_call.js",
            "frontend/preview-helper.js",
        ]:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(file=relative_path):
                self.assertRegex(source, r"function\s+formatOptionCardMeta\(meta\)")
                self.assertIn("source.groupCount !== undefined", source)
                self.assertIn("source.depth !== undefined", source)
                self.assertIn("结构：", source)
                self.assertIn('<div class="option-card-footer">', source)
                self.assertRegex(
                    source,
                    r"option-card-footer[\s\S]*option-card-meta[\s\S]*option-card-actions",
                )
                self.assertNotIn(" + ' ，'", source)

    def test_option_card_footer_is_pinned_and_primary_action_fills_width(self):
        for relative_path in [
            "frontend/assets/css/cards.css",
            "frontend/preview_edit_standalone.html",
        ]:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            footer = self.css_rule_body(source, ".option-card-footer")
            actions = self.css_rule_body(source, ".option-card-actions")
            with self.subTest(file=relative_path):
                self.assertRegex(footer, r"display:\s*flex")
                self.assertRegex(footer, r"flex-direction:\s*column")
                self.assertRegex(footer, r"margin-top:\s*auto")
                self.assertRegex(actions, r"margin-top:\s*0")
                self.assertIn(".option-card-actions .option-card-button", source)

    def test_standalone_preview_uses_same_footer_and_zero_safe_meta_formatter(self):
        source = (ROOT / "frontend/preview_edit_standalone.html").read_text(encoding="utf-8")
        self.assertRegex(source, r"function\s+formatOptionCardMeta\(meta\)")
        self.assertIn("source.groupCount !== undefined", source)
        self.assertIn("source.depth !== undefined", source)
        self.assertRegex(
            source,
            r"make\('div',\s*'option-card-footer'\)[\s\S]*footer\.appendChild\(actions\)[\s\S]*card\.appendChild\(footer\)",
        )

    def test_inline_tree_editor_inputs_do_not_force_layout_width(self):
        for relative_path in [
            "frontend/assets/css/cards.css",
            "frontend/preview_edit_standalone.html",
        ]:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            for selector in [".edit-tree-name-input", ".edit-tree-chip-v-input"]:
                body = self.css_rule_body(source, selector)
                with self.subTest(file=relative_path, selector=selector):
                    self.assertNotRegex(body, r"\bmin-width\s*:\s*(?:80|120)px")
                    self.assertNotRegex(body, r"\bborder\s*:\s*[^;]*solid")
                    self.assertRegex(body, r"\bwidth\s*:\s*var\(--inline-editor-width\)")
                    self.assertRegex(body, r"\bbox-shadow\s*:")

    def assert_editor_syncs_size_before_replace(self, relative_path, helper_name, name_fn, chip_fn):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        self.assertRegex(
            source,
            rf"function\s+{helper_name}\s*\(",
            msg=f"{relative_path} should define {helper_name}",
        )
        for fn_name, source_name in [(name_fn, "nameEl"), (chip_fn, "vEl")]:
            fn_match = re.search(
                rf"function\s+{fn_name}\s*\([^)]*\)\s*\{{(?P<body>[\s\S]*?)\n\}}",
                source,
            )
            self.assertIsNotNone(fn_match, msg=f"{relative_path} is missing {fn_name}")
            body = fn_match.group("body")
            with self.subTest(file=relative_path, function=fn_name):
                self.assertRegex(
                    body,
                    rf"{helper_name}\({source_name},\s*input\);[\s\S]*{source_name}\.replaceWith\(input\)",
                    msg=f"{fn_name} should lock input size before replacing {source_name}",
                )

    def test_inline_tree_editors_sync_original_element_size_before_replacing(self):
        self.assert_editor_syncs_size_before_replace(
            "frontend/assets/modules/tool_call.js",
            "syncInlineEditInputSize",
            "enterEditNameMode",
            "enterEditChipValueMode",
        )
        self.assert_editor_syncs_size_before_replace(
            "frontend/preview-helper.js",
            "syncInlineEditInputSize",
            "enterEditName",
            "enterEditChip",
        )

    def assert_tree_params_use_split_chip_rows(self, relative_path):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        self.assertIn(".edit-tree-row-main", source)
        self.assertIn(".edit-tree-chip-row", source)
        self.assertRegex(
            source,
            r"\.edit-tree-row-main\s*\{[^}]*display:\s*(?:flex|inline-flex)",
            msg=f"{relative_path} should keep node title/tools aligned on the first row",
        )
        chip_row_body = self.css_rule_body(source, ".edit-tree-chip-row")
        self.assertRegex(chip_row_body, r"\bdisplay\s*:\s*flex")
        self.assertRegex(chip_row_body, r"\bpadding-left\s*:\s*calc\(")
        self.assertRegex(chip_row_body, r"\bgap\s*:")
        chips_body = self.css_rule_body(source, ".edit-tree-chips")
        self.assertRegex(chips_body, r"\bdisplay\s*:\s*grid")
        self.assertRegex(chips_body, r"\bgrid-auto-flow\s*:\s*column")
        self.assertRegex(chips_body, r"\bgrid-auto-columns\s*:\s*minmax\(0,\s*1fr\)")
        self.assertNotRegex(
            chips_body,
            r"\bmargin-left\s*:\s*auto",
            msg=f"{relative_path} should not push expanded params into the title row",
        )
        chip_body = self.css_rule_body(source, ".edit-tree-chip")
        self.assertRegex(chip_body, r"\bwidth\s*:\s*100%")
        self.assertRegex(chip_body, r"\bmin-width\s*:\s*0")
        self.assertRegex(chip_body, r"\bmax-width\s*:\s*none")
        key_body = self.css_rule_body(source, ".edit-tree-chip-k")
        self.assertRegex(key_body, r"\bwhite-space\s*:\s*nowrap")
        value_body = self.css_rule_body(source, ".edit-tree-chip-v")
        self.assertRegex(value_body, r"\bwhite-space\s*:\s*nowrap")
        self.assertRegex(value_body, r"\boverflow\s*:\s*hidden")
        self.assertRegex(value_body, r"\btext-overflow\s*:\s*ellipsis")
        self.assertRegex(value_body, r"\bmin-width\s*:\s*0")
        for selector in [
            ".edit-tree-chip.chip-dir",
            ".edit-tree-chip.chip-mode",
            ".edit-tree-chip.chip-feat",
        ]:
            body = self.css_rule_body(source, selector)
            with self.subTest(file=relative_path, selector=selector):
                self.assertNotRegex(body, r"\bwidth\s*:")
                self.assertNotRegex(body, r"\bmax-width\s*:")
        self.assertNotIn("width: 112px", source)
        self.assertNotIn("max-width: 112px", source)
        self.assertNotIn("width: 260px", source)
        self.assertNotIn("min(260px", source)

    def test_tree_params_render_on_aligned_second_row(self):
        for relative_path in [
            "frontend/assets/css/cards.css",
            "frontend/preview_edit_standalone.html",
        ]:
            with self.subTest(file=relative_path):
                self.assert_tree_params_use_split_chip_rows(relative_path)

    def assert_tree_renderer_manages_chip_rows(self, relative_path, renderer_name):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        renderer_match = re.search(
            rf"function\s+{renderer_name}\s*\([^)]*\)\s*\{{(?P<body>[\s\S]*?)\n\}}",
            source,
        )
        self.assertIsNotNone(renderer_match, msg=f"{relative_path} is missing {renderer_name}")
        body = renderer_match.group("body")
        self.assertIn("'edit-tree-row-main'", body)
        self.assertIn(".edit-tree-chip-row", source)
        self.assertIn("appendChipRow", source)
        self.assertRegex(body, r"head\.appendChild\(mainRow\)")
        self.assertRegex(body, r"appendChipRow\(head,")
        self.assertNotRegex(
            body,
            r"head\.querySelector\('\.edit-tree-chips'\)",
            msg=f"{relative_path} should manage the whole second row, not only the chip list",
        )

    def test_tree_renderers_create_title_row_and_param_row(self):
        for relative_path, renderer_name in [
            ("frontend/assets/modules/tool_call.js", "buildEditNodeEl"),
            ("frontend/preview-helper.js", "renderNode"),
        ]:
            with self.subTest(file=relative_path):
                self.assert_tree_renderer_manages_chip_rows(relative_path, renderer_name)

    def test_template_tree_splice_matches_part_item_when_id_precedes_type(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertNotIn(
            r"<Item\s+type\s*=\s*[\"']Part[\"'][^>]*>",
            source,
            msg="Part splice regex must not require type to be the first Item attribute",
        )
        self.assertRegex(
            source,
            r"const\s+startRe\s*=\s*/<Item\\b\(\?=\[\^>\]\*\\btype\\s\*=",
            msg="Part splice regex should match type=\"Part\" in any attribute order",
        )
        self.assertRegex(
            source,
            r"buildEditTreeXml\(tree,\s*m\[0\]\)",
            msg="Splicing should preserve the original Part opening tag attributes",
        )

        part_re = re.compile(r"<Item\b(?=[^>]*\btype\s*=\s*[\"']Part[\"'])[^>]*>")
        old_part_re = re.compile(r"<Item\s+type\s*=\s*[\"']Part[\"'][^>]*>")
        samples = ROOT / "skills" / "kmsoft-group-template" / "assets" / "sample-templates"
        for xml_file in samples.glob("*.xml"):
            xml = xml_file.read_bytes().decode("gbk")
            with self.subTest(file=xml_file.name):
                self.assertIsNotNone(part_re.search(xml))
                self.assertIsNone(old_part_re.search(xml))

    def assert_tree_collapse_state_survives_rerender(self, relative_path):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"function\s+\w*ResolveNodeCollapsed",
            msg=f"{relative_path} should resolve collapse state during render",
        )
        self.assertRegex(
            source,
            r"function\s+\w*SetNodeCollapsed",
            msg=f"{relative_path} should persist node collapse changes outside the DOM",
        )
        self.assertRegex(
            source,
            r"_collapsedNodes\.set\(String\(node\.id\),\s*Boolean\(collapsed\)\)",
            msg=f"{relative_path} should store collapse state by stable node id",
        )
        self.assertRegex(
            source,
            r"classList\.toggle\('is-collapsed',\s*collapsed\)",
            msg=f"{relative_path} should render the persisted collapse value explicitly",
        )

    def test_node_move_preserves_expanded_or_collapsed_state_after_rerender(self):
        for relative_path in [
            "frontend/assets/modules/tool_call.js",
            "frontend/preview-helper.js",
        ]:
            with self.subTest(file=relative_path):
                self.assert_tree_collapse_state_survives_rerender(relative_path)

    def test_group_delete_runs_immediately_without_confirmation(self):
        files = [
            "frontend/assets/modules/tool_call.js",
            "frontend/preview-helper.js",
        ]
        for relative_path in files:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(file=relative_path):
                self.assertNotIn("confirm(", source)
                self.assertNotIn("openDeleteConfirmDialog", source)
                self.assertNotIn("确认删除", source)

        runtime_source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        preview_source = (ROOT / "frontend/preview-helper.js").read_text(encoding="utf-8")
        self.assertRegex(
            runtime_source,
            r"makeEditToolBtn\('delete',\s*'删除',\s*function\s*\(ev\)\s*\{[\s\S]*"
            r"ev\.stopPropagation\(\);[\s\S]*"
            r"editTreeDeleteNode\(tree,\s*path\);[\s\S]*"
            r"ctx\.onChange\s*&&\s*ctx\.onChange\(\);",
        )
        self.assertRegex(
            preview_source,
            r"makeToolBtn\('delete',\s*'删除',\s*function\s*\(\)\s*\{[\s\S]*"
            r"delNode\(tree,\s*path\);\s*ctx\.rerender\(\);",
        )

    def test_delete_confirm_component_and_styles_are_removed(self):
        self.assertFalse((ROOT / "frontend/assets/modules/delete_confirm.js").exists())
        css_source = (ROOT / "frontend/assets/css/cards.css").read_text(encoding="utf-8")

        for marker in [
            ".edit-delete-confirm-backdrop",
            ".edit-delete-confirm-dialog",
            ".edit-delete-confirm-button-danger",
        ]:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, css_source)

    def test_group_template_propose_can_browse_templates_excluding_current_cards(self):
        text = "壳体类多面加工零件，包含孔系、平面和通槽"
        first_page = self.run_group_template_skill({"text": text, "limit": 3})
        shown_ids = {item["id"] for item in first_page["candidates"]}
        self.assertTrue(first_page["browse"]["available"])

        browse_page = self.run_group_template_skill({
            "text": text,
            "limit": 20,
            "browseAll": True,
            "excludeTemplateIds": sorted(shown_ids),
        })
        browsed_ids = {item["id"] for item in browse_page["candidates"]}

        self.assertEqual(browse_page["browse"]["mode"], "all")
        self.assertGreater(len(browsed_ids), 0)
        self.assertTrue(shown_ids.isdisjoint(browsed_ids))

    def test_group_template_cards_include_browse_other_templates_action(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")
        self.assertIn("浏览其它模板", source)
        self.assertRegex(source, r"function\s+buildBrowseMoreGroupTemplatesButton")
        self.assertRegex(source, r"browseAll:\s*true")
        self.assertRegex(source, r"excludeTemplateIds")
        self.assertRegex(source, r"function:\s*'kmsoft_group_template_propose'")

    def test_feature_selection_uses_tree_multiselect_catalog(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")

        self.assertIn("const FEATURE_PARAM_KEY = '特征选择'", source)
        self.assertIn("requestJson('GET', '/api/feature-template'", source)
        self.assertRegex(source, r"function\s+openFeatureSelectDropdown")
        self.assertRegex(source, r"function\s+collectFeatureLeafNames")
        self.assertRegex(source, r"function\s+serializeFeatureSelection")
        self.assertRegex(source, r"input\.indeterminate\s*=")
        self.assertRegex(
            source,
            r"if\s*\(param\.k\s*===\s*FEATURE_PARAM_KEY\)\s*\{[\s\S]*openFeatureSelectDropdown",
        )
        self.assertRegex(
            source,
            r"const\s+def\s*=\s*k\s*===\s*FEATURE_PARAM_KEY\s*\?\s*''\s*:\s*\(ENUM_FIELDS\[k\]\s*\?\s*ENUM_FIELDS\[k\]\[0\]\s*:\s*''\)",
        )

    def test_feature_selection_styles_are_available(self):
        source = (ROOT / "frontend/assets/css/cards.css").read_text(encoding="utf-8")

        for selector in [
            ".feature-select-popover",
            ".feature-select-tree",
            ".feature-select-row",
            ".feature-select-actions",
        ]:
            with self.subTest(selector=selector):
                self.assertIn(selector, source)

    def test_feature_selection_rerender_preserves_tree_scroll_position(self):
        source = (ROOT / "frontend/assets/modules/tool_call.js").read_text(encoding="utf-8")

        self.assertRegex(source, r"function\s+getFeatureSelectScrollTop")
        self.assertRegex(source, r"function\s+restoreFeatureSelectScrollTop")
        self.assertRegex(
            source,
            r"const\s+previousTreeScrollTop\s*=\s*getFeatureSelectScrollTop\(pop\);[\s\S]*pop\.innerHTML\s*=\s*'';",
        )
        self.assertRegex(
            source,
            r"pop\.appendChild\(treeEl\);[\s\S]*restoreFeatureSelectScrollTop\(treeEl,\s*previousTreeScrollTop\);",
        )

    def test_preview_editor_keeps_feature_selection_selector_in_sync(self):
        source = (ROOT / "frontend/preview-helper.js").read_text(encoding="utf-8")

        self.assertIn("const FEATURE_PARAM_KEY = '特征选择'", source)
        self.assertRegex(source, r"function\s+openFeatureSelectDropdown")
        self.assertRegex(source, r"function\s+serializeFeatureSelection")
        self.assertRegex(source, r"if\s*\(param\.k\s*===\s*FEATURE_PARAM_KEY\)")
        self.assertRegex(source, r"function\s+restoreFeatureSelectScrollTop")


if __name__ == "__main__":
    unittest.main()
