from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

FEATURE_NAMES = (
    "hollow_ratio",
    "inner_rev_ratio",
    "inner_cyl_balance",
    "wall_to_outer",
    "slenderness",
    "plane_ratio",
    "inner_cyl_ratio",
    "outer_cyl_ratio",
)

NAME_SURFACE_AREA = "零件总体表面积"
NAME_INNER_REV_AREA = "零件总体内回转面表面积"
NAME_PLANE_RATIO = "平面总面积占比"
NAME_INNER_CYL_RATIO = "内圆柱总面积占比"
NAME_OUTER_CYL_RATIO = "外圆柱总面积占比"
NAME_WALL_MEAN = "薄壁圆柱厚度均值"
NAME_MAX_OUTER = "最大外径"
NAME_MIN_INNER = "最小内径"
NAME_SLENDERNESS = "零件细长度"

_INVALID = "未采用：{name} 无效（缺字段或取值无效）"


@dataclass(frozen=True)
class Fingerprint:
    values: dict[str, float | None]
    invalid_reasons: dict[str, str]

    def get(self, name: str) -> float | None:
        return self.values.get(name)


def collect_params(root: ET.Element) -> dict[str, str]:
    params: dict[str, str] = {}
    for param in root.iter("Param"):
        name = param.get("name")
        if name is None:
            continue
        value = param.get("value")
        if value is None:
            continue
        params[name] = value
    return params


def _parse_float(params: dict[str, str], name: str) -> float | None:
    raw = params.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _mark_invalid(
    values: dict[str, float | None],
    reasons: dict[str, str],
    name: str,
) -> None:
    values[name] = None
    reasons[name] = _INVALID.format(name=name)


def extract_fingerprint(root: ET.Element) -> Fingerprint:
    params = collect_params(root)
    values: dict[str, float | None] = {name: None for name in FEATURE_NAMES}
    reasons: dict[str, str] = {}

    surface = _parse_float(params, NAME_SURFACE_AREA)
    inner_rev = _parse_float(params, NAME_INNER_REV_AREA)
    max_outer = _parse_float(params, NAME_MAX_OUTER)
    min_inner = _parse_float(params, NAME_MIN_INNER)
    inner_cyl = _parse_float(params, NAME_INNER_CYL_RATIO)
    outer_cyl = _parse_float(params, NAME_OUTER_CYL_RATIO)
    wall = _parse_float(params, NAME_WALL_MEAN)
    slenderness = _parse_float(params, NAME_SLENDERNESS)
    plane = _parse_float(params, NAME_PLANE_RATIO)

    if min_inner is None or max_outer is None or max_outer <= 0:
        _mark_invalid(values, reasons, "hollow_ratio")
    else:
        values["hollow_ratio"] = min_inner / max_outer

    if inner_rev is None or surface is None or surface == 0:
        _mark_invalid(values, reasons, "inner_rev_ratio")
    else:
        values["inner_rev_ratio"] = inner_rev / surface

    if inner_cyl is None or outer_cyl is None or (inner_cyl + outer_cyl) == 0:
        _mark_invalid(values, reasons, "inner_cyl_balance")
    else:
        values["inner_cyl_balance"] = inner_cyl / (inner_cyl + outer_cyl)

    if wall is None or max_outer is None or max_outer <= 0:
        _mark_invalid(values, reasons, "wall_to_outer")
    else:
        values["wall_to_outer"] = wall / max_outer

    if slenderness is None:
        _mark_invalid(values, reasons, "slenderness")
    else:
        values["slenderness"] = slenderness

    if plane is None:
        _mark_invalid(values, reasons, "plane_ratio")
    else:
        values["plane_ratio"] = plane

    if inner_cyl is None:
        _mark_invalid(values, reasons, "inner_cyl_ratio")
    else:
        values["inner_cyl_ratio"] = inner_cyl

    if outer_cyl is None:
        _mark_invalid(values, reasons, "outer_cyl_ratio")
    else:
        values["outer_cyl_ratio"] = outer_cyl

    return Fingerprint(values=values, invalid_reasons=reasons)
