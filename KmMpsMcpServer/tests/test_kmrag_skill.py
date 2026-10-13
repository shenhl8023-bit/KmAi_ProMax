# -*- coding: utf-8 -*-
import io
import json
import os
import sys
import unittest
from unittest import mock


SKILL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "skills", "kmrag-search", "scripts"))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

import kmrag_search
import kmai_kmrag_search


class _FakeResponse(object):
    def __init__(self, payload):
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._body


class _DirectOpener(object):
    def __init__(self, response):
        self._response = response

    def open(self, req, timeout):
        return self._response


class _BinaryStdin(object):
    def __init__(self, payload):
        self.buffer = io.BytesIO(payload)


class KmragSkillTests(unittest.TestCase):
    def test_sanitize_result_filters_metadata_and_limits_records(self):
        response = {
            "data": {
                "records": [{
                    "content": "x" * 1300,
                    "score": 0.9,
                    "recall_type": "vector",
                    "metadata": {"title": "规范", "secret": "must-not-leak"},
                }] * 6
            }
        }

        result = kmrag_search.sanitize_result("供应商准入", response)

        self.assertTrue(result["ok"])
        self.assertEqual(5, len(result["records"]))
        self.assertEqual(1200, len(result["records"][0]["content"]))
        self.assertEqual({"title": "规范"}, result["records"][0]["metadata"])

    def test_run_request_rejects_invalid_query_without_network(self):
        result = kmai_kmrag_search.run_request({"query": " "})

        self.assertEqual(False, result["ok"])
        self.assertEqual("INVALID_QUERY", result["error_code"])

    def test_read_request_decodes_utf8_stdin_independent_of_windows_code_page(self):
        payload = json.dumps({"query": "3dmps是什么"}, ensure_ascii=False).encode("utf-8")

        request_data = kmai_kmrag_search.read_request(_BinaryStdin(payload))

        self.assertEqual("3dmps是什么", request_data["query"])

    def test_search_does_not_expose_configuration_in_error(self):
        result = kmrag_search.search("制度", environ={"KMRAG_ENABLED": "true"})

        self.assertEqual(False, result["ok"])
        self.assertEqual("KMRAG_NOT_CONFIGURED", result["error_code"])
        self.assertNotIn("BASE_URL", result["message"])

    def test_search_uses_direct_connection_instead_of_system_proxy(self):
        response = _FakeResponse({
            "code": 0,
            "ok": True,
            "success": True,
            "data": {
                "records": [{
                    "content": "3DMPS 是三维机械加工工艺设计软件。",
                    "score": 0.95,
                    "recall_type": "vector_search",
                    "metadata": {"collection_id": "collection-1"},
                }],
            },
        })
        direct_opener = _DirectOpener(response)
        environ = {
            "KMRAG_ENABLED": "true",
            "KMRAG_BASE_URL": "https://rag.example.test",
            "KMRAG_API_KEY": "test-key",
            "KMRAG_TIMEOUT": "30",
        }

        with mock.patch.object(kmrag_search.request, "build_opener", return_value=direct_opener), \
                mock.patch.object(kmrag_search.request, "urlopen", side_effect=AssertionError("system proxy used")):
            result = kmrag_search.search("3dmps是什么", environ=environ)

        self.assertTrue(result["ok"])
        self.assertEqual(1, len(result["records"]))
        self.assertIn("3DMPS", result["records"][0]["content"])


if __name__ == "__main__":
    unittest.main()
