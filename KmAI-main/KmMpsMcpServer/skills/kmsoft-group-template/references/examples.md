# Examples

Use these as compact behavior examples, not as a complete test suite.

## Create Top-Level Groups

User:

```text
创建 A侧 和 B侧 分组
```

Operations:

```json
[{ "type": "add_top_groups", "groups": ["A侧", "B侧"] }]
```

## Add The Same Children To Multiple Parents

User:

```text
在 A侧 添加外圆和端面两个子分组，B侧也一样
```

Operations:

```json
[{ "type": "add_children", "parents": ["A侧", "B侧"], "children": ["外圆", "端面"] }]
```

## Add A Nested Child

User:

```text
在 A侧 端面 下添加孔
```

Operations:

```json
[{ "type": "add_children_by_path", "parent_path": ["A侧", "端面"], "children": ["孔"] }]
```

## Set Dependency Mode

User:

```text
把外圆的依赖方式设置成相同
```

Operations:

```json
[{ "type": "set_group_param", "group": "外圆", "field": "依赖方式", "value": "相同" }]
```

## Set Feature Selection

User:

```text
外圆分组选择外圆柱面，端面分组选择轴端面
```

Operations:

```json
[
  { "type": "set_group_features", "group": "外圆", "features": ["外圆柱面"] },
  { "type": "set_group_features", "group": "端面", "features": ["轴端面"] }
]
```

