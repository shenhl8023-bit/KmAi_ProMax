# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import sys
import threading
import time

from .agent_utils import _json_bytes
from .tool_runtime import TOOL_PIPE_TARGETS

PIPE_NAME = u"\\\\.\\pipe\\3dmps_service"
BUFFER_SIZE = 64 * 1024
MAX_RESPONSE_SIZE = 8 * 1024 * 1024
_PIPE_CALL_LOCK = threading.RLock()
_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes


class PipeCallTimeout(RuntimeError):
    """3DMPS 管道调用超时。

    继承自 RuntimeError，调用方可统一通过 except RuntimeError 捕获，
    也可单独 except PipeCallTimeout 做超时降级。
    """
    def __init__(self, function_name, timeout_seconds, message=None):
        self.function_name = function_name
        self.timeout_seconds = timeout_seconds
        if message is None:
            message = u"3DMPS 函数「%s」调用超时（%.1f 秒）。" % (function_name, timeout_seconds)
        super(PipeCallTimeout, self).__init__(message)


class StubPipeClient(object):
    """Non-Windows 平台占位：命名管道不可用，所有工具调用返回错误。"""
    def __init__(self, *args, **kwargs):
        pass

    def call(self, function_name, params=None, timeout=None):
        return {
            "ok": False,
            "error": "PIPE_UNAVAILABLE",
            "message": u"命名管道仅在 Windows 上可用，当前平台不支持该功能。",
        }



if _IS_WINDOWS:
    class NamedPipeClient(object):
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        ERROR_MORE_DATA = 234
        PIPE_READMODE_MESSAGE = 0x00000002

        @property
        def INVALID_HANDLE_VALUE(self):
            return ctypes.c_void_p(-1).value


        def __init__(self, pipe_name, timeout_ms=3000, retry_count=2, retry_delay=0.5,
                     default_timeout=30.0):
            self.pipe_name = pipe_name
            self.timeout_ms = timeout_ms
            self.retry_count = max(1, retry_count)
            self.retry_delay = max(0.0, retry_delay)
            self.default_timeout = max(0.1, float(default_timeout))
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # 提前绑定 CancelIoEx（如不可用则降级为 CancelIo；WinXP+ 都有 CancelIoEx）
            try:
                self.kernel32.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                self.kernel32.CancelIoEx.restype = ctypes.c_int
                self._has_cancel_io_ex = True
            except AttributeError:
                self._has_cancel_io_ex = False

        def _wait_pipe(self):
            """等待命名管道就绪（带超时）。"""

            ok = self.kernel32.WaitNamedPipeW(self.pipe_name, self.timeout_ms)
            if not ok:
                error_code = ctypes.get_last_error()
                raise ConnectionError(
                    u"命名管道未就绪（超时 %d ms，错误码 %d）：%s"
                    % (self.timeout_ms, error_code, self.pipe_name)
                )

        def _open_pipe(self):
            """打开命名管道并设置为消息模式。"""

            self._wait_pipe()
            handle = self.kernel32.CreateFileW(
                self.pipe_name,
                self.GENERIC_READ | self.GENERIC_WRITE,
                0, None, self.OPEN_EXISTING, 0, None,
            )
            if handle == self.INVALID_HANDLE_VALUE:
                error_code = ctypes.get_last_error()
                raise ConnectionError(
                    u"打开命名管道失败（错误码 %d）：%s" % (error_code, self.pipe_name)
                )
            # SetNamedPipeHandleState 第二个参数是 LPDWORD（指针）
            mode = ctypes.c_ulong(self.PIPE_READMODE_MESSAGE)
            self.kernel32.SetNamedPipeHandleState(
                handle, ctypes.byref(mode), None, None,
            )
            return handle

        def _cancel_pending_io(self, handle):
            """尽力取消挂起的 I/O（不抛异常）。"""

            try:
                if self._has_cancel_io_ex:
                    self.kernel32.CancelIoEx(handle, None)
                else:
                    self.kernel32.CancelIo(handle)
            except Exception:
                pass

        def _read_one_message(self, handle, state_holder):
            """在线程中执行一次 ReadFile，结果写入 state_holder[0]。

            state_holder[0] = {"chunk": bytes|None, "ok": bool|None, "exception": Exception|None, "done": bool}
            """
            state = {"chunk": None, "ok": None, "exception": None, "done": False}
            state_holder[0] = state
            try:
                buffer = ctypes.create_string_buffer(BUFFER_SIZE)
                read = ctypes.c_ulong(0)
                ok = self.kernel32.ReadFile(
                    handle, buffer, BUFFER_SIZE, ctypes.byref(read), None,
                )
                state["chunk"] = buffer.raw[:read.value]
                state["ok"] = bool(ok)
            except Exception as exc:
                state["exception"] = exc
            finally:
                state["done"] = True

        def _do_call(self, handle, payload, timeout_seconds, function_name):
            """单次请求/响应（协议层，失败时不重试）。读阶段强制限时。

            超时时抛 PipeCallTimeout；调用方负责在 finally 中先等待读线程退出，再关句柄。
            """
            # 写阶段：管道是本机回路，通常瞬时完成，不做单独超时
            written = ctypes.c_ulong(0)
            ok = self.kernel32.WriteFile(
                handle, ctypes.c_char_p(payload),
                len(payload), ctypes.byref(written), None,
            )
            if not ok:
                raise RuntimeError(u"写入管道失败，错误码 %d" % ctypes.get_last_error())

            # 读阶段：分消息读取（PIPE_READMODE_MESSAGE），每条消息在独立线程中等待
            chunks = []
            total = 0
            deadline = time.monotonic() + max(0.1, float(timeout_seconds))

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PipeCallTimeout(function_name, timeout_seconds,
                                          message=u"3DMPS 函数「%s」调用总耗时超过 %.1f 秒，强制中止。"
                                                  % (function_name, timeout_seconds))

                state_holder = [None]
                t = threading.Thread(
                    target=self._read_one_message,
                    args=(handle, state_holder),
                    daemon=True,
                )
                t.start()
                t.join(timeout=remaining)

                if not (state_holder[0] and state_holder[0].get("done")):
                    # 读线程仍在运行，触发 PipeCallTimeout
                    # call() 会在 finally 前等待该线程，避免 use-after-free
                    raise PipeCallTimeout(function_name, timeout_seconds)

                state = state_holder[0]
                if state["exception"] is not None:
                    raise state["exception"]

                chunk = state["chunk"]
                ok = state["ok"]
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
                if total > MAX_RESPONSE_SIZE:
                    raise RuntimeError(u"3DMPS 返回数据超过限制")
                if ok:
                    break
                error_code = ctypes.get_last_error()
                if error_code != self.ERROR_MORE_DATA:
                    raise RuntimeError(u"读取管道失败，错误码 %d" % error_code)

            response_text = b"".join(chunks).decode("utf-8", "replace")
            try:
                response = json.loads(response_text)
            except json.JSONDecodeError:
                return {"status": "error", "message": u"3DMPS 返回非 JSON 响应"}

            # 服务端明确返回错误时，抛 RuntimeError 以触发调用方的优雅降级逻辑
            if isinstance(response, dict) and response.get("status") == "error":
                msg = response.get("message", "Unknown 3DMPS error")
                raise RuntimeError(msg)

            return response

        def call(self, function_name, params=None, timeout=None):
            """调用 3DMPS 函数。

            - 连接级错误（管道未就绪、打开失败）会自动重试 retry_count 次
            - 协议级错误（写入/读取失败/服务端业务错误）不会重试，直接抛异常
            - 超时（PipeCallTimeout）不会重试（用户已等过一次，重试只会翻倍等待）
            - timeout=None 时使用 self.default_timeout（默认 30s）
            """
            if params is None:
                params = {}
            if timeout is None:
                timeout = self.default_timeout
            timeout = max(0.1, float(timeout))

            request = {"function": function_name, "params": params}
            payload = _json_bytes(request)

            last_error = None
            for attempt in range(1, self.retry_count + 1):
                handle = None
                try:
                    # 锁只覆盖单次「打开管道 + 一次请求-响应」。
                    # 重试之间的 time.sleep 不持锁,其它 HTTP 请求（健康检查 / 前端
                    # 轮询 / 聊天流）可以并发处理,避免管道重试把整个服务卡死。
                    with _PIPE_CALL_LOCK:
                        handle = self._open_pipe()
                        # _do_call 内的读线程是 daemon,句柄关闭时 ReadFile 返回错误后退出
                        return self._do_call(handle, payload, timeout, function_name)
                except ConnectionError as exc:
                    last_error = exc
                    if attempt < self.retry_count:
                        time.sleep(self.retry_delay)
                        continue
                    raise
                except PipeCallTimeout:
                    # 超时不重试（用户已等过一次，重试只会翻倍等待）
                    raise
                except RuntimeError:
                    raise
                finally:
                    if handle:
                        self.kernel32.CloseHandle(handle)
            if last_error:
                raise last_error
            raise RuntimeError(u"未知管道错误")

        def is_available(self):
            """健康探测：是否能连上命名管道（不发送业务请求）。"""

            handle = None
            try:
                handle = self._open_pipe()
                return True
            except Exception:
                return False
            finally:
                if handle:
                    self.kernel32.CloseHandle(handle)


# ============================================
# 错误识别辅助函数
# ============================================
# 参考 mcp_server_refactor/tools/custom_tools.py:18-21 的同名函数，
# 让调用方在「主程序未暴露某函数」时返回结构化降级响应，而不是抛出字符串错误。


def is_function_not_found_error(exc, function_name):
    """判断异常是否为「函数未注册」错误，兼容工具别名。"""

    msg = str(exc)
    if "Function not found" not in msg:
        return False
    pipe_targets = globals().get("TOOL_PIPE_TARGETS", {})
    pipe_function_name = pipe_targets.get(function_name, function_name)
    return function_name in msg or pipe_function_name in msg


def make_unsupported_tool_payload(function_name, exc):
    """生成统一的「暂不支持」结构化响应。

    返回字段：
      status:       "error"
      error_code:   "FUNCTION_NOT_FOUND"
      message:      错误详情
      tool:         出问题的工具名
      available:    False
      suggestion:   建议用户联系主程序团队
    """
    return {
        "status": "error",
        "error_code": "FUNCTION_NOT_FOUND",
        "message": str(exc),
        "tool": function_name,
        "available": False,
        "suggestion": u"该功能尚未在 3DMPS 主程序命名管道服务端注册，需联系主程序团队在 Km3dmps.exe 中暴露该函数。",
    }


def is_timeout_error(exc):
    """判断异常是否为「调用超时」（包含命名管道和 Skill 子进程的超时）。"""
    from skills.runner import SkillTimeout  # 局部导入避免循环导入
    return isinstance(exc, (PipeCallTimeout, SkillTimeout))


def make_timeout_error_payload(function_name, exc):
    """生成统一的「调用超时」结构化响应。

    返回字段：
      status:       "error"
      error_code:   "TIMEOUT"（机器可读的错误类型）
      message:      超时描述
      tool:         出问题的工具
      timeout:      当时设置的超时（秒）
      retriable:    True（与「函数不存在」不同，超时通常可重试）
      suggestion:   建议用户的下一步操作
    """
    timeout = getattr(exc, "timeout_seconds", None)
    return {
        "status": "error",
        "error_code": "TIMEOUT",
        "message": str(exc),
        "tool": function_name,
        "timeout": timeout,
        "retriable": True,
        "suggestion": u"3DMPS 在 %.1f 秒内未返回结果，主程序可能正在执行长时间操作。可稍后重试，或拆分任务后再触发。" % (timeout or 0.0),
    }