from pathlib import Path

import pytest

from part_classification import classify
from part_classification.template_map import set_mapping
from tests.xml_builder import kmsoft_xml_bytes


REPO = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO / "source" / "XML样本"
SLEEVE_XML = SAMPLE_DIR / "JRT145-13-02计量活门衬套1.XML"

# 与仓库真实清单隔离：用户在界面里的配置不应改变相似样本断言。
NO_MAP = REPO / "tests" / "不存在的映射.json"
assert not NO_MAP.exists(), "隔离路径被真实文件占用了，换一个"


@pytest.fixture
def library(tmp_path):
    """隔离的样本库 + 模板库 + 清单：钉住 similarParts 里各自的 template。"""

    samples = tmp_path / "XML样本"
    templates = tmp_path / "模板"
    samples.mkdir()
    templates.mkdir()
    (templates / "T.xml").write_bytes(b"<Kmsoft/>")

    # 形状各不相同，避免彼此距离为 0 而被当成"自身"排除。
    shapes = {
        "A.XML": dict(max_outer=22.0, min_inner=16.0, wall_mean=3.0, plane_ratio=0.18),
        "B.XML": dict(max_outer=24.0, min_inner=17.0, wall_mean=3.4, plane_ratio=0.20),
        "C.XML": dict(max_outer=26.0, min_inner=15.0, wall_mean=2.8, plane_ratio=0.16),
    }
    for name, kwargs in shapes.items():
        (samples / name).write_bytes(kmsoft_xml_bytes(**kwargs))

    map_path = templates / "模板映射.json"
    set_mapping("A.XML", "T.xml", "甲的备注", map_path)
    set_mapping("B.XML", "T.xml", path=map_path)
    # C.XML 刻意不绑定

    query = tmp_path / "查询.XML"
    query.write_bytes(kmsoft_xml_bytes(max_outer=23.0, min_inner=16.5, wall_mean=3.2))
    return {"samples": samples, "templates": templates, "map": map_path, "query": query}


def _rows(result):
    return {row["name"]: row for row in result["similarParts"]}


def test_similar_parts_carry_their_own_template(library):
    result = classify(
        library["query"],
        samples_dir=library["samples"],
        template_map_path=library["map"],
    )
    rows = _rows(result)
    assert set(rows) == {"A.XML", "B.XML", "C.XML"}

    assert rows["A.XML"]["template"] == {
        "name": "T.xml",
        "path": str((library["templates"] / "T.xml").resolve()),
        "note": "甲的备注",
    }
    assert rows["B.XML"]["template"]["name"] == "T.xml"
    # 未绑定的样本不编造模板
    assert rows["C.XML"]["template"] is None


def test_similar_parts_templates_are_null_when_map_missing(library):
    result = classify(
        library["query"],
        samples_dir=library["samples"],
        template_map_path=library["templates"] / "不存在的清单.json",
    )
    assert result["ok"] is True
    assert all(row["template"] is None for row in result["similarParts"])


def test_similar_parts_templates_are_null_when_map_corrupt(library):
    """坏清单不能破坏分类，也不能破坏相似样本（与顶层 templateError 一致）。"""

    library["map"].write_text("{ broken", encoding="utf-8")
    result = classify(
        library["query"],
        samples_dir=library["samples"],
        template_map_path=library["map"],
    )
    assert result["ok"] is True
    assert result["templateError"] == "MAP_FILE_CORRUPT"
    assert result["similarParts"]
    assert all(row["template"] is None for row in result["similarParts"])


def test_export_sentinel_diameters_do_not_flatten_similarity_ranking(library):
    result = classify(
        kmsoft_xml_bytes(max_outer=-1.0, min_inner=10000.0, plane_ratio=0.19),
        samples_dir=library["samples"],
        template_map_path=library["map"],
    )
    similar = result["similarParts"]
    assert [row["name"] for row in similar[:2]] == ["A.XML", "B.XML"]
    assert similar[0]["similarity"] > 0.0
    assert similar[-1]["similarity"] < similar[0]["similarity"]


def test_top_level_template_stays_null_for_unbound_query(library):
    """顶层 template 反映查询文件自身，不取相似样本的模板（不编造）。"""

    result = classify(
        library["query"],
        samples_dir=library["samples"],
        template_map_path=library["map"],
    )
    assert result["template"] is None


def test_classify_returns_three_ranked_similar_learning_samples():
    result = classify(SLEEVE_XML, template_map_path=NO_MAP)

    similar = result["similarParts"]
    assert len(similar) == 3
    assert all(row["path"] != str(SLEEVE_XML.resolve()) for row in similar)
    assert all(0.0 <= row["similarity"] <= 1.0 for row in similar)
    assert [row["similarity"] for row in similar] == sorted(
        (row["similarity"] for row in similar), reverse=True
    )
    assert similar[0]["id"] == "JRT145-15-01计量活门衬套2"
    assert all(row["geometryClass"] in {"sleeve", "spool", "unknown"} for row in similar)


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_similar_top_k_limits_result_count(count):
    result = classify(kmsoft_xml_bytes(), similar_top_k=count, template_map_path=NO_MAP)
    assert len(result["similarParts"]) == count


def test_similar_top_k_rejects_values_outside_one_to_five():
    with pytest.raises(ValueError, match="1 到 5"):
        classify(kmsoft_xml_bytes(), similar_top_k=6, template_map_path=NO_MAP)

    with pytest.raises(ValueError, match="1 到 5"):
        classify(kmsoft_xml_bytes(), similar_top_k=0, template_map_path=NO_MAP)


def test_query_bytes_matching_a_sample_is_excluded_from_recommendations():
    result = classify(SLEEVE_XML.read_bytes(), similar_top_k=3, template_map_path=NO_MAP)
    assert all(row["id"] != SLEEVE_XML.stem for row in result["similarParts"])


def test_custom_empty_sample_directory_returns_empty_recommendations(tmp_path):
    result = classify(
        kmsoft_xml_bytes(),
        similar_top_k=3,
        samples_dir=tmp_path,
        template_map_path=NO_MAP,
    )
    assert result["similarParts"] == []
