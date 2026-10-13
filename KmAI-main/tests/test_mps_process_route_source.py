import os
import subprocess
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".."))
KM3DMPS_SRC = os.path.join(ROOT, "src", "KM3DMPS")


def read_protected_source(path):
    if not os.path.exists(path):
        raise unittest.SkipTest("MPS source file is not available")
    command = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "$OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "Get-Content -Raw -Encoding Default " + repr(path)
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    return completed.stdout


class MpsProcessRouteSourceTests(unittest.TestCase):
    def test_mps_writes_process_route_object_payload_with_manual_defaults(self):
        source = read_protected_source(os.path.join(KM3DMPS_SRC, "MpsCADCommMgr.cpp"))

        self.assertIn('"input_json"', source)
        self.assertIn('"manual_defaults"', source)
        self.assertIn('"special_process_flags"', source)
        self.assertIn('BuildProcessRouteManualDefaults', source)
        self.assertIn('BuildProcessRouteInputPayload', source)
        self.assertIn('materialGrade.CompareNoCase(_T("45")) == 0', source)
        self.assertIn('materialGrade = _T("9Cr18")', source)
        self.assertIn('value == KmAiProcessRouteText(L"\\u56de\\u8f6c\\u4f53")', source)
        self.assertIn('heatTreatment = KmAiProcessRouteText(L"\\u6dec\\u706b")', source)
        self.assertIn('KmAiAppendUniqueManualValue(inspectionItems, KmAiProcessRouteText(L"\\u88c2\\u7eb9\\u68c0\\u6d4b"));', source)
        self.assertIn('KmAiAppendUniqueManualValue(markingMethods, KmAiProcessRouteText(L"\\u6807\\u5370"));', source)
        self.assertIn('hasShapedHoleOrCutFlat = true;', source)

    def test_mps_push_flattens_object_payload_instead_of_nesting_it(self):
        source = read_protected_source(os.path.join(KM3DMPS_SRC, "MainFrm.cpp"))

        self.assertIn('inputJson.isObject()', source)
        self.assertIn('inputJson.isMember("input_json")', source)
        self.assertIn('payload["manual_defaults"] = inputJson["manual_defaults"]', source)


if __name__ == "__main__":
    unittest.main()
