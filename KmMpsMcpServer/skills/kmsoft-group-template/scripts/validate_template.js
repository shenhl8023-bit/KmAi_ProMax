#!/usr/bin/env node

const path = require('node:path');
const {
  listXmlFiles,
  parseFeatureCatalogFile,
  parseTemplateFile,
  validateTemplate
} = require('./template_core');

function usage() {
  return [
    'Usage:',
    '  node scripts/validate_template.js <template.xml|directory> [--feature-file path/to/FeatureTemplate.xml] [--text]',
    '',
    'Outputs JSON by default and exits with code 1 when blocking errors are found.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const text = args.includes('--text');
  let featureFile = path.resolve(__dirname, '..', 'assets', 'FeatureTemplate.xml');
  let target = '';

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--text') continue;
    if (arg === '--feature-file') {
      featureFile = path.resolve(args[i + 1] || '');
      i += 1;
      continue;
    }
    if (!arg.startsWith('--') && !target) target = arg;
  }

  return { target, featureFile, text };
}

function printText(results) {
  for (const result of results) {
    console.log(`${result.ok ? 'OK' : 'ERROR'} ${result.file}`);
    for (const issue of result.errors) {
      console.log(`  error ${issue.code}${issue.path ? ` ${issue.path}` : ''}: ${issue.message}`);
    }
    for (const issue of result.warnings) {
      console.log(`  warning ${issue.code}${issue.path ? ` ${issue.path}` : ''}: ${issue.message}`);
    }
    if (!result.errors.length && !result.warnings.length) {
      console.log('  no issues');
    }
  }
}

function main() {
  const { target, featureFile, text } = parseArgs(process.argv);
  if (!target) {
    console.error(usage());
    process.exit(2);
  }

  const featureCatalog = parseFeatureCatalogFile(featureFile);
  const files = listXmlFiles(path.resolve(target));
  if (!files.length) {
    console.error(`No XML files found: ${path.resolve(target)}`);
    process.exit(1);
  }

  const results = files.map((file) => {
    const parsed = parseTemplateFile(file);
    const validation = validateTemplate(parsed, featureCatalog);
    return {
      file,
      ok: validation.ok,
      errors: validation.errors,
      warnings: validation.warnings,
      summary: {
        partTemplateFieldCount: parsed.partTemplateFields.length,
        groupTemplateFieldCount: parsed.groupTemplateFields.length,
        groupCount: parsed.groupCount,
        depth: parsed.depth,
        detectedEncoding: parsed.detectedEncoding,
        declaredEncoding: parsed.declaredEncoding
      }
    };
  });

  const payload = {
    ok: results.every((result) => result.ok),
    featureFile,
    checkedCount: results.length,
    results
  };

  if (text) printText(results);
  else process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);

  if (!payload.ok) process.exit(1);
}

main();

