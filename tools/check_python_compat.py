#!/usr/bin/env python3
"""Check runtime Python sources with an explicitly supplied CPython 3.8 x64."""

from __future__ import print_function

import json
import os
from pathlib import Path
import subprocess
import sys


_PROBE = (
    "import json, platform, struct, sys; "
    "print(json.dumps({'implementation': platform.python_implementation(), "
    "'version': [sys.version_info[0], sys.version_info[1]], "
    "'bits': struct.calcsize('P') * 8}))"
)
_COMPILE = r'''
import json, sys
errors = []
checked = 0
for raw_path in sys.argv[1:]:
    path = raw_path
    try:
        with open(path, 'rb') as stream:
            source = stream.read()
        compile(source, path, 'exec')
        checked += 1
    except Exception as exc:
        errors.append({'path': path, 'message': '%s: %s' % (type(exc).__name__, exc)})
print(json.dumps({'checked_files': checked, 'errors': errors}, ensure_ascii=False))
sys.exit(1 if errors else 0)
'''


def _run(command):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _source_files(sources):
    files = []
    for raw_source in sources:
        path = Path(raw_source).expanduser()
        if path.is_file():
            if path.suffix.lower() == ".py":
                files.append(path.resolve())
            continue
        if not path.is_dir():
            raise ValueError("source does not exist: %s" % path)
        files.extend(item.resolve() for item in path.rglob("*.py") if "__pycache__" not in item.parts)
    unique = {str(path): path for path in files}
    return [unique[key] for key in sorted(unique)]


def check_compatibility(python_exe, sources):
    """Return a JSON-safe result without importing any scanned source."""
    result = {"ok": False, "checked_files": 0, "errors": []}
    executable = str(python_exe or "").strip()
    if not executable:
        result.update({"error_code": "PYTHON_NOT_FOUND", "error": "python executable is required"})
        return result
    try:
        probe = _run([executable, "-I", "-c", _PROBE])
    except OSError:
        result.update({"error_code": "PYTHON_NOT_FOUND", "error": "python executable was not found"})
        return result
    if probe.returncode != 0:
        result.update({"error_code": "PYTHON_PROBE_FAILED", "error": "python probe failed"})
        return result
    try:
        identity = json.loads((probe.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError):
        result.update({"error_code": "PYTHON_PROBE_FAILED", "error": "python probe returned invalid data"})
        return result
    result["interpreter"] = identity
    if identity.get("implementation") != "CPython" or identity.get("version") != [3, 8] or identity.get("bits") != 64:
        result.update({"error_code": "PYTHON_VERSION_MISMATCH", "error": "CPython 3.8 x64 is required"})
        return result
    try:
        files = _source_files(sources)
    except ValueError as exc:
        result.update({"error_code": "SOURCE_NOT_FOUND", "error": str(exc)})
        return result
    if not files:
        result.update({"error_code": "NO_PYTHON_SOURCES", "error": "no Python sources were selected"})
        return result
    command = [executable, "-I", "-c", _COMPILE] + [str(path) for path in files]
    try:
        compiled = _run(command)
    except OSError:
        result.update({"error_code": "PYTHON_NOT_FOUND", "error": "python executable was not found"})
        return result
    try:
        compile_result = json.loads((compiled.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError):
        compile_result = {"checked_files": 0, "errors": []}
    result["checked_files"] = int(compile_result.get("checked_files", 0))
    result["errors"] = list(compile_result.get("errors", []))
    result["ok"] = compiled.returncode == 0 and not result["errors"]
    if not result["ok"]:
        result["error_code"] = "PYTHON_SOURCE_INCOMPATIBLE"
        result["error"] = "one or more Python sources failed to compile"
    return result


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--python-exe", required=True)
    parser.add_argument("--source", required=True, nargs="+")
    args = parser.parse_args(argv)
    result = check_compatibility(args.python_exe, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
