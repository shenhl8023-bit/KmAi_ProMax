---
name: process-route-generator
description: 根据 CAD/MPS 分组特征输入和人工补充参数，生成分组匹配后的工艺路线输出。
---

# 工艺路线生成技能

## 功能
这个技能用于把：

- `cad_input` 分组特征 JSON
- `manual` 人工补充参数

转换为：

- 标准路线
- 分组匹配路线
- 最终导出路线数组

## 当前主链路
1. `scripts/serve_demo.py`
2. `scripts/generate_route.py`
3. `scripts/generate_matched_route.py`

## 当前运行时依赖
- `references/v1/factor_schema.json`
- `references/v1/factor_expansion_rules.json`
- `references/v1/route_catalog.json`
- `references/v1/route_rules.json`
- `references/v1/group_match_rules.json`
- `references/cad_reference/cad_feature_catalog.json`

## 说明
- `demo/index.html` 用于本地测试
- `agents/openai.yaml` 用于技能注册
- 当前技能已经去掉旧版兼容参考文件，只保留通用 `v1` 协议
