from pathlib import Path

from part_classification.classify import classify
from part_classification.scorecard import parse_scorecard

REPO = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO / "source" / "XML样本"
SLEEVE_XML = SAMPLE_DIR / "JRT145-13-02计量活门衬套1.XML"
SPOOL_XML = SAMPLE_DIR / "JRT145-13-01计量活门.XML"

# 测试必须与仓库里真实的、用户可编辑的 source/模板/模板映射.json 隔离：
# 否则用户在界面里的配置会改变测试观察到的 template，破坏可复现性。
# 指向一个确定不存在的路径 -> template 恒为 None，与默认路径的接线无关。
NO_MAP = REPO / "tests" / "不存在的映射.json"
assert not NO_MAP.exists(), "隔离路径被真实文件占用了，换一个"

LOCKED = parse_scorecard(
    {
        "id": "test-locked",
        "locked": True,
        "classes": [
            {
                "id": "sleeve",
                "labelZh": "活门衬套",
                "factors": {
                    "hollow_ratio": {
                        "role": "primary",
                        "weight": 2.0,
                        "interval": [0.5, 0.9],
                    },
                    "wall_to_outer": {
                        "role": "secondary",
                        "weight": 1.0,
                        "interval": [0.05, 0.25],
                    },
                },
            },
            {
                "id": "spool",
                "labelZh": "活门",
                "factors": {
                    "hollow_ratio": {
                        "role": "primary",
                        "weight": 2.0,
                        "interval": [0.0, 0.2],
                    },
                    "wall_to_outer": {
                        "role": "secondary",
                        "weight": 1.0,
                        "interval": [0.4, 0.8],
                    },
                },
            },
        ],
        "gates": {
            "min_valid_factors": 1,
            "min_top_score": 0.5,
            "min_score_gap": 0.1,
        },
    }
)


def _without_template(payload: dict) -> dict:
    """template 依赖输入文件名，bytes 输入恒为 None；比较打分结果时剔除它。"""

    return {k: v for k, v in payload.items() if k not in {"template", "templateError"}}


def test_same_xml_same_locked_card_same_payload():
    a = classify(SLEEVE_XML, scorecard=LOCKED, template_map_path=NO_MAP)
    b = classify(SLEEVE_XML.read_bytes(), scorecard=LOCKED, template_map_path=NO_MAP)
    # bytes 输入没有文件名，template 恒为 None，因此这里仍需剔除该键。
    assert _without_template(a) == _without_template(b)
    assert a["ok"] is True
    assert a["types"]


def test_locked_card_is_deterministic_on_spool_sample():
    first = classify(SPOOL_XML, scorecard=LOCKED, template_map_path=NO_MAP)
    second = classify(SPOOL_XML, scorecard=LOCKED, template_map_path=NO_MAP)
    # 两侧是同一个路径输入且映射为空，所有键都必然相同，无需剔除。
    assert first == second
    assert first["ok"] is True
    assert first["types"]


def test_default_candidate_card_path_and_bytes_match_on_learning_xml():
    for path in (SLEEVE_XML, SPOOL_XML):
        first = classify(path, template_map_path=NO_MAP)
        second = classify(path.read_bytes(), template_map_path=NO_MAP)
        assert _without_template(first) == _without_template(second)
        assert first["ok"] is True
        assert first["types"]
        assert "fingerprint" not in first


def test_bytes_input_never_reports_a_template():
    result = classify(SLEEVE_XML.read_bytes(), template_map_path=NO_MAP)
    assert result["template"] is None
    assert "templateError" not in result


def test_default_map_path_wiring_is_pinned_elsewhere():
    """默认路径的接线由 test_classify_template 用显式路径覆盖。

    这里只固定一件事：不传 template_map_path 时，默认读的是仓库真实清单
    （而不是被测试悄悄改掉的行为）。
    """

    from part_classification.template_map import default_map_path

    assert default_map_path() == REPO / "source" / "模板" / "模板映射.json"
