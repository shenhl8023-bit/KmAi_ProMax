# -*- coding: utf-8 -*-
from __future__ import print_function

from tools import (
    TOOLS as BASE_TOOLS,
    TOOL_PIPE_BUILDER,
    TOOL_PIPE_TARGETS,
    KEYWORD_RULES,
    get_timeout as base_get_timeout,
)
from skills import (
    SKILL_TOOLS,
    SKILL_RUNNERS,
    SKILL_TIMEOUTS,
    get_runtime_diagnostics as get_skill_runtime_diagnostics,
    get_skill_timeout,
)
from .agent_profiles import KMRAG_AGENT_ID

HIDDEN_3DMPS_TOOLS = frozenset([
    "get_cur_model_info",
    "get_process_steps",
    "get_rough_info",
    "get_bop_tree",
    "close_prt_file",
    "save_file",
    "save_as",
    "export_pdf",
    "export_excel",
    "export_gxk",
    "auto_save",
    "create_step",
    "reset_step_number",
    "arrange_step",
    "rapid_create_step",
    "check_process_step",
    "check_model_compare",
    "show_identify_report",
    "is_button_checked",
    "submit_ai_process_route_output",
    "get_ai_process_route_status",
    "start_ai_process_route",
    "generate_ai_process_route",
])


def _tool_name(tool):
    try:
        return tool.get("function", {}).get("name")
    except AttributeError:
        return None


def _is_public_tool(tool):
    name = _tool_name(tool)
    return bool(name and name not in HIDDEN_3DMPS_TOOLS)


TOOLS = [tool for tool in BASE_TOOLS if _is_public_tool(tool)] + list(SKILL_TOOLS)
KMRAG_TOOL_NAME = "kmrag_search"
KEYWORD_RULES = [
    rule for rule in KEYWORD_RULES
    if rule.get("tool") not in HIDDEN_3DMPS_TOOLS
]


def get_timeout(name, default=None):
    """???????????? Skill?? 3DMPS ???"""

    if name in SKILL_TIMEOUTS:
        return SKILL_TIMEOUTS[name]
    return base_get_timeout(name, default)


def get_tools_for_agent(agent_id):
    if agent_id == KMRAG_AGENT_ID:
        return [tool for tool in TOOLS if _tool_name(tool) == KMRAG_TOOL_NAME]
    return [tool for tool in TOOLS if _tool_name(tool) != KMRAG_TOOL_NAME]


def is_tool_allowed_for_agent(agent_id, tool_name):
    if agent_id is None:
        return True
    if agent_id == KMRAG_AGENT_ID:
        return tool_name == KMRAG_TOOL_NAME
    return tool_name != KMRAG_TOOL_NAME
