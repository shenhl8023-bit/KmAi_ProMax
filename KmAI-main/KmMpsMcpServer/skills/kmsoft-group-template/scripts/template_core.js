const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const REQUIRED_GROUP_FIELDS = ['依赖方向', '依赖方式', '特征选择'];
const IMPLICIT_GROUP_FIELDS = ['名称'];
const DEFAULT_PART_FIELDS = ['主方向1', '原点'];
const DEFAULT_GROUP_FIELDS = ['依赖方向', '依赖方式', '特征选择'];
const DEPENDENCY_DIRECTIONS = [
  '任意方向',
  '从父',
  '主方向1',
  '主方向2',
  '主方向3',
  '主方向4',
  '主方向5',
  '主方向6',
  '外圆加工方向',
  '多外圆加工方向',
  '六面方向',
  '无可行方向',
  '无可行加工方向',
  '未配置'
];
const DEPENDENCY_MODES = [
  '无',
  '相同',
  '相反',
  '平行',
  '平行且在同侧',
  '平行且在反侧',
  '垂直',
  '不平行',
  '接近',
  '接近反向',
  '相同或接近',
  '相反或接近反向',
  '与坐标轴方向不平行'
];
const AXIS_FLAG_VALUES = ['无关', '是', '不是'];
const YES_NO_VALUES = ['是', '否', '不是'];

function decodeBuffer(buffer) {
  const utf8 = new TextDecoder('utf-8').decode(buffer);
  const replacementCount = (utf8.match(/\uFFFD/g) || []).length;
  if (replacementCount === 0 || replacementCount / Math.max(utf8.length, 1) < 0.001) {
    return { text: utf8, encoding: 'utf-8' };
  }

  for (const encoding of ['gb18030', 'gb2312', 'gbk']) {
    try {
      const text = new TextDecoder(encoding).decode(buffer);
      return { text, encoding };
    } catch {
      // Try the next legacy Chinese encoding.
    }
  }

  return { text: utf8, encoding: 'utf-8' };
}

function readText(filePath) {
  const buffer = fs.readFileSync(filePath);
  return decodeBuffer(buffer);
}

function writeText(filePath, text) {
  fs.mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  fs.writeFileSync(filePath, text, 'utf8');
}

function encodeGb2312WithIconv(text) {
  const result = spawnSync('iconv', ['-f', 'UTF-8', '-t', 'GB2312'], {
    input: Buffer.from(text, 'utf8'),
    maxBuffer: 16 * 1024 * 1024
  });
  if (result.status !== 0 || result.error) {
    const stderr = result.stderr ? Buffer.from(result.stderr).toString('utf8').trim() : '';
    return {
      ok: false,
      message: result.error ? result.error.message : stderr || 'iconv conversion failed'
    };
  }
  return { ok: true, buffer: result.stdout, method: 'iconv' };
}

function encodeGb2312WithPowerShell(text) {
  if (process.platform !== 'win32') {
    return { ok: false, message: 'PowerShell GB2312 fallback is only available on Windows' };
  }

  const tempDir = path.join(__dirname, '..', '..', '..', '.codex-runtime', 'skill-encoding');
  fs.mkdirSync(tempDir, { recursive: true });
  const tempId = `${Date.now()}_${crypto.randomBytes(6).toString('hex')}`;
  const inputPath = path.join(tempDir, `input_${tempId}.utf8.xml`);
  const outputPath = path.join(tempDir, `output_${tempId}.gb2312.bin`);
  fs.writeFileSync(inputPath, text, 'utf8');

  const script = `
$ErrorActionPreference = 'Stop'
$inputPath = ${JSON.stringify(inputPath)}
$outputPath = ${JSON.stringify(outputPath)}
try {
  $providerType = [System.Type]::GetType('System.Text.CodePagesEncodingProvider')
  if ($providerType) {
    [System.Text.Encoding]::RegisterProvider($providerType::Instance)
  }
} catch {}
$text = [System.IO.File]::ReadAllText($inputPath, [System.Text.Encoding]::UTF8)
$encoding = [System.Text.Encoding]::GetEncoding('GB2312')
[System.IO.File]::WriteAllBytes($outputPath, $encoding.GetBytes($text))
`;

  try {
    const encodedCommand = Buffer.from(script, 'utf16le').toString('base64');
    const result = spawnSync('powershell.exe', [
      '-NoProfile',
      '-NonInteractive',
      '-ExecutionPolicy',
      'Bypass',
      '-EncodedCommand',
      encodedCommand
    ], { maxBuffer: 16 * 1024 * 1024 });

    if (result.status !== 0 || result.error) {
      const stderr = result.stderr ? Buffer.from(result.stderr).toString('utf8').trim() : '';
      return {
        ok: false,
        message: result.error ? result.error.message : stderr || 'PowerShell conversion failed'
      };
    }

    return { ok: true, buffer: fs.readFileSync(outputPath), method: 'powershell' };
  } finally {
    for (const tempPath of [inputPath, outputPath]) {
      try {
        if (fs.existsSync(tempPath)) fs.unlinkSync(tempPath);
      } catch (_) {
        // Best-effort cleanup only.
      }
    }
  }
}

function encodeText(text, encoding = 'utf8') {
  const normalized = String(encoding || 'utf8').toLowerCase().replace(/[-_]/g, '');
  if (normalized === 'utf8') return { ok: true, buffer: Buffer.from(text, 'utf8'), method: 'utf8' };
  if (normalized === 'gb2312' || normalized === 'gbk' || normalized === 'gb18030') {
    const iconvResult = encodeGb2312WithIconv(text);
    if (iconvResult.ok) return iconvResult;
    const powershellResult = encodeGb2312WithPowerShell(text);
    if (powershellResult.ok) return powershellResult;
    return {
      ok: false,
      message: `GB2312 conversion failed: ${iconvResult.message}; ${powershellResult.message}`
    };
  }
  return { ok: false, message: `Unsupported output encoding: ${encoding}` };
}

function writeEncodedText(filePath, text, encoding = 'utf8') {
  const encoded = encodeText(text, encoding);
  if (!encoded.ok) throw new Error(encoded.message);
  fs.mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  fs.writeFileSync(filePath, encoded.buffer);
  return { encoding, method: encoded.method, bytes: encoded.buffer.length };
}

function listXmlFiles(targetPath) {
  if (!fs.existsSync(targetPath)) return [];
  const stat = fs.statSync(targetPath);
  if (stat.isFile()) return targetPath.toLowerCase().endsWith('.xml') ? [targetPath] : [];

  const out = [];
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    const full = path.join(targetPath, entry.name);
    if (entry.isDirectory()) out.push(...listXmlFiles(full));
    else if (entry.isFile() && entry.name.toLowerCase().endsWith('.xml')) out.push(full);
  }
  return out;
}

function xmlUnescape(value) {
  return String(value || '')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function xmlAttr(tag, name) {
  const re = new RegExp(`${name}\\s*=\\s*(['"])(.*?)\\1`);
  const m = re.exec(tag);
  return m ? xmlUnescape(m[2]) : '';
}

function extractFirstBlock(text, startRe) {
  const startMatch = startRe.exec(text);
  if (!startMatch) return '';
  const start = startMatch.index;
  const openEnd = text.indexOf('>', start);
  if (openEnd < 0) return '';

  let depth = 1;
  const tokenRe = /<Item\b[^>]*>|<\/Item>/g;
  tokenRe.lastIndex = openEnd + 1;
  let m;
  while ((m = tokenRe.exec(text))) {
    if (m[0].startsWith('</Item')) {
      depth -= 1;
      if (depth === 0) return text.slice(start, tokenRe.lastIndex);
    } else if (!m[0].endsWith('/>')) {
      depth += 1;
    }
  }
  return '';
}

function parseTemplateFields(xml, type) {
  const block = extractFirstBlock(xml, new RegExp(`<Item\\b[^>]*type=["']${type}["'][^>]*>`));
  const fields = [];
  const itemRe = /<Item\b([^>]*)\/>/g;
  let m;
  while ((m = itemRe.exec(block))) {
    const tag = m[0];
    const name = xmlAttr(tag, 'name').trim();
    if (name && !fields.includes(name)) fields.push(name);
  }
  return fields;
}

function parseParams(block) {
  const params = {};
  const paramsBlock = /<Params>([\s\S]*?)<\/Params>/.exec(block);
  if (!paramsBlock) return params;

  const paramRe = /<param\b([^>]*)\/>/g;
  let m;
  while ((m = paramRe.exec(paramsBlock[1]))) {
    const tag = m[0];
    const name = xmlAttr(tag, 'name').trim();
    if (!name) continue;
    params[name] = xmlAttr(tag, 'value');
  }
  return params;
}

function parseGroupItems(xml) {
  const groups = [];
  const stack = [];
  const tokenRe = /<Item\b[^>]*type=["']Group["'][^>]*>|<\/Item>/g;
  let m;
  let nextId = 1;

  while ((m = tokenRe.exec(xml))) {
    const token = m[0];
    if (token.startsWith('</Item')) {
      if (stack.length) stack.pop();
      continue;
    }

    const openEnd = tokenRe.lastIndex;
    const paramsStart = xml.indexOf('<Params>', openEnd);
    const paramsEnd = paramsStart >= 0 ? xml.indexOf('</Params>', paramsStart) : -1;
    const paramsBlock = paramsStart >= 0 && paramsEnd >= 0
      ? xml.slice(paramsStart, paramsEnd + '</Params>'.length)
      : '';
    const params = parseParams(paramsBlock);
    const name = params['名称'] || xmlAttr(token, 'name') || '未命名分组';
    const node = {
      id: `group-${nextId++}`,
      name,
      params: { 名称: name, ...params },
      children: []
    };

    if (stack.length) stack[stack.length - 1].children.push(node);
    else groups.push(node);
    stack.push(node);
  }

  return groups;
}

function collectGroupStats(groups) {
  const groupNames = [];
  const featureSelections = [];
  let groupCount = 0;
  let depth = 0;

  function walk(nodes, level) {
    depth = Math.max(depth, level);
    for (const node of nodes || []) {
      groupCount += 1;
      if (node.name && !groupNames.includes(node.name)) groupNames.push(node.name);

      const featureValue = node.params && node.params['特征选择'];
      if (featureValue) {
        for (const item of splitFeatureValue(featureValue)) {
          if (item && !featureSelections.includes(item)) featureSelections.push(item);
        }
      }

      walk(node.children || [], level + 1);
    }
  }

  walk(groups, 1);
  return { groupNames, featureSelections, groupCount, depth };
}

function buildGroupStructureText(groups, depth = 0) {
  const lines = [];
  for (const group of groups || []) {
    const prefix = '  '.repeat(depth);
    lines.push(`${prefix}- ${group.name}`);
    const children = buildGroupStructureText(group.children || [], depth + 1);
    if (children) lines.push(children);
  }
  return lines.join('\n');
}

function parseTemplateXmlText(xml, sourcePath = '') {
  const partTemplateFields = parseTemplateFields(xml, 'Part_Template');
  const groupTemplateFields = parseTemplateFields(xml, 'Group_Template');
  const partBlock = extractFirstBlock(xml, /<Item\b[^>]*type=["']Part["'][^>]*>/);
  const partParams = parseParams(partBlock);
  const groups = parseGroupItems(partBlock || xml);
  const stats = collectGroupStats(groups);
  const filename = sourcePath ? path.basename(sourcePath) : '';
  const idSource = sourcePath || xml.slice(0, 500);

  return {
    id: crypto.createHash('sha1').update(idSource).digest('hex').slice(0, 12),
    filename,
    sourcePath,
    partTemplateFields,
    groupTemplateFields,
    partParams,
    groups,
    groupNames: stats.groupNames,
    featureSelections: stats.featureSelections,
    groupCount: stats.groupCount,
    depth: stats.depth,
    structureSummary: buildGroupStructureText(groups)
  };
}

function createDefaultDraft() {
  return {
    partTemplateFields: [...DEFAULT_PART_FIELDS],
    groupTemplateFields: [...DEFAULT_GROUP_FIELDS],
    partParams: Object.fromEntries(DEFAULT_PART_FIELDS.map((field) => [field, ''])),
    groups: []
  };
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeDraft(input) {
  const base = createDefaultDraft();
  if (!input || typeof input !== 'object') return base;

  const draft = cloneJson(input);
  draft.partTemplateFields = Array.isArray(draft.partTemplateFields)
    ? uniqueStrings(draft.partTemplateFields)
    : base.partTemplateFields;
  draft.groupTemplateFields = Array.isArray(draft.groupTemplateFields)
    ? uniqueStrings(draft.groupTemplateFields)
    : base.groupTemplateFields;
  draft.partParams = draft.partParams && typeof draft.partParams === 'object'
    ? draft.partParams
    : {};
  draft.groups = Array.isArray(draft.groups)
    ? draft.groups
    : [];

  for (const field of draft.partTemplateFields) {
    if (!(field in draft.partParams)) draft.partParams[field] = '';
  }
  forEachGroup(draft.groups, (node) => normalizeGroupNode(node, draft.groupTemplateFields));
  return draft;
}

function parsedTemplateToDraft(parsed) {
  return normalizeDraft({
    partTemplateFields: parsed.partTemplateFields || [],
    groupTemplateFields: parsed.groupTemplateFields || [],
    partParams: parsed.partParams || {},
    groups: parsed.groups || []
  });
}

function normalizeGroupNode(node, groupTemplateFields) {
  node.name = String(node.name || (node.params && node.params['名称']) || '').trim();
  node.params = node.params && typeof node.params === 'object' ? node.params : {};
  if (node.name) node.params['名称'] = node.name;
  for (const field of groupTemplateFields || []) {
    if (!(field in node.params)) node.params[field] = defaultGroupFieldValue(field);
  }
  node.children = Array.isArray(node.children) ? node.children : [];
}

function uniqueStrings(values) {
  return [...new Set((Array.isArray(values) ? values : [])
    .map((value) => String(value || '').trim())
    .filter(Boolean))];
}

function forEachGroup(nodes, fn) {
  for (const node of nodes || []) {
    fn(node);
    forEachGroup(node.children || [], fn);
  }
}

function defaultGroupFieldValue(field) {
  if (field === '依赖方向') return '从父';
  if (field === '依赖方式') return '无';
  return '';
}

function createGroupNode(name, draft, featureNames = []) {
  const cleanName = String(name || '').trim();
  const params = { 名称: cleanName };
  for (const field of draft.groupTemplateFields || []) {
    params[field] = defaultGroupFieldValue(field);
  }
  if ((draft.groupTemplateFields || []).includes('特征选择') && featureNames.length) {
    params['特征选择'] = uniqueStrings(featureNames).join(',');
  }
  return {
    id: `group-${crypto.randomBytes(6).toString('hex')}`,
    name: cleanName,
    params,
    children: []
  };
}

function findGroupByName(nodes, name) {
  const target = String(name || '').trim();
  if (!target) return null;
  for (const node of nodes || []) {
    if (node.name === target) return node;
    const found = findGroupByName(node.children || [], target);
    if (found) return found;
  }
  return null;
}

function findGroupsByName(nodes, name, out = []) {
  const target = String(name || '').trim();
  if (!target) return out;
  for (const node of nodes || []) {
    if (node.name === target) out.push(node);
    findGroupsByName(node.children || [], target, out);
  }
  return out;
}

function findGroupByPath(nodes, pathParts) {
  const parts = uniqueStrings(pathParts);
  if (!parts.length) return null;
  let current = (nodes || []).find((node) => node.name === parts[0]) || null;
  for (const part of parts.slice(1)) {
    if (!current) return null;
    current = findChildByName(current, part);
  }
  return current;
}

function findChildByName(parent, name) {
  const target = String(name || '').trim();
  return (parent.children || []).find((child) => child.name === target) || null;
}

function ensureTopGroup(draft, name) {
  const cleanName = String(name || '').trim();
  if (!cleanName) return null;
  let node = (draft.groups || []).find((group) => group.name === cleanName);
  if (!node) {
    node = createGroupNode(cleanName, draft);
    draft.groups.push(node);
  }
  return node;
}

function ensureChildGroup(draft, parent, name, featureNames = []) {
  const cleanName = String(name || '').trim();
  if (!parent || !cleanName) return null;
  let node = findChildByName(parent, cleanName);
  if (!node) {
    node = createGroupNode(cleanName, draft, featureNames);
    parent.children.push(node);
  } else if (featureNames.length) {
    node.params['特征选择'] = uniqueStrings(featureNames).join(',');
  }
  return node;
}

function ensureGroupPath(draft, pathParts) {
  const parts = uniqueStrings(pathParts);
  if (!parts.length) return null;
  let current = ensureTopGroup(draft, parts[0]);
  for (const part of parts.slice(1)) {
    current = ensureChildGroup(draft, current, part);
  }
  return current;
}

function ensurePartField(draft, field) {
  const cleanField = String(field || '').trim();
  if (!cleanField) return false;
  if (!draft.partTemplateFields.includes(cleanField)) draft.partTemplateFields.push(cleanField);
  if (!(cleanField in draft.partParams)) draft.partParams[cleanField] = '';
  return true;
}

function ensureGroupField(draft, field) {
  const cleanField = String(field || '').trim();
  if (!cleanField) return false;
  if (!draft.groupTemplateFields.includes(cleanField)) draft.groupTemplateFields.push(cleanField);
  forEachGroup(draft.groups, (node) => {
    if (!(cleanField in node.params)) node.params[cleanField] = defaultGroupFieldValue(cleanField);
  });
  return true;
}

function applyOperations(inputDraft, operations) {
  const draft = normalizeDraft(inputDraft);
  const logs = [];
  const warnings = [];

  for (const op of Array.isArray(operations) ? operations : []) {
    if (!op || typeof op !== 'object') continue;
    switch (op.type) {
      case 'select_part_fields': {
        for (const field of uniqueStrings(op.fields)) {
          if (ensurePartField(draft, field)) logs.push(`selected Part field: ${field}`);
        }
        break;
      }
      case 'set_part_param': {
        const field = String(op.field || '').trim();
        if (!field) {
          warnings.push('set_part_param skipped: missing field');
          break;
        }
        ensurePartField(draft, field);
        draft.partParams[field] = String(op.value ?? '');
        logs.push(`set Part param ${field}`);
        break;
      }
      case 'add_top_groups': {
        for (const name of uniqueStrings(op.groups)) {
          ensureTopGroup(draft, name);
          logs.push(`ensured top group: ${name}`);
        }
        break;
      }
      case 'add_children': {
        const parents = uniqueStrings(op.parents);
        const children = uniqueStrings(op.children);
        if (!parents.length || !children.length) {
          warnings.push('add_children skipped: missing parents or children');
          break;
        }
        for (const parentName of parents) {
          const parent = findGroupByName(draft.groups, parentName) || ensureTopGroup(draft, parentName);
          for (const childName of children) {
            ensureChildGroup(draft, parent, childName);
            logs.push(`ensured child group: ${parentName}/${childName}`);
          }
        }
        break;
      }
      case 'add_children_by_path': {
        const pathParts = uniqueStrings(op.parent_path);
        const children = uniqueStrings(op.children);
        if (!pathParts.length || !children.length) {
          warnings.push('add_children_by_path skipped: missing parent_path or children');
          break;
        }
        const parent = ensureGroupPath(draft, pathParts);
        for (const childName of children) {
          ensureChildGroup(draft, parent, childName);
          logs.push(`ensured child group: ${pathParts.join('/')}/${childName}`);
        }
        break;
      }
      case 'set_group_param': {
        const groupName = String(op.group || '').trim();
        const field = String(op.field || '').trim();
        const groupPath = Array.isArray(op.group_path) ? uniqueStrings(op.group_path) : [];
        if ((!groupName && !groupPath.length) || !field) {
          warnings.push('set_group_param skipped: missing group/group_path or field');
          break;
        }
        ensureGroupField(draft, field);
        const targets = groupPath.length
          ? [findGroupByPath(draft.groups, groupPath)].filter(Boolean)
          : findGroupsByName(draft.groups, groupName);
        if (!targets.length) {
          warnings.push(`set_group_param skipped: group not found: ${groupPath.length ? groupPath.join('/') : groupName}`);
          break;
        }
        for (const group of targets) {
          group.params[field] = String(op.value ?? '');
          if (field === '名称') {
            group.name = group.params[field].trim();
          }
        }
        logs.push(`set Group param ${(groupPath.length ? groupPath.join('/') : groupName)}.${field} on ${targets.length} node(s)`);
        break;
      }
      case 'set_group_features': {
        const groupName = String(op.group || '').trim();
        const groupPath = Array.isArray(op.group_path) ? uniqueStrings(op.group_path) : [];
        const features = uniqueStrings(op.features);
        if (!groupName && !groupPath.length) {
          warnings.push('set_group_features skipped: missing group or group_path');
          break;
        }
        ensureGroupField(draft, '特征选择');
        const targets = groupPath.length
          ? [findGroupByPath(draft.groups, groupPath)].filter(Boolean)
          : findGroupsByName(draft.groups, groupName);
        if (!targets.length) {
          warnings.push(`set_group_features skipped: group not found: ${groupPath.length ? groupPath.join('/') : groupName}`);
          break;
        }
        for (const group of targets) {
          group.params['特征选择'] = features.join(',');
        }
        logs.push(`set Group features ${groupPath.length ? groupPath.join('/') : groupName} on ${targets.length} node(s)`);
        break;
      }
      default:
        warnings.push(`unsupported operation: ${op.type || '(missing type)'}`);
    }
  }

  forEachGroup(draft.groups, (node) => normalizeGroupNode(node, draft.groupTemplateFields));
  return { draft, logs, warnings };
}

function xmlEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function xmlUuid() {
  return crypto.randomBytes(16).toString('hex');
}

function buildFieldItem(name) {
  return `                <Item name="${xmlEscape(name)}" title="${xmlEscape(name)}" value="" data_type="" visible="1" edit="1" type="String" defaultval="" respath="" />`;
}

function buildGroupXml(nodes, indent = '        ') {
  const lines = [];
  for (const node of nodes || []) {
    const name = String(node.name || (node.params && node.params['名称']) || '').trim();
    const params = { 名称: name, ...(node.params || {}) };
    params['名称'] = name;

    lines.push(`${indent}<Item id="${xmlEscape(xmlUuid())}" type="Group" stageOrders="" sourceIds="">`);
    lines.push(`${indent}    <Params>`);
    for (const [key, value] of Object.entries(params)) {
      lines.push(`${indent}        <param name="${xmlEscape(key)}" value="${xmlEscape(value)}" />`);
    }
    lines.push(`${indent}    </Params>`);
    lines.push(...buildGroupXml(node.children || [], `${indent}    `));
    lines.push(`${indent}</Item>`);
  }
  return lines;
}

function buildXml(inputDraft, options = {}) {
  const draft = normalizeDraft(inputDraft);
  const encoding = options.encoding || 'GB2312';
  const lines = [];

  lines.push(`<?xml version="1.0" encoding="${xmlEscape(encoding)}" ?>`);
  lines.push('<Kmsoft>');
  lines.push('    <Item type="Part_Template">');
  lines.push('        <GridPropList>');
  lines.push('            <GridProp name="节点配置">');
  for (const field of draft.partTemplateFields) lines.push(buildFieldItem(field));
  lines.push('            </GridProp>');
  lines.push('        </GridPropList>');
  lines.push('    </Item>');
  lines.push('    <Item type="Group_Template">');
  lines.push('        <GridPropList>');
  lines.push('            <GridProp name="节点配置">');
  for (const field of draft.groupTemplateFields) lines.push(buildFieldItem(field));
  lines.push('            </GridProp>');
  lines.push('        </GridPropList>');
  lines.push('    </Item>');
  lines.push(`    <Item id="${xmlEscape(xmlUuid())}" type="Part" filename="" >`);
  lines.push('        <Params>');
  for (const field of draft.partTemplateFields) {
    lines.push(`            <param name="${xmlEscape(field)}" value="${xmlEscape(draft.partParams[field] || '')}" />`);
  }
  lines.push('        </Params>');
  lines.push(...buildGroupXml(draft.groups || [], '        '));
  lines.push('    </Item>');
  lines.push('</Kmsoft>');

  return lines.join('\n');
}

function parseTemplateFile(filePath) {
  const { text, encoding } = readText(filePath);
  return {
    ...parseTemplateXmlText(text, filePath),
    detectedEncoding: encoding,
    declaredEncoding: parseXmlDeclaredEncoding(text)
  };
}

function parseXmlDeclaredEncoding(xml) {
  const m = /<\?xml\b[^>]*encoding=["']([^"']+)["']/i.exec(xml);
  return m ? m[1] : '';
}

function parseFeatureCatalogXml(xml) {
  const root = [];
  const stack = [];
  const flat = new Set();
  const tokenRe = /<Item\b[^>]*\/>|<Item\b[^>]*>|<\/Item>/g;
  let m;

  while ((m = tokenRe.exec(xml))) {
    const token = m[0];
    if (token.startsWith('</Item')) {
      stack.pop();
      continue;
    }

    const name = xmlAttr(token, 'name').trim();
    if (!name) continue;
    flat.add(name);
    const node = { name, children: [] };
    if (stack.length) stack[stack.length - 1].children.push(node);
    else root.push(node);
    if (!token.endsWith('/>')) stack.push(node);
  }

  return { flat: Array.from(flat), tree: root };
}

function parseFeatureCatalogFile(filePath) {
  const { text, encoding } = readText(filePath);
  return {
    ...parseFeatureCatalogXml(text),
    sourcePath: filePath,
    detectedEncoding: encoding,
    declaredEncoding: parseXmlDeclaredEncoding(text)
  };
}

function splitFeatureValue(value) {
  return String(value || '')
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function findDuplicateValues(values) {
  const seen = new Set();
  const duplicates = new Set();
  for (const raw of Array.isArray(values) ? values : []) {
    const value = String(raw || '').trim();
    if (!value) continue;
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return Array.from(duplicates);
}

function pushIssue(list, code, message, pathLabel = '') {
  list.push({ code, path: pathLabel, message });
}

function validateTemplate(parsed, featureCatalog = null) {
  const errors = [];
  const warnings = [];
  const featureSet = featureCatalog && Array.isArray(featureCatalog.flat)
    ? new Set(featureCatalog.flat)
    : null;

  if (!parsed || typeof parsed !== 'object') {
    pushIssue(errors, 'invalid_input', 'Parsed template is missing or invalid.');
    return { ok: false, errors, warnings };
  }

  if (!parsed.partTemplateFields.length) {
    pushIssue(errors, 'missing_part_template_fields', 'Part_Template has no parsed fields.');
  }
  if (!parsed.groupTemplateFields.length) {
    pushIssue(errors, 'missing_group_template_fields', 'Group_Template has no parsed fields.');
  }

  for (const field of REQUIRED_GROUP_FIELDS) {
    if (!parsed.groupTemplateFields.includes(field)) {
      pushIssue(errors, 'missing_required_group_field', `Group_Template is missing required field: ${field}.`);
    }
  }

  for (const field of findDuplicateValues(parsed.partTemplateFields)) {
    pushIssue(errors, 'duplicate_part_template_field', `Part_Template field is duplicated: ${field}.`);
  }
  for (const field of findDuplicateValues(parsed.groupTemplateFields)) {
    pushIssue(errors, 'duplicate_group_template_field', `Group_Template field is duplicated: ${field}.`);
  }

  for (const field of Object.keys(parsed.partParams || {})) {
    if (!parsed.partTemplateFields.includes(field)) {
      pushIssue(errors, 'unknown_part_param', `Part param is not defined in Part_Template: ${field}.`);
    }
  }

  validateGroupNodes(parsed.groups || [], {
    groupTemplateFields: parsed.groupTemplateFields,
    featureSet,
    errors,
    warnings,
    parentPath: 'Part'
  });

  if (!parsed.groups || parsed.groups.length === 0) {
    pushIssue(warnings, 'no_groups', 'Part has no Group nodes.');
  }

  return { ok: errors.length === 0, errors, warnings };
}

function validateGroupNodes(nodes, context) {
  const {
    groupTemplateFields,
    featureSet,
    errors,
    warnings,
    parentPath
  } = context;
  const siblingNames = new Set();

  for (let index = 0; index < (nodes || []).length; index += 1) {
    const node = nodes[index];
    const name = String((node && node.name) || '').trim();
    const pathLabel = name ? `${parentPath}/${name}` : `${parentPath}/#${index + 1}`;

    if (!name) {
      pushIssue(errors, 'empty_group_name', 'Group name is empty.', pathLabel);
    } else if (siblingNames.has(name)) {
      pushIssue(errors, 'duplicate_sibling_group_name', `Sibling group name is duplicated: ${name}.`, parentPath);
    }
    if (name) siblingNames.add(name);

    const params = node && node.params && typeof node.params === 'object' ? node.params : {};
    for (const required of REQUIRED_GROUP_FIELDS) {
      if (groupTemplateFields.includes(required) && !(required in params)) {
        pushIssue(errors, 'missing_group_param', `Group is missing parameter: ${required}.`, pathLabel);
      }
    }

    for (const field of Object.keys(params)) {
      if (!groupTemplateFields.includes(field) && !IMPLICIT_GROUP_FIELDS.includes(field)) {
        pushIssue(errors, 'unknown_group_param', `Group param is not defined in Group_Template: ${field}.`, pathLabel);
      }
    }

    validateKnownEnum(params, '依赖方向', DEPENDENCY_DIRECTIONS, warnings, pathLabel);
    validateKnownEnum(params, '依赖方式', DEPENDENCY_MODES, warnings, pathLabel);
    validateKnownEnum(params, '主轴线上特征', AXIS_FLAG_VALUES, warnings, pathLabel);
    validateKnownEnum(params, '一般轴线上特征', AXIS_FLAG_VALUES, warnings, pathLabel);
    validateKnownEnum(params, '是否按用户规则排工序', YES_NO_VALUES, warnings, pathLabel);

    if ('特征选择' in params && featureSet) {
      for (const feature of splitFeatureValue(params['特征选择'])) {
        if (!featureSet.has(feature)) {
          pushIssue(errors, 'unknown_feature', `Feature selection is not in FeatureTemplate.xml: ${feature}.`, pathLabel);
        }
      }
    }

    validateGroupNodes(node.children || [], {
      ...context,
      parentPath: pathLabel
    });
  }
}

function validateKnownEnum(params, field, allowed, warnings, pathLabel) {
  if (!(field in params)) return;
  const value = String(params[field] || '').trim();
  if (!value) return;
  if (!allowed.includes(value)) {
    pushIssue(
      warnings,
      'unknown_enum_value',
      `Parameter ${field} has an unusual value: ${value}.`,
      pathLabel
    );
  }
}

module.exports = {
  REQUIRED_GROUP_FIELDS,
  createDefaultDraft,
  normalizeDraft,
  parsedTemplateToDraft,
  applyOperations,
  buildXml,
  readText,
  writeText,
  writeEncodedText,
  encodeText,
  listXmlFiles,
  parseTemplateFile,
  parseTemplateXmlText,
  parseFeatureCatalogFile,
  parseFeatureCatalogXml,
  buildGroupStructureText,
  validateTemplate
};
