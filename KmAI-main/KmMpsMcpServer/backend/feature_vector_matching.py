# -*- coding: utf-8 -*-
"""Remote XML encoding with a persistent content cache and local cosine search."""
import hashlib
import json
import math
import socket
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


FEATURE_DIM = 256
MAX_TOP_K = 1000


class FeatureVectorError(Exception):
    def __init__(self, code, message, http_status=503):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def validate_xml(content):
    # Expat does not support GBK/GB18030 declarations on every Python build.
    # Decode legacy Chinese exports explicitly while preserving original upload bytes.
    if not isinstance(content, bytes) or not content:
        raise FeatureVectorError("NOT_KMSOFT_XML", "不是有效的开目 XML", 422)
    root = None
    for encoding in ("utf-8-sig", "gb2312", "gbk", "gb18030"):
        try:
            text = content.decode(encoding)
            if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
                break
            root = ET.fromstring(text)
            break
        except (UnicodeError, ValueError, ET.ParseError):
            continue
    if root is None or root.tag != "Kmsoft":
        raise FeatureVectorError("NOT_KMSOFT_XML", "根节点必须是 Kmsoft，且 XML 格式有效", 422)


def normalized_vector(feature):
    if (not isinstance(feature, list) or len(feature) != FEATURE_DIM or
            any(isinstance(value, bool) or not isinstance(value, (int, float))
                for value in feature)):
        raise FeatureVectorError("FEATURE_RESPONSE_INVALID", "特征服务返回的向量格式无效", 502)
    try:
        values = [float(value) for value in feature]
        if not all(math.isfinite(value) for value in values):
            raise ValueError()
        scale = max(abs(value) for value in values)
        if not scale:
            raise ValueError()
        scaled = [value / scale for value in values]
        norm = math.sqrt(math.fsum(value * value for value in scaled))
    except (OverflowError, ValueError):
        raise FeatureVectorError("FEATURE_RESPONSE_INVALID", "特征服务返回了无效或零向量", 502)
    return [value / norm for value in scaled]


class FeatureApiClient:
    def __init__(self, config):
        self.base_url = str(config.get("similar_parts_feature_api_base_url", "") or "").strip().rstrip("/")
        self.model_version = str(config.get("similar_parts_feature_model_version", "") or "").strip()
        try:
            parsed = urlsplit(self.base_url)
            valid_url = (parsed.scheme in ("http", "https") and parsed.hostname and
                         not parsed.username and not parsed.password and
                         not parsed.query and not parsed.fragment)
            parsed.port
            self.timeout = float(config.get("similar_parts_feature_api_timeout_seconds", 120))
            if not math.isfinite(self.timeout) or self.timeout <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            valid_url = False
        if not valid_url:
            raise FeatureVectorError("FEATURE_API_NOT_CONFIGURED", "请配置有效的特征服务地址与超时时间")
        if not self.model_version:
            raise FeatureVectorError("FEATURE_MODEL_VERSION_MISSING", "请配置特征模型部署版本标识")
        self.namespace = hashlib.sha256(
            json.dumps([self.base_url, self.model_version], ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        self.opener = build_opener(ProxyHandler({}))

    def extract(self, content):
        validate_xml(content)
        file_id = "kmai_" + hashlib.sha256(content).hexdigest()
        boundary = "----kmai" + uuid.uuid4().hex
        # Use an ASCII transport filename; library filenames remain local metadata.
        header = (
            '--%s\r\nContent-Disposition: form-data; name="file_id"\r\n\r\n%s\r\n'
            '--%s\r\nContent-Disposition: form-data; name="xml_file"; filename="%s.xml"\r\n'
            'Content-Type: application/xml\r\n\r\n'
        ) % (boundary, file_id, boundary, file_id)
        body = header.encode("ascii") + content + ("\r\n--%s--\r\n" % boundary).encode("ascii")
        request = Request(
            self.base_url + "/api/feature/extract", data=body, method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise ValueError()
            payload = json.loads(raw)
        except HTTPError as exc:
            exc.close()
            raise FeatureVectorError("FEATURE_API_ERROR", "特征服务提取失败，请检查服务状态和 XML 内容", 502) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise FeatureVectorError("FEATURE_API_TIMEOUT", "特征服务请求超时，请稍后重试", 504) from exc
        except (URLError, OSError) as exc:
            raise FeatureVectorError("FEATURE_API_UNAVAILABLE", "无法连接特征服务，请检查地址与网络", 503) from exc
        except (ValueError, UnicodeError) as exc:
            raise FeatureVectorError("FEATURE_RESPONSE_INVALID", "特征服务返回的 JSON 无效", 502) from exc
        if (not isinstance(payload, dict) or payload.get("file_id") != file_id or
                type(payload.get("feature_dim")) is not int or payload["feature_dim"] != FEATURE_DIM):
            raise FeatureVectorError("FEATURE_RESPONSE_INVALID", "特征服务返回的文件标识或维度无效", 502)
        return normalized_vector(payload.get("feature"))


class FeatureVectorMatcher:
    def __init__(self, config, client=None):
        self.config = dict(config)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = FeatureApiClient(self.config)
        return self._client

    @contextmanager
    def _database(self, create=False):
        value = str(self.config.get("similar_parts_feature_index_file", "") or "").strip()
        if not value:
            raise FeatureVectorError("FEATURE_INDEX_MISSING", "请配置特征索引文件，并运行建库脚本")
        path = Path(value).resolve()
        if not create and not path.is_file():
            raise FeatureVectorError("FEATURE_INDEX_MISSING", "特征索引不存在，请先运行 build_feature_index.py")
        connection = None
        try:
            if create:
                path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(path), timeout=30)
            if create:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS feature_vectors ("
                    "namespace TEXT NOT NULL, digest TEXT NOT NULL, vector TEXT NOT NULL, "
                    "PRIMARY KEY(namespace, digest))"
                )
                connection.commit()
            yield connection
        except (sqlite3.Error, OSError) as exc:
            raise FeatureVectorError("FEATURE_INDEX_INVALID", "特征索引无法读取或写入，请检查文件或重新建库", 503) from exc
        finally:
            if connection is not None:
                connection.close()

    def _library(self):
        root = Path(str(self.config.get("similar_parts_xml_library_dir", "") or "")).resolve()
        if not self.config.get("similar_parts_xml_library_dir") or not root.is_dir():
            raise FeatureVectorError("XML_LIBRARY_MISSING", "XML 零件库目录不存在", 500)
        try:
            paths = sorted(
                (path for path in root.iterdir() if path.is_file() and path.suffix.lower() == ".xml"),
                key=lambda path: (path.name.casefold(), path.name),
            )
        except OSError as exc:
            raise FeatureVectorError("XML_LIBRARY_UNREADABLE", "XML 零件库无法读取", 500) from exc
        if not paths:
            raise FeatureVectorError("XML_LIBRARY_EMPTY", "XML 零件库中没有零件", 422)
        for path in paths:
            if root != path.resolve().parent:
                raise FeatureVectorError("XML_LIBRARY_INVALID", "XML 零件库包含目录之外的文件", 500)
        return paths

    def _read_xml(self, path):
        limit = max(1, int(self.config.get("similar_parts_upload_max_bytes", 5 * 1024 * 1024)))
        try:
            with path.open("rb") as source:
                content = source.read(limit + 1)
        except OSError as exc:
            raise FeatureVectorError("XML_LIBRARY_UNREADABLE", "零件库 XML 无法读取", 500) from exc
        if len(content) > limit:
            raise FeatureVectorError("XML_TOO_LARGE", "零件库 XML 超过大小限制", 413)
        validate_xml(content)
        return content, hashlib.sha256(content).hexdigest()

    def _cached(self, connection, digest):
        row = connection.execute(
            "SELECT vector FROM feature_vectors WHERE namespace=? AND digest=?",
            (self.client.namespace, digest),
        ).fetchone()
        if row is None:
            return None
        try:
            return normalized_vector(json.loads(row[0]))
        except (ValueError, TypeError, FeatureVectorError) as exc:
            raise FeatureVectorError("FEATURE_INDEX_INVALID", "特征索引向量损坏，请检查文件或重新建库") from exc

    def _extract_and_save(self, connection, content, digest):
        feature = normalized_vector(self.client.extract(content))
        connection.execute(
            "INSERT OR REPLACE INTO feature_vectors(namespace, digest, vector) VALUES (?, ?, ?)",
            (self.client.namespace, digest, json.dumps(feature, allow_nan=False)),
        )
        # Persist each success so a failed extraction or interrupted build can resume.
        connection.commit()
        return feature

    def build(self, progress=None):
        self.client
        paths = self._library()
        report = {"total": len(paths), "extracted": 0, "cached": 0, "failed": []}
        with self._database(create=True) as connection:
            for index, path in enumerate(paths, 1):
                try:
                    content, digest = self._read_xml(path)
                    if self._cached(connection, digest) is not None:
                        report["cached"] += 1
                        status = "cached"
                    else:
                        self._extract_and_save(connection, content, digest)
                        report["extracted"] += 1
                        status = "extracted"
                except FeatureVectorError as exc:
                    if exc.code == "FEATURE_INDEX_INVALID":
                        raise
                    report["failed"].append({"name": path.name, "code": exc.code})
                    status = exc.code
                if progress:
                    progress(index, len(paths), path.name, status)
        return report

    def query(self, content, filename, top_k):
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
            raise FeatureVectorError("INVALID_TOP_K", "topK 必须是 1 到 1000 之间的整数", 400)
        validate_xml(content)
        self.client
        paths = self._library()
        current_digest = hashlib.sha256(content).hexdigest()
        with self._database() as connection:
            candidates = []
            missing = 0
            for path in paths:
                _, digest = self._read_xml(path)
                feature = self._cached(connection, digest)
                if feature is None:
                    missing += 1
                else:
                    candidates.append((path, digest, feature))
            if missing:
                raise FeatureVectorError(
                    "FEATURE_INDEX_INCOMPLETE",
                    "零件库有 %d 个 XML 尚未建立当前版本的特征索引，请运行 build_feature_index.py" % missing,
                )
            current = self._cached(connection, current_digest)
            if current is None:
                current = self._extract_and_save(connection, content, current_digest)
        ranked = []
        for path, digest, feature in candidates:
            same_content = digest == current_digest
            score = 1.0 if same_content else max(0.0, min(1.0, math.fsum(
                left * right for left, right in zip(current, feature)
            )))
            ranked.append((not same_content, -score,
                           path.name.casefold() != str(filename).casefold(),
                           path.name.casefold(), path.name, {
                               "id": path.stem, "name": path.name, "similarity": score,
                           }))
        ranked.sort(key=lambda row: row[:-1])
        return [row[-1] for row in ranked[:top_k]]
