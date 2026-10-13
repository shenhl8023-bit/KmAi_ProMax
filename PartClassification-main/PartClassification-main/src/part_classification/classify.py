from __future__ import annotations

from pathlib import Path

from part_classification.fingerprint import extract_fingerprint
from part_classification.scorecard import (
    LABEL_ZH,
    Scorecard,
    decide_geometry_class,
    load_scorecard,
    score_fingerprint,
)
from part_classification.similarity import find_similar_samples
from part_classification.template_map import TemplateMapError, template_for_sample
from part_classification.xml_read import KmsoftXmlError, read_kmsoft_xml


def _lookup_template(
    source: str | Path | bytes,
    template_map_path: str | Path | None,
) -> tuple[dict | None, str | None]:
    """返回 (模板信息, 错误码)。bytes 输入没有文件名，模板为 None。"""

    if isinstance(source, (bytes, bytearray)):
        return None, None
    try:
        info = template_for_sample(Path(source).name, map_path=template_map_path)
    except TemplateMapError as exc:
        # 一个坏配置文件不应让分类整体失败。
        return None, exc.code
    return info, None


def classify(
    source: str | Path | bytes,
    *,
    scorecard: Scorecard | None = None,
    scorecard_path: str | Path | None = None,
    similar_top_k: int = 3,
    samples_dir: str | Path | None = None,
    template_map_path: str | Path | None = None,
) -> dict:
    try:
        root = read_kmsoft_xml(source)
    except KmsoftXmlError as exc:
        return {
            "ok": False,
            "error": exc.error,
            "message": exc.message,
        }

    template_info, template_error = _lookup_template(source, template_map_path)

    card = scorecard if scorecard is not None else load_scorecard(scorecard_path)
    fingerprint = extract_fingerprint(root)
    if not card.locked:
        result = {
            "ok": True,
            "geometryClass": "unknown",
            "labelZh": LABEL_ZH["unknown"],
            "types": [],
        }
    else:
        results = score_fingerprint(fingerprint, card)
        geometry = decide_geometry_class(results, card, fingerprint)
        result = {
            "ok": True,
            "geometryClass": geometry,
            "labelZh": LABEL_ZH.get(geometry, geometry),
            "types": [
                {
                    "id": row.id,
                    "labelZh": row.label_zh,
                    "possibility": row.possibility,
                    "score": row.score,
                    "reasons": list(row.reasons),
                }
                for row in results
            ],
        }
        result["similarParts"] = find_similar_samples(
            fingerprint,
            scorecard=card,
            samples_dir=samples_dir,
            top_k=similar_top_k,
            template_map_path=template_map_path,
        )

    result["template"] = template_info
    if template_error is not None:
        result["templateError"] = template_error
    return result
