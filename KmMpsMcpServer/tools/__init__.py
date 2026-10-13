# -*- coding: utf-8 -*-
"""3DMPS AI 工具集合（按业务域拆分）。

各子模块按职责划分：
    - original      原有 4 个基础工具（当前主程序已验证可用）
    - ai_bridge_ops 主窗口 AI 桥接工具（当前主程序已注册）
    - dialog_ops    弹窗自动化工具（仅对应弹窗激活时可用，默认不注册）
    - file_ops      文件/模型操作类工具（待主程序暴露后启用）
    - process_ops   工艺执行类工具（待主程序暴露后启用）
    - query_ops     数据查询类工具（待主程序暴露后启用）

每个子模块导出四个聚合对象：
    - TOOLS              OpenAI function calling 格式的工具定义列表
    - TOOL_PIPE_BUILDER  工具名 -> 管道参数构建器（lambda）的字典
    - KEYWORD_RULES      关键词 -> 工具 的规则列表
    - TOOL_TIMEOUTS      工具名 -> 单次调用超时（秒）的字典

新增域的步骤：
    1) 在 tools/ 下新建 my_domain.py，定义上述四个对象
    2) 在下方 _MODULES 列表中追加该模块名

临时禁用某个域：将其从 _MODULES 列表中注释即可。
"""

from __future__ import print_function

from . import original
from . import ai_bridge_ops
from . import file_ops
from . import process_ops
from . import query_ops
from . import reference_ops
# dialog_ops 中的原始弹窗函数仍不默认注册；reference_ops 只暴露参考 MCP 项目中的
# 业务化别名，并在描述里标注需要弹窗上下文的工具，避免模型直接使用内部函数名。

_MODULES = [original, ai_bridge_ops, query_ops, file_ops, process_ops, reference_ops]


def _aggregate():
    """合并所有子模块的工具定义、参数构建器、关键词规则与超时配置。"""
    tools = []
    builders = {}
    targets = {}
    rules = []
    timeouts = {}
    for module in _MODULES:
        tools.extend(module.TOOLS)
        builders.update(module.TOOL_PIPE_BUILDER)
        targets.update(getattr(module, "TOOL_PIPE_TARGETS", {}))
        rules.extend(module.KEYWORD_RULES)
        timeouts.update(module.TOOL_TIMEOUTS)
    return tools, builders, targets, rules, timeouts


TOOLS, TOOL_PIPE_BUILDER, TOOL_PIPE_TARGETS, KEYWORD_RULES, TOOL_TIMEOUTS = _aggregate()


# 默认超时：未在 TOOL_TIMEOUTS 中显式配置的工具使用此值
DEFAULT_TIMEOUT = 30


def get_timeout(tool_name, default=None):
    """查询工具的调用超时（秒）。

    未配置的工具返回 default（默认 DEFAULT_TIMEOUT=30）。
    """
    if default is None:
        default = DEFAULT_TIMEOUT
    return TOOL_TIMEOUTS.get(tool_name, default)


def get_summary():
    """返回工具集合的统计信息（用于调试 / 健康检查）。"""
    return {
        "modules": [m.__name__.split(".")[-1] for m in _MODULES],
        "tools_count": len(TOOLS),
        "builders_count": len(TOOL_PIPE_BUILDER),
        "targets_count": len(TOOL_PIPE_TARGETS),
        "rules_count": len(KEYWORD_RULES),
        "timeouts_count": len(TOOL_TIMEOUTS),
        "default_timeout": DEFAULT_TIMEOUT,
        "tool_names": [t["function"]["name"] for t in TOOLS],
    }
