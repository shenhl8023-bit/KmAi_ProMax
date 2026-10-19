# -*- coding: utf-8 -*-
"""Compatibility bridge for repository build tools and Agent tool imports.

The Agent historically imports ``tools`` after adding ``KmMpsMcpServer`` to
``sys.path``.  The Win7 build utilities also live in a top-level ``tools``
directory, so re-export the application tool registry when the repository root
is first on ``sys.path`` instead of shadowing it with a namespace package.
"""

from KmMpsMcpServer.tools import (  # noqa: F401
    TOOLS,
    TOOL_PIPE_BUILDER,
    TOOL_PIPE_TARGETS,
    KEYWORD_RULES,
    TOOL_TIMEOUTS,
    DEFAULT_TIMEOUT,
    get_timeout,
    get_summary,
)
