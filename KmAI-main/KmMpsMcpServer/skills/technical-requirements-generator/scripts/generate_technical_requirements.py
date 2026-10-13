import argparse
import json
from difflib import SequenceMatcher
from copy import deepcopy
from pathlib import Path

FEATURE_ALIAS_MAP = {
    "回转面倒圆": ("outer_round", True),
    "外倒圆": ("outer_round", True),
    "外倒角": ("outer_chamfer", True),
    "内倒角": ("inner_chamfer", True),
    "内倒圆": ("inner_round", True),
    "外圆柱面": ("outer_cylinder", True),
    "轴端面": ("end_face", True),
    "端面": ("end_face", True),
    "U形外环槽": ("outer_groove", True),
    "外环槽": ("outer_groove", True),
    "单纯底凹槽": ("outer_groove", True),
    "孔": ("inner_hole", True),
    "内圆": ("inner_hole", True),
    "内螺纹": ("inner_thread", True),
    "外螺纹": ("outer_thread", True),
    "侧壁": ("plane", True),
    "平键": ("outer_keyway", True),
    "花键": ("outer_spline", True),
    "四方": ("outer_square", True),
    "六方": ("outer_hex", True),
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_process_alias_config():
    default_path = Path(__file__).resolve().parent.parent / "references" / "process_name_aliases.json"
    if not default_path.exists():
        default_path = Path(__file__).resolve().parent.parent.parent / "references" / "process_name_aliases.json"
    if not default_path.exists():
        return {"similarity_threshold": 0.78, "aliases": {}}
    try:
        data = load_json(default_path)
    except Exception:
        return {"similarity_threshold": 0.78, "aliases": {}}
    if not isinstance(data, dict):
        return {"similarity_threshold": 0.78, "aliases": {}}
    return {
        "similarity_threshold": float(data.get("similarity_threshold", 0.78)),
        "aliases": data.get("aliases", {}) if isinstance(data.get("aliases", {}), dict) else {},
    }


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


PROCESS_ALIAS_CONFIG = load_process_alias_config()


def normalize_process_name(name):
    if not name:
        return ""
    raw = str(name).strip()
    return PROCESS_ALIAS_CONFIG.get("aliases", {}).get(raw, raw)


def process_name_similarity(left, right):
    left_norm = normalize_process_name(left)
    right_norm = normalize_process_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.96
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def process_name_matches(current_name, candidate_names):
    normalized_current = normalize_process_name(current_name)
    if not normalized_current:
        return False

    for candidate in candidate_names:
        normalized_candidate = normalize_process_name(candidate)
        if not normalized_candidate:
            continue
        if normalized_current == normalized_candidate:
            return True
        if normalized_current in normalized_candidate or normalized_candidate in normalized_current:
            return True

        score = process_name_similarity(normalized_current, normalized_candidate)
        if score >= PROCESS_ALIAS_CONFIG.get("similarity_threshold", 0.78):
            return True

    return False


def infer_material_category(material_grade):
    if not material_grade:
        return None
    stainless = {"9Cr18"}
    carbon_like = {"4Cr14Ni14W2Mo"}
    if material_grade in stainless:
        return "stainless_steel"
    if material_grade in carbon_like:
        return "carbon_steel"
    return None


def infer_part_class(raw_value):
    if not raw_value:
        return None
    mapping = {
        "衬套": "bushing",
        "衬套类": "bushing",
        "活门": "valve",
        "活门类": "valve",
    }
    return mapping.get(raw_value, raw_value)


def build_empty_part_context():
    return {
        "material": {
            "category": None,
            "grade": None,
            "heat_treatment_family": None,
            "surface_treatment_family": None,
        },
        "part": {
            "part_class": None,
        },
        "features": {
            "center_hole": {
                "exists": None,
                "accuracy_grade": None,
            },
            "side_a": {},
            "side_b": {},
            "peripheral": {},
        },
        "process_flags": {
            "has_marking": None,
            "need_crack_check": None,
            "need_burn_check": None,
        },
    }


def ensure_feature_slot(container, key, include_grade=False):
    if key not in container:
        container[key] = {"exists": None}
        if include_grade:
            container[key]["accuracy_grade"] = None


def apply_cad_input(part_context, cad_input):
    if not cad_input:
        return

    for item in cad_input:
        group_path = item.get("group_path", "").strip("/")
        features = item.get("features", [])

        if group_path == "中间通孔":
            part_context["features"]["center_hole"]["exists"] = True
            ranks = [f.get("feat_rank") for f in features if isinstance(f.get("feat_rank"), int)]
            if ranks:
                part_context["features"]["center_hole"]["accuracy_grade"] = min(ranks)
            continue

        if group_path.startswith("A侧/"):
            target = part_context["features"]["side_a"]
            side_prefix = "A"
        elif group_path.startswith("B侧/"):
            target = part_context["features"]["side_b"]
            side_prefix = "B"
        elif group_path.startswith("周边/"):
            target = part_context["features"]["peripheral"]
            side_prefix = "P"
        else:
            continue

        group_leaf = group_path.split("/")[-1]
        if side_prefix in {"A", "B"}:
            group_mapping = {
                "端面": ("end_face", True),
                "外圆": ("outer_cylinder", True),
                "外环槽": ("outer_groove", True),
                "孔": ("inner_hole", True),
            }
            slot = group_mapping.get(group_leaf)
            if slot:
                key, include_grade = slot
                ensure_feature_slot(target, key, include_grade=include_grade)
                target[key]["exists"] = True
                ranks = [f.get("feat_rank") for f in features if isinstance(f.get("feat_rank"), int)]
                if include_grade and ranks:
                    target[key]["accuracy_grade"] = min(ranks)
        else:
            peripheral_mapping = {
                "孔": "radial_hole",
            }
            if group_leaf == "平面和凹槽":
                for feat in features:
                    feature_select = feat.get("feature_select")
                    if feature_select == "侧壁":
                        target["plane"] = True
                    elif feature_select == "单纯底凹槽":
                        target["outer_groove"] = True
                continue
            peripheral_key = peripheral_mapping.get(group_leaf)
            if peripheral_key:
                target[peripheral_key] = True

        for feat in features:
            feature_select = feat.get("feature_select")
            if feature_select not in FEATURE_ALIAS_MAP:
                continue
            key, include_grade = FEATURE_ALIAS_MAP[feature_select]
            if side_prefix == "P":
                target[key] = True
                continue
            ensure_feature_slot(target, key, include_grade=include_grade and key in {"end_face", "outer_cylinder", "outer_groove", "inner_hole"})
            target[key]["exists"] = True
            if "accuracy_grade" in target[key] and isinstance(feat.get("feat_rank"), int):
                current = target[key].get("accuracy_grade")
                rank = feat["feat_rank"]
                target[key]["accuracy_grade"] = rank if current is None else min(current, rank)


def apply_manual_context(part_context, manual_context):
    if not manual_context:
        return

    material_grade = manual_context.get("material_grade")
    if material_grade:
        part_context["material"]["grade"] = material_grade
        inferred_category = infer_material_category(material_grade)
        if inferred_category:
            part_context["material"]["category"] = inferred_category

    part_class = manual_context.get("part_class")
    normalized_part_class = infer_part_class(part_class)
    if normalized_part_class:
        part_context["part"]["part_class"] = normalized_part_class

    heat_treatment = manual_context.get("heat_treatment")
    if heat_treatment:
        part_context["material"]["heat_treatment_family"] = heat_treatment

    surface_treatment = manual_context.get("surface_treatment")
    if surface_treatment:
        part_context["material"]["surface_treatment_family"] = surface_treatment

    marking = manual_context.get("has_marking")
    if marking is not None:
        part_context["process_flags"]["has_marking"] = bool(marking)

    crack = manual_context.get("need_crack_check")
    if crack is not None:
        part_context["process_flags"]["need_crack_check"] = bool(crack)

    burn = manual_context.get("need_burn_check")
    if burn is not None:
        part_context["process_flags"]["need_burn_check"] = bool(burn)


def deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_part_context(cad_input=None, manual_context=None, upstream_part_context=None):
    part_context = build_empty_part_context()
    apply_cad_input(part_context, cad_input or [])
    apply_manual_context(part_context, manual_context or {})
    if upstream_part_context:
        part_context = deep_merge(part_context, upstream_part_context)
    return part_context


def get_path_value(data, path):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def is_unknown(value):
    return value is None or value == ""


def previous_process_exists(route_obj, current_key, process_name):
    normalized_target = normalize_process_name(process_name)
    for key in sorted(route_obj.keys()):
        if key == current_key:
            return False
        process = route_obj[key]
        if not isinstance(process, dict):
            continue
        current_name = normalize_process_name(
            process.get("工序名称") or process.get("工序名") or process.get("process_name")
        )
        if current_name == normalized_target:
            return True
    return False


def any_of_match(part_context, paths):
    values = [get_path_value(part_context, path) for path in paths]
    return any(value is True for value in values)


def none_of_match(part_context, paths):
    values = [get_path_value(part_context, path) for path in paths]
    if any(value is None for value in values):
        return False
    return all(value is False for value in values)


def rule_matches(rule, part_context, route_obj, current_key):
    when = rule.get("when", {})

    for field in rule.get("required_context", []):
        if rule.get("skip_if_unknown") and is_unknown(get_path_value(part_context, field)):
            return False

    for key, value in when.items():
        if key == "any_of":
            if not any_of_match(part_context, value):
                return False
            continue
        if key == "none_of":
            if not none_of_match(part_context, value):
                return False
            continue
        if key == "previous_process_exists":
            if not previous_process_exists(route_obj, current_key, value):
                return False
            continue
        if key.endswith("_in"):
            path = key[:-3]
            current = get_path_value(part_context, path)
            if current not in value:
                return False
            continue
        current = get_path_value(part_context, key)
        if current != value:
            return False

    return True


def render_template(template_text, variables):
    text = template_text
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", "" if value is None else str(value))
    return text


def apply_rules(route_input, part_context, rules_obj, templates_obj):
    original_input = deepcopy(route_input)

    if isinstance(original_input, dict) and isinstance(original_input.get("工艺路线"), list):
        route_rows = original_input.get("工艺路线", [])
        route_obj = {
            f"{index:03d}": item
            for index, item in enumerate(route_rows)
            if isinstance(item, dict)
        }
        wrap_mode = "route_dict"
    elif isinstance(original_input, list):
        route_obj = {
            f"{index:03d}": {
                "工序名称": item.get("工序名称") or item.get("工序名") or item.get("process_name"),
                "工序类型": item.get("工序类型") or item.get("工序类型"),
                "加工精度": item.get("加工精度") or item.get("precision"),
                "技术要求": list(item.get("技术要求") or item.get("technical_requirements") or []),
                "工步": item.get("工步") or item.get("steps") or [],
                "candidate_details": item.get("candidate_details") if isinstance(item.get("candidate_details"), list) else [],
            }
            for index, item in enumerate(original_input)
            if isinstance(item, dict)
        }
        wrap_mode = "route_list"
    elif isinstance(original_input, dict):
        route_obj = deepcopy(original_input)
        wrap_mode = "flat_dict"
    else:
        route_obj = {}
        wrap_mode = "unknown"

    template_map = templates_obj.get("templates", {})
    rules = rules_obj.get("rules", [])

    for key in sorted(route_obj.keys()):
        process = route_obj[key]
        if not isinstance(process, dict):
            continue
        process_name = process.get("工序名称") or process.get("工序名") or process.get("process_name")
        if not process_name:
            continue
        normalized_process_name = normalize_process_name(process_name)

        collected = []
        seen = set()
        variables = {
            "material_standard": part_context.get("material", {}).get("standard"),
            "feature_name": None,
        }

        for rule in rules:
            if not process_name_matches(normalized_process_name, rule.get("process_names", [])):
                continue
            if not rule_matches(rule, part_context, route_obj, key):
                continue

            template_ids = []
            if "append_template" in rule:
                template_ids.append(rule["append_template"])
            template_ids.extend(rule.get("append_templates", []))

            for template_id in template_ids:
                template = template_map.get(template_id)
                if not template:
                    continue
                text = render_template(template.get("text", ""), variables).strip()
                if not text:
                    continue
                if text not in seen:
                    seen.add(text)
                    collected.append(text)

        if collected:
            process["技术要求"] = collected
        elif "技术要求" not in process:
            process["技术要求"] = []

    if wrap_mode == "route_dict":
        output = deepcopy(original_input)
        output["工艺路线"] = [route_obj[key] for key in sorted(route_obj.keys())]
        return output
    if wrap_mode == "route_list":
        return [route_obj[key] for key in sorted(route_obj.keys())]
    return route_obj


def parse_args():
    parser = argparse.ArgumentParser(description="Generate technical requirements for a route.")
    parser.add_argument("--cad-input", dest="cad_input", help="Path to cad_input.json", default=None)
    parser.add_argument("--manual-context", dest="manual_context", help="Path to manual_context.json", default=None)
    parser.add_argument("--upstream-part-context", dest="upstream_part_context", help="Path to upstream part_context json", default=None)
    parser.add_argument("--route-input", dest="route_input", help="Path to route input json", required=True)
    default_rules = Path(__file__).resolve().parent / "references" / "technical_requirement_rules.json"
    default_templates = Path(__file__).resolve().parent / "references" / "technical_requirement_templates.json"
    if not default_rules.exists():
        default_rules = Path(__file__).resolve().parent.parent / "references" / "technical_requirement_rules.json"
    if not default_templates.exists():
        default_templates = Path(__file__).resolve().parent.parent / "references" / "technical_requirement_templates.json"
    parser.add_argument("--rules", dest="rules", help="Path to rules json", default=str(default_rules))
    parser.add_argument("--templates", dest="templates", help="Path to templates json", default=str(default_templates))
    parser.add_argument("--part-context-out", dest="part_context_out", help="Optional output path for generated part_context", default=None)
    parser.add_argument("--output", dest="output", help="Output path", required=True)
    return parser.parse_args()


def main():
    args = parse_args()

    cad_input = load_json(args.cad_input) if args.cad_input else []
    manual_context = load_json(args.manual_context) if args.manual_context else {}
    upstream_part_context = load_json(args.upstream_part_context) if args.upstream_part_context else None
    route_input = load_json(args.route_input)
    rules_obj = load_json(args.rules)
    templates_obj = load_json(args.templates)

    part_context = build_part_context(
        cad_input=cad_input,
        manual_context=manual_context,
        upstream_part_context=upstream_part_context,
    )

    if args.part_context_out:
        save_json(args.part_context_out, part_context)

    output = apply_rules(route_input, part_context, rules_obj, templates_obj)
    save_json(args.output, output)


if __name__ == "__main__":
    main()
