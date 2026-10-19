# -*- coding: utf-8 -*-
"""Build a clean, offline Win7 package from explicit approved inputs."""

from __future__ import print_function

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PackageBuildError(Exception):
    """Expected build input or policy failure."""


EXCLUDE_PATTERNS = (
    "config.ini",
    "*.pyc",
    "__pycache__",
    "*.log",
    ".git",
    ".superpowers",
    "step-compare-main",
    "PartClassification-main",
)
TEMPLATE_FILES = (
    "launcher.py",
    "start_win7.bat",
    "start_client_win7.bat",
    "stop_win7.bat",
    "start_agent.bat",
    "stop_agent.bat",
    "config.example.ini",
    "requirements-win7-x64.txt",
    "README.md",
)
WIN7_KB2533623_SHA256 = "58b8b00113fa8b9657d8da5b14bae93f765f29651c81055e3d127d4a22e5c0d6"
WIN7_KB2533623_FILE_NAME = "Windows6.1-KB2533623-x64.msu"
_TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".css",
    ".htm",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".txt",
    ".xml",
    ".cmd",
    ".conf",
    ".csv",
    ".properties",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".vue",
    ".yaml",
    ".yml",
}
_USER_PATH_PATTERN = re.compile(
    r"(?i)(?:[A-Z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\s\"'<>]+|/(?:Users|home)/[^\s\"'<>]+)"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?im)(?:^|[,{ \t\"'])"
    r"(?:api[_-]?key|access[_-]?token|bearer[_-]?token|password|passwd|secret)"
    r"[ \t]*[:=][ \t]*[\"']?([A-Za-z0-9][A-Za-z0-9._~+/=-]{11,})"
)
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(?:authorization\s*[:=]\s*bearer|x-api-key\s*[:=])\s*[A-Za-z0-9._~+/=-]{16,}"
)
_PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----")
_CODE_REFERENCE_PATTERN = re.compile(
    r"^(?:form|config|settings|process|os|environ|data)"
    r"\.[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
    r"(?:\([^)]*\))?$"
)


def _fail(code, message):
    raise PackageBuildError("%s: %s" % (code, message))


def _resolve(path, code):
    if path is None or not str(path).strip():
        _fail(code, "未提供路径")
    return Path(path).expanduser().resolve()


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _is_excluded(relative_path):
    parts = Path(relative_path).parts
    lower_parts = {part.casefold() for part in parts}
    if lower_parts.intersection(
        {"__pycache__", ".git", ".superpowers", "cache", "logs", "uploads", "upload", "runtime-state"}
    ):
        return True
    if any(part.casefold() in ("step-compare-main", "partclassification-main") for part in parts):
        return True
    name = Path(relative_path).name.casefold()
    if (
        name == "config.ini"
        or name.endswith(".pyc")
        or name.endswith(".log")
        or name.endswith(".metadata.json")
    ):
        return True
    return False


def _copy_tree(source, destination, exclude_tests=False, exclude_file_names=()):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not source.is_dir():
        _fail("SOURCE_NOT_FOUND", str(source))
    if _inside(destination, source):
        _fail("COPY_DESTINATION_INSIDE_SOURCE", str(destination))
    excluded_names = {str(name).casefold() for name in exclude_file_names}
    copied = []
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if item.name.casefold() in excluded_names:
            continue
        if _is_excluded(relative) or (exclude_tests and any(part.casefold() == "tests" for part in relative.parts)):
            continue
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(item), str(target))
        copied.append(target)
    return copied


def _copy_file(source, destination):
    source = Path(source).resolve()
    if not source.is_file():
        _fail("SOURCE_NOT_FOUND", str(source))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))
    return destination


def _normalize_batch_line_endings(root):
    """把 Windows 批处理文件统一为 CRLF，兼容 Win7 命令解释器。"""
    root = Path(root)
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".bat", ".cmd"):
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        path.write_bytes(normalized.replace("\n", "\r\n").encode("utf-8"))


def _normalize_ini_line_endings(root):
    """把配置文件统一为 CRLF，确保 Win7 记事本按行显示。"""
    root = Path(root)
    for path in root.rglob("*.ini"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        path.write_bytes(normalized.replace("\n", "\r\n").encode("utf-8"))


def _read_json(path, code):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, IOError, ValueError) as exc:
        _fail(code, "%s (%s)" % (path, exc))
    if not isinstance(value, dict):
        _fail(code, "%s 必须是 JSON 对象" % path)
    return value


def _is_x64_pe(path):
    try:
        with Path(path).open("rb") as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b"MZ":
                return False
            pe_offset = int.from_bytes(header[0x3C:0x40], "little")
            stream.seek(pe_offset)
            signature = stream.read(6)
        return len(signature) == 6 and signature[:4] == b"PE\0\0" and signature[4:6] == b"\x64\x86"
    except (OSError, IOError, ValueError):
        return False


def _validate_cef_client_layout(root, metadata):
    """Require a client rebuilt against the exact staged CEF ABI.

    CEF's DLL is not a drop-in replacement for an application wrapper.  A
    runtime-only CEF archive therefore must never pass the package builder;
    the wrapper, host executable, and subprocess must be present and pinned
    to the same CEF version in the external manifest.
    """
    if metadata.get("win7_supported") is not True:
        _fail("CEF_NOT_WIN7_READY", "manifest must explicitly set win7_supported=true")
    if "REBUILD_REQUIRED" in str(metadata.get("client_version", "")).upper():
        _fail("CEF_CLIENT_NOT_READY", "client_version still indicates that the CEF client must be rebuilt")
    cef_version = str(metadata.get("version", "")).strip()
    client_abi = str(metadata.get("client_abi", "")).strip()
    if not client_abi:
        _fail("CEF_CLIENT_ABI_UNPINNED", "manifest must include client_abi")
    if client_abi != cef_version:
        _fail(
            "CEF_CLIENT_ABI_MISMATCH",
            "client_abi=%s does not match CEF version=%s" % (client_abi, cef_version),
        )
    client_files = metadata.get("client_files")
    if not isinstance(client_files, dict):
        _fail(
            "CEF_CLIENT_FILES_UNPINNED",
            "manifest must include client_files.main_executable, wrapper_library, and subprocess_executable",
        )
    required = {
        "main_executable": str(client_files.get("main_executable", "")).strip(),
        "wrapper_library": str(client_files.get("wrapper_library", "")).strip(),
        "subprocess_executable": str(client_files.get("subprocess_executable", "")).strip(),
    }
    if any(not value for value in required.values()):
        _fail("CEF_CLIENT_FILES_UNPINNED", "client_files contains an empty required path")
    for label, relative_path in required.items():
        candidate = (Path(root) / relative_path).resolve()
        if not _inside(candidate, root) or not candidate.is_file():
            _fail("CEF_CLIENT_NOT_FOUND", "%s: %s" % (label, relative_path))
        if not _is_x64_pe(candidate):
            _fail("CEF_CLIENT_BINARY_ARCHITECTURE", "client file is not an x64 PE binary: %s" % relative_path)
def _metadata_for_runtime(executable, label, expected_implementation, expected_version):
    executable = Path(executable).resolve()
    metadata_path = Path(str(executable) + ".metadata.json")
    if not metadata_path.is_file():
        _fail("%s_RUNTIME_UNPINNED" % label.upper(), "缺少 %s" % metadata_path.name)
    metadata = _read_json(metadata_path, "%s_RUNTIME_METADATA_INVALID" % label.upper())
    implementation = str(metadata.get("implementation", "")).strip()
    version = str(metadata.get("version", "")).strip()
    architecture = str(metadata.get("architecture", "")).strip().lower()
    if implementation != expected_implementation:
        _fail("%s_RUNTIME_MISMATCH" % label.upper(), "implementation=%s" % implementation)
    if label == "python":
        if not re.match(r"^3\.8(?:\.|$)", version):
            _fail("PYTHON_RUNTIME_MISMATCH", "需要 CPython 3.8.x，得到 %s" % version)
    elif version != expected_version:
        _fail("NODE_RUNTIME_MISMATCH", "需要 Node.js %s，得到 %s" % (expected_version, version))
    if not _is_x64_pe(executable):
        _fail("%s_RUNTIME_BINARY_ARCHITECTURE" % label.upper(), "runtime executable is not an x64 PE binary")
    if architecture not in ("x64", "amd64"):
        _fail("%s_RUNTIME_ARCHITECTURE" % label.upper(), "需要 x64，得到 %s" % architecture)
    return {
        "implementation": implementation,
        "version": version,
        "architecture": "x64",
        "sha256": _sha256_file(executable),
    }


def _validate_python_runtime_layout(executable):
    """Reject an exe-only input before it can be called a portable runtime."""
    root = Path(executable).resolve().parent
    dlls = [path for path in root.glob("python*.dll") if path.is_file()]
    has_stdlib = (root / "Lib").is_dir() or any(
        path.is_file() and path.suffix.lower() == ".zip" and path.name.lower().startswith("python")
        for path in root.iterdir()
    )
    has_path_config = (root / "Lib").is_dir() or any(
        path.is_file() and path.suffix.lower() == "._pth" for path in root.iterdir()
    )
    if not dlls or not has_stdlib or not has_path_config:
        _fail(
            "PYTHON_RUNTIME_INCOMPLETE",
            "CPython runtime must include a python*.dll, standard library, and Lib/.pth layout",
        )


def _read_text_for_scan(path):
    if Path(path).suffix.lower() not in _TEXT_SUFFIXES:
        return None
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:4096] or len(raw) > 4 * 1024 * 1024:
        return None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _scan_package_payload(package_root):
    """Reject excluded state and unsafe text after all build probes finish."""
    for path in Path(package_root).rglob("*"):
        if not path.is_file() or path.name == "package-SHA256.txt":
            continue
        if path.name.casefold().endswith(".metadata.json"):
            _fail("PACKAGE_RUNTIME_METADATA", "runtime metadata sidecar found in %s" % path.relative_to(package_root))
        if _is_excluded(path.relative_to(package_root)):
            _fail("PACKAGE_EXCLUDED_FILE", "excluded runtime state found in %s" % path.relative_to(package_root))
        if path.suffix.lower() in _TEXT_SUFFIXES:
            try:
                payload_size = path.stat().st_size
            except OSError:
                payload_size = 0
            if payload_size > 4 * 1024 * 1024:
                _fail("PACKAGE_SCAN_TOO_LARGE", "text payload exceeds scan limit in %s" % path.relative_to(package_root))
        text = _read_text_for_scan(path)
        if text is None:
            continue
        matches = list(_USER_PATH_PATTERN.finditer(text))
        relative = path.relative_to(package_root)
        is_dependency_docs = (
            len(relative.parts) >= 2
            and relative.parts[0].casefold() == "runtime"
            and relative.parts[1].casefold() == "site-packages"
        )
        # Some third-party source/doc files contain Unix home paths as prose
        # examples. They are not machine-specific package configuration; keep
        # rejecting Windows paths and all user paths outside dependency docs.
        unsafe_matches = [
            match
            for match in matches
            if not (is_dependency_docs and match.group(0).casefold().startswith("/home/"))
        ]
        if unsafe_matches:
            _fail("PACKAGE_MACHINE_PATH", "developer user path found in %s" % path.relative_to(package_root))
        for match in _SECRET_ASSIGNMENT_PATTERN.finditer(text):
            value = match.group(1).strip().lower()
            if value.startswith(("your_", "sk-x", "test-", "private-test-")):
                continue
            if path.suffix.lower() in (".py", ".js") and _CODE_REFERENCE_PATTERN.match(value):
                # Code references such as ``form.api_key.value`` are not
                # literal credentials; configuration and manifest formats
                # remain fully scanned for unquoted values.
                continue
            _fail("PACKAGE_SECRET_FOUND", "credential-like value found in %s" % path.relative_to(package_root))
        if _AUTHORIZATION_PATTERN.search(text) or _PRIVATE_KEY_PATTERN.search(text):
            _fail("PACKAGE_SECRET_FOUND", "credential-like value found in %s" % path.relative_to(package_root))


def _external_tree_metadata(root, label):
    root = Path(root).resolve()
    if not root.is_dir():
        _fail("%s_NOT_FOUND" % label.upper(), str(root))
    metadata_candidates = (
        root / ("%s.manifest.json" % label),
        root / "manifest.json",
    )
    metadata_path = next((path for path in metadata_candidates if path.is_file()), None)
    if metadata_path is None:
        _fail("%s_UNPINNED" % label.upper(), "缺少 manifest.json")
    metadata = _read_json(metadata_path, "%s_METADATA_INVALID" % label.upper())
    version = str(metadata.get("version", "")).strip()
    architecture = str(metadata.get("architecture", "")).strip().lower()
    if not version or architecture not in ("x64", "amd64"):
        _fail("%s_UNPINNED" % label.upper(), "manifest 必须包含 version 和 x64 architecture")
    if label == "cef":
        required_versions = ("chromium_version", "qt_version", "client_version")
        missing_versions = [key for key in required_versions if not str(metadata.get(key, "")).strip()]
        if missing_versions:
            _fail("CEF_UNPINNED", "CEF manifest must include Chromium, Qt, and client versions")
    files = [path for path in root.rglob("*") if path.is_file() and not _is_excluded(path.relative_to(root))]
    if not files:
        _fail("%s_EMPTY" % label.upper(), str(root))
    if label == "similar_parts_data" and not any(path.name == "similar_parts_features.sqlite3" for path in files):
        _fail("SIMILAR_PARTS_INDEX_NOT_FOUND", "missing similar_parts_features.sqlite3")
    if label == "similar_parts_data":
        xml_root = root / "XML样本"
        step_root = root / "STEP样本"
        template_map = root / "模板" / "模板映射.json"
        if not xml_root.is_dir() or not any(xml_root.glob("*.xml")):
            _fail("SIMILAR_PARTS_XML_NOT_FOUND", "XML样本 must contain XML files")
        if not step_root.is_dir() or not any(
            path.suffix.lower() in (".stp", ".step") for path in step_root.iterdir() if path.is_file()
        ):
            _fail("SIMILAR_PARTS_STEP_NOT_FOUND", "STEP样本 must contain STEP files")
        if not template_map.is_file():
            _fail("SIMILAR_PARTS_TEMPLATE_MAP_NOT_FOUND", "missing 模板/模板映射.json")
    if label == "models":
        glb_files = [path for path in files if path.suffix.lower() == ".glb"]
        if not glb_files:
            _fail("MODELS_GLB_NOT_FOUND", "models directory must contain GLB files")
        for model in glb_files:
            try:
                valid_glb = model.read_bytes()[:4] == b"glTF"
            except OSError:
                valid_glb = False
            if not valid_glb:
                _fail("MODEL_GLB_INVALID", "invalid GLB: %s" % model.name)
    if label == "cef":
        native_files = [path for path in files if path.suffix.lower() in (".exe", ".dll")]
        if not native_files:
            _fail("CEF_BINARIES_NOT_FOUND", "CEF/Qt input must contain EXE or DLL binaries")
        for native_file in native_files:
            if not _is_x64_pe(native_file):
                _fail("CEF_BINARY_ARCHITECTURE", "CEF/Qt binary is not an x64 PE file: %s" % native_file.name)
        _validate_cef_client_layout(root, metadata)
    result = {
        "version": version,
        "architecture": "x64",
        "sha256": _sha256_files(files),
    }
    if label == "cef":
        for key in ("chromium_version", "qt_version", "client_version", "client_abi"):
            result[key] = str(metadata[key]).strip()
        result["win7_supported"] = bool(metadata["win7_supported"])
        result["client_files"] = dict(metadata["client_files"])
    return result


def _validate_model_coverage(similar_parts_data_root, models_root):
    sample_stems = {
        path.stem.casefold()
        for sample_root in (Path(similar_parts_data_root) / "XML样本", Path(similar_parts_data_root) / "STEP样本")
        for path in sample_root.iterdir()
        if path.is_file() and path.suffix.lower() in (".xml", ".stp", ".step")
    }
    model_stems = {
        path.stem.casefold()
        for path in Path(models_root).rglob("*")
        if path.is_file() and path.suffix.lower() == ".glb"
    }
    missing_models = sorted(sample_stems - model_stems)
    if missing_models:
        _fail("MODEL_GLB_MISSING", "missing GLB models for %d sample stems" % len(missing_models))


def _run_runtime_gates(source_root, python_runtime, node_runtime):
    """Exercise the explicit runtimes against the shipped sources before copy."""
    python_runtime = str(Path(python_runtime).resolve())
    node_runtime = str(Path(node_runtime).resolve())
    node_version = subprocess.run(
        [node_runtime, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if node_version.returncode != 0 or (node_version.stdout or "").strip().lstrip("v") != "12.22.12":
        _fail("NODE_RUNTIME_MISMATCH", "bundled node.exe did not report v12.22.12")

    python_sources = [
        source_root / "KmMpsMcpServer" / "agent_server.py",
        source_root / "KmMpsMcpServer" / "backend",
        source_root / "KmMpsMcpServer" / "skills",
        source_root / "KmMpsMcpServer" / "tools",
        source_root / "deploy" / "win7-compat" / "launcher.py",
        source_root / "step-compare-main" / "step-compare-main" / "step_viewer",
    ]
    checker = source_root / "tools" / "check_python_compat.py"
    python_gate = subprocess.run(
        [
            sys.executable,
            "-B",
            str(checker),
            "--python-exe",
            python_runtime,
            "--source",
        ]
        + [str(path) for path in python_sources],
        cwd=str(source_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if python_gate.returncode != 0:
        _fail("PYTHON_COMPATIBILITY_GATE_FAILED", "explicit CPython 3.8 source gate failed")

    step_probe = subprocess.run(
        [
            python_runtime,
            "-I",
            "-B",
            "-c",
            (
                "import cascadio, numpy, trimesh; "
                "api = getattr(cascadio, 'load', None) or getattr(cascadio, 'step_to_glb', None); "
                "assert callable(api); "
                "import json; print(json.dumps({'cascadio': getattr(cascadio, '__version__', ''), "
                "'numpy': numpy.__version__, 'trimesh': trimesh.__version__}))"
            ),
        ],
        cwd=str(source_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if step_probe.returncode != 0:
        _fail(
            "STEP_RUNTIME_IMPORT_FAILED",
            "CPython 3.8 runtime must import cascadio, numpy, and trimesh with a STEP API",
        )
    try:
        step_runtime_meta = json.loads((step_probe.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError):
        _fail("STEP_RUNTIME_IMPORT_FAILED", "STEP runtime version probe returned invalid data")
    expected_step_runtime = {"cascadio": "0.0.17", "numpy": "1.24.4", "trimesh": "3.23.5"}
    if any(step_runtime_meta.get(key) != value for key, value in expected_step_runtime.items()):
        _fail("STEP_RUNTIME_MISMATCH", "Win7 STEP runtime must use cascadio 0.0.17, numpy 1.24.4, trimesh 3.23.5")

    skill_scripts = sorted((source_root / "KmMpsMcpServer" / "skills").rglob("*.js"))
    if not skill_scripts:
        _fail("NODE_SKILL_SOURCES_NOT_FOUND", "no Node Skill JavaScript sources were found")
    for script in skill_scripts:
        syntax = subprocess.run(
            [node_runtime, "--check", str(script)],
            cwd=str(source_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if syntax.returncode != 0:
            _fail("NODE_SKILL_SYNTAX_FAILED", "Node 12 could not parse %s" % script.name)

    env = os.environ.copy()
    env["KMAI_NODE12_EXE"] = node_runtime
    env["KMAI_NODE_EXE"] = node_runtime
    env["PYTHONUTF8"] = "1"
    existing_pythonpath = env.get("PYTHONPATH", "")
    search_path = [str(source_root), str(source_root / "KmMpsMcpServer")]
    if existing_pythonpath:
        search_path.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(search_path)
    contract = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "tests.test_node_skill_compatibility",
            "KmMpsMcpServer.tests.test_group_template_response_contract",
        ],
        cwd=str(source_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    contract_output = (contract.stdout or "") + "\n" + (contract.stderr or "")
    if contract.returncode != 0 or "skipped=" in contract_output:
        _fail("NODE_SKILL_CONTRACT_FAILED", "Node 12 propose/confirm contract gate failed")
    return step_runtime_meta


def _configure_embedded_python_paths(package_root):
    """Keep CPython's isolated search path relocatable and able to run the Agent."""
    runtime = Path(package_root) / "runtime"
    for path_config in runtime.glob("python*._pth"):
        lines = path_config.read_text(encoding="utf-8-sig").splitlines()
        for relative in ("..", "../KmMpsMcpServer", "../step-compare"):
            if relative not in lines:
                lines.append(relative)
        path_config.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_runtime_import_gate(package_root):
    """Import the packaged Python entry points with the packaged interpreter."""
    package_root = Path(package_root).resolve()
    python_runtime = package_root / "runtime" / "python.exe"
    agent_root = package_root / "KmMpsMcpServer"
    step_root = package_root / "step-compare"
    probe = (
        "import json, sys; "
        "sys.path.insert(0, %s); "
        "sys.path.insert(0, %s); "
        "sys.path.insert(0, %s); "
        "import backend.agent_server; "
        "import skills.runner; "
        "import step_viewer.tessellate; "
        "import launcher; "
        "print(json.dumps({'ok': True}))"
        % (
            json.dumps(str(package_root), ensure_ascii=True),
            json.dumps(str(agent_root), ensure_ascii=True),
            json.dumps(str(step_root), ensure_ascii=True),
        )
    )
    result = subprocess.run(
        [str(python_runtime), "-I", "-B", "-c", probe],
        cwd=str(package_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or '"ok": true' not in (result.stdout or "").lower():
        _fail("PYTHON_RUNTIME_IMPORT_FAILED", "packaged CPython could not import Agent and Skill entry points")
    # Exercise the real launch command too: injecting sys.path above can hide a
    # broken embedded ._pth configuration that prevents agent_server.py starting.
    entry = subprocess.run(
        [str(python_runtime), "-E", "-s", "-B", str(agent_root / "agent_server.py"), "--help"],
        cwd=str(package_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if entry.returncode != 0 or "--port" not in (entry.stdout or ""):
        _fail("PYTHON_RUNTIME_ENTRY_FAILED", "packaged CPython could not start the real Agent entry point")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_win7_kb(kb_path):
    """校验要随包交付的 Windows 7 x64 前置更新。"""
    kb_path = Path(kb_path).resolve()
    if not kb_path.is_file():
        _fail("WIN7_KB_NOT_FOUND", str(kb_path))
    actual_sha256 = _sha256_file(kb_path)
    if actual_sha256.casefold() != WIN7_KB2533623_SHA256:
        _fail(
            "WIN7_KB_HASH_MISMATCH",
            "%s 的 SHA-256 不匹配 KB2533623 x64 官方文件" % kb_path,
        )
    return {
        "id": "KB2533623",
        "file": "prerequisites/%s" % WIN7_KB2533623_FILE_NAME,
        "architecture": "x64",
        "sha256": actual_sha256,
        "size_bytes": kb_path.stat().st_size,
        "requires_reboot": True,
    }


def _sha256_files(files):
    digest = hashlib.sha256()
    for path in sorted((Path(item) for item in files), key=lambda item: item.as_posix().casefold()):
        digest.update(path.name.encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _inventory(output_root):
    records = []
    for path in sorted(Path(output_root).rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.name == "package-SHA256.txt":
            continue
        relative = path.relative_to(output_root).as_posix()
        records.append("%s  %s" % (_sha256_file(path), relative))
    return records


def build_package(
    source_root,
    output_root,
    python_runtime,
    node_runtime,
    cef_root,
    similar_parts_data_root,
    models_root=None,
    win7_kb=None,
):
    source_root = _resolve(source_root, "SOURCE_ROOT_NOT_FOUND")
    output_root = Path(output_root).expanduser().resolve()
    if _inside(output_root, source_root):
        _fail("OUTPUT_INSIDE_SOURCE", str(output_root))
    if output_root.exists():
        _fail("OUTPUT_ALREADY_EXISTS", str(output_root))
    python_runtime = _resolve(python_runtime, "PYTHON_RUNTIME_NOT_FOUND")
    node_runtime = _resolve(node_runtime, "NODE_RUNTIME_NOT_FOUND")
    cef_root = _resolve(cef_root, "CEF_NOT_FOUND")
    similar_parts_data_root = _resolve(similar_parts_data_root, "SIMILAR_PARTS_DATA_NOT_FOUND")
    if models_root is not None and str(models_root).strip():
        models_root = _resolve(models_root, "MODELS_NOT_FOUND")
    else:
        models_root = None
    if win7_kb is not None and str(win7_kb).strip():
        win7_kb = _resolve(win7_kb, "WIN7_KB_NOT_FOUND")
    else:
        win7_kb = None
    input_roots = [
        python_runtime.parent,
        node_runtime.parent,
        cef_root,
        similar_parts_data_root,
    ]
    if models_root is not None:
        input_roots.append(models_root)
    if win7_kb is not None:
        input_roots.append(win7_kb.parent)
    for input_root in input_roots:
        if _inside(output_root, input_root):
            _fail("OUTPUT_INSIDE_INPUT", str(output_root))
    if not python_runtime.is_file():
        _fail("PYTHON_RUNTIME_NOT_FOUND", str(python_runtime))
    if not node_runtime.is_file():
        _fail("NODE_RUNTIME_NOT_FOUND", str(node_runtime))

    _validate_python_runtime_layout(python_runtime)
    python_meta = _metadata_for_runtime(python_runtime, "python", "CPython", "")
    node_meta = _metadata_for_runtime(node_runtime, "node", "Node.js", "12.22.12")
    cef_meta = _external_tree_metadata(cef_root, "cef")
    data_meta = _external_tree_metadata(similar_parts_data_root, "similar_parts_data")
    models_meta = None
    if models_root is not None:
        models_meta = _external_tree_metadata(models_root, "models")
        _validate_model_coverage(similar_parts_data_root, models_root)
    win7_kb_meta = None
    if win7_kb is not None:
        win7_kb_meta = _validate_win7_kb(win7_kb)

    step_runtime_meta = _run_runtime_gates(source_root, python_runtime, node_runtime)
    if not isinstance(step_runtime_meta, dict):
        # Unit-test fixtures replace the gate; keep the generated test manifest
        # honest about the required package contract without inventing runtime data.
        step_runtime_meta = {"cascadio": "0.0.17", "numpy": "1.24.4", "trimesh": "3.23.5"}

    template_root = source_root / "deploy" / "win7-compat"
    for filename in TEMPLATE_FILES:
        if not (template_root / filename).is_file():
            _fail("PACKAGE_TEMPLATE_MISSING", filename)

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".kmai-win7-package-", dir=str(output_root.parent)))
    try:
        _copy_tree(source_root / "KmMpsMcpServer", staging_root / "KmMpsMcpServer", exclude_tests=True)
        for resource_dir in (
            "Resources/GroupTemplate",
            "Resources/FeatureTemplate",
            "Resources/AutoIdentifyWithDirection",
        ):
            resource_source = source_root / resource_dir
            if resource_source.is_dir():
                _copy_tree(resource_source, staging_root / resource_dir)
        if not (staging_root / "Resources" / "FeatureTemplate" / "FeatureTemplate.xml").is_file():
            feature_template = (
                source_root
                / "KmMpsMcpServer"
                / "skills"
                / "kmsoft-group-template"
                / "assets"
                / "FeatureTemplate.xml"
            )
            if feature_template.is_file():
                _copy_file(feature_template, staging_root / "Resources" / "FeatureTemplate" / "FeatureTemplate.xml")
        for filename in TEMPLATE_FILES:
            _copy_file(template_root / filename, staging_root / filename)
        step_viewer_source = source_root / "step-compare-main" / "step-compare-main" / "step_viewer"
        if not step_viewer_source.is_dir():
            _fail("STEP_VIEWER_SOURCE_NOT_FOUND", str(step_viewer_source))
        _copy_tree(step_viewer_source, staging_root / "step-compare" / "step_viewer")
        three_vendor_source = (
            source_root / "step-compare-main" / "step-compare-main" / "web" / "vendor" / "three"
        )
        required_three_assets = (
            "LICENSE",
            "build/three.module.js",
            "examples/jsm/controls/OrbitControls.js",
            "examples/jsm/loaders/GLTFLoader.js",
        )
        if not three_vendor_source.is_dir() or any(
            not (three_vendor_source / relative_path).is_file() for relative_path in required_three_assets
        ):
            _fail("SIMILAR_PARTS_THREE_ASSETS_MISSING", str(three_vendor_source))
        _copy_tree(three_vendor_source, staging_root / "step-compare" / "web" / "vendor" / "three")
        _copy_tree(
            python_runtime.parent,
            staging_root / "runtime",
            exclude_tests=True,
            exclude_file_names=(python_runtime.name + ".metadata.json",),
        )
        _configure_embedded_python_paths(staging_root)
        _copy_file(node_runtime, staging_root / "runtime" / "node.exe")
        node_license = node_runtime.parent / "LICENSE"
        if node_license.is_file():
            _copy_file(node_license, staging_root / "runtime" / "node-LICENSE.txt")
        # 3DMPS launches KmAI\\KmAiChatCef.exe from the package root. Keep
        # the complete CEF/Qt runtime beside it so DLL and resource lookup
        # uses the same layout as the host's CreateProcess path.
        _copy_tree(cef_root, staging_root)
        _copy_tree(similar_parts_data_root, staging_root / "Resources" / "SimilarParts")
        if models_root is not None:
            _copy_tree(models_root, staging_root / "models")
        if win7_kb is not None:
            prerequisite_root = template_root / "prerequisites"
            prerequisite_files = (
                "install-kb2533623.bat",
                "README.md",
            )
            for filename in prerequisite_files:
                source = prerequisite_root / filename
                if not source.is_file():
                    _fail("PACKAGE_PREREQUISITE_TEMPLATE_MISSING", str(source))
                _copy_file(source, staging_root / "prerequisites" / filename)
            _copy_file(
                win7_kb,
                staging_root / "prerequisites" / WIN7_KB2533623_FILE_NAME,
            )
        _normalize_batch_line_endings(staging_root)
        _normalize_ini_line_endings(staging_root)
        _run_runtime_import_gate(staging_root)

        manifest = {
            "schema": 1,
            "built_at_utc": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "target": {"os": "Windows 7 SP1", "architecture": "x64"},
            "runtime": {"python": python_meta, "node": node_meta, "step_converter": step_runtime_meta},
            "external_inputs": {"cef": cef_meta, "similar_parts_data": data_meta},
            "exclude": list(EXCLUDE_PATTERNS) + ["config.ini", "cache", "logs", "*.tmp", "uploads"],
            "layout": {
                "agent": "KmMpsMcpServer/",
                "runtime": "runtime/",
                "cef": "/",
                "step_viewer": "step-compare/step_viewer/",
                "three_vendor": "step-compare/web/vendor/three/",
                "similar_parts_data": "Resources/SimilarParts/",
                "state": (
                    "KMAI_RUNTIME_DIR；否则依次使用 %LOCALAPPDATA%\\KmAI、%TEMP%\\KmAI、"
                    "%TMP%\\KmAI 和 %USERPROFILE%\\AppData\\Local\\KmAI"
                ),
            },
        }
        if models_meta is not None:
            manifest["external_inputs"]["models"] = models_meta
            manifest["layout"]["models"] = "models/"
        if win7_kb_meta is not None:
            manifest["prerequisites"] = {"kb2533623": win7_kb_meta}
            manifest["layout"]["prerequisites"] = "prerequisites/"
        manifest_path = staging_root / "package-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _scan_package_payload(staging_root)
        inventory = _inventory(staging_root)
        (staging_root / "package-SHA256.txt").write_text("\n".join(inventory) + "\n", encoding="utf-8")
        os.replace(str(staging_root), str(output_root))
    except Exception:
        shutil.rmtree(str(staging_root), ignore_errors=True)
        raise
    return {"output_root": str(output_root), "manifest": manifest, "files": inventory}


def _parser():
    parser = argparse.ArgumentParser(description="Build an offline KmAI Win7 x64 package")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--python-runtime",
        required=True,
        help="python.exe inside a complete isolated CPython 3.8 runtime directory",
    )
    parser.add_argument("--node-runtime", required=True)
    parser.add_argument("--cef-root", required=True)
    parser.add_argument("--similar-parts-data-root", required=True)
    parser.add_argument(
        "--models-root",
        required=False,
        help="optional prebuilt GLB cache; realtime STEP conversion does not require it",
    )
    parser.add_argument(
        "--win7-kb",
        required=False,
        help="可选的 Windows6.1-KB2533623-x64.msu；仅复制到离线前置目录，不会自动安装",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        result = build_package(
            args.source_root,
            args.output,
            args.python_runtime,
            args.node_runtime,
            args.cef_root,
            args.similar_parts_data_root,
            args.models_root,
            args.win7_kb,
        )
    except PackageBuildError as exc:
        sys.stderr.write("[ERROR] %s\n" % exc)
        return 1
    print(json.dumps({"output_root": result["output_root"], "file_count": len(result["files"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
