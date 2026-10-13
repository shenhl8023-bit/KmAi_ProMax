from pathlib import Path

import pytest

from part_classification.classify import classify
from part_classification.fingerprint import extract_fingerprint
from part_classification.scorecard import parse_scorecard
from part_classification.scorecard import score_fingerprint
from part_classification.xml_read import read_kmsoft_xml
from tests.xml_builder import kmsoft_xml_bytes

REPO = Path(__file__).resolve().parents[1]

# 与仓库真实清单隔离：用户在界面里的配置不应改变打分卡断言。
NO_MAP = REPO / "tests" / "不存在的映射.json"
assert not NO_MAP.exists(), "隔离路径被真实文件占用了，换一个"


def candidate_card_data():
    return {
        "id": "v2-evidence-group-calibrated-candidate",
        "locked": True,
        "validationStatus": "candidate",
        "primaryFactor": "inner_cyl_balance",
        "evidenceGroups": [
            {
                "id": "cylinder_group",
                "weight": 0.406191,
                "representativeFactor": "inner_cyl_balance",
                "factors": ["inner_cyl_balance", "inner_cyl_ratio", "outer_cyl_ratio"],
            },
            {
                "id": "inner_rev_group",
                "weight": 0.223875,
                "representativeFactor": "inner_rev_ratio",
                "factors": ["inner_rev_ratio"],
            },
            {
                "id": "wall_group",
                "weight": 0.222678,
                "representativeFactor": "wall_to_outer",
                "factors": ["wall_to_outer"],
            },
            {
                "id": "plane_group",
                "weight": 0.147255,
                "representativeFactor": "plane_ratio",
                "factors": ["plane_ratio"],
            },
        ],
        "classes": [
            {
                "id": "sleeve",
                "labelZh": "活门衬套",
                "factors": {
                    "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.433380084, 0.502170767]},
                    "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.371801970, 0.603647895]},
                    "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.139818182, 0.358200000]},
                    "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.074, 0.258]},
                },
            },
            {
                "id": "spool",
                "labelZh": "活门",
                "factors": {
                    "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.071212121, 0.418158568]},
                    "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.060164917, 0.438915538]},
                    "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.216444444, 0.564250000]},
                    "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.195, 0.373]},
                },
            },
        ],
        "gates": {"min_auxiliary_groups": 1},
    }


def test_candidate_scorecard_parses_evidence_groups_and_status():
    card = parse_scorecard(candidate_card_data())
    assert card.id == "v2-evidence-group-calibrated-candidate"
    assert card.locked is True
    assert card.validation_status == "candidate"
    assert card.primary_factor == "inner_cyl_balance"
    assert [group.id for group in card.evidence_groups] == [
        "cylinder_group", "inner_rev_group", "wall_group", "plane_group"
    ]
    # The candidate weights are rounded to six decimals and sum to 0.999999.
    assert sum(group.weight for group in card.evidence_groups) == pytest.approx(1.0, abs=2e-6)
    assert card.gates.min_auxiliary_groups == 1


def test_legacy_in_memory_card_still_has_no_candidate_groups():
    card = parse_scorecard({"id": "legacy", "locked": True, "classes": [], "gates": {}})
    assert card.evidence_groups == ()
    assert card.primary_factor is None
    assert card.validation_status is None
    assert card.gates.min_auxiliary_groups is None


def test_duplicate_cylinder_members_are_scored_once():
    card = parse_scorecard(candidate_card_data())
    fp = extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=40.0, surface_area=100.0,
        wall_mean=2.0, max_outer=10.0, plane_ratio=0.10,
    )))
    sleeve = next(row for row in score_fingerprint(fp, card) if row.id == "sleeve")
    assert sleeve.score == pytest.approx(1.0)
    assert sleeve.valid_used == 4


def test_missing_auxiliary_group_renormalizes_remaining_weights():
    card = parse_scorecard(candidate_card_data())
    fp = extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=None, wall_mean=2.0, max_outer=10.0,
        plane_ratio=0.10,
    )))
    sleeve = next(row for row in score_fingerprint(fp, card) if row.id == "sleeve")
    assert sleeve.valid_used == 3
    assert sleeve.score == pytest.approx(1.0)


def test_overlapping_auxiliary_ranges_do_not_override_primary_direction():
    card = parse_scorecard(candidate_card_data())
    result = classify(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=40.0, surface_area=100.0,
        wall_mean=2.0, max_outer=10.0, plane_ratio=0.10,
    ), scorecard=card)
    assert result["geometryClass"] == "sleeve"
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["sleeve"]["score"] > by_id["spool"]["score"]


def test_missing_primary_is_unknown_even_when_auxiliary_values_exist():
    card = parse_scorecard(candidate_card_data())
    result = classify(
        kmsoft_xml_bytes(inner_cyl_ratio=None, outer_cyl_ratio=0.55),
        scorecard=card,
    )
    assert result["geometryClass"] == "unknown"


def test_primary_value_in_both_or_neither_interval_is_unknown():
    card_data = candidate_card_data()
    card_data["classes"][1]["factors"]["inner_cyl_balance"]["interval"] = [0.40, 0.50]
    both = classify(
        kmsoft_xml_bytes(inner_cyl_ratio=0.45, outer_cyl_ratio=0.55),
        scorecard=parse_scorecard(card_data),
    )
    assert both["geometryClass"] == "unknown"

    neither = classify(
        kmsoft_xml_bytes(inner_cyl_ratio=0.80, outer_cyl_ratio=0.20),
        scorecard=parse_scorecard(candidate_card_data()),
    )
    assert neither["geometryClass"] == "unknown"


def test_no_auxiliary_support_for_primary_direction_returns_unknown():
    card_data = candidate_card_data()
    for cls in card_data["classes"]:
        cls["factors"]["inner_rev_ratio"]["interval"] = [0.0, 0.01]
        cls["factors"]["wall_to_outer"]["interval"] = [0.0, 0.01]
        cls["factors"]["plane_ratio"]["interval"] = [0.0, 0.01]
    result = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=40.0,
            surface_area=100.0,
            wall_mean=2.0,
            max_outer=10.0,
            plane_ratio=0.10,
        ),
        scorecard=parse_scorecard(card_data),
    )
    assert result["geometryClass"] == "unknown"


def test_auxiliary_evidence_cannot_overturn_unique_primary_direction():
    card_data = candidate_card_data()
    for group, weight in zip(card_data["evidenceGroups"], (0.10, 0.10, 0.50, 0.30)):
        group["weight"] = weight
    result = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=50.0,
            surface_area=100.0,
            wall_mean=5.0,
            max_outer=10.0,
            plane_ratio=0.30,
        ),
        scorecard=parse_scorecard(card_data),
    )
    assert result["geometryClass"] == "unknown"
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["spool"]["score"] > by_id["sleeve"]["score"]


def test_equal_candidate_scores_are_unknown_despite_primary_and_auxiliary_support():
    card_data = candidate_card_data()
    for group, weight in zip(card_data["evidenceGroups"], (0.20, 0.20, 0.30, 0.30)):
        group["weight"] = weight
    card_data["classes"][0]["factors"]["wall_to_outer"]["interval"] = [0.0, 0.01]
    card_data["classes"][1]["factors"]["inner_rev_ratio"]["interval"] = [0.0, 0.20]
    result = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=10.0,
            surface_area=100.0,
            wall_mean=3.0,
            max_outer=10.0,
            plane_ratio=0.10,
        ),
        scorecard=parse_scorecard(card_data),
    )
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["sleeve"]["score"] == pytest.approx(by_id["spool"]["score"])
    assert result["geometryClass"] == "unknown"


def test_missing_min_auxiliary_groups_still_requires_one_support():
    card_data = candidate_card_data()
    card_data["gates"].pop("min_auxiliary_groups")
    for cls in card_data["classes"]:
        for factor in ("inner_rev_ratio", "wall_to_outer", "plane_ratio"):
            cls["factors"][factor]["interval"] = [0.0, 0.01]
    result = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=40.0,
            surface_area=100.0,
            wall_mean=2.0,
            max_outer=10.0,
            plane_ratio=0.10,
        ),
        scorecard=parse_scorecard(card_data),
    )
    assert result["geometryClass"] == "unknown"


def test_explicit_min_auxiliary_groups_requires_two_supports():
    card_data = candidate_card_data()
    card_data["gates"]["min_auxiliary_groups"] = 2
    for cls in card_data["classes"]:
        cls["factors"]["plane_ratio"]["interval"] = [0.0, 0.01]
    one_support = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=40.0,
            surface_area=100.0,
            wall_mean=0.01,
            max_outer=10.0,
            plane_ratio=0.10,
        ),
        scorecard=parse_scorecard(card_data),
    )
    assert one_support["geometryClass"] == "unknown"

    two_support = classify(
        kmsoft_xml_bytes(
            inner_cyl_ratio=0.45,
            outer_cyl_ratio=0.55,
            inner_rev_area=40.0,
            surface_area=100.0,
            wall_mean=2.0,
            max_outer=10.0,
            plane_ratio=0.10,
        ),
        scorecard=parse_scorecard(card_data),
    )
    assert two_support["geometryClass"] == "sleeve"


def test_candidate_card_keeps_pressure_differential_valve_as_spool():
    card = parse_scorecard(candidate_card_data())
    sample = Path(__file__).resolve().parents[1] / "source" / "XML样本" / "JRT145-17-01压差活门.XML"
    result = classify(sample, scorecard=card, template_map_path=NO_MAP)
    assert result["geometryClass"] == "spool"
