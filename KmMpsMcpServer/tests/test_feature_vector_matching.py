# -*- coding: utf-8 -*-
import email
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def xml(value):
    return ('<Kmsoft><Part name="%s"/></Kmsoft>' % value).encode("utf-8")


def vector(x, y=0):
    return [x, y] + [0] * 254


class FeatureVectorMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.responses = {}
        cls.wire_response = None

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                message = email.message_from_bytes(
                    ("Content-Type: %s\r\nMIME-Version: 1.0\r\n\r\n" %
                     self.headers["Content-Type"]).encode() + raw
                )
                fields = {
                    part.get_param("name", header="content-disposition"): part
                    for part in message.walk() if part.get_content_disposition() == "form-data"
                }
                content = fields["xml_file"].get_payload(decode=True)
                file_id = fields["file_id"].get_payload(decode=True).decode()
                cls.requests.append((self.path, fields, file_id, content))
                status, feature = cls.responses.get(content, (200, vector(1)))
                if isinstance(feature, dict):
                    payload = feature
                else:
                    payload = {"file_id": file_id, "feature_dim": 256, "feature": feature}
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if cls.wire_response is not None:
                    raw_response, declared_size = cls.wire_response
                    self.send_header("Content-Length", str(declared_size))
                self.end_headers()
                self.wfile.write(raw_response if cls.wire_response is not None else json.dumps(payload).encode())

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.requests.clear()
        self.responses.clear()
        self.__class__.wire_response = None
        self.config = {
            "similar_parts_feature_api_base_url": "http://127.0.0.1:%d" % self.server.server_port,
            "similar_parts_feature_api_timeout_seconds": 3,
            "similar_parts_feature_model_version": "fixture-v1",
            "similar_parts_feature_index_file": str(self.root / "index.sqlite3"),
            "similar_parts_xml_library_dir": str(self.library),
        }

    def matcher(self):
        from KmMpsMcpServer.backend.feature_vector_matching import FeatureVectorMatcher
        return FeatureVectorMatcher(self.config)

    def assert_code(self, code, function, *args):
        from KmMpsMcpServer.backend.feature_vector_matching import FeatureVectorError
        with self.assertRaises(FeatureVectorError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_multipart_contract_and_persistent_content_cache(self):
        (self.library / "中文.XML").write_bytes(xml("甲"))
        report = self.matcher().build()
        self.assertEqual((report["extracted"], report["cached"], report["failed"]), (1, 0, []))
        path, fields, file_id, content = self.requests[0]
        self.assertEqual(path, "/api/feature/extract")
        self.assertEqual(set(fields), {"file_id", "xml_file"})
        self.assertRegex(file_id, r"^[A-Za-z0-9_-]{1,128}$")
        self.assertTrue(fields["xml_file"].get_filename().endswith(".xml"))
        self.assertEqual(content, xml("甲"))
        self.assertTrue(Path(self.config["similar_parts_feature_index_file"]).is_file())
        report = self.matcher().build()
        self.assertEqual((report["extracted"], report["cached"]), (0, 1))
        self.matcher().query(xml("甲"), "renamed.xml", 5)
        self.assertEqual(len(self.requests), 1)

    def test_cosine_ranking_and_content_self_match_not_filename(self):
        (self.library / "a.xml").write_bytes(xml("a"))
        (self.library / "自身.XML").write_bytes(xml("self"))
        (self.library / "z.xml").write_bytes(xml("z"))
        self.responses.update({
            xml("a"): (200, vector(0.6, 0.8)),
            xml("self"): (200, vector(1)),
            xml("z"): (200, vector(-1)),
        })
        self.matcher().build()
        rows = self.matcher().query(xml("self"), "a.xml", 9)
        self.assertEqual([row["name"] for row in rows], ["自身.XML", "a.xml", "z.xml"])
        self.assertEqual([row["similarity"] for row in rows], [1.0, 0.6, 0.0])
        self.assertNotIn("path", rows[0])
        self.assertEqual(len(self.requests), 3)

    def test_changed_deleted_and_new_library_members_are_checked_on_every_query(self):
        path = self.library / "a.xml"
        path.write_bytes(xml("a"))
        matcher = self.matcher()
        matcher.build()
        path.write_bytes(xml("changed"))
        self.assert_code("FEATURE_INDEX_INCOMPLETE", matcher.query, xml("a"), "a.xml", 3)
        self.assertEqual(matcher.build()["extracted"], 1)
        path.unlink()
        self.assert_code("XML_LIBRARY_EMPTY", matcher.query, xml("a"), "a.xml", 3)
        (self.library / "new.xml").write_bytes(xml("new"))
        self.assert_code("FEATURE_INDEX_INCOMPLETE", matcher.query, xml("a"), "a.xml", 3)

    def test_model_version_and_endpoint_separate_cache_namespaces(self):
        (self.library / "a.xml").write_bytes(xml("a"))
        self.matcher().build()
        self.config["similar_parts_feature_model_version"] = "fixture-v2"
        self.assert_code("FEATURE_INDEX_INCOMPLETE", self.matcher().query, xml("a"), "a.xml", 3)
        self.assertEqual(self.matcher().build()["extracted"], 1)
        self.config["similar_parts_feature_api_base_url"] += "/another-encoder"
        self.assert_code("FEATURE_INDEX_INCOMPLETE", self.matcher().query, xml("a"), "a.xml", 3)

    def test_invalid_vectors_never_enter_index(self):
        from KmMpsMcpServer.backend.feature_vector_matching import FeatureApiClient
        client = FeatureApiClient(self.config)
        for feature in ([1] * 255, [0] * 256, vector(float("nan")),
                        vector(float("inf")), vector(True), ["1"] * 256,
                        {"file_id": "wrong", "feature_dim": 256, "feature": vector(1)}):
            with self.subTest(feature=str(feature)[:30]):
                self.responses[xml("bad")] = (200, feature)
                self.assert_code("FEATURE_RESPONSE_INVALID", client.extract, xml("bad"))

    def test_truncated_http_response_is_a_stable_feature_error(self):
        from KmMpsMcpServer.backend.feature_vector_matching import FeatureApiClient
        self.__class__.wire_response = (b'{"feature":', 100)
        self.assert_code("FEATURE_RESPONSE_INVALID", FeatureApiClient(self.config).extract, xml("current"))

    def test_partial_build_is_resumable_and_errors_do_not_leak_upstream_body(self):
        (self.library / "a.xml").write_bytes(xml("a"))
        (self.library / "bad.xml").write_bytes(xml("bad"))
        self.responses[xml("bad")] = (500, {"detail": "/private/model/weights"})
        report = self.matcher().build()
        self.assertEqual(report["extracted"], 1)
        self.assertEqual(report["failed"], [{"name": "bad.xml", "code": "FEATURE_API_ERROR"}])
        self.assert_code("FEATURE_INDEX_INCOMPLETE", self.matcher().query, xml("a"), "a.xml", 3)
        self.responses.pop(xml("bad"))
        report = self.matcher().build()
        self.assertEqual((report["extracted"], report["cached"], report["failed"]), (1, 1, []))
        self.responses[xml("current")] = (500, {"detail": "/private/model/weights"})
        error = self.assert_code("FEATURE_API_ERROR", self.matcher().query, xml("current"), "current.xml", 3)
        self.assertNotIn("/private", str(error))

    def test_missing_corrupt_index_and_missing_configuration_have_clear_errors(self):
        (self.library / "a.xml").write_bytes(xml("a"))
        self.assert_code("FEATURE_INDEX_MISSING", self.matcher().query, xml("a"), "a.xml", 3)
        Path(self.config["similar_parts_feature_index_file"]).write_bytes(b"corrupt sqlite")
        self.assert_code("FEATURE_INDEX_INVALID", self.matcher().query, xml("a"), "a.xml", 3)
        self.config["similar_parts_feature_api_base_url"] = ""
        self.assert_code("FEATURE_API_NOT_CONFIGURED", self.matcher().build)

    def test_utf8_and_chinese_legacy_xml_are_validated_without_old_classifier(self):
        from KmMpsMcpServer.backend.feature_vector_matching import validate_xml
        for encoding in ("utf-8", "gb2312", "gbk", "gb18030"):
            content = ('<?xml version="1.0" encoding="%s"?><Kmsoft name="零件"/>' % encoding).encode(encoding)
            validate_xml(content)
        for content in (b"not xml", b"<Other/>", b"<Kmsoft>", b'<!DOCTYPE Kmsoft [<!ENTITY a "x">]><Kmsoft>&a;</Kmsoft>'):
            self.assert_code("NOT_KMSOFT_XML", validate_xml, content)

    def test_symlinks_outside_library_are_rejected(self):
        outside = self.root / "outside.xml"
        outside.write_bytes(xml("outside"))
        (self.library / "escaped.xml").symlink_to(outside)
        self.assert_code("XML_LIBRARY_INVALID", self.matcher().build)

    def test_cli_uses_selected_config_and_reports_partial_failure_with_nonzero_exit(self):
        (self.library / "a.xml").write_bytes(xml("a"))
        (self.library / "bad.xml").write_bytes(xml("bad"))
        self.responses[xml("bad")] = (500, {"detail": "private error"})
        config_path = self.root / "config.ini"
        config_path.write_text(
            "[SimilarParts]\nfeature_api_base_url = %s\n"
            "feature_model_version = fixture-cli\n"
            "feature_index_file = cache/features.sqlite3\nxml_library_dir = library\n" %
            self.config["similar_parts_feature_api_base_url"], encoding="utf-8",
        )
        script = Path(__file__).resolve().parents[1] / "build_feature_index.py"
        result = subprocess.run(
            [sys.executable, str(script), "--config", str(config_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["extracted"], 1)
        self.assertEqual(report["failed"], [{"name": "bad.xml", "code": "FEATURE_API_ERROR"}])
        self.responses.pop(xml("bad"))
        result = subprocess.run(
            [sys.executable, str(script), "--config", str(config_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cached"], 1)


if __name__ == "__main__":
    unittest.main()
