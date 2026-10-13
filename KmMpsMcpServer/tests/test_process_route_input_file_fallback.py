import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import http_api


class ProcessRouteInputFileFallbackTest(unittest.TestCase):
    def test_get_latest_input_falls_back_to_3dmps_input_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            input_rows = [
                {
                    "group_path": "A侧/孔/",
                    "features": [{"feature_select": "孔", "feat_rank": 10}],
                }
            ]
            input_path.write_text(json.dumps(input_rows, ensure_ascii=False), encoding="utf-8")

            state = http_api.ProcessRouteState()

            with mock.patch.object(http_api, "PROCESS_ROUTE_INPUT_PATH", str(input_path)):
                payload = state.get_input()

        self.assertEqual(input_rows, payload["input_json"])
        self.assertEqual("file", payload["source"])
        self.assertEqual("input.json", payload["input_file"])
        self.assertTrue(payload["trace_id"].startswith("input.json-"))

    def test_get_latest_input_preserves_manual_defaults_from_object_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            input_rows = [
                {
                    "group_path": "A?/?/",
                    "features": [{"feature_select": "?", "feat_rank": 10}],
                }
            ]
            manual_defaults = {
                "material_grade": "9Cr18",
                "part_type": "??",
                "heat_treatment": "??",
                "surface_treatments": [],
                "inspection_items": ["????"],
                "marking_methods": ["??"],
                "special_process_flags": {
                    "shaped_hole_or_cut_flat": True,
                    "post_stage_added_hole": False,
                },
            }
            input_path.write_text(json.dumps({
                "input_json": input_rows,
                "manual_defaults": manual_defaults,
                "source": "3dmps",
            }, ensure_ascii=False), encoding="utf-8")

            state = http_api.ProcessRouteState()

            with mock.patch.object(http_api, "PROCESS_ROUTE_INPUT_PATH", str(input_path)):
                payload = state.get_input()

        self.assertEqual(input_rows, payload["input_json"])
        self.assertEqual(manual_defaults, payload["manual_defaults"])
        self.assertEqual("3dmps", payload["source"])

    def test_get_latest_input_normalizes_manual_alias_to_manual_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            input_rows = [
                {
                    "group_path": "A?/?/",
                    "features": [{"feature_select": "?", "feat_rank": 10}],
                }
            ]
            manual = {
                "material_grade": "9Cr18",
                "part_type": "??",
            }
            input_path.write_text(json.dumps({
                "input_json": input_rows,
                "manual": manual,
            }, ensure_ascii=False), encoding="utf-8")

            state = http_api.ProcessRouteState()

            with mock.patch.object(http_api, "PROCESS_ROUTE_INPUT_PATH", str(input_path)):
                payload = state.get_input()

        self.assertEqual(manual, payload["manual_defaults"])
        self.assertEqual(manual, payload["manual"])


if __name__ == "__main__":
    unittest.main()
