# -*- coding: utf-8 -*-
from __future__ import print_function

import base64
import binascii
import copy
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

try:
    from urllib.parse import urlparse, parse_qs
    from urllib.parse import unquote as urllib_unquote
except ImportError:
    from urlparse import urlparse, parse_qs
    from urllib import unquote as urllib_unquote

try:
    from http.server import BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler

from . import agent_config
from .agent_profiles import DEFAULT_AGENT_ID, list_agent_summaries, resolve_agent_profile
from .agent_core import MiniAgent
from .agent_utils import _json_bytes
from .pipe_client import PIPE_NAME
from .similar_parts_service import SimilarPartsError, SimilarPartsService
from .tool_runtime import SKILL_RUNNERS, get_skill_runtime_diagnostics
from frontend.web_page import build_index_html
from frontend.web_page import _ASSETS_DIR


AGENT = MiniAgent()
SIMILAR_PARTS = SimilarPartsService(agent_config.CONFIG)

DEFAULT_MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
PROCESS_ROUTE_INPUT_MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
SIMILAR_PARTS_UPLOAD_MAX_REQUEST_BODY_BYTES = (
    int(agent_config.CONFIG.get("similar_parts_upload_max_bytes", 5 * 1024 * 1024) * 4 / 3)
    + 16 * 1024
)
API_AUTH_TOKEN = secrets.token_urlsafe(32)
ALLOWED_ORIGINS = set(["http://127.0.0.1", "http://localhost"])
MAX_TOOL_TIMEOUT_SEC = 180.0


class RequestBodyTooLarge(ValueError):
    def __init__(self, length, max_bytes):
        ValueError.__init__(
            self,
            "request body too large: %d bytes exceeds limit %d bytes" % (length, max_bytes),
        )
        self.length = length
        self.max_bytes = max_bytes


class InvalidRequestBody(ValueError):
    def __init__(self, error_code, message):
        ValueError.__init__(self, message)
        self.error_code = error_code
        self.public_message = message


def _expand_environment_path(path):
    value = path or ""
    for _ in range(5):
        user_expanded = os.path.expanduser(value) if value.startswith("~") else value
        expanded = os.path.expandvars(user_expanded)
        if expanded == value:
            break
        value = expanded
    return value


def _is_usable_absolute_path(path):
    return bool(path and "%" not in path and os.path.isabs(path))


def _normalize_origin(origin):
    origin = (origin or "").strip()
    if not origin:
        return ""
    try:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.hostname:
            return ""
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower()
        port = parsed.port
    except Exception:
        return ""
    if scheme not in ("http", "https"):
        return ""
    if port is None:
        return "%s://%s" % (scheme, host)
    return "%s://%s:%d" % (scheme, host, port)


def _origin_without_port(origin):
    parsed = urlparse(origin or "")
    if not parsed.scheme or not parsed.hostname:
        return ""
    return "%s://%s" % (parsed.scheme.lower(), parsed.hostname.lower())


def _origin_port(origin):
    parsed = urlparse(origin or "")
    try:
        return parsed.port
    except Exception:
        return None


def _is_allowed_origin(origin, server_port=None):
    """只允许本机页面来源访问 API；无 Origin 的 CEF/同源调用按本地调用处理。"""
    normalized = _normalize_origin(origin)
    if not normalized:
        return True
    origin_host = _origin_without_port(normalized)
    if origin_host not in ALLOWED_ORIGINS and normalized not in ALLOWED_ORIGINS:
        return False
    port = _origin_port(normalized)
    if port is not None and server_port is not None and int(port) != int(server_port):
        return False
    return True


def _is_api_auth_required(method, path):
    return bool(path and path.startswith("/api/"))


def _parse_tool_timeout(raw_timeout):
    if raw_timeout is None:
        return None
    try:
        timeout = float(raw_timeout)
    except Exception:
        raise ValueError("INVALID_TIMEOUT")
    if timeout < 1 or timeout > MAX_TOOL_TIMEOUT_SEC:
        raise ValueError("INVALID_TIMEOUT")
    if isinstance(raw_timeout, int):
        return int(timeout)
    return timeout


_TOOL_FAILURE_STATUSES = frozenset(("error", "failed", "failure"))
_TOOL_MESSAGE_FIELDS = ("message", "error", "reply")


def _tool_failure_node(result):
    """定位工具结果中第一个明确失败节点，兼容历史嵌套 result 结构。"""
    if not isinstance(result, dict):
        return None
    status = str(result.get("status") or "").strip().lower()
    if result.get("ok") is False or status in _TOOL_FAILURE_STATUSES or result.get("error_code"):
        return result
    nested = result.get("result")
    if isinstance(nested, dict) and nested is not result:
        return _tool_failure_node(nested)
    return None


def _first_tool_message(*payloads):
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for field in _TOOL_MESSAGE_FIELDS:
            value = payload.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()
    return u"工具执行失败"


def _tool_error_http_status(error_code):
    """把统一工具错误码映射为稳定的 HTTP 语义。"""
    code = str(error_code or "").strip().upper()
    if code == "TOOL_NOT_REGISTERED":
        return 404
    if code == "TIMEOUT" or code.endswith("_TIMEOUT"):
        return 504
    if code.endswith("_UNAVAILABLE") or code in ("SERVICE_UNAVAILABLE", "PIPE_UNAVAILABLE"):
        return 503
    if code in ("FUNCTION_NOT_FOUND", "RUN_ERROR", "PIPE_ERROR", "BRIDGE_ERROR", "DOWNSTREAM_ERROR"):
        return 502
    if (
        code.startswith("INVALID_")
        or code.startswith("MISSING_")
        or code in ("BAD_REQUEST", "VALIDATION_ERROR", "SCHEMA_VALIDATION_FAILED")
    ):
        return 400
    return 422


def _tool_http_response(result):
    """生成 `/api/tool` 外层响应，同时原样保留内部工具结果。"""
    failure = _tool_failure_node(result)
    if failure is None:
        return 200, {"status": "success", "result": result}
    error_code = str(failure.get("error_code") or "").strip() or "TOOL_EXECUTION_FAILED"
    payload = {
        "status": "error",
        "error_code": error_code,
        "message": _first_tool_message(failure, result),
        "result": result,
    }
    return _tool_error_http_status(error_code), payload

def _get_runtime_base_dir():
    for candidate in (
        os.environ.get("KMAI_RUNTIME_DIR", ""),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "KmAI"),
        os.path.join(os.environ.get("APPDATA", ""), "KmAI"),
        os.path.join(tempfile.gettempdir(), "KmAI"),
    ):
        candidate = _expand_environment_path(candidate).strip()
        if _is_usable_absolute_path(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(tempfile.gettempdir(), "KmAI"))


def _get_process_route_home_dir():
    candidates = [
        os.environ.get("USERPROFILE", ""),
        (os.environ.get("HOMEDRIVE", "") + os.environ.get("HOMEPATH", "")),
        os.environ.get("HOME", ""),
        os.path.expanduser("~"),
    ]
    for candidate in candidates:
        candidate = _expand_environment_path(candidate).strip()
        if _is_usable_absolute_path(candidate):
            return os.path.abspath(candidate)
    return _get_runtime_base_dir()


def _get_process_route_data_dir():
    return os.path.join(_get_process_route_home_dir(), "3dmps-path-data")


def _get_process_route_output_path():
    return os.path.join(_get_process_route_data_dir(), "output.json")


def _get_process_route_input_path():
    return os.path.join(_get_process_route_data_dir(), "input.json")


PROCESS_ROUTE_DATA_DIR = _get_process_route_data_dir()
PROCESS_ROUTE_INPUT_PATH = _get_process_route_input_path()
PROCESS_ROUTE_OUTPUT_PATH = _get_process_route_output_path()
PROCESS_ROUTE_RUNS_DIR = os.path.join(PROCESS_ROUTE_DATA_DIR, "runs")


def _safe_process_route_trace_id(value):
    trace_id = str(value or "").strip()
    if not trace_id:
        return ""
    safe_chars = []
    for char in trace_id:
        if char.isalnum() or char in ("-", "_", "."):
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    safe_trace_id = "".join(safe_chars).strip("._")
    return safe_trace_id[:160]


def _process_route_run_path(trace_id):
    safe_trace_id = _safe_process_route_trace_id(trace_id)
    if not safe_trace_id:
        return ""
    return os.path.join(PROCESS_ROUTE_RUNS_DIR, safe_trace_id + ".json")


def _normalize_process_route_input_payload(payload):
    if isinstance(payload, list):
        return {"input_json": copy.deepcopy(payload)}
    if not isinstance(payload, dict):
        return {}

    normalized = copy.deepcopy(payload)
    manual_defaults = normalized.get("manual_defaults")
    if not isinstance(manual_defaults, dict):
        for alias in ("manual", u"????"):
            candidate = normalized.get(alias)
            if isinstance(candidate, dict):
                normalized["manual_defaults"] = copy.deepcopy(candidate)
                break
    return normalized


def _read_process_route_input_file():
    path = PROCESS_ROUTE_INPUT_PATH
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_payload = json.load(handle)
    except Exception:
        return {}

    payload = _normalize_process_route_input_payload(raw_payload)
    if not payload:
        return {}

    if not isinstance(payload.get("input_json"), list) or not payload.get("input_json"):
        return {}

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = time.time()

    # 3DMPS 有时只落盘 input.json，不走 /input/push；这里给轮询接口补齐元数据。
    base_name = os.path.basename(path)
    payload.setdefault("source", "file")
    payload.setdefault("input_file", base_name)
    payload.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime(mtime)))
    payload.setdefault("trace_id", "%s-%d" % (base_name, int(mtime * 1000)))
    return payload


class ProcessRouteState(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._input = {}
        self._result = {}

    def set_input(self, value):
        with self._lock:
            self._input = copy.deepcopy(value) if isinstance(value, dict) else {}

    def set_result(self, value):
        result = copy.deepcopy(value) if isinstance(value, dict) else {}
        with self._lock:
            self._result = result
        trace_id = result.get("trace_id") if isinstance(result, dict) else ""
        run_path = _process_route_run_path(trace_id)
        if not run_path:
            return
        try:
            run_dir = os.path.dirname(run_path)
            if not os.path.isdir(run_dir):
                os.makedirs(run_dir)
            # 按 trace_id 留存历史结果，避免后续提交误用最新内存结果。
            with open(run_path, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_input(self):
        with self._lock:
            if self._input:
                return copy.deepcopy(self._input)
        return _read_process_route_input_file()

    def get_result(self, trace_id=None):
        if trace_id:
            run_path = _process_route_run_path(trace_id)
            if run_path and os.path.isfile(run_path):
                try:
                    with open(run_path, "r", encoding="utf-8") as handle:
                        result = json.load(handle)
                    if isinstance(result, dict):
                        return copy.deepcopy(result)
                except Exception:
                    return {}
            return {}
        with self._lock:
            return copy.deepcopy(self._result)

    def snapshot(self):
        with self._lock:
            return {
                "input": copy.deepcopy(self._input),
                "result": copy.deepcopy(self._result),
            }


PROCESS_ROUTE_STATE = ProcessRouteState()


def _decode_feature_template_bytes(data):
    for encoding in ("utf-8-sig", "gb18030", "gb2312", "gbk"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8"


def _feature_template_fallback_path():
    return os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "skills", "kmsoft-group-template", "assets", "FeatureTemplate.xml"
    ))


def _append_unique(values, value):
    if value and value not in values:
        values.append(value)


def _parse_feature_template_xml(xml_text, source_path):
    root = ET.fromstring(xml_text)
    tree = []
    flat = []
    leaf_names = []

    def parse_item(item):
        name = (item.get("name") or "").strip()
        if not name:
            return None
        _append_unique(flat, name)
        children = []
        for child in list(item):
            if child.tag == "Item":
                child_node = parse_item(child)
                if child_node:
                    children.append(child_node)
        node = {"name": name, "children": children}
        if children:
            for child_node in children:
                for leaf_name in _collect_feature_leaf_names([child_node]):
                    _append_unique(leaf_names, leaf_name)
        else:
            _append_unique(leaf_names, name)
        return node

    for item in list(root):
        if item.tag != "Item":
            continue
        node = parse_item(item)
        if node:
            tree.append(node)

    return {
        "tree": tree,
        "flat": flat,
        "leafNames": leaf_names,
        "sourcePath": source_path,
    }


def _collect_feature_leaf_names(nodes):
    names = []

    def walk(node):
        children = node.get("children") if isinstance(node, dict) else None
        name = (node.get("name") if isinstance(node, dict) else "") or ""
        if children:
            for child in children:
                walk(child)
        else:
            _append_unique(names, name)

    for node in nodes or []:
        walk(node)
    return names


def _read_feature_template_catalog(path=None):
    candidates = []
    if path:
        candidates.append(path)
    else:
        candidates.append(getattr(agent_config, "FEATURE_TEMPLATE_FILE", ""))
        candidates.append(_feature_template_fallback_path())

    last_error = None
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = os.path.abspath(candidate)
        if not os.path.isfile(candidate_path):
            continue
        try:
            with open(candidate_path, "rb") as handle:
                text, _encoding = _decode_feature_template_bytes(handle.read())
            return _parse_feature_template_xml(text, candidate_path)
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise IOError("FeatureTemplate.xml not found")


def _simplify_route_rows_for_output(route_rows):
    if not isinstance(route_rows, list):
        return route_rows

    simple_rows = []
    for process in route_rows:
        if not isinstance(process, dict):
            continue

        steps_raw = process.get("steps")
        if not isinstance(steps_raw, list):
            steps_raw = []

        simple_steps = []
        for step in steps_raw:
            if not isinstance(step, dict):
                continue

            candidates = step.get("candidates")
            if not isinstance(candidates, dict):
                candidates = {}

            candidate_details = step.get("candidate_details")
            if not isinstance(candidate_details, list):
                candidate_details = []

            is_last = False
            for detail in candidate_details:
                if not isinstance(detail, dict):
                    continue
                feature_flags = detail.get("feature_flags")
                if not isinstance(feature_flags, list):
                    continue
                if any(
                    isinstance(flag, dict) and bool(flag.get("is_last_process_for_feature"))
                    for flag in feature_flags
                ):
                    is_last = True
                    break

            simple_steps.append({
                "step_name": str(step.get("step_name", "")),
                "candidates": candidates,
                "is_last": is_last,
            })

        technical_requirements = process.get("technical_requirements")
        if not isinstance(technical_requirements, list):
            technical_requirements = []

        simple_rows.append({
            "process_name": str(process.get("process_name", "")),
            "process_type": str(process.get("process_type", "")),
            "precision": str(process.get("precision", "")),
            "technical_requirements": technical_requirements,
            "steps": simple_steps,
        })

    return simple_rows


def current_index_html():
    return build_index_html(agent_config._is_llm_config_enabled(agent_config.CONFIG), api_token=API_AUTH_TOKEN)


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "KmMpsAgent/0.2"

    def do_OPTIONS(self):
        if not self._validate_api_request(require_token=False):
            return
        self._send_empty(204)

    def do_GET(self):
        if self.path == "/api/startup-ping":
            self._handle_startup_ping()
            return
        if not self._validate_api_request():
            return
        if self.path in ("/", "/index.html"):
            self._send_bytes(200, current_index_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path.startswith("/similar-assets/"):
            self._serve_similar_asset()
            return
        if self.path.startswith("/assets/"):
            self._serve_static_asset()
            return
        if self.path.startswith("/api/similar-parts/models/"):
            self._handle_get_similar_model()
            return
        if self.path == "/api/similar-parts/index/status":
            try:
                result = SIMILAR_PARTS.feature_index_status()
                self._send_json(200, {"status": "success", "result": result})
            except SimilarPartsError as exc:
                self._send_similar_parts_error(exc)
            except Exception:
                self._send_similar_parts_error(SimilarPartsError(
                    "FEATURE_INDEX_BUILD_FAILED", "特征索引检查失败，请重试", 503
                ))
            return
        if self.path == "/api/health":
            health = {
                "status": "ok",
                "pipe": PIPE_NAME,
                "pipe_available": getattr(AGENT.pipe, "is_available", lambda: False)(),
                "llm_enabled": agent_config._is_llm_config_enabled(agent_config.CONFIG),
                "llm": agent_config._public_llm_config(),
                "kmrag": agent_config._public_kmrag_config(),
                "python": {
                    "executable": sys.executable,
                    "version": "%d.%d.%d" % sys.version_info[:3],
                    "version_info": list(sys.version_info[:3]),
                },
                "km3dmps": MiniAgent.get_km3dmps_runtime_diagnostics(),
                "skills": get_skill_runtime_diagnostics(),
            }
            self._send_json(200, health)
            return
        if self.path == "/api/config/llm":
            self._send_json(200, {"status": "success", "config": agent_config._public_llm_config()})
            return
        if self.path == "/api/agents":
            self._send_json(200, {"status": "success", "agents": list_agent_summaries()})
            return
        if self.path == "/api/process-route/input/latest":
            self._send_json(200, {"status": "success", "result": PROCESS_ROUTE_STATE.get_input()})
            return
        if self.path == "/api/process-route/result/latest":
            self._send_json(200, {"status": "success", "result": PROCESS_ROUTE_STATE.get_result()})
            return
        if self.path.startswith("/api/template/xml"):
            self._handle_get_template_xml()
            return
        if self.path == "/api/feature-template":
            self._handle_get_feature_template()
            return
        self._send_json(404, {"status": "error", "message": "not found"})

    def _send_similar_parts_error(self, exc):
        payload = {
            "status": "error",
            "error_code": exc.code,
            "message": exc.message,
        }
        if getattr(exc, "details", None):
            payload["result"] = dict(exc.details)
        self._send_json(exc.http_status, payload)

    def _handle_get_similar_model(self):
        prefix = "/api/similar-parts/models/"
        model_name = self.path.split("?", 1)[0][len(prefix):]
        if not model_name.lower().endswith(".glb"):
            self._send_json(404, {"status": "error", "error_code": "MODEL_NOT_FOUND", "message": "模型不存在或已过期"})
            return
        model_id = model_name[:-4]
        try:
            glb, _metadata = SIMILAR_PARTS.get_model(model_id)
            self._send_bytes(200, glb, "model/gltf-binary")
        except SimilarPartsError as exc:
            self._send_similar_parts_error(exc)

    def _serve_similar_asset(self):
        prefix = "/similar-assets/"
        rel = urllib_unquote(self.path.split("?", 1)[0][len(prefix):])
        if ".." in rel.split("/"):
            self._send_json(403, {"status": "error", "message": "forbidden"})
            return
        vendor_root = os.path.abspath(os.path.join(
            agent_config.CONFIG.get("similar_parts_step_viewer_root", ""), "web", "vendor"
        ))
        target = os.path.abspath(os.path.normpath(os.path.join(vendor_root, rel)))
        try:
            inside = os.path.commonpath([vendor_root, target]) == vendor_root
        except Exception:
            inside = False
        if not inside:
            self._send_json(403, {"status": "error", "message": "forbidden"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"status": "error", "message": "asset not found"})
            return
        try:
            with open(target, "rb") as handle:
                data = handle.read()
        except OSError:
            self._send_json(500, {"status": "error", "message": "asset unavailable"})
            return
        if os.path.splitext(target)[1].lower() == ".js" and rel.startswith("three/examples/jsm/"):
            # Older embedded CEF builds do not resolve bare "three" specifiers
            # inside dynamically imported addon modules. Keep the vendored files
            # immutable and rewrite only this local response to an absolute URL.
            data = data.replace(b"from 'three'", b"from '/similar-assets/three/build/three.module.js'")
            data = data.replace(b'from "three"', b'from "/similar-assets/three/build/three.module.js"')
        ext = os.path.splitext(target)[1].lower()
        content_type = {
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".md": "text/plain; charset=utf-8",
        }.get(ext, "text/plain; charset=utf-8")
        self._send_bytes(200, data, content_type)

    def _handle_startup_ping(self):
        if not self._is_local_request():
            self._send_json(403, {
                "status": "error",
                "error_code": "LOCAL_ONLY",
                "message": "startup ping is only available from localhost",
            })
            return
        self._send_json(200, {
            "status": "ok",
            "app": "KmAI",
            "kind": "agent",
        })

    def _is_local_request(self):
        try:
            host = self.client_address[0]
        except Exception:
            return False
        return host in ("127.0.0.1", "::1", "localhost")

    def _serve_static_asset(self):
        """提供 /assets/* 下的静态文件(目前是 modules/*.js)。

        JS 模块化后,前端入口通过 <script type="module" src="/assets/modules/entry.js">
        加载,需要服务端把这个路径映射到 frontend/assets/modules/entry.js。
        仅在 _ASSETS_DIR 内部解析,防止 ../ 等越权访问。
        """
        # 把 url 路径里的 /assets/ 前缀剥掉,得到相对 _ASSETS_DIR 的子路径
        rel = self.path[len("/assets/"):]
        # URL 解码(%xx → 字符)后用 ntpath.posix 把 / 当作分隔符(因为是 HTTP 路径)
        rel = urllib_unquote(rel)
        # 拒绝任何含 .. 的相对路径,防止目录穿越
        if ".." in rel.split("/"):
            self._send_json(403, {"status": "error", "message": "forbidden"})
            return
        target = os.path.normpath(os.path.join(_ASSETS_DIR, rel))
        # 最终结果必须仍然在 _ASSETS_DIR 里
        if os.path.commonpath([_ASSETS_DIR, target]) != _ASSETS_DIR:
            self._send_json(403, {"status": "error", "message": "forbidden"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"status": "error", "message": "asset not found"})
            return
        try:
            with open(target, "rb") as fp:
                data = fp.read()
        except OSError as exc:
            self._send_json(500, {"status": "error", "message": str(exc)})
            return
        ext = os.path.splitext(target)[1].lower()
        mime = {
            ".js": "application/javascript; charset=utf-8",
            ".mjs": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        self._send_bytes(200, data, mime)

    def _handle_get_template_xml(self):
        """返回指定模板的 XML 内容，供前端编辑器加载。"""
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            template_id = (params.get("templateId") or [""])[0]
            filename = (params.get("filename") or [""])[0]
            if not template_id:
                self._send_json(400, {"status": "error", "message": "missing templateId"})
                return
            # 复用 confirm skill：它已支持给定 templateId 返回完整 XML
            # （无需新增 get_xml action，避免脚本/注册表两边都要改）
            runner = SKILL_RUNNERS.get("kmsoft_group_template_confirm")
            if runner is None:
                self._send_json(501, {"status": "error",
                    "message": "kmsoft_group_template_confirm skill not available"})
                return
            result = runner.run({"templateId": template_id})
            self._send_json(200, {"status": "success", "result": result})
        except Exception as exc:
            self._send_json(500, {"status": "error", "message": str(exc)})

    def _handle_get_feature_template(self):
        """返回 FeatureTemplate.xml 的树形特征目录，供特征选择下拉使用。"""
        try:
            result = _read_feature_template_catalog()
            self._send_json(200, {"status": "success", "result": result})
        except Exception as exc:
            self._send_json(500, {"status": "error", "message": str(exc)})

    def _handle_post_template_save(self, payload):
        """保存用户编辑后的 XML 到 3DMPS 安装目录。"""
        try:
            filename = payload.get("filename", "")
            xml = payload.get("xml", "")
            if not filename:
                return {"status": "error", "message": "missing filename"}
            if not xml:
                return {"status": "error", "message": "missing xml content"}
            safe_filename = os.path.basename(filename)
            if safe_filename != filename or not safe_filename:
                return {"status": "error", "message": "invalid filename: " + filename}
            target_path = os.path.abspath(os.path.join(agent_config.GROUP_TEMPLATE_SAVE_DIR, safe_filename))
            save_dir = os.path.abspath(agent_config.GROUP_TEMPLATE_SAVE_DIR)
            if os.path.commonpath([save_dir, target_path]) != save_dir:
                return {"status": "error", "message": "path traversal detected: " + filename}
            if not os.path.isdir(agent_config.GROUP_TEMPLATE_SAVE_DIR):
                os.makedirs(agent_config.GROUP_TEMPLATE_SAVE_DIR)
            existed_before = os.path.exists(target_path)
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
            return {"status": "error", "message": str(exc)}

    def do_POST(self):
        try:
            if not self._validate_api_request():
                return
            try:
                payload = self._read_json()
            except RequestBodyTooLarge as exc:
                self._send_json(413, {
                    "status": "error",
                    "error_code": "PAYLOAD_TOO_LARGE",
                    "message": "request body too large",
                    "content_length": exc.length,
                    "max_bytes": exc.max_bytes,
                })
                return
            except InvalidRequestBody as exc:
                self._send_json(400, {
                    "status": "error",
                    "error_code": exc.error_code,
                    "message": exc.public_message,
                })
                return

            if self.path == "/api/similar-parts/upload":
                filename = payload.get("filename", "")
                encoded = payload.get("contentBase64", "")
                if not isinstance(encoded, str):
                    self._send_json(400, {"status": "error", "error_code": "INVALID_BASE64", "message": "XML 文件内容编码无效"})
                    return
                try:
                    content = base64.b64decode(encoded.encode("ascii"), validate=True)
                except (ValueError, UnicodeEncodeError, binascii.Error):
                    self._send_json(400, {"status": "error", "error_code": "INVALID_BASE64", "message": "XML 文件内容编码无效"})
                    return
                try:
                    result = SIMILAR_PARTS.upload_xml(filename, content)
                    self._send_json(200, {"status": "success", "result": result})
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                return

            if self.path == "/api/similar-parts/current":
                try:
                    result = SIMILAR_PARTS.load_current_part()
                    # 不向浏览器暴露本机绝对路径，只返回展示所需的文件名和 uploadId。
                    result = dict(result or {})
                    result.pop("stepPath", None)
                    self._send_json(200, {"status": "success", "result": result})
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                return

            if self.path == "/api/similar-parts/index/ensure":
                try:
                    result = SIMILAR_PARTS.ensure_feature_index()
                    status = 202 if result.get("state") == "building" else 200
                    self._send_json(status, {"status": "success", "result": result})
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                except Exception:
                    self._send_similar_parts_error(SimilarPartsError(
                        "FEATURE_INDEX_BUILD_FAILED", "特征索引准备失败，请重试", 503
                    ))
                return

            if self.path == "/api/similar-parts/query":
                try:
                    result = SIMILAR_PARTS.query(payload.get("uploadId", ""), payload.get("topK"))
                    self._send_json(200, {"status": "success", "result": result})
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                return

            if self.path == "/api/similar-parts/template":
                try:
                    result = SIMILAR_PARTS.get_candidate_template(
                        payload.get("uploadId", ""), payload.get("candidateId", "")
                    )
                    self._send_json(200, {"status": "success", "result": result})
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                return

            if self.path == "/api/similar-parts/apply-template":
                try:
                    prepared = SIMILAR_PARTS.prepare_template(
                        payload.get("uploadId", ""),
                        payload.get("candidateId", ""),
                        agent_config.GROUP_TEMPLATE_SAVE_DIR,
                        payload.get("editedTemplate"),
                    )
                    tool_result = AGENT.tool(
                        "apply_group_template",
                        {"template_name": prepared["templateName"]},
                        timeout=120,
                    )
                    http_status, tool_payload = _tool_http_response(tool_result)
                    if http_status != 200:
                        self._send_json(http_status, tool_payload)
                        return
                    self._send_json(200, {
                        "status": "success",
                        "template": prepared,
                        "result": tool_result,
                    })
                except SimilarPartsError as exc:
                    self._send_similar_parts_error(exc)
                return

            if self.path == "/api/tool":
                function_name = payload.get("function") or payload.get("function_name")
                if not function_name:
                    self._send_json(400, {
                        "status": "error",
                        "error_code": "MISSING_FUNCTION",
                        "message": "missing function",
                    })
                    return
                try:
                    req_timeout = _parse_tool_timeout(payload.get("timeout"))
                except ValueError:
                    self._send_json(400, {
                        "status": "error",
                        "error_code": "INVALID_TIMEOUT",
                        "message": "timeout must be a number between 1 and 180 seconds",
                    })
                    return
                result = AGENT.tool(function_name, payload.get("params") or {},
                                    timeout=req_timeout)
                http_status, response_payload = _tool_http_response(result)
                self._send_json(http_status, response_payload)
                return

            if self.path == "/api/chat":
                agent_id = payload.get("agent_id", DEFAULT_AGENT_ID)
                _profile, agent_found = resolve_agent_profile(agent_id)
                if not agent_found:
                    requested_agent_id = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
                    self._send_json(400, {
                        "status": "error",
                        "error_code": "UNKNOWN_AGENT",
                        "message": u"未知智能体：%s" % requested_agent_id,
                        "agent_id": requested_agent_id,
                    })
                    return
                result = AGENT.chat(
                    payload.get("message", ""),
                    session_id=payload.get("session_id", "default"),
                    agent_id=agent_id,
                )
                result["status"] = result.get("status", "success")
                self._send_json(200, result)
                return

            if self.path == "/api/chat/stream":
                message = payload.get("message", "")
                agent_id = payload.get("agent_id", DEFAULT_AGENT_ID)
                _profile, agent_found = resolve_agent_profile(agent_id)
                if not agent_found:
                    requested_agent_id = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
                    self._send_json(400, {
                        "status": "error",
                        "error_code": "UNKNOWN_AGENT",
                        "message": u"未知智能体：%s" % requested_agent_id,
                        "agent_id": requested_agent_id,
                    })
                    return
                self._send_stream(
                    message,
                    payload.get("session_id", "default"),
                    agent_id,
                )
                return

            if self.path == "/api/process-route/input/push":
                inbox_payload = _normalize_process_route_input_payload(payload or {})
                if not inbox_payload.get("created_at"):
                    ts = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime())
                    inbox_payload["created_at"] = ts
                if not inbox_payload.get("trace_id"):
                    base = inbox_payload.get("input_file") or "process-route"
                    inbox_payload["trace_id"] = "%s-%d" % (os.path.basename(base), int(time.time() * 1000))
                PROCESS_ROUTE_STATE.set_input(inbox_payload)
                self._send_json(200, {"status": "success", "received": True})
                return

            if self.path == "/api/process-route/generate":
                result = self._handle_generate_process_route(payload)
                if result.get("status") == "success":
                    PROCESS_ROUTE_STATE.set_result(result.get("result") or {})
                self._send_json(200, result)
                return

            if self.path == "/api/process-route/generate-technical-requirements":
                result = self._handle_generate_technical_requirements(payload)
                if result.get("status") == "success":
                    PROCESS_ROUTE_STATE.set_result(result.get("result") or {})
                self._send_json(200, result)
                return

            if self.path == "/api/process-route/export":
                result = self._handle_export_process_route(payload)
                self._send_json(200, result)
                return

            if self.path == "/api/process-route/submit":
                result = self._handle_submit_process_route(payload)
                self._send_json(200, result)
                return

            if self.path == "/api/template/save":
                result = self._handle_post_template_save(payload)
                self._send_json(200, result)
                return

            if self.path == "/api/config/llm":
                try:
                    config = agent_config._save_llm_config(payload)
                    AGENT.reload_llm()
                    self._send_json(200, {"status": "success", "config": config})
                except Exception as exc:
                    self._send_json(400, {"status": "error", "message": str(exc)})
                return

            self._send_json(404, {"status": "error", "message": "not found"})
        except Exception as exc:
            self._send_json(500, {
                "status": "error",
                "message": str(exc),
            })

    def _handle_generate_process_route(self, payload):
        try:
            latest = PROCESS_ROUTE_STATE.get_input()
            cad_input = latest.get("input_json")
            if not isinstance(cad_input, list):
                cad_input = payload.get("cad_input")
            if not isinstance(cad_input, list) or not cad_input:
                return {"status": "error", "message": "missing cad_input"}

            manual = payload.get("manual") or {}
            if not isinstance(manual, dict):
                manual = {}

            runner = SKILL_RUNNERS.get("process_route_generate")
            if runner is None:
                return {"status": "error", "message": "process_route_generate skill not available"}

            request_payload = {
                "cad_input": cad_input,
                "manual": manual,
            }
            skill_result = runner.run(request_payload)
            if not isinstance(skill_result, dict):
                return {"status": "error", "message": "process_route_generate returned invalid payload"}
            if not skill_result.get("ok", False) and skill_result.get("status") == "error":
                return {"status": "error", "message": skill_result.get("error") or skill_result.get("message") or "route generation failed"}

            trace_id = latest.get("trace_id") if isinstance(latest, dict) else ""
            result = dict(skill_result)
            result["trace_id"] = trace_id
            result["input_source"] = latest.get("source") if isinstance(latest, dict) else ""
            result["input_file"] = latest.get("input_file") if isinstance(latest, dict) else ""
            return {"status": "success", "result": result}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _get_latest_process_route_rows(self, trace_id=None):
        result = PROCESS_ROUTE_STATE.get_result(trace_id)
        route_rows = result.get("route")
        if isinstance(route_rows, list) and route_rows:
            return route_rows
        return []

    def _normalize_manual_context_for_technical_requirements(self, manual):
        if not isinstance(manual, dict):
            manual = {}
        normalized = {
            "material_grade": manual.get("material_grade") or "",
            "part_type": manual.get("part_type") or "",
            "heat_treatment": manual.get("heat_treatment") or "",
            "surface_treatments": manual.get("surface_treatments") if isinstance(manual.get("surface_treatments"), list) else [],
            "inspection_items": manual.get("inspection_items") if isinstance(manual.get("inspection_items"), list) else [],
            "marking_methods": manual.get("marking_methods") if isinstance(manual.get("marking_methods"), list) else [],
            "special_process_flags": manual.get("special_process_flags") if isinstance(manual.get("special_process_flags"), dict) else {},
        }
        return normalized

    def _handle_generate_technical_requirements(self, payload):
        try:
            state = PROCESS_ROUTE_STATE.snapshot()
            latest = state.get("input") if isinstance(state.get("input"), dict) else {}
            current_result = state.get("result") if isinstance(state.get("result"), dict) else {}

            matched_route = current_result.get("matched_route")
            route_rows = current_result.get("route")
            if not isinstance(matched_route, (dict, list)):
                if isinstance(route_rows, list) and route_rows:
                    matched_route = route_rows
                else:
                    return {"status": "error", "message": "missing process route result"}

            cad_input = latest.get("input_json")
            if not isinstance(cad_input, list):
                cad_input = payload.get("cad_input")
            if not isinstance(cad_input, list):
                cad_input = []

            manual = payload.get("manual")
            if not isinstance(manual, dict):
                manual = current_result.get("manual") if isinstance(current_result.get("manual"), dict) else {}
            manual = self._normalize_manual_context_for_technical_requirements(manual)

            runner = SKILL_RUNNERS.get("technical_requirements_generate")
            if runner is None:
                return {"status": "error", "message": "technical_requirements_generate skill not available"}

            request_payload = {
                "route_input": matched_route,
                "cad_input": cad_input,
                "manual": manual,
            }
            if isinstance(current_result.get("part_context"), dict):
                request_payload["upstream_part_context"] = current_result.get("part_context")

            skill_result = runner.run(request_payload)
            if not isinstance(skill_result, dict):
                return {"status": "error", "message": "technical_requirements_generate returned invalid payload"}
            if not skill_result.get("ok", False) and skill_result.get("status") == "error":
                return {"status": "error", "message": skill_result.get("error") or skill_result.get("message") or "technical requirements generation failed"}

            result = dict(current_result)
            result["manual"] = manual
            if isinstance(skill_result.get("matched_route"), (dict, list)):
                result["matched_route"] = skill_result.get("matched_route")
            if isinstance(skill_result.get("route"), list):
                result["route"] = skill_result.get("route")
            if isinstance(skill_result.get("part_context"), dict):
                result["part_context"] = skill_result.get("part_context")
            result["technical_requirements_generated"] = True
            latest_trace_id = latest.get("trace_id") if isinstance(latest, dict) else ""
            result["trace_id"] = latest_trace_id or result.get("trace_id", "")
            result["input_source"] = latest.get("source") if isinstance(latest, dict) else result.get("input_source", "")
            result["input_file"] = latest.get("input_file") if isinstance(latest, dict) else result.get("input_file", "")
            return {"status": "success", "result": result}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _handle_export_process_route(self, payload):
        try:
            trace_id = payload.get("trace_id") if isinstance(payload, dict) else ""
            result = PROCESS_ROUTE_STATE.get_result(trace_id)
            export_payload = result.get("route")
            export_kind = "route"
            if isinstance(export_payload, list):
                export_payload = _simplify_route_rows_for_output(export_payload)
                export_kind = "route_simple"
            if not isinstance(export_payload, list):
                export_payload = result.get("matched_route")
                export_kind = "matched_route"
            if not isinstance(export_payload, (dict, list)):
                return {"status": "error", "message": "missing process route result"}

            route_rows = self._get_latest_process_route_rows(trace_id)

            process_route_data_dir = _get_process_route_data_dir()
            save_path = _get_process_route_output_path()
            if not os.path.isdir(process_route_data_dir):
                os.makedirs(process_route_data_dir)

            body = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
            with open(save_path, "wb") as fp:
                fp.write(body)

            result = {
                "saved_path": save_path,
                "bytes": len(body),
                "route_count": len(route_rows),
                "export_kind": export_kind,
            }
            return {"status": "success", "result": result}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _handle_submit_process_route(self, payload):
        try:
            trace_id = payload.get("trace_id") if isinstance(payload, dict) else ""
            if not trace_id:
                return {
                    "status": "error",
                    "error_code": "PROCESS_ROUTE_TRACE_REQUIRED",
                    "message": "process route trace_id is required",
                }
            result = PROCESS_ROUTE_STATE.get_result(trace_id)
            if not result or result.get("trace_id") != trace_id:
                return {
                    "status": "error",
                    "error_code": "PROCESS_ROUTE_TRACE_MISMATCH",
                    "message": "process route trace_id does not match a generated result",
                }
            current_result = PROCESS_ROUTE_STATE.get_result()
            current_trace_id = current_result.get("trace_id") if isinstance(current_result, dict) else ""
            if current_trace_id and current_trace_id != trace_id:
                return {
                    "status": "error",
                    "error_code": "PROCESS_ROUTE_TRACE_MISMATCH",
                    "message": "process route trace_id does not match the current generated result",
                }
            export_result = self._handle_export_process_route(payload)
            route_rows = self._get_latest_process_route_rows(trace_id)
            if export_result.get("status") != "success":
                return export_result
            if not route_rows:
                return {"status": "error", "message": "missing process route result"}

            req_timeout = payload.get("timeout")
            # 3DMPS 主程序当前没有暴露 submit_ai_process_route_output；
            # 提交结果的真实落点是 do_ai_process_route(cmd_id=2)，它会进入 MainFrm.cpp
            # 里的 m_ProcessRouteFlag == 2 分支去读取同目录 output.json。
            submit_result = AGENT.tool(
                "get_ai_process_route_input",
                {"cmd_id": 2},
                timeout=req_timeout,
            )

            result = {
                "export_result": export_result.get("result") or {},
                "submit_result": submit_result,
                "route_count": len(route_rows),
            }
            if isinstance(submit_result, dict) and submit_result.get("status") == "error":
                message = submit_result.get("message") or "submit process route failed"
                return {"status": "error", "message": message, "result": result}
            return {"status": "success", "result": result}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _send_stream(self, message, session_id="default", agent_id=DEFAULT_AGENT_ID):
        """SSE 流式响应。

        stream_chat 产出的每个事件（dict）都原样序列化为 JSON 推给前端，
        事件类型见 stream_chat 文档字符串。
        """
        self.send_response(200)
        self._send_common_headers("text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            for event in AGENT.stream_chat(message, session_id=session_id, agent_id=agent_id):
                # 兼容旧实现：万一以后某处 yield 字符串，自动包成 content 事件
                if isinstance(event, str):
                    event = {"type": "content", "text": event}
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as exc:
            err = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            try:
                self.wfile.write(("data: " + err + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass
        finally:
            self.close_connection = True

    def log_message(self, fmt, *args):
        try:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        except Exception:
            pass

    def _read_json(self):
        raw_length = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            raise InvalidRequestBody("INVALID_CONTENT_LENGTH", "invalid Content-Length")
        if length < 0:
            # Content-Length 只能是非负整数，拒绝负数以避免 read(-1) 阻塞读取。
            raise InvalidRequestBody("INVALID_CONTENT_LENGTH", "invalid Content-Length")
        max_length = self._max_request_body_bytes()
        if length > max_length:
            raise RequestBodyTooLarge(length, max_length)
        body = self.rfile.read(length) if length else b"{}"
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8-sig"))
        except (TypeError, ValueError, UnicodeDecodeError):
            raise InvalidRequestBody("INVALID_JSON", "invalid JSON request body")

    def _max_request_body_bytes(self):
        if self.path == "/api/process-route/input/push":
            return PROCESS_ROUTE_INPUT_MAX_REQUEST_BODY_BYTES
        if self.path == "/api/similar-parts/upload":
            return SIMILAR_PARTS_UPLOAD_MAX_REQUEST_BODY_BYTES
        return DEFAULT_MAX_REQUEST_BODY_BYTES

    def _get_request_origin(self):
        return self.headers.get("Origin", "")

    def _validate_api_request(self, require_token=True):
        if not _is_api_auth_required(getattr(self, "command", ""), self.path):
            return True
        origin = self._get_request_origin()
        server_port = None
        try:
            server_port = self.server.server_address[1]
        except Exception:
            pass
        if not _is_allowed_origin(origin, server_port=server_port):
            self._discard_small_rejected_body()
            self._send_json(403, {
                "status": "error",
                "error_code": "ORIGIN_FORBIDDEN",
                "message": "origin is not allowed",
            })
            return False
        if require_token and API_AUTH_TOKEN:
            request_token = self.headers.get("X-KmAI-Token", "")
            if not hmac.compare_digest(str(request_token), str(API_AUTH_TOKEN)):
                self._discard_small_rejected_body()
                self._send_json(403, {
                    "status": "error",
                    "error_code": "AUTH_REQUIRED",
                    "message": "missing or invalid API token",
                })
                return False
        return True

    def _discard_small_rejected_body(self):
        if getattr(self, "command", "") != "POST":
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            return
        if length <= 0:
            return
        if length > DEFAULT_MAX_REQUEST_BODY_BYTES:
            self.close_connection = True
            return
        # 未授权请求只丢弃字节、不解析 JSON，避免客户端收不到结构化 403。
        self.rfile.read(length)

    def _send_empty(self, status):
        self.send_response(status)
        self._send_common_headers("text/plain; charset=utf-8")
        self.end_headers()

    def _send_json(self, status, data):
        self._send_bytes(status, _json_bytes(data), "application/json; charset=utf-8")

    def _send_bytes(self, status, data, content_type):
        self.send_response(status)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_common_headers(self, content_type):
        self.send_header("Content-Type", content_type)
        origin = self._get_request_origin()
        server_port = None
        try:
            server_port = self.server.server_address[1]
        except Exception:
            pass
        if origin and _is_allowed_origin(origin, server_port=server_port):
            self.send_header("Access-Control-Allow-Origin", _normalize_origin(origin))
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-KmAI-Token")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        # 禁用所有缓存（包括 CEF/3DMPS WebView 的内存和磁盘缓存），保证 HTML/JS 改动立即生效
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
