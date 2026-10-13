from pathlib import Path

import pytest

from part_classification.fingerprint import FEATURE_NAMES, extract_fingerprint
from part_classification.xml_read import read_kmsoft_xml
from tests.xml_builder import kmsoft_xml_bytes

REPO = Path(__file__).resolve().parents[1]
SLEEVE_XML = REPO / "source" / "XML样本" / "JRT145-13-02计量活门衬套1.XML"
SPOOL_XML = REPO / "source" / "XML样本" / "JRT145-13-01计量活门.XML"


def _fp(**kwargs):
    return extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(**kwargs)))


def test_feature_names_are_the_eight_period_one_factors():
    assert FEATURE_NAMES == (
        "hollow_ratio",
        "inner_rev_ratio",
        "inner_cyl_balance",
        "wall_to_outer",
        "slenderness",
        "plane_ratio",
        "inner_cyl_ratio",
        "outer_cyl_ratio",
    )


def test_zero_is_a_valid_observation():
    fp = _fp(plane_ratio=0.0, inner_cyl_ratio=0.0)
    assert fp.get("plane_ratio") == 0.0
    assert "plane_ratio" not in fp.invalid_reasons


def test_missing_field_is_invalid_not_zero():
    fp = _fp(slenderness=None)
    assert fp.get("slenderness") is None
    assert fp.invalid_reasons["slenderness"].startswith("未采用：slenderness")


def test_zero_denominator_is_invalid():
    fp = _fp(max_outer=0.0, min_inner=16.0, wall_mean=3.0)
    assert fp.get("hollow_ratio") is None
    assert fp.get("wall_to_outer") is None
    assert fp.get("slenderness") == 2.739


def test_negative_max_outer_export_sentinel_is_invalid():
    fp = _fp(max_outer=-1.0, min_inner=10000.0, wall_mean=3.078)
    assert fp.get("hollow_ratio") is None
    assert fp.get("wall_to_outer") is None
    assert "hollow_ratio" in fp.invalid_reasons
    assert "wall_to_outer" in fp.invalid_reasons


def test_inner_cyl_balance_invalid_when_both_ratios_zero():
    fp = _fp(inner_cyl_ratio=0.0, outer_cyl_ratio=0.0)
    assert fp.get("inner_cyl_balance") is None
    assert fp.get("inner_cyl_ratio") == 0.0
    assert fp.get("outer_cyl_ratio") == 0.0


def test_sleeve_sample_matches_known_ratios():
    fp = extract_fingerprint(read_kmsoft_xml(SLEEVE_XML))
    assert fp.get("hollow_ratio") == pytest.approx(16.0 / 22.0)
    assert fp.get("inner_rev_ratio") == pytest.approx(10904.024 / 28736.699)
    assert fp.get("wall_to_outer") == pytest.approx(3.076 / 22.0)


def test_spool_sample_matches_known_ratios():
    fp = extract_fingerprint(read_kmsoft_xml(SPOOL_XML))
    assert fp.get("hollow_ratio") == pytest.approx(1.0 / 16.0)
    assert fp.get("inner_rev_ratio") == pytest.approx(2044.966 / 12837.015)
    assert fp.get("wall_to_outer") == pytest.approx(9.028 / 16.0)
