#!/usr/bin/env python3
"""Build offline GLB assets from STEP files on the build machine only."""

from __future__ import print_function

import argparse
from importlib import util as importlib_util
import json
from pathlib import Path
import sys


class GlbCacheError(RuntimeError):
    pass


def _output_path(output_root, filename):
    root = Path(output_root).expanduser().resolve()
    target = (root / filename).resolve()
    try:
        inside = target == root or root in target.parents
    except Exception:
        inside = False
    if not inside:
        raise GlbCacheError("generated output escapes output directory")
    return target


def _load_tessellator(step_viewer_root):
    root = Path(step_viewer_root).expanduser().resolve()
    if not root.is_dir():
        raise GlbCacheError("STEP viewer root does not exist: %s" % root)
    module_path = root / "step_viewer" / "tessellate.py"
    if not module_path.is_file():
        raise GlbCacheError("STEP viewer tessellator does not exist: %s" % module_path)
    try:
        # Load from the requested root instead of trusting a previously
        # imported ``step_viewer`` package from another test or checkout.
        module_name = "_kmai_step_viewer_tessellate"
        spec = importlib_util.spec_from_file_location(module_name, str(module_path))
        if spec is None or spec.loader is None:
            raise ImportError("unable to create module spec")
        module = importlib_util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module.tessellate_step
    except Exception as exc:
        raise GlbCacheError("STEP viewer tessellator is unavailable") from exc


def _metadata(result, stem):
    return {
        "name": stem,
        "bounds": getattr(result, "bounds", None),
        "extents": getattr(result, "extents", None),
        "vertices": int(getattr(result, "vertices", 0) or 0),
        "faces": int(getattr(result, "faces", 0) or 0),
        "unit": getattr(result, "unit", "mm"),
        "sourceUnit": getattr(result, "source_unit", "mm"),
        "source": "build-glb-cache",
    }


def build_cache(step_viewer_root, input_dir, output_dir):
    source_root = Path(input_dir).expanduser().resolve()
    if not source_root.is_dir():
        raise GlbCacheError("STEP input directory does not exist: %s" % source_root)
    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir():
        raise GlbCacheError("GLB output path is not a directory: %s" % output_root)
    tessellate_step = _load_tessellator(step_viewer_root)
    sources = sorted(
        (item for item in source_root.iterdir() if item.is_file() and item.suffix.lower() in (".stp", ".step")),
        key=lambda item: item.name.casefold(),
    )
    if not sources:
        raise GlbCacheError("no STEP files found")
    built = []
    for source in sources:
        stem = source.stem
        glb_path = _output_path(output_root, stem + ".glb")
        metadata_path = _output_path(output_root, stem + ".json")
        try:
            result = tessellate_step(source.read_bytes(), source.name)
            glb = bytes(getattr(result, "glb"))
        except Exception as exc:
            raise GlbCacheError("STEP conversion failed for %s" % source.name) from exc
        if not glb.startswith(b"glTF"):
            raise GlbCacheError("STEP converter returned an invalid GLB for %s" % source.name)
        metadata = _metadata(result, stem)
        glb_path.write_bytes(glb)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        built.append({"source": source.name, "glb": glb_path.name, "metadata": metadata_path.name})
    return {"built": len(built), "files": built, "output_dir": str(output_root)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--step-viewer-root", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_cache(args.step_viewer_root, args.input_dir, args.output_dir)
    except GlbCacheError as exc:
        print("GLB_CACHE_ERROR: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
