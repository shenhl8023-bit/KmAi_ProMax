from pathlib import Path

import pytest

from part_classification.xml_read import (
    ERROR_MESSAGE,
    ERROR_NOT_KMSOFT,
    KmsoftXmlError,
    read_kmsoft_xml,
)
from tests.xml_builder import kmsoft_xml_bytes


def test_reads_gb2312_kmsoft_bytes():
    root = read_kmsoft_xml(kmsoft_xml_bytes())
    assert root.tag == "Kmsoft"


def test_reads_gb2312_file(tmp_path: Path):
    path = tmp_path / "part.XML"
    path.write_bytes(kmsoft_xml_bytes())
    root = read_kmsoft_xml(path)
    assert root.tag == "Kmsoft"


def test_empty_bytes_raise_not_kmsoft():
    with pytest.raises(KmsoftXmlError) as exc:
        read_kmsoft_xml(b"")
    assert exc.value.error == ERROR_NOT_KMSOFT
    assert exc.value.message == ERROR_MESSAGE


def test_undecodable_bytes_raise_not_kmsoft():
    with pytest.raises(KmsoftXmlError) as exc:
        read_kmsoft_xml(b"\xff\xfe\x00\x00not-xml")
    assert exc.value.error == ERROR_NOT_KMSOFT


def test_non_xml_raise_not_kmsoft():
    with pytest.raises(KmsoftXmlError) as exc:
        read_kmsoft_xml("this is not xml".encode("gb2312"))
    assert exc.value.error == ERROR_NOT_KMSOFT


def test_wrong_root_raise_not_kmsoft():
    with pytest.raises(KmsoftXmlError) as exc:
        read_kmsoft_xml(kmsoft_xml_bytes(root_tag="NotKmsoft"))
    assert exc.value.error == ERROR_NOT_KMSOFT
