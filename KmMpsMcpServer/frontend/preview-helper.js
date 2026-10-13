// preview-helper.js —— 给 preview_edit.html 用的本地辅助。
// 复刻 modules/tool_call.js 里 buildOptionCardEl 的 innerHTML 部分 + 事件绑定。
// 卡片编辑弹窗里复刻新的「可交互分组结构树」演示版。

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getOptionCardActionText(applied, groupTemplateOnly) {
  if (groupTemplateOnly) {
    return applied ? '已完成加载' : '写入模板库并加载';
  }
  return applied ? '已完成串联' : '写入应用并识别推理';
}

function normalizeTemplateFilenameInput(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) return '';
  if (trimmed.toLowerCase().endsWith('.xml')) return trimmed;
  return trimmed + '.xml';
}

function deriveDisplayNameFromFilename(filename) {
  const normalized = String(filename || '').trim();
  if (!normalized) return '';
  return normalized.replace(/\.xml$/i, '');
}

function resetOptionCardForTemplateEdit(card, groupTemplateOnly) {
  if (!card) return;
  card.classList.remove('is-selected');
  const button = card.querySelector('[data-action="apply-card"]');
  if (button) {
    button.disabled = false;
    button.textContent = getOptionCardActionText(false, groupTemplateOnly);
  }
}

// 与正式卡片共用相同展示规则，保留数值 0 并忽略真正缺失的字段。
function formatOptionCardMeta(meta) {
  const source = meta || {};
  const parts = [];
  if (source.groupCount !== undefined && source.groupCount !== null && source.groupCount !== '') {
    parts.push(String(source.groupCount) + ' 组');
  }
  if (source.depth !== undefined && source.depth !== null && source.depth !== '') {
    parts.push(String(source.depth) + ' 层');
  }
  return parts.length ? '结构：' + parts.join(' / ') : '';
}

export function buildOptionCardHtml(opt, ui) {
  const conf = Number(opt.confidence || 0);
  const confPct = (conf * 100).toFixed(1);
  const confCls = conf >= 0.7 ? 'high' : (conf >= 0.4 ? 'mid' : 'low');
  const fullStars = Math.round(conf * 5);
  const stars = '★'.repeat(fullStars) + '☆'.repeat(5 - fullStars);

  const rawFilename = opt.filename || opt.subtitle || '';
  const rawTitle = rawFilename ? deriveDisplayNameFromFilename(rawFilename) : (opt.title || opt.templateId || '(未命名)');
  const title = escapeHtml(rawTitle);
  const subtitle = escapeHtml(rawFilename);
  const reasons = (opt.reasons || []).slice(0, 3)
    .map(r => '<span class="card-reason">' + escapeHtml(r) + '</span>').join('');
  const tags = (opt.tags || []).slice(0, 6)
    .map(t => '<span class="card-tag">' + escapeHtml(t) + '</span>').join('');
  const metaText = formatOptionCardMeta(opt.meta);

  return '<div class="option-card"' +
    (ui && ui.groupTemplateOnly ? ' data-group-template-only="1"' : '') +
    ' data-template-id="' + (opt.templateId || opt.id || '') + '">' +
    '<div class="option-card-head">' +
      '<span class="option-card-title" title="' + title + '">' + title + '</span>' +
      '<span class="option-card-confidence ' + confCls + '">' + confPct + '%</span>' +
    '</div>' +
    '<button class="option-card-icon-btn" type="button" data-action="edit-card" title="编辑该模板卡片">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>' +
    '</button>' +
    (subtitle ? '<div class="option-card-subtitle" title="' + subtitle + '">' + subtitle + '</div>' : '') +
    '<div class="option-card-stars">' + stars + '</div>' +
    (reasons ? '<div class="option-card-reasons">' + reasons + '</div>' : '') +
    (tags ? '<div class="option-card-tags">' + tags + '</div>' : '') +
    '<div class="option-card-footer">' +
      (metaText ? '<div class="option-card-meta" title="' + escapeHtml(metaText) + '">' + escapeHtml(metaText) + '</div>' : '') +
      '<div class="option-card-actions">' +
        '<button class="option-card-button" type="button" data-action="apply-card">' + getOptionCardActionText(false, ui && ui.groupTemplateOnly) + '</button>' +
      '</div>' +
    '</div>' +
  '</div>';
}

// =========================================================
// 演示用:卡片编辑弹窗 —— 与生产版同款,但用内置假数据演示交互树
// =========================================================

const ENUM_FIELDS = {
  '依赖方向': ['任意方向', '从父', '主方向1', '主方向2', '主方向3', '主方向4', '主方向5', '主方向6', '外圆加工方向', '多外圆加工方向', '六面方向', '无可行方向', '无可行加工方向', '未配置'],
  '依赖方式': ['无', '相同', '相反', '平行', '平行且在同侧', '平行且在反侧', '垂直', '不平行', '接近', '接近反向', '相同或接近', '相反或接近反向', '与坐标轴方向不平行'],
  '主轴线上特征': ['无关', '是', '不是'],
  '一般轴线上特征': ['无关', '是', '不是'],
  '是否按用户规则排工序': ['是', '否', '不是']
};
const FEATURE_PARAM_KEY = '特征选择';
const SUGGESTED_PARAM_KEYS = ['依赖方向', '依赖方式', FEATURE_PARAM_KEY, '主轴线上特征', '一般轴线上特征', '是否按用户规则排工序', '工序说明'];
const DEMO_FEATURE_CATALOG = {
  tree: [
    { name: '六面', children: [] },
    { name: '平面', children: [] },
    { name: '轴端面', children: [] },
    { name: '外圆柱面', children: [] },
    {
      name: '各类孔特征',
      children: [
        { name: '孔', children: [] },
        { name: '孔(盲孔)', children: [] },
        { name: '孔(通孔)', children: [] },
        { name: '内圆柱面', children: [] },
        { name: '孔系', children: [] },
        { name: '同轴孔系', children: [] }
      ]
    },
    {
      name: '凹槽特征',
      children: [
        { name: '单纯底凹槽', children: [] },
        { name: '矩形底凹槽', children: [] },
        { name: '通槽', children: [] }
      ]
    }
  ],
  leafNames: ['六面', '平面', '轴端面', '外圆柱面', '孔', '孔(盲孔)', '孔(通孔)', '内圆柱面', '孔系', '同轴孔系', '单纯底凹槽', '矩形底凹槽', '通槽']
};

let _id = 0;
const nextId = () => 'tn-' + (++_id);

// 假数据(为预览准备的有代表性的分组树)
function makeDemoTree(meta) {
  const sub = (name, params, children) => ({
    id: nextId(), name, isRoot: false, params, children: children || []
  });
  return {
    id: nextId(),
    name: 'Part',
    isRoot: true,
    params: [],
    children: [
      sub('中间通孔', [
        { k: '依赖方向', v: '从父' },
        { k: '依赖方式', v: '无' },
        { k: '特征选择', v: 'A侧,端面,外圆' }
      ], [
        sub('A侧', [{ k: '依赖方向', v: '主方向1' }, { k: '依赖方式', v: '相同' }]),
        sub('端面', [{ k: '依赖方向', v: '主方向2' }, { k: '依赖方式', v: '垂直' }]),
        sub('外圆', [{ k: '依赖方向', v: '主方向3' }, { k: '依赖方式', v: '平行' }])
      ]),
      sub('外环槽', [
        { k: '依赖方向', v: '从父' },
        { k: '依赖方式', v: '无' }
      ], [
        sub('B侧', [{ k: '依赖方向', v: '主方向4' }, { k: '依赖方式', v: '相同' }]),
        sub('孔', [{ k: '依赖方向', v: '主方向5' }, { k: '依赖方式', v: '平行且在同侧' }])
      ]),
      sub('工艺组', [
        { k: '是否按用户规则排工序', v: '是' }
      ], [
        sub('粗车', [{ k: '工序说明', v: '粗车外圆' }]),
        sub('精车', [{ k: '工序说明', v: '精车端面' }])
      ])
    ]
  };
}

function countDesc(node) {
  let n = 0;
  for (const c of node.children || []) n += 1 + countDesc(c);
  return n;
}

function demoCollapsedStore(ctx) {
  if (!ctx) return null;
  if (!ctx._collapsedNodes) ctx._collapsedNodes = new Map();
  return ctx._collapsedNodes;
}

function demoDefaultNodeCollapsed(node, depth, ctx) {
  const defaultDepth = (ctx && typeof ctx.defaultCollapsedDepth === 'number') ? ctx.defaultCollapsedDepth : 99;
  return Boolean(node && !node.isRoot && defaultDepth < 99 && depth >= defaultDepth);
}

function demoResolveNodeCollapsed(node, depth, ctx) {
  const store = ctx && ctx._collapsedNodes;
  const key = node && node.id ? String(node.id) : '';
  if (store && key && store.has(key)) return Boolean(store.get(key));
  return demoDefaultNodeCollapsed(node, depth, ctx);
}

function demoSetNodeCollapsed(ctx, node, collapsed) {
  if (!node || !node.id || node.isRoot) return;
  if (!demoCollapsedStore(ctx)) return;
  ctx._collapsedNodes.set(String(node.id), Boolean(collapsed));
}

function demoSetAllNodeCollapsed(ctx, node, collapsed) {
  if (!node) return;
  demoSetNodeCollapsed(ctx, node, collapsed);
  (node.children || []).forEach((child) => demoSetAllNodeCollapsed(ctx, child, collapsed));
}

function demoSetRootChildrenCollapsed(ctx, tree, collapsed) {
  if (!tree || !tree.children) return;
  tree.children.forEach((child) => demoSetNodeCollapsed(ctx, child, collapsed));
}

function paramChipClass(k) {
  if (k === '依赖方向') return ' chip-dir';
  if (k === '依赖方式') return ' chip-mode';
  if (k === FEATURE_PARAM_KEY) return ' chip-feat';
  return '';
}

function makeToolBtn(kind, label, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'edit-tree-row-tool edit-tree-row-tool-' + kind;
  b.textContent = label;
  b.addEventListener('click', function(ev) {
    ev.preventDefault(); ev.stopPropagation(); onClick(ev);
  });
  return b;
}

function findNode(tree, path) {
  let node = tree;
  for (const idx of path) {
    if (!node || !node.children[idx]) return null;
    node = node.children[idx];
  }
  return node;
}
function addChild(tree, path) {
  const p = findNode(tree, path); if (!p) return;
  p.children.push({ id: nextId(), name: '新分组', isRoot: false, params: [{ k: '依赖方向', v: '从父' }, { k: '依赖方式', v: '无' }], children: [] });
}
function delNode(tree, path) {
  if (!path.length) return;
  const p = findNode(tree, path.slice(0, -1)); if (!p) return;
  p.children.splice(path[path.length - 1], 1);
}
function setParam(tree, path, k, v) {
  const n = findNode(tree, path); if (!n) return;
  const e = n.params.find((p) => p.k === k);
  if (e) e.v = v; else n.params.push({ k, v: v || '' });
}
function delParam(tree, path, k) {
  const n = findNode(tree, path); if (!n) return;
  const i = n.params.findIndex((p) => p.k === k);
  if (i >= 0) n.params.splice(i, 1);
}
function rename(tree, path, newName) {
  const n = findNode(tree, path); if (!n) return;
  n.name = String(newName || '').trim() || '未命名';
}
function setParamValue(tree, path, k, v) {
  const n = findNode(tree, path); if (!n) return;
  const e = n.params.find((p) => p.k === k);
  if (e) e.v = v;
}

function moveNode(tree, sourcePath, targetParentPath, targetIndex) {
  if (!Array.isArray(sourcePath) || sourcePath.length === 0) return false;
  const sourceParent = findNode(tree, sourcePath.slice(0, -1));
  if (!sourceParent) return false;
  const targetParent = findNode(tree, targetParentPath);
  if (!targetParent) return false;
  const sourceIdx = sourcePath[sourcePath.length - 1];
  if (sourceIdx < 0 || sourceIdx >= sourceParent.children.length) return false;
  const [moved] = sourceParent.children.splice(sourceIdx, 1);
  let insertAt = targetIndex;
  if (sourceParent === targetParent && sourceIdx < targetIndex) insertAt -= 1;
  if (insertAt < 0) insertAt = 0;
  if (insertAt > targetParent.children.length) insertAt = targetParent.children.length;
  targetParent.children.splice(insertAt, 0, moved);
  return true;
}

function arraysEqualPath(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function clearDropIndicators(ctx) {
  const root = (ctx && ctx._ownerContainer) || document;
  root.querySelectorAll('.edit-tree-row.drop-before, .edit-tree-row.drop-after').forEach((el) => {
    el.classList.remove('drop-before', 'drop-after');
  });
}

function handleDragMove(ev, state, ctx) {
  if (!state) return;
  const dx = ev.clientX - state.startX;
  const dy = ev.clientY - state.startY;
  if (!state.started) {
    if (Math.abs(dx) < state.threshold && Math.abs(dy) < state.threshold) return;
    state.started = true;
    state.sourceHead.classList.add('is-dragging');
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
    const rect = state.sourceHead.getBoundingClientRect();
    const clone = state.sourceHead.cloneNode(true);
    clone.classList.add('edit-tree-drag-clone');
    clone.style.position = 'fixed';
    clone.style.left = rect.left + 'px';
    clone.style.top = rect.top + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.maxWidth = rect.width + 'px';
    clone.style.background = 'var(--color-surface)';
    clone.style.boxShadow = '0 12px 32px rgba(15, 23, 42, 0.25)';
    clone.style.borderRadius = '10px';
    clone.style.opacity = '0.95';
    clone.style.padding = '6px 10px';
    clone.style.zIndex = '10002';
    clone.style.pointerEvents = 'none';
    clone.querySelectorAll('.edit-tree-row-tools, .edit-tree-chip-x').forEach((el) => el.remove());
    document.body.appendChild(clone);
    state.clone = clone;
    state.offsetX = ev.clientX - rect.left;
    state.offsetY = ev.clientY - rect.top;
  }
  if (state.clone) {
    state.clone.style.left = (ev.clientX - state.offsetX) + 'px';
    state.clone.style.top = (ev.clientY - state.offsetY) + 'px';
  }
  const targetRow = findDropTargetRow(ev.clientX, ev.clientY, state);
  clearDropIndicators(ctx);
  if (targetRow) {
    const rect = targetRow.getBoundingClientRect();
    const before = (ev.clientY - rect.top) < rect.height / 2;
    targetRow.classList.add(before ? 'drop-before' : 'drop-after');
    try {
      const targetPath = JSON.parse(targetRow.getAttribute('data-drag-path') || '[]');
      state.target = {
        parentPath: targetPath.slice(0, -1),
        index: before ? targetPath[targetPath.length - 1] : targetPath[targetPath.length - 1] + 1
      };
    } catch (e) { state.target = null; }
  } else {
    state.target = null;
  }
}

function findDropTargetRow(clientX, clientY, state) {
  const cloneEl = state.clone;
  let prevPointer = null;
  if (cloneEl) {
    prevPointer = cloneEl.style.pointerEvents;
    cloneEl.style.pointerEvents = 'none';
  }
  const elements = document.elementsFromPoint(clientX, clientY);
  if (cloneEl) cloneEl.style.pointerEvents = prevPointer || 'none';
  for (const el of elements) {
    if (cloneEl && (el === cloneEl || cloneEl.contains(el))) continue;
    const row = el.closest && el.closest('.edit-tree-row[data-drag-depth]');
    if (!row) continue;
    const rowDepth = Number(row.getAttribute('data-drag-depth'));
    if (rowDepth !== state.depth) continue;
    if (row === state.sourceHead) continue;
    if (state.sourceHead.contains(row)) continue;
    return row;
  }
  return null;
}

function handleDragUp(ev, state, ctx, onMove, onUp) {
  if (!state) return;
  document.removeEventListener('mousemove', onMove);
  document.removeEventListener('mouseup', onUp);
  document.body.style.userSelect = '';
  document.body.style.cursor = '';
  if (state.clone) state.clone.remove();
  state.sourceHead.classList.remove('is-dragging');
  clearDropIndicators(ctx);
  let moved = false;
  if (state.started && state.target) {
    const ok = moveNode(ctx && ctx._treeRef, state.path, state.target.parentPath, state.target.index);
    if (ok) {
      moved = true;
      if (ctx && ctx.rerender) ctx.rerender();
    }
  }
  if (ctx) {
    if (ctx._drag === state) ctx._drag = null;
  }
  if (moved && ev && ev.preventDefault) ev.preventDefault();
}

function buildDemoChipRow(params, node, path, tree, ctx) {
  const row = document.createElement('div');
  row.className = 'edit-tree-chip-row';
  const chips = document.createElement('span');
  chips.className = 'edit-tree-chips';
  params.forEach((p) => chips.appendChild(renderChip(p, node, path, tree, ctx)));
  row.appendChild(chips);
  return row;
}

function appendChipRow(head, params, node, path, tree, ctx) {
  const existing = head.querySelector('.edit-tree-chip-row');
  if (existing) existing.remove();
  head.appendChild(buildDemoChipRow(params, node, path, tree, ctx));
}

function renderNode(node, depth, path, tree, ctx) {
  const wrap = document.createElement('div');
  wrap.className = 'edit-tree-node' + (node.isRoot ? ' is-root' : '');
  wrap.setAttribute('data-depth', String(depth));

  const hasChildren = node.children && node.children.length > 0;
  if (hasChildren && demoResolveNodeCollapsed(node, depth, ctx)) {
    wrap.classList.add('is-collapsed');
  }

  const head = document.createElement('div');
  head.className = 'edit-tree-row';
  head.style.setProperty('--tree-depth', String(depth));
  const mainRow = document.createElement('div');
  mainRow.className = 'edit-tree-row-main';

  const toggle = document.createElement('span');
  toggle.className = 'edit-tree-toggle' + (hasChildren ? '' : ' is-leaf');
  toggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>';
  if (hasChildren) {
    toggle.tabIndex = 0;
    toggle.setAttribute('role', 'button');
    toggle.addEventListener('click', function(ev) {
      ev.stopPropagation();
      const collapsed = !wrap.classList.contains('is-collapsed');
      demoSetNodeCollapsed(ctx, node, collapsed);
      wrap.classList.toggle('is-collapsed', collapsed);
    });
  }
  mainRow.appendChild(toggle);

  const icon = document.createElement('span');
  icon.className = 'edit-tree-icon' + (node.isRoot ? ' is-root' : '');
  icon.innerHTML = node.isRoot
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="3" y1="9" x2="21" y2="9"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h18M3 12h18M3 17h18"/></svg>';
  mainRow.appendChild(icon);

  const name = document.createElement('span');
  name.className = 'edit-tree-name' + (node.isRoot ? ' is-root-name' : ' is-editable');
  name.textContent = node.name;
  if (!node.isRoot) {
    name.title = '点击修改名称';
    name.addEventListener('click', function(ev) {
      ev.stopPropagation(); enterEditName(name, node, path, tree, ctx);
    });
  }
  mainRow.appendChild(name);

  const desc = countDesc(node);
  if (desc > 0) {
    const c = document.createElement('span');
    c.className = 'edit-tree-count'; c.textContent = desc + ' 项';
    mainRow.appendChild(c);
  }

  // 参数区:默认折叠,只露一个「▸ N 属性」按钮,点击后再展开所有 chips
  if (node.params && node.params.length) {
    const expanded = ctx._expandedParams && ctx._expandedParams.has(node.id);
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'edit-tree-params-toggle' + (expanded ? ' is-expanded' : '');
    toggleBtn.innerHTML = '<span class="edit-tree-params-toggle-arrow">' + (expanded ? '▾' : '▸') + '</span>' +
      '<span class="edit-tree-params-toggle-text">' + node.params.length + ' 属性</span>';
    toggleBtn.title = expanded ? '收起属性' : '展开属性';
    toggleBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!ctx._expandedParams) ctx._expandedParams = new Set();
      const wasExpanded = ctx._expandedParams.has(node.id);
      if (wasExpanded) {
        ctx._expandedParams.delete(node.id);
      } else {
        ctx._expandedParams.add(node.id);
      }
      const existingChipRow = head.querySelector('.edit-tree-chip-row');
      const arrow = toggleBtn.querySelector('.edit-tree-params-toggle-arrow');
      if (wasExpanded) {
        if (existingChipRow) existingChipRow.remove();
        toggleBtn.classList.remove('is-expanded');
        if (arrow) arrow.textContent = '▸';
        toggleBtn.title = '展开属性';
      } else {
        appendChipRow(head, node.params, node, path, tree, ctx);
        toggleBtn.classList.add('is-expanded');
        if (arrow) arrow.textContent = '▾';
        toggleBtn.title = '收起属性';
      }
    });
    mainRow.appendChild(toggleBtn);

  }

  const tools = document.createElement('span');
  tools.className = 'edit-tree-row-tools';
  tools.appendChild(makeToolBtn('add-child', '+ 子分组', function() {
    addChild(tree, path); ctx.rerender();
  }));
  if (!node.isRoot) {
    const ap = makeToolBtn('add-param', '+ 参数', function(ev) {
      ev.stopPropagation(); openPopover(ap, node, path, tree, ctx);
    });
    tools.appendChild(ap);
    tools.appendChild(makeToolBtn('delete', '删除', function() {
      delNode(tree, path); ctx.rerender();
    }));
  }
  mainRow.appendChild(tools);
  head.appendChild(mainRow);
  if (node.params && node.params.length && ctx._expandedParams && ctx._expandedParams.has(node.id)) {
    appendChipRow(head, node.params, node, path, tree, ctx);
  }

  // 拖拽支持:纯鼠标事件 + 自定义拖拽图像
  if (!node.isRoot) {
    icon.classList.add('is-drag-handle');
    icon.title = '按住拖动可调整同级顺序';
    head.setAttribute('data-drag-path', JSON.stringify(path));
    head.setAttribute('data-drag-depth', String(depth));

    icon.addEventListener('mousedown', function(ev) {
      if (ev.button !== 0) return;
      ev.preventDefault();
      ev.stopPropagation();

      const state = {
        started: false,
        threshold: 4,
        startX: ev.clientX,
        startY: ev.clientY,
        path: path,
        depth: depth,
        sourceHead: head,
        clone: null,
        target: null
      };
      ctx._drag = state;

      const onMove = function(e) { handleDragMove(e, state, ctx); };
      const onUp = function(e) { handleDragUp(e, state, ctx, onMove, onUp); };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      state._onMove = onMove;
      state._onUp = onUp;
    });
  }

  wrap.appendChild(head);

  if (hasChildren) {
    const kids = document.createElement('div');
    kids.className = 'edit-tree-children';
    node.children.forEach((c, i) => {
      const childEl = renderNode(c, depth + 1, path.concat(i), tree, ctx);
      if (i === node.children.length - 1) childEl.classList.add('is-last');
      kids.appendChild(childEl);
    });
    wrap.appendChild(kids);
  }

  return wrap;
}

function renderChip(param, node, path, tree, ctx) {
  const c = document.createElement('span');
  c.className = 'edit-tree-chip' + paramChipClass(param.k);
  c.setAttribute('data-param-key', param.k);
  const k = document.createElement('span');
  k.className = 'edit-tree-chip-k'; k.textContent = param.k;
  c.appendChild(k);
  const v = document.createElement('span');
  v.className = 'edit-tree-chip-v is-editable';
  v.textContent = param.v || '—';
  v.title = '点击修改值';
  v.addEventListener('click', function(ev) {
    ev.stopPropagation(); enterEditChip(v, param, node, path, tree, ctx);
  });
  c.appendChild(v);
  const x = document.createElement('button');
  x.type = 'button';
  x.className = 'edit-tree-chip-x';
  x.textContent = '×';
  x.title = '删除该参数';
  x.addEventListener('click', function(ev) {
    ev.preventDefault(); ev.stopPropagation();
    delParam(tree, path, param.k);
    ctx.rerender();
  });
  c.appendChild(x);
  return c;
}


function syncInlineEditInputSize(sourceEl, input) {
  if (!sourceEl || !input) return;
  const rect = sourceEl.getBoundingClientRect();
  const computed = window.getComputedStyle ? window.getComputedStyle(sourceEl) : null;
  const width = Math.max(1, Math.ceil(rect.width || sourceEl.offsetWidth || 1));
  const height = Math.max(1, Math.ceil(rect.height || sourceEl.offsetHeight || 1));
  input.style.setProperty('--inline-editor-width', width + 'px');
  input.style.height = height + 'px';
  if (computed) {
    input.style.lineHeight = computed.lineHeight;
    input.style.fontFamily = computed.fontFamily;
    input.style.fontSize = computed.fontSize;
    input.style.fontWeight = computed.fontWeight;
    input.style.paddingTop = computed.paddingTop;
    input.style.paddingRight = computed.paddingRight;
    input.style.paddingBottom = computed.paddingBottom;
    input.style.paddingLeft = computed.paddingLeft;
  }
}

function splitFeatureSelectionValue(value) {
  return String(value || '')
    .split(/[,，]/)
    .map(function(item) { return item.trim(); })
    .filter(Boolean);
}

function collectFeatureLeafNames(nodeOrNodes) {
  const leaves = [];
  const nodes = Array.isArray(nodeOrNodes) ? nodeOrNodes : [nodeOrNodes];
  function walk(item) {
    if (!item || !item.name) return;
    const children = Array.isArray(item.children) ? item.children : [];
    if (!children.length) {
      if (!leaves.includes(item.name)) leaves.push(item.name);
      return;
    }
    children.forEach(walk);
  }
  nodes.forEach(walk);
  return leaves;
}

function buildFeatureCatalogMaps(catalog) {
  const nodeByName = new Map();
  const tree = Array.isArray(catalog && catalog.tree) ? catalog.tree : [];
  function walk(item) {
    if (!item || !item.name) return;
    if (!nodeByName.has(item.name)) nodeByName.set(item.name, item);
    (item.children || []).forEach(walk);
  }
  tree.forEach(walk);
  const leafOrder = Array.isArray(catalog && catalog.leafNames) && catalog.leafNames.length
    ? catalog.leafNames.slice()
    : collectFeatureLeafNames(tree);
  return { nodeByName: nodeByName, leafSet: new Set(leafOrder), leafOrder: leafOrder };
}

function normalizeFeatureSelectionValue(value, catalog) {
  const maps = buildFeatureCatalogMaps(catalog);
  const selected = new Set();
  const unknownValues = [];
  splitFeatureSelectionValue(value).forEach(function(token) {
    if (maps.leafSet.has(token)) {
      selected.add(token);
      return;
    }
    const featureNode = maps.nodeByName.get(token);
    if (featureNode) {
      collectFeatureLeafNames(featureNode).forEach(function(leafName) { selected.add(leafName); });
      return;
    }
    if (!unknownValues.includes(token)) unknownValues.push(token);
  });
  return { selected: selected, unknownValues: unknownValues };
}

function serializeFeatureSelection(selectedLeafNames, unknownValues, catalog) {
  const selected = selectedLeafNames instanceof Set ? selectedLeafNames : new Set(selectedLeafNames || []);
  const maps = buildFeatureCatalogMaps(catalog);
  const values = [];
  maps.leafOrder.forEach(function(featureName) {
    if (selected.has(featureName) && !values.includes(featureName)) values.push(featureName);
  });
  (unknownValues || []).forEach(function(featureName) {
    if (featureName && !values.includes(featureName)) values.push(featureName);
  });
  return values.join(',');
}

function positionFeatureSelectPopover(pop, anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const popW = Math.min(360, Math.max(300, window.innerWidth - 16));
  pop.style.position = 'fixed';
  pop.style.width = popW + 'px';
  let left = rect.left;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - 8 - popW;
  if (left < 8) left = 8;
  pop.style.left = left + 'px';
  pop.style.top = (rect.bottom + 6) + 'px';
}

function buildFeatureSelectNode(featureNode, state, depth, rerender) {
  const wrap = document.createElement('div');
  wrap.className = 'feature-select-node';
  wrap.style.setProperty('--feature-depth', String(depth || 0));
  const row = document.createElement('label');
  row.className = 'feature-select-row';
  const input = document.createElement('input');
  input.type = 'checkbox';
  const leafNames = collectFeatureLeafNames(featureNode);
  const selectedCount = leafNames.filter(function(name) { return state.selected.has(name); }).length;
  input.checked = leafNames.length > 0 && selectedCount === leafNames.length;
  input.indeterminate = selectedCount > 0 && selectedCount < leafNames.length;
  input.addEventListener('change', function(ev) {
    ev.stopPropagation();
    leafNames.forEach(function(leafName) {
      if (input.checked) state.selected.add(leafName);
      else state.selected.delete(leafName);
    });
    rerender();
  });
  row.appendChild(input);
  const name = document.createElement('span');
  name.className = 'feature-select-name';
  name.textContent = featureNode.name;
  row.appendChild(name);
  const children = Array.isArray(featureNode.children) ? featureNode.children : [];
  if (children.length) {
    const count = document.createElement('span');
    count.className = 'feature-select-count';
    count.textContent = leafNames.length + ' 项';
    row.appendChild(count);
  }
  wrap.appendChild(row);
  if (children.length) {
    const kids = document.createElement('div');
    kids.className = 'feature-select-children';
    children.forEach(function(child) {
      kids.appendChild(buildFeatureSelectNode(child, state, depth + 1, rerender));
    });
    wrap.appendChild(kids);
  }
  return wrap;
}

function getFeatureSelectScrollTop(pop) {
  const treeEl = pop && pop.querySelector ? pop.querySelector('.feature-select-tree') : null;
  return treeEl ? treeEl.scrollTop : 0;
}

function restoreFeatureSelectScrollTop(treeEl, scrollTop) {
  if (!treeEl || !scrollTop) return;
  treeEl.scrollTop = scrollTop;
  if (typeof window !== 'undefined' && window.requestAnimationFrame) {
    window.requestAnimationFrame(function() {
      treeEl.scrollTop = scrollTop;
    });
  }
}

function renderFeatureSelectDropdown(pop, state, param, path, tree, ctx, close) {
  const previousTreeScrollTop = getFeatureSelectScrollTop(pop);
  pop.innerHTML = '';
  const head = document.createElement('div');
  head.className = 'feature-select-head';
  head.textContent = '特征选择';
  pop.appendChild(head);
  if (state.unknownValues.length) {
    const unknown = document.createElement('div');
    unknown.className = 'feature-select-unknown';
    unknown.textContent = '保留未识别项: ' + state.unknownValues.join(', ');
    pop.appendChild(unknown);
  }
  const treeEl = document.createElement('div');
  treeEl.className = 'feature-select-tree';
  state.catalog.tree.forEach(function(featureNode) {
    treeEl.appendChild(buildFeatureSelectNode(featureNode, state, 0, function() {
      renderFeatureSelectDropdown(pop, state, param, path, tree, ctx, close);
    }));
  });
  pop.appendChild(treeEl);
  restoreFeatureSelectScrollTop(treeEl, previousTreeScrollTop);
  const actions = document.createElement('div');
  actions.className = 'feature-select-actions';
  const summary = document.createElement('span');
  summary.className = 'feature-select-summary';
  summary.textContent = '已选 ' + state.selected.size + ' 项';
  actions.appendChild(summary);
  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'feature-select-clear';
  clearBtn.textContent = '清空';
  clearBtn.addEventListener('click', function(ev) {
    ev.preventDefault(); ev.stopPropagation();
    state.selected.clear();
    renderFeatureSelectDropdown(pop, state, param, path, tree, ctx, close);
  });
  actions.appendChild(clearBtn);
  const okBtn = document.createElement('button');
  okBtn.type = 'button';
  okBtn.className = 'feature-select-confirm';
  okBtn.textContent = '确定';
  okBtn.addEventListener('click', function(ev) {
    ev.preventDefault(); ev.stopPropagation();
    setParamValue(tree, path, param.k, serializeFeatureSelection(state.selected, state.unknownValues, state.catalog));
    ctx.rerender();
    close();
  });
  actions.appendChild(okBtn);
  pop.appendChild(actions);
}

function openFeatureSelectDropdown(vEl, param, node, path, tree, ctx) {
  document.querySelectorAll('.feature-select-popover').forEach(function(el) { el.remove(); });
  const pop = document.createElement('div');
  pop.className = 'feature-select-popover';
  const normalized = normalizeFeatureSelectionValue(param.v, DEMO_FEATURE_CATALOG);
  const state = {
    catalog: DEMO_FEATURE_CATALOG,
    selected: normalized.selected,
    unknownValues: normalized.unknownValues
  };
  function close() {
    document.removeEventListener('click', onDocClick, true);
    document.removeEventListener('keydown', onDocKey, true);
    pop.remove();
  }
  const onDocClick = function(ev) {
    if (!pop.contains(ev.target) && ev.target !== vEl) close();
  };
  const onDocKey = function(ev) {
    if (ev.key === 'Escape') close();
  };
  document.body.appendChild(pop);
  positionFeatureSelectPopover(pop, vEl);
  renderFeatureSelectDropdown(pop, state, param, path, tree, ctx, close);
  setTimeout(function() {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onDocKey, true);
  }, 0);
}

function enterEditName(nameEl, node, path, tree, ctx) {
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'edit-tree-name-input';
  input.value = node.name || '';
  input.maxLength = 40;
  syncInlineEditInputSize(nameEl, input);
  nameEl.replaceWith(input);
  input.focus(); input.select();
  let done = false;
  const finish = function(commit) {
    if (done) return; done = true;
    if (commit) rename(tree, path, input.value);
    ctx.rerender();
  };
  input.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', function() { finish(true); });
}

function enterEditChip(vEl, param, node, path, tree, ctx) {
  if (param.k === FEATURE_PARAM_KEY) {
    openFeatureSelectDropdown(vEl, param, node, path, tree, ctx);
    return;
  }
  const enums = ENUM_FIELDS[param.k];
  let input, isSelect = false;
  if (enums) {
    isSelect = true;
    input = document.createElement('select');
    input.className = 'edit-tree-chip-v-input';
    enums.forEach((opt) => {
      const o = document.createElement('option'); o.value = opt; o.textContent = opt;
      if (opt === param.v) o.selected = true;
      input.appendChild(o);
    });
  } else {
    input = document.createElement('input');
    input.type = 'text'; input.className = 'edit-tree-chip-v-input'; input.value = param.v || '';
  }
  syncInlineEditInputSize(vEl, input);
  vEl.replaceWith(input);
  input.focus();
  if (!isSelect) input.select();
  let done = false;
  const finish = function(commit) {
    if (done) return; done = true;
    if (commit) setParamValue(tree, path, param.k, input.value);
    ctx.rerender();
  };
  input.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', function() { finish(true); });
}

function openPopover(anchorBtn, node, path, tree, ctx) {
  document.querySelectorAll('.edit-param-popover').forEach((el) => el.remove());

  const pop = document.createElement('div');
  pop.className = 'edit-param-popover';

  const title = document.createElement('div');
  title.className = 'edit-param-popover-title';
  title.textContent = '新增参数到「' + (node.name || '未命名') + '」';
  pop.appendChild(title);

  const existing = new Set((node.params || []).map((p) => p.k));
  const sug = SUGGESTED_PARAM_KEYS.filter((k) => !existing.has(k));

  if (sug.length) {
    const list = document.createElement('div');
    list.className = 'edit-param-popover-list';
    sug.forEach((k) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'edit-param-popover-item';
      const def = k === FEATURE_PARAM_KEY ? '' : (ENUM_FIELDS[k] ? ENUM_FIELDS[k][0] : '');
      btn.innerHTML = '<span class="edit-param-popover-k">' + escapeHtml(k) + '</span>' +
        (def ? '<span class="edit-param-popover-d">→ ' + escapeHtml(def) + '</span>' : '<span class="edit-param-popover-d edit-param-popover-d-empty">(空)</span>');
      btn.title = '添加「' + k + '」参数' + (def ? ',默认 ' + def : '');
      btn.addEventListener('click', function(ev) {
        ev.preventDefault(); ev.stopPropagation();
        setParam(tree, path, k, def);
        pop.remove(); ctx.rerender();
      });
      list.appendChild(btn);
    });
    pop.appendChild(list);
  } else {
    const empty = document.createElement('div');
    empty.className = 'edit-param-popover-empty';
    empty.textContent = '常用参数已全部添加,可直接在下方输入自定义 key';
    pop.appendChild(empty);
  }

  const custom = document.createElement('div');
  custom.className = 'edit-param-popover-custom';
  const ci = document.createElement('input');
  ci.type = 'text'; ci.placeholder = '或输入自定义参数名...';
  custom.appendChild(ci);
  const cb = document.createElement('button');
  cb.type = 'button'; cb.textContent = '添加'; cb.className = 'edit-param-popover-add';
  custom.appendChild(cb);
  pop.appendChild(custom);

  const submit = function() {
    const k = ci.value.trim();
    if (!k) return;
    if (existing.has(k)) {
      ci.value = ''; ci.placeholder = '参数名已存在,请换一个';
      return;
    }
    setParam(tree, path, k, '');
    pop.remove(); ctx.rerender();
  };
  cb.addEventListener('click', function(ev) { ev.preventDefault(); submit(); });
  ci.addEventListener('keydown', function(ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); submit(); }
    else if (ev.key === 'Escape') { ev.preventDefault(); pop.remove(); }
  });

  document.body.appendChild(pop);
  const rect = anchorBtn.getBoundingClientRect();
  pop.style.position = 'fixed';
  const popW = 240;
  let left = rect.right - popW;
  if (left < 8) left = 8;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - 8 - popW;
  pop.style.left = left + 'px';
  pop.style.top = (rect.bottom + 6) + 'px';
  setTimeout(function() { ci.focus(); }, 30);

  const onDocClick = function(ev) {
    if (!pop.contains(ev.target) && ev.target !== anchorBtn) {
      pop.remove();
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onDocKey, true);
    }
  };
  const onDocKey = function(ev) {
    if (ev.key === 'Escape') {
      pop.remove();
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onDocKey, true);
    }
  };
  setTimeout(function() {
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onDocKey, true);
  }, 0);
}

function renderTree(container, tree, opts) {
  container.innerHTML = '';
  if (!tree) {
    container.innerHTML = '<div class="edit-tree-empty">没有可编辑的分组结构。</div>';
    return;
  }
  if (opts) {
    if (!opts._collapsedNodes) opts._collapsedNodes = new Map();
    if (!opts._expandedParams) opts._expandedParams = new Set();
  }
  const ctx = { rerender: function() {
    renderTree(container, tree, opts);
  }};
  ctx.defaultCollapsedDepth = opts && typeof opts.defaultCollapsedDepth === 'number' ? opts.defaultCollapsedDepth : 99;
  ctx._collapsedNodes = opts && opts._collapsedNodes;
  ctx._expandedParams = opts && opts._expandedParams;
  ctx._ownerContainer = container;
  ctx._treeRef = tree;
  container.appendChild(renderNode(tree, 0, [], tree, ctx));
}

// 全屏编辑视图(演示版):共享同一棵 tree,跟主弹窗双向同步
let __fsRender = null;
function openDemoFullscreen(tree, sharedTreeOpts) {
  document.querySelectorAll('.edit-tree-fullscreen').forEach((el) => el.remove());

  const fs = document.createElement('div');
  fs.className = 'edit-tree-fullscreen';
  fs.innerHTML =
    '<div class="edit-tree-fullscreen-head">' +
      '<div class="edit-tree-fullscreen-title">' +
        '<span class="edit-tree-fullscreen-icon">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>' +
          '</svg>' +
        '</span>' +
        '<div class="edit-tree-fullscreen-title-text">' +
          '<div class="edit-tree-fullscreen-title-main">分组结构 — 放大编辑视图</div>' +
        '</div>' +
      '</div>' +
      '<div class="edit-tree-fullscreen-actions">' +
        '<button type="button" class="edit-tree-tool" data-role="fs-expand">全部展开</button>' +
        '<button type="button" class="edit-tree-tool" data-role="fs-collapse">全部折叠</button>' +
        '<button type="button" class="edit-tree-fullscreen-close" aria-label="关闭全屏" title="关闭全屏">×</button>' +
      '</div>' +
    '</div>' +
    '<div class="edit-tree-fullscreen-body">' +
      '<div class="edit-tree edit-tree-large" data-role="fs-tree"></div>' +
    '</div>';

  document.body.appendChild(fs);
  const fsTreeEl = fs.querySelector('[data-role="fs-tree"]');
  const fsTreeOpts = {
    defaultCollapsedDepth: 99,
    _collapsedNodes: sharedTreeOpts && sharedTreeOpts._collapsedNodes,
    _expandedParams: sharedTreeOpts && sharedTreeOpts._expandedParams
  };

  function fsRender() {
    renderTree(fsTreeEl, tree, fsTreeOpts);
  }
  fsRender();

  fs.querySelector('[data-role="fs-expand"]').addEventListener('click', function() {
    demoSetAllNodeCollapsed(fsTreeOpts, tree, false);
    fsTreeEl.querySelectorAll('.edit-tree-node.is-collapsed').forEach((n) => n.classList.toggle('is-collapsed', false));
  });
  fs.querySelector('[data-role="fs-collapse"]').addEventListener('click', function() {
    demoSetRootChildrenCollapsed(fsTreeOpts, tree, true);
    fsTreeEl.querySelectorAll(':scope > .edit-tree-node > .edit-tree-children > .edit-tree-node').forEach((n) => n.classList.toggle('is-collapsed', true));
  });

  const onKey = function(ev) { if (ev.key === 'Escape') { ev.stopPropagation(); close(); } };
  function close() {
    document.removeEventListener('keydown', onKey, true);
    fs.remove();
    __fsRender = null;
  }
  document.addEventListener('keydown', onKey, true);
  fs.addEventListener('click', function(ev) { if (ev.target === fs) close(); });
  fs.querySelector('.edit-tree-fullscreen-close').addEventListener('click', close);

  __fsRender = fsRender;
}

// 模拟打开卡片编辑弹窗 —— 演示态
function showEditAlert(opt) {
  const modal = document.createElement('div');
  modal.className = 'edit-backdrop';
  const conf = Number(opt.confidence || 0);
  const confPct = (conf * 100).toFixed(1);
  const fullStars = Math.round(conf * 5);
  const stars = '★'.repeat(fullStars) + '☆'.repeat(5 - fullStars);
  const groupCount = (opt.meta && opt.meta.groupCount) || 0;
  const depth = (opt.meta && opt.meta.depth) || 0;
  const initialFilename = opt.filename || opt.subtitle || '';
  const initialInputName = deriveDisplayNameFromFilename(initialFilename) || initialFilename;

  modal.innerHTML =
    '<div class="edit-dialog" role="dialog" aria-label="编辑模板卡片">' +
      '<div class="edit-dialog-head">' +
        '<div class="edit-dialog-title-wrap">' +
          '<span class="edit-dialog-icon">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>' +
          '</span>' +
          '<div class="edit-dialog-title-text">' +
            '<div class="edit-dialog-title">编辑模板卡片 (演示)</div>' +
            '<div class="edit-dialog-subtitle" data-role="filename-head">' + escapeHtml(initialFilename || opt.title) + '</div>' +
          '</div>' +
        '</div>' +
        '<button class="edit-dialog-close" type="button" data-role="close">×</button>' +
      '</div>' +
      '<div class="edit-dialog-body">' +
        '<div class="edit-conf-row">' +
          '<span class="edit-conf-label">匹配置信度</span>' +
          '<span class="edit-conf-value">' + confPct + '%</span>' +
          '<span class="edit-stars">' + stars + '</span>' +
          '<span style="margin-left:auto;font-size:12px;color:#1e40af">分组: <b>' + groupCount + '</b> · 深度: <b>' + depth + '</b></span>' +
        '</div>' +
        '<div class="edit-section">' +
          '<div class="edit-section-label">基础信息</div>' +
          '<div class="edit-field">' +
            '<label>文件名</label><input class="edit-input" data-fld="filename" value="' + escapeHtml(initialInputName) + '" />' +
          '</div>' +
        '</div>' +
        '<div class="edit-divider"></div>' +
        '<div class="edit-section">' +
          '<div class="edit-section-label-row">' +
            '<div class="edit-section-label">分组结构预览 (可交互编辑)</div>' +
            '<div class="edit-tree-tools">' +
              '<button type="button" class="edit-tree-tool edit-tree-tool-primary" data-role="tree-fullscreen" title="放大到全屏编辑">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                  '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>' +
                '</svg>' +
                '放大编辑' +
              '</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-expand">全部展开</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-collapse">全部折叠</button>' +
              '<span class="edit-tree-tool-sep"></span>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-params-expand">属性全开</button>' +
              '<button type="button" class="edit-tree-tool" data-role="tree-params-collapse">属性全收</button>' +
            '</div>' +
          '</div>' +
          '<div class="edit-tree" data-role="tree"></div>' +
          '<div class="edit-tag-hint" style="margin-top:6px">' +
            '属性默认折叠,点「▸ N 属性」展开 · 点节点名改名 · 点参数值改值(枚举字段是下拉) · ' +
            'hover 行出现 +子分组 / +参数 / 删除 · +参数弹出推荐列表 · 点「放大编辑」可全屏大图操作' +
          '</div>' +
        '</div>' +
        '<div class="edit-status ok">✓ 演示态:点保存只临时暂存,外层“写入模板库并加载”才会落盘。</div>' +
      '</div>' +
      '<div class="edit-actions">' +
        '<div class="edit-status" style="font-size:12px;color:#64748b">演示态</div>' +
        '<div class="edit-actions-right">' +
          '<button class="edit-cancel" type="button" data-role="cancel">取消</button>' +
          '<button class="edit-save" type="button" data-role="save">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>' +
            '保存' +
          '</button>' +
        '</div>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  // 渲染演示树
  const treeEl = modal.querySelector('[data-role="tree"]');
  const tree = makeDemoTree(opt.meta);
  const treeOpts = { defaultCollapsedDepth: 4 };
  function renderSmall() { renderTree(treeEl, tree, treeOpts); }
  renderSmall();

  // 全部展开 / 折叠
  modal.querySelector('[data-role="tree-expand"]').addEventListener('click', function() {
    demoSetAllNodeCollapsed(treeOpts, tree, false);
    treeEl.querySelectorAll('.edit-tree-node.is-collapsed').forEach((n) => n.classList.toggle('is-collapsed', false));
  });
  modal.querySelector('[data-role="tree-collapse"]').addEventListener('click', function() {
    demoSetRootChildrenCollapsed(treeOpts, tree, true);
    treeEl.querySelectorAll(':scope > .edit-tree-node > .edit-tree-children > .edit-tree-node').forEach((n) => n.classList.toggle('is-collapsed', true));
  });
  // 属性全开 / 全收:遍历所有 toggle 按钮逐个触发
  function bulkToggleParams(expand) {
    treeEl.querySelectorAll('.edit-tree-params-toggle').forEach((btn) => {
      const isExpanded = btn.classList.contains('is-expanded');
      if ((expand && !isExpanded) || (!expand && isExpanded)) btn.click();
    });
  }
  modal.querySelector('[data-role="tree-params-expand"]').addEventListener('click', function() { bulkToggleParams(true); });
  modal.querySelector('[data-role="tree-params-collapse"]').addEventListener('click', function() { bulkToggleParams(false); });
  // 放大编辑
  modal.querySelector('[data-role="tree-fullscreen"]').addEventListener('click', function() {
    openDemoFullscreen(tree, treeOpts);
    renderSmall(); // 关掉大图后小图保持最新
  });

  const close = () => {
    document.removeEventListener('keydown', onKey, true);
    document.querySelectorAll('.edit-tree-fullscreen').forEach((el) => el.remove());
    document.querySelectorAll('.edit-param-popover').forEach((el) => el.remove());
    modal.remove();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') {
      // 放大视图开着时,Escape 交给它
      if (document.querySelector('.edit-tree-fullscreen')) return;
      close();
    }
  };
  document.addEventListener('keydown', onKey, true);
  modal.addEventListener('click', (e) => {
    if (e.target === modal && !document.querySelector('.edit-tree-fullscreen')) close();
  });
  modal.querySelector('[data-role="close"]').addEventListener('click', close);
  modal.querySelector('[data-role="cancel"]').addEventListener('click', close);
  const filenameInput = modal.querySelector('[data-fld="filename"]');
  const filenameHead = modal.querySelector('[data-role="filename-head"]');
  filenameInput.addEventListener('input', function() {
    const normalizedFilename = normalizeTemplateFilenameInput(filenameInput.value);
    filenameHead.textContent = normalizedFilename || '';
  });
  modal.querySelector('[data-role="save"]').addEventListener('click', function() {
    const savedFilename = normalizeTemplateFilenameInput(filenameInput.value);
    const displayName = deriveDisplayNameFromFilename(savedFilename);
    const card = document.querySelector('.option-card[data-template-id="' + (opt.templateId || opt.id || '') + '"]');
    if (card) {
      card.__kmaiEditedTemplate = { filename: savedFilename, xml: '<demo-xml />' };
      const t = card.querySelector('.option-card-title');
      if (t) { t.textContent = displayName; t.setAttribute('title', displayName); }
      const s = card.querySelector('.option-card-subtitle');
      if (s) { s.textContent = savedFilename; s.setAttribute('title', savedFilename); }
      resetOptionCardForTemplateEdit(card, card.getAttribute('data-group-template-only') === '1');
    }
    filenameHead.textContent = savedFilename;
    alert('演示态: 已临时保存到当前卡片内存。\n外层点击“写入模板库并加载”时才会写入 3DMPS 模板库。\n\n模板: ' + displayName);
  });
}

export function attachOptionCardEvents(card, opt, ui) {
  const applyBtn = card.querySelector('[data-action="apply-card"]');
  if (applyBtn) {
    applyBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      alert('演示态: 实际生产中这里会调 apply_group_template 写入模板库并加载。\n\n模板: ' + (opt.title || opt.filename));
    });
  }
  const editBtn = card.querySelector('[data-action="edit-card"]');
  if (editBtn) {
    editBtn.addEventListener('click', function(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      showEditAlert(opt);
    });
  }
}
