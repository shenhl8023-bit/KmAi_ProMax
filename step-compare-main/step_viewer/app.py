# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import logging
import os
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from step_viewer.conversion_service import (
    ConversionService,
    FileTooLargeError,
    ModelRecord,
)
from step_viewer.tessellate import TessellateError

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
BROWSER_ENV = "STEP_VIEWER_OPEN_BROWSER"
PORT_ENV = "STEP_VIEWER_PORT"
logger = logging.getLogger(__name__)
conversion_service = ConversionService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get(BROWSER_ENV) == "1":
        port = os.environ.get(PORT_ENV, "8765")
        threading.Timer(
            0.3,
            lambda: webbrowser.open(f"http://127.0.0.1:{port}"),
        ).start()
    yield


app = FastAPI(title="STEP 比对", docs_url=None, redoc_url=None, lifespan=lifespan)


class TessellateMetadata(BaseModel):
    model_id: str
    name: str
    source_unit: str
    unit: str
    bounds: list[list[float]]
    extents: list[float]
    vertices: int
    faces: int
    glb_url: str
    cache_hit: bool


class ApiError(BaseModel):
    code: str
    message: str


def _status_for(code: str) -> int:
    if code == "FILE_TOO_LARGE":
        return 413
    if code == "MODEL_NOT_FOUND":
        return 404
    if code in {"INVALID_STEP", "UNSUPPORTED_UNIT", "EMPTY_MESH", "INVALID_GLB"}:
        return 422
    return 500


def _error_response(code: str, message: str, status_code: int | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code or _status_for(code),
        content=ApiError(code=code, message=message).model_dump(),
    )


def _legacy_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, TessellateError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.exception("Unexpected STEP conversion failure")
    return HTTPException(status_code=500, detail="服务内部错误")


def _metadata(record: ModelRecord) -> TessellateMetadata:
    return TessellateMetadata(
        model_id=record.model_id,
        name=record.name or "STEP",
        source_unit=record.source_unit,
        unit=record.unit,
        bounds=record.bounds,
        extents=record.extents,
        vertices=record.vertices,
        faces=record.faces,
        glb_url=f"/api/models/{record.model_id}.glb",
        cache_hit=record.cache_hit,
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/tessellate")
async def tessellate(file: UploadFile = File(...)):
    """Compatibility endpoint retaining the original Base64 JSON contract."""
    try:
        record = await conversion_service.convert_upload(file, file.filename or "")
    except (TessellateError, FileTooLargeError) as exc:
        raise _legacy_error(exc) from exc
    except Exception as exc:
        raise _legacy_error(exc) from exc
    return {
        "name": record.name or "STEP",
        "unit": record.unit,
        "bounds": record.bounds,
        "extents": record.extents,
        "vertices": record.vertices,
        "faces": record.faces,
        "glb": base64.b64encode(record.glb).decode("ascii"),
    }


@app.post("/api/tessellate/v2", response_model=TessellateMetadata, responses={
    404: {"model": ApiError},
    413: {"model": ApiError},
    422: {"model": ApiError},
    500: {"model": ApiError},
})
async def tessellate_v2(file: UploadFile = File(...)):
    try:
        record = await conversion_service.convert_upload(file, file.filename or "")
        return _metadata(record)
    except (TessellateError, FileTooLargeError) as exc:
        return _error_response(getattr(exc, "code", "INVALID_STEP"), str(exc))
    except Exception:
        logger.exception("Unexpected STEP conversion failure")
        return _error_response("INTERNAL_ERROR", "服务内部错误")


@app.get("/api/models/{model_id}.glb")
async def model_glb(model_id: str):
    glb = conversion_service.get_glb(model_id)
    if glb is None:
        return _error_response("MODEL_NOT_FOUND", "模型不存在或已过期")
    return Response(content=glb, media_type="model/gltf-binary")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
