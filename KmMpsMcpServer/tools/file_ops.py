# -*- coding: utf-8 -*-
"""文件 / 模型操作类工具（共 7 个）。

工具列表：
    - close_prt_file       关闭当前模型
    - save_file            保存到原路径
    - save_as              另存为新路径
    - export_pdf           导出 PDF 工艺文件
    - export_excel         导出 Excel 工艺文件
    - export_gxk           导出 GXK 工艺文件
    - auto_save            自动保存开关
"""

from __future__ import print_function


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "close_prt_file",
            "description": "关闭当前已打开的3D模型文件。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": "保存当前打开的3D模型到原路径，不弹保存对话框。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_as",
            "description": "将当前模型另存为新路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "新的保存路径，如 D:\\new.prt"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_pdf",
            "description": "将当前工艺文件导出为 PDF 格式。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_excel",
            "description": "将当前工艺文件导出为 Excel 格式（包含工序卡片等）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_gxk",
            "description": "将当前工艺文件导出为 GXK 格式。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "auto_save",
            "description": "开启/关闭 3DMPS 自动保存功能。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


TOOL_PIPE_BUILDER = {
    "close_prt_file": lambda a: {},
    "save_file":      lambda a: {},
    "save_as":        lambda a: {"arg1": a.get("file_path", "")},
    "export_pdf":     lambda a: {},
    "export_excel":   lambda a: {},
    "export_gxk":     lambda a: {},
    "auto_save":      lambda a: {},
}


# 顺序说明：
#   1) 另存为/保存到 比 通用「保存」 更具体，必须排在前面
#   2) 关闭/自动保存 等关键词互不冲突，按业务顺序排列
#   3) 导出三种格式（PDF/Excel/GXK）前缀相同，列在一起
KEYWORD_RULES = [
    {"keywords": [u"另存为", u"保存到"], "tool": "save_as",
     "needs_path": True,
     "path_hint": u"请提供新保存路径，例如：另存为 D:\\new.prt",
     "reply": u"已请求 3DMPS 另存为新路径。"},
    {"keywords": [u"关闭模型", u"关闭文件", u"关闭当前"], "tool": "close_prt_file",
     "reply": u"已请求 3DMPS 关闭当前模型。"},
    {"keywords": [u"保存", u"存盘"], "tool": "save_file",
     "reply": u"已请求 3DMPS 保存当前模型。"},
    {"keywords": [u"自动保存"], "tool": "auto_save",
     "reply": u"已请求 3DMPS 切换自动保存开关。"},
    {"keywords": [u"导出pdf", u"导出PDF", u"输出pdf", u"输出PDF", u"导出 pdf"],
     "tool": "export_pdf", "reply": u"已请求 3DMPS 导出 PDF 工艺文件。"},
    {"keywords": [u"导出excel", u"导出Excel", u"输出excel", u"输出Excel", u"导出 xlsx"],
     "tool": "export_excel", "reply": u"已请求 3DMPS 导出 Excel 工艺文件。"},
    {"keywords": [u"导出gxk", u"导出GXK", u"输出gxk", u"输出GXK"],
     "tool": "export_gxk", "reply": u"已请求 3DMPS 导出 GXK 工艺文件。"},
]


# 单次调用超时（秒）
# 导出 PDF/Excel/GXK 在大模型/大工艺下可能较慢，故给 60s
TOOL_TIMEOUTS = {
    "close_prt_file": 10,
    "save_file":      30,
    "save_as":        30,
    "export_pdf":     60,
    "export_excel":   60,
    "export_gxk":     60,
    "auto_save":       5,   # 仅切换开关，应该瞬间完成
}