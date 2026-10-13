# Kmsoft Group Template XML Structure

Use this reference when inspecting, generating, or validating 分组模板 XML.

## Required Shape

The root node is `<Kmsoft>`. It contains these logical sections:

1. `<Item type="Part_Template">`
   - Defines editable Part-level fields.
   - Fields usually appear as self-closing `GridProp/Item` elements with `name`, `title`, `type`, `defaultval`, `data_type`, and `respath` attributes.
2. `<Item type="Group_Template">`
   - Defines editable Group-level fields.
   - Common fields are `依赖方向`, `依赖方式`, and `特征选择`.
3. `<Item type="Part">`
   - Contains concrete Part parameter values in `<Params>`.
   - Contains the actual nested `Item type="Group"` tree.

## Instance Parameters

Part instance parameters use:

```xml
<Params>
  <param name="原点" value="" />
</Params>
```

Group instance parameters use the same shape. Each Group should have a logical name. In current project output, the group name is stored as:

```xml
<param name="名称" value="A侧" />
```

`名称` is an implicit Group instance field. It may be present even when it is not listed in `Group_Template`.

## Group Tree

Groups can nest recursively:

```text
Part
- Group: A侧
  - Group: 端面
    - Group: 孔
- Group: B侧
```

When a user says "在 A侧 端面 下添加孔", resolve the path as `["A侧", "端面"]`, not just `["A侧"]`.

## Validation Checklist

- Root contains `<Kmsoft>`.
- `Part_Template`, `Group_Template`, and `Part` exist.
- Template field names are non-empty and not duplicated.
- `Part.Params` names are defined by `Part_Template`.
- `Group.Params` names are defined by `Group_Template`, except implicit `名称`.
- Sibling group names are not duplicated.
- Group names are not empty.
- `特征选择` values come from `assets/FeatureTemplate.xml`.

## Encoding

Existing Kmsoft exports commonly declare:

```xml
<?xml version="1.0" encoding="GB2312" ?>
```

For final handoff to legacy Kmsoft consumers, write real GB2312 bytes rather than only changing the XML declaration. Use:

```bash
npm run skill:build -- --draft draft.json --out template.xml --write-encoding gb2312 --validate
```

Use UTF-8 output only for source control review or modern integration points that explicitly accept it.
