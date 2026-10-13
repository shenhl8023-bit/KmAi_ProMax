#!/usr/bin/env node

const path = require('node:path');
const { parseFeatureCatalogFile } = require('./template_core');

function usage() {
  return [
    'Usage:',
    '  node scripts/list_features.js [FeatureTemplate.xml] [--tree|--flat]',
    '',
    'Defaults to assets/FeatureTemplate.xml and JSON output.'
  ].join('\n');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const tree = args.includes('--tree');
  const flat = args.includes('--flat');
  const target = args.find((arg) => !arg.startsWith('--')) ||
    path.resolve(__dirname, '..', 'assets', 'FeatureTemplate.xml');
  return { target: path.resolve(target), tree, flat };
}

function printTree(nodes, depth = 0) {
  for (const node of nodes || []) {
    console.log(`${'  '.repeat(depth)}- ${node.name}`);
    printTree(node.children || [], depth + 1);
  }
}

function main() {
  const { target, tree, flat } = parseArgs(process.argv);
  if (!target) {
    console.error(usage());
    process.exit(2);
  }

  const catalog = parseFeatureCatalogFile(target);
  if (tree) {
    printTree(catalog.tree);
    return;
  }
  if (flat) {
    for (const item of catalog.flat) console.log(item);
    return;
  }
  process.stdout.write(`${JSON.stringify(catalog, null, 2)}\n`);
}

main();

