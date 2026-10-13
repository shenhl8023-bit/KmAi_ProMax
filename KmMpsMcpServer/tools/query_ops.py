# -*- coding: utf-8 -*-
"""数据查询类工具（共 5 个）。

工具列表：
    - get_cur_model_info   获取当前模型基本信息
    - get_process_steps    获取工序列表
    - get_features         获取特征列表
    - get_rough_info       获取毛坯信息
    - get_bop_tree         获取 BOP 工艺树结构
"""

from __future__ import print_function


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_cur_model_info",
            "description": "获取当前打开模型的基本信息（路径、名称、类型等）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_process_steps",
            "description": "获取当前 BOP 工艺树上的工序列表。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_features",
            "description": "获取当前模型的特征列表（仅特征，不含分组与方法）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rough_info",
            "description": "获取当前毛坯信息（毛坯类型、尺寸、余量等）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bop_tree",
            "description": "获取当前 BOP 工艺树结构数据。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


TOOL_PIPE_BUILDER = {
    "get_cur_model_info": lambda a: {},
    "get_process_steps":  lambda a: {},
    "get_features":       lambda a: {},
    "get_rough_info":     lambda a: {},
    "get_bop_tree":       lambda a: {},
}


# 顺序：get_all_bof_item 的规则归 original.py；本模块负责 5 个新查询工具
KEYWORD_RULES = [
    {"keywords": [u"模型信息", u"当前模型", u"打开的模型"],
     "tool": "get_cur_model_info",
     "reply": u"已调用 3DMPS 获取当前模型信息。"},
    {"keywords": [u"工序列表", u"工艺列表", u"工序清单", u"获取工序"],
     "tool": "get_process_steps",
     "reply": u"已调用 3DMPS 获取工序列表。"},
    {"keywords": [u"特征列表", u"所有特征", u"特征数据", u"当前模型特征", u"模型特征"],
     "tool": "get_features",
     "reply": u"已调用 3DMPS 获取特征列表。"},
    {"keywords": [u"毛坯", u"毛坯信息", u"毛坯类型"],
     "tool": "get_rough_info",
     "reply": u"已调用 3DMPS 获取毛坯信息。"},
    {"keywords": [u"bop树", u"bop 树", u"工艺树结构", u"bop工艺"],
     "tool": "get_bop_tree",
     "reply": u"已调用 3DMPS 获取 BOP 工艺树数据。"},
]


# 单次调用超时（秒）
# 全为只读查询，统一给 15s；模型大时 BOP 树可能稍慢也容忍
TOOL_TIMEOUTS = {
    "get_cur_model_info": 15,
    "get_process_steps":  15,
    "get_features":       15,
    "get_rough_info":     15,
    "get_bop_tree":       15,
}
