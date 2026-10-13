# -*- coding: utf-8 -*-
from __future__ import print_function

import ctypes
import os
import re
import threading
import time

from . import agent_config as _config
from .agent_config import DIALOG_POLL_INTERVAL_SEC, DIALOG_POLL_MAX_ATTEMPTS
from .pipe_client import is_timeout_error, make_timeout_error_payload
from .tool_runtime import SKILL_RUNNERS

try:
    string_types = (basestring,)  # type: ignore[name-defined]
except NameError:
    string_types = (str,)


class GroupTemplateServiceMixin(object):
    def _save_group_template_file(self, confirm_result):
        """将 confirm skill 返回的 XML 写入 3DMPS 安装目录 GroupTemplate 子目录。

        confirm_result: select_group_template.js confirm action 的返回 dict，
                        需要包含 selectedTemplate.filename 和 xml 字段。
        返回: dict {status, saved_path/bytes} 或 {status, message}
        status 取 "success" / "error"。
        """
        if not isinstance(confirm_result, dict) or not confirm_result.get("ok", True):
            return {"status": "error", "message": u"confirm skill 未成功返回"}

        selected = confirm_result.get("selectedTemplate") or {}
        filename = selected.get("filename", "")
        xml = confirm_result.get("xml", "")

        if not filename:
            return {"status": "error", "message": u"未找到模板文件名(filename 字段为空)"}
        if not xml:
            return {"status": "error", "message": u"未找到 XML 内容(xml 字段为空)"}

        try:
            safe_filename = os.path.basename(filename)
            if safe_filename != filename or not safe_filename:
                return {"status": "error", "message": u"模板文件名非法: %s" % filename}
            target_path = os.path.abspath(os.path.join(_config.GROUP_TEMPLATE_SAVE_DIR, safe_filename))
            save_dir = os.path.abspath(_config.GROUP_TEMPLATE_SAVE_DIR)
            if os.path.commonpath([save_dir, target_path]) != save_dir:
                return {"status": "error", "message": u"模板保存路径越界: %s" % filename}
            if not os.path.isdir(_config.GROUP_TEMPLATE_SAVE_DIR):
                os.makedirs(_config.GROUP_TEMPLATE_SAVE_DIR)
            existed_before = os.path.exists(target_path)
            # xml 字段是 GB2312 编码的 Unicode 字符串（由 JS buildXml 生成）。
            # 用 errors="replace" 防止个别生僻字导致编码失败。
            xml_bytes = xml.encode("gb2312", errors="replace")
            with open(target_path, "wb") as fp:
                fp.write(xml_bytes)
            return {
                "status": "success",
                "saved_path": target_path,
                "filename": safe_filename,
                "bytes": len(xml_bytes),
                "overwritten": existed_before,
            }
        except Exception as exc:
            return {"status": "error", "message": u"写入模板文件失败: %s" % exc}

    @staticmethod
    def _unique_group_template_names(names):
        unique_names = []
        seen = set()
        for name in names:
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            unique_names.append(name)
        return unique_names

    @classmethod
    def _extract_group_template_names(cls, list_result):
        if isinstance(list_result, dict):
            names = []
            for key in (
                "data",
                "result",
                "fileList",
                "files",
                "template_names",
                "templateNames",
                "template_string",
                "templateString",
                "names",
            ):
                if key in list_result:
                    names.extend(cls._extract_group_template_names(list_result.get(key)))
            return cls._unique_group_template_names(names)
        if isinstance(list_result, list):
            names = []
            for item in list_result:
                names.extend(cls._extract_group_template_names(item))
            return cls._unique_group_template_names(names)
        if isinstance(list_result, string_types):
            text = list_result.strip()
            if not text:
                return []
            names = [match.strip() for match in re.findall(r"\[([^\[\]]+)\]", text) if match.strip()]
            if not names:
                names = [part.strip() for part in re.split(r"[\r\n,;]+", text) if part.strip()]
            return cls._unique_group_template_names(names)
        return []

    def _call_group_template_list(self, timeout=15):
        return self.pipe.call("GetAllGroupTemplateList", {}, timeout=timeout)

    @classmethod
    def _start_auto_confirm_group_template_warning(cls, timeout=10.0):
        """Auto-confirm the warning shown while loading a group template."""
        state = {"enabled": False, "clicked": False, "message": "", "error": ""}
        if os.name != "nt":
            state["error"] = "auto confirm is only available on Windows"
            return None, state

        stop_event = threading.Event()

        def worker():
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                enum_child_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows.argtypes = [enum_windows_proc, ctypes.c_void_p]
                user32.EnumChildWindows.argtypes = [ctypes.c_void_p, enum_child_proc, ctypes.c_void_p]
                user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
                user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
                user32.IsWindowVisible.argtypes = [ctypes.c_void_p]

                WM_COMMAND = 0x0111
                BM_CLICK = 0x00F5
                IDYES = 6
                deadline = time.monotonic() + float(timeout)
                state["enabled"] = True

                while not stop_event.is_set() and time.monotonic() < deadline and not state["clicked"]:
                    target_windows = []

                    def enum_window(hwnd, _lparam):
                        if not user32.IsWindowVisible(hwnd):
                            return True
                        title = cls._win32_get_window_text(user32, hwnd)
                        class_name = cls._win32_get_class_name(user32, hwnd)
                        if title == "KM 3DMPS" and class_name == "#32770":
                            target_windows.append(hwnd)
                        return True

                    user32.EnumWindows(enum_windows_proc(enum_window), None)

                    for hwnd in target_windows:
                        child_texts = []
                        yes_buttons = []

                        def enum_child(child_hwnd, _lparam):
                            child_text = cls._win32_get_window_text(user32, child_hwnd)
                            child_class = cls._win32_get_class_name(user32, child_hwnd)
                            if child_text:
                                child_texts.append(child_text)
                            normalized = (child_text or "").replace("&", "").strip().lower()
                            if child_class == "Button" and (u"\u662f" in child_text or normalized in ("yes", "y")):
                                yes_buttons.append(child_hwnd)
                            return True

                        user32.EnumChildWindows(hwnd, enum_child_proc(enum_child), None)
                        combined_text = " ".join(child_texts)
                        if u"\u5220\u9664\u6240\u6709\u5206\u7ec4\u548c\u7279\u5f81" not in combined_text or u"\u5f15\u7528\u5206\u7ec4\u6a21\u677f" not in combined_text:
                            continue

                        state["message"] = combined_text
                        if yes_buttons:
                            user32.SendMessageW(yes_buttons[0], BM_CLICK, None, None)
                        else:
                            user32.PostMessageW(hwnd, WM_COMMAND, ctypes.c_void_p(IDYES), None)
                        state["clicked"] = True
                        break

                    if not state["clicked"]:
                        time.sleep(0.1)
            except Exception as exc:
                state["error"] = str(exc)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        return stop_event, state

    @classmethod
    def _normalize_group_template_candidates(cls, template_name):
        normalized = cls._normalize_group_template_name(template_name)
        if not normalized:
            return []
        candidates = [normalized]
        lower_value = normalized.lower()
        if lower_value != normalized:
            candidates.append(lower_value)
        return candidates

    @classmethod
    def _find_group_template_name(cls, template_name, template_names):
        if not template_name or not template_names:
            return ""
        candidate_names = cls._normalize_group_template_candidates(template_name)
        for candidate_name in candidate_names:
            lower_candidate = candidate_name.lower()
            for name in template_names:
                normalized_name = cls._normalize_group_template_name(name)
                if normalized_name == candidate_name or normalized_name.lower() == lower_candidate:
                    return normalized_name
        return ""

    def _save_selected_group_template(self, params):
        """将候选分组模板写入 3DMPS 模板库。

        候选卡片会传入 templateId/filename；先通过 confirm skill 生成 XML，
        再复用 _save_group_template_file 写入 GroupTemplate 目录。
        普通“按已存在模板名应用”的调用没有 templateId 时跳过保存。
        """

        params = params or {}
        template_id = self._first_non_empty_param(
            params, "templateId", "template_id", "choiceId", "choice_id"
        )
        direct_xml = self._first_non_empty_param(params, "xml")
        filename = self._first_non_empty_param(params, "filename")

        if direct_xml and filename:
            confirm_result = {
                "ok": True,
                "selectedTemplate": {"filename": filename},
                "xml": direct_xml,
            }
        elif template_id:
            runner = SKILL_RUNNERS.get("kmsoft_group_template_confirm")
            if runner is None:
                return {
                    "status": "error",
                    "message": u"kmsoft_group_template_confirm skill 不可用，无法先写入模板库。",
                    "error_code": "GROUP_TEMPLATE_CONFIRM_UNAVAILABLE",
                }
            try:
                confirm_result = runner.run({"templateId": template_id})
            except Exception as exc:
                return {
                    "status": "error",
                    "message": u"确认候选分组模板失败，未写入模板库: %s" % exc,
                    "error_code": "GROUP_TEMPLATE_CONFIRM_FAILED",
                    "template_id": template_id,
                }
        else:
            return None

        save_result = self._save_group_template_file(confirm_result)
        if save_result.get("status") != "success":
            save_result.setdefault("error_code", "GROUP_TEMPLATE_SAVE_FAILED")
        return save_result

    @staticmethod
    def _normalize_group_template_name(template_name):
        value = (template_name or "").strip().strip('"')
        if not value:
            return ""
        value = os.path.basename(value.replace("/", os.sep))
        if value.lower().endswith(".xml"):
            value = value[:-4]
        return value.strip()

    def _resolve_group_template_name(self, template_name):
        normalized = self._normalize_group_template_name(template_name)
        if not normalized:
            return ""
        try:
            list_result = self._call_group_template_list(timeout=15)
            names = self._extract_group_template_names(list_result)
        except Exception:
            names = []
        if not names:
            return normalized
        if normalized in names:
            return normalized
        lower_map = {name.lower(): name for name in names}
        resolved = lower_map.get(normalized.lower())
        if resolved:
            return resolved
        return normalized

    def _apply_group_template(self, params, source="api_tool"):
        """应用分组模板到当前文件：候选模板先写入模板库，再打开对话框应用。"""
        start = time.monotonic()
        params = params or {}
        raw_template_name = self._first_non_empty_param(
            params, "template_name", "templateName", "filename"
        )
        steps = []

        save_result = self._save_selected_group_template(params)
        if save_result is not None:
            steps.append({"step": "save_group_template_file", "result": save_result})
            if save_result.get("status") != "success":
                payload = {
                    "status": "error",
                    "message": save_result.get("message", u"写入模板库失败，已停止应用分组模板。"),
                    "error_code": save_result.get("error_code", "GROUP_TEMPLATE_SAVE_FAILED"),
                    "steps": steps,
                }
                self._audit("apply_group_template", params, start, payload, source=source)
                return payload
            raw_template_name = save_result.get("filename") or raw_template_name

        template_name = self._resolve_group_template_name(raw_template_name)
        if not template_name:
            payload = {
                "status": "error",
                "message": u"缺少分组模板名称，请先选择一个模板。",
                "error_code": "MISSING_TEMPLATE_NAME",
                "steps": steps,
            }
            self._audit("apply_group_template", params, start, payload, source=source)
            return payload

        try:
            select_root_result = self._select_bof_root_node()
            steps.append({"step": "select_bof_root_node", "result": select_root_result})
            result = self.pipe.call("do_cmdResponse_by_python", {"arg1": 52756}, timeout=10)
            steps.append({"step": "open_apply_group_template_dialog", "function": "do_cmdResponse_by_python", "params": {"arg1": 52756}, "result": result})
            list_result = None
            template_names = []
            matched_template_name = ""
            last_list_error = None
            for attempt in range(1, DIALOG_POLL_MAX_ATTEMPTS + 1):
                time.sleep(DIALOG_POLL_INTERVAL_SEC)
                try:
                    list_result = self._call_group_template_list(timeout=5)
                    last_list_error = None
                    template_names = self._extract_group_template_names(list_result)
                    matched_template_name = self._find_group_template_name(template_name, template_names)
                    steps.append({
                        "step": "read_group_template_list",
                        "attempt": attempt,
                        "function": "GetAllGroupTemplateList",
                        "result": list_result,
                        "names": template_names,
                        "matched_template_name": matched_template_name,
                    })
                except Exception as exc:
                    last_list_error = exc
                    steps.append({
                        "step": "read_group_template_list",
                        "attempt": attempt,
                        "function": "GetAllGroupTemplateList",
                        "error": str(exc),
                    })
                    continue
                if matched_template_name:
                    break
            if not matched_template_name:
                self._cancel_active_dialog(steps, "cancel_group_template_dialog_after_no_match")
                payload = {
                    "status": "error",
                    "message": u"已写入模板库，但在弹出的分组模板列表中未找到：%s" % template_name,
                    "error_code": "GROUP_TEMPLATE_NOT_FOUND_IN_DIALOG",
                    "template_name": template_name,
                    "available_templates": template_names,
                    "steps": steps,
                }
                if last_list_error is not None:
                    payload["last_list_error"] = str(last_list_error)
                self._audit("apply_group_template", params, start, payload, source=source)
                return payload

            result = self.pipe.call("SpecifyGroupTemplateName", {"arg1": matched_template_name}, timeout=15)
            steps.append({"step": "select_group_template", "function": "SpecifyGroupTemplateName", "params": {"arg1": matched_template_name}, "result": result})
            auto_confirm_stop, auto_confirm_state = self._start_auto_confirm_group_template_warning(timeout=15.0)
            try:
                result = self.pipe.call("OnBnClickedOk", {}, timeout=30)
            finally:
                if auto_confirm_stop is not None:
                    auto_confirm_stop.set()
            steps.append({"step": "confirm_group_template_dialog", "function": "OnBnClickedOk", "params": {}, "result": result, "auto_confirm_warning": auto_confirm_state})
            expand_result = self._expand_visible_bof_tree()
            steps.append({"step": "expand_bof_tree", "result": expand_result})
            payload = {
                "status": "success",
                "message": (
                    u"已写入模板库并为当前文件应用分组模板：%s" % template_name
                    if save_result is not None else
                    u"已为当前文件应用分组模板：%s" % template_name
                ),
                "template_name": template_name,
                "save_result": save_result,
                "steps": steps,
            }
            self._audit("apply_group_template", params, start, payload, source=source)
            return payload
        except Exception as exc:
            if is_timeout_error(exc):
                payload = make_timeout_error_payload("apply_group_template", exc)
            else:
                payload = {"status": "error", "message": str(exc), "tool": "apply_group_template"}
            payload["template_name"] = template_name
            payload["steps"] = steps
            self._audit("apply_group_template", params, start, payload, error=exc, source=source)
            return payload
