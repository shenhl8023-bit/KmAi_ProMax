# -*- coding: utf-8 -*-
"""Skill 聚合器（参考 tools/ 包的模式）。

本模块从 skills/registry.json 读取注册列表，逐项加载同目录下的 <name>.json，
把每个 action 包装为 OpenAI function calling 格式的工具定义，并构造一个
runner 字典供 Agent 调用。

导出四个聚合对象（与 tools/ 保持一致）：
    SKILL_TOOLS         OpenAI function calling 格式的工具定义列表
    SKILL_RUNNERS       tool_name -> SkillRunner 实例 的字典
    SKILL_TIMEOUTS      tool_name -> 超时（秒）的字典
    SKILL_METADATA      tool_name -> 元信息字典（用于调试 / 健康检查）
    get_skill_timeout() 查询工具超时

注意：本模块不调用 SkillRunner.run()，仅注册元信息与构造 runner。
执行发生在 agent_server.py 的 _execute_tool() 中。
"""

from __future__ import print_function

import json
import os
import shutil
import subprocess
import sys

try:
    from .runner import SkillRunner
except ImportError:
    # 允许作为独立脚本被 import
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from runner import SkillRunner


# 聚合顺序：先列具体 skill，最后是 fallback（如果有）
SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SKILLS_DIR, "registry.json")

# 默认超时：未在 action 注册时显式配置的，使用此值
DEFAULT_SKILL_TIMEOUT = 30


def _load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _resolve_skill_dir(skill_name, configured_dir):
    """Resolve skill_dir with a portable fallback for packaged deployments."""
    candidates = []
    if configured_dir:
        if os.path.isabs(configured_dir):
            candidates.append(configured_dir)
        else:
            candidates.append(os.path.normpath(os.path.join(SKILLS_DIR, configured_dir)))
    candidates.append(os.path.join(SKILLS_DIR, skill_name))

    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(candidates[0]) if candidates else ""


def _load_registry():
    """读取 registry.json + 各个 skill JSON，返回 list of skill configs。"""
    if not os.path.exists(REGISTRY_PATH):
        return []
    try:
        registry = _load_json(REGISTRY_PATH)
    except Exception as exc:
        sys.stderr.write("[skills] registry 读取失败: %s\n" % exc)
        return []
    skill_names = registry.get("skills", [])
    skills = []
    for name in skill_names:
        path = os.path.join(SKILLS_DIR, name + ".json")
        if not os.path.exists(path):
            sys.stderr.write("[skills] 注册项缺失: %s\n" % path)
            continue
        try:
            cfg = _load_json(path)
        except Exception as exc:
            sys.stderr.write("[skills] 加载 %s 失败: %s\n" % (path, exc))
            continue
        cfg.setdefault("name", name)
        # 关键：把 action 的 cwd 补全为 skill 所在目录
        skill_dir = _resolve_skill_dir(name, cfg.get("skill_dir"))
        cfg["skill_dir"] = skill_dir
        for action in cfg.get("actions", []):
            if skill_dir and not action.get("cwd"):
                action["cwd"] = skill_dir
        skills.append(cfg)
    return skills


def _build_tool_definition(skill_name, action):
    """把单个 action 包装为 OpenAI function calling 格式。"""
    return {
        "type": "function",
        "function": {
            "name": action["tool_name"],
            "description": u"[Skill: %s] %s" % (skill_name, action.get("description", "")),
            "parameters": action.get("parameters", {"type": "object", "properties": {}}),
        },
    }


def _version_text(version_tuple):
    if not version_tuple:
        return ""
    return "%d.%d" % (version_tuple[0], version_tuple[1])


def _diagnose_runner_runtime(runner):
    min_version = runner.python_min_version
    if runner.command in ("python-auto", "py") and min_version is None:
        min_version = (3, 10)

    info = {
        "command": runner.command,
        "python_min_version": _version_text(min_version),
        "ok": True,
    }
    if runner.command in ("python-auto", "py"):
        try:
            resolved_command = runner._resolve_python_command()
            resolved_version = runner._probe_python_version(resolved_command)
            info["resolved_command"] = resolved_command
            info["resolved_version"] = _version_text(resolved_version)
            info["ok"] = bool(resolved_version and resolved_version >= min_version)
            if not info["ok"]:
                info["error"] = "resolved Python is below required version"
        except Exception as exc:
            info["ok"] = False
            info["error"] = str(exc)
        return info

    info["resolved_command"] = ""
    info["resolved_version"] = ""
    runtime_name = os.path.splitext(os.path.basename(runner.command))[0].lower()
    resolved_command = shutil.which(runner.command)
    if not resolved_command:
        info["ok"] = False
        info["error_code"] = "NODE_NOT_FOUND" if runtime_name == "node" else "RUNTIME_NOT_FOUND"
        info["error"] = "runtime command was not found: %s" % runner.command
        return info

    info["resolved_command"] = os.path.abspath(resolved_command)
    if runtime_name != "node":
        return info

    # Node 是当前核心 Skill 的唯一非 Python 运行时，显式探测版本便于部署诊断。
    try:
        proc = subprocess.Popen(
            [info["resolved_command"], "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout_data, stderr_data = proc.communicate(timeout=10.0)
    except Exception as exc:
        info["ok"] = False
        info["error_code"] = "NODE_VERSION_PROBE_FAILED"
        info["error"] = str(exc)
        return info

    if proc.returncode != 0:
        if isinstance(stderr_data, bytes):
            stderr_text = stderr_data.decode("utf-8", "replace")
        else:
            stderr_text = str(stderr_data or "")
        info["ok"] = False
        info["error_code"] = "NODE_VERSION_PROBE_FAILED"
        info["error"] = "node --version exited with code %d: %s" % (
            proc.returncode,
            stderr_text.strip()[:200],
        )
        return info

    if isinstance(stdout_data, bytes):
        version_text = stdout_data.decode("utf-8", "replace").strip()
    else:
        version_text = str(stdout_data or "").strip()
    version_text = version_text.splitlines()[0].strip() if version_text else ""
    if version_text[:1].lower() == "v":
        version_text = version_text[1:]
    if not version_text:
        info["ok"] = False
        info["error_code"] = "NODE_VERSION_PROBE_FAILED"
        info["error"] = "node --version returned an empty version"
        return info

    info["resolved_version"] = version_text
    return info


def _aggregate():
    """合并所有已注册 skill 的工具定义、runner、超时与元信息。"""
    tools = []
    runners = {}
    timeouts = {}
    metadata = {}
    for skill in _load_registry():
        skill_name = skill.get("name", "")
        for action in skill.get("actions", []):
            tool_name = action.get("tool_name")
            if not tool_name:
                continue
            tools.append(_build_tool_definition(skill_name, action))
            try:
                runners[tool_name] = SkillRunner(action)
            except KeyError as exc:
                sys.stderr.write("[skills] action 配置缺失字段: %s\n" % exc)
                continue
            timeouts[tool_name] = float(action.get("timeout", DEFAULT_SKILL_TIMEOUT))
            metadata[tool_name] = {
                "skill": skill_name,
                "action": action.get("name", ""),
                "command": action.get("command", ""),
                "cwd": action.get("cwd", ""),
            }
    return tools, runners, timeouts, metadata


SKILL_TOOLS, SKILL_RUNNERS, SKILL_TIMEOUTS, SKILL_METADATA = _aggregate()


def get_skill_timeout(tool_name, default=None):
    """查询 Skill 工具的调用超时（秒）。未配置返回 default。"""
    if default is None:
        default = DEFAULT_SKILL_TIMEOUT
    return SKILL_TIMEOUTS.get(tool_name, default)


def get_summary():
    """返回 Skill 集合的统计信息（用于 /api/health 等调试端点）。"""
    return {
        "skills_count": len(_load_registry()),
        "tools_count": len(SKILL_TOOLS),
        "runners_count": len(SKILL_RUNNERS),
        "timeouts_count": len(SKILL_TIMEOUTS),
        "default_timeout": DEFAULT_SKILL_TIMEOUT,
        "tool_names": [t["function"]["name"] for t in SKILL_TOOLS],
        "metadata": SKILL_METADATA,
    }


def get_runtime_diagnostics():
    """Return Skill runner runtime diagnostics for /api/health."""
    tools = {}
    python_ok = True
    runtimes_ok = True
    for tool_name in sorted(SKILL_RUNNERS.keys()):
        runner = SKILL_RUNNERS[tool_name]
        info = _diagnose_runner_runtime(runner)
        tools[tool_name] = info
        if not info.get("ok"):
            runtimes_ok = False
            if runner.command in ("python-auto", "py"):
                python_ok = False
    return {
        "python_ok": python_ok,
        "runtimes_ok": runtimes_ok,
        "runners_count": len(SKILL_RUNNERS),
        "tools": tools,
    }
