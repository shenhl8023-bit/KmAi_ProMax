# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class _PendingThread(object):
    def __init__(self, target, daemon=True):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


class _FakeMatcher(object):
    def __init__(self, index_path):
        self.index_path = Path(index_path)
        self.status_calls = 0
        self.build_calls = 0
        self.reports = []
        self.last_report = None

    def index_status(self):
        self.status_calls += 1
        if self.index_path.is_file() and self.index_path.read_bytes() == b"corrupt-seed":
            return {"state": "invalid", "total": 2, "indexed": 0, "missing": 2}
        if self.index_path.name == "corrupt.sqlite3" and self.index_path.is_file():
            return {"state": "invalid", "total": 2, "indexed": 0, "missing": 2}
        if self.build_calls == 0 and not self.index_path.exists():
            return {"state": "missing", "total": 2, "indexed": 0, "missing": 2}
        if self.last_report and self.last_report.get("failed"):
            return {"state": "incomplete", "total": 2, "indexed": 1, "missing": 1}
        return {"state": "ready", "total": 2, "indexed": 2, "missing": 0}

    def build(self, progress=None):
        self.build_calls += 1
        if progress:
            progress(1, 2, "一.xml", "extracted")
            progress(2, 2, "二.xml", "cached")
        report = self.reports.pop(0) if self.reports else {
            "total": 2, "extracted": 1, "cached": 1, "failed": []
        }
        self.last_report = report
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_bytes(b"index")
        return report


class FeatureIndexManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.index = root / "cache" / "features.sqlite3"
        self.seed = root / "Resources" / "seed.sqlite3"
        self.seed.parent.mkdir(parents=True)
        self.seed.write_bytes(b"seed-index")
        self.threads = []

    def tearDown(self):
        self.temp.cleanup()

    def manager(self, matcher=None):
        from KmMpsMcpServer.backend.feature_index_manager import FeatureIndexManager

        def factory(**kwargs):
            thread = _PendingThread(**kwargs)
            self.threads.append(thread)
            return thread

        return FeatureIndexManager(
            {
                "similar_parts_feature_index_file": str(self.index),
                "similar_parts_feature_index_seed_file": str(self.seed),
            },
            matcher=matcher or _FakeMatcher(self.index),
            thread_factory=factory,
        )

    def test_seed_is_installed_only_when_runtime_index_is_missing(self):
        matcher = _FakeMatcher(self.index)
        manager = self.manager(matcher)

        first = manager.ensure()
        self.assertEqual(first["state"], "ready")
        self.assertEqual(self.index.read_bytes(), b"seed-index")

        self.index.write_bytes(b"runtime-index")
        second = manager.ensure()
        self.assertEqual(second["state"], "ready")
        self.assertEqual(self.index.read_bytes(), b"runtime-index")

    def test_repeated_ensure_uses_one_job_and_reports_progress(self):
        matcher = _FakeMatcher(self.index)
        self.seed.unlink()
        manager = self.manager(matcher)

        first = manager.ensure()
        second = manager.ensure()
        self.assertEqual(first["state"], "building")
        self.assertEqual(first["jobId"], second["jobId"])
        self.assertEqual(len(self.threads), 1)
        self.assertTrue(self.threads[0].started)

        self.threads[0].target()
        done = manager.status()
        self.assertEqual(done["state"], "ready")
        self.assertEqual((done["completed"], done["cached"], done["extracted"]), (2, 1, 1))
        self.assertEqual(done["failed"], 0)

    def test_concurrent_ensure_starts_exactly_one_worker(self):
        self.seed.unlink()
        manager = self.manager()
        barrier = threading.Barrier(3)

        def ensure_at_once():
            barrier.wait(timeout=3)
            return manager.ensure()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ensure_at_once) for _ in range(2)]
            barrier.wait(timeout=3)
            snapshots = [future.result(timeout=3) for future in futures]
        self.assertEqual(len(self.threads), 1)
        self.assertEqual(snapshots[0]["state"], "building")
        self.assertEqual(snapshots[0]["jobId"], snapshots[1]["jobId"])

    def test_partial_failure_can_be_retried_without_losing_completed_entries(self):
        matcher = _FakeMatcher(self.index)
        matcher.reports = [
            {"total": 2, "extracted": 1, "cached": 0, "failed": [{"name": "二.xml", "code": "FEATURE_API_ERROR"}]},
            {"total": 2, "extracted": 1, "cached": 1, "failed": []},
        ]
        self.seed.unlink()
        manager = self.manager(matcher)

        building = manager.ensure()
        self.threads[0].target()
        failed = manager.status()
        self.assertEqual(building["state"], "building")
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["errorCode"], "FEATURE_API_ERROR")
        self.assertEqual(failed["failed"], 1)

        retry = manager.ensure()
        self.assertEqual(retry["state"], "building")
        self.assertEqual(len(self.threads), 2)
        self.threads[1].target()
        self.assertEqual(manager.status()["state"], "ready")

    def test_corrupt_runtime_index_is_quarantined_before_rebuild(self):
        corrupt = self.index.with_name("corrupt.sqlite3")
        corrupt.parent.mkdir(parents=True)
        corrupt.write_bytes(b"corrupt")
        self.seed.unlink()
        matcher = _FakeMatcher(corrupt)
        manager = self.manager(matcher)
        manager.config["similar_parts_feature_index_file"] = str(corrupt)

        result = manager.ensure()
        self.assertEqual(result["state"], "building")
        self.assertFalse(corrupt.exists())
        self.assertTrue(list(corrupt.parent.glob("corrupt.sqlite3.corrupt-*")))

    def test_corrupt_seed_copy_is_quarantined_without_changing_packaged_seed(self):
        corrupt_seed = self.seed
        corrupt_seed.write_bytes(b"corrupt-seed")
        matcher = _FakeMatcher(self.index)
        manager = self.manager(matcher)

        result = manager.ensure()
        self.assertEqual(result["state"], "building")
        self.assertEqual(corrupt_seed.read_bytes(), b"corrupt-seed")
        self.assertTrue(list(self.index.parent.glob("features.sqlite3.corrupt-*")))
        self.assertFalse(self.index.exists())
        self.assertEqual(manager.ensure()["jobId"], result["jobId"])


if __name__ == "__main__":
    unittest.main()
