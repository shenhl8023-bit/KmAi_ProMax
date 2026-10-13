#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const {
  applyOperations,
  buildXml,
  createDefaultDraft,
  normalizeDraft,
  parseFeatureCatalogFile,
  parseTemplateFile,
  parsedTemplateToDraft,
  validateTemplate,
  writeEncodedText,
  writeText
} = require('./template_core');

function usage() {
  return [
    'Usage:',
    '  node scripts/apply_operations.js --ops operations.json [--input template.xml|--draft draft.json] [--out-draft draft.json] [--out-xml template.xml] [--encoding GB2312] [--write-encoding utf8|gb2312] [--validate]',
    '',
    'The operations file can be either an array or an object with an operations array.',
    'When no --input or --draft is provided, operations apply to a new default draft.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const out = {
    input: '',
    draft: '',
    ops: '',
    outDraft: '',
    outXml: '',
    validate: false,
    featureFile: path.resolve(__dirname, '..', 'assets', 'FeatureTemplate.xml'),
    encoding: 'GB2312',
    writeEncoding: 'utf8'
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--input') out.input = path.resolve(args[++i] || '');
    else if (arg === '--draft') out.draft = path.resolve(args[++i] || '');
    else if (arg === '--ops') out.ops = path.resolve(args[++i] || '');
    else if (arg === '--out-draft') out.outDraft = path.resolve(args[++i] || '');
    else if (arg === '--out-xml') out.outXml = path.resolve(args[++i] || '');
    else if (arg === '--feature-file') out.featureFile = path.resolve(args[++i] || '');
    else if (arg === '--encoding') out.encoding = args[++i] || out.encoding;
    else if (arg === '--write-encoding') out.writeEncoding = args[++i] || out.writeEncoding;
    else if (arg === '--validate') out.validate = true;
  }

  return out;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function readOperations(filePath) {
  const payload = readJson(filePath);
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.operations)) return payload.operations;
  throw new Error('Operations JSON must be an array or an object with an operations array.');
}

function readBaseDraft(args) {
  if (args.draft) return normalizeDraft(readJson(args.draft));
  if (args.input) return parsedTemplateToDraft(parseTemplateFile(args.input));
  return createDefaultDraft();
}

function parsedFromDraft(draft, sourcePath = '') {
  return {
    sourcePath,
    partTemplateFields: draft.partTemplateFields || [],
    groupTemplateFields: draft.groupTemplateFields || [],
    partParams: draft.partParams || {},
    groups: draft.groups || []
  };
}

function main() {
  const args = parseArgs(process.argv);
  if (!args.ops) {
    console.error(usage());
    process.exit(2);
  }

  try {
    const baseDraft = readBaseDraft(args);
    const operations = readOperations(args.ops);
    const result = applyOperations(baseDraft, operations);
    const xml = buildXml(result.draft, { encoding: args.encoding });

    let validation = null;
    if (args.validate) {
      const featureCatalog = parseFeatureCatalogFile(args.featureFile);
      validation = validateTemplate(parsedFromDraft(result.draft), featureCatalog);
    }

    if (args.outDraft) {
      writeText(args.outDraft, `${JSON.stringify(result.draft, null, 2)}\n`);
    }
    const writeXmlResult = args.outXml
      ? writeEncodedText(args.outXml, xml, args.writeEncoding)
      : null;

    process.stdout.write(`${JSON.stringify({
      ok: validation ? validation.ok : true,
      logs: result.logs,
      warnings: result.warnings,
      validation,
      draft: result.draft,
      xml: args.outXml ? undefined : xml,
      outDraft: args.outDraft || undefined,
      outXml: args.outXml || undefined,
      writeEncoding: writeXmlResult || undefined
    }, null, 2)}\n`);

    if (validation && !validation.ok) process.exit(1);
  } catch (err) {
    process.stderr.write(`${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
  }
}

main();
