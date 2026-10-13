# 技能导出说明

## 1. 当前建议导出的最小目录

```text
process-route-generator/
  SKILL.md
  README_EXPORT.md
  agents/
    openai.yaml
  demo/
    index.html
  scripts/
    serve_demo.py
    generate_route.py
    generate_matched_route.py
  references/
    cad_reference/
      cad_feature_catalog.json
    v1/
      factor_schema.json
      factor_expansion_rules.json
      route_catalog.json
      route_rules.json
      group_match_rules.json
```

## 2. 已经去掉的多余文件

这些文件不再属于当前技能运行必需文件：

- `references/factors.json`
- `references/route_catalog.json`
- `references/rules.json`
- `references/cad_reference/cad_method_tables.json`
- `references/cad_reference/cad_reference_summary.md`
- `scripts/extract_cad_reference.py`
- `scripts/__pycache__/`

## 3. 以后可以替换的文件

下面这些 JSON 是业务数据层，以后可以按同样格式直接替换：

- `references/v1/factor_schema.json`
  作用：因素定义
- `references/v1/factor_expansion_rules.json`
  作用：因素展开规则
- `references/v1/route_catalog.json`
  作用：全集母路线
- `references/v1/route_rules.json`
  作用：工序命中规则
- `references/v1/group_match_rules.json`
  作用：分组匹配规则
- `references/cad_reference/cad_feature_catalog.json`
  作用：CAD 特征规范表

### 从 ProcessMind 手工替换

ProcessMind 导出的规则包 ZIP 内包含 `kmai-v1/` 目录。停止 KmAI Agent 后，将其中以下四个文件复制到本目录的 `references/v1/` 并覆盖：

- `factor_schema.json`
- `factor_expansion_rules.json`
- `route_catalog.json`
- `route_rules.json`

保留当前 `group_match_rules.json` 和 `references/cad_reference/cad_feature_catalog.json`。重新启动 Agent 后，`process_route_generate` 会直接加载替换后的规则文件。

## 4. 不建议直接替换的文件

这些文件是程序逻辑层，除非要改算法，否则不要随意动：

- `scripts/generate_route.py`
- `scripts/generate_matched_route.py`
- `scripts/serve_demo.py`

## 5. 替换文件时的要求

1. 保持文件名不变。
2. 保持 JSON 顶层结构不变。
3. `route_catalog.json` 中的 `process_name`、`stage`、`sequence` 不能丢。
4. `group_match_rules.json` 里的 `step_name` 必须和母路线工步名可对上。
5. `cad_feature_catalog.json` 里的规范特征与子特征映射要保持一致风格。

## 6. 如果以后还想继续精简

如果不需要本地测试页面，可以再去掉：

- `demo/index.html`
- `scripts/serve_demo.py`

这样会变成纯算法包。
