# -*- coding: utf-8 -*-
"""兼容参考 MCP 项目的业务化工具别名。

这些工具名来自 F:\\Projects\\AI\\AI_wc\\mcp_server_refactor。能稳定全局调用的工具直接
映射到主窗口桥接函数；必须依赖弹窗生命周期的工具保留在工具列表中，但会走对应弹窗临时
注册的函数，未打开弹窗时由 agent_server 返回结构化 unsupported 响应。
"""

from __future__ import print_function

import json


AUTOIDENTIFY_FEATURES = [
    u"小孔", u"大孔", u"同直径深度分布孔系", u"同轴孔系", u"主轴上同轴孔系", u"非主轴上同轴孔系",
    u"外圆柱面", u"内环槽", u"外环槽", u"回转面倒角", u"回转面倒圆", u"六面", u"平面类",
    u"矩形槽", u"U形直槽", u"单纯底凹槽", u"平底沟槽", u"台阶", u"侧壁", u"矩形截面特种加工槽",
    u"平面的外周边侧壁", u"平面的内窗口通槽", u"回转面下陷通槽", u"法兰圆周缺口", u"一般外倒圆",
    u"平面上边倒角", u"倾斜面或曲面", u"普通均布齿槽", u"斜向直齿均布齿槽", u"回转面系",
    u"主回转面系", u"回转面系端面上环状缺口", u"回转面系端面上批量小通槽",
    u"回转面系端面上批量小平底槽", u"回转面系端面上批量小台阶周边",
]

BUTTON_TOOL_SPECS = [
    ("click_group_template_button", "Open the group template dialog from the main window.", 52756),
    ("click_autoidentify_button", "Open the auto-identify dialog from the main window.", 60013),
    ("click_auto_reasoning_button", "Click the Auto Reasoning button in the main window.", 60403),
    ("click_processrapid_button", "Open the process-rapid dialog from the main window.", 60408),
    ("click_generate_all_button", "Click the Generate All button in the main window.", 60410),
    ("click_one_click_generate_button", "Click the One Click Generate button in the main window.", 60429),
]


def _tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _feature_state_string(args, fill_missing):
    raw = args.get("feature_states", "{}")
    if isinstance(raw, dict):
        requested = raw
    else:
        requested = json.loads(raw or "{}")
    if not isinstance(requested, dict):
        raise ValueError("feature_states must be a JSON object")

    values = []
    for feature in AUTOIDENTIFY_FEATURES:
        if feature in requested:
            values.append(u"[%s,%s]" % (feature, requested[feature]))
        elif fill_missing:
            values.append(u"[%s,0]" % feature)
    return "".join(values)


def _identity_json_arg(args, key):
    value = args.get(key, "")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


TOOLS = [
    _tool("is_button_checked", "Return whether a toggle button is currently checked.", {
        "commandId": {"type": "integer", "description": "3DMPS command ID."},
    }, ["commandId"]),
    _tool("get_bof_tree_data", "Return BOF tree data from 3DMPS when available."),
    _tool("check_3dmps_status", "Check whether the 3DMPS bridge is currently available."),

    _tool("get_ai_process_route_input", "Prepare latest AI process route input and return input.json content."),
    _tool("submit_ai_process_route_output", "Submit externally generated AI process route output JSON and apply it to 3DMPS.", {
        "output_json": {"type": "string", "description": "Generated process route JSON."},
    }, ["output_json"]),
    _tool("get_ai_process_route_status", "Query current AI process route task status."),
    _tool("start_ai_process_route", "Start AI process route generation through the 3DMPS bridge."),
    _tool("generate_ai_process_route", "Run AI process route generation synchronously through the 3DMPS bridge."),

    _tool("check_autoidentify_btn_ok", "Confirm the auto-identify dialog. Requires the dialog to be open."),
    _tool("check_autoidentify_btn_cancel", "Cancel the auto-identify dialog. Requires the dialog to be open."),
    _tool("check_autoidentify_btn_selectall", "Select all auto-identify features. Requires the dialog to be open."),
    _tool("check_autoidentify_btn_deselectall", "Deselect all auto-identify features. Requires the dialog to be open."),
    _tool("get_autoidentify_checkbox_list", "Return the configured auto-identify checkbox list."),
    _tool("set_autoidentify_checkbox_list", "Update selected auto-identify features in the open dialog.", {
        "feature_states": {"type": "string", "description": "JSON object mapping feature name to 0/1."},
    }, ["feature_states"]),
    _tool("run_autoidentify_with_no_dlg", "Run auto-identify without opening the dialog.", {
        "feature_states": {"type": "string", "description": "JSON object mapping feature name to 0/1."},
    }, ["feature_states"]),
    _tool("get_autoidentify_template_list", "Return the auto-identify template list."),
    _tool("use_autoidentify_template", "Load an auto-identify template by name. Requires the dialog to be open.", {
        "template_name": {"type": "string", "description": "Template name without .ini suffix."},
    }, ["template_name"]),
    _tool("use_autoidentify_template_by_index", "Load an auto-identify template by 1-based index. Requires the dialog to be open.", {
        "index": {"type": "integer", "description": "Template index, starting from 1."},
    }, ["index"]),
    _tool("open_and_confirm_autoidentify_dialog", "Open the auto-identify feature dialog, confirm it, and return immediately after the confirmation is accepted."),

    _tool("check_processrapid_btn_ok", "Confirm the process-rapid dialog. Requires the dialog to be open."),

    _tool("get_all_group_template_list", "Return all group template names."),
    _tool("specify_group_template_index", "Select a group template by 1-based index. Requires the dialog to be open.", {
        "index": {"type": "integer", "description": "Template index, starting from 1."},
    }, ["index"]),
    _tool("specify_group_template_name", "Select a group template by name. Requires the dialog to be open.", {
        "template_name": {"type": "string", "description": "Group template name."},
    }, ["template_name"]),
    _tool("group_template_dialog_ok", "Confirm the group template dialog. Requires the dialog to be open."),
    _tool("group_template_dialog_cancel", "Cancel the group template dialog. Requires the dialog to be open."),
    _tool("apply_group_template", "Apply a selected group template to the current 3DMPS file. For a candidate card, pass templateId/filename so the template XML is written to the template library before opening the apply dialog, selecting the template name, and confirming it.", {
        "template_name": {"type": "string", "description": "Group template name. Do not include a path; .xml is optional."},
        "templateId": {"type": "string", "description": "Optional candidate-card templateId. When provided, the tool first generates XML and writes the selected template into the group-template library."},
        "filename": {"type": "string", "description": "Optional XML filename from the selected candidate card."},
    }, ["template_name"]),
    _tool("apply_group_template_full_flow", "Write/apply a selected group template, then continue with auto-identify and AI feature inference in order.", {
        "template_name": {"type": "string", "description": "Group template name. Do not include a path; .xml is optional."},
        "templateId": {"type": "string", "description": "Optional candidate-card templateId. When provided, the tool first generates XML and writes the selected template into the group-template library."},
        "filename": {"type": "string", "description": "Optional XML filename from the selected candidate card."},
        "autoidentify_template_name": {"type": "string", "description": "Optional auto-identify template name. If omitted, the backend chooses the default auto-identify template."},
        "autoidentify_template_index": {"type": "integer", "description": "Optional auto-identify template index, starting from 1."},
    }, ["template_name"]),
    _tool("getAllGroupTemplateList", "CamelCase alias: return all group template names."),
    _tool("specifyGroupTemplateIndex", "CamelCase alias: select a group template by 1-based index.", {
        "index": {"type": "integer", "description": "Template index, starting from 1."},
    }, ["index"]),
    _tool("specifyGroupTemplateName", "CamelCase alias: select a group template by name.", {
        "template_name": {"type": "string", "description": "Group template name."},
    }, ["template_name"]),
    _tool("groupTemplateDialogOk", "CamelCase alias: confirm the group template dialog."),
    _tool("groupTemplateDialogCancel", "CamelCase alias: cancel the group template dialog."),
]

for name, description, _command_id in BUTTON_TOOL_SPECS:
    TOOLS.append(_tool(name, description))


TOOL_PIPE_TARGETS = {
    "get_bof_tree_data": "get_all_bof_item",
    "get_ai_process_route_input": "do_ai_process_route",
    "check_autoidentify_btn_ok": "OnBnClickedOk",
    "check_autoidentify_btn_cancel": "OnBnClickedCancel",
    "check_autoidentify_btn_selectall": "SelectAllFeatures",
    "check_autoidentify_btn_deselectall": "DeselectAllFeatures",
    "get_autoidentify_checkbox_list": "GetAutoIdentifyCheckedList",
    "set_autoidentify_checkbox_list": "SetAutoIdentifyCheckedList",
    "run_autoidentify_with_no_dlg": "set_auto_featidentify_box",
    "get_autoidentify_template_list": "GetExtractDataList",
    "use_autoidentify_template": "setExtractDataList",
    "use_autoidentify_template_by_index": "setExtractDataList",
    "check_processrapid_btn_ok": "OnOK",
    "get_all_group_template_list": "GetAllGroupTemplateList",
    "specify_group_template_index": "SpecifyGroupTemplateIndex",
    "specify_group_template_name": "SpecifyGroupTemplateName",
    "group_template_dialog_ok": "OnBnClickedOk",
    "group_template_dialog_cancel": "OnBnClickedCancel",
    "getAllGroupTemplateList": "GetAllGroupTemplateList",
    "specifyGroupTemplateIndex": "SpecifyGroupTemplateIndex",
    "specifyGroupTemplateName": "SpecifyGroupTemplateName",
    "groupTemplateDialogOk": "OnBnClickedOk",
    "groupTemplateDialogCancel": "OnBnClickedCancel",
}

for name, _description, _command_id in BUTTON_TOOL_SPECS:
    TOOL_PIPE_TARGETS[name] = "do_cmdResponse_by_python"


TOOL_PIPE_BUILDER = {
    "is_button_checked": lambda a: {"arg1": a.get("commandId", a.get("command_id", a.get("arg1", 0)))},
    "get_bof_tree_data": lambda a: {},
    "check_3dmps_status": lambda a: {},
    "get_ai_process_route_input": lambda a: {"arg1": a.get("cmd_id", 1)},
    "submit_ai_process_route_output": lambda a: {"arg1": _identity_json_arg(a, "output_json")},
    "get_ai_process_route_status": lambda a: {},
    "start_ai_process_route": lambda a: {},
    "generate_ai_process_route": lambda a: {},
    "check_autoidentify_btn_ok": lambda a: {},
    "check_autoidentify_btn_cancel": lambda a: {},
    "check_autoidentify_btn_selectall": lambda a: {},
    "check_autoidentify_btn_deselectall": lambda a: {},
    "get_autoidentify_checkbox_list": lambda a: {},
    "set_autoidentify_checkbox_list": lambda a: {"arg1": _feature_state_string(a, fill_missing=False)},
    "run_autoidentify_with_no_dlg": lambda a: {"arg1": _feature_state_string(a, fill_missing=True)},
    "get_autoidentify_template_list": lambda a: {},
    "use_autoidentify_template": lambda a: {"arg1": a.get("template_name", "")},
    "use_autoidentify_template_by_index": lambda a: {"arg1": a.get("index", 0)},
    "check_processrapid_btn_ok": lambda a: {},
    "get_all_group_template_list": lambda a: {},
    "specify_group_template_index": lambda a: {"arg1": a.get("index", 0)},
    "specify_group_template_name": lambda a: {"arg1": a.get("template_name", "")},
    "group_template_dialog_ok": lambda a: {},
    "group_template_dialog_cancel": lambda a: {},
    "getAllGroupTemplateList": lambda a: {},
    "specifyGroupTemplateIndex": lambda a: {"arg1": a.get("index", 0)},
    "specifyGroupTemplateName": lambda a: {"arg1": a.get("template_name", "")},
    "groupTemplateDialogOk": lambda a: {},
    "groupTemplateDialogCancel": lambda a: {},
}

for name, _description, command_id in BUTTON_TOOL_SPECS:
    TOOL_PIPE_BUILDER[name] = (lambda _command_id: (lambda a: {"arg1": _command_id}))(command_id)


KEYWORD_RULES = [
    {"keywords": [u"\u6253\u5f00\u5206\u7ec4\u6a21\u677f", u"\u6253\u5f00\u5206\u7ec4\u6a21\u677f\u5f39\u7a97", u"\u663e\u793a\u5206\u7ec4\u6a21\u677f", u"\u5206\u7ec4\u6a21\u677f\u6309\u94ae", u"\u5206\u7ec4\u6a21\u677f\u7ba1\u7406", "open group template"],
     "tool": "click_group_template_button",
     "reply": u"\u5df2\u8bf7\u6c42 3DMPS \u6253\u5f00\u5206\u7ec4\u6a21\u677f\u5bf9\u8bdd\u6846\u3002"},
    {"keywords": [u"\u68c0\u67e53DMPS\u72b6\u6001", u"\u68c0\u67e53dmps\u72b6\u6001", u"3DMPS\u72b6\u6001", u"3dmps\u72b6\u6001", u"\u670d\u52a1\u72b6\u6001", u"\u8fde\u63a5\u72b6\u6001"],
     "tool": "check_3dmps_status",
     "reply": u"\u5df2\u68c0\u67e5 3DMPS \u670d\u52a1\u72b6\u6001\u3002"},
]


TOOL_TIMEOUTS = {
    "is_button_checked": 5,
    "get_bof_tree_data": 15,
    "check_3dmps_status": 5,
    "get_ai_process_route_input": 120,
    "submit_ai_process_route_output": 120,
    "get_ai_process_route_status": 5,
    "start_ai_process_route": 120,
    "generate_ai_process_route": 120,
    "run_autoidentify_with_no_dlg": 120,
    "get_autoidentify_template_list": 15,
    "get_autoidentify_checkbox_list": 5,
    "open_and_confirm_autoidentify_dialog": 30,
    "apply_group_template": 45,
    "apply_group_template_full_flow": 300,
    "get_all_group_template_list": 15,
    "check_processrapid_btn_ok": 10,
}

for name, _description, _command_id in BUTTON_TOOL_SPECS:
    TOOL_TIMEOUTS[name] = 10
