# -*- coding: utf-8 -*-
"""Lifecycle management for the local feature-vector index."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path

from .feature_vector_matching import FeatureVectorError, FeatureVectorMatcher


class FeatureIndexManager(object):
    """Install an optional seed and run at most one incremental build."""

    def __init__(self, config, matcher=None, thread_factory=None):
        self.config = dict(config or {})
        self._matcher = matcher
        self._thread_factory = thread_factory or (lambda **kwargs: threading.Thread(**kwargs))
        self._lock = threading.RLock()
        self._thread = None
        self._state = self._new_state("not_started")

    @property
    def matcher(self):
        if self._matcher is None:
            self._matcher = FeatureVectorMatcher(self.config)
        return self._matcher

    @staticmethod
    def _new_state(state):
        return {
            "state": state,
            "jobId": "",
            "total": 0,
            "completed": 0,
            "cached": 0,
            "extracted": 0,
            "failed": 0,
            "currentFile": "",
            "errorCode": "",
            "message": "",
        }

    def _snapshot_locked(self):
        return dict(self._state)

    def _index_path(self):
        value = str(self.config.get("similar_parts_feature_index_file", "") or "").strip()
        return Path(value).resolve() if value else None

    def _install_seed_locked(self):
        target = self._index_path()
        seed_value = str(self.config.get("similar_parts_feature_index_seed_file", "") or "").strip()
        if target is None or target.is_file() or not seed_value:
            return False
        seed = Path(seed_value).resolve()
        if not seed.is_file():
            return False
        temporary = target.with_name(target.name + ".seed-" + uuid.uuid4().hex + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(seed), str(temporary))
            if not target.exists():
                os.replace(str(temporary), str(target))
                return True
        except OSError as exc:
            raise FeatureVectorError(
                "FEATURE_INDEX_INVALID", "预置特征索引无法安装，请检查文件或目录权限", 503
            ) from exc
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass
        return False

    def _quarantine_corrupt_locked(self):
        target = self._index_path()
        if target is None or not target.exists():
            return
        backup = Path(str(target) + ".corrupt-" + uuid.uuid4().hex)
        try:
            os.replace(str(target), str(backup))
        except OSError as exc:
            raise FeatureVectorError(
                "FEATURE_INDEX_INVALID", "特征索引无法重建，请检查文件或目录权限", 503
            ) from exc

    @staticmethod
    def _error_state(code, message):
        state = FeatureIndexManager._new_state("failed")
        state["errorCode"] = str(code or "FEATURE_INDEX_BUILD_FAILED")
        state["message"] = str(message or "特征索引准备失败")
        return state

    def _inspect_locked(self):
        self._install_seed_locked()
        return self.matcher.index_status()

    def _state_from_index_locked(self, info):
        state = self._new_state(str(info.get("state") or "incomplete"))
        state["total"] = int(info.get("total", 0) or 0)
        state["completed"] = int(info.get("indexed", 0) or 0)
        state["failed"] = 0
        state["message"] = "" if state["state"] == "ready" else "特征索引尚未完成"
        return state

    def _start_build_locked(self, info):
        job_id = uuid.uuid4().hex
        state = self._new_state("building")
        state["jobId"] = job_id
        state["total"] = int(info.get("total", 0) or 0)
        self._state = state
        try:
            self._thread = self._thread_factory(target=lambda: self._run_build(job_id), daemon=True)
            self._thread.start()
        except Exception as exc:
            self._state = self._error_state("FEATURE_INDEX_BUILD_FAILED", "特征索引任务无法启动")
            self._thread = None
            raise FeatureVectorError(
                "FEATURE_INDEX_BUILD_FAILED", "特征索引任务无法启动", 503
            ) from exc
        return self._snapshot_locked()

    def _run_build(self, job_id):
        def progress(index, total, name, status):
            with self._lock:
                if self._state.get("jobId") != job_id:
                    return
                self._state["total"] = int(total)
                self._state["completed"] = int(index)
                self._state["currentFile"] = str(name or "")
                if status == "cached":
                    self._state["cached"] += 1
                elif status == "extracted":
                    self._state["extracted"] += 1
                else:
                    self._state["failed"] += 1

        try:
            report = self.matcher.build(progress=progress)
            with self._lock:
                if self._state.get("jobId") != job_id:
                    return
                failed = list(report.get("failed") or [])
                self._state["total"] = int(report.get("total", self._state["total"]) or 0)
                self._state["completed"] = self._state["total"]
                self._state["cached"] = int(report.get("cached", self._state["cached"]) or 0)
                self._state["extracted"] = int(report.get("extracted", self._state["extracted"]) or 0)
                self._state["failed"] = len(failed)
                if failed:
                    first_code = str(failed[0].get("code") or "FEATURE_INDEX_BUILD_FAILED")
                    self._state["state"] = "failed"
                    self._state["errorCode"] = first_code
                    self._state["message"] = "仍有 %d 个零件未建立特征索引，请重试" % len(failed)
                else:
                    self._state["state"] = "ready"
                    self._state["errorCode"] = ""
                    self._state["message"] = ""
        except FeatureVectorError as exc:
            with self._lock:
                if self._state.get("jobId") == job_id:
                    self._state["state"] = "failed"
                    self._state["errorCode"] = exc.code
                    self._state["message"] = exc.message
        except Exception:
            with self._lock:
                if self._state.get("jobId") == job_id:
                    self._state["state"] = "failed"
                    self._state["errorCode"] = "FEATURE_INDEX_BUILD_FAILED"
                    self._state["message"] = "特征索引准备失败，请重试"
        finally:
            with self._lock:
                if self._state.get("jobId") == job_id:
                    self._thread = None

    def ensure(self):
        with self._lock:
            if self._state.get("state") == "building":
                return self._snapshot_locked()
            try:
                self._install_seed_locked()
                info = self.matcher.index_status()
                if info.get("state") == "invalid":
                    self._quarantine_corrupt_locked()
                    # Do not reinstall a seed that was just proven corrupt.
                    info = self.matcher.index_status()
            except FeatureVectorError as exc:
                self._state = self._error_state(exc.code, exc.message)
                return self._snapshot_locked()
            except Exception:
                self._state = self._error_state("FEATURE_INDEX_BUILD_FAILED", "特征索引准备失败，请重试")
                return self._snapshot_locked()
            if info.get("state") == "ready":
                self._state = self._state_from_index_locked(info)
                return self._snapshot_locked()
            return self._start_build_locked(info)

    def status(self):
        with self._lock:
            if self._state.get("state") == "not_started":
                try:
                    info = self._inspect_locked()
                    self._state = self._state_from_index_locked(info)
                except FeatureVectorError as exc:
                    self._state = self._error_state(exc.code, exc.message)
                except Exception:
                    self._state = self._error_state("FEATURE_INDEX_BUILD_FAILED", "特征索引检查失败，请重试")
            return self._snapshot_locked()
