#!/usr/bin/env python3
"""Generate a simplified process route from factor values or CAD/MPS input."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FACTOR_ID_RE = re.compile(r"^F\d{3}$")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def payload_is_factor_map(payload: dict[str, Any]) -> bool:
    return bool(payload) and all(isinstance(k, str) and FACTOR_ID_RE.fullmatch(k) for k in payload)


def direct_factors_from_input(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload_is_factor_map(payload):
        return dict(payload)

    for key in ("因素值", "因素", "factor_values", "factors"):
        value = payload.get(key)
        if isinstance(value, dict):
            return dict(value)
    return None


def flatten_feature_entries(payload: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    if isinstance(payload, list):
        blocks = payload
    elif isinstance(payload, dict):
        for key in ("features", "cad_features", "feature_blocks", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                blocks = value
                break
        else:
            blocks = []
    else:
        blocks = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        group_path = str(block.get("group_path", ""))
        features = block.get("features", [])
        if not isinstance(features, list):
            continue
        for feature in features:
            if not isinstance(feature, dict):
                continue
            entries.append(
                {
                    "group_path": group_path,
                    "feature_select": str(feature.get("feature_select", "")),
                    "precision_rank": feature.get("feat_rank"),
                }
            )
    return entries


def build_sub_feature_lookup(cad_catalog: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in cad_catalog.get("canonical_features", []):
        if not isinstance(item, dict):
            continue
        canonical = item.get("canonical_feature")
        if not isinstance(canonical, str):
            continue
        lookup[canonical] = canonical
        for sub_feature in item.get("sub_features", []):
            if isinstance(sub_feature, str):
                lookup[sub_feature] = canonical
    return lookup


def normalize_cad_features(payload: Any, cad_catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    entries = flatten_feature_entries(payload)
    if not cad_catalog:
        return entries

    lookup = build_sub_feature_lookup(cad_catalog)
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        feature_select = entry.get("feature_select", "")
        normalized.append(
            {
                **entry,
                "canonical_feature": lookup.get(feature_select, feature_select),
            }
        )
    return normalized


def get_nested_value(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def collect_input_context(payload: Any, normalized_cad_features: list[dict[str, Any]]) -> dict[str, Any]:
    input_ctx: dict[str, Any] = {}
    manual_ctx: dict[str, Any] = {}

    if isinstance(payload, dict):
        part = payload.get("零件信息")
        if isinstance(part, dict):
            input_ctx["material_grade"] = part.get("材料牌号")
            input_ctx["part_type"] = part.get("零件类型")

        english_part = payload.get("part_info")
        if isinstance(english_part, dict):
            input_ctx["material_grade"] = english_part.get("material_grade", input_ctx.get("material_grade"))
            input_ctx["part_type"] = english_part.get("part_type", input_ctx.get("part_type"))

        manual = payload.get("人工补充")
        if isinstance(manual, dict):
            manual_ctx = manual

        manual_en = payload.get("manual")
        if isinstance(manual_en, dict):
            manual_ctx = {**manual_ctx, **manual_en}

        simplified = payload.get("简化特征")
        if isinstance(simplified, dict):
            manual_ctx.setdefault("heat_treatment", simplified.get("热处理"))
            manual_ctx.setdefault("surface_treatments", simplified.get("表面处理"))
            manual_ctx.setdefault("inspection_items", simplified.get("检测"))
            manual_ctx.setdefault("marking_methods", simplified.get("标识"))

            structure = simplified.get("结构特征")
            if isinstance(structure, list):
                special_flags = manual_ctx.setdefault("special_process_flags", {})
                if isinstance(special_flags, dict):
                    if "型孔" in structure or "割扁" in structure:
                        special_flags.setdefault("shaped_hole_or_cut_flat", True)
                    if "后段补充孔" in structure:
                        special_flags.setdefault("post_stage_added_hole", True)

    return {
        "input": input_ctx,
        "manual": manual_ctx,
        "cad_features": normalized_cad_features,
    }


def compare_values(actual: Any, op: str, expected: Any) -> bool:
    if op == "=":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == ">":
        return actual is not None and actual > expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "<":
        return actual is not None and actual < expected
    if op == "<=":
        return actual is not None and actual <= expected
    if op == "in":
        return actual in expected if isinstance(expected, list | tuple | set) else False
    if op == "not_in":
        return actual not in expected if isinstance(expected, list | tuple | set) else True
    if op == "contains":
        if isinstance(actual, list):
            return expected in actual
        if isinstance(actual, str):
            return str(expected) in actual
        return False
    if op == "not_contains":
        if isinstance(actual, list):
            return expected not in actual
        if isinstance(actual, str):
            return str(expected) not in actual
        return True
    if op == "exists":
        return actual is not None
    raise ValueError(f"Unsupported operator: {op}")


def match_feature_condition(
    condition: dict[str, Any],
    cad_features: list[dict[str, Any]],
) -> bool:
    match_mode = condition.get("match_mode", "exists")
    filters = condition.get("filters", [])
    if match_mode != "exists" or not isinstance(filters, list):
        return False

    for feature in cad_features:
        matched = True
        for feature_filter in filters:
            if not isinstance(feature_filter, dict):
                matched = False
                break
            field = feature_filter.get("field")
            op = feature_filter.get("op", "=")
            expected = feature_filter.get("value")
            actual = feature.get(field)
            if not compare_values(actual, op, expected):
                matched = False
                break
        if matched:
            return True
    return False


def match_expansion_condition(
    condition: dict[str, Any],
    context: dict[str, Any],
    expanded_factors: dict[str, Any],
) -> bool:
    source = condition.get("source")

    if source == "cad_feature":
        return match_feature_condition(condition, context.get("cad_features", []))

    if source == "factor":
        field = condition.get("field")
        op = condition.get("op", "=")
        expected = condition.get("value")
        actual = expanded_factors.get(field)
        return compare_values(actual, op, expected)

    if source in {"input", "manual"}:
        field = condition.get("field", "")
        op = condition.get("op", "=")
        expected = condition.get("value")
        actual = get_nested_value(context.get(source, {}), field)
        return compare_values(actual, op, expected)

    return False


def set_factor_value(
    expanded_factors: dict[str, Any],
    factor_key: str,
    value: Any,
    write_mode: str,
) -> None:
    if write_mode == "overwrite":
        expanded_factors[factor_key] = value
        return

    if write_mode == "set_if_absent":
        if factor_key not in expanded_factors:
            expanded_factors[factor_key] = value
        return

    if write_mode == "set_if_empty":
        current = expanded_factors.get(factor_key)
        if current in (None, "", [], False):
            expanded_factors[factor_key] = value
        return

    raise ValueError(f"Unsupported write_mode: {write_mode}")


def default_factors_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for factor in schema.get("factors", []):
        if not isinstance(factor, dict):
            continue
        factor_key = factor.get("factor_key")
        if isinstance(factor_key, str):
            defaults[factor_key] = factor.get("default_value")
    return defaults


def apply_manual_overrides(payload: Any, expanded_factors: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return

    for manual_key in ("人工补充", "manual"):
        manual = payload.get(manual_key)
        if not isinstance(manual, dict):
            continue

        overrides = manual.get("factor_overrides")
        if isinstance(overrides, dict):
            for factor_key, value in overrides.items():
                expanded_factors[str(factor_key)] = value


def factor_key_to_id_map(schema: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for factor in schema.get("factors", []):
        factor_key = factor.get("factor_key")
        factor_id = factor.get("factor_id")
        if isinstance(factor_key, str) and isinstance(factor_id, str):
            mapping[factor_key] = factor_id
    return mapping


def factor_id_to_key_map(schema: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for factor in schema.get("factors", []):
        factor_key = factor.get("factor_key")
        factor_id = factor.get("factor_id")
        if isinstance(factor_key, str) and isinstance(factor_id, str):
            mapping[factor_id] = factor_key
    return mapping


def normalize_direct_factors(
    direct_factors: dict[str, Any],
    factor_id_to_key: dict[str, str],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in direct_factors.items():
        normalized[factor_id_to_key.get(key, key)] = value
    return normalized


def factors_from_v1_input(
    payload: Any,
    schema: dict[str, Any],
    expansion_rules: dict[str, Any],
    cad_catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    factor_id_to_key = factor_id_to_key_map(schema)
    direct_factors = direct_factors_from_input(payload) if isinstance(payload, dict) else None
    if direct_factors is not None:
        return normalize_direct_factors(direct_factors, factor_id_to_key)

    normalized_features = normalize_cad_features(payload, cad_catalog)
    context = collect_input_context(payload, normalized_features)
    expanded_factors = default_factors_from_schema(schema)

    rules = sorted(
        [rule for rule in expansion_rules.get("rules", []) if rule.get("enabled", True)],
        key=lambda item: item.get("priority", 0),
        reverse=True,
    )

    for rule in rules:
        conditions = rule.get("when", {}).get("all", [])
        if not all(match_expansion_condition(cond, context, expanded_factors) for cond in conditions):
            continue

        actions = rule.get("then", {}).get("set_factors", [])
        for action in actions:
            factor_key = action.get("factor_key")
            if not isinstance(factor_key, str):
                continue
            set_factor_value(
                expanded_factors,
                factor_key,
                action.get("value"),
                action.get("write_mode", "overwrite"),
            )

    apply_manual_overrides(payload, expanded_factors)
    return expanded_factors


def collect_feature_tokens(simplified: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for value in simplified.values():
        if isinstance(value, list):
            tokens.extend(str(item) for item in value)
        elif isinstance(value, str):
            tokens.append(value)
    return tokens


def has_any(tokens: list[str], *keys: str) -> bool:
    return any(key in tokens for key in keys)


def legacy_factors_from_mps_feature_list(payload: Any) -> dict[str, Any]:
    normalized = normalize_cad_features(payload, None)
    names = [str(item.get("feature_select", "")) for item in normalized]

    def precision_hit(target_names: set[str], threshold: int) -> bool:
        for item in normalized:
            if item.get("feature_select") in target_names:
                rank = item.get("precision_rank")
                if isinstance(rank, (int, float)) and rank <= threshold:
                    return True
        return False

    factors: dict[str, Any] = {"F001": "", "F002": ""}
    factors["F003"] = any(name in {"轴端面", "侧壁", "平面"} for name in names)
    factors["F004"] = any("槽" in name for name in names)
    factors["F005"] = any(name in {"孔", "阶梯孔", "埋头孔"} for name in names)
    factors["F006"] = precision_hit({"孔", "阶梯孔", "埋头孔"}, 9)
    factors["F007"] = False
    factors["F008"] = False
    factors["F009"] = precision_hit({"孔", "阶梯孔", "埋头孔"}, 9)
    factors["F010"] = precision_hit({"孔", "阶梯孔", "埋头孔"}, 7)
    factors["F011"] = precision_hit({"孔", "阶梯孔", "埋头孔"}, 6)
    factors["F012"] = precision_hit({"外圆柱面"}, 8)
    factors["F013"] = precision_hit({"轴端面", "侧壁", "平面"}, 8)
    factors["F014"] = any("槽" in name for name in names) and any(
        isinstance(item.get("precision_rank"), (int, float))
        and item.get("precision_rank") <= 8
        and "槽" in str(item.get("feature_select", ""))
        for item in normalized
    )
    factors["F015"] = precision_hit({"外圆柱面"}, 6)
    factors["F016"] = any(name == "中心孔" for name in names)
    factors["F017"] = False
    factors["F018"] = False
    factors["F019"] = False
    factors["F020"] = False
    factors["F021"] = False
    factors["F022"] = False
    factors["F023"] = False
    factors["F024"] = False
    factors["F025"] = False
    return factors


def factors_from_legacy_simplified_input(payload: dict[str, Any]) -> dict[str, Any]:
    part = payload.get("零件信息", {})
    simplified = payload.get("简化特征", {})

    factors: dict[str, Any] = {}
    material = str(part.get("材料牌号", ""))
    part_type = str(part.get("零件类型", ""))
    factors["F001"] = material
    factors["F002"] = part_type

    tokens = collect_feature_tokens(simplified)

    factors["F003"] = has_any(tokens, "扁位", "平面")
    factors["F004"] = has_any(tokens, "槽类特征", "槽")
    factors["F005"] = has_any(tokens, "普通孔", "辅助孔", "孔")
    factors["F006"] = has_any(tokens, "铰孔", "精孔")
    factors["F007"] = has_any(tokens, "型孔", "割扁")
    factors["F008"] = has_any(tokens, "后段补充孔")
    factors["F009"] = has_any(tokens, "孔精加工")
    factors["F010"] = has_any(tokens, "珩孔要求", "珩孔")
    factors["F011"] = has_any(tokens, "研孔要求", "研孔")
    factors["F012"] = has_any(tokens, "外圆磨削", "磨外圆")
    factors["F013"] = has_any(tokens, "端面磨削", "磨端面")
    factors["F014"] = has_any(tokens, "槽磨削", "磨槽")
    factors["F015"] = has_any(tokens, "研外圆")
    factors["F016"] = has_any(tokens, "顶尖孔定位", "研顶尖孔")

    heat = str(simplified.get("热处理", ""))
    factors["F017"] = heat == "去应力"
    factors["F018"] = heat == "淬火"
    factors["F019"] = heat == "真空淬火"
    factors["F020"] = heat == "渗氮层"

    factors["F021"] = has_any(tokens, "铬酸阳极化")
    factors["F022"] = has_any(tokens, "硬质阳极化")
    factors["F023"] = has_any(tokens, "标印", "标刻")
    factors["F024"] = has_any(tokens, "裂纹检测")
    factors["F025"] = has_any(tokens, "烧伤检查")

    return factors


def legacy_rule_match(rule: dict[str, Any], factors: dict[str, Any]) -> bool:
    for cond in rule.get("when", {}).get("all", []):
        fid = cond["factor_id"]
        expected = cond["value"]
        actual = factors.get(fid)
        if actual != expected:
            return False
    return True


def build_legacy_route(
    factors: dict[str, Any],
    route_catalog: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    included: set[str] = set()

    for rule in rules:
        if legacy_rule_match(rule, factors):
            included.update(rule.get("then", {}).get("include_process_ids", []))

    for process in route_catalog:
        if process.get("type") == "main":
            included.add(process["process_id"])

    ordered = [process for process in route_catalog if process["process_id"] in included]
    ordered.sort(key=lambda item: item["sequence"])

    route: list[dict[str, Any]] = []
    for process in ordered:
        item = {
            "序号": process["sequence"],
            "工序名": process["process_name"],
        }
        steps = process.get("steps") or []
        if steps:
            item["工步"] = steps
        route.append(item)

    return {"工艺路线": collapse_adjacent_auxiliary_bundles(route)}


def route_rule_match(rule: dict[str, Any], factors: dict[str, Any]) -> bool:
    for cond in rule.get("when", {}).get("all", []):
        factor_key = cond["factor_key"]
        op = cond.get("op", "=")
        expected = cond.get("value")
        actual = factors.get(factor_key)
        if not compare_values(actual, op, expected):
            return False
    return True


def collapse_adjacent_auxiliary_bundles(route: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bundle_names = ["去毛刺", "清洗", "检验"]
    collapsed: list[dict[str, Any]] = []
    index = 0

    while index < len(route):
        window = route[index:index + 3]
        window_names = [str(item.get("工序名", "")) for item in window]

        if len(window) == 3 and window_names == bundle_names:
            collapsed.extend(window)
            index += 3

            while index + 2 < len(route):
                next_window = route[index:index + 3]
                next_names = [str(item.get("工序名", "")) for item in next_window]
                if next_names != bundle_names:
                    break
                index += 3
            continue

        collapsed.append(route[index])
        index += 1

    return collapsed


def clone_process(process: dict[str, Any], sequence: int) -> dict[str, Any]:
    cloned = dict(process)
    steps = process.get("steps") or []
    cloned["steps"] = [dict(step) if isinstance(step, dict) else step for step in steps]
    cloned["sequence"] = sequence
    return cloned


def bundle_processes_by_stage(
    ordered: list[dict[str, Any]],
    route_catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    process_lookup: dict[str, dict[str, Any]] = {}
    for process in route_catalog.get("processes", []):
        process_key = process.get("process_key")
        if isinstance(process_key, str):
            process_lookup[process_key] = process

    bundle_rules = route_catalog.get("post_stage_bundles", [])
    if not isinstance(bundle_rules, list) or not bundle_rules:
        return ordered

    result: list[dict[str, Any]] = []
    sequence_cursor = 0

    for index, process in enumerate(ordered):
        process_copy = clone_process(process, sequence_cursor)
        result.append(process_copy)
        sequence_cursor += 5

        current_stage = str(process.get("stage", ""))
        next_stage = ""
        if index + 1 < len(ordered):
            next_stage = str(ordered[index + 1].get("stage", ""))

        for bundle_rule in bundle_rules:
            if not isinstance(bundle_rule, dict):
                continue

            trigger_stages = {
                str(stage)
                for stage in bundle_rule.get("trigger_stages", [])
                if isinstance(stage, str)
            }
            if current_stage not in trigger_stages:
                continue

            final_only = bool(bundle_rule.get("final_only", False))
            if final_only:
                if index + 1 != len(ordered) - 1:
                    continue
            else:
                if next_stage and next_stage == current_stage:
                    continue

            for bundle_process_key in bundle_rule.get("process_keys", []):
                template = process_lookup.get(str(bundle_process_key))
                if not template or not template.get("enabled", True):
                    continue
                result.append(clone_process(template, sequence_cursor))
                sequence_cursor += 5

    return result


def build_v1_route(
    factors: dict[str, Any],
    route_catalog: dict[str, Any],
    route_rules: dict[str, Any],
) -> dict[str, Any]:
    included: set[str] = set()
    excluded: set[str] = set()
    processes = route_catalog.get("processes", [])

    active_rules = sorted(
        [rule for rule in route_rules.get("rules", []) if rule.get("enabled", True)],
        key=lambda item: item.get("priority", 0),
        reverse=True,
    )

    for rule in active_rules:
        if route_rule_match(rule, factors):
            then = rule.get("then", {})
            included.update(then.get("include_process_keys", []))
            excluded.update(then.get("exclude_process_keys", []))

    for process in processes:
        if process.get("default_included"):
            included.add(process["process_key"])

    included.difference_update(excluded)

    ordered = [process for process in processes if process["process_key"] in included and process.get("enabled", True)]
    ordered.sort(key=lambda item: item["sequence"])
    ordered = bundle_processes_by_stage(ordered, route_catalog)

    route: list[dict[str, Any]] = []
    for process in ordered:
        item = {
            "序号": process["sequence"],
            "工序名": process["process_name"],
        }
        steps = process.get("steps") or []
        if steps:
            item["工步"] = [step["step_name"] if isinstance(step, dict) else step for step in steps]
        route.append(item)

    return {"工艺路线": route}


def is_v1_factor_schema(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("factors"), list)


def is_v1_route_catalog(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("processes"), list)


def is_v1_route_rules(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("rules"), list)


def resolve_cad_catalog_path(
    factors_path: Path,
    explicit_cad_catalog: Path | None,
) -> Path | None:
    if explicit_cad_catalog is not None:
        return explicit_cad_catalog

    candidate = factors_path.parent / "cad_reference" / "cad_feature_catalog.json"
    if candidate.exists():
        return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--factors", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expansion-rules", type=Path, default=None)
    parser.add_argument("--cad-catalog", type=Path, default=None)
    args = parser.parse_args()

    payload = load_json(args.input)
    factors_ref = load_json(args.factors)
    route_catalog = load_json(args.catalog)
    route_rules = load_json(args.rules)

    if is_v1_factor_schema(factors_ref) and is_v1_route_catalog(route_catalog) and is_v1_route_rules(route_rules):
        if args.expansion_rules is None:
            raise SystemExit("--expansion-rules is required when using v1 references.")
        expansion_rules = load_json(args.expansion_rules)
        cad_catalog_path = resolve_cad_catalog_path(args.factors, args.cad_catalog)
        cad_catalog = load_json(cad_catalog_path) if cad_catalog_path and cad_catalog_path.exists() else None
        factors = factors_from_v1_input(payload, factors_ref, expansion_rules, cad_catalog)
        output = build_v1_route(factors, route_catalog, route_rules)
    else:
        direct_factors = direct_factors_from_input(payload) if isinstance(payload, dict) else None
        if direct_factors is not None:
            factors = direct_factors
        elif isinstance(payload, list):
            factors = legacy_factors_from_mps_feature_list(payload)
        else:
            factors = factors_from_legacy_simplified_input(payload)
        output = build_legacy_route(factors, route_catalog, route_rules)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
