import json

import pytest

from part_classification import classify
from part_classification.cli import main
from part_classification.scorecard import parse_scorecard
from part_classification.template_map import set_mapping
from tests.xml_builder import kmsoft_xml_bytes

UNLOCKED_CARD = parse_scorecard(
    {
        "id": "v0-unlocked",
        "locked": False,
        "classes": [
            {"id": "sleeve", "labelZh": "活门衬套", "factors": {}},
            {"id": "spool", "labelZh": "活门", "factors": {}},
        ],
        "gates": {
            "min_valid_factors": None,
            "min_top_score": None,
            "min_score_gap": None,
        },
    }
)


@pytest.fixture
def mapped(tmp_path):
    """一份样本 XML + 同目录模板库 + 已写好一条映射的清单。"""

    templates = tmp_path / "模板"
    templates.mkdir()
    template = templates / "套筒类模板.xml"
    template.write_bytes(b"<Kmsoft/>")
    sample = tmp_path / "JRT145-13-02计量活门衬套1.XML"
    sample.write_bytes(kmsoft_xml_bytes())
    map_path = templates / "模板映射.json"
    set_mapping(sample.name, "套筒类模板.xml", "配置备注", map_path)
    return {"sample": sample, "map": map_path, "template": template, "templates": templates}


def test_classify_reports_configured_template(mapped):
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["ok"] is True
    assert result["template"] == {
        "name": "套筒类模板.xml",
        "path": str(mapped["template"].resolve()),
        "note": "配置备注",
    }


def test_classify_reports_null_template_when_sample_has_no_mapping(mapped, tmp_path):
    other = tmp_path / "未配置.XML"
    other.write_bytes(kmsoft_xml_bytes())
    result = classify(other, template_map_path=mapped["map"])
    assert result["template"] is None
    assert "templateError" not in result


def test_classify_bytes_input_has_null_template(mapped):
    result = classify(kmsoft_xml_bytes(), template_map_path=mapped["map"])
    assert result["template"] is None


def test_classify_reports_template_with_null_path_when_file_deleted(mapped):
    mapped["template"].unlink()
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["template"]["name"] == "套筒类模板.xml"
    assert result["template"]["path"] is None


def test_unlocked_scorecard_still_reports_template(mapped):
    result = classify(
        mapped["sample"],
        scorecard=UNLOCKED_CARD,
        template_map_path=mapped["map"],
    )
    assert result["types"] == []
    assert result["template"]["name"] == "套筒类模板.xml"


def test_corrupt_map_does_not_fail_classification(mapped):
    mapped["map"].write_text("{ broken", encoding="utf-8")
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["ok"] is True
    assert result["template"] is None
    assert result["templateError"] == "MAP_FILE_CORRUPT"
    assert result["geometryClass"] in {"sleeve", "spool", "unknown"}


def test_read_failure_has_no_template_key(mapped):
    result = classify(b"", template_map_path=mapped["map"])
    assert result["ok"] is False
    assert "template" not in result


def test_cli_accepts_template_map_and_prints_template(mapped, capsys):
    code = main([str(mapped["sample"]), "--template-map", str(mapped["map"])])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["template"]["name"] == "套筒类模板.xml"


def test_cli_default_map_missing_file_is_not_an_error(tmp_path, capsys):
    sample = tmp_path / "X.XML"
    sample.write_bytes(kmsoft_xml_bytes())
    empty_map = tmp_path / "空映射.json"
    code = main([str(sample), "--template-map", str(empty_map)])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["template"] is None
