# -*- coding: utf-8 -*-
from __future__ import print_function

from .autoidentify_service import (
    AUTOIDENTIFY_FEATURE_NAMES,
    AutoIdentifyServiceMixin,
)
from .bof_formatter import BofFormatterMixin
from .chat_service import ChatServiceMixin
from .group_template_service import GroupTemplateServiceMixin
from .llm_service import LlmServiceMixin, create_initial_llm_client
from .pipe_client import PIPE_NAME, StubPipeClient, _IS_WINDOWS
from .session_store import SessionStore
from .tool_dispatcher import COMPOSITE_TOOL_NAMES, ToolDispatcherMixin

if _IS_WINDOWS:
    from .pipe_client import NamedPipeClient as _PipeClientClass
else:
    _PipeClientClass = StubPipeClient

_SessionStore = SessionStore


class MiniAgent(
        ChatServiceMixin,
        LlmServiceMixin,
        ToolDispatcherMixin,
        AutoIdentifyServiceMixin,
        GroupTemplateServiceMixin,
        BofFormatterMixin):
    def __init__(self):
        self.pipe = _PipeClientClass(PIPE_NAME)
        self.llm = create_initial_llm_client()
        self.conversations = SessionStore()
