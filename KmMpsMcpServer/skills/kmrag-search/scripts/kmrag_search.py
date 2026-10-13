# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
from urllib import error, request


MAX_QUERY_LENGTH = 2000
MAX_RECORDS = 5
MAX_CONTENT_LENGTH = 1200
MAX_TOTAL_CONTENT_LENGTH = 6000
METADATA_KEYS = (
    "source_id", "chunk_id", "page", "page_number", "title", "section", "collection_id",
)


def _error(code, message):
    return {"ok": False, "error_code": code, "message": message, "records": []}


def _safe_text(value, limit):
    return str(value or "")[:limit]


def sanitize_result(query, response):
    data = response.get("data", response) if isinstance(response, dict) else {}
    raw_records = data.get("records", []) if isinstance(data, dict) else []
    if not isinstance(raw_records, list):
        return _error("KMRAG_BAD_RESPONSE", "知识库检索服务返回的数据格式无效。")

    records = []
    total_content_length = 0
    for item in raw_records[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        remaining = MAX_TOTAL_CONTENT_LENGTH - total_content_length
        if remaining <= 0:
            break
        content = _safe_text(item.get("content"), min(MAX_CONTENT_LENGTH, remaining))
        total_content_length += len(content)
        metadata = item.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        records.append({
            "content": content,
            "score": item.get("score"),
            "recall_type": _safe_text(item.get("recall_type"), 80),
            "metadata": {key: metadata[key] for key in METADATA_KEYS if key in metadata},
        })
    return {"ok": True, "query": query, "records": records}


def search(query, environ=None, opener=None):
    environ = os.environ if environ is None else environ
    query = str(query or "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return _error("INVALID_QUERY", "检索问题不能为空，且不能超过 2000 个字符。")
    if str(environ.get("KMRAG_ENABLED", "false")).lower() not in ("1", "true", "yes", "on"):
        return _error("KMRAG_NOT_CONFIGURED", "KMRAG 知识库检索未启用或未配置。")
    base_url = str(environ.get("KMRAG_BASE_URL", "")).strip().rstrip("/")
    api_key = str(environ.get("KMRAG_API_KEY", "")).strip()
    bearer_token = str(environ.get("KMRAG_BEARER_TOKEN", "")).strip()
    if not base_url or not (api_key or bearer_token):
        return _error("KMRAG_NOT_CONFIGURED", "KMRAG 知识库检索未启用或未配置。")
    payload = {
        "query": query,
        "vector_search": {"topk": 5, "similarity": 0.5},
        "fulltext_search": {"topk": 5},
        "rerank": True,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    else:
        headers["Authorization"] = "Bearer " + bearer_token
    try:
        timeout = float(environ.get("KMRAG_TIMEOUT", 30))
        req = request.Request(base_url + "/api/v2/collections/search", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        if opener is None:
            opener = request.build_opener(request.ProxyHandler({})).open
        response = opener(req, timeout=max(1.0, min(timeout, 120.0)))
        with response:
            body = response.read().decode("utf-8")
        return sanitize_result(query, json.loads(body))
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            return _error("KMRAG_AUTH_FAILED", "KMRAG 鉴权失败，请检查本机配置。")
        return _error("KMRAG_BAD_RESPONSE", "知识库检索服务返回异常。")
    except error.URLError:
        return _error("KMRAG_UNREACHABLE", "无法连接 KMRAG 知识库检索服务。")
    except TimeoutError:
        return _error("KMRAG_TIMEOUT", "KMRAG 知识库检索超时。")
    except (ValueError, json.JSONDecodeError):
        return _error("KMRAG_BAD_RESPONSE", "知识库检索服务返回的数据格式无效。")
    except Exception:
        return _error("KMRAG_UNREACHABLE", "无法连接 KMRAG 知识库检索服务。")
