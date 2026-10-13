# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
import trimesh

from step_viewer import tessellate as tessellate_module
from step_viewer.tessellate import TessellateError, _part_name, parse_source_unit, tessellate_step

FIXTURE = Path(__file__).resolve().parents[1] / "S-DEMO-02.stp"


def test_invalid_step_raises_readable_error():
    with pytest.raises(TessellateError, match="无法解析"):
        tessellate_step(b"not a step file", "bad.stp")


def test_demo_part_bounds_are_millimetres():
    result = tessellate_step(FIXTURE.read_bytes(), "S-DEMO-02.stp")
    assert result.name == "S-DEMO-02"
    assert result.unit == "mm"
    assert result.vertices > 100
    assert result.faces > 100
    dx, dy, dz = result.extents
    assert dx == pytest.approx(50.0, abs=0.2)
    assert dy == pytest.approx(50.0, abs=0.2)
    assert dz == pytest.approx(25.0, abs=0.2)
    assert result.glb[:4] == b"glTF"


def test_empty_bytes_raises():
    with pytest.raises(TessellateError):
        tessellate_step(b"", "empty.stp")


def test_display_name_uses_filename_not_embedded_product():
    result = tessellate_step(FIXTURE.read_bytes(), "机加样例4.stp")
    assert result.name == "机加样例4"


def test_display_name_strips_path_and_step_suffix():
    assert _part_name(r"C:\parts\ZHB kuangjia.STEP") == "ZHB kuangjia"


def test_display_name_falls_back_when_filename_missing():
    assert _part_name("") == "STEP"


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        (b"SI_UNIT(.MILLI.,.METRE.)", "mm"),
        (b"SI_UNIT(.CENTI.,.METRE.)", "cm"),
        (b"SI_UNIT($,.METRE.)", "m"),
        (b"CONVERSION_BASED_UNIT('INCH',#1)", "in"),
        (b"CONVERSION_BASED_UNIT('FOOT',#1)", "ft"),
    ],
)
def test_parse_source_unit_supports_common_length_units(declaration, expected):
    assert parse_source_unit(b"ISO-10303-21;" + declaration) == expected


def test_unknown_source_unit_is_rejected_without_guessing():
    with pytest.raises(TessellateError) as exc_info:
        parse_source_unit(b"ISO-10303-21;SI_UNIT(.FURLONG.,.METRE.)")
    assert exc_info.value.code == "UNSUPPORTED_UNIT"


def test_large_millimetre_model_is_scaled_without_size_heuristic(monkeypatch):
    source_glb = trimesh.creation.box(extents=[3.0, 1.0, 1.0]).export(file_type="glb")
    monkeypatch.setattr(tessellate_module.cascadio, "load", lambda *args, **kwargs: source_glb)
    data = b"ISO-10303-21;SI_UNIT(.MILLI.,.METRE.)"
    result = tessellate_step(data, "large.stp")
    assert result.source_unit == "mm"
    assert result.extents[0] == pytest.approx(3000.0)


def test_preview_conversion_uses_coarse_enough_tessellation_tolerance(monkeypatch):
    source_glb = trimesh.creation.box().export(file_type="glb")
    calls = []

    def fake_load(*args, **kwargs):
        calls.append(kwargs)
        return source_glb

    monkeypatch.setattr(tessellate_module.cascadio, "load", fake_load)
    tessellate_step(b"ISO-10303-21;SI_UNIT(.MILLI.,.METRE.)", "preview.stp")

    assert calls[0]["tol_linear"] == pytest.approx(0.01)
    assert calls[0]["tol_angular"] == pytest.approx(0.15)
