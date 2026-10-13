# Feature Dictionary

Use `assets/FeatureTemplate.xml` as the source of truth. This file is a compact human-readable snapshot for quick orientation.

## Current Feature Tree

- 六面
- 平面
- 轴端面
- 外圆柱面
- U形外环槽
- U形内环槽
- 各类孔特征
  - 孔
  - 孔(盲孔)
  - 孔(通孔)
  - 内圆柱面
  - 孔系
  - 同轴孔系
- 凹槽特征
  - 单纯底凹槽
  - 矩形底凹槽
  - 通槽
  - 同回转面下陷通槽
  - T形截面通槽
  - 切口
  - 沟槽
  - L形端面环槽
  - 侧壁
  - U形直槽
  - 台阶
  - 反向台阶
  - 矩形截面特种加工槽
- 倒圆倒角特征
  - 边倒角
  - 内倒角
  - 外倒角
  - 倒角
  - 倒圆
  - 回转面倒圆

## Rules

- Use exact dictionary values in `特征选择`.
- Multiple selected features are comma-separated.
- Placeholder UI text such as `请双击进行选择` is not a valid feature.
- When a user says "孔", prefer the dictionary value `孔` unless they specify blind hole or through hole.
- When a user says "端面", prefer `轴端面` if the context is a rotary/axis-oriented part.
- When a user says "外圆", prefer `外圆柱面`.

