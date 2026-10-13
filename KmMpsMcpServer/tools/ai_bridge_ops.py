# -*- coding: utf-8 -*-
"""AI 桥接类工具。

这些工具对应 3DMPS C++ 主窗口中已经常驻注册到 PythonBridge 的函数，
按 original.py 的模式包装为 LLM 可调用工具。
"""

from __future__ import print_function


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_auto_featidentify_box",
            "description": "根据指定的特征勾选/选择字符串执行自动特征识别。调用前应先打开模型；选择字符串格式沿用3DMPS端约定，例如：[孔,1][槽,0]。",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_selection": {
                        "type": "string",
                        "description": "自动特征识别的特征选择字符串，UTF-8文本，按3DMPS可解析格式传入。",
                    },
                },
                "required": ["feature_selection"],
            },
        },
    },
]


TOOL_PIPE_BUILDER = {
    "set_auto_featidentify_box": lambda a: {
        "arg1": a.get("feature_selection", a.get("arg1", "")),
    },
    "do_cmdResponse_by_python": lambda a: {
        "arg1": a.get("command_id", a.get("arg1", 0)),
    },
}


# 这两个工具都依赖较强上下文，不做无 LLM 关键词兜底，避免误触发。
KEYWORD_RULES = []


TOOL_TIMEOUTS = {
    "set_auto_featidentify_box": 120,
    "do_cmdResponse_by_python": 5,
}
