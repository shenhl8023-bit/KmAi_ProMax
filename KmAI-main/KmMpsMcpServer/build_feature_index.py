#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Incrementally index the configured XML library using the feature API."""
import argparse
import json
import sys
from pathlib import Path

from backend import agent_config
from backend.feature_vector_matching import FeatureVectorError, FeatureVectorMatcher


def main():
    parser = argparse.ArgumentParser(description="Build or update the XML feature vector index.")
    parser.add_argument("--config", default=agent_config.CONFIG_PATH, help="Path to local config.ini")
    args = parser.parse_args()
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.is_file():
        print(json.dumps({"error": "CONFIG_NOT_FOUND", "message": "配置文件不存在"}, ensure_ascii=False))
        return 1
    agent_config.CONFIG_PATH = str(config_path)
    agent_config.CONFIG_BASE_DIR = str(config_path.parent)
    config = agent_config._load_config()
    if config.get("similar_parts_matching_backend") != "feature_vector":
        print(json.dumps({"error": "MATCHING_BACKEND_INVALID"}, ensure_ascii=False))
        return 1

    def progress(index, total, name, status):
        print("[%d/%d] %s: %s" % (index, total, name, status), file=sys.stderr, flush=True)

    try:
        report = FeatureVectorMatcher(config).build(progress=progress)
    except FeatureVectorError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
