# -*- coding: utf-8 -*-
from __future__ import print_function

import json

from . import agent_config as _config
from .agent_config import LLM_MAX_TOOL_ITERATIONS
from .agent_profiles import DEFAULT_AGENT_ID, KMRAG_AGENT_ID, get_agent_profile, resolve_agent_profile
from .llm_client import LLMClient, _friendly_llm_exception
from .prompts import SYSTEM_PROMPT
from .tool_runtime import get_tools_for_agent


def create_initial_llm_client():
    return LLMClient(_config.CONFIG) if _config.LLM_ENABLED else None


class LlmServiceMixin(object):
    @staticmethod
    def _make_session_key(session_id, agent_id=None):
        clean_session_id = (session_id or "default").strip() or "default"
        clean_agent_id = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
        return clean_agent_id + "::" + clean_session_id

    @staticmethod
    def _resolve_agent(agent_id=None):
        return get_agent_profile(agent_id)

    @staticmethod
    def _resolve_agent_with_status(agent_id=None):
        return resolve_agent_profile(agent_id)

    @staticmethod
    def _unknown_agent_result(agent_id):
        requested = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
        return {
            "status": "error",
            "error_code": "UNKNOWN_AGENT",
            "message": u"未知智能体：%s" % requested,
            "agent_id": requested,
        }

    def _reset_session(self, session_id, message=None, agent_id=None, system_prompt=None):
        session_key = self._make_session_key(session_id, agent_id)
        prompt = system_prompt or SYSTEM_PROMPT
        messages = [{"role": "system", "content": prompt}]
        if message:
            messages.append({"role": "user", "content": message})
        self.conversations.set(session_key, messages)
        return messages

    def reload_llm(self):
        self.llm = LLMClient(_config.CONFIG) if _config._is_llm_config_enabled(_config.CONFIG) else None
        self.conversations.reset()

    def _llm_chat(self, message, session_id, profile=None):
        """LLM 对话：支持多轮工具调用，"""

        profile = profile or self._resolve_agent()
        agent_id = profile.get("id", DEFAULT_AGENT_ID)
        system_prompt = profile.get("prompt") or SYSTEM_PROMPT
        session_key = self._make_session_key(session_id, agent_id)

        # 命中复用,未命中则用空会话列表初始化（仅含 system prompt,
        # user 消息在下面追加）。get_or_init 内部会刷新访问时间并触发淘汰。
        messages = self.conversations.get_or_init(
            session_key,
            lambda: [{"role": "system", "content": system_prompt}],
        )
        messages.append({"role": "user", "content": message})

        tool_calls_log = []
        agent_tools = get_tools_for_agent(agent_id)
        max_iterations = LLM_MAX_TOOL_ITERATIONS

        for iteration in range(max_iterations):
            # DeepSeek 特殊行为：当 messages 中已包含 tool 消息（第二轮起），
            # 同时传 tools=TOOLS 会触发 "tool must respond to preceding tool_calls" 校验错误。
            # 第二轮起改传 tools=None，让 LLM 基于 tool 结果直接给最终回答。
            current_tools = agent_tools if iteration == 0 else None
            try:
                resp = self.llm.chat(messages, tools=current_tools)
            except Exception as exc:
                if iteration == 0:
                    messages = self._reset_session(session_id, message, agent_id=agent_id, system_prompt=system_prompt)
                    try:
                        resp = self.llm.chat(messages, tools=current_tools)
                    except Exception as retry_exc:
                        self._reset_session(session_id, agent_id=agent_id, system_prompt=system_prompt)
                        return {
                            "reply": u"智能对话调用失败：%s" % _friendly_llm_exception(retry_exc),
                            "tool": None,
                            "result": None,
                            "status": "error",
                        }
                else:
                    self._reset_session(session_id, agent_id=agent_id, system_prompt=system_prompt)
                    return {
                        "reply": u"智能对话调用失败：%s" % _friendly_llm_exception(exc),
                        "tool": None,
                        "result": None,
                        "status": "error",
                    }

            choices = resp.get("choices", [])
            if not choices:
                return {"reply": u"LLM 未返回有效结果。", "tool": None, "result": None}

            msg = choices[0].get("message", {})
            finish_reason = choices[0].get("finish_reason", "")

            # 检查是否有 tool_calls
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                if agent_id == KMRAG_AGENT_ID:
                    return {
                        "reply": u"未执行知识库检索，无法基于企业知识库回答。",
                        "tool": None,
                        "result": None,
                    }
                # 直接回答
                content = msg.get("content", "")
                messages.append(dict(msg))
                return {
                    "reply": content,
                    "tool": None,
                    "result": None,
                }

            # 处理工具调用
            messages.append(msg)  # 保留 assistant 的 tool_calls 消息

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_raw = tc.get("function", {}).get("arguments", "{}")
                try:
                    func_args = json.loads(func_args_raw) if isinstance(func_args_raw, str) else func_args_raw
                except json.JSONDecodeError:
                    func_args = {}

                tool_result = self._execute_tool(func_name, func_args, agent_id=agent_id)
                tool_calls_log.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": tool_result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

                if agent_id == KMRAG_AGENT_ID:
                    records = tool_result.get("records", []) if isinstance(tool_result, dict) else []
                    if self._tool_result_is_error(tool_result):
                        reply = tool_result.get("message", u"知识库检索失败。")
                    elif not records:
                        reply = u"知识库未检索到相关内容。"
                    else:
                        continue
                    messages.append({"role": "assistant", "content": reply})
                    return {
                        "reply": reply,
                        "tool": func_name,
                        "args": func_args,
                        "result": tool_result,
                        "status": "error" if self._tool_result_is_error(tool_result) else "success",
                    }

                if self._tool_result_is_error(tool_result):
                    reply = self._tool_error_reply(func_name, tool_result)
                    messages.append({"role": "assistant", "content": reply})
                    return {
                        "reply": reply,
                        "tool": func_name,
                        "args": func_args,
                        "result": tool_result,
                        "status": "error",
                    }

        # 超过最大迭代次数
        return {
            "reply": u"工具调用循环超过最大次数。",
            "tool": tool_calls_log[-1]["tool"] if tool_calls_log else None,
            "result": tool_calls_log[-1]["result"] if tool_calls_log else None,
        }
