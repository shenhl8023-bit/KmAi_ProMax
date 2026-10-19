# -*- coding: utf-8 -*-
"""Win7-compatible process launcher for the packaged KmAI agent.

This module intentionally uses only the Python standard library available in
CPython 3.8.  Process discovery is done through WMIC, which is present on
Windows 7, and shutdown is limited to the exact package path and port written
to the state file by ``start``.
"""

from __future__ import print_function

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
try:
    from urllib.request import urlopen
except ImportError:  # pragma: no cover - Python 2 is not a supported target.
    urlopen = None


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9095
STATE_FILE_NAME = "kmai-win7-agent.json"


class LauncherError(Exception):
    """An expected launcher failure that can be shown without a traceback."""


def package_root_from_file():
    return Path(__file__).resolve().parent


def resolve_state_dir(package_root=None):
    configured = os.environ.get("KMAI_RUNTIME_DIR", "").strip()
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured))).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return (Path(local_app_data) / "KmAI").resolve()
    temp_dir = os.environ.get("TEMP", "").strip() or os.environ.get("TMP", "").strip()
    if temp_dir:
        return (Path(os.path.expandvars(os.path.expanduser(temp_dir))) / "KmAI").resolve()
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        return (
            Path(os.path.expandvars(os.path.expanduser(user_profile)))
            / "AppData"
            / "Local"
            / "KmAI"
        ).resolve()
    raise LauncherError(
        "KMAI_RUNTIME_DIR、LOCALAPPDATA、TEMP、TMP 和 USERPROFILE 均未指向可写运行时目录"
    )


def ensure_state_dir(state_dir):
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    probe = state_dir / ".write-test"
    try:
        with probe.open("a", encoding="utf-8"):
            pass
        probe.unlink()
    except (OSError, IOError) as exc:
        raise LauncherError("KMAI_RUNTIME_DIR 不可写: %s" % exc)
    return state_dir


def ensure_external_state_dir(state_dir, package_root):
    """Keep mutable state and logs outside the read-only package tree."""
    state_dir = Path(state_dir).expanduser().resolve()
    package_root = Path(package_root).resolve()
    try:
        state_dir.relative_to(package_root)
    except ValueError:
        return ensure_state_dir(state_dir)
    raise LauncherError("KMAI_RUNTIME_DIR must be outside the package directory")


def runtime_paths(package_root):
    package_root = Path(package_root).resolve()
    runtime = package_root / "runtime"
    return runtime / "python.exe", runtime / "node.exe"


def agent_script_path(package_root):
    package_root = Path(package_root).resolve()
    candidates = (
        package_root / "KmMpsMcpServer" / "agent_server.py",
        package_root / "agent_server.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Return the canonical package location so diagnostics remain actionable.
    return candidates[0]


def build_runtime_environment(package_root, state_dir):
    package_root = Path(package_root).resolve()
    state_dir = ensure_state_dir(state_dir)
    python_exe, node_exe = runtime_paths(package_root)
    env = os.environ.copy()
    env.update(
        {
            "KMAI_WIN7_COMPAT": "1",
            "KMAI_PACKAGE_ROOT": str(package_root),
            "KMAI_RUNTIME_DIR": str(state_dir),
            "KMAI_PYTHON_EXE": str(python_exe),
            "KMAI_SKILL_PYTHON": str(python_exe),
            "KMAI_NODE_EXE": str(node_exe),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return env


def build_start_command(package_root, port, state_dir=None):
    package_root = Path(package_root).resolve()
    state_dir = resolve_state_dir(package_root) if state_dir is None else Path(state_dir)
    python_exe, _node_exe = runtime_paths(package_root)
    script = agent_script_path(package_root)
    return [
        str(python_exe),
        # Embedded Python ignores PYTHONDONTWRITEBYTECODE from the environment.
        "-B",
        str(script),
        "--host",
        DEFAULT_HOST,
        "--port",
        str(int(port)),
    ]


def _validate_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise LauncherError("端口必须是整数")
    if not 1 <= port <= 65535:
        raise LauncherError("端口必须在 1 到 65535 之间")
    return port


def check_port(host, port, timeout=0.4):
    """Return 0 when free, 1 when listening, 2 for an invalid port."""
    try:
        port = _validate_port(port)
    except LauncherError:
        return 2
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return 1
    except (socket.timeout, socket.error, OSError):
        return 0


def health(host, port, timeout=2.0):
    if urlopen is None:
        return False
    try:
        response = urlopen("http://%s:%d/api/startup-ping" % (host, int(port)), timeout=timeout)
        try:
            status = getattr(response, "status", response.getcode())
            body = response.read(4097)
        finally:
            response.close()
        if status < 200 or status >= 300:
            return False
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError):
            return False
        return (isinstance(data, dict) and data.get("status") == "ok"
                and data.get("app") == "KmAI" and data.get("kind") == "agent")
    except Exception:
        return False


def state_path(state_dir):
    return Path(state_dir).resolve() / STATE_FILE_NAME


def read_state(state_dir):
    path = state_path(state_dir)
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, IOError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_state(state_dir, state):
    path = state_path(ensure_state_dir(state_dir))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    try:
        os.replace(str(temporary), str(path))
    except AttributeError:  # pragma: no cover - only for older Python hosts.
        if path.exists():
            path.unlink()
        temporary.rename(path)
    return path


def remove_state(state_dir):
    path = state_path(state_dir)
    try:
        path.unlink()
    except OSError:
        pass


def query_process_commandline(pid):
    """Return ``(pid, commandline)`` using Win7's WMIC interface."""
    try:
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "ProcessId=%d" % int(pid),
                "get",
                "CommandLine",
                "/value",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, ValueError, TypeError):
        return None, ""
    commandline = ""
    for line in (result.stdout or "").splitlines():
        if line.strip().lower().startswith("commandline="):
            commandline = line.split("=", 1)[1].strip()
            break
    return (int(pid), commandline) if commandline else (None, "")


def _path_token(value):
    value = str(value or "").strip().strip('"').strip("'")
    return value.replace("/", "\\").casefold().rstrip("\\")


def _normalized_path(value):
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    return _path_token(os.path.abspath(os.path.expandvars(os.path.expanduser(raw))))


def _commandline_tokens(commandline):
    # WMIC returns a Windows command line. Preserve paths containing spaces
    # while avoiding substring-based process matching.
    return [
        token.strip().strip('"').strip("'")
        for token in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", str(commandline or ""))
    ]


def _commandline_has_path(commandline, path):
    target = _normalized_path(path)
    if not target:
        return False
    return any(_normalized_path(token) == target for token in _commandline_tokens(commandline))


def _commandline_has_port(commandline, port):
    tokens = _commandline_tokens(commandline)
    port = str(int(port))
    for index, token in enumerate(tokens):
        if token == "--port" and index + 1 < len(tokens) and tokens[index + 1] == port:
            return True
        if token == "--port=" + port:
            return True
    return False


def _state_process_matches(state, package_root, expected_port=None):
    if not isinstance(state, dict):
        return False
    try:
        pid = int(state.get("pid"))
        port = _validate_port(state.get("port"))
        if expected_port is not None and port != _validate_port(expected_port):
            return False
    except (TypeError, ValueError, LauncherError):
        return False
    package_root = Path(package_root).resolve()
    if _normalized_path(state.get("package_root")) != _normalized_path(package_root):
        return False
    python_exe, _node_exe = runtime_paths(package_root)
    expected_script = agent_script_path(package_root)
    if _normalized_path(state.get("agent_script")) != _normalized_path(expected_script):
        return False
    current_pid, commandline = query_process_commandline(pid)
    if current_pid != pid or not commandline:
        return False
    return (
        _commandline_has_path(commandline, python_exe)
        and _commandline_has_path(commandline, expected_script)
        and _commandline_has_port(commandline, port)
    )


def stop_state(state, package_root):
    """Safely stop the exact process described by a launcher state record."""
    if not isinstance(state, dict):
        return False
    try:
        pid = int(state.get("pid"))
        port = _validate_port(state.get("port"))
    except (TypeError, ValueError, LauncherError):
        return False
    if not _state_process_matches(state, package_root, port):
        return False
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    return_code = getattr(result, "returncode", None)
    return isinstance(return_code, int) and return_code == 0


def _log_handles(state_dir):
    state_dir = ensure_state_dir(state_dir)
    logs = state_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "agent_server.out.log", logs / "agent_server.err.log"


def start(package_root, port, state_dir):
    package_root = Path(package_root).resolve()
    port = _validate_port(port)
    state_dir = ensure_external_state_dir(state_dir, package_root)
    if check_port(DEFAULT_HOST, port) == 1:
        state = read_state(state_dir)
        if _state_process_matches(state, package_root, port) and health(DEFAULT_HOST, port):
            return 0
        raise LauncherError("端口 %d 已被其他进程占用或不是当前包实例" % port)
    python_exe, node_exe = runtime_paths(package_root)
    script = agent_script_path(package_root)
    for required in (python_exe, node_exe, script):
        if not required.is_file():
            raise LauncherError("缺少运行时文件: %s" % required)
    out_log, err_log = _log_handles(state_dir)
    command = build_start_command(package_root, port, state_dir)
    env = build_runtime_environment(package_root, state_dir)
    out_stream = out_log.open("ab")
    err_stream = err_log.open("ab")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            cwd=str(package_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out_stream,
            stderr=err_stream,
            creationflags=flags,
        )
    finally:
        out_stream.close()
        err_stream.close()
    state = {
        "pid": process.pid,
        "port": port,
        "host": DEFAULT_HOST,
        "package_root": str(package_root),
        "agent_script": str(script),
        "python_exe": str(python_exe),
        "node_exe": str(node_exe),
    }
    write_state(state_dir, state)
    for _attempt in range(20):
        if health(DEFAULT_HOST, port, timeout=0.5):
            return 0
        time.sleep(0.25)
    raise LauncherError("Agent 未在端口 %d 上就绪，请查看 %s" % (port, err_log))


def stop(package_root, state_dir, expected_port=None):
    state_dir = ensure_external_state_dir(state_dir, package_root)
    state = read_state(state_dir)
    if not state:
        return 0
    if expected_port is not None:
        try:
            if _validate_port(state.get("port")) != _validate_port(expected_port):
                raise LauncherError("请求端口与状态文件端口不匹配，未执行终止")
        except (TypeError, ValueError, LauncherError):
            raise LauncherError("请求端口与状态文件端口不匹配，未执行终止")
    if not stop_state(state, package_root):
        raise LauncherError("状态中的进程与当前包路径或端口不匹配，未执行终止")
    remove_state(state_dir)
    return 0


def _parser():
    parser = argparse.ArgumentParser(description="KmAI Windows 7 local agent launcher")
    parser.add_argument("action", choices=("check-port", "health", "start", "stop"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--package-root", default=str(package_root_from_file()))
    parser.add_argument("--state-dir", default="")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    package_root = Path(args.package_root).resolve()
    try:
        if args.action == "check-port":
            return check_port(args.host, args.port)
        if args.action == "health":
            return 0 if health(args.host, args.port) else 1
        state_dir = resolve_state_dir(package_root) if not args.state_dir else Path(args.state_dir).resolve()
        if args.action == "start":
            return start(package_root, args.port, state_dir)
        return stop(package_root, state_dir, args.port)
    except LauncherError as exc:
        sys.stderr.write("[ERROR] %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
