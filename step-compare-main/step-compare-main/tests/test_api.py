# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from step_viewer.app import app, conversion_service

FIXTURE = Path(__file__).resolve().parents[1] / "S-DEMO-02.stp"
client = TestClient(app)


def test_health_endpoint_returns_ready_status():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tessellate_endpoint_returns_mesh_metadata():
    response = client.post(
        "/api/tessellate",
        files={"file": ("机加样例4.stp", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "机加样例4"
    assert body["unit"] == "mm"
    assert body["extents"][0] == pytest.approx(50.0, abs=0.2)
    assert body["glb"]


def test_tessellate_rejects_garbage():
    response = client.post(
        "/api/tessellate",
        files={"file": ("x.stp", b"hello", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "无法解析" in response.json()["detail"]


def test_v2_returns_metadata_and_binary_model():
    response = client.post(
        "/api/tessellate/v2",
        files={"file": ("second.stp", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "second"
    assert body["source_unit"] == "mm"
    assert body["glb_url"].startswith("/api/models/")

    model = client.get(body["glb_url"])
    assert model.status_code == 200
    assert model.headers["content-type"].startswith("model/gltf-binary")
    assert model.content[:4] == b"glTF"


def test_v2_uses_stable_error_for_upload_limit(monkeypatch):
    monkeypatch.setattr(conversion_service, "max_upload_bytes", 4)
    response = client.post(
        "/api/tessellate/v2",
        files={"file": ("large.stp", b"12345", "application/octet-stream")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"
