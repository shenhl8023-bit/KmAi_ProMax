# Natural-Language Intent Operations

Use this reference when converting Chinese user instructions into draft/tree changes.

## Operation Shape

Represent edits as JSON operations before applying them:

```json
{
  "operations": [
    { "type": "select_part_fields", "fields": ["原点", "主方向1"] },
    { "type": "set_part_param", "field": "有主轴线", "value": "是" },
    { "type": "add_top_groups", "groups": ["A侧", "B侧"] },
    { "type": "add_children", "parents": ["A侧"], "children": ["外圆", "端面"] },
    { "type": "add_children_by_path", "parent_path": ["A侧", "端面"], "children": ["孔"] },
    { "type": "set_group_param", "group": "A侧", "field": "依赖方向", "value": "主方向1" },
    { "type": "set_group_features", "group": "外圆", "features": ["外圆柱面"] }
  ]
}
```

## Supported Operations

- `select_part_fields`: Ensure Part_Template contains the listed fields.
- `set_part_param`: Set one Part parameter value.
- `add_top_groups`: Add top-level Group nodes under Part.
- `add_children`: Add child Group nodes under one or more named parent groups.
- `add_children_by_path`: Add child Group nodes under a precise nested path.
- `set_group_param`: Set one Group parameter by group name.
- `set_group_features`: Set `特征选择` for a group using feature dictionary values.

`set_group_param` and `set_group_features` apply to all groups with the same `group` name. Use `group_path` for one precise node:

```json
{ "type": "set_group_features", "group_path": ["A侧", "端面"], "features": ["轴端面"] }
```

## CLI Usage

Create an operations JSON file:

```json
{
  "operations": [
    { "type": "add_top_groups", "groups": ["A侧", "B侧"] },
    { "type": "add_children", "parents": ["A侧", "B侧"], "children": ["端面", "外圆"] },
    { "type": "set_group_features", "group": "外圆", "features": ["外圆柱面"] }
  ]
}
```

Apply it from the project root:

```bash
npm run skill:apply -- --ops operations.json --out-draft draft.json --out-xml template.xml --validate
```

On Windows PowerShell environments that block `npm.ps1`, use `npm.cmd run ...`.

## Interpretation Rules

- If the instruction is uncertain, ask a clarification question instead of guessing operations.
- When the user says "也一样", "同理", or "同上", reuse the most recent applicable parent/group context.
- When the user says "A侧和B侧都...", apply the same operation to both targets.
- When the user says "在 A侧 端面 下添加孔", use `add_children_by_path` with `["A侧", "端面"]`.
- Do not interpret "设置成相同/相反" as mirrored structure; it usually means `依赖方式`.
- Only mirror/copy group structure when the user explicitly says "结构一样", "复制结构", or equivalent.
- Match features against `assets/FeatureTemplate.xml`. If no confident match exists, leave `特征选择` empty or ask.
