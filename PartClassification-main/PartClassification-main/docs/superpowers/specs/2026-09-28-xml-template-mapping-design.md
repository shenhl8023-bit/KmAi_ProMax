# XML 样本与模板映射设计

日期：2026-09-28
状态：设计已确认，尚未实现
范围：PartClassification 的「样本 → 分组模板」登记与查询，含桌面配置界面。不包含模板解析、XML 生成、结构校验、KmAI 或网络服务。

## 1. 背景

`source/模板/` 目前只有一份开目分组模板 `套筒类模板.xml`（141950 字节，GB2312，未跟踪）。`source/XML样本/` 下有 20 份零件 XML，它们与模板之间没有任何已记录的对应关系：代码中不存在 `模板` 或 `template` 字样，`classify` 只读打分卡，不涉及模板。

模板文件与零件 XML 是两类不同的文档，不能混用同一套解析：

| | 零件 XML（样本） | 分组模板 |
|---|---|---|
| 顶层结构 | `Part_Info` / `Part_OtherInfo` / `Point_Set` / `Line_Set` | `Item type="Part_Template"` / `Item type="Group_Template"` / `Item type="Part"` |
| 主要节点 | `Param`（Int / Double / String / Vector）约 1420 个 | `param`（String / Multi / Int / Check）约 815 个 |
| 分组信息 | 无 | `Item type="Group"` 树，带 `特征选择`、`依赖方向`、`依赖方式`、`主轴线上特征` |
| 其他 | 面类型、点集、线集 | 37 个 `Step` 工艺节点 |

因此本设计只登记「哪个样本用哪个模板」，不解析模板内容，也不改动任何 XML 文件。

## 2. 目标与非目标

目标：

1. 20 份样本 XML 可以各自指定一份模板，配置结果可持久化、可查询、可导出。
2. 用户通过本地桌面窗口自行维护映射，不需要改代码或手写 JSON，也不需要命令行。
3. 后续往 `source/模板/` 放入新的模板文件后，界面重新扫描即可使用，无需改代码。
4. 映射命中时，`classify` 的输出带上模板信息。

非目标（本期明确不做）：

- 不解析、不校验模板 XML 的结构或合法性；模板是否规范由开目负责。
- 不比对样本分组与模板 Group 树，不输出差异报告。
- 不生成、不套用、不回写任何 XML。
- 不做件号前缀或几何类的批量继承规则，映射键就是单个样本文件。
- 不引入除标准库外的依赖，不起 HTTP 服务，不做 KmAI 集成。

## 3. 数据模型

### 3.1 模板库

模板库 = 目录扫描结果，不额外登记。

- 默认目录：`<仓库>/source/模板`
- 收录条件：目录下的普通文件，扩展名不区分大小写等于 `.xml`
- 排序：按文件名 `casefold()` 升序
- 模板标识：**完整文件名**（含扩展名），例如 `套筒类模板.xml`
- 只记录文件名与绝对路径，不读取文件内容

### 3.2 映射清单

单一 JSON 文件：`<仓库>/source/模板/模板映射.json`。

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

字段说明：

| 字段 | 说明 |
|---|---|
| `version` | 清单格式版本，本期为整数 `1` |
| `samplesDir` | 相对仓库根的样本目录，仅作记录与界面默认值；不参与查找 |
| `mappings` | 键 = 样本文件名（含扩展名，大小写按磁盘实际）；值 = 目标模板与备注 |
| `mappings.*.template` | 模板文件名，必须存在于模板库中才能写入 |
| `mappings.*.note` | 自由文本，可为空 |
| `mappings.*.updatedAt` | 本地时间 `YYYY-MM-DDTHH:MM:SS`，由程序写入，不手工维护 |

写入规则：

- 编码 UTF-8，`ensure_ascii=False`，`indent=2`，键按 `casefold()` 排序，保证 diff 稳定。
- 原子替换：先写同目录临时文件，`flush` + `os.fsync` 后 `os.replace` 覆盖目标。任何一步失败都不留下半个清单。
- 覆盖式写入：内存中的完整清单写回，不支持并发写保护；单用户本地工具，不做锁文件。

### 3.3 读取语义

- 清单文件不存在 → 返回空清单（`version: 1`、`samplesDir` 默认值、`mappings: {}`），不报错。
- JSON 语法错误、顶层不是对象、`mappings` 不是对象 → `TemplateMapError("MAP_FILE_CORRUPT")`。
- `version` 缺失或不等于 `1` → `TemplateMapError("MAP_VERSION_UNSUPPORTED")`。
- 单条记录缺 `template` 字段 → 视为损坏，报 `MAP_FILE_CORRUPT`，不静默丢弃。

模板缺失不改变清单：映射指向的模板文件被删除或改名后，映射仍然保留，只在查询结果里标记 `templateExists: false`，由用户决定修改或删除。

## 4. 模块接口：`template_map.py`

新增 `src/part_classification/template_map.py`，纯逻辑，不导入 tkinter、不访问网络，全部函数可单测。

```text
default_templates_dir() -> Path                  # 仓库 source/模板
default_map_path() -> Path                       # 仓库 source/模板/模板映射.json
default_samples_dir() -> Path                    # 复用 similarity 的仓库 source/XML样本

list_templates(templates_dir=None) -> list[dict]
    # [{"name": "套筒类模板.xml", "path": "<绝对路径>"}]，按 name 排序

load_map(path=None) -> dict                      # 完整清单字典；不存在则空清单
save_map(data, path=None) -> None                # 原子写入
get_mapping(sample, path=None) -> dict | None    # {"template","note","updatedAt"}
set_mapping(sample, template, note="", path=None) -> dict
remove_mapping(sample, path=None) -> bool        # 是否确实删除了一条
list_mappings(templates_dir=None, samples_dir=None, path=None) -> list[dict]
```

`list_mappings` 的汇总视图供 GUI、CLI 与导出共用，每行：

```json
{
  "sample": "JRT145-13-02计量活门衬套1.XML",
  "sampleExists": true,
  "template": "套筒类模板.xml",
  "templateExists": true,
  "templatePath": "<绝对路径或 null>",
  "note": "",
  "updatedAt": "2026-09-28T10:54:56"
}
```

排序：已配置行按样本名升序在前，未配置行按样本名升序在后。样本目录中存在的文件与清单中残留的键取并集，残留键的 `sampleExists` 为 `false`。

错误类型：

```python
class TemplateMapError(Exception):
    def __init__(self, code: str, message: str) -> None: ...
```

| code | 触发条件 |
|---|---|
| `MAP_FILE_CORRUPT` | 清单语法或结构损坏 |
| `MAP_VERSION_UNSUPPORTED` | `version` 不是 `1` |
| `TEMPLATE_NOT_FOUND` | `set_mapping` 的目标模板不在模板库中 |
| `SAMPLE_KEY_EMPTY` | 样本名为空或只有扩展名 |
| `MAP_DIR_MISSING` | 清单父目录不存在或不可写（§10.6 规定不自动创建目录，因此需要一个明确的错误码） |

`set_mapping` 校验顺序：先校验样本名非空，再校验模板存在于模板库，最后才写盘。校验失败不修改清单文件。

## 5. 接入 `classify`

`classify()` 新增可选参数 `template_map_path: str | Path | None = None`，默认使用 `default_map_path()`。

- 查找键 = 输入路径的**文件名**；命中 → 在结果里增加 `template` 键：

```json
"template": {"name": "套筒类模板.xml", "path": "<绝对路径>", "note": ""}
```

- 未配置 → `"template": null`。
- 输入是 `bytes`（没有文件名）→ `"template": null`，不报错。
- 未锁定卡（`locked: false`）的返回同样带 `template`，字段位置与其他路径一致。
- 清单损坏时，`classify` 不抛异常：`template` 记 `null`，并增加 `"templateError": "<code>"`，避免一个坏配置文件让分类整体失败。
- 读 XML 失败（`NOT_KMSOFT_XML`）的返回不含 `template` 键，与现有错误形态一致。

CLI 相应增加可选参数 `--template-map <路径>`；`template` 随 `classify` 的 JSON 自动输出，不需要其他改动。现有位置参数 `xml_path` 保持不变。

## 6. 界面：`gui.py`（tkinter）

新增 `src/part_classification/gui.py`。

启动方式（两者等价）：

```text
py -3 -m part_classification.gui
part-classify-gui          # pyproject 新增 [project.scripts] 入口
```

`part-classify` 的位置参数语义不变，`tests/test_cli.py` 不受影响。

窗口布局：

- 顶部：样本目录、模板目录、清单文件三个路径（只读显示）+「重新扫描」+「导出清单…」
- 左侧：样本列表，两列显示 `样本名` 与 `模板名`。未配置显示「（未指定）」，模板缺失显示「（模板缺失）」并以红色标记，样本缺失显示「（样本缺失）」；顶部状态文字为「样本 N 个，已配置 M 个」
- 右侧：所选样本的模板下拉框（含「（未指定）」项，选它等于解除映射）、备注输入框、「保存」按钮
- 底部：状态栏，显示保存结果或错误原因

行为：

- 保存即写盘（`set_mapping` / `remove_mapping`），不设自动保存，不需要「应用」二次确认。
- 保存成功后在列表立即刷新该行，状态栏显示「已保存」。
- 校验失败或清单损坏 → `messagebox.showerror` 弹出错误码与说明，界面保持可用，磁盘内容不变。
- 导出：`asksaveasfilename` 选择路径，写 CSV（`utf-8-sig`，Excel 直接打开不乱码），列为 `样本文件, 模板文件, 模板是否存在, 备注, 更新时间`。
- 不联网、不起服务、不开线程、不写临时文件；关闭窗口即退出。
- tkinter 不可用的环境（无显示器、缺少 Tk）在启动时打印明确错误并返回非零退出码，不抛裸回溯。

界面逻辑（模板库扫描、校验、排序、导出数据组织）全部位于 `template_map.py`，GUI 只负责取数、展示和调用，因此自动化测试覆盖在 `template_map` 层完成。

## 7. 错误处理汇总

| 场景 | 行为 |
|---|---|
| 清单文件不存在 | 视为空清单，界面显示 0 个已配置 |
| 清单损坏 / 版本不支持 | GUI 弹窗报错且不写盘；`classify` 记 `templateError` 并继续返回分类结果 |
| 模板文件被删或改名 | 映射保留，界面与 `list_mappings` 标记 `templateExists: false` |
| 样本文件被删或改名 | 映射保留，标记 `sampleExists: false` |
| 目标模板不在模板库 | `set_mapping` 拒绝并报 `TEMPLATE_NOT_FOUND`，不写盘 |
| 模板目录不存在或为空 | 下拉框只有「（未指定）」，保存任意模板都会失败并提示 |
| 写盘中断 | 原子替换保证清单要么是旧内容、要么是新内容 |
| 清单不可写（只读文件、被占用、磁盘满等 `OSError`） | GUI 必须弹窗说明失败原因并保持界面可用；**不得**只留一个 traceback 让用户以为保存成功。`set_mapping` / `remove_mapping` / `save_map` 不得吞掉 `OSError` |

## 8. 测试

新增 `tests/test_template_map.py`：

- 清单不存在时 `load_map` 返回空清单且不报错
- `set_mapping` → `get_mapping` 往返一致，`updatedAt` 被写入
- 覆盖同一映射只保留最后一条
- `remove_mapping` 命中返回 `True`，不命中返回 `False` 且不报错
- 模板不在模板库中 → `TEMPLATE_NOT_FOUND`，且清单文件内容未变
- 空样本名 → `SAMPLE_KEY_EMPTY`
- 坏 JSON、`version: 2`、`mappings` 非对象 → 对应错误码
- `list_mappings` 正确标记 `sampleExists` / `templateExists`
- 写入为原子替换：写入后原文件不残留临时文件
- 输出编码为 UTF-8 且中文文件名不被转义（读回原始文本断言包含中文字面）

新增 `tests/test_classify_template.py`：

- 配好映射后 `classify` 返回的 `template` 是 dict，`name` 与配置一致
- 未配置时 `template` 为 `null`
- 传入 `bytes` 时 `template` 为 `null`
- 未锁定卡的返回同样带 `template`
- 清单损坏时 `template` 为 `null` 且 `templateError` 为 `MAP_FILE_CORRUPT`，分类结果仍正常

测试全部使用 `tmp_path` 构造清单与模板目录，不读取也不修改仓库内真实清单。

验证边界：GUI 需要显示器，不做自动化测试；`gui.py` 仅保证可导入、不产生副作用，界面行为靠人工点开确认。

## 9. 文档更新

- `README.md`：新增「样本与模板映射」一节，说明清单位置与格式、`classify` 的 `template` 字段、GUI 启动命令、CSV 导出。
- `AGENTS.md`：新增一节，写明模板映射的边界——只登记映射，不解析模板、不校验结构、不生成 XML；`source/模板/` 与 `模板映射.json` 的性质；映射不参与打分卡与分类判定。

## 10. 已定决策与影响

1. **映射键 = 单个样本文件名。** 不做前缀或几何类继承。
2. **只登记与查询。** 模板内容不解析、不校验、不生成 XML。
3. **界面形态 = 本地 tkinter 桌面窗口。** 零新依赖、不起 HTTP 服务，不与 AGENTS.md 的「不做 HTTP 集成」冲突。
4. **`classify` 输出新增 `template` 键。** 这是对外契约变更，会打破两处现有断言，必须同步更新：
   - `tests/test_classify_unlocked.py` 中 `result == {...}` 的整体相等断言。
   - `tests/test_reproducibility.py` 中 3 个断言「路径输入与 `bytes` 输入返回完全相同」的测试。`template` 依赖文件名，而 `bytes` 没有文件名，因此该相等性对 `template` 键不再成立。这些测试的价值在于打分结果的确定性，修改方式是先剔除 `template` / `templateError` 再比较，并另外钉住「`bytes` 输入 `template` 恒为 `null`」。

   其余测试只做键存在性或子集断言，不受影响。
5. **`source/模板/模板映射.json` 纳入版本控制。** 它是人工配置成果，需要可追溯；`source/模板/` 目录本身目前未跟踪，实现时一并加入。模板 XML 文件是否入库由用户另行决定，本设计不代为判断。
6. **不自动创建模板目录。** 目录缺失时按「模板库为空」处理，不悄悄创建空目录。

## 11. 风险与未验证项

- 模板文件可能很大（现有 141950 字节）；本设计不读取内容，因此不存在性能与编码风险。若将来要做结构校验，需另行设计 GB2312 解析路径。
- 单文件清单在多实例同时编辑时会互相覆盖。当前是单用户本地工具，不处理并发；出现该场景再加锁。
- 20 个样本的映射配置需要人工逐条填写，本设计不提供批量导入；如需要，作为后续独立需求。
- `classify` 的 `template` 字段是登记信息，不是几何真值，也不参与打分卡判定或 `similarParts` 计算。
