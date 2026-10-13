#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REFERENCE_DIR = SKILL_DIR / "references"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_technical_requirements as tech_engine


def read_request():
    raw = sys.stdin.buffer.read()
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def as_string_list(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def normalize_manual(request_payload):
    manual = request_payload.get("manual") if isinstance(request_payload, dict) else {}
    if not isinstance(manual, dict):
        manual = {}

    special_flags = manual.get("special_process_flags")
    if not isinstance(special_flags, dict):
        special_flags = {}

    inspection_items = as_string_list(manual.get("inspection_items"))
    marking_methods = as_string_list(manual.get("marking_methods"))
    surface_treatments = as_string_list(manual.get("surface_treatments"))

    return {
        "material_grade": (str(manual.get("material_grade") or "").strip() or None),
        "part_class": (str(manual.get("part_type") or "").strip() or None),
        "heat_treatment": (str(manual.get("heat_treatment") or "").strip() or None),
        "surface_treatment": (surface_treatments[0] if surface_treatments else None),
        "has_marking": bool(marking_methods),
        "need_crack_check": any(item in ("裂纹检测", "磁粉检测") for item in inspection_items),
        "need_burn_check": any(item == "烧伤检查" for item in inspection_items),
        "special_process_flags": {
            "shaped_hole_or_cut_flat": bool(special_flags.get("shaped_hole_or_cut_flat")),
            "post_stage_added_hole": bool(special_flags.get("post_stage_added_hole")),
        },
        "surface_treatments": surface_treatments,
        "inspection_items": inspection_items,
        "marking_methods": marking_methods,
    }


def extract_route_input(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("route_input", "matched_route"):
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            return deepcopy(value)
    return None


def extract_cad_input(payload):
    if not isinstance(payload, dict):
        return []
    value = payload.get("cad_input")
    if isinstance(value, list):
        return deepcopy(value)
    return []


def extract_upstream_part_context(payload):
    value = payload.get("upstream_part_context") if isinstance(payload, dict) else None
    if isinstance(value, dict):
        return deepcopy(value)
    return None


def route_rows_from_output(output):
    if isinstance(output, dict) and isinstance(output.get("工艺路线"), list):
        rows = output.get("工艺路线") or []
        export_rows = []
        for process in rows:
            if not isinstance(process, dict):
                continue
            steps_raw = process.get("工步", [])
            if not isinstance(steps_raw, list):
                steps_raw = []
            steps = []
            for step in steps_raw:
                if isinstance(step, dict):
                    candidates = step.get("候选分组", {})
                    if not isinstance(candidates, dict):
                        candidates = {}
                    candidate_details = step.get("候选明细", [])
                    if not isinstance(candidate_details, list):
                        candidate_details = []
                    is_last = False
                    for detail in candidate_details:
                        if not isinstance(detail, dict):
                            continue
                        feature_flags = detail.get("feature_flags", [])
                        if not isinstance(feature_flags, list):
                            continue
                        if any(
                            isinstance(flag, dict) and bool(flag.get("is_last_process_for_feature"))
                            for flag in feature_flags
                        ):
                            is_last = True
                            break
                    steps.append({
                        "step_name": str(step.get("工步名") or step.get("工步名称") or ""),
                        "candidates": candidates,
                        "candidate_details": candidate_details,
                        "is_last": is_last,
                    })
                else:
                    steps.append({
                        "step_name": str(step),
                        "candidates": {},
                        "candidate_details": [],
                        "is_last": False,
                    })
            tech_reqs = process.get("技术要求", [])
            if not isinstance(tech_reqs, list):
                tech_reqs = []
            export_rows.append({
                "process_name": str(process.get("工序名") or process.get("工序名称") or process.get("process_name") or ""),
                "process_type": str(process.get("工序类型") or process.get("process_type") or ""),
                "precision": str(process.get("加工精度") or process.get("precision") or ""),
                "technical_requirements": tech_reqs,
                "steps": steps,
            })
        return export_rows

    if isinstance(output, list):
        rows = []
        for item in output:
            if not isinstance(item, dict):
                continue
            tech_reqs = item.get("technical_requirements")
            if not isinstance(tech_reqs, list):
                tech_reqs = item.get("技术要求", [])
            if not isinstance(tech_reqs, list):
                tech_reqs = []
            rows.append({
                "process_name": str(item.get("process_name") or item.get("工序名") or item.get("工序名称") or ""),
                "process_type": str(item.get("process_type") or item.get("工序类型") or ""),
                "precision": str(item.get("precision") or item.get("加工精度") or ""),
                "technical_requirements": tech_reqs,
                "steps": item.get("steps") if isinstance(item.get("steps"), list) else [],
            })
        return rows

    return []


def generate_result(request_payload):
    route_input = extract_route_input(request_payload)
    if route_input is None:
        raise ValueError("route_input is empty")

    cad_input = extract_cad_input(request_payload)
    manual_context = normalize_manual(request_payload)
    upstream_part_context = extract_upstream_part_context(request_payload)

    rules_obj = tech_engine.load_json(REFERENCE_DIR / "technical_requirement_rules.json")
    templates_obj = tech_engine.load_json(REFERENCE_DIR / "technical_requirement_templates.json")
    part_context = tech_engine.build_part_context(
        cad_input=cad_input,
        manual_context=manual_context,
        upstream_part_context=upstream_part_context,
    )
    output = tech_engine.apply_rules(route_input, part_context, rules_obj, templates_obj)
    route_rows = route_rows_from_output(output)

    return {
      "ok": True,
      "status": "success",
      "part_context": part_context,
      "matched_route": output,
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
