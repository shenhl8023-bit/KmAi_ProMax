# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
from dataclasses import dataclass

import cascadio
import trimesh


class TessellateError(Exception):
    """A stable, user-facing STEP conversion error."""

    def __init__(self, message: str, code: str = "INVALID_STEP") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class TessellateResult:
    name: str
    glb: bytes
    bounds: list[list[float]]
    extents: list[float]
    vertices: int
    faces: int
    unit: str
    source_unit: str = "mm"


_SI_UNIT_RE = re.compile(
    rb"SI_UNIT\s*\(\s*(?:\$|\.(?P<prefix>[A-Z]+)\.)\s*,\s*\.(?:METRE|METER)\.\s*\)",
    re.IGNORECASE,
)
_CONVERSION_UNIT_RE = re.compile(
    rb"CONVERSION_BASED_UNIT\s*\(\s*'(?P<name>[^']+)'",
    re.IGNORECASE,
)

_SI_UNITS = {
    "": ("m", 1000.0),
    "DECI": ("dm", 100.0),
    "CENTI": ("cm", 10.0),
    "MILLI": ("mm", 1.0),
    "MICRO": ("um", 0.001),
    "NANO": ("nm", 0.000001),
    "DECA": ("dam", 10000.0),
    "HECTO": ("hm", 100000.0),
    "KILO": ("km", 1000000.0),
}
_CONVERSION_UNITS = {
    "MM": "mm",
    "MILLIMETRE": "mm",
    "MILLIMETER": "mm",
    "CM": "cm",
    "CENTIMETRE": "cm",
    "CENTIMETER": "cm",
    "M": "m",
    "METRE": "m",
    "METER": "m",
    "IN": "in",
    "INCH": "in",
    "INCHES": "in",
    "FT": "ft",
    "FOOT": "ft",
    "FEET": "ft",
}


def parse_source_unit(data: bytes) -> str:
    """Return the declared STEP length unit, or raise when it is ambiguous."""
    upper = data.upper()
    for match in _SI_UNIT_RE.finditer(upper):
        prefix = (match.group("prefix") or b"").decode("ascii").upper()
        unit = _SI_UNITS.get(prefix)
        if unit:
            return unit[0]

    for match in _CONVERSION_UNIT_RE.finditer(upper):
        raw_name = re.sub(rb"[^A-Z0-9]+", b"", match.group("name")).decode("ascii")
        unit = _CONVERSION_UNITS.get(raw_name)
        if unit:
            return unit

    raise TessellateError("STEP 长度单位缺失或不受支持", "UNSUPPORTED_UNIT")


def _part_name(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = re.sub(r"\.(stp|step)$", "", stem, flags=re.IGNORECASE)
    return stem or "STEP"


def _to_mesh(glb: bytes) -> trimesh.Trimesh:
    try:
        loaded = trimesh.load(io.BytesIO(glb), file_type="glb", force="mesh")
        if isinstance(loaded, trimesh.Scene):
            geoms = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not geoms:
                raise TessellateError("网格为空，没有可显示的实体", "EMPTY_MESH")
            loaded = trimesh.util.concatenate(geoms)
        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise TessellateError("网格为空，没有可显示的实体", "EMPTY_MESH")
        return loaded
    except TessellateError:
        raise
    except Exception as exc:
        raise TessellateError("转换结果不是有效的 GLB", "INVALID_GLB") from exc


def tessellate_step(data: bytes, filename: str = "") -> TessellateResult:
    if not data or not data.lstrip().upper().startswith(b"ISO-10303"):
        raise TessellateError("无法解析 STEP 文件", "INVALID_STEP")

    source_unit = parse_source_unit(data)
    try:
        # This mesh is for interactive preview, not manufacturing inspection.
        # A 0.12 mm tolerance makes some otherwise small NX exports spend many
        # minutes in OpenCascade.  10 mm in SI metres still preserves
        # the visible part shape while keeping browser previews responsive.
        glb = cascadio.load(data, file_type="step", tol_linear=0.01, tol_angular=0.15)
    except Exception as exc:
        raise TessellateError("无法解析 STEP 文件", "INVALID_STEP") from exc

    if not glb:
        raise TessellateError("网格为空，没有可显示的实体", "EMPTY_MESH")

    mesh = _to_mesh(glb)
    try:
        # cascadio emits SI metres; normalize every declared STEP unit to mm.
        mesh.apply_scale(1000.0)
        try:
            mesh.fix_normals()
        except ModuleNotFoundError as exc:
            # trimesh treats scipy as optional; the portable runtime deliberately
            # does not ship it because rendering does not require it.
            if exc.name != "scipy" and "scipy" not in str(exc):
                raise
        if hasattr(mesh.visual, "vertex_colors"):
            mesh.visual.vertex_colors = [180, 186, 194, 255]
        exported = mesh.export(file_type="glb")
    except TessellateError:
        raise
    except Exception as exc:
        raise TessellateError("无法导出有效的 GLB 网格", "INVALID_GLB") from exc

    if isinstance(exported, str):
        exported = exported.encode("utf-8")
    if not exported:
        raise TessellateError("网格为空，没有可显示的实体", "EMPTY_MESH")

    bounds = mesh.bounds.tolist()
    extents = mesh.extents.tolist()
    return TessellateResult(
        name=_part_name(filename),
        glb=bytes(exported),
        bounds=[[float(v) for v in bounds[0]], [float(v) for v in bounds[1]]],
        extents=[float(v) for v in extents],
        vertices=int(len(mesh.vertices)),
        faces=int(len(mesh.faces)),
        unit="mm",
        source_unit=source_unit,
    )
