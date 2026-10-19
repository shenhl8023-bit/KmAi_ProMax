# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "kmai_win7_package_builder", ROOT / "tools" / "build_win7_package.py"
)
BUILDER = importlib.util.module_from_spec(_BUILDER_SPEC)
sys.modules[_BUILDER_SPEC.name] = BUILDER
_BUILDER_SPEC.loader.exec_module(BUILDER)

PackageBuildError = BUILDER.PackageBuildError
_run_runtime_import_gate = BUILDER._run_runtime_import_gate
_scan_package_payload = BUILDER._scan_package_payload
_validate_python_runtime_layout = BUILDER._validate_python_runtime_layout
build_package = BUILDER.build_package


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_x64_pe(path):
    header = bytearray(70)
    header[:2] = b"MZ"
    header[0x3C:0x40] = (64).to_bytes(4, "little")
    header[64:70] = b"PE\0\0\x64\x86"
    path.write_bytes(header)


class Win7PackageBuilderTests(unittest.TestCase):
    def test_runtime_layout_rejects_executable_only_python_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "python.exe"
            _write_x64_pe(executable)
            with self.assertRaises(PackageBuildError) as caught:
                _validate_python_runtime_layout(executable)
            self.assertIn("PYTHON_RUNTIME_INCOMPLETE", str(caught.exception))

    def test_package_scan_rejects_credentials_and_developer_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            payload = package_root / "config.sample.ini"
            payload.write_text("api_key = abcdefghijklmnop\n", encoding="utf-8")
            with self.assertRaises(PackageBuildError) as secret:
                _scan_package_payload(package_root)
            self.assertIn("PACKAGE_SECRET_FOUND", str(secret.exception))

            payload.write_text("safe = yes\n", encoding="utf-8")
            (package_root / "README.md").write_text("C:\\Users\\Developer\\project\\config.ini", encoding="utf-8")
            with self.assertRaises(PackageBuildError) as path:
                _scan_package_payload(package_root)
            self.assertIn("PACKAGE_MACHINE_PATH", str(path.exception))

            (package_root / "README.md").unlink()
            (package_root / "config.js").write_text("const api_key = 'abc.defghijklmnop';\n", encoding="utf-8")
            with self.assertRaises(PackageBuildError) as dotted_secret:
                _scan_package_payload(package_root)
            self.assertIn("PACKAGE_SECRET_FOUND", str(dotted_secret.exception))

            (package_root / "config.js").write_text("const api_key = form.api_key.value.trim();\n", encoding="utf-8")
            _scan_package_payload(package_root)

    def test_package_scan_rejects_unscannably_large_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = Path(temp_dir) / "large.txt"
            payload.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
            with self.assertRaises(PackageBuildError) as caught:
                _scan_package_payload(temp_dir)
            self.assertIn("PACKAGE_SCAN_TOO_LARGE", str(caught.exception))

    @mock.patch("kmai_win7_package_builder.subprocess.run")
    def test_runtime_import_gate_uses_packaged_python_and_isolation(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = '{"ok": true}\n--port\n'
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            _run_runtime_import_gate(package_root)
        command = run.call_args_list[0].args[0]
        self.assertEqual(str(package_root / "runtime" / "python.exe"), command[0])
        self.assertIn("-I", command)
        self.assertIn("-B", command)
        self.assertIn("backend.agent_server", command[-1])
        entry_command = run.call_args_list[1].args[0]
        self.assertEqual(command[0], entry_command[0])
        self.assertIn("-B", entry_command)
        self.assertIn(str(package_root / "KmMpsMcpServer" / "agent_server.py"), entry_command)
        self.assertEqual("--help", entry_command[-1])
        self.assertNotIn("-c", entry_command)

    @mock.patch("kmai_win7_package_builder.subprocess.run")
    def test_runtime_import_gate_rejects_broken_direct_entry(self, run):
        run.side_effect = [
            mock.Mock(returncode=0, stdout='{"ok": true}\n'),
            mock.Mock(returncode=1, stdout="", stderr="ModuleNotFoundError: backend"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PackageBuildError) as caught:
                _run_runtime_import_gate(temp_dir)
        self.assertIn("PYTHON_RUNTIME_ENTRY_FAILED", str(caught.exception))

    def _external_inputs(self, temp_dir):
        temp_dir = Path(temp_dir)
        python_root = temp_dir / "python-runtime"
        python_root.mkdir()
        python_runtime = python_root / "python.exe"
        _write_x64_pe(python_runtime)
        (python_root / "python38.dll").write_bytes(b"PYTHON-DLL-FIXTURE")
        (python_root / "python38.zip").write_bytes(b"PYTHON-STDLIB-FIXTURE")
        (python_root / "python38._pth").write_text("python38.zip\n.\n", encoding="ascii")
        node_root = temp_dir / "node-runtime"
        node_root.mkdir()
        node_runtime = node_root / "node.exe"
        _write_x64_pe(node_runtime)
        _write_json(
            Path(str(python_runtime) + ".metadata.json"),
            {"implementation": "CPython", "version": "3.8.18", "architecture": "x64"},
        )
        _write_json(
            Path(str(node_runtime) + ".metadata.json"),
            {"implementation": "Node.js", "version": "12.22.12", "architecture": "x64"},
        )
        cef_root = temp_dir / "cef"
        cef_root.mkdir()
        _write_x64_pe(cef_root / "libcef.dll")
        _write_x64_pe(cef_root / "KmAiChatCef.exe")
        _write_x64_pe(cef_root / "QCefView.dll")
        _write_x64_pe(cef_root / "CefViewWing.exe")
        (cef_root / "resources" / "locales").mkdir(parents=True)
        (cef_root / "resources" / "resources.pak").write_bytes(b"CEF-RESOURCES")
        (cef_root / "resources" / "locales" / "zh-CN.pak").write_bytes(b"CEF-ZH")
        _write_json(
            cef_root / "cef.manifest.json",
            {
                "version": "Win7-CEF-fixture",
                "chromium_version": "fixture-chromium",
                "qt_version": "fixture-qt",
                "client_version": "fixture-client",
                "client_abi": "Win7-CEF-fixture",
                "win7_supported": True,
                "client_files": {
                    "main_executable": "KmAiChatCef.exe",
                    "wrapper_library": "QCefView.dll",
                    "subprocess_executable": "CefViewWing.exe",
                },
                "architecture": "x64",
            },
        )
        data_root = temp_dir / "similar-data"
        data_root.mkdir()
        (data_root / "similar_parts_features.sqlite3").write_bytes(b"INDEX-FIXTURE")
        (data_root / "XML样本").mkdir()
        (data_root / "XML样本" / "candidate.xml").write_text("<Kmsoft />", encoding="utf-8")
        (data_root / "STEP样本").mkdir()
        (data_root / "STEP样本" / "candidate.stp").write_text("ISO-10303-21;", encoding="ascii")
        (data_root / "模板").mkdir()
        _write_json(data_root / "模板" / "模板映射.json", {"candidate": "candidate.xml"})
        _write_json(data_root / "manifest.json", {"version": "fixture-index-1", "architecture": "x64"})
        models_root = temp_dir / "models"
        models_root.mkdir()
        (models_root / "candidate.glb").write_bytes(b"glTF\x02model")
        _write_json(models_root / "manifest.json", {"version": "fixture-model-1", "architecture": "x64"})
        return python_runtime, node_runtime, cef_root, data_root, models_root

    def test_build_copies_whitelist_and_records_external_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            output = temp_dir / "package"
            with mock.patch("kmai_win7_package_builder._run_runtime_gates") as gates, mock.patch(
                "kmai_win7_package_builder._run_runtime_import_gate"
            ) as import_gate:
                result = build_package(
                    ROOT,
                    output,
                    python_runtime,
                    node_runtime,
                    cef_root,
                    data_root,
                    models_root,
                )
            gates.assert_called_once()
            import_gate.assert_called_once()
            manifest = json.loads((output / "package-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("Windows 7 SP1", manifest["target"]["os"])
            self.assertEqual("x64", manifest["target"]["architecture"])
            self.assertRegex(manifest["built_at_utc"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
            self.assertEqual("3.8.18", manifest["runtime"]["python"]["version"])
            self.assertEqual("12.22.12", manifest["runtime"]["node"]["version"])
            self.assertEqual("Win7-CEF-fixture", manifest["external_inputs"]["cef"]["version"])
            self.assertEqual("fixture-chromium", manifest["external_inputs"]["cef"]["chromium_version"])
            self.assertEqual("fixture-qt", manifest["external_inputs"]["cef"]["qt_version"])
            self.assertEqual("fixture-client", manifest["external_inputs"]["cef"]["client_version"])
            self.assertEqual("Win7-CEF-fixture", manifest["external_inputs"]["cef"]["client_abi"])
            self.assertTrue(manifest["external_inputs"]["cef"]["win7_supported"])
            self.assertEqual("/", manifest["layout"]["cef"])
            self.assertTrue(manifest["runtime"]["python"]["sha256"])
            self.assertTrue((output / "KmMpsMcpServer").is_dir())
            self.assertTrue((output / "runtime" / "python.exe").is_file())
            self.assertTrue((output / "runtime" / "python38.dll").is_file())
            self.assertTrue((output / "runtime" / "python38.zip").is_file())
            self.assertTrue((output / "runtime" / "python38._pth").is_file())
            python_paths = (output / "runtime" / "python38._pth").read_text(encoding="utf-8").splitlines()
            self.assertIn("python38.zip", python_paths)
            self.assertIn("../KmMpsMcpServer", python_paths)
            self.assertNotIn(str(output), "\n".join(python_paths))
            self.assertFalse((output / "runtime" / "python.exe.metadata.json").exists())
            self.assertTrue((output / "runtime" / "node.exe").is_file())
            self.assertTrue((output / "KmAiChatCef.exe").is_file())
            self.assertTrue((output / "QCefView.dll").is_file())
            self.assertTrue((output / "CefViewWing.exe").is_file())
            self.assertTrue((output / "libcef.dll").is_file())
            self.assertFalse((output / "CefView" / "KmAiChatCef.exe").exists())
            self.assertTrue((output / "Resources" / "resources.pak").is_file())
            self.assertTrue((output / "Resources" / "locales" / "zh-CN.pak").is_file())
            self.assertTrue((output / "Resources" / "SimilarParts" / "similar_parts_features.sqlite3").is_file())
            self.assertTrue((output / "Resources" / "SimilarParts" / "XML样本" / "candidate.xml").is_file())
            self.assertTrue((output / "Resources" / "GroupTemplate").is_dir())
            self.assertTrue((output / "models" / "candidate.glb").is_file())
            self.assertTrue((output / "package-SHA256.txt").is_file())
            self.assertNotIn(str(ROOT).replace("\\", "/").lower(), json.dumps(manifest).replace("\\", "/").lower())
            inventory = (output / "package-SHA256.txt").read_text(encoding="utf-8")
            expected = hashlib.sha256((output / "runtime" / "python.exe").read_bytes()).hexdigest()
            self.assertIn(expected, inventory)
            self.assertEqual(str(output), result["output_root"])

    def test_build_excludes_machine_state_and_copies_only_step_viewer_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            output = temp_dir / "package"
            with mock.patch("kmai_win7_package_builder._run_runtime_gates"), mock.patch(
                "kmai_win7_package_builder._run_runtime_import_gate"
            ):
                build_package(ROOT, output, python_runtime, node_runtime, cef_root, data_root, models_root)
            paths = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
            self.assertFalse(any(path == "config.ini" or path.endswith("/__pycache__/x.pyc") for path in paths))
            self.assertFalse(any("step-compare-main" in path for path in paths))
            self.assertIn("step-compare/step_viewer/tessellate.py", paths)
            self.assertIn("step-compare/web/vendor/three/LICENSE", paths)
            self.assertIn("step-compare/web/vendor/three/build/three.module.js", paths)
            self.assertIn("step-compare/web/vendor/three/examples/jsm/controls/OrbitControls.js", paths)
            self.assertIn("step-compare/web/vendor/three/examples/jsm/loaders/GLTFLoader.js", paths)
            self.assertFalse(any(path.endswith(".pyc") for path in paths))
            config_bytes = (output / "config.example.ini").read_bytes()
            self.assertGreater(config_bytes.count(b"\r\n"), 0)
            self.assertEqual(config_bytes.count(b"\r\n"), config_bytes.count(b"\n"))
            manifest = json.loads((output / "package-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("config.ini", manifest["exclude"])
            self.assertIn("__pycache__", manifest["exclude"])
            self.assertIn("*.pyc", manifest["exclude"])
            self.assertEqual("step-compare/web/vendor/three/", manifest["layout"]["three_vendor"])

    def test_build_rejects_bytecode_created_by_import_probe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, _ = self._external_inputs(temp_dir)
            output = temp_dir / "package"

            def create_bytecode(package_root):
                cache = Path(package_root) / "KmMpsMcpServer" / "__pycache__"
                cache.mkdir()
                (cache / "agent_server.cpython-38.pyc").write_bytes(b"probe-generated-bytecode")

            with mock.patch("kmai_win7_package_builder._run_runtime_gates"), mock.patch(
                "kmai_win7_package_builder._run_runtime_import_gate", side_effect=create_bytecode
            ):
                with self.assertRaises(PackageBuildError) as caught:
                    build_package(ROOT, output, python_runtime, node_runtime, cef_root, data_root)
            self.assertIn("PACKAGE_EXCLUDED_FILE", str(caught.exception))
            self.assertFalse(output.exists())

    def test_realtime_step_build_does_not_require_glb_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, _ = self._external_inputs(temp_dir)
            output = temp_dir / "package"
            with mock.patch("kmai_win7_package_builder._run_runtime_gates"), mock.patch(
                "kmai_win7_package_builder._run_runtime_import_gate"
            ):
                result = build_package(ROOT, output, python_runtime, node_runtime, cef_root, data_root)
            manifest = json.loads((output / "package-manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("models", manifest["external_inputs"])
            self.assertFalse((output / "models").exists())
            self.assertEqual(str(output), result["output_root"])

    def test_build_includes_optional_win7_kb_prerequisite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            kb_root = temp_dir / "kb-input"
            kb_root.mkdir()
            kb_source = kb_root / "approved-kb.msu"
            kb_source.write_bytes(b"KB2533623-FIXTURE")
            fixture_hash = hashlib.sha256(kb_source.read_bytes()).hexdigest()
            output = temp_dir / "package"
            with mock.patch.object(BUILDER, "WIN7_KB2533623_SHA256", fixture_hash), mock.patch(
                "kmai_win7_package_builder._run_runtime_gates"
            ), mock.patch("kmai_win7_package_builder._run_runtime_import_gate"):
                build_package(
                    ROOT,
                    output,
                    python_runtime,
                    node_runtime,
                    cef_root,
                    data_root,
                    models_root,
                    kb_source,
                )
            manifest = json.loads((output / "package-manifest.json").read_text(encoding="utf-8"))
            prerequisite = manifest["prerequisites"]["kb2533623"]
            self.assertEqual("KB2533623", prerequisite["id"])
            self.assertEqual(fixture_hash, prerequisite["sha256"])
            self.assertTrue(prerequisite["requires_reboot"])
            self.assertEqual(
                b"KB2533623-FIXTURE",
                (output / "prerequisites" / "Windows6.1-KB2533623-x64.msu").read_bytes(),
            )
            self.assertTrue((output / "prerequisites" / "install-kb2533623.bat").is_file())
            self.assertTrue((output / "prerequisites" / "README.md").is_file())
            installer_text = (output / "prerequisites" / "install-kb2533623.bat").read_bytes()
            self.assertIn(b"\r\n", installer_text)
            self.assertNotIn(b"\n", installer_text.replace(b"\r\n", b""))

    def test_win7_kb_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            kb_source = Path(temp_dir) / "Windows6.1-KB2533623-x64.msu"
            kb_source.write_bytes(b"not-the-approved-update")
            with self.assertRaises(PackageBuildError) as caught:
                BUILDER._validate_win7_kb(kb_source)
            self.assertIn("WIN7_KB_HASH_MISMATCH", str(caught.exception))

    def test_missing_or_unpinned_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            (Path(str(node_runtime) + ".metadata.json")).unlink()
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, temp_dir / "package", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("NODE_RUNTIME_UNPINNED", str(caught.exception))
            _write_json(
                Path(str(node_runtime) + ".metadata.json"),
                {"implementation": "Node.js", "version": "12.22.12", "architecture": "x64"},
            )
            with self.assertRaises(PackageBuildError) as missing:
                build_package(ROOT, temp_dir / "package2", python_runtime, node_runtime, cef_root, data_root, temp_dir / "missing-models")
            self.assertIn("MODELS_NOT_FOUND", str(missing.exception))

    def test_builder_rejects_unpinned_cef_version_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            _write_json(
                cef_root / "cef.manifest.json",
                {"version": "fixture", "architecture": "x64", "chromium_version": "fixture"},
            )
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, temp_dir / "package", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("CEF_UNPINNED", str(caught.exception))

    def test_builder_rejects_cef_runtime_without_rebuilt_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            for filename in ("KmAiChatCef.exe", "QCefView.dll", "CefViewWing.exe"):
                (cef_root / filename).unlink()
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, temp_dir / "package", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("CEF_CLIENT_NOT_FOUND", str(caught.exception))

    def test_builder_reports_rebuild_requirement_before_client_abi_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            manifest_path = cef_root / "cef.manifest.json"
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata["client_version"] = "REBUILD_REQUIRED_QCefView_KmAiChatCef"
            metadata["client_abi"] = "REBUILD_REQUIRED_FOR_Win7-CEF-fixture"
            _write_json(manifest_path, metadata)
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, temp_dir / "package", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("CEF_CLIENT_NOT_READY", str(caught.exception))

    def test_builder_rejects_invalid_glb_and_missing_sample_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            (models_root / "candidate.glb").write_bytes(b"not-glb")
            with self.assertRaises(PackageBuildError) as invalid:
                build_package(ROOT, temp_dir / "invalid-glb", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("MODEL_GLB_INVALID", str(invalid.exception))
            (models_root / "candidate.glb").write_bytes(b"glTF\x02model")
            (models_root / "candidate.glb").unlink()
            with self.assertRaises(PackageBuildError) as missing:
                build_package(ROOT, temp_dir / "missing-model", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("MODELS_GLB_NOT_FOUND", str(missing.exception))

    def test_output_must_be_outside_source_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, ROOT / "_win7-package-test-output", python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("OUTPUT_INSIDE_SOURCE", str(caught.exception))

    def test_output_must_be_outside_external_runtime_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            python_runtime, node_runtime, cef_root, data_root, models_root = self._external_inputs(temp_dir)
            output = python_runtime.parent / "package"
            with self.assertRaises(PackageBuildError) as caught:
                build_package(ROOT, output, python_runtime, node_runtime, cef_root, data_root, models_root)
            self.assertIn("OUTPUT_INSIDE_INPUT", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
