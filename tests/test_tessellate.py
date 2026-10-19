# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STEP_ROOT = ROOT / "step-compare-main" / "step-compare-main"
if str(STEP_ROOT) not in sys.path:
    sys.path.insert(0, str(STEP_ROOT))

from step_viewer import tessellate  # noqa: E402


class TessellateCompatibilityTests(unittest.TestCase):
    def test_legacy_cascadio_step_to_glb_receives_a_real_temporary_step_file(self):
        observed = {}

        def legacy_step_to_glb(input_path, output_path, **kwargs):
            observed["input"] = Path(input_path).read_bytes()
            observed["name"] = Path(input_path).name
            observed["kwargs"] = kwargs
            Path(output_path).write_bytes(b"glTF\x02legacy")
            return 0

        with mock.patch.object(tessellate.cascadio, "load", None), mock.patch.object(
            tessellate.cascadio, "step_to_glb", legacy_step_to_glb, create=True
        ):
            result = tessellate._convert_step_to_glb(b"ISO-10303-21;fixture", r"C:\upload\中文零件.step")

        self.assertEqual(b"ISO-10303-21;fixture", observed["input"])
        self.assertEqual("中文零件.step", observed["name"])
        self.assertEqual({"tol_linear": 0.01, "tol_angular": 0.15}, observed["kwargs"])
        self.assertEqual(b"glTF\x02legacy", result)

    def test_modern_cascadio_load_remains_the_preferred_path(self):
        modern = mock.Mock(return_value=b"glTF\x02modern")
        with mock.patch.object(tessellate.cascadio, "load", modern), mock.patch.object(
            tessellate.cascadio, "step_to_glb", side_effect=AssertionError("legacy path used"), create=True
        ):
            result = tessellate._convert_step_to_glb(b"ISO-10303-21;fixture", "part.stp")

        self.assertEqual(b"glTF\x02modern", result)
        modern.assert_called_once_with(b"ISO-10303-21;fixture", file_type="step", tol_linear=0.01, tol_angular=0.15)

    def test_legacy_filename_is_reduced_to_a_safe_temp_basename(self):
        observed = {}

        def legacy_step_to_glb(input_path, output_path, **kwargs):
            observed["name"] = Path(input_path).name
            Path(output_path).write_bytes(b"glTF\x02legacy")
            return 0

        with mock.patch.object(tessellate.cascadio, "load", None), mock.patch.object(
            tessellate.cascadio, "step_to_glb", legacy_step_to_glb, create=True
        ):
            tessellate._convert_step_to_glb(b"ISO-10303-21;fixture", 'C:\\bad:name?.step')

        self.assertEqual("bad_name_.step", observed["name"])


if __name__ == "__main__":
    unittest.main()
