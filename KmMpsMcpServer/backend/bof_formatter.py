# -*- coding: utf-8 -*-
from __future__ import print_function


class BofFormatterMixin(object):
    @staticmethod
    def _looks_like_model_tree_key(value):
        lower_value = str(value or "").strip().lower()
        return lower_value.endswith((".prt", ".catpart", ".z3prt", ".stp", ".step"))

    @staticmethod
    def _mojibake_readability_score(text):
        score = 0
        for ch in text or "":
            code = ord(ch)
            if 0x4E00 <= code <= 0x9FFF:
                score += 3
            elif 0x00A0 <= code <= 0x00FF:
                score -= 2
        return score

    @classmethod
    def _repair_mojibake_text(cls, value):
        text = str(value or "").strip()
        if not text:
            return text
        best = text
        best_score = cls._mojibake_readability_score(text)
        for source_encoding in ("latin1", "cp1252"):
            try:
                candidate = text.encode(source_encoding).decode("gb18030")
            except UnicodeError:
                continue
            candidate_score = cls._mojibake_readability_score(candidate)
            if candidate_score > best_score:
                best = candidate
                best_score = candidate_score
        return best

    @classmethod
    def _extract_bof_model_names(cls, bof_result):
        data = cls._extract_bof_data_node(bof_result)
        model_names = []
        seen = set()

        def collect(node):
            if not isinstance(node, dict):
                return
            for key, child in node.items():
                if cls._looks_like_model_tree_key(key):
                    name = cls._repair_mojibake_text(key)
                    if name and name not in seen:
                        seen.add(name)
                        model_names.append(name)
                collect(child)

        collect(data)
        return model_names

    @classmethod
    def _format_bof_tree_reply(cls, result):
        if not isinstance(result, dict) or result.get("status") == "error":
            return None
        model_names = cls._extract_bof_model_names(result)
        tree_lines = cls._format_bof_tree_lines(result)
        lines = [u"已获取 BOF/特征树数据。"]
        if model_names:
            lines.append(u"模型：" + u"、".join(model_names[:5]))
        if tree_lines:
            lines.append(u"BOF/特征树结构：")
            lines.extend(tree_lines)
        else:
            lines.append(u"当前未提取到特征节点名称。")
        return "\n".join(lines)

    @classmethod
    def _format_bof_feature_summary_reply(cls, result):
        if not isinstance(result, dict) or result.get("status") == "error":
            return None
        model_names = cls._extract_bof_model_names(result)
        features = cls._extract_bof_feature_names(result)
        lines = [u"已获取 BOF/特征树数据。"]
        if model_names:
            lines.append(u"模型：" + u"、".join(model_names[:5]))
        if features:
            lines.append(u"特征节点共 %d 个，前 %d 个：" % (len(features), min(len(features), 40)))
            for index, feature in enumerate(features[:40], 1):
                lines.append(u"%d. %s" % (index, feature))
            if len(features) > 40:
                lines.append(u"……还有 %d 个特征节点未展示。" % (len(features) - 40))
        else:
            lines.append(u"当前未提取到特征节点名称。")
        return "\n".join(lines)

    @classmethod
    def _format_bof_tree_lines(cls, bof_result, max_lines=160):
        data = cls._extract_bof_data_node(bof_result)
        if not isinstance(data, dict):
            return []
        lines = []
        omitted = [0]

        def repair(value):
            return cls._repair_mojibake_text(value)

        def collapse_duplicate_child(name, child):
            current = child
            # C++ BOF 快照可能重复包装同名节点，展示时合并但保留真实父子结构。
            while isinstance(current, dict) and len(current) == 1:
                only_key, only_child = next(iter(current.items()))
                if repair(only_key) != repair(name):
                    break
                current = only_child
            return current

        def append_node(name, child, prefix, is_last):
            if len(lines) >= max_lines:
                omitted[0] += 1
                return
            text = repair(name)
            if not text:
                return
            connector = u"└─ " if is_last else u"├─ "
            lines.append(prefix + connector + text)
            child = collapse_duplicate_child(name, child)
            if not isinstance(child, dict) or not child:
                return
            items = list(child.items())
            child_prefix = prefix + (u"   " if is_last else u"│  ")
            for index, item in enumerate(items):
                append_node(item[0], item[1], child_prefix, index == len(items) - 1)

        items = list(data.items())
        for index, item in enumerate(items):
            append_node(item[0], item[1], u"", index == len(items) - 1)
        if omitted[0]:
            lines.append(u"……还有 %d 个节点未展示。" % omitted[0])
        return lines

    @classmethod
    def _extract_bof_data_node(cls, value):
        if not isinstance(value, dict):
            return {}
        data = value.get("data")
        if isinstance(data, dict):
            nested_result = data.get("result")
            if isinstance(nested_result, dict) and isinstance(nested_result.get("data"), dict):
                return nested_result.get("data")
            if isinstance(data.get("data"), dict):
                return data.get("data")
            if any(cls._looks_like_model_tree_key(key) for key in data.keys()):
                return data
        result = value.get("result")
        if isinstance(result, dict) and isinstance(result.get("data"), dict):
            return result.get("data")
        if any(cls._looks_like_model_tree_key(key) for key in value.keys()):
            return value
        return data if isinstance(data, dict) else value

    @classmethod
    def _extract_bof_feature_names(cls, bof_result):
        data = cls._extract_bof_data_node(bof_result)
        feature_names = []
        seen = set()

        def add_name(name):
            text = cls._repair_mojibake_text(name)
            if not text or text in seen:
                return
            seen.add(text)
            feature_names.append(text)

        def collect(node, under_model):
            if not isinstance(node, dict):
                return
            for key, child in node.items():
                if cls._looks_like_model_tree_key(key):
                    collect(child, True)
                else:
                    add_name(key)
                    collect(child, under_model)

        collect(data, False)
        return feature_names
