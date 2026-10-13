#!/usr/bin/env python3
"""Generate matched process route output from CAD input plus route references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import generate_route as route_engine


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_path(path: str, separator: str = "/") -> str:
    normalized = str(path).replace("\\", separator)
    parts = [part.strip() for part in normalized.split(separator) if part.strip()]
    return separator.join(parts)


def flatten_group_nodes(payload: list[dict[str, Any]], group_rules: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    tag_rules = group_rules.get("group_tag_rules", [])
    separator = (
        group_rules.get("context_rules", {})
        .get("region_extract_policy", {})
        .get("path_separator", "/")
    )

    for block in payload:
        if not isinstance(block, dict):
            continue
        raw_path = str(block.get("group_path", ""))
        path = normalize_path(raw_path, separator)
        if not path:
            continue
        features_raw = block.get("features", [])
        if not isinstance(features_raw, list):
            continue

        feature_selects: list[str] = []
        features: list[dict[str, Any]] = []
        for feature in features_raw:
            if not isinstance(feature, dict):
                continue
            feature_select = str(feature.get("feature_select", "")).strip()
            if not feature_select:
                continue
            feature_selects.append(feature_select)
            features.append(
                {
                    "featureSelect": feature_select,
                    "featRank": feature.get("feat_rank"),
                }
            )

        if not feature_selects:
            continue

        tags: list[str] = []
        for rule in tag_rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("path_pattern", ""))
            match_mode = str(rule.get("match_mode", "contains"))
            if not pattern:
                continue
            matched = pattern in path if match_mode == "contains" else path == pattern
            if matched:
                for tag in rule.get("tags", []):
                    if isinstance(tag, str) and tag not in tags:
                        tags.append(tag)

        region = path.split(separator, 1)[0]
        nodes.append(
            {
                "path": path,
                "name": path.split(separator)[-1],
                "region": region,
                "tags": tags,
                "featureSelect": feature_selects,
                "features": features,
            }
        )

    return nodes


def build_feature_lookup(cad_catalog: dict[str, Any]) -> dict[str, str]:
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


def normalize_node_features(nodes: list[dict[str, Any]], cad_catalog: dict[str, Any]) -> None:
    lookup = build_feature_lookup(cad_catalog)
    for node in nodes:
        normalized: list[str] = []
        normalized_feature_rows: list[dict[str, Any]] = []
        original_feature_map: dict[str, list[str]] = {}
        for feature in node.get("features", []):
            name = feature.get("featureSelect")
            canonical = lookup.get(name, name)
            normalized.append(canonical)
            if isinstance(name, str):
                original_feature_map.setdefault(canonical, [])
                if name not in original_feature_map[canonical]:
                    original_feature_map[canonical].append(name)
            normalized_feature_rows.append(
                {
                    "featureSelect": canonical,
                    "featRank": feature.get("featRank"),
                }
            )
        node["featureSelect"] = normalized
        node["features"] = normalized_feature_rows
        node["originalFeatureMap"] = original_feature_map


def step_rule_map(group_rules: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    for rule in group_rules.get("step_rules", []):
        step_name = rule.get("step_name")
        if isinstance(step_name, str):
            mapping.setdefault(step_name, []).append(rule)
    return mapping


def normalize_step_rules(rules_by_name: dict[str, list[dict[str, Any]]], cad_catalog: dict[str, Any]) -> None:
    lookup = build_feature_lookup(cad_catalog)
    for rules in rules_by_name.values():
        for rule in rules:
            normalized: list[str] = []
            for feature in rule.get("candidate_features", []):
                if not isinstance(feature, str):
                    continue
                canonical = lookup.get(feature, feature)
                if canonical not in normalized:
                    normalized.append(canonical)
            if normalized:
                rule["candidate_features"] = normalized


def extract_regions(nodes: list[dict[str, Any]]) -> set[str]:
    return {node.get("region", "") for node in nodes if node.get("region")}


def resolve_context_regions(process_name: str, group_rules: dict[str, Any], available_regions: set[str]) -> set[str]:
    region_rules = group_rules.get("context_rules", {}).get("region_rules", [])
    matched_regions: set[str] = set()
    for rule in region_rules:
        if not isinstance(rule, dict):
            continue
        tokens = [token for token in rule.get("process_tokens", []) if isinstance(token, str)]
        if not any(token in process_name for token in tokens):
            continue
        for region in rule.get("group_regions", []):
            if isinstance(region, str) and region in available_regions:
                matched_regions.add(region)
    return matched_regions


def get_step_rule(process_name: str, step_name: str, rules_by_name: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    rules = rules_by_name.get(step_name) or []
    if not rules:
        return None

    fallback_rule: dict[str, Any] | None = None
    for rule in rules:
        if not rule.get("match_enabled", False):
            continue

        process_tokens = [item for item in rule.get("process_tokens", []) if isinstance(item, str) and item]
        if not process_tokens:
            if fallback_rule is None:
                fallback_rule = rule
            continue

        if any(token in process_name for token in process_tokens):
            return rule

    return fallback_rule


def get_rank_bonus(feat_rank: Any, scoring_rules: dict[str, Any]) -> float:
    try:
        numeric = float(feat_rank)
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 0:
        return 0.0

    for rule in scoring_rules.get("feat_rank_bonus", []):
        try:
            max_rank = float(rule.get("max_rank"))
            bonus = float(rule.get("bonus", 0))
        except (TypeError, ValueError):
            continue
        if numeric <= max_rank:
            return bonus
    return 0.0


def match_fraction(required: list[str], actual: list[str]) -> float:
    if not required or not actual:
        return 0.0
    hits = [item for item in required if item in actual]
    return len(hits) / len(required)


def matched_features(required: list[str], actual: list[str]) -> list[str]:
    return [item for item in required if item in actual]


def get_bias(process_name: str, step_name: str, candidate: dict[str, Any], group_rules: dict[str, Any]) -> float:
    total = 0.0
    region_rules = group_rules.get("context_rules", {}).get("region_rules", [])
    region_key = None
    for rule in region_rules:
        if not isinstance(rule, dict):
            continue
        group_regions = [region for region in rule.get("group_regions", []) if isinstance(region, str)]
        if candidate.get("region") in group_regions:
            region_key = rule.get("context_key")
            break

    for rule in group_rules.get("context_rules", {}).get("bias_rules", []):
        if not isinstance(rule, dict):
            continue

        step_names = [item for item in rule.get("step_names", []) if isinstance(item, str)]
        if step_names and step_name not in step_names:
            continue

        path_fragments = [item for item in rule.get("candidate_path_contains", []) if isinstance(item, str)]
        if path_fragments and not any(fragment in candidate.get("path", "") for fragment in path_fragments):
            continue

        region_keys = [item for item in rule.get("candidate_region_keys", []) if isinstance(item, str)]
        if region_keys and region_key not in region_keys:
            continue

        try:
            total += float(rule.get("bonus", 0))
        except (TypeError, ValueError):
            continue

    return total


def infer_precision_label(rank: float | None, precision_rules: dict[str, Any]) -> str:
    if rank is None:
        return str(precision_rules.get("missing_rank_policy", "一般加工"))

    for band in precision_rules.get("rank_bands", []):
        try:
            max_rank = float(band.get("max_rank"))
        except (TypeError, ValueError):
            continue
        if rank <= max_rank:
            return str(band.get("precision_label", "一般加工"))
    return str(precision_rules.get("missing_rank_policy", "一般加工"))


def numeric_rank(value: Any, precision_rules: dict[str, Any]) -> float | None:
    special_values = {str(item) for item in precision_rules.get("special_ultra_precision_values", [])}
    if value is None:
        return None
    if str(value) in special_values:
        return 0.001
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_candidate_map(candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for candidate in candidates:
        features = candidate.get("matched_features") or candidate.get("featureSelect") or []
        original_feature_map = candidate.get("originalFeatureMap") or {}
        display_features: list[str] = []
        for feature in features:
            originals = original_feature_map.get(feature)
            if isinstance(originals, list) and originals:
                for original in originals:
                    if isinstance(original, str) and original not in display_features:
                        display_features.append(original)
            elif isinstance(feature, str) and feature not in display_features:
                display_features.append(feature)
        mapping[candidate["path"]] = display_features
    return mapping


def build_candidate_details(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for candidate in candidates:
        features = candidate.get("matched_features") or candidate.get("featureSelect") or []
        original_feature_map = candidate.get("originalFeatureMap") or {}
        display_features: list[str] = []
        for feature in features:
            originals = original_feature_map.get(feature)
            if isinstance(originals, list) and originals:
                for original in originals:
                    if isinstance(original, str) and original not in display_features:
                        display_features.append(original)
            elif isinstance(feature, str) and feature not in display_features:
                display_features.append(feature)

        details.append(
            {
                "group_path": candidate.get("path", ""),
                "group_name": candidate.get("name", ""),
                "features": display_features,
            }
        )
    return details


def score_candidates(
    process_name: str,
    step_name: str,
    nodes: list[dict[str, Any]],
    group_rules: dict[str, Any],
    rules_by_name: dict[str, list[dict[str, Any]]],
 ) -> tuple[dict[str, list[str]], list[dict[str, Any]], float | None]:
    step_rule = get_step_rule(process_name, step_name, rules_by_name)
    if step_rule is None:
        return {}, [], None

    required_tags = [item for item in step_rule.get("step_tags", []) if isinstance(item, str)]
    required_features = [item for item in step_rule.get("candidate_features", []) if isinstance(item, str)]
    required_path_fragments = [item for item in step_rule.get("candidate_path_contains", []) if isinstance(item, str)]
    scoring_rules = group_rules.get("scoring_rules", {})

    available_regions = extract_regions(nodes)
    matched_regions = resolve_context_regions(process_name, group_rules, available_regions)

    candidate_pool = nodes
    if matched_regions and group_rules.get("context_rules", {}).get("region_match_policy", {}).get("prefer_region_candidates_first", False):
        narrowed = [node for node in nodes if node.get("region") in matched_regions]
        if narrowed:
            candidate_pool = narrowed
        elif not group_rules.get("context_rules", {}).get("region_match_policy", {}).get("fallback_to_global_if_region_empty", True):
            candidate_pool = []

    scored: list[dict[str, Any]] = []
    for node in candidate_pool:
        if required_path_fragments and not any(fragment in node.get("path", "") for fragment in required_path_fragments):
            continue
        tag_score = match_fraction(required_tags, node.get("tags", []))
        feature_score = match_fraction(required_features, node.get("featureSelect", []))
        base = round(tag_score * float(scoring_rules.get("tag_weight", 0.4)) + feature_score * float(scoring_rules.get("feature_weight", 0.6)), 4)
        matched = matched_features(required_features, node.get("featureSelect", []))
        if base <= 0 and not matched:
            continue

        matched_ranks = [
            numeric_rank(feature.get("featRank"), group_rules.get("precision_rules", {}))
            for feature in node.get("features", [])
            if feature.get("featureSelect") in matched
        ]
        matched_ranks = [rank for rank in matched_ranks if rank is not None]
        best_rank = min(matched_ranks) if matched_ranks else None
        bonus = get_rank_bonus(best_rank, scoring_rules) if best_rank is not None else 0.0
        process_bias = get_bias(process_name, step_name, node, group_rules)
        total = round(base + bonus + process_bias, 4)
        if total <= 0:
            continue

        scored.append(
            {
                **node,
                "score": total,
                "matched_features": matched,
                "best_rank": best_rank,
            }
        )

    if not scored:
        return {}, [], None

    scored.sort(key=lambda item: (-item["score"], item["path"]))
    candidate_map = build_candidate_map(scored)
    candidate_details = build_candidate_details(scored)

    best_rank = None
    ranks = [item.get("best_rank") for item in scored if item.get("best_rank") is not None]
    if ranks:
        best_rank = min(ranks)
    return candidate_map, candidate_details, best_rank


def mark_last_occurrence_candidates(route_rows: list[dict[str, Any]]) -> None:
    last_occurrence: dict[tuple[str, str], tuple[int, int]] = {}

    for process_index, process in enumerate(route_rows):
        steps = process.get("工步", [])
        if not isinstance(steps, list):
            continue
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            candidate_details = step.get("候选明细", [])
            if not isinstance(candidate_details, list):
                continue
            for detail in candidate_details:
                if not isinstance(detail, dict):
                    continue
                group_path = str(detail.get("group_path", "")).strip()
                features = detail.get("features", [])
                if not group_path or not isinstance(features, list):
                    continue
                for feature_name in features:
                    if not isinstance(feature_name, str) or not feature_name.strip():
                        continue
                    last_occurrence[(group_path, feature_name)] = (process_index, step_index)

    for process_index, process in enumerate(route_rows):
        steps = process.get("工步", [])
        if not isinstance(steps, list):
            continue
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            candidate_details = step.get("候选明细", [])
            if not isinstance(candidate_details, list):
                continue
            for detail in candidate_details:
                if not isinstance(detail, dict):
                    continue
                group_path = str(detail.get("group_path", "")).strip()
                features = detail.get("features", [])
                if not group_path or not isinstance(features, list):
                    detail["is_last_process_for_group"] = False
                    detail["last_features"] = []
                    detail["feature_flags"] = []
                    continue

                last_features: list[str] = []
                feature_flags: list[dict[str, Any]] = []
                for feature_name in features:
                    is_last = last_occurrence.get((group_path, feature_name)) == (process_index, step_index)
                    if is_last and feature_name not in last_features:
                        last_features.append(feature_name)
                    feature_flags.append(
                        {
                            "feature_name": feature_name,
                            "is_last_process_for_feature": is_last,
                        }
                    )

                detail["is_last_process_for_group"] = bool(last_features) and len(last_features) == len(features)
                detail["last_features"] = last_features
                detail["feature_flags"] = feature_flags


def build_route_stage_lookup(route_catalog: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for process in route_catalog.get("processes", []):
        if not isinstance(process, dict):
            continue
        process_name = process.get("process_name")
        stage = process.get("stage")
        if isinstance(process_name, str) and isinstance(stage, str) and process_name:
            lookup[process_name] = stage
    return lookup


def precision_from_route_stage(stage: str | None) -> str:
    if stage == "finish":
        return "精加工"
    if stage == "semi_finish":
        return "半精加工"
    if stage == "rough_machining":
        return "粗加工"
    return "辅助工序"


def build_matched_route_output(
    standard_route: dict[str, Any],
    cad_input: list[dict[str, Any]],
    group_rules: dict[str, Any],
    cad_catalog: dict[str, Any],
    route_catalog: dict[str, Any],
) -> dict[str, Any]:
    nodes = flatten_group_nodes(cad_input, group_rules)
    normalize_node_features(nodes, cad_catalog)
    rules_by_name = step_rule_map(group_rules)
    normalize_step_rules(rules_by_name, cad_catalog)
    route_stage_lookup = build_route_stage_lookup(route_catalog)

    route_rows: list[dict[str, Any]] = []
    for process in standard_route.get("工艺路线", []):
        process_name = str(process.get("工序名", ""))
        sequence = process.get("序号")
        steps = process.get("工步", [])
        if not isinstance(steps, list):
            steps = []

        step_rows: list[dict[str, Any]] = []
        for step_name in steps:
            candidate_map, candidate_details, best_rank = score_candidates(process_name, str(step_name), nodes, group_rules, rules_by_name)
            if candidate_map:
                step_rows.append(
                    {
                        "工步名": step_name,
                        "候选分组": candidate_map,
                        "候选明细": candidate_details,
                    }
                )

        stage = route_stage_lookup.get(process_name)
        precision = precision_from_route_stage(stage)
        if precision == "辅助工序":
            process_type = "辅助工序"
        else:
            process_type = "加工工序"

        route_rows.append(
            {
                "序号": sequence,
                "工序名": process_name,
                "工序类型": process_type,
                "加工精度": precision,
                "技术要求": [],
                "工步": step_rows,
            }
        )

    mark_last_occurrence_candidates(route_rows)

    return {
        "schema_version": "matched-process-route-v1",
        "工艺路线": route_rows,
    }


def export_route_rows(matched_route: dict[str, Any]) -> list[dict[str, Any]]:
    def export_precision(value: Any) -> str:
        raw = str(value or "")
        if raw == "精加工":
            return "精加工"
        if raw == "半精加工":
            return "半精加工"
        if raw in {"一般加工", "粗加工"}:
            return "粗加工"
        return ""

    def export_process_type(process: dict[str, Any]) -> str:
        raw_type = str(process.get("工序类型", ""))
        if raw_type == "辅助工序":
            return "辅助工序"
        precision = export_precision(process.get("加工精度"))
        return precision or "粗加工"

    export_rows: list[dict[str, Any]] = []
    for process in matched_route.get("工艺路线", []):
        steps_raw = process.get("工步", [])
        if not isinstance(steps_raw, list):
            steps_raw = []

        steps: list[dict[str, Any]] = []
        for step in steps_raw:
            if not isinstance(step, dict):
                continue
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
            steps.append(
                {
                    "step_name": str(step.get("工步名", "")),
                    "candidates": candidates,
                    "candidate_details": candidate_details,
                    "is_last": is_last,
                }
            )

        technical_requirements = process.get("技术要求", [])
        if not isinstance(technical_requirements, list):
            technical_requirements = []

        process_type = export_process_type(process)
        precision = export_precision(process.get("加工精度"))
        if not precision and process_type == "辅助工序":
            precision = "辅助工序"

        export_rows.append(
            {
                "process_name": str(process.get("工序名", "")),
                "process_type": process_type,
                "precision": precision,
                "technical_requirements": technical_requirements,
                "steps": steps,
            }
        )

    return export_rows


def export_route_rows_simple(matched_route: dict[str, Any]) -> list[dict[str, Any]]:
    export_rows = export_route_rows(matched_route)
    simple_rows: list[dict[str, Any]] = []

    for process in export_rows:
        if not isinstance(process, dict):
            continue

        steps_raw = process.get("steps", [])
        if not isinstance(steps_raw, list):
            steps_raw = []

        simple_steps: list[dict[str, Any]] = []
        for step in steps_raw:
            if not isinstance(step, dict):
                continue

            candidates = step.get("candidates", {})
            if not isinstance(candidates, dict):
                candidates = {}

            candidate_details = step.get("candidate_details", [])
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

            simple_steps.append(
                {
                    "step_name": str(step.get("step_name", "")),
                    "candidates": candidates,
                    "is_last": is_last,
                }
            )

        technical_requirements = process.get("technical_requirements", [])
        if not isinstance(technical_requirements, list):
            technical_requirements = []

        simple_rows.append(
            {
                "process_name": str(process.get("process_name", "")),
                "process_type": str(process.get("process_type", "")),
                "precision": str(process.get("precision", "")),
                "technical_requirements": technical_requirements,
                "steps": simple_steps,
            }
        )

    return simple_rows


def default_runtime_payload(cad_input: list[dict[str, Any]], manual: dict[str, Any]) -> dict[str, Any]:
    advanced = manual.get("advanced_overrides", {}) if isinstance(manual, dict) else {}
    return {
        "cad_features": cad_input,
        "manual": {
            "heat_treatment": advanced.get("heat_treatment"),
            "surface_treatments": manual.get("surface_treatments", []),
            "inspection_items": manual.get("inspection_items", []),
            "marking_methods": manual.get("marking_methods", []),
            "special_process_flags": manual.get("special_process_flags", {}),
            "factor_overrides": advanced.get("factor_overrides", {}),
        },
        "part_info": {
            "material_grade": manual.get("material_grade"),
            "part_type": manual.get("part_type"),
        },
    }


def generate_standard_route(
    cad_input: list[dict[str, Any]],
    manual: dict[str, Any],
    factor_schema: dict[str, Any],
    expansion_rules: dict[str, Any],
    route_catalog: dict[str, Any],
    route_rules: dict[str, Any],
    cad_catalog: dict[str, Any],
) -> dict[str, Any]:
    runtime_payload = default_runtime_payload(cad_input, manual)
    factors = route_engine.factors_from_v1_input(runtime_payload, factor_schema, expansion_rules, cad_catalog)
    return route_engine.build_v1_route(factors, route_catalog, route_rules)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cad-input", required=True, type=Path)
    parser.add_argument("--manual-options", type=Path, default=None)
    parser.add_argument("--factor-schema", required=True, type=Path)
    parser.add_argument("--expansion-rules", required=True, type=Path)
    parser.add_argument("--route-catalog", required=True, type=Path)
    parser.add_argument("--route-rules", required=True, type=Path)
    parser.add_argument("--cad-catalog", required=True, type=Path)
    parser.add_argument("--group-match-rules", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--standard-route-out", type=Path, default=None)
    args = parser.parse_args()

    cad_input = load_json(args.cad_input)
    if not isinstance(cad_input, list):
        raise SystemExit("cad_input must be a list of group blocks.")

    manual = load_json(args.manual_options) if args.manual_options and args.manual_options.exists() else {}
    factor_schema = load_json(args.factor_schema)
    expansion_rules = load_json(args.expansion_rules)
    route_catalog = load_json(args.route_catalog)
    route_rules = load_json(args.route_rules)
    cad_catalog = load_json(args.cad_catalog)
    group_rules = load_json(args.group_match_rules)

    standard_route = generate_standard_route(
        cad_input,
        manual if isinstance(manual, dict) else {},
        factor_schema,
        expansion_rules,
        route_catalog,
        route_rules,
        cad_catalog,
    )
    matched_route = build_matched_route_output(standard_route, cad_input, group_rules, cad_catalog, route_catalog)
    export_route = export_route_rows(matched_route)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(export_route, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.standard_route_out is not None:
        args.standard_route_out.parent.mkdir(parents=True, exist_ok=True)
        args.standard_route_out.write_text(json.dumps(standard_route, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
