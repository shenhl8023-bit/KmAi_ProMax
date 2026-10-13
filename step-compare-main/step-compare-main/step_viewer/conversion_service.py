# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Callable

from starlette.datastructures import UploadFile

from step_viewer.tessellate import TessellateResult, _part_name, tessellate_step


DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_CACHE_ENTRIES = 4
DEFAULT_MAX_CACHE_BYTES = 128 * 1024 * 1024
DEFAULT_CACHE_TTL_SECONDS = 30 * 60
DEFAULT_CONVERSION_CONCURRENCY = 1
READ_CHUNK_BYTES = 1024 * 1024


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


class FileTooLargeError(Exception):
    code = "FILE_TOO_LARGE"

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"上传文件超过 {limit // (1024 * 1024)} MB 限制")


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    name: str
    source_unit: str
    unit: str
    bounds: list[list[float]]
    extents: list[float]
    vertices: int
    faces: int
    glb: bytes
    cache_hit: bool


@dataclass
class _CacheEntry:
    key: str
    result: TessellateResult
    expires_at: float
    size: int


class ConversionService:
    """Bounded in-memory STEP conversion service shared by both API versions."""

    def __init__(
        self,
        *,
        max_upload_bytes: int | None = None,
        max_cache_entries: int | None = None,
        max_cache_bytes: int | None = None,
        cache_ttl_seconds: int | None = None,
        conversion_concurrency: int | None = None,
        converter: Callable[[bytes, str], TessellateResult] = tessellate_step,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_upload_bytes = max_upload_bytes or _env_int(
            "STEP_VIEWER_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES
        )
        self.max_cache_entries = max_cache_entries or _env_int(
            "STEP_VIEWER_MAX_CACHE_ENTRIES", DEFAULT_MAX_CACHE_ENTRIES
        )
        self.max_cache_bytes = max_cache_bytes or _env_int(
            "STEP_VIEWER_MAX_CACHE_BYTES", DEFAULT_MAX_CACHE_BYTES
        )
        self.cache_ttl_seconds = cache_ttl_seconds or _env_int(
            "STEP_VIEWER_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS
        )
        self.conversion_concurrency = conversion_concurrency or _env_int(
            "STEP_VIEWER_CONVERSION_CONCURRENCY", DEFAULT_CONVERSION_CONCURRENCY
        )
        self._converter = converter
        self._clock = clock
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._cache_bytes = 0
        self._semaphore = asyncio.Semaphore(self.conversion_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=self.conversion_concurrency,
            thread_name_prefix="step-convert",
        )

    async def convert_upload(self, upload: UploadFile, filename: str = "") -> ModelRecord:
        data = await read_upload_limited(upload, self.max_upload_bytes)
        return await self.convert_bytes(data, filename or upload.filename or "")

    async def convert_bytes(self, data: bytes, filename: str = "") -> ModelRecord:
        if len(data) > self.max_upload_bytes:
            raise FileTooLargeError(self.max_upload_bytes)
        key = hashlib.sha256(data).hexdigest()
        entry = self._get_entry(key)
        if entry is not None:
            return self._record(entry, filename, cache_hit=True)

        async with self._semaphore:
            # A request that waited for the worker may find a freshly cached result.
            entry = self._get_entry(key)
            if entry is None:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(self._executor, self._converter, data, filename)
                entry = self._put_entry(key, replace(result, name=""))
                return self._record(entry, filename, cache_hit=False)
            return self._record(entry, filename, cache_hit=True)

    def get_glb(self, model_id: str) -> bytes | None:
        entry = self._get_entry(model_id)
        return bytes(entry.result.glb) if entry is not None else None

    def _record(self, entry: _CacheEntry, filename: str, cache_hit: bool) -> ModelRecord:
        result = entry.result
        return ModelRecord(
            model_id=entry.key,
            name=_part_name(filename),
            source_unit=result.source_unit,
            unit=result.unit,
            bounds=result.bounds,
            extents=result.extents,
            vertices=result.vertices,
            faces=result.faces,
            glb=result.glb,
            cache_hit=cache_hit,
        )

    def _get_entry(self, key: str) -> _CacheEntry | None:
        self._purge_expired()
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        return entry

    def _put_entry(self, key: str, result: TessellateResult) -> _CacheEntry:
        self._purge_expired()
        existing = self._cache.pop(key, None)
        if existing:
            self._cache_bytes -= existing.size
        entry = _CacheEntry(
            key=key,
            result=result,
            expires_at=self._clock() + self.cache_ttl_seconds,
            size=len(result.glb),
        )
        self._cache[key] = entry
        self._cache_bytes += entry.size
        while self._cache and (
            len(self._cache) > self.max_cache_entries or self._cache_bytes > self.max_cache_bytes
        ):
            _, removed = self._cache.popitem(last=False)
            self._cache_bytes -= removed.size
        return entry

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [key for key, entry in self._cache.items() if entry.expires_at <= now]
        for key in expired:
            entry = self._cache.pop(key)
            self._cache_bytes -= entry.size

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
