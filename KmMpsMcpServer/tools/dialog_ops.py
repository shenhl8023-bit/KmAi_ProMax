# -*- coding: utf-8 -*-
"""3DMPS 弹窗自动化工具。

这些函数来自 C++ 端若干对话框在打开时临时注册到 PythonBridge 的函数。
只有对应弹窗处于激活/注册状态时才可调用；否则主程序会返回 Function not found。
"""

from __future__ import print_function


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedCancel",
            "description": "取消或关闭当前已激活的3DMPS自动化弹窗。仅当用户明确要取消当前弹窗时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedOk",
            "description": "确认当前已激活的3DMPS弹窗（适用于自动特征识别方向弹窗、分组模板管理弹窗等使用 OnBnClickedOk 的窗口）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnOK",
            "description": "确认当前快速工艺编排弹窗。仅当快速工艺编排弹窗处于激活状态且用户要求确认时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SelectAllFeatures",
            "description": "在自动特征识别方向弹窗中全选特征类型。仅当该弹窗已打开时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "DeselectAllFeatures",
            "description": "在自动特征识别方向弹窗中取消全选特征类型。仅当该弹窗已打开时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SetAutoIdentifyCheckedList",
            "description": "设置自动特征识别方向弹窗中的特征勾选列表。格式示例：[孔,1][槽,0]，1表示勾选，0表示取消。",
            "parameters": {
                "type": "object",
                "properties": {
                    "checked_list": {
                        "type": "string",
                        "description": "特征勾选列表字符串，例如：[孔,1][槽,0]。",
                    },
                },
                "required": ["checked_list"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GetAutoIdentifyCheckedList",
            "description": "获取自动特征识别方向弹窗中当前特征勾选列表，返回形如 [特征名,1][特征名,0] 的字符串。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GetExtractDataList",
            "description": "获取自动特征识别方向弹窗可用的自动识别模板/提取数据文件列表。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "setExtractDataList",
            "description": "在自动特征识别方向弹窗中按模板名称加载自动识别模板数据。名称不需要带 .ini 后缀。",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "自动识别模板名称，不含 .ini 后缀。",
                    },
                },
                "required": ["template_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedAddStep",
            "description": "在快速工艺编排弹窗中添加/创建一个工序。仅当该弹窗已打开时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedDelStep",
            "description": "在快速工艺编排弹窗中删除当前选中的工序。仅当该弹窗已打开且已有选中工序时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedAddMethodButton",
            "description": "在快速工艺编排弹窗中把左侧选中的加工方法添加到右侧。仅当该弹窗已打开且已有选中方法时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "OnBnClickedHeader",
            "description": "触发快速工艺编排弹窗表头全选/反选事件。通常无需传参数，只有明确知道 WPARAM/LPARAM 时才传。",
            "parameters": {
                "type": "object",
                "properties": {
                    "wparam": {"type": "integer", "description": "Windows WPARAM，默认0。", "default": 0},
                    "lparam": {"type": "integer", "description": "Windows LPARAM，默认0。", "default": 0},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GetAllGroupTemplateList",
            "description": "获取分组模板管理弹窗中的全部分组模板名称列表，返回形如 [模板A][模板B] 的字符串。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SpecifyGroupTemplateIndex",
            "description": "在分组模板管理弹窗中按序号选中分组模板。序号从1开始。",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "模板序号，从1开始。"},
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SpecifyGroupTemplateName",
            "description": "在分组模板管理弹窗中按模板名称选中分组模板。",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "要选中的分组模板名称。"},
                },
                "required": ["template_name"],
            },
        },
    },
]


TOOL_PIPE_BUILDER = {
    "OnBnClickedCancel": lambda a: {},
    "OnBnClickedOk": lambda a: {},
    "OnOK": lambda a: {},
    "SelectAllFeatures": lambda a: {},
    "DeselectAllFeatures": lambda a: {},
    "SetAutoIdentifyCheckedList": lambda a: {"arg1": a.get("checked_list", a.get("arg1", ""))},
    "GetAutoIdentifyCheckedList": lambda a: {},
    "GetExtractDataList": lambda a: {},
    "setExtractDataList": lambda a: {"arg1": a.get("template_name", a.get("arg1", ""))},
    "OnBnClickedAddStep": lambda a: {},
    "OnBnClickedDelStep": lambda a: {},
    "OnBnClickedAddMethodButton": lambda a: {},
    "OnBnClickedHeader": lambda a: {"arg1": a.get("wparam", a.get("arg1", 0)),
                                    "arg2": a.get("lparam", a.get("arg2", 0))},
    "GetAllGroupTemplateList": lambda a: {},
    "SpecifyGroupTemplateIndex": lambda a: {"arg1": a.get("index", a.get("arg1", 0))},
    "SpecifyGroupTemplateName": lambda a: {"arg1": a.get("template_name", a.get("arg1", ""))},
}


# 弹窗工具只能在具体 UI 上下文中安全调用，不参与关键词兜底。
KEYWORD_RULES = []


TOOL_TIMEOUTS = {
    "OnBnClickedCancel": 5,
    "OnBnClickedOk": 5,
    "OnOK": 5,
    "SelectAllFeatures": 5,
    "DeselectAllFeatures": 5,
    "SetAutoIdentifyCheckedList": 5,
    "GetAutoIdentifyCheckedList": 5,
    "GetExtractDataList": 15,
    "setExtractDataList": 15,
    "OnBnClickedAddStep": 10,
    "OnBnClickedDelStep": 10,
    "OnBnClickedAddMethodButton": 10,
    "OnBnClickedHeader": 5,
    "GetAllGroupTemplateList": 10,
    "SpecifyGroupTemplateIndex": 5,
    "SpecifyGroupTemplateName": 5,
}
