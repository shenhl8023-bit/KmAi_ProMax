# XML classify 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供 Python `classify` 入口：开目零件 XML 进，按已确认契约给出每一类的可能性、分数和原因；默认打分卡未锁定，不得对外下类别结论。

**Architecture:** 内部三层互不泄漏到公开 JSON：① GB2312 解码并校验 `<Kmsoft>`；② 抽第一期 8 个派生因子（0 有效，缺字段或分母为 0 为 invalid）；③ 套打分卡。未锁定只返回空 `types`；锁定后按区间匹配打分、归一化可能性，并由未定闸门决定 `geometryClass`。

**Tech Stack:** Python 3.10+ 标准库（`xml.etree.ElementTree`、`json`、`argparse`）；pytest；src layout。

**Spec:** `docs/superpowers/specs/2026-08-21-xml-classify-scoring-design.md`

## Global Constraints

- 输入只有零件 XML（路径或字节）。不要件号、不要 PRT、不要模板类型。
- XML 按 GB2312 / GBK 解码，不要当 UTF-8 读。
- 公开成功 JSON 字段仅：`ok`、`geometryClass`、`labelZh`、`types[]`（`id` / `labelZh` / `possibility` / `score` / `reasons`）。
- 失败：`ok: false`，`error: "NOT_KMSOFT_XML"`，不是未定。
- 打分卡未锁定：`geometryClass = unknown`，`types = []`，不得把试算分当结论。
- 打分卡锁定后闸门触发：`geometryClass = unknown`，**仍返回完整 `types`**。
- `unknown` 不进入 `types`，不占可能性。
- `possibility_i = score_i / Σ score`（Σ 为 0 则各类为 0）。
- `score = Σ(权重 × 匹配度) / Σ(本轮实际用到的权重)`；无可用权重时 `score = 0`。
- invalid 因子跳过，不当 0 分；理由可写「未采用：…」。
- 数值 0 是有效观测。
- 第一期因子仅：`hollow_ratio`、`inner_rev_ratio`、`inner_cyl_balance`、`wall_to_outer`、`slenderness`、`plane_ratio`、`inner_cyl_ratio`、`outer_cyl_ratio`。
- 默认生产打分卡必须 `locked: false`。测试可用内存中的锁定卡，不得把生产卡锁上。
- 匹配度：区间内为 1，越出按区间宽度线性降到 0（见 Task 4）。
- 指纹不写入公开 JSON，不落盘。
- 本阶段不上黑盒模型、不写 HTTP、不集成 KmAI。

## File structure

| Path | Responsibility |
|------|----------------|
| `pyproject.toml` | 包元数据、pytest `pythonpath = src` |
| `.gitignore` | `__pycache__`、pytest、egg-info、venv、`_preview_out/` |
| `src/part_classification/__init__.py` | 只导出 `classify` |
| `src/part_classification/__main__.py` | `python -m part_classification` |
| `src/part_classification/xml_read.py` | GB2312/GBK 解码 + `<Kmsoft>` 校验 |
| `src/part_classification/fingerprint.py` | 第一期因子与 invalid 规则 |
| `src/part_classification/scorecard.py` | 打分卡加载、匹配度、单类得分、未定闸门 |
| `src/part_classification/classify.py` | 公开 `classify` |
| `src/part_classification/cli.py` | 读路径、打印 UTF-8 JSON |
| `src/part_classification/data/scorecard.json` | 默认未锁定卡 |
| `tests/xml_builder.py` | 测试用 GB2312 Kmsoft 字节构造 |
| `tests/test_xml_read.py` | 解码与根节点 |
| `tests/test_fingerprint.py` | 因子公式与 invalid |
| `tests/test_classify_unlocked.py` | 未锁定不下结论 |
| `tests/test_scorecard.py` | 锁定后得分、闸门、主因子缺失 |
| `tests/test_reproducibility.py` | 同样 XML + 同样锁定卡 → 同样结果 |
| `tests/test_cli.py` | CLI 出口 |

---

### Task 1: GB2312 读取与 `<Kmsoft>` 校验

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tests/xml_builder.py`
- Create: `tests/test_xml_read.py`
- Create: `src/part_classification/__init__.py`
- Create: `src/part_classification/xml_read.py`

**Interfaces:**
- Consumes: 无
- Produces: `KmsoftXmlError(error: str, message: str)`；`read_kmsoft_xml(source: str | Path | bytes) -> xml.etree.ElementTree.Element`；常量 `ERROR_NOT_KMSOFT = "NOT_KMSOFT_XML"`，`ERROR_MESSAGE = "根节点不是 Kmsoft，或无法按 GB2312 解析"`

- [ ] **Step 1: Write the failing tests and scaffold files that tests import**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "part-classification"
version = "0.1.0"
description = "Classify KMSOFT part XML into geometry classes"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.4"]

[project.scripts]
part-classify = "part_classification.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
part_classification = ["data/*.json"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

`.gitignore`:

```
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
.venv/
venv/
dist/
build/
.superpowers/
.worktrees/
_preview_out/
```

`tests/xml_builder.py` — 构造 GB2312 字节；缺省给出可抽满 8 因子的值；传入 `None` 表示省略该 Param：

```python
from __future__ import annotations


def kmsoft_xml_bytes(
    *,
    root_tag: str = "Kmsoft",
    surface_area: float | None = 28736.699,
    inner_rev_area: float | None = 10904.024,
    plane_ratio: float | None = 0.176,
    inner_cyl_ratio: float | None = 0.377,
    outer_cyl_ratio: float | None = 0.416,
    wall_mean: float | None = 3.076,
    max_outer: float | None = 22.0,
    min_inner: float | None = 16.0,
    slenderness: float | None = 2.739,
) -> bytes:
    def param(name: str, value: float | None) -> str:
        if value is None:
            return ""
        return f'<Param name="{name}" type="Double" value="{value}"/>'

    xml = f"""<?xml version="1.0" encoding="GB2312" ?>
<{root_tag}>
  <Item type="Part_Info">
    <Params>
      {param("零件总体表面积", surface_area)}
      {param("零件总体内回转面表面积", inner_rev_area)}
    </Params>
  </Item>
  <Item type="Part_OtherInfo">
    <Item name="面分类信息">
      <Params name="平面信息">{param("平面总面积占比", plane_ratio)}</Params>
      <Params name="外圆柱信息">{param("外圆柱总面积占比", outer_cyl_ratio)}</Params>
      <Params name="内圆柱信息">{param("内圆柱总面积占比", inner_cyl_ratio)}</Params>
    </Item>
    <Item name="薄壁分类信息">
      <Params name="薄壁圆柱信息">{param("薄壁圆柱厚度均值", wall_mean)}</Params>
    </Item>
    <Item name="主回转面信息">
      <Params name="主回转面信息">
        {param("最大外径", max_outer)}
        {param("最小内径", min_inner)}
      </Params>
    </Item>
    <Item name="主惯性轴信息">
      <Params name="主惯性轴信息">{param("零件细长度", slenderness)}</Params>
    </Item>
  </Item>
</{root_tag}>
"""
    return xml.encode("gb2312")
```

`tests/test_xml_read.py`:

```python
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
```

`src/part_classification/__init__.py` 先留空字符串（Task 3 再导出 `classify`）。

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_xml_read.py -v`

Expected: FAIL — `ModuleNotFoundError: part_classification.xml_read` 或 import 失败。

- [ ] **Step 3: Write minimal implementation**

`src/part_classification/xml_read.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_xml_read.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/part_classification/__init__.py src/part_classification/xml_read.py tests/xml_builder.py tests/test_xml_read.py
git commit -m "feat: read GB2312 Kmsoft XML"
```

---

### Task 2: 第一期指纹提取与 invalid 规则

**Files:**
- Create: `src/part_classification/fingerprint.py`
- Create: `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: `read_kmsoft_xml` 返回的 `ET.Element`
- Produces:
  - `FEATURE_NAMES: tuple[str, ...]` 按上列 8 个名字、该顺序
  - `Fingerprint(values: dict[str, float | None], invalid_reasons: dict[str, str])`，`None` = invalid
  - `extract_fingerprint(root: ET.Element) -> Fingerprint`
  - `Fingerprint.get(name: str) -> float | None`

公式与 invalid（照抄 spec）：

| 内部名 | 算法 | invalid |
|--------|------|---------|
| `hollow_ratio` | 最小内径 / 最大外径 | 缺任一端，或最大外径 = 0 |
| `inner_rev_ratio` | 零件总体内回转面表面积 / 零件总体表面积 | 缺任一端，或表面积 = 0 |
| `inner_cyl_balance` | 内圆柱总面积占比 / (内圆柱总面积占比 + 外圆柱总面积占比) | 缺占比，或两者之和 = 0 |
| `wall_to_outer` | 薄壁圆柱厚度均值 / 最大外径 | 缺任一端，或最大外径 = 0 |
| `slenderness` | 零件细长度 | 缺该字段 |
| `plane_ratio` | 平面总面积占比 | 缺该字段 |
| `inner_cyl_ratio` | 内圆柱总面积占比 | 缺该字段 |
| `outer_cyl_ratio` | 外圆柱总面积占比 | 缺该字段 |

Param `name`（按文档）：`零件总体表面积`、`零件总体内回转面表面积`、`平面总面积占比`、`外圆柱总面积占比`、`内圆柱总面积占比`、`薄壁圆柱厚度均值`、`最大外径`、`最小内径`、`零件细长度`。在整棵树里按 `Param@name` 取值；值为 0 仍解析为 0.0。无法 `float()` 的值视为缺字段。

invalid 理由统一：`未采用：{name} 无效（缺字段或分母为 0）`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from part_classification.fingerprint import FEATURE_NAMES, extract_fingerprint
from part_classification.xml_read import read_kmsoft_xml
from tests.xml_builder import kmsoft_xml_bytes

REPO = Path(__file__).resolve().parents[1]
SLEEVE_XML = REPO / "source" / "XML样本" / "JRT145-13-02计量活门衬套1.XML"
SPOOL_XML = REPO / "source" / "XML样本" / "JRT145-13-01计量活门.XML"


def _fp(**kwargs):
    return extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(**kwargs)))


def test_feature_names_are_the_eight_period_one_factors():
    assert FEATURE_NAMES == (
        "hollow_ratio",
        "inner_rev_ratio",
        "inner_cyl_balance",
        "wall_to_outer",
        "slenderness",
        "plane_ratio",
        "inner_cyl_ratio",
        "outer_cyl_ratio",
    )


def test_zero_is_a_valid_observation():
    fp = _fp(plane_ratio=0.0, inner_cyl_ratio=0.0)
    assert fp.get("plane_ratio") == 0.0
    assert "plane_ratio" not in fp.invalid_reasons


def test_missing_field_is_invalid_not_zero():
    fp = _fp(slenderness=None)
    assert fp.get("slenderness") is None
    assert fp.invalid_reasons["slenderness"].startswith("未采用：slenderness")


def test_zero_denominator_is_invalid():
    fp = _fp(max_outer=0.0, min_inner=16.0, wall_mean=3.0)
    assert fp.get("hollow_ratio") is None
    assert fp.get("wall_to_outer") is None
    assert fp.get("slenderness") == 2.739


def test_inner_cyl_balance_invalid_when_both_ratios_zero():
    fp = _fp(inner_cyl_ratio=0.0, outer_cyl_ratio=0.0)
    assert fp.get("inner_cyl_balance") is None
    assert fp.get("inner_cyl_ratio") == 0.0
    assert fp.get("outer_cyl_ratio") == 0.0


def test_sleeve_sample_matches_known_ratios():
    fp = extract_fingerprint(read_kmsoft_xml(SLEEVE_XML))
    assert fp.get("hollow_ratio") == pytest.approx(16.0 / 22.0)
    assert fp.get("inner_rev_ratio") == pytest.approx(10904.024 / 28736.699)
    assert fp.get("wall_to_outer") == pytest.approx(3.076 / 22.0)


def test_spool_sample_matches_known_ratios():
    fp = extract_fingerprint(read_kmsoft_xml(SPOOL_XML))
    assert fp.get("hollow_ratio") == pytest.approx(1.0 / 16.0)
    assert fp.get("inner_rev_ratio") == pytest.approx(2044.966 / 12837.015)
    assert fp.get("wall_to_outer") == pytest.approx(9.028 / 16.0)
```

在文件顶部补 `import pytest`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_fingerprint.py -v`

Expected: FAIL — `ModuleNotFoundError: part_classification.fingerprint`

- [ ] **Step 3: Write minimal implementation**

`src/part_classification/fingerprint.py` 实现 `collect_params`（`root.iter("Param")`）、上表公式、`Fingerprint.get`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_xml_read.py tests/test_fingerprint.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/part_classification/fingerprint.py tests/test_fingerprint.py
git commit -m "feat: extract period-one XML fingerprint"
```

---

### Task 3: `classify` JSON 出口（未锁定路径）与 CLI

**Files:**
- Create: `src/part_classification/data/scorecard.json`
- Create: `src/part_classification/scorecard.py`（本任务只做加载 + `locked`；打分函数下任务再写）
- Create: `src/part_classification/classify.py`
- Create: `src/part_classification/cli.py`
- Create: `src/part_classification/__main__.py`
- Modify: `src/part_classification/__init__.py`
- Create: `tests/test_classify_unlocked.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `read_kmsoft_xml`、`extract_fingerprint`（内部可抽，不得出现在返回 JSON）
- Produces:
  - `classify(source: str | Path | bytes, *, scorecard: Scorecard | None = None, scorecard_path: str | Path | None = None) -> dict`
  - `load_scorecard(path: str | Path | None = None) -> Scorecard`；默认读包内 `data/scorecard.json`
  - `parse_scorecard(data: dict) -> Scorecard`
  - `Scorecard(id: str, locked: bool, classes: tuple[ClassSpec, ...], gates: Gates)`
  - `ClassSpec(id: str, label_zh: str, factors: dict[str, FactorSpec])`
  - `FactorSpec(role: str, weight: float, interval: tuple[float, float])`
  - `Gates(min_valid_factors: int | None, min_top_score: float | None, min_score_gap: float | None)`
  - `LABEL_ZH = {"sleeve": "活门衬套", "spool": "活门", "unknown": "未定"}`
  - CLI: `part-classify XML_PATH [--scorecard PATH]`，stdout UTF-8 JSON；`ok` 为 false 时 exit 1

默认 `data/scorecard.json`：

```json
{
  "id": "v0-unlocked",
  "locked": false,
  "classes": [
    {"id": "sleeve", "labelZh": "活门衬套", "factors": {}},
    {"id": "spool", "labelZh": "活门", "factors": {}}
  ],
  "gates": {
    "min_valid_factors": null,
    "min_top_score": null,
    "min_score_gap": null
  }
}
```

未锁定成功体：

```json
{
  "ok": true,
  "geometryClass": "unknown",
  "labelZh": "未定",
  "types": []
}
```

失败体：

```json
{
  "ok": false,
  "error": "NOT_KMSOFT_XML",
  "message": "根节点不是 Kmsoft，或无法按 GB2312 解析"
}
```

`classify` 必须先解析 XML；解析失败返回失败体，不因卡未锁定而改成未定。解析成功后即使抽了指纹，未锁定也不得填 `types`、不得出现指纹字段。

- [ ] **Step 1: Write the failing tests**

`tests/test_classify_unlocked.py`:

```python
from part_classification import classify
from tests.xml_builder import kmsoft_xml_bytes


def test_unlocked_card_returns_unknown_and_empty_types():
    result = classify(kmsoft_xml_bytes())
    assert result == {
        "ok": True,
        "geometryClass": "unknown",
        "labelZh": "未定",
        "types": [],
    }


def test_unlocked_does_not_leak_fingerprint_or_trial_scores():
    result = classify(kmsoft_xml_bytes())
    assert "fingerprint" not in result
    assert result["types"] == []


def test_parse_failure_is_error_not_unknown():
    result = classify(b"")
    assert result["ok"] is False
    assert result["error"] == "NOT_KMSOFT_XML"
    assert result["message"] == "根节点不是 Kmsoft，或无法按 GB2312 解析"
    assert "geometryClass" not in result
```

`tests/test_cli.py`:

```python
import json
from pathlib import Path

from part_classification.cli import main
from tests.xml_builder import kmsoft_xml_bytes


def test_cli_prints_unlocked_json(tmp_path: Path, capsys):
    path = tmp_path / "part.XML"
    path.write_bytes(kmsoft_xml_bytes())
    code = main([str(path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["types"] == []


def test_cli_nonzero_on_bad_xml(capsys):
    code = main(["no-such-file.XML"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_classify_unlocked.py tests/test_cli.py -v`

Expected: FAIL — cannot import `classify`

- [ ] **Step 3: Write minimal implementation**

- `scorecard.py`：数据类 + `parse_scorecard` + `load_scorecard`（本任务不要实现 `score_fingerprint` / `match_degree` / `decide_geometry_class`）
- `classify.py`：捕获 `KmsoftXmlError` → 失败 dict；卡未锁定 → 未定空 `types`
- `cli.py`：`argparse`，`json.dump(..., ensure_ascii=False, indent=2)`
- `__main__.py`：`from part_classification.cli import main; raise SystemExit(main())`
- `__init__.py`：`from part_classification.classify import classify` 且 `__all__ = ["classify"]`

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest tests -v`

Expected: PASS（尚无锁定打分测试）

- [ ] **Step 5: Commit**

```bash
git add src/part_classification tests/test_classify_unlocked.py tests/test_cli.py
git commit -m "feat: add classify JSON exit for unlocked scorecard"
```

---

### Task 4: 打分卡套用、单类得分、未定闸门

**Files:**
- Modify: `src/part_classification/scorecard.py`
- Modify: `src/part_classification/classify.py`
- Create: `tests/test_scorecard.py`

**Interfaces:**
- Consumes: `Fingerprint`、`Scorecard`（Task 2/3）
- Produces:
  - `match_degree(value: float, interval: tuple[float, float]) -> float`
  - `score_fingerprint(fp: Fingerprint, card: Scorecard) -> list[TypeResult]`
  - `decide_geometry_class(results: list[TypeResult], card: Scorecard) -> str`
  - `TypeResult(id, label_zh, possibility, score, reasons: tuple[str, ...], primary_invalid: bool, valid_used: int)`
  - 锁定后 `classify` 填充 `types` 并套闸门

**匹配度（本阶段选定的分段，写进 AGENTS 时再抄）：**

```
low, high = interval（若 low > high 则对调）
若 low <= value <= high：1.0
width = high - low
若 width == 0：0.0（点区间只在相等时已返回 1）
dist = low - value 若 value < low 否则 value - high
返回 max(0.0, 1.0 - dist / width)
```

**单类得分：** 只用「卡里有、且指纹有效」的因子。`score = Σ(w * match) / Σ w`；Σ w = 0 则 score = 0。全部类算完后 `possibility_i = score_i / Σ score`（Σ 为 0 则各类 0）。`types` 顺序与打分卡 `classes` 顺序一致。

**理由：** 与加分同源。有效因子按权重降序最多 3 条，写明中文量名、实际值（`{value:.2f}`）和期望区间：

- 匹配度 ≥ 0.5：`{中文}为 {v}，落在{类中文}期望区间 [{lo:.2f}, {hi:.2f}]`
- 匹配度 < 0.5：`{中文}为 {v}，偏离{类中文}期望区间 [{lo:.2f}, {hi:.2f}]`

中文量名：

| 因子 | 中文 |
|------|------|
| hollow_ratio | 最小内径/最大外径 |
| inner_rev_ratio | 内回转面占表面积 |
| inner_cyl_balance | 内圆柱面积占内外圆柱之和 |
| wall_to_outer | 薄壁圆柱厚度均值/最大外径 |
| slenderness | 零件细长度 |
| plane_ratio | 平面总面积占比 |
| inner_cyl_ratio | 内圆柱总面积占比 |
| outer_cyl_ratio | 外圆柱总面积占比 |

卡中因子 invalid 时追加 `Fingerprint.invalid_reasons` 原文。主因子 invalid 的「未采用」须出现在该类 `reasons` 里。无任何理由时写 `本轮无有效因子参与加分`。禁止空话。

**未定闸门（仅 `locked is True`）：** 任一则 `geometryClass = unknown`，仍返回完整 `types`：

1. 卡中出现过的因子里，指纹有效个数 < `gates.min_valid_factors`（该闸为 `null` 则关闭）
2. 任一结构类存在 `role == "primary"` 的因子且该因子 invalid
3. 最高 `score` < `gates.min_top_score`（`null` 则关闭）
4. 两类最高分之差 < `gates.min_score_gap`（不足两类或 `null` 则关闭）
5. 全部 `score` 为 0

否则 `geometryClass` 为最高 `score` 的类 `id`（并列取 `classes` 中先出现者）。`labelZh` 用 `LABEL_ZH`。

测试用锁定卡（仅测试，不写入生产 `data/scorecard.json`）：

```python
LOCKED_CARD = parse_scorecard({
    "id": "test-locked",
    "locked": True,
    "classes": [
        {
            "id": "sleeve",
            "labelZh": "活门衬套",
            "factors": {
                "hollow_ratio": {"role": "primary", "weight": 2.0, "interval": [0.5, 0.9]},
                "wall_to_outer": {"role": "secondary", "weight": 1.0, "interval": [0.05, 0.25]},
            },
        },
        {
            "id": "spool",
            "labelZh": "活门",
            "factors": {
                "hollow_ratio": {"role": "primary", "weight": 2.0, "interval": [0.0, 0.2]},
                "wall_to_outer": {"role": "secondary", "weight": 1.0, "interval": [0.4, 0.8]},
            },
        },
    ],
    "gates": {
        "min_valid_factors": 1,
        "min_top_score": 0.5,
        "min_score_gap": 0.1,
    },
})
```

- [ ] **Step 1: Write the failing tests**

```python
from part_classification.classify import classify
from part_classification.scorecard import match_degree, parse_scorecard
from tests.xml_builder import kmsoft_xml_bytes

LOCKED_CARD = parse_scorecard({...})  # 同上


def test_match_degree_inside_interval_is_one():
    assert match_degree(0.73, (0.5, 0.9)) == 1.0


def test_match_degree_falls_off_outside_interval():
    assert match_degree(0.4, (0.5, 0.9)) == 0.75
    assert match_degree(0.0, (0.5, 0.9)) == 0.0


def test_locked_sleeve_like_xml_prefers_sleeve():
    result = classify(kmsoft_xml_bytes(), scorecard=LOCKED_CARD)
    assert result["ok"] is True
    assert result["geometryClass"] == "sleeve"
    assert result["labelZh"] == "活门衬套"
    by_id = {row["id"]: row for row in result["types"]}
    assert set(by_id) == {"sleeve", "spool"}
    assert by_id["sleeve"]["score"] > by_id["spool"]["score"]
    assert by_id["sleeve"]["possibility"] + by_id["spool"]["possibility"] == pytest.approx(1.0)
    assert any("最小内径/最大外径" in line and "落在" in line for line in by_id["sleeve"]["reasons"])
    assert any("偏离" in line for line in by_id["spool"]["reasons"])


def test_invalid_factor_is_skipped_not_scored_as_zero():
    xml = kmsoft_xml_bytes(max_outer=0.0, min_inner=16.0, wall_mean=3.076)
    result = classify(xml, scorecard=LOCKED_CARD)
    assert result["geometryClass"] == "unknown"
    sleeve = next(row for row in result["types"] if row["id"] == "sleeve")
    assert any("未采用：hollow_ratio" in line for line in sleeve["reasons"])
    assert sleeve["score"] == 1.0  # 仅 wall_to_outer=3.076/22 不可用因为 max_outer=0，wait
```

**纠正：** `max_outer=0` 时 `hollow_ratio` 与 `wall_to_outer` **都** invalid。主因子 invalid → unknown；两类 score 均为 0。改测：

```python
def test_invalid_factor_is_skipped_not_scored_as_zero():
    xml = kmsoft_xml_bytes(min_inner=None)  # hollow invalid; wall_to_outer still valid
    result = classify(xml, scorecard=LOCKED_CARD)
    assert result["geometryClass"] == "unknown"  # primary invalid
    sleeve = next(row for row in result["types"] if row["id"] == "sleeve")
    assert any("未采用：hollow_ratio" in line for line in sleeve["reasons"])
    assert sleeve["score"] == 1.0  # only wall_to_outer 3.076/22 ≈ 0.14, in [0.05, 0.25]


def test_missing_primary_still_returns_types():
    xml = kmsoft_xml_bytes(min_inner=None)
    result = classify(xml, scorecard=LOCKED_CARD)
    assert result["ok"] is True
    assert result["geometryClass"] == "unknown"
    assert len(result["types"]) == 2
    assert all("possibility" in row and "score" in row and "reasons" in row for row in result["types"])


def test_low_top_score_is_unknown_with_types():
    card = parse_scorecard({
        "id": "high-bar",
        "locked": True,
        "classes": [{
            "id": "sleeve",
            "labelZh": "活门衬套",
            "factors": {
                "hollow_ratio": {"role": "secondary", "weight": 1.0, "interval": [0.01, 0.02]},
            },
        }],
        "gates": {"min_valid_factors": 1, "min_top_score": 0.9, "min_score_gap": None},
    })
    result = classify(kmsoft_xml_bytes(), scorecard=card)
    assert result["geometryClass"] == "unknown"
    assert result["types"][0]["score"] < 0.9


def test_close_scores_trigger_unknown():
    card = parse_scorecard({
        "id": "close",
        "locked": True,
        "classes": [
            {"id": "sleeve", "labelZh": "活门衬套", "factors": {
                "hollow_ratio": {"role": "secondary", "weight": 1.0, "interval": [0.0, 1.0]}
            }},
            {"id": "spool", "labelZh": "活门", "factors": {
                "hollow_ratio": {"role": "secondary", "weight": 1.0, "interval": [0.0, 1.0]}
            }},
        ],
        "gates": {"min_valid_factors": 1, "min_top_score": 0.0, "min_score_gap": 0.1},
    })
    result = classify(kmsoft_xml_bytes(), scorecard=card)
    assert result["geometryClass"] == "unknown"
    assert result["types"][0]["score"] == result["types"][1]["score"]
```

`test_invalid_factor_is_skipped_not_scored_as_zero`：默认 `wall_mean=3.076`，`max_outer=22` → `wall_to_outer ≈ 0.1398` 落在衬套 [0.05, 0.25] → match 1；活门 [0.4, 0.8] 外，dist=0.4-0.1398，width=0.4，match ≈ 0.35。sleeve score=1.0，spool score≈0.35。主因子 invalid 所以 geometryClass unknown。断言 sleeve score == 1.0。

补 `import pytest`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_scorecard.py -v`

Expected: FAIL — `match_degree` 未定义，或锁定路径仍返回空 `types`

- [ ] **Step 3: Write scoring + wire `classify` locked path**

按上面公式实现。`classify` 在 `card.locked` 为 True 时：`fp = extract_fingerprint(root)` → `score_fingerprint` → `decide_geometry_class` → 填 `types`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest tests -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/part_classification/scorecard.py src/part_classification/classify.py tests/test_scorecard.py
git commit -m "feat: score locked cards and apply unknown gates"
```

---

### Task 5: 可复现性核对与文档同步

**Files:**
- Create: `tests/test_reproducibility.py`
- Modify: `AGENTS.md`（智能体现在怎么做 / 短期：classify 已实现，默认卡未锁定）
- Modify: `docs/superpowers/specs/2026-08-21-xml-classify-scoring-design.md` 状态改为已实现（打分卡未锁定）；非目标里删「本阶段不写分类程序」；实现顺序标为已执行
- Modify: `README.md` 写清如何调用 `classify` / CLI，并写明未锁定不下结论

**Interfaces:**
- Consumes: Task 3/4 的 `classify` 与测试锁定卡（可从 `tests/test_scorecard.py` 抽 `LOCKED_CARD` 到 `tests/locked_card.py` 以免循环导入；或在本测试内再 `parse_scorecard` 一份相同 dict）
- Produces: 无新公开 API

- [ ] **Step 1: Write the failing reproducibility tests**

```python
from pathlib import Path

from part_classification.classify import classify
from part_classification.scorecard import parse_scorecard

REPO = Path(__file__).resolve().parents[1]
SLEEVE_XML = REPO / "source" / "XML样本" / "JRT145-13-02计量活门衬套1.XML"
SPOOL_XML = REPO / "source" / "XML样本" / "JRT145-13-01计量活门.XML"

LOCKED = parse_scorecard({
    "id": "test-locked",
    "locked": True,
    "classes": [
        {"id": "sleeve", "labelZh": "活门衬套", "factors": {
            "hollow_ratio": {"role": "primary", "weight": 2.0, "interval": [0.5, 0.9]},
            "wall_to_outer": {"role": "secondary", "weight": 1.0, "interval": [0.05, 0.25]},
        }},
        {"id": "spool", "labelZh": "活门", "factors": {
            "hollow_ratio": {"role": "primary", "weight": 2.0, "interval": [0.0, 0.2]},
            "wall_to_outer": {"role": "secondary", "weight": 1.0, "interval": [0.4, 0.8]},
        }},
    ],
    "gates": {"min_valid_factors": 1, "min_top_score": 0.5, "min_score_gap": 0.1},
})


def test_same_xml_same_locked_card_same_payload():
    a = classify(SLEEVE_XML, scorecard=LOCKED)
    b = classify(SLEEVE_XML.read_bytes(), scorecard=LOCKED)
    assert a == b
    assert a["ok"] is True
    assert a["types"]


def test_default_unlocked_card_does_not_conclude_real_samples():
    for path in (SLEEVE_XML, SPOOL_XML):
        result = classify(path)
        assert result["geometryClass"] == "unknown"
        assert result["types"] == []
```

- [ ] **Step 2: Run tests**

Run: `py -3 -m pytest tests/test_reproducibility.py -v`

Expected: 若 Task 4 完成则 PASS；若分类器未接锁定路径则 FAIL。不得为了让默认卡通过真实样本而把生产卡锁上。

- [ ] **Step 3: Update AGENTS.md, spec status, README**

AGENTS 必须写明：

- `classify` 已实现，输入只有 XML
- 默认打分卡 `locked: false`，现场不得把返回当成类别结论
- 匹配度曲线：区间内 1，越出按区间宽度线性降到 0
- 主次/权重/区间/闸门数字仍等 PRT 标定后写入
- 学样本流程不变：先看 `.prt`

- [ ] **Step 4: Run full suite**

Run: `py -3 -m pytest tests -v`

Expected: PASS，覆盖 spec 点名的：解码与根节点、invalid 跳过、未锁定不下结论、主因子缺失走未定、锁定后分数可复现。

- [ ] **Step 5: Commit**

```bash
git add tests/test_reproducibility.py AGENTS.md docs README.md
git commit -m "docs: record unlocked classify entry and reproducibility tests"
```

---

## Spec coverage

| Spec 要求 | Task |
|-----------|------|
| GB2312 读取与 `<Kmsoft>` 校验 | 1 |
| 失败 `NOT_KMSOFT_XML` 不是未定 | 1, 3 |
| 第一期 8 因子与 invalid（0 有效） | 2 |
| `classify` JSON 未锁定空 `types` | 3 |
| CLI / Python 入口 | 3 |
| 打分卡加载、锁定标志 | 3 |
| 匹配度、单类得分、possibility 归一化 | 4 |
| 理由与加分同源 | 4 |
| 主因子 invalid / 有效因子过少 / 最高分过低 / 分差过小 → unknown 仍给 types | 4 |
| 默认卡未锁定、测试卡可锁定 | 3, 4, 5 |
| 同一 XML + 同一锁定卡可复现 | 5 |
| 指纹不对外 | 3, 5 |
| 标定数字仍空 | 5（不写入生产卡） |

## Execution note

五步串行，后一步依赖前一步接口。本会话按 TDD 在 `feat/xml-classify` 上顺序执行，不在 `main` 上直接改。
