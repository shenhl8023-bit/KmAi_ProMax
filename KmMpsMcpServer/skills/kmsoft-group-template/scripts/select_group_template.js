#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const {
  listXmlFiles,
  parseFeatureCatalogFile,
  parseTemplateFile,
  parsedTemplateToDraft,
  readText,
  validateTemplate,
  writeEncodedText,
  writeText
} = require('./template_core');

const DEFAULT_SAMPLE_DIR = path.resolve(__dirname, '..', 'assets', 'sample-templates');
const DEFAULT_FEATURE_FILE = path.resolve(__dirname, '..', 'assets', 'FeatureTemplate.xml');
const CHOICE_CONFIDENCE = 0.35;

const DOMAIN_SYNONYMS = new Map([
  ['衬套/套类/回转体', ['衬套', '轴套', '套类', '回转体', '轴类', '车削']],
  ['壳体/箱体', ['壳体', '箱体', '盒体', '多面', '六面', '加工面']],
  ['小件/简单件', ['小件', '简单件', '简单零件', '通用件']],
  ['活门/阀类', ['放油活门', '活门', '阀', '阀类']]
]);

const FEATURE_SYNONYMS = new Map([
  ['A侧', ['A侧', 'A面', 'A测', 'a侧', 'a面']],
  ['B侧', ['B侧', 'B面', 'B测', 'b侧', 'b面']],
  ['端面', ['端面', '轴端面']],
  ['外圆', ['外圆', '外圆柱面', '圆柱面']],
  ['孔', ['孔', '通孔', '盲孔', '直孔', '斜孔', '孔系', '内圆柱面']],
  ['槽', ['槽', '环槽', '外环槽', '内环槽', '凹槽', '通槽', '沟槽']],
  ['倒角倒圆', ['倒角', '倒圆', '倒圆倒角']]
]);

function usage() {
  return [
    'Usage:',
    '  node scripts/select_group_template.js propose --text "<零件描述>" [--limit 3]',
    '  node scripts/select_group_template.js confirm --template-id <id|filename|path> [--text "<零件描述>"] [--out-draft draft.json] [--out-xml template.xml]',
    '  node scripts/select_group_template.js --input request.json',
    '  cat request.json | node scripts/select_group_template.js --stdin',
    '',
    'Actions:',
    '  propose  Return workflow state and clickable group-template candidate cards.',
    '  confirm  Apply the selected template and return draft/XML/structure summary for the caller agent.',
    '',
    'JSON input examples:',
    '  { "action": "propose", "text": "衬套类回转体，A侧B侧，包含端面、外圆、孔", "limit": 3 }',
    '  { "action": "confirm", "templateId": "...", "outXml": "selected.xml", "writeEncoding": "gb2312" }'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const parsed = {
    action: '',
    text: '',
    templateId: '',
    samples: DEFAULT_SAMPLE_DIR,
    featureFile: DEFAULT_FEATURE_FILE,
    limit: 3,
    input: '',
    stdin: false,
    outDraft: '',
    outXml: '',
    writeEncoding: 'utf8',
    validate: false,
    browseAll: false,
    excludeTemplateIds: []
  };

  // 注意：process.argv.slice(2) 已经跳过了 node 和脚本路径，
  // 所以 args[0] 才是用户传入的第一个真正参数。
  let i = 0;

  // 可选位置参数：action 名（白名单校验，避免把某个 flag 的值误识别为 action）
  // 例：args = ['--input', '/path/to.json'] 时 args[0] 是 flag，不应被当成 action
  const KNOWN_ACTIONS = new Set(['propose', 'confirm', 'help']);
  if (args[i] && KNOWN_ACTIONS.has(args[i])) {
    parsed.action = args[i];
    i += 1;
  }

  for (; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--text') parsed.text = args[++i] || '';
    else if (arg === '--template-id') parsed.templateId = args[++i] || '';
    else if (arg === '--samples') parsed.samples = path.resolve(args[++i] || '');
    else if (arg === '--feature-file') parsed.featureFile = path.resolve(args[++i] || '');
    else if (arg === '--limit') parsed.limit = Number(args[++i]) || parsed.limit;
    else if (arg === '--input') parsed.input = path.resolve(args[++i] || '');
    else if (arg === '--stdin') parsed.stdin = true;
    else if (arg === '--out-draft') parsed.outDraft = path.resolve(args[++i] || '');
    else if (arg === '--out-xml') parsed.outXml = path.resolve(args[++i] || '');
    else if (arg === '--write-encoding') parsed.writeEncoding = args[++i] || parsed.writeEncoding;
    else if (arg === '--validate') parsed.validate = true;
    else if (arg === '--browse-all') parsed.browseAll = true;
    else if (arg === '--exclude-template-ids') {
      parsed.excludeTemplateIds = String(args[++i] || '').split(',').map((v) => v.trim()).filter(Boolean);
    }
    else if (arg === '--help') {
      console.log(usage());
      process.exit(0);
    }
  }

  if (parsed.input || parsed.stdin) {
    const raw = parsed.stdin
      ? fs.readFileSync(0, 'utf8')
      : fs.readFileSync(parsed.input, 'utf8');
    const input = JSON.parse(raw.replace(/^\uFEFF/, ''));
    return {
      ...parsed,
      ...input,
      action: input.action || parsed.action,
      templateId: input.templateId || input.template_id || parsed.templateId,
      samples: input.samples ? path.resolve(input.samples) : parsed.samples,
      featureFile: input.featureFile ? path.resolve(input.featureFile) : parsed.featureFile,
      outDraft: input.outDraft ? path.resolve(input.outDraft) : parsed.outDraft,
      outXml: input.outXml ? path.resolve(input.outXml) : parsed.outXml,
      browseAll: Boolean(input.browseAll || input.browse_all || parsed.browseAll),
      excludeTemplateIds: Array.isArray(input.excludeTemplateIds)
        ? input.excludeTemplateIds
        : (Array.isArray(input.exclude_template_ids) ? input.exclude_template_ids : parsed.excludeTemplateIds)
    };
  }

  return parsed;
}

function normalizeText(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, '');
}

function splitQueryTokens(text) {
  return normalizeText(text).split(/[，,。；;、|/\\\s]+/).filter(Boolean);
}

function expandQueryTerms(text) {
  const normalized = normalizeText(text);
  const terms = new Set(splitQueryTokens(text));

  for (const [label, values] of [...DOMAIN_SYNONYMS, ...FEATURE_SYNONYMS]) {
    if (values.some((value) => normalized.includes(normalizeText(value)))) {
      terms.add(normalizeText(label));
      for (const value of values) terms.add(normalizeText(value));
    }
  }

  return Array.from(terms).filter(Boolean);
}

function templateHaystack(item) {
  return normalizeText([
    item.filename,
    ...item.partTemplateFields,
    ...item.groupTemplateFields,
    ...item.groupNames,
    ...item.featureSelections,
    item.structureSummary
  ].join(' '));
}

function safeRelativeTemplatePath(item, samples) {
  const filename = String(item.filename || path.basename(item.sourcePath || '') || item.id || '');
  const relativePath = path.relative(samples, item.sourcePath || '').replace(/\\/g, '/');
  const segments = relativePath.split('/');
  if (!relativePath || path.isAbsolute(relativePath) || segments.includes('..')) return filename;
  return relativePath;
}

function publicTemplateItem(item, samples) {
  return {
    id: item.id,
    templateId: item.id,
    filename: item.filename,
    displayName: item.filename ? item.filename.replace(/\.xml$/i, '') : item.id,
    relativePath: safeRelativeTemplatePath(item, samples),
    groupCount: item.groupCount,
    depth: item.depth
  };
}

function publicTemplateTags(item) {
  return [...item.groupNames, ...item.featureSelections].slice(0, 6);
}

function publicTemplateCandidate(item, samples, ranking, browseAll) {
  const reasons = browseAll && !ranking.reasons.length
    ? ['模板库浏览候选']
    : ranking.reasons;
  return {
    ...publicTemplateItem(item, samples),
    tags: publicTemplateTags(item),
    confidence: ranking.confidence,
    reasons
  };
}

function scoreTemplate(text, item) {
  const normalizedText = normalizeText(text);
  const haystack = templateHaystack(item);
  let score = 0;
  const reasons = [];

  for (const [label, values] of DOMAIN_SYNONYMS) {
    const queryMatches = values.some((value) => normalizedText.includes(normalizeText(value)));
    const templateMatches = values.some((value) => haystack.includes(normalizeText(value)));
    if (queryMatches && templateMatches) {
      score += 0.38;
      reasons.push(`零件类型匹配：${label}`);
    }
  }

  for (const [label, values] of FEATURE_SYNONYMS) {
    const queryMatches = values.some((value) => normalizedText.includes(normalizeText(value)));
    const templateMatches = values.some((value) => haystack.includes(normalizeText(value)));
    if (queryMatches && templateMatches) {
      score += 0.08;
      reasons.push(`结构/特征匹配：${label}`);
    }
  }

  for (const term of expandQueryTerms(text)) {
    if (term.length < 2) continue;
    if (haystack.includes(term)) score += term.length >= 3 ? 0.03 : 0.015;
  }

  if (item.groupCount > 0) score += Math.min(item.groupCount, 30) / 500;
  if (item.featureSelections.length > 0) score += Math.min(item.featureSelections.length, 20) / 600;

  return {
    score,
    confidence: Math.max(0, Math.min(0.99, Number(score.toFixed(3)))),
    reasons: [...new Set(reasons)].slice(0, 8)
  };
}

function loadTemplates(samples) {
  return listXmlFiles(samples).map(parseTemplateFile);
}

function normalizeTemplateIdList(value) {
  if (!Array.isArray(value)) return new Set();
  return new Set(value.map((item) => String(item || '').trim()).filter(Boolean));
}

function rankTemplates({ text, samples }) {
  return loadTemplates(samples)
    .map((item) => ({
      template: item,
      ...scoreTemplate(text, item)
    }))
    .sort((a, b) => b.score - a.score
      || b.template.groupCount - a.template.groupCount
      || a.template.filename.localeCompare(b.template.filename, 'zh'));
}

function recommendTemplates({ text, samples, limit, browseAll = false, excludeTemplateIds = [] }) {
  const ranked = rankTemplates({ text, samples });
  const filtered = browseAll
    ? ranked
    : ranked.filter((item) => item.confidence >= CHOICE_CONFIDENCE);
  const excludeSet = normalizeTemplateIdList(excludeTemplateIds);
  const visible = filtered.filter((item) => !excludeSet.has(item.template.id));
  const resolvedLimit = Number(limit) || (browseAll ? 100 : 3);
  const candidates = visible
    .slice(0, resolvedLimit)
    .map((item) => publicTemplateCandidate(item.template, samples, item, browseAll));

  return {
    candidates,
    totalCount: ranked.length,
    matchingCount: filtered.length,
    browseAll,
    excludedCount: excludeSet.size
  };
}

function browseMeta(recommendation) {
  const mode = recommendation.browseAll ? 'all' : 'recommended';
  return {
    mode,
    available: !recommendation.browseAll && recommendation.totalCount > recommendation.candidates.length,
    total: recommendation.totalCount,
    matching: recommendation.matchingCount,
    shown: recommendation.candidates.length,
    excluded: recommendation.excludedCount,
    threshold: CHOICE_CONFIDENCE
  };
}

function workflow(status) {
  return {
    currentStep: 'select_group_template',
    steps: [
      {
        id: 'select_group_template',
        title: '选择分组模板',
        status
      }
    ]
  };
}

function optionCards(candidates, selectedTemplateId = '') {
  if (!candidates.length) return [];
  return [
    {
      type: 'option_cards',
      id: 'group_template_candidates',
      stage: 'select_group_template',
      title: '请选择分组模板',
      options: candidates.map((item) => ({
        id: item.id,
        choiceId: item.templateId,
        templateId: item.templateId,
        filename: item.filename,
        title: item.displayName,
        subtitle: item.filename,
        confidence: item.confidence,
        reasons: item.reasons,
        tags: item.tags,
        meta: {
          groupCount: item.groupCount,
          depth: item.depth,
          relativePath: item.relativePath
        },
        selected: selectedTemplateId === item.id
      }))
    }
  ];
}

function propose(args) {
  const text = String(args.text || '').trim();
  const browseAll = Boolean(args.browseAll || args.browse_all);
  if (!text) {
    return {
      ok: true,
      action: 'propose',
      stage: 'select_group_template',
      mode: 'needs_input',
      reply: '请先提供零件类型、加工侧和典型特征，用于选择分组模板。',
      workflow: workflow('needs_input'),
      browse: browseMeta({ browseAll, totalCount: 0, matchingCount: 0, candidates: [], excludedCount: 0 }),
      ui: [],
      candidates: []
    };
  }

  const recommendation = recommendTemplates({
    text,
    samples: args.samples,
    limit: args.limit,
    browseAll,
    excludeTemplateIds: args.excludeTemplateIds || args.exclude_template_ids || []
  });
  const candidates = recommendation.candidates;
  const hasCandidates = candidates.length > 0;
  return {
    ok: true,
    action: 'propose',
    stage: 'select_group_template',
    mode: hasCandidates ? 'awaiting_choice' : 'needs_input',
    queryText: text,
    browse: browseMeta(recommendation),
    reply: hasCandidates
      ? (browseAll ? '已列出其它分组模板，请让用户确认其中一个。' : '已找到可选分组模板，请让用户确认其中一个。')
      : '未找到足够匹配的分组模板，请补充零件类型、A/B侧信息或典型特征。',
    workflow: workflow(hasCandidates ? 'awaiting_choice' : 'needs_input'),
    ui: optionCards(candidates),
    candidates
  };
}

function findTemplate(args) {
  const target = String(args.templateId || '').trim();
  if (!target) throw new Error('confirm requires --template-id or templateId.');
  const templates = loadTemplates(args.samples);
  return templates.find((item) => {
    const relativePath = path.relative(args.samples, item.sourcePath || '').replace(/\\/g, '/');
    return item.id === target
      || item.filename === target
      || item.sourcePath === target
      || relativePath === target;
  }) || null;
}

function xmlWithDeclaredEncoding(xml, encoding) {
  const text = String(xml || '');
  const targetEncoding = String(encoding || 'GB2312');
  if (/^\s*<\?xml\b[^>]*encoding\s*=\s*(['"])[^'"]*\1[^>]*\?>/i.test(text)) {
    return text.replace(
      /^(\s*<\?xml\b[^>]*encoding\s*=\s*)(['"])[^'"]*\2([^>]*\?>)/i,
      `$1$2${targetEncoding}$2$3`
    );
  }
  if (/^\s*<\?xml\b[^>]*\?>/i.test(text)) {
    return text.replace(/^(\s*<\?xml\b[^>]*?)(\s*\?>)/i, (match, prefix, suffix) => {
      if (/encoding\s*=\s*(['"])/i.test(prefix)) return match;
      return `${prefix} encoding="${targetEncoding}"${suffix}`;
    });
  }
  return `<?xml version="1.0" encoding="${targetEncoding}" ?>\n${text}`;
}

function confirm(args) {
  const selected = findTemplate(args);
  if (!selected) {
    return {
      ok: false,
      action: 'confirm',
      stage: 'select_group_template',
      message: `未找到分组模板：${args.templateId}`
    };
  }

  const template = publicTemplateItem(selected, args.samples);
  const draft = parsedTemplateToDraft(selected);
  const sourceXml = selected.sourcePath ? readText(selected.sourcePath).text : '';
  const xml = xmlWithDeclaredEncoding(sourceXml, 'GB2312');
  const artifacts = {};
  let validation = null;

  if (args.validate) {
    const featureCatalog = parseFeatureCatalogFile(args.featureFile);
    validation = validateTemplate(selected, featureCatalog);
  }
  if (args.outDraft) {
    writeText(args.outDraft, `${JSON.stringify(draft, null, 2)}\n`);
    artifacts.draft = args.outDraft;
  }
  if (args.outXml) {
    artifacts.xml = {
      path: args.outXml,
      writeEncoding: writeEncodedText(args.outXml, xml, args.writeEncoding)
    };
  }

  const candidate = {
    ...template,
    tags: publicTemplateTags(selected),
    confidence: 1,
    reasons: ['用户已确认该分组模板']
  };

  return {
    ok: validation ? validation.ok : true,
    action: 'confirm',
    stage: 'select_group_template',
    mode: 'completed',
    reply: `已确认分组模板「${template.displayName}」。`,
    workflow: workflow('completed'),
    ui: optionCards([candidate], template.id),
    selectedTemplate: template,
    draft,
    xml,
    structureSummary: selected.structureSummary,
    validation,
    artifacts,
    handoff: {
      step: 'select_group_template',
      completed: true,
      selectedGroupTemplate: {
        id: template.id,
        displayName: template.displayName,
        filename: template.filename,
        relativePath: template.relativePath
      },
      draft,
      xml,
      structureSummary: selected.structureSummary
    }
  };
}

function main() {
  try {
    const args = parseArgs(process.argv);
    const action = String(args.action || (args.templateId ? 'confirm' : 'propose')).trim();
    if (!action || action === 'help') {
      console.log(usage());
      return;
    }

    const result = action === 'confirm' ? confirm(args) : propose(args);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    if (!result.ok) process.exit(1);
  } catch (err) {
    process.stderr.write(`${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
  }
}

main();
