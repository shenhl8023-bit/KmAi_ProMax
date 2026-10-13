# -*- coding: utf-8 -*-
from __future__ import print_function

import json

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import Request, urlopen, URLError, HTTPError

from .agent_utils import _json_bytes


def _extract_llm_error_message(body_text, limit=220):
    """Extract a compact user-safe LLM error message from JSON or text."""

    try:
        data = json.loads(body_text)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("type") or body_text
            else:
                msg = data.get("message") or body_text
        else:
            msg = body_text
    except Exception:
        msg = body_text
    msg = str(msg).replace("\r", " ").replace("\n", " ").strip()
    if "tool_use_id" in msg or "tool_result" in msg:
        return u"工具调用上下文不完整，已重置会话。请重新发送刚才的问题。"
    if "content[].thinking" in msg or "thinking mode" in msg:
        return u"模型思考上下文不完整，已重置会话。请重新发送刚才的问题。"
    if len(msg) > limit:
        msg = msg[:limit] + "..."
    return msg or u"未知错误"


def _friendly_llm_exception(exc):
    msg = str(exc)
    if "content[].thinking" in msg or "thinking mode" in msg:
        return u"模型思考上下文异常，已自动重置会话。请重新发送刚才的问题。"
    if "tool_use_id" in msg or "tool_result" in msg or "tool_call" in msg:
        return u"工具调用上下文异常，已自动重置会话。请重新发送刚才的问题。"
    if len(msg) > 220:
        msg = msg[:220] + "..."
    return msg


# ============================================
# 工具定义（OpenAI function calling 格式）
# ============================================
# 工具按业务域拆分，tools/ 子包中，TOOLS / TOOL_PIPE_BUILDER / KEYWORD_RULES
# 在导入时，tools/__init__.py 聚合，
# 当前有多个工具域：original、ai_bridge_ops、dialog_ops、file_ops、process_ops、query_ops、reference_ops
# 注意：扩展工具依赖 3DMPS 主程序团队在管道服务端暴露对应函数，
#       未暴露的工具会被服务端返回 "Function not found" 错误，
#       调用方会通过 is_function_not_found_error() 识别并返回结构化降级响应，


class LLMClient(object):
    def __init__(self, config):
        self.config = config
        self.base_url = config["base_url"].rstrip("/")
        self.api_key = config["api_key"]
        self.model = config["model"]
        self.max_tokens = config["max_tokens"]
        self.temperature = config["temperature"]

    def chat(self, messages, tools=None, stream=False, include_reasoning=False):
        """调用 LLM API（OpenAI 兼容格式）。"""

        url = self.base_url + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key,
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if stream:
            body["stream"] = True

        req = Request(url, data=_json_bytes(body), headers=headers, method="POST")

        if stream:
            return self._stream_chat(req, include_reasoning=include_reasoning)

        try:
            resp = urlopen(req, timeout=120)
            data = resp.read().decode("utf-8")
            return json.loads(data)
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(u"LLM API HTTP %d: %s" % (exc.code, _extract_llm_error_message(body_text)))
        except URLError as exc:
            raise RuntimeError(u"LLM API 连接失败: %s" % exc.reason)
        except Exception as exc:
            raise RuntimeError(u"LLM API 调用异常: %s" % exc)

    def _stream_chat(self, req, include_reasoning=False):
        """流式调用，逐行 yield 内容片段。"""

        try:
            resp = urlopen(req, timeout=120)
            for line in resp:
                line = line.decode("utf-8", "replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices") or []
                        # 跳过空 choices（DeepSeek 等流式 API 在内容收尾时常发送
                        # "choices": [] 的 keepalive 包；不做防护会导致 IndexError）
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content") or ""
                        reasoning_content = (delta.get("reasoning_content") or
                                             delta.get("reasoning") or
                                             delta.get("thinking") or "")
                        if include_reasoning:
                            if content or reasoning_content:
                                yield {
                                    "content": content,
                                    "reasoning_content": reasoning_content,
                                }
                        elif content:
                            yield content
                    except json.JSONDecodeError:
                        pass
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(u"LLM 流式接口 HTTP %d: %s" % (exc.code, _extract_llm_error_message(body_text)))
        except URLError as exc:
            raise RuntimeError(u"LLM 流式接口连接失败: %s" % exc.reason)
        except Exception as exc:
            raise RuntimeError(u"LLM 流式接口异常: %s" % exc)
