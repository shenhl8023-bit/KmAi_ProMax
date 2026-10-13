# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import sys

import kmrag_search


def run_request(request, environ=None):
    request = request if isinstance(request, dict) else {}
    return kmrag_search.search(request.get("query"), environ=environ)


def read_request(stream):
    try:
        raw = stream.buffer.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw or "{}")
    except (ValueError, json.JSONDecodeError):
        return {}


def main():
    request = read_request(sys.stdin)
    # Windows text stdout follows the active code page; the runner consumes UTF-8 bytes.
    sys.stdout.buffer.write(json.dumps(run_request(request), ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
