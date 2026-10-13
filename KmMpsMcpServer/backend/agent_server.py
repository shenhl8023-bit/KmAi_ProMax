#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse

try:
    from http.server import HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:
    from BaseHTTPServer import HTTPServer
    from SocketServer import ThreadingMixIn

from . import agent_config
from .http_api import AgentRequestHandler
from .pipe_client import PIPE_NAME


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持并发 SSE 连接。"""

    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=u"AI小沐本地智能体服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9095)
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.host, args.port), AgentRequestHandler)
    llm_enabled = agent_config._is_llm_config_enabled(agent_config.CONFIG)
    print("AI小沐 Agent listening on http://%s:%s" % (args.host, args.port))
    print("LLM 模式: %s" % ("已启用" if llm_enabled else "未启用（关键词匹配）"))
    print("命名管道: %s" % PIPE_NAME)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
