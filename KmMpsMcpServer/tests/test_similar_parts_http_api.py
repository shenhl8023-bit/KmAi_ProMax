# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import ctypes
import json
import threading
import unittest
from http.server import HTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError


class _FakeFunction(object):
    argtypes = None
    restype = None

    def __call__(self, *args, **kwargs):
        return 0


class _FakeKernel(object):
    def __getattr__(self, _name):
        return _FakeFunction()


if not hasattr(ctypes, "WinDLL"):
    ctypes.WinDLL = lambda *args, **kwargs: _FakeKernel()

from backend import http_api
from backend.similar_parts_service import SimilarPartsError


class _StubService(object):
    def __init__(self):
        self.calls = []

    def upload_xml(self, filename, content):
        self.calls.append(("upload", filename, content))
        if filename == "bad.XML":
            raise SimilarPartsError("NOT_KMSOFT_XML", "不是有效的开目 XML", 422)
        return {"uploadId": "upload-1", "filename": filename, "size": len(content)}

    def query(self, upload_id, top_k=3):
        self.calls.append(("query", upload_id, top_k))
        return {"uploadId": upload_id, "current": {"modelUrl": "/api/similar-parts/models/current.glb"}, "candidates": []}

    def load_current_part(self):
        self.calls.append(("current",))
        return {
            "uploadId": "upload-current",
            "filename": "AIBasicInfo.xml",
            "size": 3,
            "stepFilename": "stepModel.stp",
            "stepPath": "/private/current/stepModel.stp",
        }

    def get_model(self, model_id):
        self.calls.append(("model", model_id))
        if model_id == "missing":
            raise SimilarPartsError("MODEL_NOT_FOUND", "模型不存在或已过期", 404)
        return b"glTF-test", {"name": "零件"}

    def get_candidate_template(self, upload_id, candidate_id):
        self.calls.append(("template", upload_id, candidate_id))
        return {"filename": "套筒类模板.xml", "xml": "<Kmsoft/>"}

    def prepare_template(self, upload_id, candidate_id, destination_dir, edited_template=None):
        self.calls.append(("prepare", upload_id, candidate_id, destination_dir, edited_template))
        filename = (edited_template or {}).get("filename") or "套筒类.xml"
        return {"templateName": filename[:-4], "templateFilename": filename}


class _StubAgent(object):
    def __init__(self):
        self.calls = []

    def tool(self, name, params, timeout=None):
        self.calls.append((name, params, timeout))
        return {"status": "success", "message": "已应用"}


class SimilarPartsHttpApiTests(unittest.TestCase):
    def setUp(self):
        self.original_service = http_api.SIMILAR_PARTS
        self.original_agent = http_api.AGENT
        self.original_token = http_api.API_AUTH_TOKEN
        self.service = _StubService()
        self.agent = _StubAgent()
        http_api.SIMILAR_PARTS = self.service
        http_api.AGENT = self.agent
        http_api.API_AUTH_TOKEN = "test-token"
        self.server = HTTPServer(("127.0.0.1", 0), http_api.AgentRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()
        http_api.SIMILAR_PARTS = self.original_service
        http_api.AGENT = self.original_agent
        http_api.API_AUTH_TOKEN = self.original_token

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            self.base + path,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-KmAI-Token": "test-token",
                "Origin": self.base,
            },
            method="POST",
        )
        return urlrequest.urlopen(req, timeout=5)

    def get(self, path, token=True):
        headers = {"Origin": self.base}
        if token:
            headers["X-KmAI-Token"] = "test-token"
        return urlrequest.urlopen(urlrequest.Request(self.base + path, headers=headers), timeout=5)

    def test_upload_query_model_and_apply_routes(self):
        upload = json.loads(self.post("/api/similar-parts/upload", {
            "filename": "当前零件.XML",
            "contentBase64": base64.b64encode(b"xml").decode("ascii"),
        }).read().decode("utf-8"))
        self.assertEqual(upload["result"]["uploadId"], "upload-1")

        query = json.loads(self.post("/api/similar-parts/query", {"uploadId": "upload-1", "topK": 3}).read().decode("utf-8"))
        self.assertEqual(query["result"]["uploadId"], "upload-1")

        model = self.get("/api/similar-parts/models/current.glb")
        self.assertEqual(model.headers.get_content_type(), "model/gltf-binary")
        self.assertEqual(model.read(), b"glTF-test")

        applied = json.loads(self.post("/api/similar-parts/apply-template", {
            "uploadId": "upload-1", "candidateId": "candidate-1"
        }).read().decode("utf-8"))
        self.assertEqual(applied["status"], "success")
        self.assertEqual(self.agent.calls, [("apply_group_template", {"template_name": "套筒类"}, 120)])

    def test_candidate_template_route_and_edited_apply_payload(self):
        template = json.loads(self.post("/api/similar-parts/template", {
            "uploadId": "upload-1", "candidateId": "candidate-1"
        }).read().decode("utf-8"))
        self.assertEqual(template["result"]["filename"], "套筒类模板.xml")
        self.assertEqual(template["result"]["xml"], "<Kmsoft/>")

        edited = {
            "filename": "套筒类模板-编辑.xml",
            "xml": "<?xml version=\"1.0\"?><Kmsoft/>",
        }
        applied = json.loads(self.post("/api/similar-parts/apply-template", {
            "uploadId": "upload-1",
            "candidateId": "candidate-1",
            "editedTemplate": edited,
        }).read().decode("utf-8"))

        self.assertEqual(applied["template"]["templateFilename"], "套筒类模板-编辑.xml")
        self.assertIn(("template", "upload-1", "candidate-1"), self.service.calls)
        self.assertTrue(any(call[-1] == edited for call in self.service.calls if call[0] == "prepare"))
        self.assertEqual(
            self.agent.calls[-1],
            ("apply_group_template", {"template_name": "套筒类模板-编辑"}, 120),
        )

    def test_current_route_loads_fixed_part_without_browser_upload(self):
        current = json.loads(self.post("/api/similar-parts/current", {}).read().decode("utf-8"))
        self.assertEqual(current["result"]["uploadId"], "upload-current")
        self.assertEqual(current["result"]["stepFilename"], "stepModel.stp")
        self.assertNotIn("stepPath", current["result"])
        self.assertEqual(self.service.calls, [("current",)])

    def test_query_delegates_default_count_to_service_config(self):
        json.loads(self.post("/api/similar-parts/query", {"uploadId": "upload-1"}).read().decode("utf-8"))

        self.assertEqual(self.service.calls, [("query", "upload-1", None)])

    def test_invalid_base64_and_service_errors_are_stable(self):
        with self.assertRaises(HTTPError) as invalid:
            self.post("/api/similar-parts/upload", {"filename": "part.XML", "contentBase64": "%%%"})
        self.assertEqual(invalid.exception.code, 400)
        payload = json.loads(invalid.exception.read().decode("utf-8"))
        self.assertEqual(payload["error_code"], "INVALID_BASE64")

        with self.assertRaises(HTTPError) as bad_xml:
            self.post("/api/similar-parts/upload", {
                "filename": "bad.XML", "contentBase64": base64.b64encode(b"bad").decode("ascii")
            })
        self.assertEqual(bad_xml.exception.code, 422)
        payload = json.loads(bad_xml.exception.read().decode("utf-8"))
        self.assertEqual(payload["error_code"], "NOT_KMSOFT_XML")
        self.assertNotIn("trace", payload)

    def test_local_three_assets_are_served_without_api_token_and_block_traversal(self):
        response = self.get("/similar-assets/three/LICENSE", token=False)
        self.assertEqual(response.status, 200)
        self.assertIn(b"MIT", response.read())
        addon = self.get("/similar-assets/three/examples/jsm/controls/OrbitControls.js", token=False)
        self.assertEqual(addon.status, 200)
        self.assertIn(b"from '/similar-assets/three/build/three.module.js'", addon.read())
        with self.assertRaises(HTTPError) as traversal:
            self.get("/similar-assets/../README.md", token=False)
        self.assertIn(traversal.exception.code, (403, 404))


if __name__ == "__main__":
    unittest.main()
