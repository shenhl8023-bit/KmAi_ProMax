from part_classification import classify
from part_classification.scorecard import parse_scorecard
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


def test_unlocked_card_returns_unknown_and_empty_types():
    result = classify(kmsoft_xml_bytes(), scorecard=UNLOCKED_CARD)
    assert result == {
        "ok": True,
        "geometryClass": "unknown",
        "labelZh": "未定",
        "types": [],
        "template": None,
    }


def test_unlocked_does_not_leak_fingerprint_or_trial_scores():
    result = classify(kmsoft_xml_bytes(), scorecard=UNLOCKED_CARD)
    assert "fingerprint" not in result
    assert result["types"] == []


def test_parse_failure_is_error_not_unknown():
    result = classify(b"")
    assert result["ok"] is False
    assert result["error"] == "NOT_KMSOFT_XML"
    assert result["message"] == "根节点不是 Kmsoft，或无法按 GB2312 解析"
    assert "geometryClass" not in result
