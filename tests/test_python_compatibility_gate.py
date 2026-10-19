# -*- coding: utf-8 -*-
from __future__ import print_function

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.check_python_compat import check_compatibility


class PythonCompatibilityGateTests(unittest.TestCase):
    def test_gate_rejects_non_cpython_38_interpreter_before_source_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "incompatible.py"
            source.write_text("this is intentionally not python\n", encoding="utf-8")
            result = check_compatibility(sys.executable, [source])
        self.assertFalse(result["ok"])
        self.assertEqual("PYTHON_VERSION_MISMATCH", result["error_code"])
        self.assertEqual(0, result["checked_files"])

    def test_gate_reports_missing_explicit_interpreter(self):
        result = check_compatibility("definitely-missing-kmai-python38", [])
        self.assertFalse(result["ok"])
        self.assertEqual("PYTHON_NOT_FOUND", result["error_code"])


if __name__ == "__main__":
    unittest.main()
