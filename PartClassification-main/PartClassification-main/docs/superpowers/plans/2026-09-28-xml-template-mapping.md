# 样本与模板映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 20 份 `source/XML样本/*.XML` 各自登记一份 `source/模板/*.xml` 分组模板，并提供本地 tkinter 窗口让用户自行配置、查询和导出这份映射。

**Architecture:** 新增纯逻辑模块 `template_map.py`（模板库=目录扫描，映射=单份 JSON 清单，原子写入，不解析模板内容），GUI `gui.py` 只负责取数、展示与调用，因此自动化测试全部落在 `template_map` 与 `classify` 两层。`classify()` 新增可选参数 `template_map_path`，命中映射时在返回 JSON 里增加 `template` 键。

**Tech Stack:** Python >=3.10（本机 3.14.5）、标准库 `json` / `os` / `tempfile` / `datetime` / `pathlib` / `csv` / `tkinter`（Tk 8.6 已确认可用）、pytest。**不得引入任何第三方运行时依赖。**

**Spec:** `docs/superpowers/specs/2026-09-28-xml-template-mapping-design.md`

## Global Constraints

- 运行时依赖必须保持为空：`pyproject.toml` 的 `dependencies` 不得新增任何条目，只能用标准库。
- 不解析、不校验、不生成任何 XML；模板文件只按文件名登记，绝不读取其内容。
- 所有读写路径使用 UTF-8；模板与样本文件名是中文，写入清单时必须 `ensure_ascii=False`，不得把中文转义成 `\uXXXX`。
- 清单写入必须是原子替换：临时文件 + `fsync` + `os.replace`，任何失败都不留半个清单、不留临时文件。
- 不自动创建模板目录；目录缺失按「模板库为空」处理。
- `classify` 的现有位置参数、`part-classify <xml_path>` 的命令行位置参数语义不得改变。
- 映射信息只作登记：不参与打分卡判定，不影响 `similarParts`。
- **本仓库 `AGENTS.md` §8 规定：未经用户明确要求，不执行 `commit` / `push`。** 本计划各任务的提交步骤只有在用户明确授权后才执行；未获授权时跳过该步骤，并在汇报中说明哪些改动尚未提交。
- 测试命令一律用 `py -3 -m pytest`（Windows，`python` 可能是 Store 别名）。基线：改动前仓库 56 个测试全部通过。

## Review Focus

以下是 spec 隐含、但用户很可能真实遇到、且最容易出错的输入。每一行都已在下面某个任务里配了对应的钉住测试。

1. **清单文件存在但是 0 字节** —— 合理预期是报 `MAP_FILE_CORRUPT`，而不是被当成「还没有配置过」而静默返回空清单。
2. **清单里 `"mappings": null`** —— 合理预期是同报 `MAP_FILE_CORRUPT`；一个被编辑器写坏的清单不能伪装成空清单，否则界面会显示 0 个已配置、用户会以为配置丢了。
3. **清单里单条记录没有 `note` 字段**（手写或旧版本留下的） —— 合理预期是正常读取、`note` 取空字符串；只有缺 `template` 才算损坏。
4. **模板名里带路径分隔符**（例如 `../套筒类模板.xml`） —— 合理预期是报 `TEMPLATE_NOT_FOUND` 并拒绝写入，绝不能顺着路径写到 `source/模板/` 之外。
5. **样本名与磁盘上的大小写不一致**（清单写 `a.xml`，磁盘是 `A.XML`） —— 映射按字节精确匹配，界面上该行会显示「（样本缺失）」。这是 Windows 大小写不敏感文件系统上的已知假警报，用测试钉住当前行为，不改成模糊匹配。
6. **映射存在但模板文件事后被删/改名** —— 合理预期是 `classify` 仍报出模板名、`path` 为 `null`，界面显示「（模板缺失）」，而映射本身不被自动删除。

---

## File Structure

| 文件 | 状态 | 职责 |
|---|---|---|
| `src/part_classification/template_map.py` | 新建 | 模板库扫描、清单读写、映射增删查、汇总视图、错误类型。纯逻辑，不导入 tkinter。 |
| `src/part_classification/gui.py` | 新建 | tkinter 窗口：展示、编辑、导出。只调用 `template_map`，自身不含业务规则。 |
| `src/part_classification/classify.py` | 修改 | 新增 `template_map_path` 参数与 `template` / `templateError` 输出键。 |
| `src/part_classification/cli.py` | 修改 | 新增可选参数 `--template-map`。 |
| `pyproject.toml` | 修改 | 新增 `part-classify-gui` 脚本入口。 |
| `tests/test_template_map.py` | 新建 | `template_map` 全量单测。 |
| `tests/test_classify_template.py` | 新建 | `classify` / CLI 的 `template` 字段行为。 |
| `tests/test_classify_unlocked.py` | 修改 | 修整体相等断言（新增 `template` 键导致）。 |
| `tests/test_reproducibility.py` | 修改 | 路径/字节相等断言需剔除 `template`（字节输入无文件名）。 |
| `README.md` | 修改 | 清单格式、`template` 字段、GUI 启动、CSV 导出。 |
| `AGENTS.md` | 修改 | 模板映射的边界说明。 |
| `source/模板/模板映射.json` | 运行时生成 | 清单文件，纳入版本控制；由 GUI 或 `set_mapping` 生成，不手工创建。 |

---

### Task 1: 模板库扫描与清单读写

**Files:**
- Create: `src/part_classification/template_map.py`
- Test: `tests/test_template_map.py`

**Interfaces:**
- Consumes: 无（本任务是最底层）
- Produces:
  - 常量：`MAP_VERSION: int = 1`、`MAP_FILENAME = "模板映射.json"`、`SAMPLES_DIR_RELATIVE = "source/XML样本"`、`ERROR_MAP_FILE_CORRUPT = "MAP_FILE_CORRUPT"`、`ERROR_MAP_VERSION_UNSUPPORTED = "MAP_VERSION_UNSUPPORTED"`、`ERROR_TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"`、`ERROR_SAMPLE_KEY_EMPTY = "SAMPLE_KEY_EMPTY"`、`ERROR_MAP_DIR_MISSING = "MAP_DIR_MISSING"`
  - `class TemplateMapError(Exception)`，属性 `code: str`、`message: str`
  - `default_templates_dir() -> Path`、`default_map_path() -> Path`、`default_samples_dir() -> Path`
  - `list_templates(templates_dir: str | Path | None = None) -> list[dict]`，元素为 `{"name": str, "path": str}`
  - `load_map(path: str | Path | None = None) -> dict`，形如 `{"version": 1, "samplesDir": str, "mappings": dict}`
  - `save_map(data: dict, path: str | Path | None = None) -> None`

> **说明（相对 spec 的一处补充）：** spec §4 的错误码表只有 4 个码。实现时发现「清单父目录不存在」需要明确行为，而 spec §10.6 又规定不得自动创建目录，因此新增 `MAP_DIR_MISSING` 一个码。这是本计划对 spec 的唯一增补。

- [ ] **Step 1: 写失败测试（模板库扫描与路径默认值）**

创建 `tests/test_template_map.py`：

```python
import json
from pathlib import Path

import pytest

from part_classification.similarity import default_samples_dir as similarity_samples_dir
from part_classification.template_map import (
    MAP_VERSION,
    TemplateMapError,
    default_map_path,
    default_samples_dir,
    default_templates_dir,
    list_templates,
    load_map,
    save_map,
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
    directory = tmp_path / "模板"
    directory.mkdir()
    for name in ("b.xml", "a.xml", "B.XML"):
        (directory / name).write_bytes(b"<Kmsoft/>")
    names = [row["name"] for row in list_templates(directory)]
    assert names == ["a.xml", "b.xml", "B.XML"]


def test_list_templates_returns_absolute_paths(workspace):
    rows = list_templates(workspace["templates"])
    assert all(Path(row["path"]).is_absolute() for row in rows)
    assert all(Path(row["path"]).is_file() for row in rows)


def test_list_templates_on_missing_directory_returns_empty(tmp_path):
    assert list_templates(tmp_path / "不存在") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'part_classification.template_map'`

- [ ] **Step 3: 写最小实现（模块骨架 + 扫描）**

创建 `src/part_classification/template_map.py`：

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

MAP_VERSION = 1
MAP_FILENAME = "模板映射.json"
TEMPLATES_DIR_NAME = "模板"
SAMPLES_DIR_NAME = "XML样本"
SAMPLES_DIR_RELATIVE = "source/XML样本"

ERROR_MAP_FILE_CORRUPT = "MAP_FILE_CORRUPT"
ERROR_MAP_VERSION_UNSUPPORTED = "MAP_VERSION_UNSUPPORTED"
ERROR_TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
ERROR_SAMPLE_KEY_EMPTY = "SAMPLE_KEY_EMPTY"
ERROR_MAP_DIR_MISSING = "MAP_DIR_MISSING"


class TemplateMapError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _repo_root() -> Path:
    # src/part_classification/template_map.py -> 仓库根
    return Path(__file__).resolve().parents[2]


def default_templates_dir() -> Path:
    return _repo_root() / "source" / TEMPLATES_DIR_NAME


def default_map_path() -> Path:
    return default_templates_dir() / MAP_FILENAME


def default_samples_dir() -> Path:
    return _repo_root() / "source" / SAMPLES_DIR_NAME


def list_templates(templates_dir: str | Path | None = None) -> list[dict]:
    """扫描模板库；目录不存在返回空列表，不创建目录。"""

    directory = Path(templates_dir) if templates_dir is not None else default_templates_dir()
    if not directory.is_dir():
        return []
    found = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".xml"
    ]
    found.sort(key=lambda path: path.name.casefold())
    return [{"name": path.name, "path": str(path.resolve())} for path in found]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 写失败测试（清单读写、原子写入、损坏检测）**

追加到 `tests/test_template_map.py`：

```python
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
```

- [ ] **Step 6: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: FAIL —— `ImportError: cannot import name 'load_map'`

- [ ] **Step 7: 实现 load_map / save_map**

在 `src/part_classification/template_map.py` 的 `list_templates` 之后追加：

```python
def _empty_map() -> dict:
    return {"version": MAP_VERSION, "samplesDir": SAMPLES_DIR_RELATIVE, "mappings": {}}


def _expect_object(value: object, target: Path, field: str) -> dict:
    if not isinstance(value, dict):
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT,
            f"清单字段 {field} 不是对象：{target}",
        )
    return value


def load_map(path: str | Path | None = None) -> dict:
    """读取清单。文件不存在返回空清单；损坏或版本不支持抛 TemplateMapError。"""

    target = Path(path) if path is not None else default_map_path()
    if not target.is_file():
        return _empty_map()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"清单无法读取：{target}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"清单不是合法 JSON：{target}") from exc

    data = _expect_object(data, target, "根")
    if data.get("version") != MAP_VERSION:
        raise TemplateMapError(
            ERROR_MAP_VERSION_UNSUPPORTED,
            f"清单版本不受支持（期望 {MAP_VERSION}）：{target}",
        )
    mappings = _expect_object(data.get("mappings"), target, "mappings")

    normalised: dict[str, dict] = {}
    for sample, entry in mappings.items():
        if not isinstance(sample, str) or not sample:
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本键无效：{sample!r}")
        if not isinstance(entry, dict):
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的记录不是对象")
        template = entry.get("template")
        if not isinstance(template, str) or not template:
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 缺少 template 字段")
        note = entry.get("note", "")
        if not isinstance(note, str):
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的 note 不是字符串")
        updated_at = entry.get("updatedAt", "")
        if not isinstance(updated_at, str):
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的 updatedAt 不是字符串")
        normalised[sample] = {
            "template": template,
            "note": note,
            "updatedAt": updated_at,
        }

    samples_dir = data.get("samplesDir")
    if not isinstance(samples_dir, str):
        samples_dir = SAMPLES_DIR_RELATIVE
    return {"version": MAP_VERSION, "samplesDir": samples_dir, "mappings": normalised}


def save_map(data: dict, path: str | Path | None = None) -> None:
    """原子写入清单：临时文件 + fsync + os.replace；不创建父目录。"""

    target = Path(path) if path is not None else default_map_path()
    mappings = data.get("mappings") or {}
    payload = {
        "version": MAP_VERSION,
        "samplesDir": data.get("samplesDir") or SAMPLES_DIR_RELATIVE,
        "mappings": {
            key: {
                "template": entry["template"],
                "note": entry.get("note", ""),
                "updatedAt": entry.get("updatedAt", ""),
            }
            for key, entry in sorted(mappings.items(), key=lambda item: item[0].casefold())
        },
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    try:
        handle_fd, temp_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=".template-map-",
            suffix=".tmp",
        )
    except OSError as exc:
        raise TemplateMapError(
            ERROR_MAP_DIR_MISSING,
            f"清单目录不存在或不可写：{target.parent}",
        ) from exc

    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
```

- [ ] **Step 8: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: PASS（全部通过，含参数化的 6 个损坏用例）

- [ ] **Step 9: 运行全量测试确认没有回归**

Run: `py -3 -m pytest -q`
Expected: PASS（原有 56 个 + 新增全部通过）

- [ ] **Step 10: 提交（仅在用户明确授权后执行）**

```bash
git add src/part_classification/template_map.py tests/test_template_map.py
git commit -m "feat: 增加模板库扫描与映射清单读写"
```

---

### Task 2: 映射增删查与汇总视图

**Files:**
- Modify: `src/part_classification/template_map.py`
- Test: `tests/test_template_map.py`

**Interfaces:**
- Consumes: Task 1 的 `load_map` / `save_map` / `list_templates` / `TemplateMapError` / 各错误码常量
- Produces:
  - `get_mapping(sample: str, path: str | Path | None = None) -> dict | None`
  - `set_mapping(sample: str, template: str, note: str = "", path: str | Path | None = None) -> dict`
  - `remove_mapping(sample: str, path: str | Path | None = None) -> bool`
  - `list_mappings(templates_dir=None, samples_dir=None, path=None) -> list[dict]`，每行 `{"sample", "sampleExists", "template", "templateExists", "templatePath", "note", "updatedAt"}`
  - `template_for_sample(sample: str, *, templates_dir=None, map_path=None) -> dict | None`，返回 `{"name", "path", "note"}`，模板文件不在库中时 `path` 为 `None`
  - 内部：`_resolve_templates_dir(path, templates_dir=None) -> Path`（`path` 给定时取 `path.parent`，否则取默认模板目录）、`_template_names(templates_dir) -> dict[str, str]`、`_sample_names(samples_dir) -> set[str]`、`_validate_sample_key(sample) -> str`

> **说明：** `template_for_sample` 是 spec §5 需要的便利函数，spec §4 的接口表未列出；它让 `classify` 不必自己推导模板目录。行为已在 spec §7「模板缺失」一行覆盖。

- [ ] **Step 1: 写失败测试（增删查）**

追加到 `tests/test_template_map.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: FAIL —— `ImportError: cannot import name 'set_mapping'`

- [ ] **Step 3: 实现增删查**

在 `src/part_classification/template_map.py` 的 `save_map` 之后追加：

```python
def _resolve_templates_dir(
    path: str | Path | None,
    templates_dir: str | Path | None = None,
) -> Path:
    if templates_dir is not None:
        return Path(templates_dir)
    if path is not None:
        # 清单与模板库同目录；自定义清单路径时以清单所在目录为模板库。
        return Path(path).parent
    return default_templates_dir()


def _template_names(templates_dir: Path) -> dict[str, str]:
    return {row["name"]: row["path"] for row in list_templates(templates_dir)}


def _validate_sample_key(sample: str) -> str:
    # 注意：Path(".XML").suffix 是空串、stem 是 ".XML"，所以必须按 suffix 判定，
    # 不能用 stem == ""，否则「只有扩展名」的键会被放过。
    if not isinstance(sample, str) or not sample.strip():
        raise TemplateMapError(ERROR_SAMPLE_KEY_EMPTY, f"样本名无效：{sample!r}")
    path = Path(sample)
    if path.suffix == "" or not path.stem.strip("."):
        raise TemplateMapError(
            ERROR_SAMPLE_KEY_EMPTY,
            f"样本名无效（缺文件名或只有扩展名）：{sample!r}",
        )
    return sample


def get_mapping(sample: str, path: str | Path | None = None) -> dict | None:
    entry = load_map(path)["mappings"].get(sample)
    return dict(entry) if entry is not None else None


def set_mapping(
    sample: str,
    template: str,
    note: str = "",
    path: str | Path | None = None,
) -> dict:
    """登记一条映射。样本名与模板名先校验，校验失败不写盘。"""

    key = _validate_sample_key(sample)
    if template not in _template_names(_resolve_templates_dir(path)):
        raise TemplateMapError(
            ERROR_TEMPLATE_NOT_FOUND,
            f"模板不在模板库中：{template!r}",
        )
    data = load_map(path)
    entry = {
        "template": template,
        "note": note,
        "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data["mappings"][key] = entry
    save_map(data, path)
    return dict(entry)


def remove_mapping(sample: str, path: str | Path | None = None) -> bool:
    data = load_map(path)
    if sample not in data["mappings"]:
        return False
    del data["mappings"][sample]
    save_map(data, path)
    return True


def template_for_sample(
    sample: str,
    *,
    templates_dir: str | Path | None = None,
    map_path: str | Path | None = None,
) -> dict | None:
    """给 classify 用：返回 {"name", "path", "note"}；未配置返回 None。

    映射存在但模板文件已缺失时 path 为 None，映射本身不被清除。
    """

    entry = get_mapping(sample, map_path)
    if entry is None:
        return None
    names = _template_names(_resolve_templates_dir(map_path, templates_dir))
    return {
        "name": entry["template"],
        "path": names.get(entry["template"]),
        "note": entry["note"],
    }
```

把文件顶部的 `from datetime import datetime` 补进 import 区（放在 `import tempfile` 之后）：

```python
from datetime import datetime
```

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: PASS

- [ ] **Step 5: 写失败测试（汇总视图与模板查找）**

追加到 `tests/test_template_map.py`：

```python
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
```

同时在文件顶部的 import 中补上 `get_mapping, list_mappings, remove_mapping, set_mapping, template_for_sample`。

- [ ] **Step 6: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: FAIL —— `ImportError: cannot import name 'list_mappings'`

- [ ] **Step 7: 实现汇总视图**

在 `src/part_classification/template_map.py` 的 `template_for_sample` 之后追加：

```python
def _sample_names(samples_dir: Path) -> set[str]:
    if not samples_dir.is_dir():
        return set()
    return {
        path.name
        for path in samples_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".xml"
    }


def list_mappings(
    templates_dir: str | Path | None = None,
    samples_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> list[dict]:
    """汇总视图：已配置行按样本名升序在前，未配置行在后。"""

    data = load_map(path)
    templates = _template_names(_resolve_templates_dir(path, templates_dir))
    directory = Path(samples_dir) if samples_dir is not None else default_samples_dir()
    present = _sample_names(directory)
    mappings = data["mappings"]

    rows: list[dict] = []
    for sample in set(mappings) | present:
        entry = mappings.get(sample)
        template_name = entry["template"] if entry is not None else None
        rows.append(
            {
                "sample": sample,
                "sampleExists": sample in present,
                "template": template_name,
                "templateExists": template_name in templates if template_name else False,
                "templatePath": templates.get(template_name) if template_name else None,
                "note": entry["note"] if entry is not None else "",
                "updatedAt": entry["updatedAt"] if entry is not None else "",
            }
        )
    rows.sort(key=lambda row: (row["template"] is None, row["sample"].casefold()))
    return rows
```

并把文件末尾的 `__all__` 补全（若无则在文件末尾新增）：

```python
__all__ = [
    "MAP_FILENAME",
    "MAP_VERSION",
    "SAMPLES_DIR_RELATIVE",
    "TemplateMapError",
    "default_map_path",
    "default_samples_dir",
    "default_templates_dir",
    "get_mapping",
    "list_mappings",
    "list_templates",
    "load_map",
    "remove_mapping",
    "save_map",
    "set_mapping",
    "template_for_sample",
]
```

- [ ] **Step 8: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_template_map.py -v`
Expected: PASS（全部通过）

- [ ] **Step 9: 运行全量测试确认没有回归**

Run: `py -3 -m pytest -q`
Expected: PASS

- [ ] **Step 10: 提交（仅在用户明确授权后执行）**

```bash
git add src/part_classification/template_map.py tests/test_template_map.py
git commit -m "feat: 增加样本模板映射的增删查与汇总视图"
```

---

### Task 3: `classify` 输出模板字段与 CLI 参数

**Files:**
- Modify: `src/part_classification/classify.py`
- Modify: `src/part_classification/cli.py`
- Modify: `tests/test_classify_unlocked.py:22-29`
- Modify: `tests/test_reproducibility.py:58-81`
- Test: `tests/test_classify_template.py`

**Interfaces:**
- Consumes: Task 2 的 `template_for_sample(sample, *, templates_dir=None, map_path=None)`、`TemplateMapError`
- Produces: `classify(source, *, scorecard=None, scorecard_path=None, similar_top_k=3, samples_dir=None, template_map_path=None) -> dict`，成功时额外含 `"template": {"name": str, "path": str | None, "note": str} | None`，清单损坏时额外含 `"templateError": "<code>"`；CLI 新增 `--template-map`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_classify_template.py`：

```python
import json

import pytest

from part_classification import classify
from part_classification.cli import main
from part_classification.scorecard import parse_scorecard
from part_classification.template_map import set_mapping
from tests.xml_builder import kmsoft_xml_bytes

UNLOCKED_CARD = parse_scorecard(
    {
        "id": "v0-unlocked",
        "locked": False,
        "classes": [
            {"id": "sleeve", "labelZh": "活门衬套", "factors": {}},
            {"id": "spool", "labelZh": "活门", "factors": {}},
        ],
        "gates": {
            "min_valid_factors": None,
            "min_top_score": None,
            "min_score_gap": None,
        },
    }
)


@pytest.fixture
def mapped(tmp_path):
    """一份样本 XML + 同目录模板库 + 已写好一条映射的清单。"""

    templates = tmp_path / "模板"
    templates.mkdir()
    template = templates / "套筒类模板.xml"
    template.write_bytes(b"<Kmsoft/>")
    sample = tmp_path / "JRT145-13-02计量活门衬套1.XML"
    sample.write_bytes(kmsoft_xml_bytes())
    map_path = templates / "模板映射.json"
    set_mapping(sample.name, "套筒类模板.xml", "配置备注", map_path)
    return {"sample": sample, "map": map_path, "template": template, "templates": templates}


def test_classify_reports_configured_template(mapped):
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["ok"] is True
    assert result["template"] == {
        "name": "套筒类模板.xml",
        "path": str(mapped["template"].resolve()),
        "note": "配置备注",
    }


def test_classify_reports_null_template_when_sample_has_no_mapping(mapped, tmp_path):
    other = tmp_path / "未配置.XML"
    other.write_bytes(kmsoft_xml_bytes())
    result = classify(other, template_map_path=mapped["map"])
    assert result["template"] is None
    assert "templateError" not in result


def test_classify_bytes_input_has_null_template(mapped):
    result = classify(kmsoft_xml_bytes(), template_map_path=mapped["map"])
    assert result["template"] is None


def test_classify_reports_template_with_null_path_when_file_deleted(mapped):
    mapped["template"].unlink()
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["template"]["name"] == "套筒类模板.xml"
    assert result["template"]["path"] is None


def test_unlocked_scorecard_still_reports_template(mapped):
    result = classify(
        mapped["sample"],
        scorecard=UNLOCKED_CARD,
        template_map_path=mapped["map"],
    )
    assert result["types"] == []
    assert result["template"]["name"] == "套筒类模板.xml"


def test_corrupt_map_does_not_fail_classification(mapped):
    mapped["map"].write_text("{ broken", encoding="utf-8")
    result = classify(mapped["sample"], template_map_path=mapped["map"])
    assert result["ok"] is True
    assert result["template"] is None
    assert result["templateError"] == "MAP_FILE_CORRUPT"
    assert result["geometryClass"] in {"sleeve", "spool", "unknown"}


def test_read_failure_has_no_template_key(mapped):
    result = classify(b"", template_map_path=mapped["map"])
    assert result["ok"] is False
    assert "template" not in result


def test_cli_accepts_template_map_and_prints_template(mapped, capsys):
    code = main([str(mapped["sample"]), "--template-map", str(mapped["map"])])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["template"]["name"] == "套筒类模板.xml"


def test_cli_default_map_missing_file_is_not_an_error(tmp_path, capsys):
    sample = tmp_path / "X.XML"
    sample.write_bytes(kmsoft_xml_bytes())
    empty_map = tmp_path / "空映射.json"
    code = main([str(sample), "--template-map", str(empty_map)])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["template"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3 -m pytest tests/test_classify_template.py -v`
Expected: FAIL —— `TypeError: classify() got an unexpected keyword argument 'template_map_path'`

- [ ] **Step 3: 实现 classify 的模板查询**

修改 `src/part_classification/classify.py`：在 import 区加入

```python
from part_classification.template_map import TemplateMapError, template_for_sample
```

在 `classify` 之前加入辅助函数：

```python
def _lookup_template(
    source: str | Path | bytes,
    template_map_path: str | Path | None,
) -> tuple[dict | None, str | None]:
    """返回 (模板信息, 错误码)。bytes 输入没有文件名，模板为 None。"""

    if isinstance(source, (bytes, bytearray)):
        return None, None
    try:
        info = template_for_sample(Path(source).name, map_path=template_map_path)
    except TemplateMapError as exc:
        # 一个坏配置文件不应让分类整体失败。
        return None, exc.code
    return info, None
```

把 `classify` 整体替换为：

```python
def classify(
    source: str | Path | bytes,
    *,
    scorecard: Scorecard | None = None,
    scorecard_path: str | Path | None = None,
    similar_top_k: int = 3,
    samples_dir: str | Path | None = None,
    template_map_path: str | Path | None = None,
) -> dict:
    try:
        root = read_kmsoft_xml(source)
    except KmsoftXmlError as exc:
        return {
            "ok": False,
            "error": exc.error,
            "message": exc.message,
        }

    template_info, template_error = _lookup_template(source, template_map_path)

    card = scorecard if scorecard is not None else load_scorecard(scorecard_path)
    fingerprint = extract_fingerprint(root)
    if not card.locked:
        result = {
            "ok": True,
            "geometryClass": "unknown",
            "labelZh": LABEL_ZH["unknown"],
            "types": [],
        }
    else:
        results = score_fingerprint(fingerprint, card)
        geometry = decide_geometry_class(results, card, fingerprint)
        result = {
            "ok": True,
            "geometryClass": geometry,
            "labelZh": LABEL_ZH.get(geometry, geometry),
            "types": [
                {
                    "id": row.id,
                    "labelZh": row.label_zh,
                    "possibility": row.possibility,
                    "score": row.score,
                    "reasons": list(row.reasons),
                }
                for row in results
            ],
        }
        result["similarParts"] = find_similar_samples(
            fingerprint,
            scorecard=card,
            samples_dir=samples_dir,
            top_k=similar_top_k,
        )

    result["template"] = template_info
    if template_error is not None:
        result["templateError"] = template_error
    return result
```

- [ ] **Step 4: 实现 CLI 参数**

修改 `src/part_classification/cli.py`：在 `--samples-dir` 之后加入

```python
    parser.add_argument(
        "--template-map",
        help="样本模板映射清单路径；默认使用 source/模板/模板映射.json",
    )
```

并把调用改为

```python
    result = classify(
        args.xml_path,
        scorecard_path=args.scorecard,
        similar_top_k=args.similar_top_k,
        samples_dir=args.samples_dir,
        template_map_path=args.template_map,
    )
```

- [ ] **Step 5: 修整体相等断言（unlocked）**

修改 `tests/test_classify_unlocked.py`：把第 24-29 行的期望值改为（新增 `template` 键）

```python
    assert result == {
        "ok": True,
        "geometryClass": "unknown",
        "labelZh": "未定",
        "types": [],
        "template": None,
    }
```

- [ ] **Step 6: 修可复现性测试的路径/字节相等断言**

修改 `tests/test_reproducibility.py`：`template` 依赖文件名而 `bytes` 没有文件名，所以「路径输入 == `字节` 输入」不再对 `template` 成立。在文件顶部加一个剔除该键的辅助函数：

```python
def _without_template(payload: dict) -> dict:
    """template 依赖输入文件名，bytes 输入恒为 None；比较打分结果时剔除它。"""

    return {k: v for k, v in payload.items() if k not in {"template", "templateError"}}
```

并把三处相等断言改为（第 61、69 行，以及第 78 行）：

```python
    assert _without_template(a) == _without_template(b)
```

```python
    assert _without_template(first) == _without_template(second)
```

```python
        assert _without_template(first) == _without_template(second)
```

同时在 `tests/test_reproducibility.py` 末尾追加一个测试，钉住字节输入的行为：

```python
def test_bytes_input_never_reports_a_template():
    result = classify(SLEEVE_XML.read_bytes())
    assert result["template"] is None
    assert "templateError" not in result
```

- [ ] **Step 7: 运行测试确认通过**

Run: `py -3 -m pytest tests/test_classify_template.py tests/test_classify_unlocked.py tests/test_reproducibility.py -v`
Expected: PASS

- [ ] **Step 8: 运行全量测试确认没有回归**

Run: `py -3 -m pytest -q`
Expected: PASS（56 个原有测试 + Task 1/2/3 新增全部通过）

- [ ] **Step 9: 提交（仅在用户明确授权后执行）**

```bash
git add src/part_classification/classify.py src/part_classification/cli.py tests/test_classify_template.py tests/test_classify_unlocked.py tests/test_reproducibility.py
git commit -m "feat: classify 输出样本对应的模板信息"
```

---

### Task 4: tkinter 配置界面

**Files:**
- Create: `src/part_classification/gui.py`
- Modify: `pyproject.toml:15-16`
- Test: 无自动化测试（spec §8 已确认：GUI 需显示器，只保证可导入且不产生副作用，行为靠人工确认）

**Interfaces:**
- Consumes: Task 2 的 `list_mappings` / `list_templates` / `set_mapping` / `remove_mapping` / `TemplateMapError` / `default_*` 路径函数
- Produces: `main(argv: list[str] | None = None) -> int`；控制台脚本 `part-classify-gui`

- [ ] **Step 1: 确认 tkinter 可用**

Run: `py -3 -c "import tkinter; print(tkinter.TkVersion)"`
Expected: 打印 `8.6`（已在本机确认）；若失败则说明该 Python 缺少 Tk，必须先解决环境才能继续。

- [ ] **Step 2: 写实现**

创建 `src/part_classification/gui.py`：

```python
from __future__ import annotations

import csv
import sys

from part_classification.template_map import (
    TemplateMapError,
    default_map_path,
    default_samples_dir,
    default_templates_dir,
    list_mappings,
    list_templates,
    remove_mapping,
    set_mapping,
)

UNSPECIFIED = "（未指定）"
MISSING_TEMPLATE = "（模板缺失）"
MISSING_SAMPLE = "（样本缺失）"


class TemplateMapWindow:
    """样本 → 模板映射的配置窗口。业务规则全部来自 template_map。"""

    def __init__(self, root, *, tk, ttk, filedialog, messagebox) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.rows: list[dict] = []
        root.title("样本 → 模板映射配置")
        root.minsize(720, 420)
        self._build()
        self.refresh()

    def _build(self) -> None:
        tk, ttk = self.tk, self.ttk

        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        self.path_text = tk.StringVar()
        ttk.Label(top, textvariable=self.path_text, justify="left").pack(side="left", anchor="w")
        buttons = ttk.Frame(top)
        buttons.pack(side="right", anchor="n")
        ttk.Button(buttons, text="重新扫描", command=self.refresh).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="导出清单…", command=self.export_csv).pack(side="left")

        middle = ttk.Frame(self.root, padding=(8, 0))
        middle.pack(fill="both", expand=True)

        left = ttk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(
            left,
            columns=("sample", "template"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("sample", text="样本文件")
        self.tree.heading("template", text="模板文件")
        self.tree.column("sample", width=280, anchor="w")
        self.tree.column("template", width=220, anchor="w")
        self.tree.tag_configure("missing", foreground="#c00000")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.LabelFrame(middle, text="所选样本", padding=8)
        right.pack(side="left", fill="y", padx=(8, 0))
        ttk.Label(right, text="模板").grid(row=0, column=0, sticky="w")
        self.template_var = tk.StringVar()
        self.template_box = ttk.Combobox(
            right,
            textvariable=self.template_var,
            state="readonly",
            width=30,
        )
        self.template_box.grid(row=1, column=0, sticky="we", pady=(0, 8))
        ttk.Label(right, text="备注").grid(row=2, column=0, sticky="w")
        self.note_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.note_var, width=32).grid(
            row=3, column=0, sticky="we", pady=(0, 8)
        )
        ttk.Button(right, text="保存", command=self.save).grid(row=4, column=0, sticky="we")

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 6), anchor="w").pack(fill="x")

    def refresh(self) -> None:
        self.path_text.set(
            f"样本目录：{default_samples_dir()}\n"
            f"模板目录：{default_templates_dir()}\n"
            f"清单文件：{default_map_path()}"
        )
        try:
            self.rows = list_mappings()
            templates = list_templates()
        except TemplateMapError as exc:
            self.rows = []
            templates = []
            self.messagebox.showerror("清单无法读取", f"{exc.code}\n{exc.message}")

        configured = sum(1 for row in self.rows if row["template"])
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            label = row["template"] or UNSPECIFIED
            tags: tuple[str, ...] = ()
            if not row["sampleExists"]:
                label, tags = MISSING_SAMPLE, ("missing",)
            elif row["template"] and not row["templateExists"]:
                label, tags = MISSING_TEMPLATE, ("missing",)
            self.tree.insert("", "end", iid=str(index), values=(row["sample"], label), tags=tags)

        self.template_box["values"] = [UNSPECIFIED] + [item["name"] for item in templates]
        self.template_var.set(UNSPECIFIED)
        self.note_var.set("")
        self.status_var.set(f"样本 {len(self.rows)} 个，已配置 {configured} 个")

    def _selected_row(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.rows[int(selection[0])]

    def _on_select(self, _event=None) -> None:
        row = self._selected_row()
        if row is None:
            return
        self.template_var.set(row["template"] or UNSPECIFIED)
        self.note_var.set(row["note"])

    def save(self) -> None:
        row = self._selected_row()
        if row is None:
            self.status_var.set("请先在左侧选择一个样本")
            return
        chosen = self.template_var.get()
        try:
            if chosen == UNSPECIFIED:
                remove_mapping(row["sample"])
            else:
                set_mapping(row["sample"], chosen, self.note_var.get())
        except TemplateMapError as exc:
            self.messagebox.showerror("保存失败", f"{exc.code}\n{exc.message}")
            return
        sample = row["sample"]
        self.refresh()
        self.status_var.set(f"已保存：{sample} → {chosen}")

    def export_csv(self) -> None:
        target = self.filedialog.asksaveasfilename(
            title="导出映射清单",
            defaultextension=".csv",
            initialfile="样本模板映射.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["样本文件", "模板文件", "模板是否存在", "备注", "更新时间"])
                for row in self.rows:
                    writer.writerow(
                        [
                            row["sample"],
                            row["template"] or "",
                            "是" if row["templateExists"] else "否",
                            row["note"],
                            row["updatedAt"],
                        ]
                    )
        except OSError as exc:
            self.messagebox.showerror("导出失败", str(exc))
            return
        self.status_var.set(f"已导出 {len(self.rows)} 行到 {target}")


def main(argv: list[str] | None = None) -> int:
    # tkinter 在无显示器或未安装 Tk 的机器上不可用，给出明确提示而不是裸回溯。
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        print(f"无法启动界面：当前 Python 缺少 tkinter（{exc}）", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法启动界面：没有可用的图形显示（{exc}）", file=sys.stderr)
        return 1
    TemplateMapWindow(
        root,
        tk=tk,
        ttk=ttk,
        filedialog=filedialog,
        messagebox=messagebox,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 加控制台入口**

修改 `pyproject.toml`，把 `[project.scripts]` 改为：

```toml
[project.scripts]
part-classify = "part_classification.cli:main"
part-classify-gui = "part_classification.gui:main"
```

重新安装以注册入口：

Run: `py -3 -m pip install -e .`

- [ ] **Step 4: 验证模块可导入且无副作用**

Run: `py -3 -c "import part_classification.gui as g; print(callable(g.main))"`
Expected: 打印 `True`，且**不弹出任何窗口**（tkinter 是延迟导入的）。若弹出窗口说明 tkinter 被提到了模块顶层，必须改回延迟导入。

- [ ] **Step 5: 验证无显示器时的行为**

Run: `py -3 -c "import part_classification.gui as g; raise SystemExit(g.main())"` （在无图形会话下）
Expected: 有显示器的机器上会正常打开窗口，用 `关闭窗口` 结束并返回 0；无显示器时应打印「无法启动界面：…」并返回 1。两种结果都算通过，关键是**不出现裸回溯**。

- [ ] **Step 6: 人工验收界面**

Run: `py -3 -m part_classification.gui`

逐条确认：

1. 左侧列出 `source/XML样本/` 的 20 个样本，状态栏显示「样本 20 个，已配置 0 个」。
2. 选中一个样本，右侧下拉出现「（未指定）」+「套筒类模板.xml」，选模板、填备注、点保存，状态栏显示「已保存」且左侧该行立即变成模板名。
3. 关掉窗口再打开，配置仍在（已落盘）。
4. 用「（未指定）」保存一次，该行退回「（未指定）」。
5. 把 `source/模板/套筒类模板.xml` 临时改名，点「重新扫描」，该行变红并显示「（模板缺失）」；改回名字后重新扫描恢复。
6. 点「导出清单…」，用 Excel 打开导出的 CSV，中文不乱码。
7. 确认仓库里生成的是 `source/模板/模板映射.json`，用记事本打开是 UTF-8 中文原文，不是 `\uXXXX`。

- [ ] **Step 7: 运行全量测试确认没有回归**

Run: `py -3 -m pytest -q`
Expected: PASS

- [ ] **Step 8: 提交（仅在用户明确授权后执行）**

```bash
git add src/part_classification/gui.py pyproject.toml
git commit -m "feat: 增加样本模板映射的桌面配置界面"
```

---

### Task 5: 文档与清单入库

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: 无自动化测试；回读并检查结构、命令与描述是否与实际行为一致

**Interfaces:**
- Consumes: Task 1-4 全部产物
- Produces: 无代码接口

- [ ] **Step 1: 更新 README**

在 `README.md` 的「## 调用」一节之前插入新一节：

````markdown
## 样本与模板映射

`source/XML样本/` 下的样本可以各自登记一份 `source/模板/` 里的开目分组模板。本期只做**登记与查询**：不解析模板内容、不校验结构、不生成新 XML。

模板库 = 目录扫描：`source/模板/*.xml`，只按文件名登记，模板是否规范由开目负责。

映射清单 = `source/模板/模板映射.json`（UTF-8）：

```json
{
  "version": 1,
  "samplesDir": "source/XML样本",
  "mappings": {
    "JRT145-13-02计量活门衬套1.XML": {
      "template": "套筒类模板.xml",
      "note": "",
      "updatedAt": "2026-09-28T10:54:56"
    }
  }
}
```

界面配置（本地 tkinter 窗口，不起服务、不联网）：

```text
py -3 -m part_classification.gui
```

或安装后使用控制台入口 `part-classify-gui`。窗口左侧列出样本与当前模板，右侧选择模板并保存；「导出清单…」可导出 UTF-8 BOM 的 CSV。

`classify` 命中映射时会在结果里多一个 `template` 键，未配置为 `null`：

```json
"template": {"name": "套筒类模板.xml", "path": "<绝对路径>", "note": ""}
```

映射存在但模板文件已被删除/改名时，`name` 仍在、`path` 为 `null`，映射不会被自动清除。清单损坏时分类仍照常返回，只是 `template` 为 `null` 并多一个 `templateError` 字段（如 `MAP_FILE_CORRUPT`）。输入是 `bytes` 时没有文件名，`template` 恒为 `null`。

CLI 对应参数为 `--template-map <清单路径>`。`template` 只是登记信息，不是几何真值，不参与打分卡判定，也不影响 `similarParts`。
````

- [ ] **Step 2: 更新 AGENTS.md**

在 `AGENTS.md` 的「## 仓库里有什么」代码块中，把 `source/` 部分改为（新增两行，保持原有对齐风格）：

```text
source/XML样本/         开目 XML，与 prt 同名对应
source/模板/            开目分组模板；模板映射.json 为样本→模板登记清单
source/测试样本/        输入输出抽查，不纳入学习
```

并在「## 分类原则」之后、「## 第一期类别」之前插入新一节：

```markdown
## 样本与模板映射

`source/模板/` 存放开目分组模板（如 `套筒类模板.xml`），`source/模板/模板映射.json` 记录「哪个样本用哪个模板」。界面：`py -3 -m part_classification.gui` 或 `part-classify-gui`。

边界：

1. 只登记映射，不解析模板内容、不校验模板结构、不生成或回写 XML。模板是否规范由开目负责。
2. 映射键是单个样本文件名，不做件号前缀或几何类的继承。
3. 模板库就是 `source/模板/*.xml` 的目录扫描结果；新增模板只需放入文件，重新扫描即可见。
4. 映射不参与打分卡判定，不影响 `classify` 的 `geometryClass` 与 `similarParts`；它只是登记信息，不是几何真值。
5. 映射指向的模板或样本被删除后，映射保留并标记缺失，由用户决定修改或删除。
```

- [ ] **Step 3: 生成初始清单并确认入库**

通过界面或一次性命令，为实际样本配置映射（示例：把 10 个衬套样本指向 `套筒类模板.xml`）。至少配置 1 条，让 `source/模板/模板映射.json` 真实存在：

Run: `py -3 -c "from part_classification.template_map import set_mapping; print(set_mapping('JRT145-13-02计量活门衬套1.XML', '套筒类模板.xml', ''))"`
Expected: 打印写入的记录；`source/模板/模板映射.json` 出现。

- [ ] **Step 4: 回读文档核对**

逐项核对，发现不一致就改文档：

1. README 里的命令 `py -3 -m part_classification.gui` 能启动窗口。
2. README 的清单示例字段与实际生成的 `模板映射.json` 一致（`version` / `samplesDir` / `mappings` / `template` / `note` / `updatedAt`）。
3. README 描述的 `template` / `templateError` 行为与实际运行结果一致（可跑一次 `py -3 -m part_classification source/XML样本/JRT145-13-02计量活门衬套1.XML` 对照）。
4. AGENTS.md 新节的 5 条边界与 spec §2「非目标」一致。
5. 没有把模板 XML 文件本身加入 git（本任务只加清单）。

- [ ] **Step 5: 运行全量测试确认没有回归**

Run: `py -3 -m pytest -q`
Expected: PASS

- [ ] **Step 6: 提交（仅在用户明确授权后执行）**

```bash
git add README.md AGENTS.md source/模板/模板映射.json
git commit -m "docs: 记录样本模板映射的用法与边界"
```

---

## 完成标准

1. `py -3 -m pytest -q` 全绿（原有 56 个 + 新增全部）。
2. `py -3 -m part_classification.gui` 能打开窗口，完成 Task 4 Step 6 的 7 项人工验收。
3. `py -3 -m part_classification source/XML样本/JRT145-13-02计量活门衬套1.XML` 输出的 JSON 含正确的 `template`。
4. `source/模板/模板映射.json` 是 UTF-8 中文原文，字段与 README 示例一致。
5. `pyproject.toml` 的 `dependencies` 仍为 `[]`。
6. README 与 AGENTS.md 的描述与实际行为逐条核对一致。
