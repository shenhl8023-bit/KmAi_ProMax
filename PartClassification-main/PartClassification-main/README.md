# PartClassification

从开目零件 XML 给出结构类的可能性、分数和原因。学样本仍先看 `.prt` 几何，规则见 `AGENTS.md`。

当前默认打分卡为 `v2-evidence-group-calibrated-candidate`：`locked: true`、`validationStatus: candidate`，由 20 对学习样本校准。`locked` 表示参数已固定且可以运行分类；`candidate` 表示独立集只有两件用户确认的衬套、尚缺独立活门，不能宣称完整两类泛化准确率或“已验证生产卡”。`source/测试样本/` 不纳入学习，只作独立输入输出检查。学样本规则见 `AGENTS.md`。

## 候选卡规则与边界

因子按 `evidence_strength = directional_auc × family_leave_group_out_accuracy × bootstrap_auc_lower_95` 排序：

```text
inner_cyl_balance > inner_cyl_ratio > outer_cyl_ratio > inner_rev_ratio
> wall_to_outer > hollow_ratio > plane_ratio > slenderness
```

三个高度相关的圆柱面因子只计一个证据组，以 `inner_cyl_balance` 为代表；`inner_cyl_ratio`、`outer_cyl_ratio` 仅用于诊断，不重复加分。四个生产证据组权重为 `0.406191 / 0.223875 / 0.222678 / 0.147255`（六位小数和为 `0.999999`）；评分会按当前实际有效组权重和归一化。这些是候选校准值，不是训练结果、概率或总体最优值。`hollow_ratio` 与 `slenderness` 不进入候选生产分数。

主因子必须唯一命中，且至少有一个独立辅助组支持；辅助总分不能推翻主方向，并列返回未定。候选卡不再使用固定 `0.50` 最高分或 `0.10` 分差闸门。

生产卡的区间端点保存为学习 XML 的全精度经验 min/max；文档中的约 9 位小数仅用于展示，不能替代实际端点。20 件学习样本回放 20/20 只证明配置与标定集一致，并非泛化准确率；两件独立衬套通过，按系列留组为 16/20 正确、4/20 未定、0 误判，压差活门保持活门。

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

批量配置：列表支持多选（Ctrl 点选、Shift 连选、Ctrl+A 全选）。选中多个后下拉框改成「批量套用（N 个）」，一次给所有选中样本套用同一模板。**批量只改模板，不动各样本已有的备注**（选中多个时备注框置灰）；选「（未指定）」再批量保存即批量解除映射。批量写入只落盘一次，任一项校验失败则磁盘不变。

`classify` 命中映射时会在结果里多一个 `template` 键，未配置为 `null`：

```json
"template": {"name": "套筒类模板.xml", "path": "<绝对路径>", "note": ""}
```

`similarParts` 里**每一条也带自己的 `template`**（就在 `name` 之后），表示那条相似样本绑定的模板；该条未绑定时为 `null`：

```json
{
  "id": "JRT148-02-01区计量活门衬套",
  "name": "JRT148-02-01区计量活门衬套.XML",
  "template": {"name": "套筒类模板.xml", "path": "<绝对路径>", "note": ""},
  "similarity": 0.920771
}
```

顶层 `template` 只反映**被查询的那个文件自身**，不会拿相似样本的模板替它填。`source/测试样本/` 下的样本不在映射清单里，查它们时顶层是 `null`，但 `similarParts` 里各条仍带自己的模板。

映射存在但模板文件已被删除/改名时，`name` 仍在、`path` 为 `null`，映射不会被自动清除。清单损坏时分类仍照常返回，只是 `template` 为 `null`、各相似项的 `template` 也为 `null`，并多一个 `templateError` 字段（如 `MAP_FILE_CORRUPT`）。输入是 `bytes` 时没有文件名，顶层 `template` 恒为 `null`。

CLI 对应参数为 `--template-map <清单路径>`。`template` 只是登记信息，不是几何真值，不参与打分卡判定。

## 调用

先安装：

```text
py -3 -m pip install -e .
```

```python
from part_classification import classify

result = classify(r"source/XML样本/JRT145-13-01计量活门.XML")
```

或：

```text
py -3 -m part_classification path.xml
```

输入为文件路径或原始字节，按 GB2312 / GBK 解码，不要当 UTF-8 读。生产调用只输入 XML，不要传件号或 PRT；PRT 只用于学习阶段的几何标定。项目不做黑盒训练、HTTP 或 KmAI 集成。

成功时 JSON 含 `ok`、`geometryClass`、`labelZh`、`types`（每类 `id` / `labelZh` / `possibility` / `score` / `reasons`），以及默认按相似度降序排列的 `similarParts`（最多 3 个）。相似样本来自 `source/XML样本/` 这批已标定学习 XML，不包含 `source/测试样本/`；输入本身不会出现在推荐结果中。每条相似样本含 `id`、`name`、`path`、`geometryClass`、`labelZh`、`similarity`（0-1）和 `validFactors`。读失败时 `ok` 为 false，`error` 为 `NOT_KMSOFT_XML`，这不是未定。

Python 调用可用 `similar_top_k=1/2/3` 选择返回数量，并用 `samples_dir` 指定另一批 XML 样本：

```python
result = classify(
    r"source/XML样本/JRT145-13-02计量活门衬套1.XML",
    similar_top_k=3,
)
```

CLI 对应参数为 `--similar-top-k 1|2|3` 和可选的 `--samples-dir <目录>`。相似度使用六个非重复形状因子的样本内归一化绝对距离，缺失因子跳过；它是样本邻近度，不是新的几何真值或泛化准确率。
