# -*- coding: utf-8 -*-
"""原有 4 个工具。

这 4 个工具是最早期就实现并通过验证的，单独保留以便对照历史版本。
所有工具都依赖 3DMPS 主程序（Km3dmps.exe）的命名管道服务端暴露对应函数。
"""

from __future__ import print_function


# ============================================
# OpenAI function calling 格式的工具定义
# ============================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "process_prt_file",
            "description": "打开模型并自动执行特征识别和工艺路线生成，返回完整结果。适合一次性完成整个处理流程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "模型文件的完整路径"},
                    "trace_id": {"type": "string", "description": "追踪ID（可选，用于日志关联）", "default": ""},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_prt_file",
            "description": "打开一个3D模型文件（.prt, .CATPart, .Z3PRT等），需要在3DMPS中加载模型时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "模型文件的完整路径，如 D:\\test.prt"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_bof_item",
            "description": "获取当前打开模型的BOF特征树数据，包括所有特征、分组、加工方法。返回当前工作模型的结构信息。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "do_ai_process_route",
            "description": "执行AI工艺路线推理，自动生成工序编排。根据当前BOF特征树数据推导加工工艺。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd_id": {"type": "integer", "description": "命令ID，默认为1", "default": 1},
                },
                "required": [],
            },
        },
    },
]


# ============================================
# 工具参数构建器（LLM args → 管道 params）
# ============================================

TOOL_PIPE_BUILDER = {
    "process_prt_file":    lambda a: {"arg1": a.get("file_path", ""),
                                     "arg2": a.get("trace_id", "")},
    "open_prt_file":       lambda a: {"arg1": a.get("file_path", "")},
    "get_all_bof_item":    lambda a: {},
    "do_ai_process_route": lambda a: {"arg1": a.get("cmd_id", 1)},
}


# ============================================
# 关键词规则（无 LLM 时的回退匹配）
# ============================================

KEYWORD_RULES = [
    {"keywords": [u"一站式", u"一键处理"], "tool": "process_prt_file",
     "needs_path": True,
     "path_hint": u"请提供模型路径，例如：一站式处理 D:\\test.prt",
     "reply": u"已请求 3DMPS 一站式处理模型（含特征识别+工艺生成）。"},

    {"keywords": [u"打开模型", u"打开文件"], "tool": "open_prt_file",
     "needs_path": True,
     "path_hint": u"请提供模型路径，例如：打开模型 D:\\test.prt",
     "reply": u"已请求 3DMPS 打开模型。"},

    {"keywords": [u"bof", u"结构树", u"特征树", u"当前数据", u"零件信息"],
     "tool": "get_all_bof_item",
     "reply": u"已调用 3DMPS 获取当前 BOF/特征树数据。"},

    {"keywords": [u"工艺路线", u"生成路线", u"生成工艺", u"工艺编排", u"自动编排"],
     "tool": "do_ai_process_route", "params": {"arg1": 1},
     "reply": u"已请求 3DMPS 执行 AI 工艺路线生成。"},
]


# ============================================
# 单次调用超时（秒）
# ============================================
# 仅在「与原默认 30s 不一致」的工具上显式列出，避免无意义噪声。
# 一站式与 AI 推理比较慢，查询类比较快。

TOOL_TIMEOUTS = {
    "process_prt_file":     180,   # 打开 + 识别 + 工艺生成（复合操作）
    "open_prt_file":         30,
    "get_all_bof_item":      15,   # 只读查询
    "do_ai_process_route":  120,   # AI 推理
}