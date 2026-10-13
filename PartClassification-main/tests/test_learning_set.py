from pathlib import Path

from part_classification.classify import classify

REPO = Path(__file__).resolve().parents[1]
XML_DIR = REPO / "source" / "XML样本"
TEST_DIR = REPO / "source" / "测试样本"

# 与仓库真实清单隔离：用户在界面里的配置不应改变这些学习集断言的观察结果。
NO_MAP = REPO / "tests" / "不存在的映射.json"
assert not NO_MAP.exists(), "隔离路径被真实文件占用了，换一个"


def _folder_label(prt_dir: str) -> str:
    if prt_dir == "活门prt":
        return "spool"
    if prt_dir == "活门衬套prt":
        return "sleeve"
    raise AssertionError(prt_dir)


def test_learning_samples_match_folder_labels():
    for folder, expected in (("活门prt", "spool"), ("活门衬套prt", "sleeve")):
        for prt in sorted((REPO / "source" / folder).glob("*.prt")):
            xml = XML_DIR / f"{prt.stem}.XML"
            result = classify(xml, template_map_path=NO_MAP)
            assert result["ok"] is True, prt.stem
            assert result["types"], prt.stem
            assert result["geometryClass"] == expected, (
                f"{prt.stem}: expected {expected}, got {result['geometryClass']}"
                f" scores={[ (t['id'], round(t['score'], 3)) for t in result['types'] ]}"
            )


def test_holdout_samples_are_not_empty_types_and_not_errors():
    for xml in sorted(TEST_DIR.glob("*.XML")):
        result = classify(xml, template_map_path=NO_MAP)
        assert result["ok"] is True, xml.name
        assert "fingerprint" not in result
        assert {row["id"] for row in result["types"]} == {"sleeve", "spool"}
        for row in result["types"]:
            assert "possibility" in row
            assert "score" in row
            assert row["reasons"]
