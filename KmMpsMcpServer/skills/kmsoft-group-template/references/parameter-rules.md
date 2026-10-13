# Part And Group Parameter Rules

Use this reference when deciding which fields to include or how Part-level choices affect Group-level fields.

## Conceptual Model

Part-level parameters define global machining context: coordinate origins, main directions, axis existence, and turning-related switches.

Group-level parameters reference that context to filter features: dependency direction, dependency mode, feature selection, axis filters, and process-order hints.

## Common Part Fields

- `原点`: Part coordinate origin or machining datum.
- `主方向1` to `主方向6`: Main machining direction vectors.
- `是否自动按坐标轴方向加工面积多少选择主方向1`: Whether the system chooses a main direction automatically.
- `是否需要加工面分离`: Whether complex or disconnected machining faces should be split before processing.
- `有主轴线`: Whether a rotary part has a central main axis.
- `有轴线`: Whether a part has an axis.
- `需要判断外圆车削加工方向`: Enables turning direction judgment for outer cylinders.
- `需要判断多外圆车削加工方向`: Enables turning direction judgment for multiple outer cylinders.

## Common Group Fields

- `依赖方向`: The direction anchor. Common values include `任意方向`, `从父`, `主方向1` to `主方向6`, `外圆加工方向`, `多外圆加工方向`, `六面方向`, `无可行方向`, `无可行加工方向`, and `未配置`.
- `依赖方式`: The geometric relationship to the dependency direction. Common values include `无`, `相同`, `相反`, `平行`, `平行且在同侧`, `平行且在反侧`, `垂直`, `不平行`, `接近`, `接近反向`, `相同或接近`, `相反或接近反向`, and `与坐标轴方向不平行`.
- `特征选择`: Feature type filter. Values must come from `assets/FeatureTemplate.xml`; multiple values use commas.
- `主轴线上特征`: Axis filter used when `有主轴线` is selected.
- `一般轴线上特征`: Axis filter used when `有轴线` is selected.
- `是否按用户规则排工序`: Whether the group participates in user-defined process ordering.

## Dependency Hints

- Top-level direction groups often use `依赖方向 = 主方向N` and `依赖方式 = 相同`.
- Child groups commonly use `依赖方向 = 从父`.
- When `有主轴线` is selected at Part level, include `主轴线上特征` in `Group_Template` if the template needs main-axis filtering.
- When `有轴线` is selected at Part level, include `一般轴线上特征` in `Group_Template` if the template needs general-axis filtering.
- Turning-oriented templates usually include fields related to `外圆加工方向` or `多外圆加工方向`.

## Defaulting Strategy

When the user does not specify a value:

- Use real sample templates as defaults when adapting from `assets/sample-templates/`.
- For new child groups, prefer `依赖方向 = 从父`.
- Leave `特征选择` empty if no dictionary match is confident.
- Ask a clarification question instead of inventing a feature token.

