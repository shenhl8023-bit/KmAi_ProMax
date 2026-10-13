# XML 因子重标定与证据组评分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前没有可追溯依据的 `v1-folder-calibrated` 因子权重替换为基于20对学习样本重算的、去除重复信息的证据组候选卡，并保持 XML 分类结果可解释、可拒判、可复现。

**Architecture:** 保留现有 XML 解码、指纹提取和公开 JSON 契约。`scorecard.py` 增加可选的证据组模型：圆柱面构成组只用 `inner_cyl_balance` 代表，`inner_cyl_ratio` 和 `outer_cyl_ratio` 作为诊断成员不重复加分；内部回转面、薄壁、平面各作为独立辅助组。没有 `evidenceGroups` 的内存测试卡继续走旧评分路径，生产卡使用新路径。主因子先确定唯一方向，辅助组只能支持或拒判，不能翻转主因子。

**Tech Stack:** Python 3.10+ 标准库（`dataclasses`、`json`、`pathlib`）、pytest、现有 src layout；不新增依赖，不引入训练模型、HTTP 或 KmAI。

**Spec:** `docs/superpowers/specs/2026-08-24-xml-factor-recalibration-design.md`

## Global Constraints

- 学习标签来自 `source/活门prt/` 与 `source/活门衬套prt/` 的20对 PRT/XML；`source/测试样本/` 不参与权重、区间或排序计算。
- `JRT145-17-01压差活门` 的用户确认类型是 `spool`（活门），必须保留为回归样本。
- 输入只有 XML；按 GB2312 / GBK 解码；PRT 只用于学习阶段，不能进入 `classify` 请求。
- invalid 因子跳过，不当作0分；缺失证据组从分母移除，剩余有效组重新归一化；数值0仍是有效观测。
- 生产卡固定为 `locked: true`，但必须写 `validationStatus: "candidate"`，不得宣称统计验证完成。
- 新卡权重固定为：圆柱面构成组 `0.406191`、内部回转面组 `0.223875`、薄壁组 `0.222678`、平面组 `0.147255`；合计为1。
- 新卡经验范围严格使用学习样本实际最小值/最大值，不做人为外扩：`inner_cyl_balance` 衬套 `[0.433380084, 0.502170767]`、活门 `[0.071212121, 0.418158568]`；`inner_rev_ratio` 衬套 `[0.371801970, 0.603647895]`、活门 `[0.060164917, 0.438915538]`；`wall_to_outer` 衬套 `[0.139818182, 0.358200000]`、活门 `[0.216444444, 0.564250000]`；`plane_ratio` 衬套 `[0.074, 0.258]`、活门 `[0.195, 0.373]`。
- `hollow_ratio` 和 `slenderness` 保留在指纹/诊断层，不进入新卡生产分数；不得再次用未追溯的固定权重。
- 新判定不沿用旧的固定 `min_top_score=0.50` 和 `min_score_gap=0.10`：主因子未命中唯一类别、无辅助支持、辅助结果推翻主方向或两类分数相等时返回 `unknown`。
- 除非用户另行授权，不执行 commit、push、rebase、reset 或删除操作。

## File Structure

| Path | Responsibility |
|---|---|
| `src/part_classification/scorecard.py` | 解析证据组、候选组评分、旧卡兼容、主方向闸门 |
| `src/part_classification/classify.py` | 保持锁定/未锁定分支，调用新评分和判定接口 |
| `src/part_classification/data/scorecard.json` | 写入 `v2-evidence-group-calibrated-candidate` 生产卡 |
| `tests/test_scorecard.py` | 保留旧卡行为测试，补充证据组单元测试 |
| `tests/test_candidate_calibration.py` | 20件学习集、2件独立衬套和压差活门回归 |
| `tests/test_reproducibility.py` | 新默认卡路径与字节/路径输入的一致性 |
| `AGENTS.md` | 同步当前生产卡、排序、权重和验证限制 |
| `README.md` | 同步调用方式、候选状态和未定规则 |
| `docs/superpowers/specs/2026-08-24-xml-factor-recalibration-design.md` | 标记候选设计已实现，保留样本限制和分析依据 |

---

### Task 1: 扩展 Scorecard 数据结构并锁定候选卡 schema

**Files:**
- Modify: `src/part_classification/scorecard.py`
- Modify: `tests/test_scorecard.py`
- Create: `tests/test_candidate_scorecard.py`

**Interfaces:**
- `EvidenceGroupSpec(id: str, weight: float, representative_factor: str, factors: tuple[str, ...])`
- `Scorecard` 新增 `validation_status: str | None`、`primary_factor: str | None`、`evidence_groups: tuple[EvidenceGroupSpec, ...]`；旧字段保持不变。
- `parse_scorecard(data: dict) -> Scorecard` 读取顶层 `validationStatus`、`primaryFactor`、`evidenceGroups`；没有 `evidenceGroups` 的旧内存卡得到空 tuple，不能影响现有旧路径。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_candidate_scorecard.py` 中先用以下完整的最小候选卡验证解析结果：

```python
from part_classification.scorecard import parse_scorecard


def candidate_card_data():
    return {
        "id": "v2-evidence-group-calibrated-candidate",
        "locked": True,
        "validationStatus": "candidate",
        "primaryFactor": "inner_cyl_balance",
        "evidenceGroups": [
            {
                "id": "cylinder_group",
                "weight": 0.406191,
                "representativeFactor": "inner_cyl_balance",
                "factors": ["inner_cyl_balance", "inner_cyl_ratio", "outer_cyl_ratio"],
            },
            {
                "id": "inner_rev_group",
                "weight": 0.223875,
                "representativeFactor": "inner_rev_ratio",
                "factors": ["inner_rev_ratio"],
            },
            {
                "id": "wall_group",
                "weight": 0.222678,
                "representativeFactor": "wall_to_outer",
                "factors": ["wall_to_outer"],
            },
            {
                "id": "plane_group",
                "weight": 0.147255,
                "representativeFactor": "plane_ratio",
                "factors": ["plane_ratio"],
            },
        ],
        "classes": [
            {
                "id": "sleeve",
                "labelZh": "活门衬套",
                "factors": {
                    "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.433380084, 0.502170767]},
                    "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.371801970, 0.603647895]},
                    "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.139818182, 0.358200000]},
                    "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.074, 0.258]},
                },
            },
            {
                "id": "spool",
                "labelZh": "活门",
                "factors": {
                    "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.071212121, 0.418158568]},
                    "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.060164917, 0.438915538]},
                    "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.216444444, 0.564250000]},
                    "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.195, 0.373]},
                },
            },
        ],
        "gates": {"min_auxiliary_groups": 1},
    }


def test_candidate_scorecard_parses_evidence_groups_and_status():
    card = parse_scorecard(candidate_card_data())
    assert card.id == "v2-evidence-group-calibrated-candidate"
    assert card.locked is True
    assert card.validation_status == "candidate"
    assert card.primary_factor == "inner_cyl_balance"
    assert [group.id for group in card.evidence_groups] == [
        "cylinder_group", "inner_rev_group", "wall_group", "plane_group"
    ]
    assert sum(group.weight for group in card.evidence_groups) == pytest.approx(1.0)


def test_legacy_in_memory_card_still_has_no_candidate_groups():
    card = parse_scorecard({"id": "legacy", "locked": True, "classes": [], "gates": {}})
    assert card.evidence_groups == ()
    assert card.primary_factor is None
```

补 `import pytest`，并用上一段相同的 `candidate_card_data` 给后续任务复用；不要从生产 JSON 导入测试数据。

- [ ] **Step 2: Run test to verify it fails**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py -q`

预期：失败，当前 `Scorecard` 没有 `validation_status` / `evidence_groups` 属性。

- [ ] **Step 3: Implement the minimal parser/model change**

在 `scorecard.py` 增加数据类并在 `parse_scorecard` 中只解析新字段，不改变旧字段含义：

```python
@dataclass(frozen=True)
class EvidenceGroupSpec:
    id: str
    weight: float
    representative_factor: str
    factors: tuple[str, ...]


@dataclass(frozen=True)
class Scorecard:
    id: str
    locked: bool
    classes: tuple[ClassSpec, ...]
    gates: Gates
    validation_status: str | None = None
    primary_factor: str | None = None
    evidence_groups: tuple[EvidenceGroupSpec, ...] = ()
```

`evidenceGroups` 每项按 `EvidenceGroupSpec` 转换；`representativeFactor` 必须是 `factors` 成员；`weight` 使用 `float`。候选解析不把 `inner_cyl_ratio` / `outer_cyl_ratio` 自动变成独立组。`Gates` 增加 `min_auxiliary_groups: int | None`，旧 `min_valid_factors`、`min_top_score`、`min_score_gap` 原样保留，以支持现有测试卡。

- [ ] **Step 4: Run tests to verify they pass**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py tests/test_scorecard.py -q`

预期：新 schema 测试和既有旧评分卡测试均通过；此时新组尚未参与评分。

- [ ] **Step 5: Stop for review**

记录解析结构的测试结果，暂不提交 Git；生产 JSON 仍保持旧卡，等待 Task 2 的评分实现。

### Task 2: 实现证据组去重评分与缺失组归一化

**Files:**
- Modify: `src/part_classification/scorecard.py`
- Modify: `tests/test_candidate_scorecard.py`

**Interfaces:**
- 保持 `match_degree(value, interval) -> float` 的二值匹配契约：区间内 `1.0`，区间外 `0.0`。
- 保持 `score_fingerprint(fp, card) -> list[TypeResult]`；当 `card.evidence_groups` 非空时走候选组路径，否则走现有旧因子路径。
- 候选组路径中 `TypeResult.valid_used` 表示本轮实际使用的有效组数；旧路径仍表示有效因子数。

- [ ] **Step 1: Write the failing tests**

加入以下三类行为测试，使用 `candidate_card_data()` 和 `kmsoft_xml_bytes`：

```python
from part_classification.classify import classify
from part_classification.scorecard import parse_scorecard, score_fingerprint
from part_classification.fingerprint import extract_fingerprint
from part_classification.xml_read import read_kmsoft_xml
from tests.xml_builder import kmsoft_xml_bytes


def test_duplicate_cylinder_members_are_scored_once():
    card = parse_scorecard(candidate_card_data())
    fp = extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=40.0, surface_area=100.0,
        wall_mean=2.0, max_outer=10.0, plane_ratio=0.10,
    )))
    sleeve = next(row for row in score_fingerprint(fp, card) if row.id == "sleeve")
    assert sleeve.score == pytest.approx(1.0)
    assert sleeve.valid_used == 4


def test_missing_auxiliary_group_renormalizes_remaining_weights():
    card = parse_scorecard(candidate_card_data())
    fp = extract_fingerprint(read_kmsoft_xml(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=None, wall_mean=2.0, max_outer=10.0,
        plane_ratio=0.10,
    )))
    sleeve = next(row for row in score_fingerprint(fp, card) if row.id == "sleeve")
    assert sleeve.valid_used == 3
    assert sleeve.score == pytest.approx((0.406191 + 0.222678 + 0.147255) / (1.0 - 0.223875))


def test_overlapping_auxiliary_ranges_do_not_override_primary_direction():
    card = parse_scorecard(candidate_card_data())
    result = classify(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=40.0, surface_area=100.0,
        wall_mean=2.0, max_outer=10.0, plane_ratio=0.10,
    ), scorecard=card)
    assert result["geometryClass"] == "sleeve"
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["sleeve"]["score"] > by_id["spool"]["score"]
```

- [ ] **Step 2: Run test to verify it fails**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py -q`

预期：失败，当前评分器只遍历 `ClassSpec.factors`，不知道 `evidence_groups`，也没有按有效组重新归一化。

- [ ] **Step 3: Implement candidate group scoring**

在 `scorecard.py` 增加候选路径，核心规则固定为：

```python
def _score_candidate_class(fp: Fingerprint, cls: ClassSpec, card: Scorecard):
    weighted = 0.0
    weight_sum = 0.0
    valid_groups = 0
    for group in card.evidence_groups:
        value = fp.get(group.representative_factor)
        if value is None:
            continue
        spec = cls.factors[group.representative_factor]
        weighted += group.weight * match_degree(value, spec.interval)
        weight_sum += group.weight
        valid_groups += 1
    score = weighted / weight_sum if weight_sum else 0.0
    return score, valid_groups
```

实际实现需同时沿用现有理由生成和 invalid 理由逻辑：理由只按证据组代表因子排序，圆柱面构成组的其他成员最多作为“诊断成员，已去重”附加说明，不能改变 `weighted` 或 `weight_sum`。`score_fingerprint` 仍按卡中 classes 顺序返回，possibility 仍为两类 score 的总和归一化。

- [ ] **Step 4: Run tests to verify they pass**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py tests/test_scorecard.py -q`

预期：证据组重复不放大、缺失组重新归一化、旧卡行为全部通过。

- [ ] **Step 5: Stop for review**

核对测试中 `valid_used` 是组数而不是因子数，确认任何重复组成员都没有进入分母；不提交 Git。

### Task 3: 接入主因子唯一命中和保守拒判闸门

**Files:**
- Modify: `src/part_classification/scorecard.py`
- Modify: `src/part_classification/classify.py`
- Modify: `tests/test_candidate_scorecard.py`

**Interfaces:**
- 保持 `decide_geometry_class(results, card, fp) -> str` 签名。
- 候选卡判定顺序：主因子有效且只命中一个类别 → 至少一个独立辅助组支持该类别 → 最高分与主方向一致 → 两类分数不相等；否则返回 `"unknown"`。
- 旧卡无 `evidence_groups` 时继续使用原 `Gates(min_valid_factors, min_top_score, min_score_gap)` 逻辑。

- [ ] **Step 1: Write the failing tests**

加入以下拒判和边界测试：

```python
def test_missing_primary_is_unknown_even_when_auxiliary_values_exist():
    card = parse_scorecard(candidate_card_data())
    result = classify(kmsoft_xml_bytes(inner_cyl_ratio=None, outer_cyl_ratio=0.55), scorecard=card)
    assert result["geometryClass"] == "unknown"


def test_primary_value_in_both_or_neither_interval_is_unknown():
    card_data = candidate_card_data()
    card_data["classes"][1]["factors"]["inner_cyl_balance"]["interval"] = [0.40, 0.50]
    both = classify(kmsoft_xml_bytes(inner_cyl_ratio=0.45, outer_cyl_ratio=0.55), scorecard=parse_scorecard(card_data))
    assert both["geometryClass"] == "unknown"

    neither = classify(kmsoft_xml_bytes(inner_cyl_ratio=0.80, outer_cyl_ratio=0.20), scorecard=parse_scorecard(candidate_card_data()))
    assert neither["geometryClass"] == "unknown"


def test_primary_direction_conflict_returns_unknown():
    card_data = candidate_card_data()
    for cls in card_data["classes"]:
        cls["factors"]["inner_rev_ratio"]["interval"] = [0.0, 0.01]
        cls["factors"]["wall_to_outer"]["interval"] = [0.0, 0.01]
        cls["factors"]["plane_ratio"]["interval"] = [0.0, 0.01]
    result = classify(kmsoft_xml_bytes(
        inner_cyl_ratio=0.45, outer_cyl_ratio=0.55,
        inner_rev_area=40.0, surface_area=100.0,
        wall_mean=2.0, max_outer=10.0, plane_ratio=0.10,
    ), scorecard=parse_scorecard(card_data))
    assert result["geometryClass"] == "unknown"
```

另外加入真实边界样本：`source/XML样本/JRT145-17-01压差活门.XML` 必须判为 `spool`。

- [ ] **Step 2: Run test to verify it fails**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py -q`

预期：失败，旧 `decide_geometry_class` 会按普通最高分或旧闸门判定，尚未检查主因子唯一命中和方向冲突。

- [ ] **Step 3: Implement candidate decision path**

在 `decide_geometry_class` 开头按 `card.evidence_groups` 分派候选逻辑：

```python
primary = card.primary_factor
primary_value = fp.get(primary) if primary else None
hits = [cls for cls in card.classes
        if primary_value is not None
        and primary in cls.factors
        and match_degree(primary_value, cls.factors[primary].interval) == 1.0]
if len(hits) != 1:
    return "unknown"
target = hits[0].id
```

统计除主组外的有效辅助组中，代表因子落入 `target` 类区间的组数；少于 `card.gates.min_auxiliary_groups` 时返回 `unknown`。再比较 `results`：最高分必须是 `target`，且最高分不能与另一类相等；任何缺失组已经由 Task 2 从分母删除。候选路径不得读取 `min_top_score` / `min_score_gap` 作为固定闸门。`classify.py` 继续在锁定卡返回完整 `types`，只把 `geometryClass` 置为 `unknown`。

- [ ] **Step 4: Run tests to verify they pass**

运行：`py -3 -m pytest tests/test_candidate_scorecard.py tests/test_classify_unlocked.py tests/test_scorecard.py -q`

预期：主因子缺失、主因子重叠/未命中、辅助冲突均拒判；旧未锁定和旧锁定卡测试保持通过。

- [ ] **Step 5: Stop for review**

重点人工核对：压差活门的辅助因子不能把主因子指向从 `spool` 翻成 `sleeve`；主因子冲突必须是 `unknown`，而不是强行二选一。

### Task 4: 替换生产评分卡并做学习集/独立样本回放

**Files:**
- Modify: `src/part_classification/data/scorecard.json`
- Create: `tests/test_candidate_calibration.py`
- Modify: `tests/test_reproducibility.py`

**Interfaces:**
- 默认 `load_scorecard()` 返回 `v2-evidence-group-calibrated-candidate`，`locked=True`、`validationStatus="candidate"`。
- `classify(path)` 与 `classify(path.read_bytes())` 对同一 XML 返回完全相同 JSON。

- [ ] **Step 1: Write the failing regression tests**

`tests/test_candidate_calibration.py` 使用真实文件，不读取 PRT 内容来做运行时判定：

```python
from pathlib import Path

from part_classification import classify

REPO = Path(__file__).resolve().parents[1]
XML_DIR = REPO / "source" / "XML样本"
TEST_DIR = REPO / "source" / "测试样本"


def test_default_card_is_the_candidate_card():
    result = classify(XML_DIR / "JRT145-13-02计量活门衬套1.XML")
    assert result["geometryClass"] == "sleeve"


def test_all_learning_xml_match_folder_labels():
    for folder, expected in (("活门prt", "spool"), ("活门衬套prt", "sleeve")):
        for prt in sorted((REPO / "source" / folder).glob("*.prt")):
            result = classify(XML_DIR / f"{prt.stem}.XML")
            assert result["geometryClass"] == expected, prt.stem


def test_two_holdouts_are_sleeves():
    for name in ("taotong.XML", "衬套.XML"):
        assert classify(TEST_DIR / name)["geometryClass"] == "sleeve"


def test_confirmed_pressure_valve_remains_spool():
    result = classify(XML_DIR / "JRT145-17-01压差活门.XML")
    assert result["geometryClass"] == "spool"
    by_id = {row["id"]: row for row in result["types"]}
    assert by_id["spool"]["score"] > by_id["sleeve"]["score"]
```

同时断言默认 card 的四个组权重和为 `pytest.approx(1.0)`，不存在 `4.0` 权重，且 `validationStatus == "candidate"`；把这些断言放在 `load_scorecard()` 上，避免只验证一个 XML 结果。

- [ ] **Step 2: Run test to verify it fails**

运行：`py -3 -m pytest tests/test_candidate_calibration.py -q`

预期：失败，默认生产卡仍是旧 `v1-folder-calibrated`，新 schema/新闸门还未覆盖完整样本。

- [ ] **Step 3: Write the candidate production JSON**

将 `scorecard.json` 改为下列结构；四类组使用 Global Constraints 中的权重和范围，类内只放四个代表因子：

```json
{
  "id": "v2-evidence-group-calibrated-candidate",
  "locked": true,
  "validationStatus": "candidate",
  "primaryFactor": "inner_cyl_balance",
  "evidenceGroups": [
    {"id": "cylinder_group", "weight": 0.406191, "representativeFactor": "inner_cyl_balance", "factors": ["inner_cyl_balance", "inner_cyl_ratio", "outer_cyl_ratio"]},
    {"id": "inner_rev_group", "weight": 0.223875, "representativeFactor": "inner_rev_ratio", "factors": ["inner_rev_ratio"]},
    {"id": "wall_group", "weight": 0.222678, "representativeFactor": "wall_to_outer", "factors": ["wall_to_outer"]},
    {"id": "plane_group", "weight": 0.147255, "representativeFactor": "plane_ratio", "factors": ["plane_ratio"]}
  ],
  "classes": [
    {"id": "sleeve", "labelZh": "活门衬套", "factors": {
      "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.433380084, 0.502170767]},
      "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.371801970, 0.603647895]},
      "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.139818182, 0.3582]},
      "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.074, 0.258]}
    }},
    {"id": "spool", "labelZh": "活门", "factors": {
      "inner_cyl_balance": {"role": "primary", "weight": 0.406191, "interval": [0.071212121, 0.418158568]},
      "inner_rev_ratio": {"role": "secondary", "weight": 0.223875, "interval": [0.060164917, 0.438915538]},
      "wall_to_outer": {"role": "secondary", "weight": 0.222678, "interval": [0.216444444, 0.56425]},
      "plane_ratio": {"role": "secondary", "weight": 0.147255, "interval": [0.195, 0.373]}
    }}
  ],
  "gates": {"min_auxiliary_groups": 1}
}
```

`inner_cyl_ratio`、`outer_cyl_ratio`、`hollow_ratio`、`slenderness` 不得作为 class factor 进入生产分数；它们仍由 `fingerprint.py` 提取，可在诊断理由中显示。

- [ ] **Step 4: Run tests to verify they pass**

运行：`py -3 -m pytest tests/test_candidate_calibration.py tests/test_reproducibility.py -q`，再运行完整套件 `py -3 -m pytest -q`。

预期：20件学习样本回放20/20正确；`taotong` 和 `衬套` 判为 `sleeve`；`JRT145-17-01压差活门` 判为 `spool`；路径与字节输入结果一致。系列留组的16/20正确、4/20未定、0误判属于分析验证结果，不把它硬编码成运行时测试准确率。

- [ ] **Step 5: Stop for review**

保存完整测试输出，确认独立集只有两件衬套，不能在文档或测试名称中声称已经得到完整两类泛化准确率；不提交 Git。

### Task 5: 同步项目规则、README 和重标定设计状态

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-24-xml-factor-recalibration-design.md`

**Interfaces:**
- 不增加 Python API；文档必须与 `scorecard.json` 和 `scorecard.py` 的实际字段、闸门和输出一致。

- [ ] **Step 1: Write documentation assertions before editing**

用 PowerShell 做静态检查，先让它失败以确保文档没有悄悄沿用旧结论：

```powershell
$agents = Get-Content -Raw AGENTS.md
$readme = Get-Content -Raw README.md
if ($agents -match 'v1-folder-calibrated' -or $readme -match 'v1-folder-calibrated') {
    throw '文档仍引用旧生产卡'
}
if ($agents -notmatch 'validationStatus|candidate' -or $readme -notmatch 'candidate') {
    throw '文档缺少候选验证状态'
}
```

- [ ] **Step 2: Run assertion to verify it fails**

运行：`powershell -NoProfile -Command '& { $agents = Get-Content -Raw AGENTS.md; $readme = Get-Content -Raw README.md; if ($agents -match "v1-folder-calibrated" -or $readme -match "v1-folder-calibrated") { throw "文档仍引用旧生产卡" }; if ($agents -notmatch "validationStatus|candidate" -or $readme -notmatch "candidate") { throw "文档缺少候选验证状态" } }'`

预期：失败，因为当前文档仍描述旧 `v1-folder-calibrated`。

- [ ] **Step 3: Update documentation from the implemented card**

在 `AGENTS.md` 和 `README.md` 明确写出：排序依据是 `evidence_strength = AUC × 系列留组正确率 × Bootstrap 下界`；生产组权重为 `0.406191 / 0.223875 / 0.222678 / 0.147255`；三项圆柱面因子只计代表因子；候选卡不是训练模型或统计概率；主因子冲突返回未定；只有 XML 输入。设计文档把状态从“候选设计、未写入生产卡”改为“候选卡已实现”，保留20件学习集、2件独立衬套、16/20系列留组和缺少独立活门样本等限制。

- [ ] **Step 4: Run documentation and full verification**

运行静态断言（此时应通过）以及：

```powershell
py -3 -m pytest -q
rg -n "4\.0|v1-folder-calibrated|validationStatus|0\.406191|inner_cyl_balance" AGENTS.md README.md docs/superpowers/specs/2026-08-24-xml-factor-recalibration-design.md src/part_classification/data/scorecard.json
```

预期：全套测试通过；文档和生产卡不再把 `4.0` 当作当前权重；候选状态和限制在三处保持一致。

- [ ] **Step 5: Stop and report**

汇报修改文件、实际测试命令与结果、系列留组的保守未定样本，以及“尚缺独立活门样本，`validationStatus` 仍为 candidate”的限制。提交和推送等待用户明确授权。

## Self-review Checklist

- [ ] 解析器同时支持新候选卡和无 `evidenceGroups` 的旧内存测试卡。
- [ ] 评分只按证据组代表因子计算；缺失组不当0分；重复圆柱因子不重复计分。
- [ ] 主因子唯一命中、辅助支持、冲突拒判、分数相等拒判均有测试。
- [ ] 20件学习样本、2件独立衬套和压差活门均有真实 XML 回归测试。
- [ ] 文档明确权重是当前20件样本的候选校准值，不是训练结果、概率或总体最优值。
- [ ] 未执行 commit/push，未改动与任务无关的文件。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-24-xml-factor-recalibration.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints for review

Which approach?
