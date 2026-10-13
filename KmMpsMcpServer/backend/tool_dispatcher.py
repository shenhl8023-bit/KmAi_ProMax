# -*- coding: utf-8 -*-
from __future__ import print_function

import ctypes
import json
import os
import threading
import time

from .audit import AUDIT, _safe_json_size
from .pipe_client import (
    PIPE_NAME,
    is_function_not_found_error,
    is_timeout_error,
    make_timeout_error_payload,
    make_unsupported_tool_payload,
)
from .tool_runtime import (
    TOOLS,
    TOOL_PIPE_BUILDER,
    TOOL_PIPE_TARGETS,
    SKILL_RUNNERS,
    get_timeout,
    is_tool_allowed_for_agent,
)
from . import agent_config


COMPOSITE_TOOL_NAMES = frozenset([
    "apply_group_template",
    "auto_identify",
    "get_autoidentify_feature_combinations",
    "apply_auto_identify_with_combination",
    "open_and_confirm_autoidentify_dialog",
    "apply_group_template_full_flow",
    "ai_feature_inference",
    "click_auto_reasoning_button",
])


class ToolDispatcherMixin(object):
    def _audit(self, function_name, params, start_time, result, error=None, source="api_tool"):
        """统一写审计日志。失败也不抛异常（审计不应影响主流程），"""

        try:
            args_size = _safe_json_size(params)
            AUDIT.log_call(
                tool=function_name,
                source=source,
                start_time=start_time,
                result=result,
                error=error,
                args_size=args_size,
            )
        except Exception:
            pass

    @staticmethod
    def _public_tool_names():
        names = set(COMPOSITE_TOOL_NAMES)
        for tool in TOOLS:
            try:
                name = tool.get("function", {}).get("name")
            except AttributeError:
                name = None
            if name:
                names.add(name)
        names.update(SKILL_RUNNERS.keys())
        return names

    @classmethod
    def _is_registered_tool(cls, function_name):
        return function_name in cls._public_tool_names()

    def _make_unregistered_tool_payload(self, function_name, params, start, source):
        payload = {
            "status": "error",
            "error_code": "TOOL_NOT_REGISTERED",
            "tool": function_name,
            "message": "Tool is not registered or public.",
        }
        self._audit(function_name, params, start, payload, source=source)
        return payload

    @staticmethod
    def _expected_km3dmps_exe_path():
        return os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "Km3dmps.exe",
        ))

    @staticmethod
    def _iso_local_time(timestamp):
        if not timestamp:
            return ""
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        except Exception:
            return ""

    @classmethod
    def _query_km3dmps_processes(cls):
        if os.name != "nt":
            return []
        try:
            import subprocess
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-Process -Name Km3dmps -ErrorAction SilentlyContinue | "
                    "Select-Object Id,Path,StartTime | ConvertTo-Json -Compress"
                ),
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _stderr = proc.communicate(timeout=5)
        except Exception:
            return []
        if proc.returncode not in (0, None):
            return []
        try:
            text = stdout.decode("utf-8-sig", "replace").strip()
            if not text:
                return []
            data = json.loads(text)
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        processes = []
        for item in data:
            if not isinstance(item, dict):
                continue
            path = item.get("Path") or ""
            proc_info = {
                "pid": item.get("Id"),
                "path": path,
                "start_time": item.get("StartTime") or "",
            }
            if path and os.path.exists(path):
                try:
                    proc_info["exe_last_write_time"] = cls._iso_local_time(os.path.getmtime(path))
                except Exception:
                    proc_info["exe_last_write_time"] = ""
            else:
                proc_info["exe_last_write_time"] = ""
            processes.append(proc_info)
        return processes

    @classmethod
    def get_km3dmps_runtime_diagnostics(cls):
        expected_path = cls._expected_km3dmps_exe_path()
        expected_exists = os.path.exists(expected_path)
        diag = {
            "running": False,
            "processes": [],
            "expected_exe_path": expected_path,
            "expected_exe_exists": expected_exists,
            "expected_exe_last_write_time": "",
        }
        if expected_exists:
            try:
                diag["expected_exe_last_write_time"] = cls._iso_local_time(os.path.getmtime(expected_path))
            except Exception:
                diag["expected_exe_last_write_time"] = ""
        processes = cls._query_km3dmps_processes()
        diag["processes"] = processes
        diag["running"] = bool(processes)
        return diag

    @classmethod
    def _format_km3dmps_diagnostic_hint(cls, diag=None):
        diag = diag or cls.get_km3dmps_runtime_diagnostics()
        expected_path = diag.get("expected_exe_path") or ""
        expected_time = diag.get("expected_exe_last_write_time") or "未知"
        processes = diag.get("processes") or []
        if processes:
            first = processes[0]
            running_path = first.get("path") or "未知路径"
            running_time = first.get("exe_last_write_time") or "未知"
            return (
                u"当前 Km3dmps.exe：PID=%s，路径=%s，运行 exe 时间戳=%s；"
                u"期望路径=%s，期望 exe 时间戳=%s。若刚更新过桥接，请重启 3DMPS 后重试。"
            ) % (first.get("pid") or "未知", running_path, running_time, expected_path, expected_time)
        return (
            u"当前未检测到运行中的 Km3dmps.exe；期望路径=%s，期望 exe 时间戳=%s。"
            u"请启动或重启 3DMPS，确认已加载包含新桥接注册的 exe。"
        ) % (expected_path, expected_time)

    def _check_3dmps_status(self, params, start, source):
        km3dmps_diag = self.get_km3dmps_runtime_diagnostics()
        try:
            pipe_available = bool(self.pipe.is_available())
        except Exception as exc:
            payload = {
                "status": "error",
                "tool": "check_3dmps_status",
                "pipe": PIPE_NAME,
                "pipe_available": False,
                "available": False,
                "message": str(exc),
                "km3dmps": km3dmps_diag,
            }
            self._audit("check_3dmps_status", params, start, payload, error=exc, source=source)
            return payload

        payload = {
            "status": "success",
            "tool": "check_3dmps_status",
            "pipe": PIPE_NAME,
            "pipe_available": pipe_available,
            "available": pipe_available,
            "message": u"3DMPS 命名管道可用。" if pipe_available else u"3DMPS 命名管道不可用，请确认主程序已启动并完成桥接注册。",
            "km3dmps": km3dmps_diag,
        }
        self._audit("check_3dmps_status", params, start, payload, source=source)
        return payload

    def _get_features_from_bof_tree(self, params, timeout, start, source):
        actual_timeout = timeout if timeout is not None else get_timeout("get_features")
        try:
            bof_result = self.pipe.call("get_all_bof_item", {}, timeout=actual_timeout)
        except Exception as exc:
            if is_function_not_found_error(exc, "get_all_bof_item"):
                payload = make_unsupported_tool_payload("get_features", exc)
            elif is_timeout_error(exc):
                payload = make_timeout_error_payload("get_features", exc)
            else:
                payload = {"status": "error", "message": str(exc), "tool": "get_features"}
            payload["source_tool"] = "get_all_bof_item"
            self._audit("get_features", params, start, payload, error=exc, source=source)
            return payload

        if self._tool_result_is_error(bof_result):
            payload = {
                "status": "error",
                "tool": "get_features",
                "source_tool": "get_all_bof_item",
                "message": u"无法从 BOF 特征树获取特征列表。",
                "source_result": bof_result,
            }
            self._audit("get_features", params, start, payload, source=source)
            return payload

        features = self._extract_bof_feature_names(bof_result)
        payload = {
            "status": "success",
            "tool": "get_features",
            "source_tool": "get_all_bof_item",
            "features": features,
            "count": len(features),
            "message": u"已从 BOF 特征树提取特征列表。",
        }
        self._audit("get_features", params, start, payload, source=source)
        return payload

    @classmethod
    def _post_km3dmps_command(cls, command_id):
        """Post a 3DMPS command to the main frame without waiting for command completion."""
        state = {
            "status": "error",
            "message": "visible KM3DMPS main window was not found",
            "function": "PostMessageW",
            "command_id": command_id,
            "hwnd": 0,
        }
        if os.name != "nt":
            state["message"] = "posting a 3DMPS command is only available on Windows"
            return state

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows.argtypes = [enum_windows_proc, ctypes.c_void_p]
            user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
            user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            user32.PostMessageW.restype = ctypes.c_int
            kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            WM_COMMAND = 0x0111
            windows = []

            def process_path(pid):
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not handle:
                    return ""
                try:
                    size = ctypes.c_ulong(1024)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                        return buffer.value or ""
                finally:
                    kernel32.CloseHandle(handle)
                return ""

            def enum_top(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if not pid.value:
                    return True
                if os.path.basename(process_path(pid.value)).lower() == "km3dmps.exe":
                    windows.append(hwnd)
                    return False
                return True

            user32.EnumWindows(enum_windows_proc(enum_top), None)
            if not windows:
                return state

            hwnd = windows[0]
            ok = user32.PostMessageW(hwnd, WM_COMMAND, ctypes.c_void_p(int(command_id)), None)
            if not ok:
                error_code = ctypes.get_last_error()
                state.update({
                    "message": "PostMessageW failed with error code %d" % error_code,
                    "error_code": error_code,
                    "hwnd": int(hwnd),
                })
                return state

            state.update({
                "status": "success",
                "message": u"\u5df2\u5411 3DMPS \u4e3b\u7a97\u53e3\u6295\u9012\u547d\u4ee4\uff0c\u540e\u53f0\u7ee7\u7eed\u6267\u884c\u3002",
                "hwnd": int(hwnd),
            })
            return state
        except Exception as exc:
            state["message"] = str(exc)
            return state

    def _start_background_cmd_response(self, command_id, label, timeout=1.0):
        """Start the legacy pipe trigger in a daemon thread so HTTP responses never wait on it."""
        result = {
            "status": "accepted",
            "message": u"\u5df2\u63d0\u4ea4\u540e\u53f0\u89e6\u53d1\u8bf7\u6c42\uff0c3DMPS \u5c06\u7ee7\u7eed\u6267\u884c\u3002",
            "function": "do_cmdResponse_by_python",
            "params": {"arg1": command_id},
            "background": True,
            "timeout": timeout,
        }

        def worker():
            start = time.monotonic()
            worker_params = {"command_id": command_id, "label": label, "timeout": timeout}
            try:
                call_result = self.pipe.call("do_cmdResponse_by_python", {"arg1": command_id}, timeout=timeout)
                payload = {
                    "status": "success",
                    "message": u"\u540e\u53f0\u547d\u4ee4\u89e6\u53d1\u5df2\u8fd4\u56de\u3002",
                    "command_id": command_id,
                    "label": label,
                    "result": call_result,
                }
                self._audit("background_cmd_response", worker_params, start, payload, source="background")
            except Exception as exc:
                if is_timeout_error(exc):
                    payload = make_timeout_error_payload("do_cmdResponse_by_python", exc)
                    payload["status"] = "accepted"
                    payload["message"] = u"\u540e\u53f0\u547d\u4ee4\u5df2\u53d1\u51fa\uff0c\u4f46 3DMPS \u672a\u5728\u77ed\u8d85\u65f6\u5185\u8fd4\u56de\u54cd\u5e94\u3002"
                elif is_function_not_found_error(exc, "do_cmdResponse_by_python"):
                    payload = make_unsupported_tool_payload("do_cmdResponse_by_python", exc)
                else:
                    payload = {"status": "error", "message": str(exc), "command_id": command_id, "label": label}
                self._audit("background_cmd_response", worker_params, start, payload, error=exc, source="background")

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        return result

    def _trigger_ai_feature_inference_nonblocking(self):
        """Trigger AI feature inference without waiting for the long-running 3DMPS operation."""
        command_id = 60403
        post_result = self._post_km3dmps_command(command_id)
        if post_result.get("status") == "success":
            return {
                "status": "success",
                "message": u"\u5df2\u89e6\u53d1\u7279\u5f81\u63a8\u7406\uff0c3DMPS \u540e\u53f0\u7ee7\u7eed\u6267\u884c\u3002",
                "tool": "ai_feature_inference",
                "trigger": post_result,
                "background": True,
            }

        pipe_result = self._start_background_cmd_response(command_id, "ai_feature_inference", timeout=1.0)
        return {
            "status": "accepted",
            "message": u"\u5df2\u63d0\u4ea4\u7279\u5f81\u63a8\u7406\u89e6\u53d1\u8bf7\u6c42\uff0c3DMPS \u540e\u53f0\u7ee7\u7eed\u6267\u884c\u3002",
            "tool": "ai_feature_inference",
            "trigger": pipe_result,
            "primary_trigger": post_result,
            "background": True,
        }

    def _cancel_active_dialog(self, steps, step_name, timeout=5):
        try:
            result = self.pipe.call("OnBnClickedCancel", {}, timeout=timeout)
            steps.append({
                "step": step_name,
                "function": "OnBnClickedCancel",
                "params": {},
                "result": result,
            })
            return result
        except Exception as exc:
            steps.append({
                "step": step_name,
                "function": "OnBnClickedCancel",
                "params": {},
                "error": str(exc),
            })
            return None

    @staticmethod
    def _first_non_empty_param(params, *names):
        for name in names:
            value = params.get(name)
            if value is None:
                continue
            value = str(value).strip()
            if value:
                return value
        return ""

    @staticmethod
    def _win32_get_window_text(user32, hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or ""

    @staticmethod
    def _win32_get_class_name(user32, hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value or ""
    @classmethod
    def _select_bof_root_node(cls):
        """Select the visible BOF tree root before opening the apply-template menu."""
        state = {"status": "skipped", "message": "", "tree_hwnd": 0}
        if os.name != "nt":
            state["message"] = "selecting BOF root is only available on Windows"
            return state

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            enum_child_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows.argtypes = [enum_windows_proc, ctypes.c_void_p]
            user32.EnumChildWindows.argtypes = [ctypes.c_void_p, enum_child_proc, ctypes.c_void_p]
            user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            user32.SendMessageW.restype = ctypes.c_void_p
            kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            TV_FIRST = 0x1100
            TVM_GETNEXTITEM = TV_FIRST + 10
            TVM_SELECTITEM = TV_FIRST + 11
            TVM_ENSUREVISIBLE = TV_FIRST + 20
            TVGN_ROOT = 0x0000
            TVGN_CARET = 0x0009

            def process_path(pid):
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not handle:
                    return ""
                try:
                    size = ctypes.c_ulong(1024)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                        return buffer.value or ""
                finally:
                    kernel32.CloseHandle(handle)
                return ""

            def window_pid(hwnd):
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                return pid.value

            def is_km3dmps_window(hwnd):
                pid = window_pid(hwnd)
                if not pid:
                    return False
                return os.path.basename(process_path(pid)).lower() == "km3dmps.exe"

            def has_bof_parent(hwnd):
                parent = user32.GetParent(hwnd)
                depth = 0
                while parent and depth < 8:
                    if cls._win32_get_window_text(user32, parent) == u"\u7279\u5f81\u6811(BOF)":
                        return True
                    parent = user32.GetParent(parent)
                    depth += 1
                return False

            trees = []

            def enum_top(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd) or not is_km3dmps_window(hwnd):
                    return True

                def enum_child(child_hwnd, _child_lparam):
                    if not user32.IsWindowVisible(child_hwnd):
                        return True
                    if cls._win32_get_class_name(user32, child_hwnd) != "SysTreeView32":
                        return True
                    if not has_bof_parent(child_hwnd):
                        return True
                    root_item = user32.SendMessageW(child_hwnd, TVM_GETNEXTITEM, ctypes.c_void_p(TVGN_ROOT), None)
                    if root_item:
                        trees.append((child_hwnd, root_item))
                    return True

                user32.EnumChildWindows(hwnd, enum_child_proc(enum_child), None)
                return True

            user32.EnumWindows(enum_windows_proc(enum_top), None)
            if not trees:
                state["message"] = "visible BOF tree root was not found"
                return state

            tree_hwnd, root_item = trees[0]
            user32.SendMessageW(tree_hwnd, TVM_ENSUREVISIBLE, None, root_item)
            user32.SendMessageW(tree_hwnd, TVM_SELECTITEM, ctypes.c_void_p(TVGN_CARET), root_item)
            selected_item = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, ctypes.c_void_p(TVGN_CARET), None)
            state.update({
                "status": "success" if selected_item == root_item else "warning",
                "message": "BOF root selected" if selected_item == root_item else "BOF root select message was sent",
                "tree_hwnd": int(tree_hwnd),
            })
            return state
        except Exception as exc:
            state.update({"status": "error", "message": str(exc)})
            return state

    @classmethod
    def _scroll_tree_to_left(cls, user32, tree_hwnd):
        """Keep tree expand/collapse buttons visible after Win32 auto-scroll."""
        WM_HSCROLL = 0x0114
        SB_LEFT = 0x0006
        user32.SendMessageW(tree_hwnd, WM_HSCROLL, ctypes.c_void_p(SB_LEFT), None)
        user32.InvalidateRect(tree_hwnd, None, True)
        user32.UpdateWindow(tree_hwnd)

    @classmethod
    def _expand_visible_bof_tree(cls):
        """Expand the visible BOF tree after applying a group template."""
        state = {"status": "skipped", "message": "", "tree_hwnd": 0, "expanded_count": 0}
        if os.name != "nt":
            state["message"] = "expanding BOF tree is only available on Windows"
            return state

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            enum_child_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows.argtypes = [enum_windows_proc, ctypes.c_void_p]
            user32.EnumChildWindows.argtypes = [ctypes.c_void_p, enum_child_proc, ctypes.c_void_p]
            user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            user32.SendMessageW.restype = ctypes.c_void_p
            user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            user32.UpdateWindow.argtypes = [ctypes.c_void_p]
            kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            TV_FIRST = 0x1100
            TVM_EXPAND = TV_FIRST + 2
            TVM_GETNEXTITEM = TV_FIRST + 10
            TVGN_ROOT = 0x0000
            TVGN_NEXT = 0x0001
            TVGN_CHILD = 0x0004
            TVE_EXPAND = 0x0002

            def process_path(pid):
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not handle:
                    return ""
                try:
                    size = ctypes.c_ulong(1024)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                        return buffer.value or ""
                finally:
                    kernel32.CloseHandle(handle)
                return ""

            def window_pid(hwnd):
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                return pid.value

            def is_km3dmps_window(hwnd):
                pid = window_pid(hwnd)
                if not pid:
                    return False
                return os.path.basename(process_path(pid)).lower() == "km3dmps.exe"

            def has_bof_parent(hwnd):
                parent = user32.GetParent(hwnd)
                depth = 0
                while parent and depth < 8:
                    if cls._win32_get_window_text(user32, parent) == u"\u7279\u5f81\u6811(BOF)":
                        return True
                    parent = user32.GetParent(parent)
                    depth += 1
                return False

            trees = []

            def enum_top(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd) or not is_km3dmps_window(hwnd):
                    return True

                def enum_child(child_hwnd, _child_lparam):
                    if not user32.IsWindowVisible(child_hwnd):
                        return True
                    if cls._win32_get_class_name(user32, child_hwnd) != "SysTreeView32":
                        return True
                    if not has_bof_parent(child_hwnd):
                        return True
                    root_item = user32.SendMessageW(child_hwnd, TVM_GETNEXTITEM, ctypes.c_void_p(TVGN_ROOT), None)
                    if root_item:
                        trees.append((child_hwnd, root_item))
                    return True

                user32.EnumChildWindows(hwnd, enum_child_proc(enum_child), None)
                return True

            def expand_item(tree_hwnd, item):
                if not item:
                    return 0
                count = 1
                user32.SendMessageW(tree_hwnd, TVM_EXPAND, ctypes.c_void_p(TVE_EXPAND), item)
                child = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, ctypes.c_void_p(TVGN_CHILD), item)
                while child:
                    count += expand_item(tree_hwnd, child)
                    child = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, ctypes.c_void_p(TVGN_NEXT), child)
                return count

            user32.EnumWindows(enum_windows_proc(enum_top), None)
            if not trees:
                state["message"] = "visible BOF tree root was not found"
                return state

            tree_hwnd, root_item = trees[0]
            expanded_count = expand_item(tree_hwnd, root_item)
            cls._scroll_tree_to_left(user32, tree_hwnd)
            state.update({
                "status": "success",
                "message": "BOF tree expanded and scrolled left",
                "tree_hwnd": int(tree_hwnd),
                "expanded_count": int(expanded_count),
                "horizontal_scroll_reset": True,
            })
            return state
        except Exception as exc:
            state.update({"status": "error", "message": str(exc)})
            return state

    @staticmethod
    def _coerce_positive_int(value):
        try:
            number = int(value)
        except Exception:
            return 0
        return number if number > 0 else 0

    def _apply_group_template_full_flow(self, params, source="api_tool"):
        """写入并应用分组模板后，继续执行自动识别和特征推理。"""
        start = time.monotonic()
        params = params or {}
        steps = []

        template_name = self._first_non_empty_param(params, "template_name", "templateName", "filename")
        group_result = self._apply_group_template(params, source=source)
        steps.append({"step": "apply_group_template", "result": group_result})

        if self._tool_result_is_error(group_result):
            payload = {
                "status": "error",
                "message": group_result.get("message", u"分组模板写入/应用失败，已停止后续自动识别和特征推理。"),
                "error_code": group_result.get("error_code", "GROUP_TEMPLATE_CHAIN_FAILED"),
                "template_name": template_name or group_result.get("template_name", ""),
                "failed_step": "apply_group_template",
                "group_template_result": group_result,
                "steps": steps,
            }
            self._audit("apply_group_template_full_flow", params, start, payload, source=source)
            return payload

        auto_params = {}
        autoidentify_template_name = self._first_non_empty_param(
            params, "autoidentify_template_name", "autoidentifyTemplateName"
        )
        if autoidentify_template_name:
            auto_params["template_name"] = autoidentify_template_name

        autoidentify_template_index = self._coerce_positive_int(
            params.get("autoidentify_template_index", params.get("autoidentifyTemplateIndex", 0))
        )
        if autoidentify_template_index:
            auto_params["template_index"] = autoidentify_template_index

        preferred_keyword = self._first_non_empty_param(params, "preferred_keyword", "preferredKeyword")
        if preferred_keyword:
            auto_params["preferred_keyword"] = preferred_keyword

        auto_result = self._apply_auto_identify(auto_params, source=source)
        steps.append({"step": "auto_identify", "params": auto_params, "result": auto_result})
        if self._tool_result_is_error(auto_result):
            payload = {
                "status": "error",
                "message": auto_result.get("message", u"自动识别失败，已停止后续特征推理。"),
                "error_code": auto_result.get("error_code", "AUTO_IDENTIFY_CHAIN_FAILED"),
                "template_name": template_name,
                "failed_step": "auto_identify",
                "group_template_result": group_result,
                "auto_identify_result": auto_result,
                "steps": steps,
            }
            self._audit("apply_group_template_full_flow", params, start, payload, source=source)
            return payload

        inference_result = self._trigger_ai_feature_inference_nonblocking()
        steps.append({
            "step": "trigger_ai_feature_inference",
            "function": "do_cmdResponse_by_python",
            "params": {"arg1": 60403},
            "result": inference_result,
        })
        if self._tool_result_is_error(inference_result):
            payload = {
                "status": "error",
                "message": inference_result.get("message", u"触发特征推理失败。"),
                "error_code": inference_result.get("error_code", "AI_FEATURE_INFERENCE_TRIGGER_FAILED"),
                "template_name": template_name,
                "failed_step": "trigger_ai_feature_inference",
                "group_template_result": group_result,
                "auto_identify_result": auto_result,
                "ai_feature_inference_result": inference_result,
                "steps": steps,
            }
            self._audit("apply_group_template_full_flow", params, start, payload, source=source)
            return payload

        payload = {
            "status": "success",
            "message": u"已完成分组模板写入/应用和自动识别，并已触发特征推理：%s" % (template_name or u"当前模板"),
            "template_name": template_name,
            "group_template_result": group_result,
            "auto_identify_result": auto_result,
            "ai_feature_inference_result": inference_result,
            "steps": steps,
        }
        self._audit("apply_group_template_full_flow", params, start, payload, source=source)
        return payload
    def _execute_tool_impl(self, function_name, params, timeout, source, agent_id=None):
        """统一的工具执行逻辑。

        Args:
            function_name: 工具名称
            params: 工具参数
            timeout: 超时秒数，None 表示使用工具默认超时
            source: 审计来源标识（"api_tool" 或 "llm_chat"）

        Returns:
            工具执行结果字典
        """
        start = time.monotonic()
        params = params or {}

        if not self._is_registered_tool(function_name):
            return self._make_unregistered_tool_payload(function_name, params, start, source)

        if not is_tool_allowed_for_agent(agent_id, function_name):
            payload = {
                "status": "error",
                "error_code": "TOOL_NOT_ALLOWED_FOR_AGENT",
                "tool": function_name,
                "agent_id": agent_id,
                "message": u"当前助手无权调用该工具。",
            }
            self._audit(function_name, params, start, payload, source=source)
            return payload

        if function_name == "check_3dmps_status":
            return self._check_3dmps_status(params, start, source)
        if function_name == "get_features":
            return self._get_features_from_bof_tree(params, timeout, start, source)

        # 复合工具分支（这些工具内部包含多个步骤）
        if function_name == "apply_group_template":
            return self._apply_group_template(params, source=source)
        if function_name == "auto_identify":
            return self._apply_auto_identify(params, source=source)
        if function_name == "get_autoidentify_feature_combinations":
            return self._get_autoidentify_feature_combinations(params, source=source)
        if function_name == "apply_auto_identify_with_combination":
            return self._apply_auto_identify_with_combination(params, source=source)
        if function_name == "open_and_confirm_autoidentify_dialog":
            return self._open_and_confirm_autoidentify_dialog(params, source=source)
        if function_name == "apply_group_template_full_flow":
            return self._apply_group_template_full_flow(params, source=source)
        if function_name in ("ai_feature_inference", "click_auto_reasoning_button"):
            result = self._trigger_ai_feature_inference_nonblocking()
            self._audit(function_name, params, start, result, source=source)
            return result

        # Skill 分支（子进程调用）
        runner = SKILL_RUNNERS.get(function_name)
        if runner is not None:
            try:
                if function_name == "kmrag_search":
                    result = runner.run(params, env_overrides=agent_config._kmrag_runtime_env())
                else:
                    result = runner.run(params)
            except Exception as exc:
                if is_timeout_error(exc):
                    payload = make_timeout_error_payload(function_name, exc)
                else:
                    payload = {"status": "error", "error_code": "RUN_ERROR", "message": str(exc), "tool": function_name}
                self._audit(function_name, params, start, payload, error=exc, source=source)
                return payload
            self._audit(function_name, params, start, result, source=source)
            return result

        # 3DMPS 命名管道分支
        actual_timeout = timeout if timeout is not None else get_timeout(function_name)
        try:
            builder = TOOL_PIPE_BUILDER.get(function_name)
            if builder is not None and not any(str(k).startswith("arg") for k in params):
                pipe_params = builder(params)
            else:
                pipe_params = params
            pipe_function_name = TOOL_PIPE_TARGETS.get(function_name, function_name)
            result = self.pipe.call(pipe_function_name, pipe_params, timeout=actual_timeout)
        except Exception as exc:
            if is_function_not_found_error(exc, function_name):
                payload = make_unsupported_tool_payload(function_name, exc)
            elif is_timeout_error(exc):
                payload = make_timeout_error_payload(function_name, exc)
            else:
                payload = {"status": "error", "error_code": "PIPE_ERROR", "message": str(exc)}
            self._audit(function_name, params, start, payload, error=exc, source=source)
            return payload
        self._audit(function_name, params, start, result, source=source)
        return result

    def tool(self, function_name, params=None, timeout=None):
        """直接调用工具（3DMPS 命名管道或 Skill 子进程）。

        遇到「函数未注册」错误时返回结构化的暂不支持响应（不抛出异常），
        遇到「调用超时」错误时返回结构化的超时响应（不抛出异常），
        timeout=None 时按工具默认超时（get_timeout()）调用。
        """
        return self._execute_tool_impl(function_name, params, timeout, source="api_tool")

    def _execute_tool(self, name, args, agent_id=None):
        """执行 LLM 请求的工具调用，转换为命名管道格式。

        通过 TOOL_PIPE_BUILDER 注册表批量映射工具参数，
        函数未注册时返回结构化降级响应，超时时返回结构化超时响应，
        LLM 可识别后给出友好回答。

        Skill 工具（SKILL_RUNNERS 中的）走子进程分支，
        3DMPS 工具（TOOL_PIPE_BUILDER 中的）走命名管道分支，
        所有调用都写入审计日志（source=llm_chat）。
        """
        return self._execute_tool_impl(
            name, args, timeout=None, source="llm_chat", agent_id=agent_id
        )

    def _tool_result_is_error(self, result):
        if not isinstance(result, dict):
            return False
        if result.get("status") == "error" or result.get("error_code"):
            return True
        nested = result.get("result")
        if isinstance(nested, dict) and nested is not result:
            return self._tool_result_is_error(nested)
        return False
