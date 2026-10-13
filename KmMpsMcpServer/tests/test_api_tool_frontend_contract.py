import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES = ROOT / "frontend" / "assets" / "modules"


class ApiToolFrontendContractTest(unittest.TestCase):
    def _read(self, name):
        return (MODULES / name).read_text(encoding="utf-8")

    def test_request_json_preserves_structured_http_error(self):
        source = self._read("shared.js")
        self.assertIn("error.httpStatus = xhr.status;", source)
        self.assertIn("error.errorCode = data && data.error_code ? data.error_code : '';", source)
        self.assertIn("error.payload = data;", source)

    def test_all_direct_tool_consumers_import_shared_predicate(self):
        for filename in ("workflow.js", "process_route.js", "tool_call.js"):
            with self.subTest(filename=filename):
                source = self._read(filename)
                self.assertIn("isToolSuccess", source.split("from './shared.js';", 1)[0])

    def test_direct_tool_consumers_do_not_use_private_success_predicates(self):
        combined = "\n".join(
            self._read(name)
            for name in ("workflow.js", "process_route.js", "tool_call.js")
        )
        self.assertNotIn("result && result.status === 'success'", combined)
        self.assertNotIn("result && result.status === 'error'", combined)
        self.assertNotIn("result && result.ok !== false", combined)

    def test_is_tool_success_rejects_explicit_and_nested_failures(self):
        script = r"""
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

globalThis.window = {};
globalThis.document = { getElementById() { return null; }, createElement() { return {}; } };
globalThis.localStorage = { getItem() { return null; }, setItem() {} };

const source = process.argv[1];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kmai-shared-'));
const target = path.join(dir, 'shared.mjs');
fs.copyFileSync(source, target);
const mod = await import(pathToFileURL(target).href);
const results = {
  success: mod.isToolSuccess({ status: 'success' }),
  ok: mod.isToolSuccess({ ok: true }),
  explicitFailureWins: mod.isToolSuccess({ status: 'success', ok: false }),
  errorCodeFails: mod.isToolSuccess({ ok: true, error_code: 'BROKEN' }),
  nestedFailure: mod.isToolSuccess({ status: 'success', result: { ok: false } })
};
process.stdout.write(JSON.stringify(results));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script, str(MODULES / "shared.js")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            {
                "success": True,
                "ok": True,
                "explicitFailureWins": False,
                "errorCodeFails": False,
                "nestedFailure": False,
            },
            json.loads(completed.stdout),
        )

    def test_call_tool_rehydrates_structured_http_failure_for_shared_predicate(self):
        script = r"""
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

globalThis.window = {};
globalThis.document = { getElementById() { return null; }, createElement() { return {}; } };
globalThis.localStorage = { getItem() { return null; }, setItem() {} };
class FakeXHR {
  open() {}
  setRequestHeader() {}
  send() {
    this.status = 422;
    this.responseText = JSON.stringify({
      status: 'error',
      error_code: 'TOOL_EXECUTION_FAILED',
      message: 'business failed',
      result: { ok: false, message: 'business failed' }
    });
    this.onload();
  }
}
globalThis.XMLHttpRequest = FakeXHR;

const source = process.argv[1];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kmai-shared-'));
const target = path.join(dir, 'shared.mjs');
fs.copyFileSync(source, target);
const mod = await import(pathToFileURL(target).href);
const result = await mod.callTool('broken_tool', {}, 5, 1000);
process.stdout.write(JSON.stringify({ result, success: mod.isToolSuccess(result) }));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script, str(MODULES / "shared.js")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            {
                "result": {"ok": False, "message": "business failed"},
                "success": False,
            },
            json.loads(completed.stdout),
        )

    def test_call_tool_does_not_swallow_api_error_without_tool_result(self):
        script = r"""
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

globalThis.window = {};
globalThis.document = { getElementById() { return null; }, createElement() { return {}; } };
globalThis.localStorage = { getItem() { return null; }, setItem() {} };
class FakeXHR {
  open() {}
  setRequestHeader() {}
  send() {
    this.status = 403;
    this.responseText = JSON.stringify({
      status: 'error',
      error_code: 'AUTH_REQUIRED',
      message: 'authentication required'
    });
    this.onload();
  }
}
globalThis.XMLHttpRequest = FakeXHR;

const source = process.argv[1];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kmai-shared-'));
const target = path.join(dir, 'shared.mjs');
fs.copyFileSync(source, target);
const mod = await import(pathToFileURL(target).href);
let captured = null;
try {
  await mod.callTool('check_3dmps_status', {}, 5, 1000);
} catch (error) {
  captured = { message: error.message, httpStatus: error.httpStatus, errorCode: error.errorCode };
}
process.stdout.write(JSON.stringify(captured));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script, str(MODULES / "shared.js")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            {
                "message": "authentication required",
                "httpStatus": 403,
                "errorCode": "AUTH_REQUIRED",
            },
            json.loads(completed.stdout),
        )


if __name__ == "__main__":
    unittest.main()
