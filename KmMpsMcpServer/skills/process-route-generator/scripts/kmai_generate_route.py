#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REFERENCE_V1_DIR = SKILL_DIR / "references" / "v1"
CAD_REFERENCE_DIR = SKILL_DIR / "references" / "cad_reference"


if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_matched_route as match_engine
import generate_route as route_engine


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_request():
    raw = sys.stdin.buffer.read()
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def as_string_list(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def extract_cad_input(request_payload):
    if not isinstance(request_payload, dict):
        return []

    for key in ("cad_input", "cad_features", "input_json"):
        value = request_payload.get(key)
        if isinstance(value, list):
            return value

    payload = request_payload.get("payload")
    if isinstance(payload, dict):
        for key in ("cad_input", "cad_features", "input_json"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []


def normalize_manual(request_payload):
    manual = request_payload.get("manual") if isinstance(request_payload, dict) else {}
    if not isinstance(manual, dict):
        manual = {}

    special_flags = manual.get("special_process_flags")
    if not isinstance(special_flags, dict):
        special_flags = {}

    factor_overrides = manual.get("factor_overrides")
    if not isinstance(factor_overrides, dict):
        factor_overrides = {}

    material_grade = manual.get("material_grade")
    part_type = manual.get("part_type")
    heat_treatment = manual.get("heat_treatment")

    return {
        "material_grade": (str(material_grade).strip() if material_grade is not None else ""),
        "part_type": (str(part_type).strip() if part_type is not None else ""),
        "heat_treatment": (str(heat_treatment).strip() if heat_treatment is not None else ""),
        "surface_treatments": as_string_list(manual.get("surface_treatments")),
        "inspection_items": as_string_list(manual.get("inspection_items")),
        "marking_methods": as_string_list(manual.get("marking_methods")),
        "special_process_flags": {
            "shaped_hole_or_cut_flat": bool(special_flags.get("shaped_hole_or_cut_flat")),
            "post_stage_added_hole": bool(special_flags.get("post_stage_added_hole")),
        },
        "factor_overrides": factor_overrides,
    }


def build_runtime_payload(cad_input, manual):
    return {
        "cad_features": cad_input,
        "manual": {
            "heat_treatment": manual.get("heat_treatment") or None,
            "surface_treatments": manual.get("surface_treatments", []),
            "inspection_items": manual.get("inspection_items", []),
            "marking_methods": manual.get("marking_methods", []),
            "special_process_flags": manual.get("special_process_flags", {}),
            "factor_overrides": manual.get("factor_overrides", {}),
        },
        "part_info": {
            "material_grade": manual.get("material_grade") or None,
            "part_type": manual.get("part_type") or None,
        },
    }


def count_features(cad_input):
    total = 0
    for block in cad_input:
        if not isinstance(block, dict):
            continue
        features = block.get("features")
        if isinstance(features, list):
            total += len(features)
    return total


def build_summary(cad_input, route_rows, factors):
    true_factors = []
    if isinstance(factors, dict):
        for key, value in factors.items():
            if value is True:
                true_factors.append(key)

    step_count = 0
    for row in route_rows:
        if not isinstance(row, dict):
            continue
        steps = row.get("steps")
        if isinstance(steps, list):
            step_count += len(steps)

    return {
        "group_block_count": len(cad_input),
        "feature_count": count_features(cad_input),
        "process_count": len(route_rows),
        "step_count": step_count,
        "true_factor_keys": true_factors,
    }


def generate_result(request_payload):
    cad_input = extract_cad_input(request_payload)
    if not isinstance(cad_input, list) or not cad_input:
        raise ValueError("cad_input is empty")

    manual = normalize_manual(request_payload)
    runtime_payload = build_runtime_payload(cad_input, manual)

    factor_schema = load_json(REFERENCE_V1_DIR / "factor_schema.json")
    expansion_rules = load_json(REFERENCE_V1_DIR / "factor_expansion_rules.json")
    route_catalog = load_json(REFERENCE_V1_DIR / "route_catalog.json")
    route_rules = load_json(REFERENCE_V1_DIR / "route_rules.json")
    group_match_rules = load_json(REFERENCE_V1_DIR / "group_match_rules.json")
    cad_catalog = load_json(CAD_REFERENCE_DIR / "cad_feature_catalog.json")

    factors = route_engine.factors_from_v1_input(
        runtime_payload,
        factor_schema,
        expansion_rules,
        cad_catalog,
    )
    standard_route = route_engine.build_v1_route(factors, route_catalog, route_rules)
    matched_route = match_engine.build_matched_route_output(
        standard_route,
        cad_input,
        group_match_rules,
        cad_catalog,
        route_catalog,
    )
    route_rows = match_engine.export_route_rows(matched_route)

    return {
        "ok": True,
        "status": "success",
        "summary": build_summary(cad_input, route_rows, factors),
        "normalized_input": runtime_payload,
        "factors": factors,
        "standard_route": standard_route,
        "matched_route": matched_route,
        "route": route_rows,
    }


def main():
    try:
        request_payload = read_request()
        result = generate_result(request_payload)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except Exception as exc:
        error = {
            "ok": False,
            "status": "error",
            "error": str(exc),
        }
        sys.stdout.buffer.write(json.dumps(error, ensure_ascii=False).encode("utf-8"))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
