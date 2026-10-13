# 3DMPS MCP 工具可用性排查报告

排查时间：2026-07-06

## 1. 排查结论

当前 Python 端注册了 64 个 MCP 工具。经过源码静态对比和安全只读接口抽样验证，结论如下：

| 分类 | 数量 | 说明 |
|---|---:|---|
| 明确未注册，当前不可用 | 27 | Python 端有工具声明，但 3DMPS 主程序端没有对应桥接函数，调用会 `FUNCTION_NOT_FOUND` |
| 已注册但依赖弹窗状态 | 18 | C++ 端有注册，但只有对应弹窗打开/激活时才可用 |
| 主窗口常驻注册 | 13 | 主程序 `MainFrm` 已注册，通常可通过命名管道调用；其中部分会触发操作 |
| 后端组合工具 / 操作型工具 | 6 | Python 后端内部组合多个步骤，或点击主窗口按钮；可用性取决于当前模型、弹窗、模板和业务状态 |

> 本次没有直接逐个执行 64 个工具，因为其中包含打开模型、保存、关闭、导出、生成工艺、点击按钮等有副作用操作。只对只读/状态类工具做了实际调用验证。

## 2. 关键源码依据

主窗口常驻函数注册位置：

```text
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6152
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6154
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6155
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6156
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6157
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp:6158
```

旧工具名到语义化函数名的兼容映射位置：

```text
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:169
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:175
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:178
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:181
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:184
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:187
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp:190
```

弹窗工具注册位置：

```text
E:\MPS\3DMPS\src\KM3DMPS\DlgFeatureWithDirection.cpp:905
E:\MPS\3DMPS\src\KM3DMPS\DlgProcessRapidArrange.cpp:3418
E:\MPS\3DMPS\src\KM3DMPS\KmGroupTemplateManager.cpp:605
```

Python 后端复合工具分支位置：

```text
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1669
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1670
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1672
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1678
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1680
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\KmMpsMcpServer\backend\agent_core.py:1682
```

## 3. 安全实际验证结果

只调用了只读/状态类工具，结果如下：

| 工具 | 结果 | 说明 |
|---|---|---|
| `get_all_bof_item` | 成功 | 已能返回当前模型 BOF / 特征树数据 |
| `get_bof_tree_data` | 成功 | 映射到 `get_all_bof_item`，可用 |
| `check_3dmps_status` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_cur_model_info` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_process_steps` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_features` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_rough_info` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_bop_tree` | 失败 | `FUNCTION_NOT_FOUND` |
| `is_button_checked` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_ai_process_route_status` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_autoidentify_checkbox_list` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_autoidentify_template_list` | 失败 | `FUNCTION_NOT_FOUND` |
| `get_all_group_template_list` | 当前失败 | `Target window not available: group_template_dialog`，说明需要分组模板弹窗打开 |
| `getAllGroupTemplateList` | 当前超时 | 同样属于分组模板弹窗上下文工具 |

原始验证结果保存于：

```text
E:\MPS\3DMPS\Project\VS2019MPS\Win32\DbgRelease\KmAI\mcp_safe_probe_results.json
```

## 4. 明确未注册，当前不可用的 27 个工具

这些工具在 Python 端注册了，但在当前 3DMPS 主程序桥接注册表里没有对应函数或兼容映射。当前直接调用会返回 `FUNCTION_NOT_FOUND`，或按源码对比可判定为未注册。

| 序号 | 工具 | Python 目标函数 | 问题 |
|---:|---|---|---|
| 1 | `get_cur_model_info` | `get_cur_model_info` | 主程序未注册 |
| 2 | `get_process_steps` | `get_process_steps` | 主程序未注册 |
| 3 | `get_features` | `get_features` | 主程序未注册 |
| 4 | `get_rough_info` | `get_rough_info` | 主程序未注册 |
| 5 | `get_bop_tree` | `get_bop_tree` | 主程序未注册 |
| 6 | `close_prt_file` | `close_prt_file` | 主程序未注册 |
| 7 | `save_file` | `save_file` | 主程序未注册 |
| 8 | `save_as` | `save_as` | 主程序未注册 |
| 9 | `export_pdf` | `export_pdf` | 主程序未注册 |
| 10 | `export_excel` | `export_excel` | 主程序未注册 |
| 11 | `export_gxk` | `export_gxk` | 主程序未注册 |
| 12 | `auto_save` | `auto_save` | 主程序未注册 |
| 13 | `create_step` | `create_step` | 主程序未注册 |
| 14 | `reset_step_number` | `reset_step_number` | 主程序未注册 |
| 15 | `arrange_step` | `arrange_step` | 主程序未注册 |
| 16 | `rapid_create_step` | `rapid_create_step` | 主程序未注册 |
| 17 | `check_process_step` | `check_process_step` | 主程序未注册 |
| 18 | `check_model_compare` | `check_model_compare` | 主程序未注册 |
| 19 | `show_identify_report` | `show_identify_report` | 主程序未注册 |
| 20 | `is_button_checked` | `is_button_checked` | 主程序未注册 |
| 21 | `check_3dmps_status` | `check_3dmps_status` | 主程序未注册；建议改成后端本地 health 检查 |
| 22 | `submit_ai_process_route_output` | `submit_ai_process_route_output` | 主程序未注册 |
| 23 | `get_ai_process_route_status` | `get_ai_process_route_status` | 主程序未注册 |
| 24 | `start_ai_process_route` | `start_ai_process_route` | 主程序未注册 |
| 25 | `generate_ai_process_route` | `generate_ai_process_route` | 主程序未注册 |
| 26 | `get_autoidentify_checkbox_list` | `get_autoidentify_checkbox_list` | Python 映射名不对；C++ 侧兼容的是 `GetAutoIdentifyCheckedList` |
| 27 | `get_autoidentify_template_list` | `get_autoidentify_template_list` | Python 映射名不对；C++ 侧兼容的是 `GetExtractDataList` |

## 5. 已注册但依赖弹窗状态的 18 个工具

这些工具 C++ 端有注册，但只有对应弹窗处于打开/激活状态时才能用。否则会返回 `Target window not available`、超时，或因为当前 active dialog 不匹配而失败。

| 序号 | 工具 | 实际 C++ 语义函数 | 使用条件 |
|---:|---|---|---|
| 1 | `check_autoidentify_btn_ok` | `autoidentify.dialog.confirm` | 自动识别弹窗打开 |
| 2 | `check_autoidentify_btn_cancel` | `autoidentify.dialog.cancel` | 自动识别弹窗打开 |
| 3 | `check_autoidentify_btn_selectall` | `autoidentify.features.select_all` | 自动识别弹窗打开 |
| 4 | `check_autoidentify_btn_deselectall` | `autoidentify.features.deselect_all` | 自动识别弹窗打开 |
| 5 | `set_autoidentify_checkbox_list` | `autoidentify.features.set_checked` | 自动识别弹窗打开 |
| 6 | `use_autoidentify_template` | `autoidentify.templates.apply` | 自动识别弹窗打开 |
| 7 | `use_autoidentify_template_by_index` | `autoidentify.templates.apply` | 自动识别弹窗打开 |
| 8 | `check_processrapid_btn_ok` | `processrapid.dialog.confirm` | 快速工序弹窗打开 |
| 9 | `get_all_group_template_list` | `group_template.templates.list` | 分组模板弹窗打开 |
| 10 | `specify_group_template_index` | `group_template.templates.select_by_index` | 分组模板弹窗打开 |
| 11 | `specify_group_template_name` | `group_template.templates.select_by_name` | 分组模板弹窗打开 |
| 12 | `group_template_dialog_ok` | `group_template.dialog.confirm` | 分组模板弹窗打开 |
| 13 | `group_template_dialog_cancel` | `group_template.dialog.cancel` | 分组模板弹窗打开 |
| 14 | `getAllGroupTemplateList` | `group_template.templates.list` | 分组模板弹窗打开 |
| 15 | `specifyGroupTemplateIndex` | `group_template.templates.select_by_index` | 分组模板弹窗打开 |
| 16 | `specifyGroupTemplateName` | `group_template.templates.select_by_name` | 分组模板弹窗打开 |
| 17 | `groupTemplateDialogOk` | `group_template.dialog.confirm` | 分组模板弹窗打开 |
| 18 | `groupTemplateDialogCancel` | `group_template.dialog.cancel` | 分组模板弹窗打开 |

## 6. 主窗口常驻注册的 13 个工具

这些工具最终能映射到 `MainFrm` 常驻注册函数。是否执行成功仍取决于当前是否有模型、参数是否正确、业务状态是否满足。

| 序号 | 工具 | 实际 C++ 语义函数 | 说明 |
|---:|---|---|---|
| 1 | `process_prt_file` | `main.prt.process` | 打开并处理模型；有副作用 |
| 2 | `open_prt_file` | `main.prt.open` | 打开模型；有副作用 |
| 3 | `get_all_bof_item` | `main.bof_tree.get` | 获取 BOF / 特征树；已验证成功 |
| 4 | `do_ai_process_route` | `main.ai_process_route.run_stage` | 执行 AI 工艺路线；有副作用 |
| 5 | `set_auto_featidentify_box` | `main.autoidentify.run` | 无弹窗自动识别；有副作用 |
| 6 | `get_bof_tree_data` | `main.bof_tree.get` | 获取 BOF / 特征树；已验证成功 |
| 7 | `get_ai_process_route_input` | `main.ai_process_route.run_stage` | 当前映射到 `do_ai_process_route`，语义需要复核 |
| 8 | `run_autoidentify_with_no_dlg` | `main.autoidentify.run` | 无弹窗自动识别；有副作用 |
| 9 | `click_group_template_button` | `main.command.click` | 点击主窗口按钮；有副作用 |
| 10 | `click_autoidentify_button` | `main.command.click` | 点击主窗口按钮；有副作用 |
| 11 | `click_processrapid_button` | `main.command.click` | 点击主窗口按钮；有副作用 |
| 12 | `click_generate_all_button` | `main.command.click` | 点击主窗口按钮；有副作用 |
| 13 | `click_one_click_generate_button` | `main.command.click` | 点击主窗口按钮；有副作用 |

## 7. 后端组合工具 / 操作型工具 6 个

这些不是简单的一次管道函数调用，而是 Python 后端组合多个步骤或直接触发主窗口按钮。

| 工具 | 状态 | 说明 |
|---|---|---|
| `auto_identify` | 有条件可用 | 后端会打开自动识别弹窗、读模板、选择模板并确认；会执行识别 |
| `ai_feature_inference` | 可触发操作 | 后端会触发主窗口自动推理按钮；有副作用 |
| `open_and_confirm_autoidentify_dialog` | 有条件可用 | 后端会打开并确认自动识别弹窗；有副作用 |
| `apply_group_template` | 有条件可用 | 后端会打开分组模板弹窗、选择模板并确认；有副作用 |
| `apply_group_template_full_flow` | 有条件可用 | 应用分组模板后继续自动识别和特征推理；强副作用 |
| `click_auto_reasoning_button` | 可触发操作 | 后端特殊处理为触发自动推理；有副作用 |

## 8. 最需要优先修复的工具

建议优先处理这些，因为它们容易被自然语言触发，且用户感知明显：

1. `check_3dmps_status`
   - 当前问题：主程序未注册。
   - 建议：不要走 3DMPS 管道函数，改成 Python 后端本地检查 `AGENT.pipe.is_available()` 或 `/api/health`。

2. `get_features`
   - 当前问题：主程序未注册。
   - 建议：Python 后端包装为调用 `get_all_bof_item`，再从 BOF 树里提取特征名称。

3. `get_autoidentify_template_list`
   - 当前问题：Python 映射名不对。
   - 建议：在 `TOOL_PIPE_TARGETS` 里映射到 `GetExtractDataList`。

4. `get_autoidentify_checkbox_list`
   - 当前问题：Python 映射名不对。
   - 建议：在 `TOOL_PIPE_TARGETS` 里映射到 `GetAutoIdentifyCheckedList`。

5. `get_cur_model_info`、`get_process_steps`、`get_rough_info`、`get_bop_tree`
   - 当前问题：Python 已声明，但 C++ 未注册。
   - 建议：如果短期不实现，先从工具列表移除或让 LLM 不要调用；如果要保留，需要在 `MainFrm` / `PythonBridge` 补注册。

## 9. 建议修复顺序

### 第一阶段：Python 端兼容修复

- `check_3dmps_status` 改成本地 health 检查。
- `get_features` 包装到 `get_all_bof_item`。
- `get_autoidentify_template_list` 映射到 `GetExtractDataList`。
- `get_autoidentify_checkbox_list` 映射到 `GetAutoIdentifyCheckedList`。
- 把未实现的查询/文件/工艺工具从 LLM 可见工具列表中临时隐藏，避免误调用。

### 第二阶段：C++ 主程序补注册

在以下位置补齐真正的 3DMPS 主程序函数：

```text
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.cpp
E:\MPS\3DMPS\src\KM3DMPS\MainFrm.h
E:\MPS\3DMPS\src\KM3DMPS\PythonBridge.cpp
```

建议优先补：

```text
get_cur_model_info
get_process_steps
get_rough_info
get_bop_tree
close_prt_file
save_file
save_as
export_pdf
export_excel
export_gxk
```

### 第三阶段：工具清单治理

- 将工具分为：已验证可用、需要弹窗、未实现、危险操作。
- 前端展示时给工具加状态标签。
- LLM 工具列表只暴露当前状态可用的工具，避免 AI 误选。

## 10. 2026-07-06 第一阶段 Python 端修复记录

已完成第一阶段快速修复，范围仅限 Python 后端，未修改 3DMPS C++ 主程序。

| 工具 | 修复后状态 | 说明 |
|---|---|---|
| `check_3dmps_status` | 已可用 | 改为 Python 后端本地检查 `AGENT.pipe.is_available()`，不再调用主程序未注册函数 |
| `get_features` | 已可用 | 改为内部调用 `get_all_bof_item`，再从 BOF / 特征树中提取特征名称 |
| `get_autoidentify_template_list` | 已修正映射 | 映射到 C++ 已支持的 `GetExtractDataList`；需要自动识别弹窗打开 |
| `get_autoidentify_checkbox_list` | 已修正映射 | 映射到 C++ 已支持的 `GetAutoIdentifyCheckedList`；需要自动识别弹窗打开 |
| 明确未实现的工具 | 已临时隐藏 | 从 LLM / 公共工具列表隐藏，避免 AI 继续误调用未注册函数 |

实际 HTTP 验证结果：

- `check_3dmps_status` 返回 `pipe_available: true`。
- `get_features` 已从当前 BOF 树提取到特征列表。
- `get_autoidentify_template_list` / `get_autoidentify_checkbox_list` 不再返回 `FUNCTION_NOT_FOUND`；在自动识别弹窗未打开时返回 `Target window not available: autoidentify_dialog`。
- `save_file` 等未实现工具当前返回 `TOOL_NOT_REGISTERED`，避免误触发。

验证命令：

```powershell
py -m unittest tests.test_tool_compatibility
py -m unittest discover -s tests
```

验证结果：

```text
Ran 4 tests in 0.055s - OK
Ran 29 tests in 0.156s - OK
```
