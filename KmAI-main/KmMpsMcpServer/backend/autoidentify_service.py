# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import re
import sys
import time
from collections import OrderedDict

from . import agent_config as _config
from .agent_config import DIALOG_POLL_INTERVAL_SEC, DIALOG_POLL_MAX_ATTEMPTS
from .pipe_client import (
    is_function_not_found_error,
    is_timeout_error,
    make_timeout_error_payload,
    make_unsupported_tool_payload,
)
from .tool_runtime import get_timeout

try:
    string_types = (basestring,)  # type: ignore[name-defined]
except NameError:
    string_types = (str,)


AUTOIDENTIFY_FEATURE_NAMES = [
    u"\u5c0f\u5b54", u"\u5927\u5b54", u"\u540c\u76f4\u5f84\u6df1\u5ea6\u5206\u5e03\u5b54\u7cfb", u"\u540c\u8f74\u5b54\u7cfb", u"\u4e3b\u8f74\u4e0a\u540c\u8f74\u5b54\u7cfb", u"\u975e\u4e3b\u8f74\u4e0a\u540c\u8f74\u5b54\u7cfb",
    u"\u5916\u5706\u67f1\u9762", u"\u5185\u73af\u69fd", u"\u5916\u73af\u69fd", u"\u5185\u5706\u9525\u9762", u"\u5916\u5706\u9525\u9762", u"\u56de\u8f6c\u9762\u5012\u89d2", u"\u56de\u8f6c\u9762\u5012\u5706",
    u"\u516d\u9762", u"\u5e73\u9762\u7c7b", u"\u77e9\u5f62\u69fd", u"U\u5f62\u76f4\u69fd", u"\u5355\u7eaf\u5e95\u51f9\u69fd", u"\u5e73\u5e95\u6c9f\u69fd", u"\u53f0\u9636", u"\u4fa7\u58c1",
    u"\u77e9\u5f62\u622a\u9762\u7279\u6b8a\u52a0\u5de5\u69fd", u"\u5e73\u9762\u7684\u5916\u5468\u8fb9\u4fa7\u58c1", u"\u5e73\u9762\u7684\u5185\u7a97\u53e3\u901a\u69fd", u"\u56de\u8f6c\u9762\u4e0b\u9677\u901a\u69fd",
    u"\u56de\u8f6c\u4f53\u5f84\u5411\u5bf9\u79f0\u901a\u69fd", u"\u6cd5\u5170\u5706\u5468\u7f3a\u53e3", u"\u4e00\u822c\u5916\u5012\u5706", u"\u5e73\u9762\u4e0a\u8fb9\u5012\u89d2", u"\u503e\u659c\u9762\u6216\u66f2\u9762",
    u"\u666e\u901a\u5747\u5e03\u9f7f\u69fd", u"\u659c\u5411\u76f4\u9f7f\u5747\u5e03\u9f7f\u69fd", u"\u56de\u8f6c\u9762\u7cfb", u"\u4e3b\u56de\u8f6c\u9762\u7cfb", u"\u56de\u8f6c\u9762\u7cfb\u7aef\u9762\u4e0a\u73af\u72b6\u7f3a\u53e3",
    u"\u56de\u8f6c\u9762\u7cfb\u7aef\u9762\u4e0a\u6279\u91cf\u5c0f\u901a\u69fd", u"\u56de\u8f6c\u9762\u7cfb\u7aef\u9762\u4e0a\u6279\u91cf\u5c0f\u5e73\u5e95\u69fd", u"\u56de\u8f6c\u9762\u7cfb\u7aef\u9762\u4e0a\u6279\u91cf\u5c0f\u53f0\u9636\u5468\u8fb9",
]


class AutoIdentifyServiceMixin(object):
    @staticmethod
    def _normalize_autoidentify_template_name(template_name):
        value = (template_name or "").strip().strip('"')
        if not value:
            return ""
        value = os.path.basename(value.replace("/", os.sep))
        if value.lower().endswith(".ini"):
            value = value[:-4]
        return value.strip()

    @classmethod
    def _extract_autoidentify_template_names(cls, list_result):
        names = cls._extract_group_template_names(list_result)
        normalized_names = []
        seen = set()
        for name in names:
            normalized = cls._normalize_autoidentify_template_name(name)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_names.append(normalized)
        return normalized_names

    @classmethod
    def _find_autoidentify_template_name(cls, template_name, template_names):
        normalized = cls._normalize_autoidentify_template_name(template_name)
        if not normalized or not template_names:
            return ""
        lower_normalized = normalized.lower()
        for name in template_names:
            candidate = cls._normalize_autoidentify_template_name(name)
            if candidate == normalized or candidate.lower() == lower_normalized:
                return candidate
        return ""

    @classmethod
    def _choose_autoidentify_template_name(cls, params, template_names):
        if not template_names:
            return ""

        requested_index = cls._coerce_positive_int(
            params.get("template_index", params.get("templateIndex", params.get("index", 0)))
        )
        if requested_index and requested_index <= len(template_names):
            return cls._normalize_autoidentify_template_name(template_names[requested_index - 1])

        requested_name = ""
        for key in ("template_name", "templateName", "filename"):
            requested_name = cls._normalize_autoidentify_template_name(params.get(key, ""))
            if requested_name:
                break
        if requested_name:
            return cls._find_autoidentify_template_name(requested_name, template_names)

        preferred_keywords = []
        for key in ("preferred_keyword", "preferredKeyword"):
            value = (params.get(key, "") or "").strip()
            if value:
                preferred_keywords.append(value)
        preferred_keywords.append(u"套筒类")
        for keyword in preferred_keywords:
            for name in template_names:
                normalized = cls._normalize_autoidentify_template_name(name)
                if keyword in normalized:
                    return normalized

        if len(template_names) >= 2:
            return cls._normalize_autoidentify_template_name(template_names[1])
        return cls._normalize_autoidentify_template_name(template_names[0])

    @staticmethod
    def _build_autoidentify_checked_list(features):
        selected = set(features or [])
        values = []
        for feature in AUTOIDENTIFY_FEATURE_NAMES:
            values.append(u"[%s,%s]" % (feature, 1 if feature in selected else 0))
        return "".join(values)

    @staticmethod
    def _build_autoidentify_checked_list_from_states(feature_states):
        values = []
        for feature_state in feature_states or []:
            feature_name = (feature_state.get("name", "") or "").strip()
            if not feature_name:
                continue
            values.append(u"[%s,%s]" % (feature_name, 1 if feature_state.get("checked") else 0))
        return "".join(values)

    @staticmethod
    def _read_text_file_with_fallback(file_path):
        with open(file_path, "rb") as file_obj:
            content = file_obj.read()
        last_error = None
        for encoding_name in ("utf-8-sig", "utf-8", "gbk", "mbcs"):
            try:
                return content.decode(encoding_name)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            try:
                sys.stderr.write("[autoidentify] decode fallback for %s: %s\n" % (file_path, last_error))
            except Exception:
                pass
        return content.decode("utf-8", "replace")

    @staticmethod
    def _natural_file_sort_key(file_name):
        parts = []
        for part in re.split(r"(\d+)", file_name or ""):
            if part.isdigit():
                parts.append((0, int(part)))
            else:
                parts.append((1, part.lower()))
        return parts

    @staticmethod
    def _unwrap_autoidentify_root_params_payload(root_params_payload):
        data = root_params_payload
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data.get("data")
        if isinstance(data, dict) and isinstance(data.get("result"), dict):
            data = data.get("result")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_autoidentify_root_param_specified(value):
        if value is None:
            return False
        text = value.strip() if isinstance(value, string_types) else (u"%s" % value).strip()
        if not text:
            return False
        # 3DMPS 节点配置表里的占位提示不能当成已指定参数。
        placeholders = set([
            u"\u8bf7\u53cc\u51fb\u8fdb\u884c\u9009\u62e9",
            u"\u8bf7\u53cc\u51fb\u8fdb\u884c\u6307\u5b9a",
            u"\u8bf7\u53cc\u51fb\u9009\u62e9",
            u"\u8bf7\u53cc\u51fb\u6307\u5b9a",
            u"\u672a\u6307\u5b9a",
        ])
        return text not in placeholders

    @staticmethod
    def _autoidentify_main_direction_sort_key(name):
        match = re.match(u"^\u4e3b\u65b9\u5411(\\d+)$", name or "")
        if match:
            return (0, int(match.group(1)), name)
        return (1, 0, name or "")

    @classmethod
    def _normalize_autoidentify_main_direction_values(cls, raw_values):
        if isinstance(raw_values, dict):
            items = raw_values.items()
        elif isinstance(raw_values, list):
            items = []
            for item in raw_values:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("field") or item.get("key")
                    value = item.get("value")
                    if name:
                        items.append((name, value))
        else:
            items = []

        values = OrderedDict()
        for name, value in sorted(items, key=lambda pair: cls._autoidentify_main_direction_sort_key(pair[0])):
            if re.match(u"^\u4e3b\u65b9\u5411\\d+$", name or ""):
                values[name] = value
        return values

    @classmethod
    def _build_autoidentify_root_params_verification(cls, root_params_payload):
        data = cls._unwrap_autoidentify_root_params_payload(root_params_payload)
        origin_field = u"\u539f\u70b9"

        if not data:
            return {
                "status": "error",
                "all_required_specified": False,
                "origin_value": "",
                "main_direction_values": {},
                "missing_fields": [origin_field],
            }

        origin_value = data.get("origin_value", data.get(origin_field, ""))
        main_direction_values = cls._normalize_autoidentify_main_direction_values(
            data.get("main_direction_values", {})
        )

        missing_fields = []
        if not cls._is_autoidentify_root_param_specified(origin_value):
            missing_fields.append(origin_field)
        for field_name, field_value in main_direction_values.items():
            if not cls._is_autoidentify_root_param_specified(field_value):
                missing_fields.append(field_name)

        return {
            "status": "missing_required" if missing_fields else "ready",
            "all_required_specified": not missing_fields,
            "origin_value": origin_value,
            "main_direction_values": dict(main_direction_values),
            "missing_fields": missing_fields,
        }

    def _get_autoidentify_root_params_verification(self, timeout=5):
        root_params = self.pipe.call("main.bof_root_params.get", {}, timeout=timeout)
        return root_params, self._build_autoidentify_root_params_verification(root_params)

    @staticmethod
    def _count_bof_tree_nodes(node):
        if not isinstance(node, dict):
            return 0
        total = 0
        for child in node.values():
            total += 1
            total += AutoIdentifyServiceMixin._count_bof_tree_nodes(child)
        return total

    @classmethod
    def _build_autoidentify_bof_verification(cls, before_tree, after_tree):
        before_data = before_tree.get("data", before_tree) if isinstance(before_tree, dict) else {}
        after_data = after_tree.get("data", after_tree) if isinstance(after_tree, dict) else {}
        before_count = cls._count_bof_tree_nodes(before_data)
        after_count = cls._count_bof_tree_nodes(after_data)
        return {
            "status": "changed" if before_data != after_data else "unchanged",
            "changed": before_data != after_data,
            "before_node_count": before_count,
            "after_node_count": after_count,
        }

    def _wait_for_autoidentify_result(self, *args, **kwargs):
        # 兼容旧测试/旧调用点；当前第 2 步成功门槛已经改为根节点必要参数预检。
        return {"status": "skipped", "changed": False}

    def _find_known_autoidentify_failure_dialog(self):
        # 当前主路径依赖根节点预检；这里保留兜底入口，便于后续接入已知业务弹窗检测。
        return {"found": False}

    @classmethod
    def _parse_autoidentify_combination_file(cls, file_path):
        text = cls._read_text_file_with_fallback(file_path)
        feature_states = []
        control_values = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "," in line:
                feature_name, state_value = line.split(",", 1)
                feature_name = feature_name.strip()
                state_token = state_value.strip().lower()
                if feature_name and state_token in ("0", "1", "true", "false", "yes", "no"):
                    feature_states.append({
                        "name": feature_name,
                        "checked": state_token in ("1", "true", "yes"),
                    })
                    continue
            if "=" in line:
                control_name, control_value = line.split("=", 1)
                control_name = control_name.strip()
                if control_name:
                    control_values[control_name] = control_value.strip()

        if not feature_states:
            return None

        file_name = os.path.basename(file_path)
        template_name = os.path.splitext(file_name)[0]
        checked_features = [
            feature_state["name"] for feature_state in feature_states if feature_state.get("checked")
        ]
        relative_dir = _config.CONFIG.get("autoidentify_with_direction_dir", "")
        relative_path = os.path.join(relative_dir, file_name) if relative_dir else file_name
        checked_count = len(checked_features)
        total_count = len(feature_states)
        return {
            "id": template_name,
            "title": file_name,
            "desc": u"\u6765\u81ea\u914d\u7f6e\u6587\u4ef6\uff1a%s\uff0c\u52fe\u9009 %d/%d \u9879\u3002" % (
                file_name, checked_count, total_count
            ),
            "template_name": template_name,
            "file_name": file_name,
            "relative_path": relative_path,
            "features": checked_features,
            "feature_states": feature_states,
            "feature_total": total_count,
            "control_values": control_values,
            "tags": checked_features[:6],
            "checked_list": cls._build_autoidentify_checked_list_from_states(feature_states),
        }

    @classmethod
    def _load_autoidentify_feature_combinations(cls):
        config_dir = getattr(_config, "AUTOIDENTIFY_WITH_DIRECTION_DIR", "")
        if not config_dir or not os.path.isdir(config_dir):
            return [], [u"\u672a\u627e\u5230\u81ea\u52a8\u8bc6\u522b\u65b9\u5411\u914d\u7f6e\u76ee\u5f55\uff1a%s" % config_dir]

        combinations = []
        load_errors = []
        file_names = [
            file_name for file_name in os.listdir(config_dir)
            if file_name.lower().endswith(".ini")
        ]
        for file_name in sorted(file_names, key=cls._natural_file_sort_key):
            file_path = os.path.join(config_dir, file_name)
            try:
                combination = cls._parse_autoidentify_combination_file(file_path)
            except Exception as exc:
                load_errors.append(u"%s: %s" % (file_name, exc))
                continue
            if combination is not None:
                combinations.append(combination)
        if not combinations and not load_errors:
            load_errors.append(u"\u81ea\u52a8\u8bc6\u522b\u65b9\u5411\u914d\u7f6e\u76ee\u5f55\u4e2d\u6ca1\u6709 ini \u6587\u4ef6\uff1a%s" % config_dir)
        return combinations, load_errors

    @staticmethod
    def _autoidentify_combination_public_item(item, current_features=None):
        features = list(item.get("features") or [])
        selected_count = len(features)
        overlap = 0
        if current_features:
            overlap = len(set(features).intersection(set(current_features)))
        checked_list = item.get("checked_list") or AutoIdentifyServiceMixin._build_autoidentify_checked_list(features)
        return {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "desc": item.get("desc", ""),
            "template_name": item.get("template_name", ""),
            "file_name": item.get("file_name", ""),
            "relative_path": item.get("relative_path", ""),
            "features": features,
            "feature_count": selected_count,
            "feature_total": item.get("feature_total", selected_count),
            "tags": list(item.get("tags") or [])[:8],
            "checked_list": checked_list,
            "control_values": dict(item.get("control_values") or {}),
            "current_overlap": overlap,
        }

    @staticmethod
    def _parse_autoidentify_checked_features(value):
        if isinstance(value, dict):
            for key in ("data", "result", "checked_list", "checkedList", "value", "message"):
                if key in value:
                    parsed = AutoIdentifyServiceMixin._parse_autoidentify_checked_features(value.get(key))
                    if parsed:
                        return parsed
            return []
        if isinstance(value, list):
            features = []
            for item in value:
                features.extend(AutoIdentifyServiceMixin._parse_autoidentify_checked_features(item))
            seen = set()
            unique = []
            for feature in features:
                if feature not in seen:
                    seen.add(feature)
                    unique.append(feature)
            return unique
        if not isinstance(value, string_types):
            return []
        features = []
        for name, state in re.findall(r"\[([^,\[\]]+)\s*,\s*([^\]\[]+)\]", value):
            if str(state).strip() in ("1", "true", "True", "TRUE"):
                feature = name.strip()
                if feature:
                    features.append(feature)
        return features
    def _choose_autoidentify_template(self, params, steps):
        requested_template_name = self._first_non_empty_param(
            params, "template_name", "templateName", "filename"
        )
        list_result = None
        template_names = []
        matched_template_name = ""
        last_list_error = None
        for attempt in range(1, 21):
            time.sleep(0.25)
            try:
                list_result = self.pipe.call("GetExtractDataList", {}, timeout=5)
                last_list_error = None
                template_names = self._extract_autoidentify_template_names(list_result)
                if requested_template_name:
                    matched_template_name = self._find_autoidentify_template_name(
                        requested_template_name, template_names
                    )
                elif template_names:
                    template_index = self._coerce_positive_int(
                        params.get("template_index", params.get("templateIndex", 0))
                    )
                    if template_index and template_index <= len(template_names):
                        matched_template_name = template_names[template_index - 1]
                    else:
                        preferred_keyword = self._first_non_empty_param(params, "preferred_keyword", "preferredKeyword")
                        if not preferred_keyword:
                            preferred_keyword = u"??"
                        for name in template_names:
                            if preferred_keyword and preferred_keyword in name:
                                matched_template_name = name
                                break
                        if not matched_template_name:
                            fallback_index = 1 if len(template_names) >= 2 else 0
                            matched_template_name = template_names[fallback_index]
                steps.append({
                    "step": "read_autoidentify_template_list",
                    "attempt": attempt,
                    "function": "GetExtractDataList",
                    "result": list_result,
                    "names": template_names,
                    "matched": matched_template_name,
                })
                if matched_template_name:
                    break
            except Exception as exc:
                last_list_error = exc
                steps.append({
                    "step": "read_autoidentify_template_list",
                    "attempt": attempt,
                    "function": "GetExtractDataList",
                    "error": str(exc),
                })
        return requested_template_name, template_names, matched_template_name, last_list_error

    def _open_autoidentify_dialog_and_choose_template(self, params, steps):
        select_root_result = self._select_bof_root_node()
        steps.append({"step": "select_bof_root_node", "result": select_root_result})

        result = self.pipe.call("do_cmdResponse_by_python", {"arg1": 60013}, timeout=10)
        steps.append({
            "step": "open_autoidentify_dialog",
            "function": "do_cmdResponse_by_python",
            "params": {"arg1": 60013},
            "result": result,
        })

        requested_template_name, template_names, matched_template_name, last_list_error = self._choose_autoidentify_template(params, steps)
        if not matched_template_name:
            message = (
                u"\u81ea\u52a8\u8bc6\u522b\u5f39\u7a97\u5df2\u6253\u5f00\uff0c\u4f46\u672a\u627e\u5230\u6307\u5b9a\u6a21\u677f\uff1a%s" % requested_template_name
                if requested_template_name else
                u"\u81ea\u52a8\u8bc6\u522b\u5f39\u7a97\u5df2\u6253\u5f00\uff0c\u4f46\u672a\u8bfb\u53d6\u5230\u53ef\u7528\u7684\u81ea\u52a8\u8bc6\u522b\u6a21\u677f\u3002"
            )
            return {
                "status": "error",
                "message": message,
                "error_code": "AUTOIDENTIFY_TEMPLATE_NOT_FOUND_IN_DIALOG",
                "template_name": requested_template_name,
                "available_templates": template_names,
                "last_list_error": str(last_list_error) if last_list_error is not None else "",
            }

        result = self.pipe.call("setExtractDataList", {"arg1": matched_template_name}, timeout=15)
        steps.append({
            "step": "select_autoidentify_template",
            "function": "setExtractDataList",
            "params": {"arg1": matched_template_name},
            "result": result,
        })
        return {
            "status": "success",
            "template_name": matched_template_name,
            "available_templates": template_names,
        }

    def _get_autoidentify_feature_combinations(self, params, source="api_tool"):
        start = time.monotonic()
        params = params or {}
        raw_combinations, load_errors = self._load_autoidentify_feature_combinations()
        combinations = [
            self._autoidentify_combination_public_item(item)
            for item in raw_combinations
        ]
        if not combinations:
            payload = {
                "status": "error",
                "message": u"\u672a\u8bfb\u53d6\u5230\u53ef\u7528\u7684\u81ea\u52a8\u8bc6\u522b\u914d\u7f6e\u5361\u7247\u3002",
                "error_code": "AUTOIDENTIFY_COMBINATION_CONFIG_NOT_FOUND",
                "config_dir": _config.CONFIG.get("autoidentify_with_direction_dir", ""),
                "load_errors": load_errors,
                "steps": [],
            }
            self._audit("get_autoidentify_feature_combinations", params, start, payload, source=source)
            return payload
        payload = {
            "status": "success",
            "mode": "awaiting_choice",
            "stage": "select_autoidentify_feature_combination",
            "message": u"\u8bf7\u9009\u62e9\u4e00\u4e2a\u81ea\u52a8\u8bc6\u522b\u9009\u62e9\u9879\u7ec4\u5408\u3002\u9009\u62e9\u540e\u5c06\u6253\u5f00\u81ea\u52a8\u8bc6\u522b\u5f39\u7a97\uff0c\u6309\u8be5\u7ec4\u5408\u52fe\u9009\u7279\u5f81\u7c7b\u578b\u5e76\u6267\u884c\u81ea\u52a8\u8bc6\u522b\u3002",
            "combinations": combinations,
            "config_dir": _config.CONFIG.get("autoidentify_with_direction_dir", ""),
            "load_errors": load_errors,
            "steps": [],
        }
        self._audit("get_autoidentify_feature_combinations", params, start, payload, source=source)
        return payload

    def _apply_auto_identify_with_combination(self, params, source="api_tool"):
        start = time.monotonic()
        params = params or {}
        steps = []
        combination_id = self._first_non_empty_param(params, "combination_id", "combinationId", "id")
        checked_list = self._first_non_empty_param(params, "checked_list", "checkedList")
        selected_combination = None
        raw_combinations, load_errors = self._load_autoidentify_feature_combinations()
        normalized_combination_id = self._normalize_autoidentify_template_name(combination_id).lower()
        for item in raw_combinations:
            lookup_values = [
                item.get("id", ""),
                item.get("template_name", ""),
                item.get("file_name", ""),
                item.get("title", ""),
            ]
            normalized_lookup_values = [
                self._normalize_autoidentify_template_name(value).lower()
                for value in lookup_values if value
            ]
            if normalized_combination_id and normalized_combination_id in normalized_lookup_values:
                selected_combination = item
                break
        if selected_combination is not None:
            checked_list = selected_combination.get("checked_list") or self._build_autoidentify_checked_list(
                selected_combination.get("features") or []
            )
            if not self._first_non_empty_param(params, "template_name", "templateName", "filename"):
                params = dict(params)
                params["template_name"] = selected_combination.get("template_name", "")
        if not checked_list:
            payload = {
                "status": "error",
                "message": u"\u7f3a\u5c11\u81ea\u52a8\u8bc6\u522b\u9009\u62e9\u9879\u7ec4\u5408\uff0c\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u7ec4\u5408\u5361\u7247\u3002",
                "error_code": "MISSING_AUTOIDENTIFY_COMBINATION",
                "load_errors": load_errors,
                "steps": steps,
            }
            self._audit("apply_auto_identify_with_combination", params, start, payload, source=source)
            return payload

        try:
            open_result = self._open_autoidentify_dialog_and_choose_template(params, steps)
            if open_result.get("status") != "success":
                payload = dict(open_result)
                payload["steps"] = steps
                self._audit("apply_auto_identify_with_combination", params, start, payload, source=source)
                return payload

            result = self.pipe.call("SetAutoIdentifyCheckedList", {"arg1": checked_list}, timeout=5)
            steps.append({
                "step": "set_autoidentify_checked_list",
                "function": "SetAutoIdentifyCheckedList",
                "params": {"arg1": checked_list},
                "result": result,
            })

            result = self.pipe.call("OnBnClickedOk", {}, timeout=get_timeout("auto_identify"))
            steps.append({
                "step": "confirm_autoidentify_dialog",
                "function": "OnBnClickedOk",
                "params": {},
                "result": result,
            })

            payload = {
                "status": "success",
                "message": u"\u5df2\u6309\u9009\u62e9\u9879\u7ec4\u5408\u6267\u884c\u81ea\u52a8\u7279\u5f81\u8bc6\u522b\uff1a%s" % (
                    selected_combination.get("title") if selected_combination else combination_id or u"\u81ea\u5b9a\u4e49\u7ec4\u5408"
                ),
                "template_name": open_result.get("template_name", ""),
                "available_templates": open_result.get("available_templates", []),
                "combination": self._autoidentify_combination_public_item(selected_combination) if selected_combination else {},
                "checked_list": checked_list,
                "steps": steps,
            }
            self._audit("apply_auto_identify_with_combination", params, start, payload, source=source)
            return payload
        except Exception as exc:
            if is_timeout_error(exc):
                payload = make_timeout_error_payload("apply_auto_identify_with_combination", exc)
            else:
                payload = {"status": "error", "message": str(exc), "tool": "apply_auto_identify_with_combination"}
            payload["steps"] = steps
            self._audit("apply_auto_identify_with_combination", params, start, payload, error=exc, source=source)
            return payload

    def _open_and_confirm_autoidentify_dialog(self, params, source="api_tool"):
        """打开 3DMPS 自动识别加工特征对话框并点击确定，不等待后续几何识别完成。"""
        start = time.monotonic()
        params = params or {}
        steps = []

        try:
            try:
                # 打开自动识别对话框前先读 BOF 根节点配置，缺参数时让工作流停在第 2 步重试。
                root_params, verification = self._get_autoidentify_root_params_verification(timeout=5)
                steps.append({
                    "step": "precheck_autoidentify_root_params",
                    "function": "main.bof_root_params.get",
                    "result": root_params,
                    "verification": verification,
                })
            except Exception as exc:
                if is_function_not_found_error(exc, "main.bof_root_params.get"):
                    verification = {
                        "status": "skipped",
                        "all_required_specified": True,
                        "missing_fields": [],
                        "warning": str(exc),
                    }
                    steps.append({
                        "step": "precheck_autoidentify_root_params_skipped",
                        "function": "main.bof_root_params.get",
                        "reason": "function_not_registered",
                        "error": str(exc),
                    })
                else:
                    payload = {
                        "status": "error",
                        "message": u"\u81ea\u52a8\u8bc6\u522b\u524d\u7f6e\u68c0\u67e5\u5931\u8d25\uff0c\u65e0\u6cd5\u8bfb\u53d6 BOF \u6839\u8282\u70b9\u53c2\u6570\u3002",
                        "error_code": "AUTOIDENTIFY_ROOT_PARAMS_CHECK_FAILED",
                        "verification": {
                            "status": "error",
                            "all_required_specified": False,
                            "missing_fields": [],
                            "error": str(exc),
                        },
                        "steps": steps,
                    }
                    self._audit("open_and_confirm_autoidentify_dialog", params, start, payload, source=source)
                    return payload

            if not verification.get("all_required_specified"):
                payload = {
                    "status": "error",
                    "message": u"\u81ea\u52a8\u8bc6\u522b\u524d\u7f6e\u68c0\u67e5\u672a\u901a\u8fc7\uff1a%s \u5c1a\u672a\u6307\u5b9a\u3002" % (
                        u"\u3001".join(verification.get("missing_fields") or [])
                    ),
                    "error_code": "AUTOIDENTIFY_ROOT_PARAMS_MISSING",
                    "verification": verification,
                    "steps": steps,
                }
                self._audit("open_and_confirm_autoidentify_dialog", params, start, payload, source=source)
                return payload

            result = self.pipe.call("do_cmdResponse_by_python", {"arg1": 60013}, timeout=10)
            steps.append({
                "step": "open_autoidentify_dialog",
                "function": "do_cmdResponse_by_python",
                "params": {"arg1": 60013},
                "result": result,
            })

            dialog_ready = False
            last_dialog_error = None
            for attempt in range(1, DIALOG_POLL_MAX_ATTEMPTS + 1):
                time.sleep(DIALOG_POLL_INTERVAL_SEC)
                try:
                    list_result = self.pipe.call("GetExtractDataList", {}, timeout=3)
                    steps.append({
                        "step": "wait_autoidentify_dialog",
                        "attempt": attempt,
                        "function": "GetExtractDataList",
                        "result": list_result,
                    })
                    dialog_ready = True
                    break
                except Exception as exc:
                    last_dialog_error = exc
                    steps.append({
                        "step": "wait_autoidentify_dialog",
                        "attempt": attempt,
                        "function": "GetExtractDataList",
                        "error": str(exc),
                    })
            if not dialog_ready:
                payload = {
                    "status": "error",
                    "message": u"已点击自动识别按钮，但未确认自动识别加工特征对话框已弹出。",
                    "error_code": "AUTOIDENTIFY_DIALOG_NOT_READY",
                    "last_dialog_error": str(last_dialog_error) if last_dialog_error is not None else "",
                    "steps": steps,
                }
                self._audit("open_and_confirm_autoidentify_dialog", params, start, payload, source=source)
                return payload

            confirm_timeout = 1.0
            try:
                result = self.pipe.call("OnBnClickedOk", {}, timeout=confirm_timeout)
                steps.append({
                    "step": "confirm_autoidentify_dialog",
                    "function": "OnBnClickedOk",
                    "params": {},
                    "timeout": confirm_timeout,
                    "result": result,
                })
                payload = {
                    "status": "success",
                    "message": u"已打开自动识别加工特征对话框并点击确定。",
                    "steps": steps,
                }
            except Exception as exc:
                if not is_timeout_error(exc):
                    raise
                steps.append({
                    "step": "confirm_autoidentify_dialog",
                    "function": "OnBnClickedOk",
                    "params": {},
                    "timeout": confirm_timeout,
                    "accepted": True,
                    "error": str(exc),
                })
                payload = {
                    "status": "accepted",
                    "message": u"已打开自动识别加工特征对话框并提交确定，3DMPS 后台继续处理。",
                    "background": True,
                    "steps": steps,
                }
            self._audit("open_and_confirm_autoidentify_dialog", params, start, payload, source=source)
            return payload
        except Exception as exc:
            if is_timeout_error(exc):
                payload = make_timeout_error_payload("open_and_confirm_autoidentify_dialog", exc)
            else:
                payload = {"status": "error", "message": str(exc), "tool": "open_and_confirm_autoidentify_dialog"}
            payload["steps"] = steps
            self._audit("open_and_confirm_autoidentify_dialog", params, start, payload, error=exc, source=source)
            return payload
    def _apply_auto_identify(self, params, source="api_tool"):
        """通过自动识别弹窗执行自动特征识别，避免裸调未注册的 auto_identify 管道函数。"""
        start = time.monotonic()
        params = params or {}
        steps = []
        requested_template_name = self._first_non_empty_param(
            params, "template_name", "templateName", "filename"
        )

        try:
            select_root_result = self._select_bof_root_node()
            steps.append({"step": "select_bof_root_node", "result": select_root_result})

            result = self.pipe.call("do_cmdResponse_by_python", {"arg1": 60013}, timeout=10)
            steps.append({
                "step": "open_autoidentify_dialog",
                "function": "do_cmdResponse_by_python",
                "params": {"arg1": 60013},
                "result": result,
            })

            list_result = None
            template_names = []
            matched_template_name = ""
            last_list_error = None
            for attempt in range(1, DIALOG_POLL_MAX_ATTEMPTS + 1):
                time.sleep(DIALOG_POLL_INTERVAL_SEC)
                try:
                    list_result = self.pipe.call("GetExtractDataList", {}, timeout=5)
                    last_list_error = None
                    template_names = self._extract_autoidentify_template_names(list_result)
                    matched_template_name = self._choose_autoidentify_template_name(params, template_names)
                    steps.append({
                        "step": "read_autoidentify_template_list",
                        "attempt": attempt,
                        "function": "GetExtractDataList",
                        "result": list_result,
                        "names": template_names,
                        "matched_template_name": matched_template_name,
                    })
                except Exception as exc:
                    last_list_error = exc
                    steps.append({
                        "step": "read_autoidentify_template_list",
                        "attempt": attempt,
                        "function": "GetExtractDataList",
                        "error": str(exc),
                    })
                    continue
                if matched_template_name:
                    break

            if not matched_template_name:
                self._cancel_active_dialog(steps, "cancel_autoidentify_dialog_after_no_match")
                message = (
                    u"自动识别弹窗已打开，但未找到指定模板：%s" % requested_template_name
                    if requested_template_name else
                    u"自动识别弹窗已打开，但未读取到可用的自动识别模板。"
                )
                payload = {
                    "status": "error",
                    "message": message,
                    "error_code": "AUTOIDENTIFY_TEMPLATE_NOT_FOUND_IN_DIALOG",
                    "template_name": requested_template_name,
                    "available_templates": template_names,
                    "steps": steps,
                }
                if last_list_error is not None:
                    payload["last_list_error"] = str(last_list_error)
                self._audit("auto_identify", params, start, payload, source=source)
                return payload

            result = self.pipe.call("setExtractDataList", {"arg1": matched_template_name}, timeout=15)
            steps.append({
                "step": "select_autoidentify_template",
                "function": "setExtractDataList",
                "params": {"arg1": matched_template_name},
                "result": result,
            })

            result = self.pipe.call("OnBnClickedOk", {}, timeout=get_timeout("auto_identify"))
            steps.append({
                "step": "confirm_autoidentify_dialog",
                "function": "OnBnClickedOk",
                "params": {},
                "result": result,
            })

            payload = {
                "status": "success",
                "message": u"已按自动识别模板执行自动特征识别：%s" % matched_template_name,
                "template_name": matched_template_name,
                "available_templates": template_names,
                "steps": steps,
            }
            self._audit("auto_identify", params, start, payload, source=source)
            return payload
        except Exception as exc:
            if is_timeout_error(exc):
                payload = make_timeout_error_payload("auto_identify", exc)
            elif is_function_not_found_error(exc, "auto_identify"):
                payload = make_unsupported_tool_payload("auto_identify", exc)
            else:
                payload = {"status": "error", "message": str(exc), "tool": "auto_identify"}
            payload["template_name"] = requested_template_name
            payload["steps"] = steps
            self._audit("auto_identify", params, start, payload, error=exc, source=source)
            return payload
