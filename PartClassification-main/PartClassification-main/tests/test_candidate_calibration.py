from pathlib import Path

import pytest

from part_classification import classify
from part_classification.scorecard import load_scorecard


REPO = Path(__file__).resolve().parents[1]
XML_DIR = REPO / "source" / "XML样本"
TEST_DIR = REPO / "source" / "测试样本"

# 与仓库真实清单隔离：用户在界面里的配置不应改变这些标定断言。
NO_MAP = REPO / "tests" / "不存在的映射.json"
assert not NO_MAP.exists(), "隔离路径被真实文件占用了，换一个"


def test_default_card_metadata_and_weights():
    card = load_scorecard()
    assert card.id == "v2-evidence-group-calibrated-candidate"
    assert card.locked is True
    assert card.validation_status == "candidate"
    assert sum(group.weight for group in card.evidence_groups) == pytest.approx(
        1.0, abs=2e-6
    )
    assert all(group.weight != 4.0 for group in card.evidence_groups)


def test_all_learning_xml_match_folder_labels():
    for folder, expected in (("活门prt", "spool"), ("活门衬套prt", "sleeve")):
        for prt in sorted((REPO / "source" / folder).glob("*.prt")):
            result = classify(XML_DIR / f"{prt.stem}.XML", template_map_path=NO_MAP)
            assert result["geometryClass"] == expected, prt.stem


def test_two_holdouts_are_sleeves():
    for name in ("taotong.XML", "衬套.XML"):
        assert classify(TEST_DIR / name, template_map_path=NO_MAP)["geometryClass"] == "sleeve"


def test_confirmed_pressure_valve_remains_spool():
    result = classify(XML_DIR / "JRT145-17-01压差活门.XML", template_map_path=NO_MAP)
    assert result["geometryClass"] == "spool"
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["spool"]["score"] > by_id["sleeve"]["score"]
