#!/usr/bin/env node

const path = require('node:path');
const {
  listXmlFiles,
  parseTemplateFile
} = require('./template_core');

const DEFAULT_SAMPLE_DIR = path.resolve(__dirname, '..', 'assets', 'sample-templates');

const DOMAIN_SYNONYMS = new Map([
  ['衬套', ['衬套', '回转体']],
  ['壳体', ['壳体', '箱体']],
  ['小件', ['小件', '车削']],
  ['放油活门', ['放油活门', '活门', '阀']]
]);

const FEATURE_SYNONYMS = new Map([
  ['A侧', ['A侧', 'A测', 'a侧', 'a测']],
  ['B侧', ['B侧', 'B测', 'b侧', 'b测']],
  ['端面', ['端面', '轴端面']],
  ['外圆', ['外圆', '外圆柱面']],
  ['孔', ['孔', '通孔', '盲孔', '内圆柱面', '孔系']],
  ['槽', ['槽', '凹槽', '通槽', '环槽', '沟槽']],
  ['倒角', ['倒角', '倒圆', '倒圆倒角']]
]);

function usage() {
  return [
    'Usage:',
    '  node scripts/recommend_template.js "<Chinese description>" [--samples assets/sample-templates] [--limit 5]',
    '',
    'Outputs ranked sample-template candidates as JSON.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  let text = '';
  let samples = DEFAULT_SAMPLE_DIR;
  let limit = 5;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--samples') {
      samples = path.resolve(args[i + 1] || '');
      i += 1;
      continue;
    }
    if (arg === '--limit') {
      limit = Number(args[i + 1]) || limit;
      i += 1;
      continue;
    }
    if (!arg.startsWith('--') && !text) text = arg;
  }

  return { text: text.trim(), samples, limit };
}

function normalizeText(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, '');
}

function expandQueryTerms(text) {
  const normalized = normalizeText(text);
  const terms = new Set();

  for (const char of normalized) {
    if (/[\u4e00-\u9fffA-Za-z0-9]/.test(char)) terms.add(char);
  }

  for (const [key, values] of [...DOMAIN_SYNONYMS, ...FEATURE_SYNONYMS]) {
    if (values.some((value) => normalized.includes(normalizeText(value)))) {
      terms.add(normalizeText(key));
      for (const value of values) terms.add(normalizeText(value));
    }
  }

  for (const token of normalized.split(/[，,。；;、\s]+/).filter(Boolean)) {
    terms.add(token);
  }

  return Array.from(terms).filter((term) => term.length > 0);
}

function haystackForTemplate(item) {
  return normalizeText([
    item.filename,
    ...item.partTemplateFields,
    ...item.groupTemplateFields,
    ...item.groupNames,
    ...item.featureSelections
  ].join(' '));
}

function scoreTemplate(text, item) {
  const terms = expandQueryTerms(text);
  const haystack = haystackForTemplate(item);
  let score = 0;
  const reasons = [];

  for (const term of terms) {
    if (term.length < 2) continue;
    if (haystack.includes(term)) {
      const weight = term.length >= 3 ? 0.12 : 0.07;
      score += weight;
      if (reasons.length < 8) reasons.push(`matched "${term}"`);
    }
  }

  const name = normalizeText(item.filename);
  for (const [key, values] of DOMAIN_SYNONYMS.entries()) {
    const queryMatches = values.some((value) => normalizeText(text).includes(normalizeText(value)));
    const fileMatches = values.some((value) => name.includes(normalizeText(value)));
    if (queryMatches && fileMatches) {
      score += 0.4;
      reasons.unshift(`filename/domain match: ${key}`);
    }
  }

  for (const [key, values] of FEATURE_SYNONYMS.entries()) {
    const queryMatches = values.some((value) => normalizeText(text).includes(normalizeText(value)));
    const templateMatches = values.some((value) => haystack.includes(normalizeText(value)));
    if (queryMatches && templateMatches) {
      score += 0.08;
      if (reasons.length < 8) reasons.push(`feature match: ${key}`);
    }
  }

  if (item.groupCount > 0) score += Math.min(item.groupCount, 40) / 400;
  if (item.featureSelections.length > 0) score += Math.min(item.featureSelections.length, 20) / 300;

  return {
    score,
    confidence: Math.max(0, Math.min(0.99, Number(score.toFixed(3)))),
    reasons: [...new Set(reasons)].slice(0, 10)
  };
}

function publicTemplateItem(item) {
  return {
    id: item.id,
    filename: item.filename,
    sourcePath: item.sourcePath,
    partTemplateFields: item.partTemplateFields,
    groupTemplateFields: item.groupTemplateFields,
    groupNames: item.groupNames,
    featureSelections: item.featureSelections,
    groupCount: item.groupCount,
    depth: item.depth,
    structureSummary: item.structureSummary
  };
}

function main() {
  const { text, samples, limit } = parseArgs(process.argv);
  if (!text) {
    console.error(usage());
    process.exit(2);
  }

  const files = listXmlFiles(samples);
  const recommendations = files
    .map(parseTemplateFile)
    .map((item) => ({
      ...publicTemplateItem(item),
      ...scoreTemplate(text, item)
    }))
    .filter((item) => item.confidence > 0)
    .sort((a, b) => b.score - a.score || b.groupCount - a.groupCount)
    .slice(0, limit);

  process.stdout.write(`${JSON.stringify({
    ok: true,
    text,
    samples,
    recommendations
  }, null, 2)}\n`);
}

main();
