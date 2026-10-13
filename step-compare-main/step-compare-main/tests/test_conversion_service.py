# -*- coding: utf-8 -*-
import asyncio
import io

import pytest
from starlette.datastructures import UploadFile

from step_viewer.conversion_service import (
    ConversionService,
    FileTooLargeError,
    read_upload_limited,
)
from step_viewer.tessellate import TessellateResult


def fake_result(data: bytes, filename: str) -> TessellateResult:
    return TessellateResult(
        name=filename,
        glb=b"glTF" + data,
        bounds=[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
        extents=[1.0, 1.0, 1.0],
        vertices=3,
        faces=1,
        unit="mm",
        source_unit="mm",
    )


def upload(data: bytes, name: str = "part.stp") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


def test_read_upload_allows_exact_limit_and_rejects_one_extra_byte():
    async def run():
        assert await read_upload_limited(upload(b"12345"), 5) == b"12345"
        with pytest.raises(FileTooLargeError):
            await read_upload_limited(upload(b"123456"), 5)

    asyncio.run(run())


def test_cache_hit_uses_content_key_but_current_filename():
    calls = []

    def convert(data, filename):
        calls.append(filename)
        return fake_result(data, filename)

    service = ConversionService(converter=convert, max_cache_bytes=1024)

    async def run():
        first = await service.convert_upload(upload(b"same", "first.stp"))
        second = await service.convert_upload(upload(b"same", "second.stp"))
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert second.name == "second"
        assert first.model_id == second.model_id
        assert calls == ["first.stp"]

    asyncio.run(run())
    service.close()


def test_cache_ttl_and_capacity_eviction():
    now = [0.0]

    def convert(data, filename):
        return fake_result(data, filename)

    service = ConversionService(
        converter=convert,
        max_cache_entries=2,
        max_cache_bytes=100,
        cache_ttl_seconds=10,
        clock=lambda: now[0],
    )

    async def run():
        one = await service.convert_bytes(b"one", "one.stp")
        await service.convert_bytes(b"two", "two.stp")
        await service.convert_bytes(b"three", "three.stp")
        assert service.get_glb(one.model_id) is None
        now[0] = 11
        assert service.get_glb(one.model_id) is None

    asyncio.run(run())
    service.close()


def test_conversion_is_limited_to_configured_concurrency():
    active = [0]
    maximum = [0]

    def convert(data, filename):
        active[0] += 1
        maximum[0] = max(maximum[0], active[0])
        import time

        time.sleep(0.03)
        active[0] -= 1
        return fake_result(data, filename)

    service = ConversionService(converter=convert, conversion_concurrency=1)

    async def run():
        await asyncio.gather(
            service.convert_bytes(b"a", "a.stp"),
            service.convert_bytes(b"b", "b.stp"),
        )

    asyncio.run(run())
    assert maximum[0] == 1
    service.close()
