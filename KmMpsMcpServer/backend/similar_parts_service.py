# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import secrets
import shutil
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

from .feature_index_manager import FeatureIndexManager
from .feature_vector_matching import FeatureVectorError, FeatureVectorMatcher, MAX_TOP_K, validate_xml


class SimilarPartsError(Exception):
    def __init__(self, code, message, http_status=400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = int(http_status)
        self.details = dict(details or {})


class SimilarPartsService(object):
    """Feature vector similarity, controlled model access, and template handoff."""

    def __init__(self, config, matcher=None, tessellator=None, clock=None, index_manager=None):
        self.config = dict(config or {})
        self._matcher = matcher
        self._index_manager = index_manager or FeatureIndexManager(self.config, matcher=matcher)
        self._tessellator = tessellator
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._uploads = OrderedDict()
        self._models = {}
        self._model_cache = OrderedDict()
        self._model_cache_bytes = 0

    @property
    def enabled(self):
        return bool(self.config.get("similar_parts_enabled", True))

    def _ttl(self):
        return max(1, int(self.config.get("similar_parts_cache_ttl_seconds", 1800)))

    def _now(self):
        return float(self._clock())

    def _token(self):
        return secrets.token_urlsafe(18)

    def _add_import_root(self, key):
        root = str(self.config.get(key, "") or "").strip()
        candidates = []
        if root:
            candidates.append(root)
            src = os.path.join(root, "src")
            if os.path.isdir(src):
                candidates.insert(0, src)
        for candidate in reversed(candidates):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)

    def _load_tessellator(self):
        if self._tessellator is not None:
            return
        self._add_import_root("similar_parts_step_viewer_root")
        try:
            from step_viewer.tessellate import tessellate_step

            self._tessellator = tessellate_step
        except Exception as exc:
            raise SimilarPartsError("STEP_CONVERTER_UNAVAILABLE", "STEP 模型转换组件不可用", 503) from exc

    def _win7_lite_mode(self):
        value = self.config.get("similar_parts_win7_lite_mode", False)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _find_prebuilt_model(self, display_name, source_path=None):
        root_value = str(self.config.get("similar_parts_prebuilt_model_dir", "") or "").strip()
        if not root_value:
            raise SimilarPartsError(
                "PREBUILT_MODEL_DIR_MISSING",
                "Win7 Lite 模式未配置预生成 GLB 目录",
                500,
            )
        root = Path(root_value).resolve()
        if not root.is_dir():
            raise SimilarPartsError(
                "PREBUILT_MODEL_DIR_MISSING",
                "预生成 GLB 目录不存在",
                500,
            )
        stems = []
        for value in (display_name, source_path):
            stem = Path(str(value or "")).stem
            if stem and stem.casefold() not in [item.casefold() for item in stems]:
                stems.append(stem)
        if not stems:
            raise SimilarPartsError("PREBUILT_MODEL_MISSING", "预生成 GLB 文件不存在", 404)
        matches = [
            path for path in root.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".glb"
            and path.stem.casefold() in [item.casefold() for item in stems]
        ]
        stem_order = {stem.casefold(): index for index, stem in enumerate(stems)}
        matches.sort(
            key=lambda path: (
                stem_order.get(path.stem.casefold(), len(stems)),
                path.name.casefold(),
            )
        )
        if not matches:
            raise SimilarPartsError(
                "PREBUILT_MODEL_MISSING",
                "零件 %s 缺少预生成 GLB 文件" % stems[0],
                500,
            )
        target = matches[0].resolve()
        if not self._inside(root, target):
            raise SimilarPartsError("PREBUILT_MODEL_MISSING", "预生成 GLB 文件不存在", 500)
        return target

    @staticmethod
    def _read_prebuilt_metadata(path, display_name):
        metadata = {
            "name": str(display_name),
            "source": "prebuilt-glb",
            "bounds": None,
            "extents": None,
            "vertices": 0,
            "faces": 0,
            "unit": "mm",
            "sourceUnit": "mm",
        }
        sidecar = path.with_suffix(".json")
        if not sidecar.is_file():
            return metadata
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError, TypeError):
            return metadata
        if not isinstance(raw, dict):
            return metadata
        for key in ("bounds", "extents", "vertices", "faces", "unit", "sourceUnit"):
            if key in raw:
                metadata[key] = raw[key]
        return metadata

    def _purge(self):
        now = self._now()
        expired_uploads = [key for key, row in self._uploads.items() if row["expiresAt"] <= now]
        for key in expired_uploads:
            self._uploads.pop(key, None)
        expired_models = [key for key, row in self._models.items() if row["expiresAt"] <= now]
        for key in expired_models:
            self._models.pop(key, None)
            self._drop_cached_model(key)

    def _drop_cached_model(self, model_id):
        cached = self._model_cache.pop(model_id, None)
        if cached:
            self._model_cache_bytes -= cached["size"]

    def upload_xml(self, filename, content):
        if not self.enabled:
            raise SimilarPartsError("FEATURE_DISABLED", "相似零件查询未启用", 503)
        safe_name = os.path.basename(str(filename or "").strip())
        if not safe_name or safe_name != str(filename or "").strip() or Path(safe_name).suffix.lower() != ".xml":
            raise SimilarPartsError("INVALID_XML_FILE", "请选择有效的 XML 文件")
        if not isinstance(content, (bytes, bytearray)):
            raise SimilarPartsError("INVALID_XML", "XML 文件内容无效")
        data = bytes(content)
        max_bytes = max(1, int(self.config.get("similar_parts_upload_max_bytes", 5 * 1024 * 1024)))
        if len(data) > max_bytes:
            raise SimilarPartsError("XML_TOO_LARGE", "XML 文件超过上传大小限制", 413)
        if not data:
            raise SimilarPartsError("INVALID_XML", "XML 文件内容为空")
        try:
            validate_xml(data)
        except FeatureVectorError as exc:
            raise SimilarPartsError(exc.code, exc.message, exc.http_status) from exc

        upload_id = self._token()
        with self._lock:
            self._purge()
            while len(self._uploads) >= 32:
                self._uploads.popitem(last=False)
            self._uploads[upload_id] = {
                "filename": safe_name,
                "stem": Path(safe_name).stem,
                "content": data,
                "expiresAt": self._now() + self._ttl(),
                "candidates": {},
            }
        return {"uploadId": upload_id, "filename": safe_name, "size": len(data)}

    def _get_upload(self, upload_id):
        with self._lock:
            self._purge()
            row = self._uploads.get(str(upload_id or ""))
            if row is None:
                raise SimilarPartsError("UPLOAD_NOT_FOUND", "上传记录不存在或已过期", 404)
            self._uploads.move_to_end(str(upload_id))
            return row

    @staticmethod
    def _inside(root, target):
        try:
            root_path = Path(root).resolve()
            target_path = Path(target).resolve()
            return os.path.commonpath([str(root_path), str(target_path)]) == str(root_path)
        except Exception:
            return False

    def _find_step(self, stem):
        directory = Path(str(self.config.get("similar_parts_step_library_dir", "") or ""))
        if not directory.is_dir():
            raise SimilarPartsError("STEP_LIBRARY_MISSING", "STEP 模型库目录不存在", 500)
        matches = [
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in (".stp", ".step") and path.stem.casefold() == str(stem).casefold()
        ]
        if not matches:
            raise SimilarPartsError("STEP_FILE_MISSING", "零件 %s 缺少同名 STEP 文件" % stem, 500)
        matches.sort(key=lambda path: (path.suffix.lower() != ".stp", path.name.casefold()))
        return matches[0].resolve()

    def _find_current_step(self, stem):
        configured = str(self.config.get("similar_parts_current_step_file", "") or "").strip()
        # 当前零件使用固定 stepModel 文件；只有未配置固定文件时才回退到旧的同名查找。
        if configured:
            path = Path(configured).resolve()
            if path.suffix.lower() not in (".stp", ".step") or not path.is_file():
                raise SimilarPartsError("CURRENT_STEP_FILE_MISSING", "当前零件 STEP 文件不存在", 500)
            return path, path.parent
        try:
            return self._find_step(stem), self.config.get("similar_parts_step_library_dir")
        except SimilarPartsError:
            raise

    def _current_xml_path(self):
        configured = str(self.config.get("similar_parts_current_xml_file", "") or "").strip()
        if configured:
            path = Path(configured).resolve()
            if path.suffix.lower() != ".xml" or not path.is_file():
                raise SimilarPartsError("CURRENT_XML_FILE_MISSING", "当前零件 XML 文件不存在", 500)
            return path

        directory_value = str(self.config.get("similar_parts_current_part_dir", "") or "").strip()
        if not directory_value:
            configured_step = str(self.config.get("similar_parts_current_step_file", "") or "").strip()
            if configured_step:
                directory_value = str(Path(configured_step).expanduser().parent)
        if not directory_value:
            raise SimilarPartsError("CURRENT_XML_NOT_CONFIGURED", "当前零件 XML 固定路径未配置", 500)
        directory = Path(directory_value).resolve()
        if not directory.is_dir():
            raise SimilarPartsError("CURRENT_PART_DIR_MISSING", "当前零件固定目录不存在", 500)
        matches = sorted(
            (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".xml"),
            key=lambda path: path.name.casefold(),
        )
        if not matches:
            raise SimilarPartsError("CURRENT_XML_FILE_MISSING", "当前零件固定目录中没有 XML 文件", 500)
        if len(matches) != 1:
            raise SimilarPartsError("CURRENT_XML_AMBIGUOUS", "当前零件固定目录中的 XML 文件不唯一", 500)
        return matches[0].resolve()

    def load_current_part(self):
        """读取固定目录当前 XML，并返回可用于后续查询的上传记录。"""
        xml_path = self._current_xml_path()
        configured_step = str(self.config.get("similar_parts_current_step_file", "") or "").strip()
        if configured_step:
            step_path = Path(configured_step).resolve()
            if step_path.suffix.lower() not in (".stp", ".step") or not step_path.is_file():
                raise SimilarPartsError("CURRENT_STEP_FILE_MISSING", "当前零件 STEP 文件不存在", 500)
        else:
            step_path, _root = self._find_current_step(xml_path.stem)
        try:
            result = self.upload_xml(xml_path.name, xml_path.read_bytes())
        except OSError as exc:
            raise SimilarPartsError("CURRENT_XML_UNREADABLE", "当前零件 XML 文件无法读取", 500) from exc
        result.update({
            "stepFilename": step_path.name,
            "stepPath": str(step_path),
        })
        return result

    def _register_model(self, path, display_name, expires_at, allowed_root=None):
        model_id = self._token()
        self._models[model_id] = {
            "path": Path(path).resolve(),
            "name": str(display_name),
            "root": Path(allowed_root or self.config.get("similar_parts_step_library_dir", "")).resolve(),
            "expiresAt": expires_at,
        }
        return model_id

    def _template_source(self, candidate):
        template = candidate.get("template") if isinstance(candidate, dict) else None
        template_name = str((template or {}).get("name") or "").strip()
        raw_path = str((template or {}).get("path") or "").strip()
        if not template_name:
            # 外部零件库可能使用不同的扩展名大小写（例如 ``.xml``），
            # 而模板映射沿用项目样本的 ``.XML`` 键。保留模板管理模块的
            # 精确匹配语义，只在查询结果落到服务层时做兼容查找。
            candidate_name = str(
                candidate.get("name") or candidate.get("id") or ""
            ).strip()
            map_path = Path(str(self.config.get("similar_parts_template_map_file", "") or ""))
            try:
                data = json.loads(map_path.read_text(encoding="utf-8-sig"))
                mappings = data.get("mappings") if isinstance(data, dict) else None
                if isinstance(mappings, dict):
                    exact = mappings.get(candidate_name)
                    if exact is None:
                        folded = candidate_name.casefold()
                        matching = sorted(
                            (
                                (str(key), value)
                                for key, value in mappings.items()
                                if str(key).casefold() == folded
                            ),
                            key=lambda item: item[0].casefold(),
                        )
                        exact = matching[0][1] if matching else None
                    if isinstance(exact, dict):
                        template_name = str(exact.get("template") or "").strip()
            except (OSError, UnicodeError, ValueError, TypeError):
                pass
        if template_name and not raw_path:
            raw_path = str(
                Path(str(self.config.get("similar_parts_template_map_file", "") or "")).parent
                / template_name
            )
        if not template_name or not raw_path:
            raise SimilarPartsError(
                "TEMPLATE_FILE_MISSING",
                "零件 %s 缺少分组模板" % (candidate.get("id") or candidate.get("name") or ""),
                500,
            )
        template_root = Path(str(self.config.get("similar_parts_template_map_file", "") or "")).parent
        source = Path(raw_path).resolve()
        if not self._inside(template_root, source) or not source.is_file():
            raise SimilarPartsError(
                "TEMPLATE_FILE_MISSING",
                "零件 %s 的分组模板文件不存在" % (candidate.get("id") or candidate.get("name") or ""),
                500,
            )
        return source, template_name

    def _configured_top_k(self):
        try:
            top_k = int(self.config.get("similar_parts_top_k", 5))
        except (TypeError, ValueError):
            return 5
        return top_k if 1 <= top_k <= MAX_TOP_K else 5

    def ensure_feature_index(self):
        if not self.enabled:
            raise SimilarPartsError("FEATURE_DISABLED", "相似零件查询未启用", 503)
        try:
            state = self._index_manager.ensure()
        except FeatureVectorError as exc:
            raise SimilarPartsError(exc.code, exc.message, exc.http_status) from exc
        except Exception as exc:
            raise SimilarPartsError("FEATURE_INDEX_BUILD_FAILED", "特征索引准备失败，请重试", 503) from exc
        if state.get("state") == "failed":
            raise SimilarPartsError(
                state.get("errorCode") or "FEATURE_INDEX_BUILD_FAILED",
                state.get("message") or "特征索引准备失败，请重试",
                503,
                details=state,
            )
        return dict(state)

    def feature_index_status(self):
        if not self.enabled:
            raise SimilarPartsError("FEATURE_DISABLED", "相似零件查询未启用", 503)
        try:
            return dict(self._index_manager.status())
        except FeatureVectorError as exc:
            raise SimilarPartsError(exc.code, exc.message, exc.http_status) from exc
        except Exception as exc:
            raise SimilarPartsError("FEATURE_INDEX_BUILD_FAILED", "特征索引检查失败，请重试", 503) from exc

    def query(self, upload_id, top_k=None):
        if top_k is None:
            top_k = self._configured_top_k()
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
            raise SimilarPartsError("INVALID_TOP_K", "topK 必须是 1 到 1000 之间的整数")
        upload = self._get_upload(upload_id)
        if self.config.get("similar_parts_matching_backend", "feature_vector") != "feature_vector":
            raise SimilarPartsError("MATCHING_BACKEND_INVALID", "请将 matching_backend 配置为 feature_vector", 503)
        index_state = self.ensure_feature_index()
        if index_state.get("state") != "ready":
            raise SimilarPartsError(
                "FEATURE_INDEX_BUILDING",
                "正在准备相似件索引，请稍候",
                409,
                details=index_state,
            )
        try:
            self._matcher = self._index_manager.matcher
            candidates = self._matcher.query(upload["content"], upload["filename"], top_k)
        except FeatureVectorError as exc:
            raise SimilarPartsError(exc.code, exc.message, exc.http_status) from exc
        except Exception as exc:
            raise SimilarPartsError("QUERY_FAILED", "相似零件查询失败", 500) from exc

        expires_at = self._now() + self._ttl()
        with self._lock:
            current_step, current_root = self._find_current_step(upload["stem"])
            current_model_id = self._register_model(
                current_step, upload["stem"], expires_at, allowed_root=current_root
            )
            public_candidates = []
            private_candidates = {}
            for rank, candidate in enumerate(candidates, start=1):
                candidate_stem = Path(str(candidate.get("name") or candidate.get("id") or "")).stem
                step_path = self._find_step(candidate_stem)
                template_path, template_name = self._template_source(candidate)
                candidate_id = self._token()
                model_id = self._register_model(step_path, candidate_stem, expires_at)
                private_candidates[candidate_id] = {
                    "templatePath": template_path,
                    "templateFilename": template_name,
                    "partName": candidate_stem,
                }
                public_candidates.append({
                    "candidateId": candidate_id,
                    "id": str(candidate.get("id") or candidate_stem),
                    "name": str(candidate.get("name") or candidate_stem),
                    "rank": rank,
                    "similarity": candidate.get("similarity"),
                    "geometryClass": str(candidate.get("geometryClass") or ""),
                    "labelZh": str(candidate.get("labelZh") or ""),
                    "template": {"name": template_name},
                    "modelId": model_id,
                    "modelUrl": "/api/similar-parts/models/%s.glb" % model_id,
                })
            upload["candidates"] = private_candidates
            upload["expiresAt"] = expires_at
        return {
            "uploadId": str(upload_id),
            "geometryClass": "",
            "labelZh": "",
            "current": {
                "id": upload["stem"],
                "name": upload["filename"],
                "modelId": current_model_id,
                "modelUrl": "/api/similar-parts/models/%s.glb" % current_model_id,
            },
            "candidates": public_candidates,
        }

    def _cache_model(self, model_id, glb, metadata, expires_at):
        self._drop_cached_model(model_id)
        size = len(glb)
        max_bytes = max(1, int(self.config.get("similar_parts_model_cache_bytes", 256 * 1024 * 1024)))
        max_entries = max(1, int(self.config.get("similar_parts_model_cache_entries", 8)))
        if size > max_bytes:
            return
        self._model_cache[model_id] = {
            "glb": glb,
            "metadata": metadata,
            "size": size,
            "expiresAt": expires_at,
        }
        self._model_cache_bytes += size
        while self._model_cache and (
            len(self._model_cache) > max_entries or self._model_cache_bytes > max_bytes
        ):
            key, row = self._model_cache.popitem(last=False)
            self._model_cache_bytes -= row["size"]

    def get_model(self, model_id):
        key = str(model_id or "")
        with self._lock:
            self._purge()
            row = self._models.get(key)
            if row is None:
                raise SimilarPartsError("MODEL_NOT_FOUND", "模型不存在或已过期", 404)
            cached = self._model_cache.get(key)
            if cached and cached["expiresAt"] > self._now():
                self._model_cache.move_to_end(key)
                return bytes(cached["glb"]), dict(cached["metadata"])
            path = Path(row["path"])
            allowed_root = Path(row["root"])
            name = row["name"]
            expires_at = row["expiresAt"]
        if not self._inside(allowed_root, path) or not path.is_file():
            raise SimilarPartsError("MODEL_NOT_FOUND", "模型不存在或已过期", 404)
        if self._win7_lite_mode():
            prebuilt_path = self._find_prebuilt_model(name, path)
            try:
                glb = prebuilt_path.read_bytes()
            except OSError as exc:
                raise SimilarPartsError("PREBUILT_MODEL_MISSING", "预生成 GLB 文件无法读取", 500) from exc
            if not glb.startswith(b"glTF"):
                raise SimilarPartsError("PREBUILT_MODEL_INVALID", "预生成 GLB 文件无效", 422)
            metadata = self._read_prebuilt_metadata(prebuilt_path, name)
            with self._lock:
                self._cache_model(key, glb, metadata, expires_at)
            return glb, metadata
        self._load_tessellator()
        try:
            converted = self._tessellator(path.read_bytes(), path.name)
        except Exception as exc:
            code = getattr(exc, "code", "STEP_CONVERSION_FAILED")
            message = getattr(exc, "message", None) or str(exc) or "STEP 模型转换失败"
            raise SimilarPartsError(code, message, 422) from exc
        glb = bytes(converted.glb)
        metadata = {
            "name": name,
            "bounds": converted.bounds,
            "extents": converted.extents,
            "vertices": int(converted.vertices),
            "faces": int(converted.faces),
            "unit": converted.unit,
            "sourceUnit": converted.source_unit,
        }
        with self._lock:
            self._cache_model(key, glb, metadata, expires_at)
        return glb, metadata

    def prepare_template(self, upload_id, candidate_id, destination_dir, edited_template=None):
        upload = self._get_upload(upload_id)
        candidate = upload.get("candidates", {}).get(str(candidate_id or ""))
        if candidate is None:
            raise SimilarPartsError("CANDIDATE_NOT_FOUND", "候选零件不存在或已过期", 404)
        source = Path(candidate["templatePath"]).resolve()
        template_root = Path(str(self.config.get("similar_parts_template_map_file", "") or "")).parent
        if not self._inside(template_root, source) or not source.is_file():
            raise SimilarPartsError("TEMPLATE_FILE_MISSING", "候选零件的分组模板文件不存在", 500)
        filename = os.path.basename(str(candidate["templateFilename"]))
        if not filename or filename != str(candidate["templateFilename"]):
            raise SimilarPartsError("INVALID_TEMPLATE_NAME", "分组模板文件名无效", 500)
        source_bytes = None
        if edited_template is not None:
            if not isinstance(edited_template, dict):
                raise SimilarPartsError("INVALID_TEMPLATE", "编辑后的分组模板无效")
            edited_filename = str(edited_template.get("filename") or "").strip()
            edited_xml = edited_template.get("xml")
            if not edited_filename or os.path.basename(edited_filename) != edited_filename or Path(edited_filename).suffix.lower() != ".xml":
                raise SimilarPartsError("INVALID_TEMPLATE_NAME", "编辑后的分组模板文件名无效")
            if not isinstance(edited_xml, str) or not edited_xml.strip() or len(edited_xml.encode("utf-8")) > 5 * 1024 * 1024:
                raise SimilarPartsError("INVALID_TEMPLATE", "编辑后的分组模板内容无效")
            try:
                root = ET.fromstring(edited_xml)
            except ET.ParseError as exc:
                raise SimilarPartsError("INVALID_TEMPLATE", "编辑后的分组模板 XML 格式无效") from exc
            if root.tag != "Kmsoft":
                raise SimilarPartsError("INVALID_TEMPLATE", "编辑后的分组模板根节点必须是 Kmsoft")
            filename = edited_filename
            source_bytes = edited_xml.encode("gb2312", errors="replace")
        destination_root = Path(destination_dir).resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        target = (destination_root / filename).resolve()
        if not self._inside(destination_root, target):
            raise SimilarPartsError("INVALID_TEMPLATE_NAME", "分组模板文件名无效", 500)
        if source_bytes is None:
            shutil.copyfile(str(source), str(target))
        else:
            target.write_bytes(source_bytes)
        return {
            "candidateId": str(candidate_id),
            "partName": candidate["partName"],
            "templateFilename": filename,
            "templateName": Path(filename).stem,
        }

    def get_candidate_template(self, upload_id, candidate_id):
        upload = self._get_upload(upload_id)
        candidate = upload.get("candidates", {}).get(str(candidate_id or ""))
        if candidate is None:
            raise SimilarPartsError("CANDIDATE_NOT_FOUND", "候选零件不存在或已过期", 404)
        source = Path(candidate["templatePath"]).resolve()
        template_root = Path(str(self.config.get("similar_parts_template_map_file", "") or "")).parent.resolve()
        if not self._inside(template_root, source) or not source.is_file():
            raise SimilarPartsError("TEMPLATE_FILE_MISSING", "候选零件的分组模板文件不存在", 500)
        try:
            xml = source.read_text(encoding="gb2312")
        except UnicodeDecodeError:
            xml = source.read_text(encoding="utf-8-sig")
        return {"filename": str(candidate["templateFilename"]), "xml": xml}


__all__ = ["SimilarPartsError", "SimilarPartsService"]
