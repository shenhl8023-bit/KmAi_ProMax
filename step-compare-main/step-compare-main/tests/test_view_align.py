# -*- coding: utf-8 -*-
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_translation_to_origin_centers_offset_bounds():
    result = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "test_view_align.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
    assert result.returncode == 0
