#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const {
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
    '  node scripts/build_template.js [--draft draft.json|--input template.xml] [--out template.xml] [--encoding GB2312] [--write-encoding utf8|gb2312] [--json] [--validate]',
    '',
    'Builds Kmsoft XML from a draft JSON file, an existing XML template, or a new default draft.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const out = {
    draft: '',
    input: '',
    outFile: '',
    encoding: 'GB2312',
    writeEncoding: 'utf8',
    json: false,
    validate: false,
    featureFile: path.resolve(__dirname, '..', 'assets', 'FeatureTemplate.xml')
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--draft') out.draft = path.resolve(args[++i] || '');
    else if (arg === '--input') out.input = path.resolve(args[++i] || '');
    else if (arg === '--out') out.outFile = path.resolve(args[++i] || '');
    else if (arg === '--encoding') out.encoding = args[++i] || out.encoding;
    else if (arg === '--write-encoding') out.writeEncoding = args[++i] || out.writeEncoding;
    else if (arg === '--feature-file') out.featureFile = path.resolve(args[++i] || '');
    else if (arg === '--json') out.json = true;
    else if (arg === '--validate') out.validate = true;
    else if (arg === '--help') {
      console.log(usage());
      process.exit(0);
    }
  }

  return out;
}

function readDraft(args) {
  if (args.draft) return normalizeDraft(JSON.parse(fs.readFileSync(args.draft, 'utf8').replace(/^\uFEFF/, '')));
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

  try {
    const draft = readDraft(args);
    const xml = buildXml(draft, { encoding: args.encoding });
    let validation = null;

    if (args.validate) {
      const featureCatalog = parseFeatureCatalogFile(args.featureFile);
      validation = validateTemplate(parsedFromDraft(draft), featureCatalog);
    }

    const writeResult = args.outFile
      ? writeEncodedText(args.outFile, xml, args.writeEncoding)
      : null;

    if (args.json) {
      process.stdout.write(`${JSON.stringify({
        ok: validation ? validation.ok : true,
        outFile: args.outFile || undefined,
        writeEncoding: writeResult || undefined,
        validation,
        xml: args.outFile ? undefined : xml
      }, null, 2)}\n`);
    } else if (!args.outFile) {
      process.stdout.write(`${xml}\n`);
    }

    if (validation && !validation.ok) process.exit(1);
  } catch (err) {
    process.stderr.write(`${err && err.stack ? err.stack : err}\n`);
    process.exit(1);
  }
}

main();
