# Selection Contract

This skill provides only the first MPS workflow step: `select_group_template`.

## Caller Responsibilities

- Own the full MPS agent conversation.
- Render option cards from `ui`.
- Collect the user's selected `templateId`.
- Call `confirm`.
- Continue later MPS steps outside this skill.

## Skill Responsibilities

- Rank sample group templates from a Chinese part description.
- Return clickable group-template options.
- Confirm the user's selected template.
- Return draft/XML/structure summary as a handoff payload.

## Propose Request

Schema: `schemas/propose.request.schema.json`

```json
{
  "action": "propose",
  "text": "衬套类回转体零件，A侧和B侧，包含端面、外圆、孔和外环槽",
  "limit": 3
}
```

## Propose Response

Schema: `schemas/propose.response.schema.json`

```json
{
  "ok": true,
  "stage": "select_group_template",
  "mode": "awaiting_choice",
  "workflow": {
    "currentStep": "select_group_template",
    "steps": [
      {
        "id": "select_group_template",
        "title": "选择分组模板",
        "status": "awaiting_choice"
      }
    ]
  },
  "ui": [
    {
      "type": "option_cards",
      "id": "group_template_candidates",
      "stage": "select_group_template",
      "title": "请选择分组模板",
      "options": [
        {
          "id": "961a209ede9b",
          "choiceId": "961a209ede9b",
          "templateId": "961a209ede9b",
          "filename": "新衬套模板.xml",
          "title": "新衬套模板",
          "subtitle": "新衬套模板.xml",
          "confidence": 0.95,
          "reasons": ["零件类型匹配：衬套/套类/回转体"],
          "tags": ["A测", "端面", "外圆", "外圆车", "外圆磨", "外环槽"],
          "meta": {
            "groupCount": 33,
            "depth": 4,
            "relativePath": "新衬套模板.xml"
          },
          "selected": false
        }
      ]
    }
  ],
  "candidates": [
    {
      "id": "961a209ede9b",
      "templateId": "961a209ede9b",
      "filename": "新衬套模板.xml",
      "displayName": "新衬套模板",
      "relativePath": "新衬套模板.xml",
      "groupCount": 33,
      "depth": 4,
      "tags": ["A测", "端面", "外圆", "外圆车", "外圆磨", "外环槽"],
      "confidence": 0.95,
      "reasons": ["零件类型匹配：衬套/套类/回转体"]
    }
  ]
}
```

Public candidate and selected-template metadata never includes an absolute `sourcePath`; callers select and confirm templates with the opaque `templateId`. Detailed draft/XML/tree data is returned only by `confirm`.

## Confirm Request

Schema: `schemas/confirm.request.schema.json`

```json
{
  "action": "confirm",
  "templateId": "template-id",
  "validate": true
}
```

## Confirm Response

Schema: `schemas/confirm.response.schema.json`

```json
{
  "ok": true,
  "stage": "select_group_template",
  "mode": "completed",
  "workflow": {
    "currentStep": "select_group_template",
    "steps": [
      {
        "id": "select_group_template",
        "title": "选择分组模板",
        "status": "completed"
      }
    ]
  },
  "selectedTemplate": {},
  "draft": {},
  "xml": "",
  "structureSummary": "",
  "handoff": {
    "step": "select_group_template",
    "completed": true,
    "selectedGroupTemplate": {},
    "draft": {},
    "xml": "",
    "structureSummary": ""
  }
}
```

## Invocation

Use `--input request.json` for file-based calls, or `--stdin` for direct JSON pipes:

```bash
cat request.json | node scripts/select_group_template.js --stdin
```
