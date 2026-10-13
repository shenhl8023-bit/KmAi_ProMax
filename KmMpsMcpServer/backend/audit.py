# -*- coding: utf-8 -*-
"""工具调用审计日志。

每个工具调用（3DMPS 命名管道 + Skill 子进程 + LLM 驱动）都会记录一行 JSON：
    {
        "ts":              ISO 时间戳
        "tool":            工具名
        "source":          "api_tool" | "llm_chat" | "llm_stream"
        "status":          "ok" | "error" | "timeout" | "not_found"
        "error_code":      可选，结构化错误码（FUNCTION_NOT_FOUND / TIMEOUT / ...）
        "duration_ms":     耗时（毫秒）
        "args_size":       入参 JSON 序列化字节数
        "result_size":     返回值 JSON 序列化字节数（-1 表示不可序列化）
        "error":           可选，异常文本（截断到 200 字符）
    }

为什么用 JSONL：
    - 追加写（高并发下不会冲突）
    - 解析简单：每行一个 JSON，直接 `for line in f: json.loads(line)`
    - 易于 grep / awk 提取

为什么只记 size 不记内容：
    - 中文 args 可能很长（17 KB 见过），写日志会膨胀
    - args 可能含敏感信息（零件描述、文件路径）
    - 调试时看 size + status + duration 通常足够
"""

from __future__ import print_function

import json
import os
import sys
import threading
import time
from datetime import datetime


# 默认日志路径：与 agent_server.out.log / .err.log 同目录
def _expand_environment_path(path):
    value = path or ""
    for _ in range(5):
        user_expanded = os.path.expanduser(value) if value.startswith("~") else value
        expanded = os.path.expandvars(user_expanded)
        if expanded == value:
            break
        value = expanded
    return value


def _default_runtime_dir():
    configured = _expand_environment_path(os.environ.get("KMAI_RUNTIME_DIR", "")).strip()
    if configured and "%" not in configured:
        return os.path.abspath(configured)

    local_app_data = _expand_environment_path(os.environ.get("LOCALAPPDATA", "")).strip()
    if local_app_data and "%" not in local_app_data:
        return os.path.abspath(os.path.join(local_app_data, "KmAI"))

    return os.path.abspath(os.path.join(os.path.expanduser("~"), ".kmai"))


DEFAULT_LOG_PATH = os.path.join(_default_runtime_dir(), "logs", "agent_server.audit.log")


def _safe_json_size(obj):
    """序列化字节数，失败时返回 -1。"""
    if obj is None:
        return 0
    try:
        return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return -1


def _truncate(text, max_len=200):
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= max_len else text[:max_len] + "..."


class AuditLogger(object):
    """线程安全的 JSONL 审计日志写入器。"""

    def __init__(self, path=None):
        self.path = path or DEFAULT_LOG_PATH
        self._lock = threading.Lock()
        # 延迟打开：第一次写入时再创建文件
        self._file = None

    def _ensure_open(self):
        if self._file is not None:
            return
        try:
            # append 模式；不缓冲（每行 flush）
            log_dir = os.path.dirname(os.path.abspath(self.path))
            if log_dir and not os.path.isdir(log_dir):
                os.makedirs(log_dir)
            self._file = open(self.path, "a", encoding="utf-8", buffering=1)
        except OSError as exc:
            sys.stderr.write("[audit] open log failed: %s\n" % exc)
            self._file = None

    def write(self, record):
        """写一条审计记录（dict）。失败不抛异常（审计不应影响主流程）。"""
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            sys.stderr.write("[audit] serialize failed: %s\n" % exc)
            return
        with self._lock:
            self._ensure_open()
            if self._file is None:
                return
            try:
                self._file.write(line + "\n")
            except OSError as exc:
                sys.stderr.write("[audit] write failed: %s\n" % exc)

    def log_call(self, tool, source, start_time, result=None, error=None,
                 args_size=None):
        """高阶 API：根据 result/error 自动推导 status 与 error_code。

        入参:
            tool        工具名
            source      "api_tool" | "llm_chat" | "llm_stream"
            start_time  time.monotonic() 起始时间
            result      工具返回值（dict 或 None）
            error       异常对象（None / Exception）
            args_size   入参序列化字节数（可选；为 None 时不记录）
        """
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "tool": tool,
            "source": source,
            "duration_ms": duration_ms,
        }
        if args_size is not None:
            record["args_size"] = args_size
        if result is not None:
            record["result_size"] = _safe_json_size(result)
            if isinstance(result, dict):
                # 推导 status：优先看显式 status 字段
                if "status" in result:
                    record["status"] = result["status"]
                elif result.get("ok") is True:
                    record["status"] = "ok"
                elif result.get("ok") is False:
                    record["status"] = "error"
                if "error_code" in result:
                    record["error_code"] = result["error_code"]
        if error is not None:
            record["status"] = "error"
            record["error"] = _truncate(repr(error))
        self.write(record)


# 全局单例
AUDIT = AuditLogger()
