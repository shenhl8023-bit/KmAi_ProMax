from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "kmsoft-group-template" / "scripts" / "select_group_template.js"
PROPOSE_SCHEMA = ROOT / "skills" / "kmsoft-group-template" / "schemas" / "propose.response.schema.json"
CONFIRM_SCHEMA = ROOT / "skills" / "kmsoft-group-template" / "schemas" / "confirm.response.schema.json"

PROPOSE_BASELINE_BYTES = 6969
PROPOSE_MAX_BYTES = int(PROPOSE_BASELINE_BYTES * 0.60)
PUBLIC_TEMPLATE_KEYS = {
    "id",
    "templateId",
    "filename",
    "displayName",
    "relativePath",
    "groupCount",
    "depth",
}
PUBLIC_CANDIDATE_KEYS = PUBLIC_TEMPLATE_KEYS | {"tags", "confidence", "reasons"}
OPTION_KEYS = {
    "id",
    "choiceId",
    "templateId",
    "filename",
    "title",
    "subtitle",
    "confidence",
    "reasons",
    "tags",
    "meta",
    "selected",
}
FORBIDDEN_PROPOSE_KEYS = {
    "sourcePath",
    "partTemplateFields",
    "groupTemplateFields",
    "groupNames",
    "featureSelections",
    "groups",
    "structureSummary",
    "score",
    "xml",
    "draft",
}
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class GroupTemplateResponseContractTest(unittest.TestCase):
    def run_skill(self, action, payload):
        proc = subprocess.run(
            ["node", str(SCRIPT), action, "--stdin"],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(SCRIPT.parents[1]),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return json.loads(proc.stdout)

    def propose_three_templates(self):
        return self.run_skill(
            "propose",
            {
                "text": "浏览全部分组模板",
                "limit": 3,
                "browseAll": True,
            },
        )

    def walk_payload(self, value, path="$"):
        if isinstance(value, dict):
            for key, child in value.items():
                yield path, key, child
                yield from self.walk_payload(child, "%s.%s" % (path, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from self.walk_payload(child, "%s[%d]" % (path, index))

    def assert_no_windows_absolute_paths(self, value):
        for path, key, child in self.walk_payload(value):
            if isinstance(child, str):
                self.assertIsNone(
                    WINDOWS_ABSOLUTE_PATH.match(child),
                    msg="absolute path leaked at %s.%s: %s" % (path, key, child),
                )

    def test_propose_returns_only_compact_public_candidate_fields(self):
        result = self.propose_three_templates()

        self.assertEqual(3, len(result["candidates"]))
        for candidate in result["candidates"]:
            self.assertEqual(PUBLIC_CANDIDATE_KEYS, set(candidate))
            self.assertEqual(candidate["id"], candidate["templateId"])
            self.assertLessEqual(len(candidate["tags"]), 6)
            self.assertFalse(Path(candidate["relativePath"]).is_absolute())
            self.assertNotIn("..", Path(candidate["relativePath"]).parts)

        all_keys = {key for _, key, _ in self.walk_payload(result)}
        self.assertTrue(FORBIDDEN_PROPOSE_KEYS.isdisjoint(all_keys))
        self.assert_no_windows_absolute_paths(result)

        compact_size = len(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        self.assertLessEqual(compact_size, PROPOSE_MAX_BYTES)

    def test_propose_ui_options_match_the_canonical_candidates(self):
        result = self.propose_three_templates()
        options = result["ui"][0]["options"]

        self.assertEqual(len(result["candidates"]), len(options))
        for candidate, option in zip(result["candidates"], options):
            self.assertEqual(OPTION_KEYS, set(option))
            self.assertEqual(candidate["id"], option["id"])
            self.assertEqual(candidate["templateId"], option["choiceId"])
            self.assertEqual(candidate["templateId"], option["templateId"])
            self.assertEqual(candidate["filename"], option["filename"])
            self.assertEqual(candidate["filename"], option["subtitle"])
            self.assertEqual(candidate["displayName"], option["title"])
            self.assertEqual(candidate["confidence"], option["confidence"])
            self.assertEqual(candidate["reasons"], option["reasons"])
            self.assertEqual(candidate["tags"], option["tags"])
            self.assertEqual(
                {
                    "groupCount": candidate["groupCount"],
                    "depth": candidate["depth"],
                    "relativePath": candidate["relativePath"],
                },
                option["meta"],
            )

    def test_confirm_accepts_opaque_template_id_without_metadata_path_leak(self):
        proposed = self.propose_three_templates()
        template_id = proposed["candidates"][0]["templateId"]

        confirmed = self.run_skill("confirm", {"templateId": template_id})
        selected = confirmed["selectedTemplate"]

        self.assertTrue(confirmed["ok"])
        self.assertEqual(PUBLIC_TEMPLATE_KEYS, set(selected))
        self.assertEqual(template_id, selected["templateId"])
        self.assert_no_windows_absolute_paths(selected)
        self.assertIsInstance(confirmed["draft"], dict)
        self.assertTrue(confirmed["draft"])
        self.assertIn("<?xml", confirmed["xml"])
        self.assertTrue(confirmed["structureSummary"])

    def test_response_schemas_reject_extra_public_dto_fields(self):
        propose_schema = json.loads(PROPOSE_SCHEMA.read_text(encoding="utf-8"))
        confirm_schema = json.loads(CONFIRM_SCHEMA.read_text(encoding="utf-8"))

        self.assertFalse(propose_schema["additionalProperties"])
        self.assertIn("queryText", propose_schema["properties"])
        self.assertIn("browse", propose_schema["properties"])

        candidate_schema = propose_schema["$defs"]["templateCandidate"]
        self.assertFalse(candidate_schema["additionalProperties"])
        self.assertEqual(PUBLIC_CANDIDATE_KEYS, set(candidate_schema["properties"]))

        option_schema = propose_schema["$defs"]["templateOption"]
        self.assertFalse(option_schema["additionalProperties"])
        self.assertEqual(OPTION_KEYS, set(option_schema["properties"]))
        self.assertEqual(
            "#/$defs/templateOptionMeta",
            option_schema["properties"]["meta"]["$ref"],
        )

        option_meta_schema = propose_schema["$defs"]["templateOptionMeta"]
        self.assertFalse(option_meta_schema["additionalProperties"])
        self.assertEqual(
            {"groupCount", "depth", "relativePath"},
            set(option_meta_schema["properties"]),
        )

        selected_schema = confirm_schema["$defs"]["template"]
        self.assertFalse(selected_schema["additionalProperties"])
        self.assertEqual(PUBLIC_TEMPLATE_KEYS, set(selected_schema["properties"]))

        handoff_schema = confirm_schema["$defs"]["handoffTemplate"]
        self.assertFalse(handoff_schema["additionalProperties"])
        self.assertEqual(
            {"id", "displayName", "filename", "relativePath"},
            set(handoff_schema["properties"]),
        )
        self.assertEqual(
            "#/$defs/handoffTemplate",
            confirm_schema["$defs"]["handoff"]["properties"]["selectedGroupTemplate"]["$ref"],
        )


if __name__ == "__main__":
    unittest.main()