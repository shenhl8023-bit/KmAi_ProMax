import pytest

from part_classification.classify import classify
from part_classification.scorecard import match_degree, parse_scorecard
from tests.xml_builder import kmsoft_xml_bytes

LOCKED_CARD = parse_scorecard(
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


def test_match_degree_inside_interval_is_one():
    assert match_degree(0.73, (0.5, 0.9)) == 1.0


def test_match_degree_outside_interval_is_zero():
    assert match_degree(0.4, (0.5, 0.9)) == 0.0
    assert match_degree(0.0, (0.5, 0.9)) == 0.0


def test_legacy_scorecard_defaults_candidate_schema_fields():
    assert LOCKED_CARD.validation_status is None
    assert LOCKED_CARD.primary_factor is None
    assert LOCKED_CARD.evidence_groups == ()
    assert LOCKED_CARD.gates.min_auxiliary_groups is None


def test_locked_sleeve_like_xml_prefers_sleeve():
    result = classify(kmsoft_xml_bytes(), scorecard=LOCKED_CARD)
    assert result["ok"] is True
    assert result["geometryClass"] == "sleeve"
    assert result["labelZh"] == "活门衬套"
    by_id = {row["id"]: row for row in result["types"]}
    assert set(by_id) == {"sleeve", "spool"}
    assert by_id["sleeve"]["score"] > by_id["spool"]["score"]
    assert by_id["sleeve"]["possibility"] + by_id["spool"]["possibility"] == pytest.approx(1.0)
    assert any(
        "最小内径/最大外径" in line and "落在" in line
        for line in by_id["sleeve"]["reasons"]
    )
    assert any("偏离" in line for line in by_id["spool"]["reasons"])


def test_invalid_factor_is_skipped_not_scored_as_zero():
    xml = kmsoft_xml_bytes(min_inner=None)
    result = classify(xml, scorecard=LOCKED_CARD)
    assert result["geometryClass"] == "unknown"
    sleeve = next(row for row in result["types"] if row["id"] == "sleeve")
    assert any("未采用：hollow_ratio" in line for line in sleeve["reasons"])
    assert sleeve["score"] == 1.0


def test_missing_primary_still_returns_types():
    xml = kmsoft_xml_bytes(min_inner=None)
    result = classify(xml, scorecard=LOCKED_CARD)
    assert result["ok"] is True
    assert result["geometryClass"] == "unknown"
    assert len(result["types"]) == 2
    assert all(
        "possibility" in row and "score" in row and "reasons" in row
        for row in result["types"]
    )


def test_low_top_score_is_unknown_with_types():
    card = parse_scorecard(
        {
            "id": "high-bar",
            "locked": True,
            "classes": [
                {
                    "id": "sleeve",
                    "labelZh": "活门衬套",
                    "factors": {
                        "hollow_ratio": {
                            "role": "secondary",
                            "weight": 1.0,
                            "interval": [0.01, 0.02],
                        },
                    },
                }
            ],
            "gates": {
                "min_valid_factors": 1,
                "min_top_score": 0.9,
                "min_score_gap": None,
            },
        }
    )
    result = classify(kmsoft_xml_bytes(), scorecard=card)
    assert result["geometryClass"] == "unknown"
    assert result["types"][0]["score"] < 0.9


def test_too_few_valid_factors_is_unknown_with_types():
    card = parse_scorecard(
        {
            "id": "need-many",
            "locked": True,
            "classes": [
                {
                    "id": "sleeve",
                    "labelZh": "活门衬套",
                    "factors": {
                        "hollow_ratio": {
                            "role": "secondary",
                            "weight": 1.0,
                            "interval": [0.5, 0.9],
                        },
                    },
                }
            ],
            "gates": {
                "min_valid_factors": 8,
                "min_top_score": 0.0,
                "min_score_gap": None,
            },
        }
    )
    result = classify(kmsoft_xml_bytes(), scorecard=card)
    assert result["geometryClass"] == "unknown"
    assert result["labelZh"] == "未定"
    assert len(result["types"]) == 1
    assert result["types"][0]["id"] == "sleeve"


def test_close_scores_trigger_unknown():
    card = parse_scorecard(
        {
            "id": "close",
            "locked": True,
            "classes": [
                {
                    "id": "sleeve",
                    "labelZh": "活门衬套",
                    "factors": {
                        "hollow_ratio": {
                            "role": "secondary",
                            "weight": 1.0,
                            "interval": [0.0, 1.0],
                        }
                    },
                },
                {
                    "id": "spool",
                    "labelZh": "活门",
                    "factors": {
                        "hollow_ratio": {
                            "role": "secondary",
                            "weight": 1.0,
                            "interval": [0.0, 1.0],
                        }
                    },
                },
            ],
            "gates": {
                "min_valid_factors": 1,
                "min_top_score": 0.0,
                "min_score_gap": 0.1,
            },
        }
    )
    result = classify(kmsoft_xml_bytes(), scorecard=card)
    assert result["geometryClass"] == "unknown"
    assert result["types"][0]["score"] == result["types"][1]["score"]
