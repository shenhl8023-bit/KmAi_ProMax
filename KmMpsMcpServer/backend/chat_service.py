# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import re

from .agent_profiles import DEFAULT_AGENT_ID, KMRAG_AGENT_ID
from .llm_client import _friendly_llm_exception
from .pipe_client import PIPE_NAME
from .prompts import SYSTEM_PROMPT
from .tool_runtime import KEYWORD_RULES, get_timeout, get_tools_for_agent


class ChatServiceMixin(object):
    @staticmethod
    def _format_numbered_names_reply(title, names, total_count=None, max_visible=80):
        values = list(names or [])
        count = total_count if isinstance(total_count, int) else len(values)
        if not values:
            return title + u"，但当前未提取到可展示名称。"
        lines = [title + u"，共 %d 个：" % count]
        for index, name in enumerate(values[:max_visible], 1):
            lines.append(u"%d. %s" % (index, name))
        if count > max_visible:
            lines.append(u"……还有 %d 个未展示。" % (count - max_visible))
        return "\n".join(lines)

    @staticmethod
    def _format_feature_list_reply(result):
        if not isinstance(result, dict) or result.get("status") == "error":
            return None
        return ChatServiceMixin._format_numbered_names_reply(
            u"已获取特征列表",
            result.get("features") or [],
            result.get("count"),
        )

    @staticmethod
    def _format_status_reply(result):
        if not isinstance(result, dict) or result.get("status") == "error":
            return None
        available = bool(result.get("pipe_available") or result.get("available"))
        pipe = result.get("pipe") or PIPE_NAME
        if available:
            return u"3DMPS 服务状态：可用。\n命名管道：%s" % pipe
        return u"3DMPS 服务状态：不可用。\n命名管道：%s\n请确认 3DMPS 主程序已启动并完成桥接注册。" % pipe

    @classmethod
    def _format_list_tool_reply(cls, tool_name, result):
        if tool_name in ("get_all_group_template_list", "getAllGroupTemplateList"):
            names = cls._extract_group_template_names(result)
            return cls._format_numbered_names_reply(u"已获取分组模板列表", names)
        if tool_name == "get_autoidentify_template_list":
            names = cls._extract_autoidentify_template_names(result)
            return cls._format_numbered_names_reply(u"已获取自动识别模板列表", names)
        if tool_name == "get_autoidentify_checkbox_list":
            names = cls._parse_autoidentify_checked_features(result)
            return cls._format_numbered_names_reply(u"已获取自动识别已勾选特征", names)
        return None

    def _format_direct_tool_reply(self, tool_name, default_reply, result, agent_id=DEFAULT_AGENT_ID):
        if self._tool_result_is_error(result):
            return self._tool_error_reply(tool_name, result)
        if tool_name == "check_3dmps_status":
            status_reply = self._format_status_reply(result)
            if status_reply:
                return status_reply
        if tool_name == "get_features":
            feature_reply = self._format_feature_list_reply(result)
            if feature_reply:
                return feature_reply
        if tool_name in ("get_all_bof_item", "get_bof_tree_data"):
            if agent_id == DEFAULT_AGENT_ID:
                bof_reply = self._format_bof_tree_reply(result)
            else:
                bof_reply = self._format_bof_feature_summary_reply(result)
            if bof_reply:
                return bof_reply
        list_reply = self._format_list_tool_reply(tool_name, result)
        if list_reply:
            return list_reply
        return default_reply

    def _keyword_match(self, text, agent_id=DEFAULT_AGENT_ID):
        """关键词匹配（非 LLM 时的回退模式）。

        通过 KEYWORD_RULES 注册表批量处理关键词→工具的映射。
        """
        lower = text.lower()
        template_text = self._extract_group_template_text(text)
        if template_text is not None:
            if not template_text:
                return {
                    "reply": u"请补充零件描述，例如：选择分组模板：衬套类回转体零件。",
                    "tool": None,
                    "result": None,
                }
            params = {"text": template_text, "limit": 3}
            tool_name = "kmsoft_group_template_propose"
            result = self._execute_tool(tool_name, params)
            return {
                "reply": u"已根据“%s”推荐分组模板候选，请在候选卡片中选择。" % template_text,
                "tool": tool_name,
                "args": params,
                "result": result,
            }

        for rule in KEYWORD_RULES:
            if any(kw in lower for kw in rule["keywords"]):
                # 需要先抽取路径
                if rule.get("needs_path"):
                    path = self._extract_path(text)
                    if not path:
                        return {
                            "reply": rule.get("path_hint",
                                u"请把路径一起发过来，例如：%s D:\\file.prt，" % rule["keywords"][0]),
                            "tool": None,
                            "result": None,
                        }
                    params = {"arg1": path}
                else:
                    params = dict(rule.get("params", {}))
                tool_name = rule["tool"]
                timeout = get_timeout(tool_name)
                result = self.tool(tool_name, params, timeout=timeout)
                reply = self._format_direct_tool_reply(tool_name, rule["reply"], result, agent_id=agent_id)
                return {
                    "reply": reply,
                    "tool": tool_name,
                    "args": params,
                    "result": result,
                }
        return {
            "reply": u"当前为关键词匹配模式。请在 config.ini 中配置 [LLM] 段后可启用智能对话。\n当前可直接识别的关键词：检查3DMPS状态、BOF/特征、获取特征列表、选择/推荐分组模板、自动识别、特征推理、AI工艺路线/工艺面板、主窗口按钮操作等。\n当前暂不可直接使用：save_file/save_as/close_prt_file、export_pdf/export_excel/export_gxk、check_model_compare、show_identify_report、create_step/check_process_step 等未注册或未实现的 3DMPS 端函数。",
            "tool": None,
            "result": None,
        }

    @staticmethod
    def _extract_group_template_text(text):
        normalized = (text or "").strip()
        if not normalized:
            return None
        lower = normalized.lower()
        has_group_template = (u"分组模板" in normalized) or ("group template" in lower)
        has_generic_template = u"模板" in normalized
        has_intent = any(kw in normalized for kw in (u"选择", u"推荐", u"匹配", u"选用", u"套用"))
        if not has_intent:
            return None
        if not has_group_template:
            if not has_generic_template:
                return None
            # “自动识别模板/工序模板”等不是分组模板推荐，避免误触发。
            if any(kw in normalized for kw in (u"自动识别", u"识别模板", u"工序模板", u"路线模板")):
                return None

        if has_group_template:
            prefixes = (u"选择分组模板", u"推荐分组模板", u"匹配分组模板", u"选用分组模板", u"套用分组模板")
        else:
            prefixes = (u"选择", u"推荐", u"匹配", u"选用", u"套用")

        cleaned = normalized
        for noise in (u"AI小沐", u"ai小沐", u"小沐", u"请", u"帮我", u"给我", u"一下"):
            cleaned = cleaned.replace(noise, u"")
        cleaned = cleaned.strip(u" \t\r\n：:，,。；;")

        if not cleaned:
            return None

        for sep in (u"：", ":"):
            if sep in cleaned:
                return cleaned.split(sep, 1)[1].strip(u" \t\r\n，,。；;")

        for prefix in prefixes:
            if prefix in cleaned:
                cleaned = cleaned.split(prefix, 1)[1].strip(u" \t\r\n：:，,。；;")
                break

        if has_group_template:
            cleaned = cleaned.replace(u"分组模板", u"")
        elif cleaned.endswith(u"模板"):
            cleaned = cleaned[:-2]
        cleaned = cleaned.strip(u" \t\r\n：:，,。；;")

        return cleaned or normalized

    @staticmethod
    def _extract_path(text):
        for token in text.replace(u"，", " ").replace(",", " ").split():
            if ":\\" in token or ":/" in token:
                return token.strip().strip('"')
        return ""

    def _direct_keyword_match(self, text, agent_id=DEFAULT_AGENT_ID):
        """短命令优先走确定性关键词工具，避免 LLM 误答或输出伪 tool_call。"""
        normalized = (text or "").strip()
        if not normalized or len(normalized) > 40:
            return None
        question_markers = (u"?", u"？", u"什么", u"为什么", u"为何", u"怎么", u"如何", u"能否", u"可以吗", u"吗")
        if any(marker in normalized for marker in question_markers):
            return None
        result = self._keyword_match(normalized, agent_id=agent_id)
        if result.get("tool"):
            return result
        return None

    def _tool_error_reply(self, tool_name, result):
        error = result if isinstance(result, dict) else {}
        nested = error.get("result") if isinstance(error, dict) else None
        if isinstance(nested, dict) and self._tool_result_is_error(nested):
            error = nested
        error_code = error.get("error_code") if isinstance(error, dict) else ""
        message = error.get("message") if isinstance(error, dict) else ""
        if not message and isinstance(error, dict):
            message = error.get("error", "")
        message_text = str(message or "").strip()
        if len(message_text) > 180:
            message_text = message_text[:180] + "..."
        if error_code == "FUNCTION_NOT_FOUND":
            return (
                u"工具「%s」当前不可用：3DMPS 主程序尚未暴露对应函数。%s"
                % (tool_name, self._format_km3dmps_diagnostic_hint())
            )
        if error_code == "TIMEOUT" or u"超时" in message_text or "timeout" in message_text.lower():
            return u"工具「%s」调用超时，3DMPS 可能仍在处理，请稍后查看主程序状态或重试。" % tool_name
        if not message_text:
            message_text = u"未知错误"
        return u"工具「%s」调用失败：%s" % (tool_name, message_text)

    @staticmethod
    def _stream_status(text):
        return {"type": "status", "text": text}

    @staticmethod
    def _tool_stream_status_text(tool_name):
        data_tool_keywords = (
            "get",
            "query",
            "read",
            "bof",
            "feature",
            "status",
            "tree",
            "input",
        )
        normalized = (tool_name or "").lower()
        if any(keyword in normalized for keyword in data_tool_keywords):
            return u"正在读取 3DMPS 数据..."
        return u"正在执行工具..."

    @staticmethod
    def _is_process_auto_ai_input_request(message_text):
        normalized = (message_text or "").strip()
        if not normalized:
            return False
        lower = normalized.lower()
        triggers = (
            u"进行ai工艺推理",
            u"获取ai工艺输入",
            u"获取工艺输入json",
        )
        return any(trigger in lower for trigger in triggers)

    def _process_auto_ai_input_override(self, message_text, profile, source="llm_chat"):
        if not profile or profile.get("id") != "process-auto-generate-agent":
            return None
        if not self._is_process_auto_ai_input_request(message_text):
            return None

        tool_name = "get_ai_process_route_input"
        result = self._execute_tool(tool_name, {})
        reply = "```json\n%s\n```" % json.dumps(result, ensure_ascii=False, indent=2)
        return {
            "reply": reply,
            "tool": tool_name,
            "args": {},
            "result": result,
            "status": result.get("status", "success") if isinstance(result, dict) else "success",
        }

    @staticmethod
    def _is_explicit_bof_tree_query(message_text):
        normalized = re.sub(r"\s+", "", (message_text or "").strip().lower())
        if not normalized:
            return False
        has_bof_target = ("bof" in normalized) or (u"特征树" in normalized)
        has_tree_shape_intent = any(marker in normalized for marker in (
            u"树",
            u"结构",
            u"层级",
            u"节点",
        ))
        return has_bof_target and has_tree_shape_intent

    def _default_direct_query_match(self, message_text, agent_id):
        if agent_id != DEFAULT_AGENT_ID:
            return None
        if not self._is_explicit_bof_tree_query(message_text):
            return None

        # 默认助手里 BOF 树结构是确定性只读查询，先走工具可避免 LLM 误选状态检查。
        tool_name = "get_all_bof_item"
        params = {}
        result = self.tool(tool_name, params, timeout=get_timeout(tool_name))
        reply = self._format_direct_tool_reply(
            tool_name,
            u"已调用 3DMPS 获取当前 BOF/特征树数据。",
            result,
            agent_id=agent_id,
        )
        return {
            "reply": reply,
            "tool": tool_name,
            "args": params,
            "result": result,
        }

    def chat(self, message, session_id="default", agent_id=DEFAULT_AGENT_ID):
        """主对话入口，"""

        clean_message = (message or "").strip()
        if not clean_message:
            return {
                "reply": u"请输入指令或问题。",
                "tool": None,
                "result": None,
            }

        profile, agent_found = self._resolve_agent_with_status(agent_id)
        if not agent_found:
            return self._unknown_agent_result(agent_id)
        forced_result = self._process_auto_ai_input_override(clean_message, profile)
        if forced_result:
            return forced_result

        if self.llm:
            profile_id = profile.get("id", DEFAULT_AGENT_ID)
            if profile_id != KMRAG_AGENT_ID:
                direct_keyword = self._direct_keyword_match(clean_message, agent_id=profile_id)
                if direct_keyword:
                    return direct_keyword
                direct_result = self._default_direct_query_match(clean_message, profile_id)
                if direct_result:
                    return direct_result

        # 无 LLM：使用关键词匹配
        if not self.llm:
            if profile.get("id") == KMRAG_AGENT_ID:
                return {
                    "reply": u"需要先启用 LLM 智能对话。",
                    "tool": None,
                    "result": None,
                }
            return self._keyword_match(clean_message, agent_id=profile.get("id", DEFAULT_AGENT_ID))

        # 有 LLM：使用工具调用循环
        return self._llm_chat(clean_message, session_id, profile)
    def stream_chat(self, message, session_id="default", agent_id=DEFAULT_AGENT_ID):
        """流式对话，逐事件 yield。

        事件结构（dict）：
            {"type": "content",  "text": "..."}      文本片段
            {"type": "tool_call","tool": "...",       工具调用结果（前端可用于渲染 option cards 等结构化 UI）
                         "args": {...},
                         "result": {...}}
        异常以 {"type": "error", "message": "..."} 形式 yield。
        """




        clean_message = (message or "").strip()
        yield self._stream_status(u"正在理解问题...")

        profile, agent_found = self._resolve_agent_with_status(agent_id)
        if not agent_found:
            yield {"type": "error", "message": self._unknown_agent_result(agent_id)["message"], "error_code": "UNKNOWN_AGENT"}
            return
        forced_result = self._process_auto_ai_input_override(clean_message, profile)
        if forced_result:
            if forced_result.get("tool"):
                yield {
                    "type": "tool_call",
                    "tool": forced_result.get("tool"),
                    "args": forced_result.get("args", {}),
                    "result": forced_result.get("result"),
                }
            yield {"type": "content", "text": forced_result.get("reply", "")}
            return

        if self.llm:
            profile_id = profile.get("id", DEFAULT_AGENT_ID)
            if profile_id != KMRAG_AGENT_ID:
                direct_keyword = self._direct_keyword_match(clean_message, agent_id=profile_id)
                if direct_keyword:
                    if direct_keyword.get("tool"):
                        yield {
                            "type": "tool_call",
                            "tool": direct_keyword.get("tool"),
                            "args": direct_keyword.get("args", {}),
                            "result": direct_keyword.get("result"),
                        }
                    yield {"type": "content", "text": direct_keyword.get("reply", "")}
                    return
                direct_result = self._default_direct_query_match(clean_message, profile_id)
                if direct_result:
                    if direct_result.get("tool"):
                        yield {
                            "type": "tool_call",
                            "tool": direct_result.get("tool"),
                            "args": direct_result.get("args", {}),
                            "result": direct_result.get("result"),
                        }
                    yield {"type": "content", "text": direct_result.get("reply", "")}
                    return

        if not self.llm:
            if profile.get("id") == KMRAG_AGENT_ID:
                yield {"type": "content", "text": u"需要先启用 LLM 智能对话。"}
                return
            result = self._keyword_match(clean_message, agent_id=profile.get("id", DEFAULT_AGENT_ID))
            if result.get("tool"):
                yield {
                    "type": "tool_call",
                    "tool": result.get("tool"),
                    "args": result.get("args", {}),
                    "result": result.get("result"),
                }
            yield {"type": "content", "text": result.get("reply", "")}
            return

        agent_id = profile.get("id", DEFAULT_AGENT_ID)
        agent_tools = get_tools_for_agent(agent_id)
        system_prompt = profile.get("prompt") or SYSTEM_PROMPT
        session_key = self._make_session_key(session_id, agent_id)

        messages = self.conversations.get_or_init(
            session_key,
            lambda: [{"role": "system", "content": system_prompt}],
        )
        messages.append({"role": "user", "content": clean_message})

        # 先做一轮工具调用判断（非流式）
        status_text = u"正在检索企业知识库..." if agent_id == KMRAG_AGENT_ID else u"正在判断是否需要调用 3DMPS 工具..."
        yield self._stream_status(status_text)
        try:
            resp = self.llm.chat(messages, tools=agent_tools, stream=False)
        except Exception as exc:
            messages = self._reset_session(session_id, message, agent_id=agent_id, system_prompt=system_prompt)
            try:
                resp = self.llm.chat(messages, tools=agent_tools, stream=False)
            except Exception as retry_exc:
                self._reset_session(session_id, agent_id=agent_id, system_prompt=system_prompt)
                yield {"type": "error", "message": u"智能对话调用失败：%s" % _friendly_llm_exception(retry_exc)}
                return

        choices = resp.get("choices", [])
        if not choices:
            yield {"type": "content", "text": u"LLM 未返回结果。"}
            return

        msg = choices[0].get("message", {})
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # 首轮已判定无需工具：直接复用本轮回答，避免再发一次流式请求。
            if agent_id == KMRAG_AGENT_ID:
                reply = u"未执行知识库检索，无法基于企业知识库回答。"
            else:
                reply = msg.get("content", "") or ""
            assistant_msg = {"role": "assistant", "content": reply}
            reasoning = msg.get("reasoning_content")
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)
            yield {"type": "content", "text": reply}
            return
        has_visible_tool_result = False
        visible_tool_reply = u"\u5df2\u8fd4\u56de\u7ed3\u679c\uff0c\u8bf7\u67e5\u770b\u4e0a\u65b9\u5361\u7247\u3002"
        tool_error_reply = None

        if tool_calls:
            # 需要工具调用：先保留 assistant/tool_calls，再执行工具并流式返回最终回答。
            messages.append(msg)
            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_raw = tc.get("function", {}).get("arguments", "{}")
                try:
                    func_args = json.loads(func_args_raw) if isinstance(func_args_raw, str) else func_args_raw
                except json.JSONDecodeError:
                    func_args = {}
                yield self._stream_status(self._tool_stream_status_text(func_name))
                tool_result = self._execute_tool(func_name, func_args, agent_id=agent_id)
                if isinstance(tool_result, dict) and (tool_result.get("ui") or tool_result.get("candidates")):
                    has_visible_tool_result = True
                    if tool_result.get("save_result"):
                        visible_tool_reply = u"\u5df2\u8fd4\u56de\u5e76\u4fdd\u5b58\u6a21\u677f\u7ed3\u679c\uff0c\u8bf7\u67e5\u770b\u4e0a\u65b9\u5361\u7247\u3002"
                    elif tool_result.get("candidates"):
                        visible_tool_reply = u"\u5df2\u8fd4\u56de\u5019\u9009\u7ed3\u679c\uff0c\u8bf7\u5728\u4e0a\u65b9\u5361\u7247\u4e2d\u9009\u62e9\u3002"
                if self._tool_result_is_error(tool_result) and tool_error_reply is None:
                    tool_error_reply = self._tool_error_reply(func_name, tool_result)
                elif not self._tool_result_is_error(tool_result):
                    formatted_tool_reply = self._format_direct_tool_reply(
                        func_name,
                        visible_tool_reply,
                        tool_result,
                        agent_id=agent_id,
                    )
                    if formatted_tool_reply != visible_tool_reply:
                        visible_tool_reply = formatted_tool_reply
                        has_visible_tool_result = True
                # 把工具结果推给前端（前端根据 result.ui 渲染可视化卡片，
                # 没有 ui 字段时回退到 JSON details 显示）
                yield {
                    "type": "tool_call",
                    "tool": func_name,
                    "args": func_args,
                    "result": tool_result,
                }
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
                    yield {"type": "content", "text": reply}
                    return

        if has_visible_tool_result:
            messages.append({"role": "assistant", "content": visible_tool_reply})
            yield {"type": "content", "text": visible_tool_reply}
            return

        if tool_error_reply:
            messages.append({"role": "assistant", "content": tool_error_reply})
            yield {"type": "content", "text": tool_error_reply}
            return

        # Stream final answer and store full assistant reply in conversation history.
        final_chunks = []
        reasoning_chunks = []
        yield self._stream_status(u"正在组织回复...")
        try:
            for delta in self.llm.chat(messages, tools=None, stream=True, include_reasoning=True):
                if isinstance(delta, dict):
                    chunk = delta.get("content") or ""
                    reasoning_content = delta.get("reasoning_content") or ""
                else:
                    chunk = delta
                    reasoning_content = ""
                if reasoning_content:
                    reasoning_chunks.append(reasoning_content)
                if chunk:
                    final_chunks.append(chunk)
                    yield {"type": "content", "text": chunk}
            final_text = "".join(final_chunks)
            reasoning_text = "".join(reasoning_chunks)
            if final_text or reasoning_text:
                assistant_msg = {"role": "assistant", "content": final_text}
                if reasoning_text:
                    assistant_msg["reasoning_content"] = reasoning_text
                messages.append(assistant_msg)
        except Exception as exc:
            self._reset_session(session_id, agent_id=agent_id, system_prompt=system_prompt)
            if has_visible_tool_result:
                if not final_chunks:
                    yield {"type": "content", "text": visible_tool_reply}
                return
            yield {"type": "error", "message": _friendly_llm_exception(exc)}
