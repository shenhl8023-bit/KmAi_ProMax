---
name: technical-requirements-generator
description: Generate technical requirements for an existing process route JSON from CAD input, optional manual context, or upstream part_context. Use when the route already exists and you need to append technical requirements without changing process order, process names, or process numbers.
---

# Technical Requirements Generator

补充已生成工艺路线的 `技术要求`。

## 作用

输入已有工艺路线，读取 CAD 输入和可选上下文，按规则仅补充每个工序的 `技术要求`。

## 何时使用

使用这个技能时，必须已经有工艺路线结果。适用场景：

- 已有 `route_input.json`，需要补技术要求
- 已有分组匹配后的工艺路线，需要生成最终完整 JSON
- 只有 `input.json` 和少量人工参数，需要生成带技术要求的路线

不要在这些场景使用：

- 还没有工艺路线
- 需要重新生成工艺路线顺序
- 需要修改工序名、工序号或工步结构

## 输入

必需输入：

- `route_input.json`

可选输入：

- `cad_input.json`
- `manual_context.json`
- `upstream_part_context.json`

优先级：

1. `upstream_part_context`
2. `manual_context`
3. `cad_input`

## 运行规则

1. 先读取工艺路线
2. 再构建 `part_context`
3. 按工序名匹配规则
4. 只新增或补充 `技术要求`
5. 不修改工艺路线结构

未知字段处理：

- 只允许输出已知且可确定的要求
- `required_context` 缺失且 `skip_if_unknown = true` 时，跳过该规则
- 不允许猜测

## 参考文件

固定参考：

- `references/process_name_aliases.json`

业务可替换：

- `references/technical_requirement_rules.json`
- `references/technical_requirement_templates.json`

可选样例：

- `assets/manual_context.example.json`

## 输出

输出保持原 JSON 结构，仅在工序内新增 `技术要求` 字段。

要求：

- 保持工序顺序不变
- 保持工序名称不变
- 保持工序编号不变
- 去重后保留首次出现顺序

## 推荐调用

```powershell
py .\scripts\generate_technical_requirements.py `
  --cad-input C:\path\to\input.json `
  --manual-context C:\path\to\manual_context.json `
  --route-input C:\path\to\route_input.json `
  --part-context-out C:\path\to\part_context.generated.json `
  --output C:\path\to\output_with_technical_requirements.json
```

如果上游已经提供标准化 `part_context`：

```powershell
py .\scripts\generate_technical_requirements.py `
  --upstream-part-context C:\path\to\part_context.json `
  --route-input C:\path\to\route_input.json `
  --output C:\path\to\output_with_technical_requirements.json
```

## 扩展顺序

需要新增规则时，优先按这个顺序改：

1. `references/technical_requirement_templates.json`
2. `references/technical_requirement_rules.json`
3. `scripts/generate_technical_requirements.py`

