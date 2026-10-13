import json
import os
import stat
from pathlib import Path

import pytest

import part_classification.template_map as tm
from part_classification.similarity import default_samples_dir as similarity_samples_dir
from part_classification.template_map import (
    MAP_VERSION,
    TemplateMapError,
    default_map_path,
    default_samples_dir,
    default_templates_dir,
    get_mapping,
    list_mappings,
    list_templates,
    load_map,
    remove_mapping,
    remove_mappings,
    save_map,
    set_mapping,
    set_mappings,
    template_for_sample,
)


@pytest.fixture
def workspace(tmp_path):
    """临时模板库 + 临时样本目录，彼此独立，不碰仓库真实文件。"""

    templates = tmp_path / "模板"
    samples = tmp_path / "XML样本"
    templates.mkdir()
    samples.mkdir()
    (templates / "套筒类模板.xml").write_bytes(b"<Kmsoft/>")
    (templates / "活门类模板.xml").write_bytes(b"<Kmsoft/>")
    (samples / "A.XML").write_bytes(b"<Kmsoft/>")
    (samples / "B.XML").write_bytes(b"<Kmsoft/>")
    return {
        "templates": templates,
        "samples": samples,
        "map": templates / "模板映射.json",
    }


def test_default_samples_dir_matches_similarity_module():
    assert default_samples_dir() == similarity_samples_dir()


def test_default_paths_point_into_repo_source_tree():
    assert default_templates_dir().name == "模板"
    assert default_templates_dir().parent.name == "source"
    assert default_map_path() == default_templates_dir() / "模板映射.json"


def test_list_templates_only_returns_xml_files(workspace):
    (workspace["templates"] / "说明.txt").write_text("not a template", encoding="utf-8")
    names = [row["name"] for row in list_templates(workspace["templates"])]
    assert names == ["套筒类模板.xml", "活门类模板.xml"]


def test_list_templates_sorts_by_casefolded_name(tmp_path):
    # 刻意避开只在大小写上不同的名字：NTFS 不区分大小写，b.xml 与 B.XML
    # 会是同一个文件。B.xml 与 a.xml 既能共存，又能区分 casefold 排序与
    # 朴素 sorted()（后者按 ASCII 会把 B.xml 排在 a.xml 之前）。
    directory = tmp_path / "模板"
    directory.mkdir()
    for name in ("B.xml", "a.xml"):
        (directory / name).write_bytes(b"<Kmsoft/>")
    names = [row["name"] for row in list_templates(directory)]
    assert names == ["a.xml", "B.xml"]


def test_list_templates_returns_absolute_paths(workspace):
    rows = list_templates(workspace["templates"])
    assert all(Path(row["path"]).is_absolute() for row in rows)
    assert all(Path(row["path"]).is_file() for row in rows)


def test_list_templates_on_missing_directory_returns_empty(tmp_path):
    assert list_templates(tmp_path / "不存在") == []


def test_load_map_missing_file_returns_empty_map(workspace):
    assert load_map(workspace["map"]) == {
        "version": MAP_VERSION,
        "samplesDir": "source/XML样本",
        "mappings": {},
    }


def test_save_then_load_roundtrip(workspace):
    data = {
        "version": MAP_VERSION,
        "samplesDir": "source/XML样本",
        "mappings": {
            "B.XML": {"template": "活门类模板.xml", "note": "第二", "updatedAt": "2026-09-28T10:00:00"},
            "A.XML": {"template": "套筒类模板.xml", "note": "", "updatedAt": "2026-09-28T09:00:00"},
        },
    }
    save_map(data, workspace["map"])
    assert load_map(workspace["map"]) == data


def test_save_map_sorts_keys_and_writes_utf8_without_escapes(workspace):
    data = {
        "version": MAP_VERSION,
        "samplesDir": "source/XML样本",
        "mappings": {
            "B.XML": {"template": "活门类模板.xml", "note": "", "updatedAt": ""},
            "A.XML": {"template": "套筒类模板.xml", "note": "中文备注", "updatedAt": ""},
        },
    }
    save_map(data, workspace["map"])
    text = workspace["map"].read_text(encoding="utf-8")
    assert "套筒类模板.xml" in text
    assert "\\u" not in text
    assert text.index('"A.XML"') < text.index('"B.XML"')


def test_save_map_translates_oserror_into_template_map_error(workspace):
    """清单只读时应报 MAP_FILE_UNWRITABLE，而不是漏出 PermissionError。

    只漏 OSError 的话 GUI 只捕获 TemplateMapError，用户点保存会看不到任何提示。
    """

    set_mapping("A.XML", "套筒类模板.xml", "保留", workspace["map"])
    before = workspace["map"].read_bytes()
    os.chmod(workspace["map"], stat.S_IREAD)
    try:
        with pytest.raises(TemplateMapError) as excinfo:
            set_mapping("B.XML", "套筒类模板.xml", path=workspace["map"])
        assert excinfo.value.code == "MAP_FILE_UNWRITABLE"
    finally:
        os.chmod(workspace["map"], stat.S_IWRITE | stat.S_IREAD)

    # 原清单完好，且没有残留临时文件
    assert workspace["map"].read_bytes() == before
    leftovers = [p.name for p in workspace["templates"].iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_load_map_accepts_utf8_bom(workspace):
    """记事本/PowerShell 重定向会写 BOM；BOM 仍是合法 UTF-8，不能当成损坏。"""

    workspace["map"].write_bytes(
        b"\xef\xbb\xbf" + json.dumps(
            {"version": 1, "mappings": {"A.XML": {"template": "套筒类模板.xml"}}},
            ensure_ascii=False,
        ).encode("utf-8")
    )
    assert load_map(workspace["map"])["mappings"]["A.XML"]["template"] == "套筒类模板.xml"


def test_load_map_reports_non_utf8_map_as_corrupt(workspace):
    """按 GBK 存盘的清单必须报 MAP_FILE_CORRUPT，不能漏 UnicodeDecodeError。

    本仓库 XML 一律 GB2312，用户按同样习惯存清单是很可能的；漏出
    UnicodeDecodeError（ValueError 而非 OSError）会让 GUI 打不开窗口、
    classify 直接抛异常。
    """

    workspace["map"].write_bytes(
        json.dumps(
            {"version": 1, "mappings": {"A.XML": {"template": "套筒类模板.xml"}}},
            ensure_ascii=False,
        ).encode("gbk")
    )
    with pytest.raises(TemplateMapError) as excinfo:
        load_map(workspace["map"])
    assert excinfo.value.code == "MAP_FILE_CORRUPT"


def test_set_mapping_rejects_non_string_note(workspace):
    """写路径必须和读路径一样校验，否则会写出自己都读不回的清单。"""

    with pytest.raises(TemplateMapError) as excinfo:
        set_mapping("A.XML", "套筒类模板.xml", None, workspace["map"])
    assert excinfo.value.code == "MAP_FILE_CORRUPT"
    assert not workspace["map"].exists()


def test_save_map_result_is_always_loadable(workspace):
    """save_map 写出的清单必须能被 load_map 读回（读写不变量一致）。"""

    save_map(
        {
            "version": MAP_VERSION,
            "samplesDir": "source/XML样本",
            "mappings": {"A.XML": {"template": "套筒类模板.xml", "note": "", "updatedAt": ""}},
        },
        workspace["map"],
    )
    assert load_map(workspace["map"])["mappings"]["A.XML"]["note"] == ""


@pytest.mark.parametrize(
    "bad_mappings",
    ["x", [], 5],
)
def test_save_map_rejects_non_mapping_container(workspace, bad_mappings):
    """容器类型不对时要报 TemplateMapError，不能漏 AttributeError/TypeError。"""

    with pytest.raises(TemplateMapError) as excinfo:
        save_map({"version": MAP_VERSION, "mappings": bad_mappings}, workspace["map"])
    assert excinfo.value.code == "MAP_FILE_CORRUPT"


def test_list_mappings_order_is_stable_when_casefold_ties(workspace):
    """仅大小写不同的键会造成 casefold 并列，顺序必须确定（不能随哈希种子变）。

    list_mappings 遍历 set(...)，而排序键在并列时无法区分，Python 的稳定排序
    会保留 set 的任意顺序 —— GUI 列表和 CSV 导出都吃这个顺序。
    """

    save_map(
        {
            "version": MAP_VERSION,
            "samplesDir": "source/XML样本",
            "mappings": {
                "B.XML": {"template": "套筒类模板.xml", "note": "", "updatedAt": ""},
                "b.xml": {"template": "套筒类模板.xml", "note": "", "updatedAt": ""},
                "A.XML": {"template": "套筒类模板.xml", "note": "", "updatedAt": ""},
                "a.xml": {"template": "套筒类模板.xml", "note": "", "updatedAt": ""},
            },
        },
        workspace["map"],
    )
    rows = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    # 在大小写不敏感的文件系统上重复调用也必须一致
    again = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    assert [r["sample"] for r in rows] == [r["sample"] for r in again]
    # 并列时以原始样本名（区分大小写）作为最终键，给出确定的顺序
    tied = [r["sample"] for r in rows if r["sample"].casefold() in {"a.xml", "b.xml"}]
    assert tied == ["A.XML", "a.xml", "B.XML", "b.xml"]


def test_save_map_leaves_no_temporary_file(workspace):
    save_map(
        {"version": MAP_VERSION, "samplesDir": "source/XML样本", "mappings": {}},
        workspace["map"],
    )
    leftovers = [p.name for p in workspace["templates"].iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_save_map_rejects_missing_parent_directory(tmp_path):
    with pytest.raises(TemplateMapError) as excinfo:
        save_map(
            {"version": MAP_VERSION, "samplesDir": "source/XML样本", "mappings": {}},
            tmp_path / "不存在" / "模板映射.json",
        )
    assert excinfo.value.code == "MAP_DIR_MISSING"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{ not json",
        "[]",
        '{"version": 1, "mappings": null}',
        '{"version": 1, "mappings": {"A.XML": {"note": "缺 template"}}}',
        '{"version": 1, "mappings": {"A.XML": {"template": ""}}}',
    ],
)
def test_corrupt_map_is_reported_not_silently_emptied(workspace, raw):
    workspace["map"].write_text(raw, encoding="utf-8")
    with pytest.raises(TemplateMapError) as excinfo:
        load_map(workspace["map"])
    assert excinfo.value.code == "MAP_FILE_CORRUPT"


def test_unsupported_version_is_reported(workspace):
    workspace["map"].write_text('{"version": 2, "mappings": {}}', encoding="utf-8")
    with pytest.raises(TemplateMapError) as excinfo:
        load_map(workspace["map"])
    assert excinfo.value.code == "MAP_VERSION_UNSUPPORTED"


def test_version_missing_is_unsupported_not_corrupt(workspace):
    workspace["map"].write_text('{"mappings": {}}', encoding="utf-8")
    with pytest.raises(TemplateMapError) as excinfo:
        load_map(workspace["map"])
    assert excinfo.value.code == "MAP_VERSION_UNSUPPORTED"


def test_entry_without_note_is_tolerated(workspace):
    workspace["map"].write_text(
        json.dumps(
            {"version": 1, "mappings": {"A.XML": {"template": "套筒类模板.xml"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    entry = load_map(workspace["map"])["mappings"]["A.XML"]
    assert entry == {"template": "套筒类模板.xml", "note": "", "updatedAt": ""}


def test_set_then_get_mapping_roundtrip(workspace):
    entry = set_mapping("A.XML", "套筒类模板.xml", "首件", workspace["map"])
    assert entry["template"] == "套筒类模板.xml"
    assert entry["note"] == "首件"
    assert len(entry["updatedAt"]) == 19  # YYYY-MM-DDTHH:MM:SS
    assert get_mapping("A.XML", workspace["map"]) == entry


def test_get_mapping_on_unconfigured_sample_returns_none(workspace):
    assert get_mapping("不存在.XML", workspace["map"]) is None


def test_set_mapping_overwrites_previous_entry(workspace):
    set_mapping("A.XML", "套筒类模板.xml", "旧的", workspace["map"])
    set_mapping("A.XML", "活门类模板.xml", "新的", workspace["map"])
    data = load_map(workspace["map"])
    assert list(data["mappings"]) == ["A.XML"]
    assert data["mappings"]["A.XML"]["template"] == "活门类模板.xml"
    assert data["mappings"]["A.XML"]["note"] == "新的"


def test_remove_mapping_reports_whether_row_existed(workspace):
    set_mapping("A.XML", "套筒类模板.xml", path=workspace["map"])
    assert remove_mapping("A.XML", workspace["map"]) is True
    assert remove_mapping("A.XML", workspace["map"]) is False
    assert load_map(workspace["map"])["mappings"] == {}


def test_unknown_template_is_rejected_and_file_untouched(workspace):
    set_mapping("A.XML", "套筒类模板.xml", "保留", workspace["map"])
    before = workspace["map"].read_bytes()
    with pytest.raises(TemplateMapError) as excinfo:
        set_mapping("B.XML", "不存在的模板.xml", path=workspace["map"])
    assert excinfo.value.code == "TEMPLATE_NOT_FOUND"
    assert workspace["map"].read_bytes() == before


def test_template_name_with_path_separator_is_rejected(workspace):
    (workspace["templates"].parent / "套筒类模板.xml").write_bytes(b"<Kmsoft/>")
    with pytest.raises(TemplateMapError) as excinfo:
        set_mapping("A.XML", "../套筒类模板.xml", path=workspace["map"])
    assert excinfo.value.code == "TEMPLATE_NOT_FOUND"
    assert not workspace["map"].exists()


@pytest.mark.parametrize("sample", ["", "   ", ".XML"])
def test_invalid_sample_key_is_rejected(workspace, sample):
    with pytest.raises(TemplateMapError) as excinfo:
        set_mapping(sample, "套筒类模板.xml", path=workspace["map"])
    assert excinfo.value.code == "SAMPLE_KEY_EMPTY"


def test_custom_map_path_uses_its_own_directory_as_template_library(tmp_path):
    """清单路径自定义时，模板库 = 清单所在目录（默认布局下二者同在 source/模板）。"""

    (tmp_path / "T.xml").write_bytes(b"<Kmsoft/>")
    map_path = tmp_path / "map.json"
    set_mapping("A.XML", "T.xml", path=map_path)
    assert load_map(map_path)["mappings"]["A.XML"]["template"] == "T.xml"


def test_custom_map_path_rejects_template_from_default_library(workspace, tmp_path):
    """清单搬走后，默认模板库里的模板不再算数，防止跨目录误配。"""

    map_path = tmp_path / "map.json"
    with pytest.raises(TemplateMapError) as excinfo:
        set_mapping("A.XML", "套筒类模板.xml", path=map_path)
    assert excinfo.value.code == "TEMPLATE_NOT_FOUND"
    assert not map_path.exists()


def test_list_mappings_marks_missing_sample_and_template(workspace):
    set_mapping("A.XML", "套筒类模板.xml", "在库", workspace["map"])
    set_mapping("已删除.XML", "活门类模板.xml", path=workspace["map"])
    (workspace["templates"] / "活门类模板.xml").unlink()

    rows = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    by_sample = {row["sample"]: row for row in rows}

    assert set(by_sample) == {"A.XML", "B.XML", "已删除.XML"}
    assert by_sample["A.XML"]["templateExists"] is True
    assert by_sample["A.XML"]["templatePath"] is not None
    assert by_sample["已删除.XML"]["templateExists"] is False
    assert by_sample["已删除.XML"]["templatePath"] is None
    assert by_sample["已删除.XML"]["sampleExists"] is False
    assert by_sample["B.XML"]["sampleExists"] is True
    assert by_sample["B.XML"]["template"] is None


def test_list_mappings_puts_configured_rows_first_then_sorts(workspace):
    set_mapping("B.XML", "套筒类模板.xml", path=workspace["map"])
    rows = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    assert [row["sample"] for row in rows] == ["B.XML", "A.XML"]


def test_list_mappings_on_empty_map_lists_all_samples(workspace):
    rows = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    assert [row["sample"] for row in rows] == ["A.XML", "B.XML"]
    assert all(row["template"] is None for row in rows)


def test_list_mappings_on_missing_directories_is_empty(tmp_path):
    rows = list_mappings(
        templates_dir=tmp_path / "无模板",
        samples_dir=tmp_path / "无样本",
        path=tmp_path / "无模板" / "模板映射.json",
    )
    assert rows == []


def test_sample_key_case_mismatch_is_reported_as_missing(workspace):
    """已知行为：映射按字节精确匹配，大小写不一致会显示样本缺失。"""

    set_mapping("a.xml", "套筒类模板.xml", path=workspace["map"])
    rows = list_mappings(
        templates_dir=workspace["templates"],
        samples_dir=workspace["samples"],
        path=workspace["map"],
    )
    by_sample = {row["sample"]: row for row in rows}
    assert by_sample["a.xml"]["sampleExists"] is False
    assert by_sample["A.XML"]["sampleExists"] is True


def test_template_for_sample_returns_none_when_unconfigured(workspace):
    assert template_for_sample("A.XML", map_path=workspace["map"]) is None


def test_template_for_sample_reports_null_path_for_deleted_template(workspace):
    set_mapping("A.XML", "活门类模板.xml", "备注", workspace["map"])
    (workspace["templates"] / "活门类模板.xml").unlink()
    info = template_for_sample("A.XML", map_path=workspace["map"])
    assert info == {"name": "活门类模板.xml", "path": None, "note": "备注"}


def test_template_for_sample_returns_absolute_path(workspace):
    set_mapping("A.XML", "套筒类模板.xml", path=workspace["map"])
    info = template_for_sample("A.XML", map_path=workspace["map"])
    assert Path(info["path"]).is_absolute()
    assert Path(info["path"]).name == "套筒类模板.xml"


def test_set_mappings_writes_all_samples_in_one_call(workspace):
    written = set_mappings(
        ["A.XML", "B.XML", "已删除.XML"],
        "套筒类模板.xml",
        path=workspace["map"],
    )
    assert written == ["A.XML", "B.XML", "已删除.XML"]
    data = load_map(workspace["map"])["mappings"]
    assert sorted(data) == ["A.XML", "B.XML", "已删除.XML"]
    assert all(entry["template"] == "套筒类模板.xml" for entry in data.values())


def test_set_mappings_writes_the_map_file_only_once(workspace):
    """批量必须只写一次盘：逐个 set_mapping 会重写 N 次整个清单。"""

    calls = []
    real_save = tm.save_map

    def counting_save(data, path=None):
        calls.append(path)
        return real_save(data, path)

    tm.save_map = counting_save
    try:
        set_mappings(["A.XML", "B.XML"], "套筒类模板.xml", path=workspace["map"])
    finally:
        tm.save_map = real_save

    assert len(calls) == 1, f"写盘次数应为 1，实际 {len(calls)}"


def test_set_mappings_deduplicates_and_keeps_order(workspace):
    written = set_mappings(
        ["B.XML", "A.XML", "B.XML", "A.XML"],
        "套筒类模板.xml",
        path=workspace["map"],
    )
    assert written == ["B.XML", "A.XML"]


def test_set_mappings_empty_list_does_not_create_file(workspace):
    assert set_mappings([], "套筒类模板.xml", path=workspace["map"]) == []
    assert not workspace["map"].exists()


def test_set_mappings_with_unknown_template_leaves_file_untouched(workspace):
    set_mapping("A.XML", "套筒类模板.xml", "保留", workspace["map"])
    before = workspace["map"].read_bytes()
    with pytest.raises(TemplateMapError) as excinfo:
        set_mappings(["B.XML", "C.XML"], "不存在的模板.xml", path=workspace["map"])
    assert excinfo.value.code == "TEMPLATE_NOT_FOUND"
    assert workspace["map"].read_bytes() == before


def test_set_mappings_with_one_bad_key_writes_nothing(workspace):
    """任一项校验失败就整体不写盘，不能留下写了一半的清单。"""

    set_mapping("A.XML", "套筒类模板.xml", "保留", workspace["map"])
    before = workspace["map"].read_bytes()
    with pytest.raises(TemplateMapError) as excinfo:
        set_mappings(["B.XML", "", "C.XML"], "套筒类模板.xml", path=workspace["map"])
    assert excinfo.value.code == "SAMPLE_KEY_EMPTY"
    assert workspace["map"].read_bytes() == before


def test_set_mappings_preserves_existing_notes_by_default(workspace):
    """批量默认只改模板、不动备注，避免一次抹掉多行已有备注。"""

    set_mapping("A.XML", "活门类模板.xml", "原备注", workspace["map"])
    set_mappings(["A.XML", "B.XML"], "套筒类模板.xml", path=workspace["map"])
    data = load_map(workspace["map"])["mappings"]
    assert data["A.XML"]["template"] == "套筒类模板.xml"
    assert data["A.XML"]["note"] == "原备注"
    assert data["B.XML"]["note"] == ""


def test_set_mappings_accepts_a_shared_note(workspace):
    set_mappings(["A.XML", "B.XML"], "套筒类模板.xml", "同一批", workspace["map"])
    data = load_map(workspace["map"])["mappings"]
    assert data["A.XML"]["note"] == "同一批"
    assert data["B.XML"]["note"] == "同一批"


def test_remove_mappings_removes_only_configured_samples(workspace):
    set_mapping("A.XML", "套筒类模板.xml", path=workspace["map"])
    set_mapping("B.XML", "套筒类模板.xml", path=workspace["map"])

    removed = remove_mappings(["A.XML", "B.XML", "未配置.XML"], workspace["map"])
    assert removed == ["A.XML", "B.XML"]
    assert load_map(workspace["map"])["mappings"] == {}


def test_remove_mappings_writes_the_map_file_only_once(workspace):
    set_mapping("A.XML", "套筒类模板.xml", path=workspace["map"])
    set_mapping("B.XML", "套筒类模板.xml", path=workspace["map"])

    calls = []
    real_save = tm.save_map

    def counting_save(data, path=None):
        calls.append(path)
        return real_save(data, path)

    tm.save_map = counting_save
    try:
        remove_mappings(["A.XML", "B.XML"], workspace["map"])
    finally:
        tm.save_map = real_save

    assert len(calls) == 1, f"写盘次数应为 1，实际 {len(calls)}"


def test_remove_mappings_on_empty_selection_does_not_write(workspace):
    set_mapping("A.XML", "套筒类模板.xml", path=workspace["map"])
    before = workspace["map"].read_bytes()
    assert remove_mappings([], workspace["map"]) == []
    assert workspace["map"].read_bytes() == before
