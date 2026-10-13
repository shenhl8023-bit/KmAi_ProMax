# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT
STEP_ROOT = WORKSPACE / "step-compare-main" / "step-compare-main"


def kmsoft_xml_bytes() -> bytes:
    return '<?xml version="1.0" encoding="GB2312"?><Kmsoft></Kmsoft>'.encode("gb2312")


class FakeTessellation:
    glb = b"glTF-test"
    bounds = [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
    extents = [1.0, 2.0, 3.0]
    vertices = 3
    faces = 1
    unit = "mm"
    source_unit = "mm"


class FailingTessellation:
    def __call__(self, data, filename):
        raise AssertionError("Win7 Lite mode must not invoke STEP tessellation")


class FixtureFeatureClient:
    namespace = "service-fixture"

    def extract(self, content):
        for index, score in enumerate((0.91, 0.82, 0.73), 1):
            if ('candidate="%d"' % index).encode() in content:
                return [score, math.sqrt(1 - score * score)] + [0] * 254
        return [1.0] + [0] * 255


class SimilarPartsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.xml_dir = base / "xml"
        self.step_dir = base / "step"
        self.template_dir = base / "templates"
        self.xml_dir.mkdir()
        self.step_dir.mkdir()
        self.template_dir.mkdir()
        self.map_path = self.template_dir / "模板映射.json"

        mappings = {}
        for index, score in enumerate((0.91, 0.82, 0.73), start=1):
            name = f"候选{index}.XML"
            (self.xml_dir / name).write_bytes(('<Kmsoft candidate="%d"/>' % index).encode())
            (self.step_dir / f"候选{index}.stp").write_bytes(b"ISO-10303-21;candidate")
            (self.template_dir / f"模板{index}.xml").write_bytes(b"<Kmsoft/>")
            mappings[name] = {"template": f"模板{index}.xml", "note": "", "updatedAt": ""}
        self.map_path.write_text(
            json.dumps({"version": 1, "samplesDir": "xml", "mappings": mappings}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.step_dir / "当前零件.step").write_bytes(b"ISO-10303-21;current")

        self.now = [100.0]
        self.tessellate_calls = []

        def tessellator(data, filename):
            self.tessellate_calls.append((data, filename))
            return FakeTessellation()

        self.config = {
            "similar_parts_enabled": True,
            "similar_parts_matching_backend": "feature_vector",
            "similar_parts_feature_index_file": str(base / "features.sqlite3"),
            "similar_parts_step_viewer_root": str(STEP_ROOT),
            "similar_parts_xml_library_dir": str(self.xml_dir),
            "similar_parts_step_library_dir": str(self.step_dir),
            "similar_parts_template_map_file": str(self.map_path),
            "similar_parts_upload_max_bytes": 1024,
            "similar_parts_cache_ttl_seconds": 10,
            "similar_parts_model_cache_entries": 1,
            "similar_parts_model_cache_bytes": 1024,
        }
        self.tessellator = tessellator

    def tearDown(self):
        self.temp.cleanup()

    def service(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsService
        from KmMpsMcpServer.backend.feature_vector_matching import FeatureVectorMatcher

        matcher = FeatureVectorMatcher(self.config, client=FixtureFeatureClient())
        matcher.build()
        return SimilarPartsService(
            self.config,
            matcher=matcher,
            tessellator=self.tessellator,
            clock=lambda: self.now[0],
        )

    def test_upload_query_returns_sanitized_top_three_and_same_name_models(self):
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)

        self.assertEqual(result["current"]["name"], "当前零件.XML")
        self.assertNotIn("path", result["current"])
        for row, score in zip(result["candidates"], (0.91, 0.82, 0.73)):
            self.assertAlmostEqual(row["similarity"], score)
        self.assertEqual(result["geometryClass"], "")
        self.assertEqual(result["labelZh"], "")
        self.assertEqual([row["template"]["name"] for row in result["candidates"]], ["模板1.xml", "模板2.xml", "模板3.xml"])
        self.assertTrue(all("path" not in row for row in result["candidates"]))
        self.assertTrue(all(row["candidateId"] for row in result["candidates"]))
        self.assertTrue(result["current"]["modelId"])

    def test_candidate_template_is_read_through_private_part_mapping(self):
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)

        template = service.get_candidate_template(
            upload["uploadId"],
            result["candidates"][0]["candidateId"],
        )

        self.assertEqual(template["filename"], "模板1.xml")
        self.assertEqual(template["xml"], "<Kmsoft/>")
        self.assertNotIn("path", template)

    def test_win7_lite_mode_reads_prebuilt_glb_without_tessellation(self):
        prebuilt_dir = Path(self.temp.name) / "models"
        prebuilt_dir.mkdir()
        glb = b"glTF-prebuilt-candidate"
        (prebuilt_dir / "候选1.glb").write_bytes(glb)
        config = dict(self.config)
        config.update({
            "similar_parts_win7_lite_mode": True,
            "similar_parts_prebuilt_model_dir": str(prebuilt_dir),
        })
        self.config.update(config)
        service = self.service()
        service._tessellator = FailingTessellation()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)

        payload, metadata = service.get_model(result["candidates"][0]["modelId"])
        self.assertEqual(payload, glb)
        self.assertEqual(metadata["name"], "候选1")
        self.assertEqual(metadata["source"], "prebuilt-glb")

    def test_win7_lite_mode_reports_missing_prebuilt_glb(self):
        prebuilt_dir = Path(self.temp.name) / "models"
        prebuilt_dir.mkdir()
        config = dict(self.config)
        config.update({
            "similar_parts_win7_lite_mode": True,
            "similar_parts_prebuilt_model_dir": str(prebuilt_dir),
        })
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        service = self.service()
        service.config.update(config)
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)
        with self.assertRaises(SimilarPartsError) as ctx:
            service.get_model(result["candidates"][0]["modelId"])
        self.assertEqual(ctx.exception.code, "PREBUILT_MODEL_MISSING")

    def test_prepare_template_writes_edited_xml_instead_of_original_mapping(self):
        destination = Path(self.temp.name) / "saved"
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)
        candidate_id = result["candidates"][0]["candidateId"]

        prepared = service.prepare_template(
            upload["uploadId"],
            candidate_id,
            destination,
            edited_template={
                "filename": "模板1-已编辑.xml",
                "xml": "<?xml version=\"1.0\"?><Kmsoft><Item type=\"Part\"/></Kmsoft>",
            },
        )

        saved = (destination / "模板1-已编辑.xml").read_bytes().decode("gb2312")
        self.assertIn('<Item type="Part"/>', saved)
        self.assertEqual(prepared["templateFilename"], "模板1-已编辑.xml")
        self.assertEqual(prepared["templateName"], "模板1-已编辑")

    def test_query_uses_configured_count_and_returns_available_candidates_up_to_1000(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        self.config["similar_parts_top_k"] = 2
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"])

        self.assertEqual(len(result["candidates"]), 2)

        for top_k in (5, 6, 1000):
            self.assertEqual(len(service.query(upload["uploadId"], top_k=top_k)["candidates"]), 3)
        for top_k in (0, True, 1001, "5"):
            with self.assertRaises(SimilarPartsError) as rejected:
                service.query(upload["uploadId"], top_k=top_k)
            self.assertEqual(rejected.exception.code, "INVALID_TOP_K")

    def test_database_part_is_ranked_first_and_can_apply_its_own_template(self):
        current_name = "当前零件.XML"
        current_template = "当前零件模板.xml"
        (self.xml_dir / current_name).write_bytes(kmsoft_xml_bytes())
        (self.template_dir / current_template).write_bytes(b"<Kmsoft current='true'/>")
        mapping = json.loads(self.map_path.read_text(encoding="utf-8"))
        mapping["mappings"][current_name] = {
            "template": current_template,
            "note": "",
            "updatedAt": "",
        }
        self.map_path.write_text(
            json.dumps(mapping, ensure_ascii=False),
            encoding="utf-8",
        )

        service = self.service()
        upload = service.upload_xml(current_name.lower(), kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)

        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["candidates"][0]["name"], current_name)
        self.assertEqual(result["candidates"][0]["similarity"], 1.0)
        self.assertEqual(result["candidates"][0]["template"]["name"], current_template)
        self.assertEqual(
            [row["name"] for row in result["candidates"][1:]],
            ["候选1.XML", "候选2.XML"],
        )

        destination = Path(self.temp.name) / "installed-current"
        prepared = service.prepare_template(
            upload["uploadId"],
            result["candidates"][0]["candidateId"],
            str(destination),
        )
        self.assertEqual(prepared["templateName"], Path(current_template).stem)
        self.assertEqual(
            (destination / current_template).read_bytes(),
            b"<Kmsoft current='true'/>",
        )

    def test_configured_current_step_supports_aibasicinfo_and_stepmodel_pair(self):
        current_dir = Path(self.temp.name) / "current-model"
        current_dir.mkdir()
        current_step = current_dir / "stepModel.stp"
        current_step.write_bytes(b"ISO-10303-21;current-configured")
        self.config["similar_parts_current_step_file"] = str(current_step)
        prebuilt_dir = Path(self.temp.name) / "models"
        prebuilt_dir.mkdir()
        (prebuilt_dir / "stepModel.glb").write_bytes(b"glTF-fixed-current")
        self.config.update({
            "similar_parts_win7_lite_mode": True,
            "similar_parts_prebuilt_model_dir": str(prebuilt_dir),
        })

        service = self.service()
        upload = service.upload_xml("AIBasicInfo.xml", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)
        payload, metadata = service.get_model(result["current"]["modelId"])

        self.assertEqual(result["current"]["name"], "AIBasicInfo.xml")
        self.assertEqual(payload, b"glTF-fixed-current")
        self.assertEqual(metadata["name"], "AIBasicInfo")
        self.assertEqual(self.tessellate_calls, [])

    def test_configured_stepmodel_always_takes_priority_over_same_name_step(self):
        current_dir = Path(self.temp.name) / "current-model"
        current_dir.mkdir()
        configured_step = current_dir / "stepModel.stp"
        configured_step.write_bytes(b"ISO-10303-21;configured-test-model")
        self.config["similar_parts_current_step_file"] = str(configured_step)

        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)
        service.get_model(result["current"]["modelId"])

        self.assertEqual(self.tessellate_calls[0][1], "stepModel.stp")
        self.assertEqual(
            self.tessellate_calls[0][0],
            b"ISO-10303-21;configured-test-model",
        )

    def test_load_current_part_reads_configured_xml_and_reports_fixed_step(self):
        current_dir = Path(self.temp.name) / "current-model"
        current_dir.mkdir()
        current_xml = current_dir / "AIBasicInfo.xml"
        current_xml.write_bytes(kmsoft_xml_bytes())
        current_step = current_dir / "stepModel.stp"
        current_step.write_bytes(b"ISO-10303-21;fixed-step")
        self.config["similar_parts_current_xml_file"] = str(current_xml)
        self.config["similar_parts_current_step_file"] = str(current_step)

        service = self.service()
        result = service.load_current_part()

        self.assertTrue(result["uploadId"])
        self.assertEqual(result["filename"], "AIBasicInfo.xml")
        self.assertEqual(result["stepFilename"], "stepModel.stp")
        self.assertEqual(result["stepPath"], str(current_step.resolve()))

    def test_load_current_part_scans_fixed_directory_when_xml_file_is_not_explicit(self):
        current_dir = Path(self.temp.name) / "current-model"
        current_dir.mkdir()
        (current_dir / "AIBasicInfo.xml").write_bytes(kmsoft_xml_bytes())
        current_step = current_dir / "stepModel.stp"
        current_step.write_bytes(b"ISO-10303-21;fixed-step")
        self.config["similar_parts_current_part_dir"] = str(current_dir)
        self.config["similar_parts_current_step_file"] = str(current_step)

        service = self.service()
        result = service.load_current_part()

        self.assertEqual(result["filename"], "AIBasicInfo.xml")

    def test_load_current_part_rejects_multiple_xml_files_in_fixed_directory(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        current_dir = Path(self.temp.name) / "current-model"
        current_dir.mkdir()
        for filename in ("AIBasicInfo.xml", "other.xml"):
            (current_dir / filename).write_bytes(kmsoft_xml_bytes())
        self.config["similar_parts_current_part_dir"] = str(current_dir)

        with self.assertRaises(SimilarPartsError) as ctx:
            self.service().load_current_part()
        self.assertEqual(ctx.exception.code, "CURRENT_XML_AMBIGUOUS")

    def test_lowercase_external_xml_uses_case_insensitive_template_mapping(self):
        for path in self.xml_dir.iterdir():
            path.rename(path.with_suffix(".xml"))
        self.config["similar_parts_current_step_file"] = str(self.step_dir / "当前零件.step")
        service = self.service()
        upload = service.upload_xml("AIBasicInfo.xml", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)

        self.assertEqual(
            [row["template"]["name"] for row in result["candidates"]],
            ["模板1.xml", "模板2.xml", "模板3.xml"],
        )

    def test_same_name_with_different_xml_does_not_force_self_match(self):
        service = self.service()
        upload = service.upload_xml("候选3.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], top_k=3)
        self.assertEqual(result["candidates"][0]["name"], "候选1.XML")
        self.assertAlmostEqual(result["candidates"][2]["similarity"], 0.73)

    def test_remote_error_is_translated_without_old_algorithm_fallback(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError, SimilarPartsService
        config = dict(self.config, similar_parts_feature_api_base_url="")
        service = SimilarPartsService(config)
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        with self.assertRaises(SimilarPartsError) as caught:
            service.query(upload["uploadId"])
        self.assertEqual(caught.exception.code, "FEATURE_API_NOT_CONFIGURED")

    def test_upload_rejects_bad_extension_invalid_xml_and_oversize(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        service = self.service()
        for filename, content, code in (
            ("part.txt", kmsoft_xml_bytes(), "INVALID_XML_FILE"),
            ("part.xml", b"not xml", "NOT_KMSOFT_XML"),
            ("part.xml", b"x" * 1025, "XML_TOO_LARGE"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(SimilarPartsError) as ctx:
                    service.upload_xml(filename, content)
                self.assertEqual(ctx.exception.code, code)

    def test_expired_and_forged_ids_are_rejected(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        with self.assertRaises(SimilarPartsError) as forged:
            service.query("forged", 3)
        self.assertEqual(forged.exception.code, "UPLOAD_NOT_FOUND")

        self.now[0] = 111.0
        with self.assertRaises(SimilarPartsError) as expired:
            service.query(upload["uploadId"], 3)
        self.assertEqual(expired.exception.code, "UPLOAD_NOT_FOUND")

    def test_missing_ranked_resource_is_database_error_not_rank_replacement(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        (self.step_dir / "候选2.stp").unlink()
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        with self.assertRaises(SimilarPartsError) as ctx:
            service.query(upload["uploadId"], 3)
        self.assertEqual(ctx.exception.code, "STEP_FILE_MISSING")
        self.assertIn("候选2", ctx.exception.message)

    def test_model_cache_is_bounded_and_model_ids_cannot_read_arbitrary_files(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], 3)
        current_id = result["current"]["modelId"]
        candidate_id = result["candidates"][0]["modelId"]

        first, meta = service.get_model(current_id)
        again, _ = service.get_model(current_id)
        self.assertEqual(first, b"glTF-test")
        self.assertEqual(meta["extents"], [1.0, 2.0, 3.0])
        self.assertEqual(len(self.tessellate_calls), 1)
        self.assertEqual(again, first)

        service.get_model(candidate_id)
        service.get_model(current_id)
        self.assertEqual(len(self.tessellate_calls), 3)
        with self.assertRaises(SimilarPartsError) as ctx:
            service.get_model("../../etc/passwd")
        self.assertEqual(ctx.exception.code, "MODEL_NOT_FOUND")

    def test_prepare_template_only_accepts_candidate_from_latest_query(self):
        from KmMpsMcpServer.backend.similar_parts_service import SimilarPartsError

        destination = Path(self.temp.name) / "installed"
        service = self.service()
        upload = service.upload_xml("当前零件.XML", kmsoft_xml_bytes())
        result = service.query(upload["uploadId"], 3)
        selected = result["candidates"][1]

        prepared = service.prepare_template(upload["uploadId"], selected["candidateId"], str(destination))
        self.assertEqual(prepared["templateName"], "模板2")
        self.assertEqual((destination / "模板2.xml").read_bytes(), b"<Kmsoft/>")
        self.assertNotIn("path", prepared)

        with self.assertRaises(SimilarPartsError) as ctx:
            service.prepare_template(upload["uploadId"], "forged", str(destination))
        self.assertEqual(ctx.exception.code, "CANDIDATE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
