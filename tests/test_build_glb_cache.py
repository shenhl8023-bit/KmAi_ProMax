# -*- coding: utf-8 -*-
from __future__ import print_function

import json
from pathlib import Path
import tempfile
import unittest

from tools.build_glb_cache import GlbCacheError, build_cache, _output_path


class BuildGlbCacheTests(unittest.TestCase):
    def _fixture_root(self, base):
        root = base / "step-viewer"
        package = root / "step_viewer"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("\n", encoding="utf-8")
        (package / "tessellate.py").write_text(
            """
class Result:
    glb = b'glTF\\x02fixture'
    bounds = [[0, 0, 0], [1, 2, 3]]
    extents = [1, 2, 3]
    vertices = 8
    faces = 12
    unit = 'mm'
    source_unit = 'mm'

def tessellate_step(data, filename):
    if not data.startswith(b'ISO-10303-21;'):
        raise ValueError('invalid STEP')
    return Result()
""",
            encoding="utf-8",
        )
        return root

    def test_builds_glb_and_metadata_without_copying_step(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            viewer = self._fixture_root(base)
            inputs = base / "inputs"
            outputs = base / "models"
            inputs.mkdir()
            (inputs / "中文零件.step").write_bytes(b"ISO-10303-21;valid")
            result = build_cache(viewer, inputs, outputs)
            self.assertEqual(1, result["built"])
            self.assertEqual(b"glTF\x02fixture", (outputs / "中文零件.glb").read_bytes())
            self.assertFalse((outputs / "中文零件.step").exists())
            metadata = json.loads((outputs / "中文零件.json").read_text(encoding="utf-8"))
            self.assertEqual("中文零件", metadata["name"])
            self.assertEqual("mm", metadata["unit"])

    def test_invalid_step_fails_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            viewer = self._fixture_root(base)
            inputs = base / "inputs"
            outputs = base / "models"
            inputs.mkdir()
            (inputs / "bad.stp").write_bytes(b"not-step")
            with self.assertRaises(GlbCacheError):
                build_cache(viewer, inputs, outputs)
            self.assertFalse((outputs / "bad.glb").exists())

    def test_output_path_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with self.assertRaises(GlbCacheError):
                _output_path(base / "models", "../outside.glb")


if __name__ == "__main__":
    unittest.main()
