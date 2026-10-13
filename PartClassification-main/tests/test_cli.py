import json
from pathlib import Path

from part_classification.cli import main
from tests.xml_builder import kmsoft_xml_bytes


def test_cli_prints_classify_json(tmp_path: Path, capsys):
    path = tmp_path / "part.XML"
    path.write_bytes(kmsoft_xml_bytes())
    code = main([str(path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "geometryClass" in payload
    assert "types" in payload


def test_cli_nonzero_on_bad_xml(capsys):
    code = main(["no-such-file.XML"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
