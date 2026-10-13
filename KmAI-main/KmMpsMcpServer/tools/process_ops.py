# -*- coding: utf-8 -*-
"""工艺执行类工具（共 10 个）。

工具列表：
    - auto_identify            自动特征识别
    - ai_feature_inference     AI 推理特征加工方法
    - create_step              创建工序节点
    - reset_step_number        重置工序号
    - arrange_step             工序模板编排
    - rapid_create_step        快速创建工序
    - click_generate_all_button 生成全部工序模型
    - check_process_step       工序检查
    - check_model_compare      模型对比
    - show_identify_report     显示识别报告

注意：create_step / arrange_step 当前未配置关键词规则（需 LLM 直接调用）。
"""

from __future__ import print_function


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "auto_identify",
            "description": "打开自动特征识别弹窗，按自动识别模板执行当前模型的自动特征识别。未指定模板时优先选择套筒类模板，其次选择列表第 2 项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "可选，自动识别模板名称，不需要 .ini 后缀。"},
                    "template_index": {"type": "integer", "description": "可选，自动识别模板序号，从 1 开始。"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ai_feature_inference",
            "description": "对当前特征执行 AI 加工方法推理，自动判断每个特征的加工方式。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_step",
            "description": "在 BOP 工艺树上创建一个新的工序节点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_name": {"type": "string", "description": "工序名称（可选）", "default": ""},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_step_number",
            "description": "重新编排当前 BOP 树上所有工序的工序号。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arrange_step",
            "description": "使用工序模板编排 BOP 工艺（标准工艺路线模板应用）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rapid_create_step",
            "description": "快速创建工序（弹出工序快速创建对话框）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_process_step",
            "description": "执行工序检查（验证工序完整性与正确性）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_model_compare",
            "description": "模型对比检查：与另一个模型文件进行几何/拓扑对比。",
            "parameters": {
                "type": "object",
                "properties": {
                    "compare_path": {"type": "string", "description": "待对比的模型文件路径"},
                },
                "required": ["compare_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_identify_report",
            "description": "显示当前模型的特征识别报告（弹出报告窗口）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


TOOL_PIPE_BUILDER = {
    "auto_identify":            lambda a: {k: v for k, v in a.items() if k in ("template_name", "templateName", "template_index", "templateIndex", "index")},
    "ai_feature_inference":     lambda a: {},
    "create_step":              lambda a: {"arg1": a.get("step_name", "")},
    "reset_step_number":        lambda a: {},
    "arrange_step":             lambda a: {},
    "rapid_create_step":        lambda a: {},
    "check_process_step":       lambda a: {},
    "check_model_compare":      lambda a: {"arg1": a.get("compare_path", "")},
    "show_identify_report":     lambda a: {},
}


# create_step / arrange_step 当前不挂关键词规则
KEYWORD_RULES = [
    {"keywords": [u"推理特征", u"特征推理", u"加工方法推理", u"特征加工方法"],
     "tool": "ai_feature_inference",
     "reply": u"已请求 3DMPS 对特征执行 AI 加工方法推理。"},
    {"keywords": [u"自动识别", u"自动拾取", u"识别特征"],
     "tool": "auto_identify",
     "reply": u"已请求 3DMPS 执行自动特征识别。"},
    {"keywords": [u"识别报告", u"特征报告", u"识别结果"],
     "tool": "show_identify_report",
     "reply": u"已请求 3DMPS 显示特征识别报告。"},
    {"keywords": [u"工序检查", u"检查工序"],
     "tool": "check_process_step",
     "reply": u"已请求 3DMPS 执行工序检查。"},
    {"keywords": [u"快速创建工序", u"快速建工序"],
     "tool": "rapid_create_step",
     "reply": u"已请求 3DMPS 快速创建工序。"},
    {"keywords": [u"重置工序号", u"工序号重置", u"重新编号"],
     "tool": "reset_step_number",
     "reply": u"已请求 3DMPS 重置工序号。"},
    {"keywords": [u"生成工序模型", u"生成中间模型", u"生成工艺模型"],
     "tool": "click_generate_all_button",
     "reply": u"已请求 3DMPS 生成全部工序模型。"},
    {"keywords": [u"模型对比", u"对比模型", u"模型校验"],
     "tool": "check_model_compare", "needs_path": True,
     "path_hint": u"请提供待对比的模型路径。",
     "reply": u"已请求 3DMPS 执行模型对比。"},
]


# 单次调用超时（秒）
# 识别 / 工艺生成 / 模型生成 与 模型对比 比较耗时；UI 类（弹窗/重编号）很快
TOOL_TIMEOUTS = {
    "auto_identify":            120,  # 自动特征识别（含几何运算）
    "ai_feature_inference":     120,  # AI 推理
    "create_step":               10,  # 创建单个节点
    "reset_step_number":         10,
    "arrange_step":              30,  # 模板编排
    "rapid_create_step":         10,  # 弹对话框
    "create_process_model_all": 180,  # 全部工序模型生成
    "check_process_step":        30,
    "check_model_compare":      300,  # 几何/拓扑对比可能很慢
    "show_identify_report":      10,  # 弹报告窗口
}
