import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "KmMpsMcpServer" / "tools" / "nx11_batch_xt_to_step.py"


class NxBatchXtToStepScriptTests(unittest.TestCase):
    def _load_module(self):
        nxopen = types.ModuleType("NXOpen")
        old_module = sys.modules.get("NXOpen")
        sys.modules["NXOpen"] = nxopen
        try:
            spec = importlib.util.spec_from_file_location("nx11_batch_xt_to_step", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if old_module is None:
                sys.modules.pop("NXOpen", None)
            else:
                sys.modules["NXOpen"] = old_module

    def test_script_uses_real_step_exporter(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("CreateStep214Creator", source)
        self.assertNotIn("part.SaveAs(output_stp)", source)

    def test_output_name_preserves_source_stem(self):
        module = self._load_module()
        self.assertEqual(module.output_name(r"C:\parts\shaft.x_t"), "shaft.stp")
        self.assertEqual(module.output_name(r"C:\parts\SHAFT.X_T"), "SHAFT.stp")

    def test_source_files_are_sorted_and_case_insensitive(self):
        module = self._load_module()
        names = ["b.x_t", "ignore.stp", "A.X_T"]
        self.assertEqual(module.source_names(names), ["A.X_T", "b.x_t"])


if __name__ == "__main__":
    unittest.main()
