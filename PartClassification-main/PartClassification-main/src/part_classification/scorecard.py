from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from part_classification.fingerprint import Fingerprint

LABEL_ZH = {
    "sleeve": "活门衬套",
    "spool": "活门",
    "unknown": "未定",
}

FEATURE_LABEL_ZH = {
    "hollow_ratio": "最小内径/最大外径",
    "inner_rev_ratio": "内回转面占表面积",
    "inner_cyl_balance": "内圆柱面积占内外圆柱之和",
    "wall_to_outer": "薄壁圆柱厚度均值/最大外径",
    "slenderness": "零件细长度",
    "plane_ratio": "平面总面积占比",
    "inner_cyl_ratio": "内圆柱总面积占比",
    "outer_cyl_ratio": "外圆柱总面积占比",
}

TOP_REASONS = 3
_NO_FACTORS_REASON = "本轮无有效因子参与加分"
_INVALID_FALLBACK = "未采用：{name} 无效（缺字段或分母为 0）"


@dataclass(frozen=True)
class FactorSpec:
    role: str
    weight: float
    interval: tuple[float, float]


@dataclass(frozen=True)
class ClassSpec:
    id: str
    label_zh: str
    factors: dict[str, FactorSpec]


@dataclass(frozen=True)
class Gates:
    min_valid_factors: int | None
    min_top_score: float | None
    min_score_gap: float | None
    min_auxiliary_groups: int | None = None


@dataclass(frozen=True)
class EvidenceGroupSpec:
    id: str
    weight: float
    representative_factor: str
    factors: tuple[str, ...]


@dataclass(frozen=True)
class Scorecard:
    id: str
    locked: bool
    classes: tuple[ClassSpec, ...]
    gates: Gates
    validation_status: str | None = None
    primary_factor: str | None = None
    evidence_groups: tuple[EvidenceGroupSpec, ...] = ()


@dataclass(frozen=True)
class TypeResult:
    id: str
    label_zh: str
    possibility: float
    score: float
    reasons: tuple[str, ...]
    primary_invalid: bool
    valid_used: int


def _default_scorecard_path() -> Path:
    return Path(__file__).with_name("data") / "scorecard.json"


def parse_scorecard(data: dict) -> Scorecard:
    gates_raw = data.get("gates") or {}
    evidence_groups: list[EvidenceGroupSpec] = []
    for group in data.get("evidenceGroups") or []:
        factors = tuple(str(name) for name in group.get("factors") or [])
        representative_factor = str(group["representativeFactor"])
        if representative_factor not in factors:
            raise ValueError(
                "evidence group representativeFactor must be one of its factors"
            )
        evidence_groups.append(
            EvidenceGroupSpec(
                id=str(group["id"]),
                weight=float(group["weight"]),
                representative_factor=representative_factor,
                factors=factors,
            )
        )
    classes: list[ClassSpec] = []
    for cls in data.get("classes") or []:
        factors: dict[str, FactorSpec] = {}
        for fname, spec in (cls.get("factors") or {}).items():
            interval = spec["interval"]
            factors[fname] = FactorSpec(
                role=spec["role"],
                weight=float(spec["weight"]),
                interval=(float(interval[0]), float(interval[1])),
            )
        classes.append(
            ClassSpec(
                id=cls["id"],
                label_zh=cls["labelZh"],
                factors=factors,
            )
        )
    return Scorecard(
        id=str(data.get("id", "unnamed")),
        locked=bool(data.get("locked", False)),
        classes=tuple(classes),
        gates=Gates(
            min_valid_factors=gates_raw.get("min_valid_factors"),
            min_top_score=gates_raw.get("min_top_score"),
            min_score_gap=gates_raw.get("min_score_gap"),
            min_auxiliary_groups=gates_raw.get("min_auxiliary_groups"),
        ),
        validation_status=data.get("validationStatus"),
        primary_factor=data.get("primaryFactor"),
        evidence_groups=tuple(evidence_groups),
    )


def load_scorecard(path: str | Path | None = None) -> Scorecard:
    card_path = Path(path) if path is not None else _default_scorecard_path()
    data = json.loads(card_path.read_text(encoding="utf-8"))
    return parse_scorecard(data)


def match_degree(value: float, interval: tuple[float, float]) -> float:
    low, high = interval
    if low > high:
        low, high = high, low
    if low <= value <= high:
        return 1.0
    return 0.0


def _reason_for_match(
    fname: str,
    value: float,
    spec: FactorSpec,
    class_label: str,
    degree: float,
) -> str:
    label = FEATURE_LABEL_ZH.get(fname, fname)
    lo, hi = spec.interval
    if lo > hi:
        lo, hi = hi, lo
    relation = "落在" if degree >= 0.5 else "偏离"
    return (
        f"{label}为 {value:.2f}，{relation}{class_label}期望区间 "
        f"[{lo:.2f}, {hi:.2f}]"
    )


def _score_class(
    fp: Fingerprint, cls: ClassSpec
) -> tuple[float, list[str], bool, int]:
    weighted = 0.0
    weight_sum = 0.0
    primary_invalid = False
    valid_used = 0
    contributions: list[tuple[float, str]] = []
    unused_reasons: list[str] = []
    primary_unused: list[str] = []

    for fname, spec in cls.factors.items():
        value = fp.get(fname)
        if value is None:
            note = fp.invalid_reasons.get(
                fname, _INVALID_FALLBACK.format(name=fname)
            )
            unused_reasons.append(note)
            if spec.role == "primary":
                primary_invalid = True
                primary_unused.append(note)
            continue
        degree = match_degree(value, spec.interval)
        weighted += spec.weight * degree
        weight_sum += spec.weight
        valid_used += 1
        contributions.append(
            (spec.weight, _reason_for_match(fname, value, spec, cls.label_zh, degree))
        )

    score = (weighted / weight_sum) if weight_sum > 0 else 0.0
    contributions.sort(key=lambda item: item[0], reverse=True)
    reasons = [text for _, text in contributions[:TOP_REASONS]]
    for note in reversed(primary_unused):
        if note not in reasons:
            reasons.insert(0, note)
    remaining = [note for note in unused_reasons if note not in reasons]
    room = max(0, TOP_REASONS - len(reasons))
    reasons.extend(remaining[:room])
    if not reasons:
        reasons = [_NO_FACTORS_REASON]
    return score, reasons, primary_invalid, valid_used


def _score_candidate_class(
    fp: Fingerprint, cls: ClassSpec, card: Scorecard
) -> tuple[float, list[str], bool, int]:
    weighted = 0.0
    weight_sum = 0.0
    primary_invalid = False
    valid_used = 0
    contributions: list[tuple[float, str]] = []
    unused_reasons: list[str] = []
    primary_unused: list[str] = []

    for group in card.evidence_groups:
        fname = group.representative_factor
        spec = cls.factors.get(fname)
        if spec is None:
            continue
        value = fp.get(fname)
        if value is None:
            note = fp.invalid_reasons.get(
                fname, _INVALID_FALLBACK.format(name=fname)
            )
            unused_reasons.append(note)
            if fname == card.primary_factor or spec.role == "primary":
                primary_invalid = True
                primary_unused.append(note)
            continue

        degree = match_degree(value, spec.interval)
        weighted += group.weight * degree
        weight_sum += group.weight
        valid_used += 1
        reason = _reason_for_match(fname, value, spec, cls.label_zh, degree)
        diagnostics = [
            FEATURE_LABEL_ZH.get(member, member)
            for member in group.factors
            if member != fname and fp.get(member) is not None
        ]
        if diagnostics:
            reason += f"（诊断成员 {', '.join(diagnostics)}，已去重）"
        contributions.append((group.weight, reason))

    score = (weighted / weight_sum) if weight_sum > 0 else 0.0
    contributions.sort(key=lambda item: item[0], reverse=True)
    reasons = [text for _, text in contributions[:TOP_REASONS]]
    for note in reversed(primary_unused):
        if note not in reasons:
            reasons.insert(0, note)
    remaining = [note for note in unused_reasons if note not in reasons]
    room = max(0, TOP_REASONS - len(reasons))
    reasons.extend(remaining[:room])
    if not reasons:
        reasons = [_NO_FACTORS_REASON]
    return score, reasons, primary_invalid, valid_used


def score_fingerprint(fp: Fingerprint, card: Scorecard) -> list[TypeResult]:
    scored: list[tuple[ClassSpec, float, list[str], bool, int]] = []
    for cls in card.classes:
        if card.evidence_groups:
            scored.append((cls, *_score_candidate_class(fp, cls, card)))
        else:
            scored.append((cls, *_score_class(fp, cls)))
    total = sum(item[1] for item in scored)
    results: list[TypeResult] = []
    for cls, score, reasons, primary_invalid, valid_used in scored:
        possibility = (score / total) if total > 0 else 0.0
        results.append(
            TypeResult(
                id=cls.id,
                label_zh=cls.label_zh,
                possibility=possibility,
                score=score,
                reasons=tuple(reasons),
                primary_invalid=primary_invalid,
                valid_used=valid_used,
            )
        )
    return results


def _valid_factor_count(fp: Fingerprint, card: Scorecard) -> int:
    names: set[str] = set()
    for cls in card.classes:
        names.update(cls.factors)
    return sum(1 for name in names if fp.get(name) is not None)


def decide_geometry_class(
    results: list[TypeResult],
    card: Scorecard,
    fp: Fingerprint,
) -> str:
    if card.evidence_groups:
        primary = card.primary_factor
        primary_value = fp.get(primary) if primary is not None else None
        if primary_value is None:
            return "unknown"

        primary_hits = [
            cls
            for cls in card.classes
            if primary in cls.factors
            and match_degree(primary_value, cls.factors[primary].interval) == 1.0
        ]
        if len(primary_hits) != 1:
            return "unknown"
        target = primary_hits[0].id

        auxiliary_support = 0
        for group in card.evidence_groups:
            factor = group.representative_factor
            if factor == primary:
                continue
            value = fp.get(factor)
            target_spec = primary_hits[0].factors.get(factor)
            if (
                value is not None
                and target_spec is not None
                and match_degree(value, target_spec.interval) == 1.0
            ):
                auxiliary_support += 1
        required_auxiliary = card.gates.min_auxiliary_groups or 1
        if auxiliary_support < required_auxiliary:
            return "unknown"

        if not results:
            return "unknown"
        highest_score = max(row.score for row in results)
        highest = [row for row in results if row.score == highest_score]
        if len(highest) != 1 or highest[0].id != target:
            return "unknown"
        return target

    if any(row.primary_invalid for row in results):
        return "unknown"
    min_valid = card.gates.min_valid_factors
    if min_valid is not None and _valid_factor_count(fp, card) < min_valid:
        return "unknown"
    if not results or all(row.score == 0 for row in results):
        return "unknown"
    ranked = sorted(results, key=lambda row: row.score, reverse=True)
    top = ranked[0]
    if card.gates.min_top_score is not None and top.score < card.gates.min_top_score:
        return "unknown"
    if len(ranked) >= 2 and card.gates.min_score_gap is not None:
        if ranked[0].score - ranked[1].score < card.gates.min_score_gap:
            return "unknown"
    return top.id
