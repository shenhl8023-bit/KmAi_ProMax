# -*- coding: utf-8 -*-
"""Skill 子进程执行器。

每个 Skill 是一个自包含的目录（含 SKILL.md / scripts/ / schemas/）。
本模块负责：把 LLM 给出的参数封装为 JSON 请求 → 启动子进程（stdin 输入、
stdout 输出）→ 解析 JSON 响应 → 错误降级为结构化响应（与 NamedPipeClient
保持一致的错误格式）。

设计要点（借鉴 E / 借鉴 B 的合并版）：
    - 超时：subprocess.communicate 同时排水 stdout/stderr，超时后 kill 子进程
    - 错误：3 类结构化响应
        * TOOL_NOT_REGISTERED  - registry 里找不到 action
        * TIMEOUT              - 子进程超时
        * RUN_ERROR            - 退出码非零 / JSON 解析失败
    - cwd：默认用 skill 所在目录，确保相对路径（assets/FeatureTemplate.xml
      等）能正确解析
"""

from __future__ import print_function

import json
import os
import re
import subprocess
import sys
import threading
import time


# 子进程 stdout 读取上限（8 MB）。Skill 返回值不应超过此值。
MAX_OUTPUT_SIZE = 8 * 1024 * 1024


_PYTHON_LAUNCHER_VERSIONS = None


def _parse_version_tuple(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        if len(value) >= 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                return None
        return None

    text = str(value).strip()
    if not text:
        return None
    parts = text.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 0
    except (TypeError, ValueError, IndexError):
        return None
    return (major, minor)


def _version_tuple_text(version_tuple):
    if not version_tuple:
        return ""
    return "%d.%d" % (version_tuple[0], version_tuple[1])


def _parse_python_launcher_spec(value):
    if not value or not isinstance(value, str):
        return None
    match = re.match(r"^-([23])(?:\.(\d+))?(?:-\d+)?$", value.strip())
    if not match:
        return None
    try:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
    except (TypeError, ValueError):
        return None
    return (major, minor)


def _load_python_launcher_versions():
    global _PYTHON_LAUNCHER_VERSIONS
    if _PYTHON_LAUNCHER_VERSIONS is not None:
        return _PYTHON_LAUNCHER_VERSIONS

    versions = []
    if os.name != "nt":
        _PYTHON_LAUNCHER_VERSIONS = versions
        return versions

    try:
        proc = subprocess.Popen(
            ["py", "-0p"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout_data, _ = proc.communicate(timeout=10.0)
    except Exception:
        _PYTHON_LAUNCHER_VERSIONS = versions
        return versions

    if proc.returncode != 0:
        _PYTHON_LAUNCHER_VERSIONS = versions
        return versions

    if isinstance(stdout_data, bytes):
        stdout_text = stdout_data.decode("utf-8", "replace")
    else:
        stdout_text = stdout_data

    pattern = re.compile(r"^-V:(\d+)\.(\d+)(?:-\d+)?(?:\s+\*)?\s+(.+)$")
    for line in stdout_text.splitlines():
        line = line.strip()
        match = pattern.match(line)
        if not match:
            continue
        try:
            major = int(match.group(1))
            minor = int(match.group(2))
        except (TypeError, ValueError):
            continue
        path = match.group(3).strip()
        if not path:
            continue
        versions.append({"version": (major, minor), "path": path})

    versions.sort(key=lambda item: item["version"], reverse=True)
    _PYTHON_LAUNCHER_VERSIONS = versions
    return versions


class SkillTimeout(RuntimeError):
    """Skill 子进程执行超时。"""

    def __init__(self, tool_name, timeout_seconds, message=None):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        if message is None:
            message = u"Skill「%s」执行超时（%.1f 秒）。" % (tool_name, timeout_seconds)
        super(SkillTimeout, self).__init__(message)


class SkillRunner(object):
    """单个 Skill 的执行器。

    action_config 结构（由 registry JSON 提供）：
        {
            "name": "propose",
            "tool_name": "kmsoft_group_template_propose",
            "command": "node",
            "args": ["scripts/select_group_template.js", "propose"],
            "cwd": "<skill_dir>",          # 可选，默认 None
            "timeout": 30,                 # 可选，默认 30 秒
            "env": {...}                   # 可选，附加到子进程环境变量
        }
    """

    def __init__(self, action_config):
        self.name = action_config["name"]
        self.tool_name = action_config["tool_name"]
        self.command = action_config["command"]
        self.args = list(action_config.get("args", []))
        self.cwd = action_config.get("cwd") or None
        self.timeout = float(action_config.get("timeout", 30))
        self.env = action_config.get("env") or None
        self.python_min_version = _parse_version_tuple(
            action_config.get("python_min_version") or action_config.get("min_python_version")
        )

    def _probe_python_version(self, command):
        try:
            proc = subprocess.Popen(
                list(command) + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout_data, _ = proc.communicate(timeout=10.0)
        except Exception:
            return None

        if proc.returncode != 0:
            return None

        if isinstance(stdout_data, bytes):
            stdout_text = stdout_data.decode("utf-8", "replace")
        else:
            stdout_text = stdout_data
        return _parse_version_tuple(stdout_text.strip())

    def _resolve_python_command(self):
        min_version = self.python_min_version or (3, 10)

        env_python = os.environ.get("KMAI_SKILL_PYTHON") or os.environ.get("KMAI_PYTHON_EXE")
        if env_python:
            version_tuple = self._probe_python_version([env_python])
            if version_tuple and version_tuple >= min_version:
                return [env_python]

        best_path = None
        best_version = None
        for item in _load_python_launcher_versions():
            version_tuple = item.get("version")
            path = item.get("path")
            if not path or not version_tuple:
                continue
            if version_tuple < min_version:
                continue
            if best_version is None or version_tuple > best_version:
                best_version = version_tuple
                best_path = path
        if best_path:
            return [best_path]

        candidates = [["py", "-3"], ["python"]] if os.name == "nt" else [["python3"], ["python"]]
        for command in candidates:
            version_tuple = self._probe_python_version(command)
            if version_tuple and version_tuple >= min_version:
                return command

        raise RuntimeError(
            u"Skill Python 启动失败: 未找到 Python %s 或更高版本"
            % _version_tuple_text(min_version)
        )

    def _build_cmdline(self, request):
        """把 JSON 请求序列化为命令行调用。

        约定：所有 Skill 脚本支持通过 stdin 接收 JSON 请求。
        这样避免 shell 转义问题（中文文本 / 路径含空格都不需要处理）。
        """
        if self.command in ("python-auto", "py"):
            args = list(self.args)
            if args and _parse_python_launcher_spec(args[0]) is not None:
                args = args[1:]
            return self._resolve_python_command() + args
        return [self.command] + self.args

    @staticmethod
    def _decode_pipe_output(data):
        if not data:
            return ""
        if isinstance(data, bytes):
            return data.decode("utf-8", "replace")
        return str(data)

    def _communicate_with_output_limit(self, proc, payload):
        stdout_chunks = []
        stderr_chunks = []
        totals = {"stdout": 0, "stderr": 0}
        limit_info = {"stream": None, "size": 0}
        errors = []
        limit_event = threading.Event()

        def request_kill():
            try:
                proc.kill()
            except Exception:
                pass

        def read_pipe(pipe, chunks, stream_name):
            try:
                while True:
                    chunk = pipe.read(65536)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        chunk = str(chunk).encode("utf-8", "replace")

                    previous_total = totals[stream_name]
                    totals[stream_name] = previous_total + len(chunk)
                    remaining = MAX_OUTPUT_SIZE - previous_total
                    if remaining > 0:
                        chunks.append(chunk[:remaining])

                    if totals[stream_name] > MAX_OUTPUT_SIZE:
                        if limit_info["stream"] is None:
                            limit_info["stream"] = stream_name
                            limit_info["size"] = totals[stream_name]
                        limit_event.set()
                        request_kill()
                        break
            except Exception as exc:
                errors.append(exc)
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        stdout_thread = threading.Thread(target=read_pipe, args=(proc.stdout, stdout_chunks, "stdout"))
        stderr_thread = threading.Thread(target=read_pipe, args=(proc.stderr, stderr_chunks, "stderr"))
        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        try:
            proc.stdin.write(payload)
            proc.stdin.close()
        except OSError:
            try:
                proc.stdin.close()
            except Exception:
                pass

        deadline = time.time() + self.timeout
        timed_out = False
        while proc.poll() is None:
            if limit_event.is_set():
                request_kill()
                break
            if time.time() >= deadline:
                timed_out = True
                request_kill()
                break
            time.sleep(0.01)

        try:
            proc.wait(timeout=2.0)
        except Exception:
            request_kill()

        stdout_thread.join(2.0)
        stderr_thread.join(2.0)

        raw = b"".join(stdout_chunks)
        stderr_data = b"".join(stderr_chunks)

        if timed_out:
            stderr_text = self._decode_pipe_output(stderr_data)
            raise SkillTimeout(
                self.tool_name, self.timeout,
                message=u"Skill「%s」执行超过 %.1f 秒未返回。stderr: %s"
                        % (self.tool_name, self.timeout, stderr_text[:200]),
            )

        if limit_info["stream"]:
            raise RuntimeError(
                u"Skill 返回数据超过限制（%s > %d 字节）"
                % (limit_info["stream"], MAX_OUTPUT_SIZE)
            )

        if errors:
            raise RuntimeError(u"Skill stdin/stdout 处理失败: %s" % errors[0])

        return raw, stderr_data

    def run(self, params, env_overrides=None):
        """执行 Skill action。

        入参 params: dict，来自 LLM 的 tool_call.function.arguments。
        返回值: dict，Skill 脚本输出的 JSON（已解析）。
        抛出:
            SkillTimeout         - 子进程超时
            RuntimeError         - 退出码非零 / JSON 解析失败
        """
        request = dict(params or {})
        # 把 action 字段补上（脚本强依赖）
        if "action" not in request:
            request["action"] = self.name

        try:
            payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RuntimeError(u"Skill 请求序列化失败: %s" % exc)

        cmdline = self._build_cmdline(request)
        env = None
        if self.env or env_overrides:
            env = dict(os.environ)
            if self.env:
                env.update(self.env)
            if env_overrides:
                env.update(env_overrides)

        try:
            proc = subprocess.Popen(
                cmdline,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                # 在 Windows 上避免弹出命令行窗口
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(u"Skill 子进程启动失败: %s (cmd=%s)" % (exc, cmdline))

        try:
            raw, stderr_data = self._communicate_with_output_limit(proc, payload)
        except OSError as exc:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(u"Skill stdin/stdout 处理失败: %s" % exc)

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")

        returncode = proc.returncode
        stderr_text = self._decode_pipe_output(stderr_data)

        if returncode != 0:
            # 子进程报错：尝试从 stdout 解析 JSON（脚本可能仍写了结构化错误响应）
            parsed_err = None
            if raw.strip():
                try:
                    parsed_err = json.loads(raw)
                except json.JSONDecodeError:
                    pass
            if parsed_err and isinstance(parsed_err, dict):
                # 把 ok 标记为 false，保持结构化输出
                parsed_err.setdefault("ok", False)
                parsed_err.setdefault("stderr", stderr_text[:500])
                return parsed_err
            raise RuntimeError(
                u"Skill「%s」退出码 %d。stderr: %s"
                % (self.tool_name, returncode, stderr_text[:500])
            )

        # 解析 JSON 输出
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                u"Skill「%s」返回非 JSON 响应: %s。原始输出: %.200s"
                % (self.tool_name, exc, raw)
            )

        return response
