from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ERROR_NOT_KMSOFT = "NOT_KMSOFT_XML"
ERROR_MESSAGE = "根节点不是 Kmsoft，或无法按 GB2312 解析"
_ENCODINGS = ("gb2312", "gbk", "gb18030")


class KmsoftXmlError(Exception):
    def __init__(
        self,
        error: str = ERROR_NOT_KMSOFT,
        message: str = ERROR_MESSAGE,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


def _load_bytes(source: str | Path | bytes) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    try:
        return Path(source).read_bytes()
    except OSError as exc:
        raise KmsoftXmlError from exc


def _decode(raw: bytes) -> str:
    if not raw:
        raise KmsoftXmlError
    last_error: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise KmsoftXmlError from last_error


def read_kmsoft_xml(source: str | Path | bytes) -> ET.Element:
    text = _decode(_load_bytes(source))
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise KmsoftXmlError from exc
    if root.tag != "Kmsoft":
        raise KmsoftXmlError
    return root
