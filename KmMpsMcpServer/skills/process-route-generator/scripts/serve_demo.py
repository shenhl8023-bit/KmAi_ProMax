#!/usr/bin/env python3
"""Serve a local demo UI for CAD input plus manual supplements."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import generate_matched_route as match_engine
import generate_route as route_engine


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = SKILL_ROOT / "demo"
V1_ROOT = SKILL_ROOT / "references" / "v1"
CAD_ROOT = SKILL_ROOT / "references" / "cad_reference"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sample_payload() -> Any:
    return load_json(ROOT / "样例_新零件输入.json")


def current_cad_payload() -> Any:
    desktop_input = ROOT.parent / "input.json"
    if desktop_input.exists():
        return load_json(desktop_input)
    return []


def build_runtime_payload(request_payload: dict[str, Any]) -> dict[str, Any]:
    cad_input = request_payload.get("cad_input")
    manual = request_payload.get("manual") or {}

    if not isinstance(cad_input, list):
        cad_input = current_cad_payload()

    if not isinstance(manual, dict):
        manual = {}

    return {
        "cad_features": cad_input,
        "manual": {
            "heat_treatment": manual.get("heat_treatment"),
            "surface_treatments": manual.get("surface_treatments", []),
            "inspection_items": manual.get("inspection_items", []),
            "marking_methods": manual.get("marking_methods", []),
            "special_process_flags": manual.get("special_process_flags", {}),
            "factor_overrides": manual.get("factor_overrides", {}),
        },
        "part_info": {
            "material_grade": manual.get("material_grade"),
            "part_type": manual.get("part_type"),
        },
    }


def load_references() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    factor_schema = load_json(V1_ROOT / "factor_schema.json")
    expansion_rules = load_json(V1_ROOT / "factor_expansion_rules.json")
    route_catalog = load_json(V1_ROOT / "route_catalog.json")
    route_rules = load_json(V1_ROOT / "route_rules.json")
    cad_catalog = load_json(CAD_ROOT / "cad_feature_catalog.json")
    group_match_rules = load_json(V1_ROOT / "group_match_rules.json")
    return factor_schema, expansion_rules, route_catalog, route_rules, cad_catalog, group_match_rules


def generate_demo_result(request_payload: dict[str, Any]) -> dict[str, Any]:
    factor_schema, expansion_rules, route_catalog, route_rules, cad_catalog, group_match_rules = load_references()
    runtime_payload = build_runtime_payload(request_payload)

    factors = route_engine.factors_from_v1_input(
        runtime_payload,
        factor_schema,
        expansion_rules,
        cad_catalog,
    )
    standard_route = route_engine.build_v1_route(factors, route_catalog, route_rules)
    matched_route = match_engine.build_matched_route_output(
        standard_route,
        runtime_payload["cad_features"],
        group_match_rules,
        cad_catalog,
        route_catalog,
    )
    export_route = match_engine.export_route_rows(matched_route)

    return {
        "normalized_input": runtime_payload,
        "factors": factors,
        "standard_route": standard_route,
        "matched_route": matched_route,
        "route": export_route,
    }


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "ProcessRouteDemo/1.0"

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(DEMO_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/sample-input":
            self._send_json(
                {
                    "cad_input": current_cad_payload(),
                    "manual": {
                        "material_grade": "9Cr18",
                        "heat_treatment": None,
                        "surface_treatments": [],
                        "inspection_items": ["裂纹检测"],
                        "marking_methods": ["标印"],
                        "special_process_flags": {
                            "shaped_hole_or_cut_flat": False,
                            "post_stage_added_hole": False,
                        },
                        "factor_overrides": {},
                    },
                }
            )
            return
        if parsed.path == "/api/references":
            factor_schema, _, route_catalog, _, cad_catalog, group_match_rules = load_references()
            self._send_json(
                {
                    "factor_schema": factor_schema,
                    "route_catalog": route_catalog,
                    "cad_catalog": cad_catalog,
                    "group_match_rules": group_match_rules,
                }
            )
            return

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate-route":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            request_payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=400)
            return

        try:
            result = generate_demo_result(request_payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=500)
            return

        self._send_json(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Serving demo on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
