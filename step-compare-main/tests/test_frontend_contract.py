# -*- coding: utf-8 -*-
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")


def test_frontend_uses_binary_v2_api_and_has_request_race_guards():
    assert 'fetch("/api/tessellate/v2"' in JS
    assert ".arrayBuffer()" in JS
    assert "atob(" not in JS
    assert "AbortController" in JS
    assert "request.sequence" in JS
    assert "isCurrentRequest" in JS


def test_frontend_handles_gltf_errors_and_disposes_gpu_resources():
    assert "loader.parse(buffer, \"\", resolve, reject)" in JS
    assert ".geometry.dispose()" in JS
    assert ".isTexture" in JS
    assert "material.dispose()" in JS
    assert "stepViewerMaterial" in JS


def test_upload_markup_accessibility_and_mobile_layout():
    assert '<label class="dropzone"' in HTML
    assert '<button type="button" class="clear"' in HTML
    assert '<label class="slot"' not in HTML
    assert 'aria-pressed="true"' in HTML
    assert 'aria-pressed="false"' in HTML
    assert "@media (max-width: 720px)" in CSS
    assert ".slots { grid-template-columns: 1fr; }" in CSS


def test_runtime_frontend_has_no_external_url_dependency():
    runtime_sources = "\n".join(
        (ROOT / "web" / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.js", "align.js", "style.css")
    )
    assert "http://" not in runtime_sources
    assert "https://" not in runtime_sources
