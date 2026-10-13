from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from part_classification.fingerprint import Fingerprint, extract_fingerprint
from part_classification.scorecard import (
    LABEL_ZH,
    Scorecard,
    decide_geometry_class,
    score_fingerprint,
)
from part_classification.template_map import TemplateMapError, template_for_sample
from part_classification.xml_read import KmsoftXmlError, read_kmsoft_xml

# The three cylinder-area factors are highly correlated. Keep the same
# representative factor used by the scorecard and add useful shape factors.
SIMILARITY_FEATURES = (
    "inner_cyl_balance",
    "inner_rev_ratio",
    "wall_to_outer",
    "plane_ratio",
    "hollow_ratio",
    "slenderness",
)


@dataclass(frozen=True)
class _SampleFingerprint:
    path: Path
    fingerprint: Fingerprint


def default_samples_dir() -> Path:
    """Return the repository's calibrated XML sample directory."""

    return Path(__file__).resolve().parents[2] / "source" / "XML样本"


def _xml_paths(samples_dir: Path) -> list[Path]:
    if not samples_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in samples_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".xml"
        ),
        key=lambda path: path.name.casefold(),
    )


def _load_samples(samples_dir: Path) -> list[_SampleFingerprint]:
    samples: list[_SampleFingerprint] = []
    for path in _xml_paths(samples_dir):
        try:
            fingerprint = extract_fingerprint(read_kmsoft_xml(path))
        except KmsoftXmlError:
            # A bad sample must not make an otherwise valid incoming XML fail.
            continue
        samples.append(_SampleFingerprint(path=path, fingerprint=fingerprint))
    return samples


def _ranges(samples: list[_SampleFingerprint]) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    for name in SIMILARITY_FEATURES:
        values = [
            sample.fingerprint.get(name)
            for sample in samples
            if sample.fingerprint.get(name) is not None
        ]
        if values:
            ranges[name] = (min(values), max(values))
    return ranges


def _distance(
    query: Fingerprint,
    sample: Fingerprint,
    ranges: dict[str, tuple[float, float]],
) -> tuple[float, int]:
    normalized: list[float] = []
    for name in SIMILARITY_FEATURES:
        query_value = query.get(name)
        sample_value = sample.get(name)
        bounds = ranges.get(name)
        if query_value is None or sample_value is None or bounds is None:
            continue
        low, high = bounds
        span = high - low
        if span == 0:
            normalized.append(0.0 if query_value == sample_value else 1.0)
        else:
            normalized.append(abs(query_value - sample_value) / span)
    if not normalized:
        return 1.0, 0
    return sum(normalized) / len(normalized), len(normalized)


def _sample_geometry(
    fingerprint: Fingerprint,
    scorecard: Scorecard,
) -> str:
    if not scorecard.locked:
        return "unknown"
    results = score_fingerprint(fingerprint, scorecard)
    return decide_geometry_class(results, scorecard, fingerprint)


def _sample_template(
    sample_name: str,
    template_map_path: str | Path | None,
) -> dict | None:
    """查样本自身绑定的模板；未绑定或清单损坏都返回 None。

    清单损坏时不抛异常：与 classify 的「坏清单不破坏分类」一致，也与本模块
    「坏样本跳过、不牵连整体」的既有做法一致。
    """

    try:
        return template_for_sample(sample_name, map_path=template_map_path)
    except TemplateMapError:
        return None


def find_similar_samples(
    query: Fingerprint,
    *,
    scorecard: Scorecard,
    samples_dir: str | Path | None = None,
    top_k: int = 3,
    template_map_path: str | Path | None = None,
) -> list[dict]:
    """Find up to top_k nearest calibrated XML samples.

    Similarity is 1 minus the mean normalized absolute difference over the
    six non-correlated shape factors. Invalid values are skipped. Each row
    carries its own ``template`` (None when unbound).
    """

    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
        raise ValueError("top_k 必须是 1 到 5 之间的整数")

    directory = Path(samples_dir) if samples_dir is not None else default_samples_dir()
    samples = _load_samples(directory)
    if not samples:
        return []

    ranges = _ranges(samples)
    ranked: list[tuple[float, int, Path, Fingerprint]] = []
    for sample in samples:
        distance, valid_count = _distance(query, sample.fingerprint, ranges)
        if valid_count == 0 or distance <= 1e-12:
            # Do not recommend the input itself when it is one of the samples.
            continue
        similarity = max(0.0, min(1.0, 1.0 - distance))
        ranked.append((similarity, valid_count, sample.path, sample.fingerprint))

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2].name.casefold()))
    output: list[dict] = []
    for similarity, valid_count, path, fingerprint in ranked[:top_k]:
        geometry = _sample_geometry(fingerprint, scorecard)
        output.append(
            {
                "id": path.stem,
                "name": path.name,
                "template": _sample_template(path.name, template_map_path),
                "path": str(path.resolve()),
                "geometryClass": geometry,
                "labelZh": LABEL_ZH.get(geometry, geometry),
                "similarity": round(similarity, 6),
                "validFactors": valid_count,
            }
        )
    return output


find_similar_parts = find_similar_samples


__all__ = [
    "SIMILARITY_FEATURES",
    "default_samples_dir",
    "find_similar_parts",
    "find_similar_samples",
]
