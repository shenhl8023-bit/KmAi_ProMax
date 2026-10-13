from __future__ import annotations

import argparse
import json
import sys

from part_classification.classify import classify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="part-classify")
    parser.add_argument("xml_path")
    parser.add_argument("--scorecard")
    parser.add_argument(
        "--similar-top-k",
        type=int,
        choices=(1, 2, 3),
        default=3,
        help="返回最相似的学习样本数量（1-3，默认 3）",
    )
    parser.add_argument(
        "--samples-dir",
        help="学习 XML 样本目录；默认使用 source/XML样本",
    )
    parser.add_argument(
        "--template-map",
        help="样本模板映射清单路径；默认使用 source/模板/模板映射.json",
    )
    args = parser.parse_args(argv)
    result = classify(
        args.xml_path,
        scorecard_path=args.scorecard,
        similar_top_k=args.similar_top_k,
        samples_dir=args.samples_dir,
        template_map_path=args.template_map,
    )
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    if stdout_buffer is not None and (sys.stdout.encoding or "").lower() not in {"utf-8", "utf8"}:
        stdout_buffer.write(output.encode("utf-8"))
    else:
        sys.stdout.write(output)
    return 0 if result.get("ok") else 1
