#!/usr/bin/env node

const path = require('node:path');
const {
  listXmlFiles,
  parseTemplateFile
} = require('./template_core');

function usage() {
  return [
    'Usage:',
    '  node scripts/parse_template.js <template.xml|directory> [--summary]',
    '',
    'Outputs JSON by default. Use --summary for a compact text summary.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const summary = args.includes('--summary');
  const target = args.find((arg) => !arg.startsWith('--'));
  return { target, summary };
}

function printSummary(items) {
  for (const item of items) {
    console.log(`File: ${item.sourcePath}`);
    console.log(`Encoding: detected=${item.detectedEncoding || ''} declared=${item.declaredEncoding || ''}`);
    console.log(`Part_Template fields (${item.partTemplateFields.length}): ${item.partTemplateFields.join(', ')}`);
    console.log(`Group_Template fields (${item.groupTemplateFields.length}): ${item.groupTemplateFields.join(', ')}`);
    console.log(`Groups: ${item.groupCount}; depth: ${item.depth}`);
    console.log('Structure:');
    console.log(item.structureSummary || '(no groups)');
    console.log('');
  }
}

function main() {
  const { target, summary } = parseArgs(process.argv);
  if (!target) {
    console.error(usage());
    process.exit(2);
  }

  const resolved = path.resolve(target);
  const files = listXmlFiles(resolved);
  if (!files.length) {
    console.error(`No XML files found: ${resolved}`);
    process.exit(1);
  }

  const parsed = files.map(parseTemplateFile);
  if (summary) {
    printSummary(parsed);
    return;
  }

  const payload = files.length === 1 ? parsed[0] : { templates: parsed };
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

main();

