# -*- coding: utf-8 -*-
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Win7ClientPatchTests(unittest.TestCase):
    def test_cef_runtime_paths_and_virtual_machine_gpu_fallback_are_configured(self):
        patch = (ROOT / "deploy" / "win7-compat" / "kmai-client-cef109.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("config.setBrowserSubProcessPath(QDir(root).filePath(\"CefViewWing.exe\"));", patch)
        self.assertIn("config.setResourceDirectoryPath(QDir(root).filePath(\"resources\"));", patch)
        self.assertIn("config.setLocalesDirectoryPath(QDir(root).filePath(\"resources/locales\"));", patch)
        self.assertIn('config.addCommandLineSwitch("disable-gpu");', patch)
        self.assertIn('config.addCommandLineSwitch("disable-gpu-compositing");', patch)


if __name__ == "__main__":
    unittest.main()
