# -*- coding: utf-8 -*-
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_uses_vendored_three_js_without_network_urls():
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "/static/vendor/three/build/three.module.js" in index
    assert "/static/vendor/three/examples/jsm/" in index
    assert "/static/favicon.svg" in index
    assert "https://" not in index
    assert "http://" not in index
    assert (ROOT / "web" / "vendor" / "three" / "build" / "three.module.js").is_file()
    assert (ROOT / "web" / "vendor" / "three" / "examples" / "jsm" / "controls" / "OrbitControls.js").is_file()
    assert (ROOT / "web" / "vendor" / "three" / "examples" / "jsm" / "loaders" / "GLTFLoader.js").is_file()
    assert (ROOT / "web" / "vendor" / "three" / "examples" / "jsm" / "utils" / "BufferGeometryUtils.js").is_file()
    assert (ROOT / "web" / "favicon.svg").is_file()
    assert "three@0.160.0" in (ROOT / "web" / "vendor" / "three" / "README.md").read_text(encoding="utf-8")


def test_runtime_requirements_are_pinned_and_hashed():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    entries = [line for line in requirements if line and not line.startswith("#")]
    assert len(entries) == 18
    assert all("==" in line and " --hash=sha256:" in line for line in entries)


def test_portable_build_files_keep_runtime_and_wheel_cache_out_of_zip_source():
    starter = (ROOT / "start.bat").read_text(encoding="ascii")
    builder = (ROOT / "scripts" / "build-offline.ps1").read_text(encoding="utf-8")
    starter_script = (ROOT / "scripts" / "start-portable.ps1").read_text(encoding="utf-8")
    ignores = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "runtime\\python\\python.exe" in starter
    assert "--no-browser" in starter_script
    assert "--require-hashes" in builder
    assert "--no-index --find-links $wheelhouse" in builder
    assert "..\\.." in builder
    assert "https://pypi.org/simple/" in builder
    assert ".offline-build/" in ignores
    assert ".offline-lock/" in ignores
