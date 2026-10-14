import * as THREE from '/similar-assets/three/build/three.module.js';
import { OrbitControls } from '/similar-assets/three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from '/similar-assets/three/examples/jsm/loaders/GLTFLoader.js';
import {
  dom, escapeHtml, getApiToken, requestJsonPromise, setStatus,
  addBotMsg, addErrorMsg,
} from './shared.js';
import { modelColorForSlot } from './similar_parts_palette.js';
import {
  DEFAULT_SCALE_MODE, scaleModeLabel, uniformScaleForExtents, cameraFitDistance,
} from './similar_parts_scale.js';
import {
  recommendedTemplateRowMarkup, recommendedTemplateLabel, buildTemplateApplyPayload,
} from './similar_parts_template_ui.js';
import { openOptionCardEditor } from './tool_call.js';

let activePanel = null;
let requestSequence = 0;
let activeController = null;
const CANONICAL_PART_AXIS = new THREE.Vector3(1, 0, 0);
const MAX_ORIENTATION_SAMPLES = 6000;

function disposeObject(root) {
  if (!root) return;
  root.traverse(function(object) {
    if (object.geometry) object.geometry.dispose();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach(function(material) {
      if (!material) return;
      Object.values(material).forEach(function(value) {
        if (value && value.isTexture) value.dispose();
      });
      material.dispose();
    });
  });
}

function makeScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f7fa);  // 精致低饱和工作室浅灰
  scene.add(new THREE.HemisphereLight(0xffffff, 0xcfdbe8, 1.15));
  const light = new THREE.DirectionalLight(0xffffff, 1.15);
  light.position.set(2, -3, 4);
  scene.add(light);
  const fillLight = new THREE.DirectionalLight(0xe8edf5, 0.45);
  fillLight.position.set(-3, 2, -2);
  scene.add(fillLight);
  const rimLight = new THREE.DirectionalLight(0xffffff, 0.55);
  rimLight.position.set(-2, 4, 3);
  scene.add(rimLight);
  const grid = new THREE.GridHelper(160, 20, 0xc8d3e0, 0xe2e8f0);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);
  return scene;
}

function paint(root, color) {
  root.traverse(function(object) {
    if (!object.isMesh) return;
    if (!object.geometry.attributes.normal) object.geometry.computeVertexNormals();
    object.material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.38,
      metalness: 0.22,
      side: THREE.DoubleSide,
    });
  });
}

function collectOrientationSamples(root) {
  let vertexCount = 0;
  root.traverse(function(object) {
    const position = object.geometry && object.geometry.attributes.position;
    if (object.isMesh && position) vertexCount += position.count;
  });
  if (vertexCount < 3) return [];

  root.updateWorldMatrix(true, true);
  const inverseRoot = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const stride = Math.max(1, Math.ceil(vertexCount / MAX_ORIENTATION_SAMPLES));
  const samples = [];
  root.traverse(function(object) {
    const position = object.geometry && object.geometry.attributes.position;
    if (!object.isMesh || !position) return;
    const toRoot = new THREE.Matrix4().multiplyMatrices(inverseRoot, object.matrixWorld);
    for (let index = 0; index < position.count; index += stride) {
      samples.push(new THREE.Vector3().fromBufferAttribute(position, index).applyMatrix4(toRoot));
    }
  });
  return samples;
}

function dominantAxis(samples, center) {
  const covariance = [0, 0, 0, 0, 0, 0]; // xx, xy, xz, yy, yz, zz
  samples.forEach(function(point) {
    const x = point.x - center.x;
    const y = point.y - center.y;
    const z = point.z - center.z;
    covariance[0] += x * x;
    covariance[1] += x * y;
    covariance[2] += x * z;
    covariance[3] += y * y;
    covariance[4] += y * z;
    covariance[5] += z * z;
  });
  const diagonal = [covariance[0], covariance[3], covariance[5]];
  const startIndex = diagonal.indexOf(Math.max.apply(null, diagonal));
  let axis = new THREE.Vector3(startIndex === 0 ? 1 : 0, startIndex === 1 ? 1 : 0, startIndex === 2 ? 1 : 0);
  for (let iteration = 0; iteration < 16; iteration += 1) {
    const next = new THREE.Vector3(
      covariance[0] * axis.x + covariance[1] * axis.y + covariance[2] * axis.z,
      covariance[1] * axis.x + covariance[3] * axis.y + covariance[4] * axis.z,
      covariance[2] * axis.x + covariance[4] * axis.y + covariance[5] * axis.z
    );
    if (next.lengthSq() < 1e-12) break;
    axis = next.normalize();
  }
  return axis;
}

function endpointRadius(samples, center, axis, minProjection, maxProjection, positiveEnd) {
  const span = Math.max(maxProjection - minProjection, 1e-9);
  const threshold = positiveEnd
    ? maxProjection - span * 0.15
    : minProjection + span * 0.15;
  let radiusSquared = 0;
  samples.forEach(function(point) {
    const offset = point.clone().sub(center);
    const projection = offset.dot(axis);
    if ((positiveEnd && projection < threshold) || (!positiveEnd && projection > threshold)) return;
    radiusSquared = Math.max(radiusSquared, Math.max(0, offset.lengthSq() - projection * projection));
  });
  return Math.sqrt(radiusSquared);
}

function normalizePartOrientation(root) {
  const samples = collectOrientationSamples(root);
  if (samples.length < 3) return root;
  const center = samples.reduce(function(total, point) { return total.add(point); }, new THREE.Vector3())
    .multiplyScalar(1 / samples.length);
  const axis = dominantAxis(samples, center);
  let minProjection = Infinity;
  let maxProjection = -Infinity;
  let thirdMoment = 0;
  samples.forEach(function(point) {
    const projection = point.clone().sub(center).dot(axis);
    minProjection = Math.min(minProjection, projection);
    maxProjection = Math.max(maxProjection, projection);
    thirdMoment += projection * projection * projection;
  });
  const negativeRadius = endpointRadius(samples, center, axis, minProjection, maxProjection, false);
  const positiveRadius = endpointRadius(samples, center, axis, minProjection, maxProjection, true);
  const radiusScale = Math.max(negativeRadius, positiveRadius, 1e-9);
  if (negativeRadius > positiveRadius + radiusScale * 0.05 ||
      (Math.abs(negativeRadius - positiveRadius) <= radiusScale * 0.05 && thirdMoment < 0)) {
    axis.negate();
  }

  const wrapper = new THREE.Group();
  wrapper.name = 'normalized-part-orientation';
  wrapper.add(root);
  wrapper.quaternion.setFromUnitVectors(axis, CANONICAL_PART_AXIS);
  wrapper.updateWorldMatrix(true, true);
  return wrapper;
}

function center(root) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const middle = box.getCenter(new THREE.Vector3());
  root.position.sub(middle);
  root.updateWorldMatrix(true, true);
}

function createViewer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setScissorTest(true);
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 10000);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  const scenes = { current: makeScene(), candidate: makeScene() };
  const roots = { current: null, candidate: null };
  let scaleMode = DEFAULT_SCALE_MODE;
  let animationFrame = 0;
  let lastWidth = 0;
  let lastHeight = 0;

  function resize() {
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    if (width === lastWidth && height === lastHeight) return;
    lastWidth = width;
    lastHeight = height;
    renderer.setSize(width, height, false);
    fit();
  }

  function fit() {
    const boxes = Object.values(roots).filter(Boolean).map(function(root) {
      return new THREE.Box3().setFromObject(root);
    });
    if (!boxes.length) return;
    const box = boxes[0].clone();
    boxes.slice(1).forEach(function(item) { box.union(item); });
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 1);
    const aspect = Math.max(1, Math.floor(canvas.clientWidth / 2)) / Math.max(1, canvas.clientHeight);
    const distance = cameraFitDistance(Math.max(size.length() / 2, 1), aspect, camera.fov);
    controls.target.set(0, 0, 0);
    camera.position.set(1.35, -1.55, 1.05).normalize().multiplyScalar(distance);
    camera.near = Math.max(radius / 1000, 0.01);
    camera.far = Math.max(distance * 20, 100);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    controls.update();
  }

  function applyScaleMode(root) {
    if (!root) return;
    root.scale.setScalar(1);
    root.position.set(0, 0, 0);
    root.updateWorldMatrix(true, true);
    const naturalSize = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3());
    const scale = uniformScaleForExtents(
      [naturalSize.x, naturalSize.y, naturalSize.z],
      scaleMode
    );
    root.scale.setScalar(scale);
    root.position.set(0, 0, 0);
    root.updateWorldMatrix(true, true);
    center(root);
  }

  function setScaleMode(nextMode) {
    scaleMode = nextMode === 'actual' ? 'actual' : 'shape';
    Object.values(roots).forEach(applyScaleMode);
    fit();
    return scaleMode;
  }

  function setRoot(slot, root) {
    if (roots[slot]) {
      scenes[slot].remove(roots[slot]);
      disposeObject(roots[slot]);
    }
    const normalizedRoot = normalizePartOrientation(root);
    paint(normalizedRoot, modelColorForSlot(slot));
    roots[slot] = normalizedRoot;
    scenes[slot].add(normalizedRoot);
    applyScaleMode(normalizedRoot);
    fit();
  }

  function render() {
    animationFrame = window.requestAnimationFrame(render);
    resize();
    controls.update();
    const width = Math.max(canvas.clientWidth, 1);
    const height = Math.max(canvas.clientHeight, 1);
    const leftWidth = Math.floor(width / 2);
    camera.aspect = Math.max(leftWidth, 1) / height;
    camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, leftWidth, height);
    renderer.setScissor(0, 0, leftWidth, height);
    renderer.render(scenes.current, camera);
    renderer.setViewport(leftWidth, 0, width - leftWidth, height);
    renderer.setScissor(leftWidth, 0, width - leftWidth, height);
    renderer.render(scenes.candidate, camera);
  }
  render();

  return {
    setRoot,
    setScaleMode,
    getScaleMode: function() { return scaleMode; },
    fit,
    dispose: function() {
      window.cancelAnimationFrame(animationFrame);
      disposeObject(roots.current);
      disposeObject(roots.candidate);
      controls.dispose();
      renderer.dispose();
    },
  };
}

async function loadGltf(url, signal) {
  const response = await fetch(url, {
    headers: { 'X-KmAI-Token': getApiToken() },
    signal,
  });
  if (!response.ok) {
    let message = '模型加载失败';
    try { message = (await response.json()).message || message; } catch (error) { /* ignore */ }
    throw new Error(message);
  }
  const buffer = await response.arrayBuffer();
  const loader = new GLTFLoader();
  return new Promise(function(resolve, reject) {
    loader.parse(buffer, '', function(gltf) { resolve(gltf.scene); }, reject);
  });
}

function panelMarkup() {
  return '' +
    '<section class="similar-parts-panel" aria-label="查询相似零件，匹配分组模板">' +
      '<div class="similar-parts-toolbar">' +
        '<div class="similar-parts-title-wrap">' +
          '<svg class="sp-icon-cube" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>' +
            '<polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>' +
            '<line x1="12" y1="22.08" x2="12" y2="12"></line>' +
          '</svg>' +
          '<h2>查询相似零件，匹配分组模板</h2>' +
        '</div>' +
        '<button type="button" class="similar-parts-retry" data-role="retry" style="display:none" title="重新查询">↻ 重新查询</button>' +

        '<span class="similar-parts-status" data-role="status"></span>' +
        '<button class="similar-parts-close" type="button" aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="similar-parts-workbench" data-role="workbench" hidden>' +
        '<div class="similar-parts-stage">' +
          '<canvas data-role="canvas"></canvas>' +
          '<div class="similar-parts-view-label current">' +
            '<span class="sp-label-tag">基准 · 当前零件</span>' +
            '<strong data-role="current-name">—</strong>' +
          '</div>' +
          '<div class="similar-parts-view-label candidate">' +
            '<span class="sp-label-tag" data-role="candidate-rank">候选 · 相似零件</span>' +
            '<strong data-role="candidate-name">—</strong>' +
          '</div>' +
          '<div class="similar-parts-divider"><span class="sp-vs-badge">VS</span></div>' +
          '<div class="similar-parts-view-tools">' +
            '<div class="similar-parts-scale-switch" role="group" aria-label="模型缩放模式">' +
              '<button type="button" data-scale-mode="shape" aria-pressed="true"><span>形状对比</span></button>' +
              '<button type="button" data-scale-mode="actual" aria-pressed="false"><span>真实尺寸</span></button>' +
            '</div>' +
            '<button type="button" class="similar-parts-fit" data-role="fit">' +
              '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>' +
              '<span>适应窗口</span>' +
            '</button>' +
          '</div>' +
        '</div>' +
        '<div class="similar-parts-results">' +
          '<div class="similar-parts-result-head">' +
            '<div class="sp-head-info">' +
              '<strong data-role="candidate-count">候选零件</strong>' +

              '<span class="sp-head-sub">按特征相似度排序</span>' +
            '</div>' +
            '<div class="similar-parts-nav">' +
              '<button type="button" data-role="prev" title="上一个候选">‹ 上一件</button>' +
              '<button type="button" data-role="next" title="下一个候选">下一件 ›</button>' +
            '</div>' +
          '</div>' +
          '<div class="similar-parts-candidates" data-role="candidates"></div>' +
          '<div class="similar-parts-selection">' +
            recommendedTemplateRowMarkup() +
            '<button type="button" class="similar-parts-apply" data-role="apply" disabled>' +
              '<span data-role="apply-label">应用当前分组模板</span>' +
            '</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</section>';
}

function setPanelStatus(panel, text, kind) {
  const status = panel.querySelector('[data-role="status"]');
  status.textContent = text;
  status.className = 'similar-parts-status ' + (kind || '');
}

const FEATURE_INDEX_POLL_DELAY_MS = 1000;
const FEATURE_INDEX_POLL_TIMEOUT_MS = 10 * 60 * 1000;

function featureIndexState(response) {
  return response && response.result ? response.result : response;
}

function featureIndexProgress(state) {
  const completed = Number(state && state.completed || 0);
  const total = Number(state && state.total || 0);
  return total > 0 ? (' ' + completed + '/' + total) : '';
}

function requireOpenPanel(panel) {
  if (!panel.__closing) return;
  const error = new Error('相似件索引准备已取消');
  error.name = 'AbortError';
  throw error;
}

async function waitForFeatureIndex(panel, initialState) {
  const startedAt = Date.now();
  let state = initialState || {};
  while (state.state === 'building' || state.state === 'incomplete') {
    requireOpenPanel(panel);
    if (Date.now() - startedAt >= FEATURE_INDEX_POLL_TIMEOUT_MS) {
      throw new Error('相似件索引准备超时，请点击重试');
    }
    setPanelStatus(panel, '正在准备相似件索引' + featureIndexProgress(state) + '…', 'is-busy');
    await new Promise(function(resolve) {
      window.setTimeout(resolve, FEATURE_INDEX_POLL_DELAY_MS);
    });
    requireOpenPanel(panel);
    state = featureIndexState(await requestJsonPromise(
      'GET', '/api/similar-parts/index/status', null, 30000
    ));
  }
  requireOpenPanel(panel);
  if (state.state !== 'ready') {
    throw new Error((state && state.message) || '相似件索引准备失败，请点击重试');
  }
  return state;
}

async function ensureFeatureIndexReady(panel) {
  const state = featureIndexState(await requestJsonPromise(
    'POST', '/api/similar-parts/index/ensure', '{}', 30000
  ));
  return waitForFeatureIndex(panel, state);
}

function showPanel(panel) {
  if (!dom.similarPartsPanel) return;
  panel.__closing = false;
  dom.similarPartsPanel.style.display = 'flex';
  dom.similarPartsPanel.classList.add('is-open');
  if (dom.similarPartsPanelBackdrop) {
    dom.similarPartsPanelBackdrop.style.display = '';
    dom.similarPartsPanelBackdrop.classList.add('is-open');
  }
  if (panel.__viewer) {
    window.requestAnimationFrame(function() { panel.__viewer.fit(); });
  }
}

function hidePanel() {
  if (!dom.similarPartsPanel) return;
  dom.similarPartsPanel.classList.remove('is-open');
  if (dom.similarPartsPanelBackdrop) {
    dom.similarPartsPanelBackdrop.classList.remove('is-open');
    window.setTimeout(function() {
      if (dom.similarPartsPanel && !dom.similarPartsPanel.classList.contains('is-open')) {
        dom.similarPartsPanel.style.display = 'none';
      }
      if (dom.similarPartsPanelBackdrop && !dom.similarPartsPanelBackdrop.classList.contains('is-open')) {
        dom.similarPartsPanelBackdrop.style.display = 'none';
      }
    }, 180);
  } else {
    dom.similarPartsPanel.style.display = 'none';
  }
}

function closePanel(panel) {
  panel.__closing = true;
  if (activeController) activeController.abort();
  // 关闭只隐藏面板，保留上传结果和已加载模型，方便再次打开继续操作。
  hidePanel();
  if (!panel.__options.autoContinue && !panel.__applied) {
    import('./workflow.js').then(function(workflow) {
      workflow.markProcessWorkflowStepIdle('select_group_template');
    }).catch(function() {});
  }
}

export function openSimilarPartsPanel(options) {
  if (activePanel && document.body.contains(activePanel)) {
    const shouldResume = activePanel.__closing && activePanel.__queryPending;
    // Bug修复#6：重新打开时，若面板处于错误状态则清除，避免用户看到陈旧错误信息
    const statusEl = activePanel.querySelector('[data-role="status"]');
    if (statusEl && statusEl.classList.contains('is-error')) {
      setPanelStatus(activePanel, '当前零件将从固定目录自动加载，点击查询相似零件', '');
    }
    showPanel(activePanel);
    if (shouldResume && !activePanel.__queryRunning && activePanel.__resumeQuery) {
      activePanel.__resumeQuery();
    }
    return activePanel;
  }
  const host = dom.similarPartsPanel && dom.similarPartsPanel.querySelector('.similar-parts-panel-host');
  if (!host) throw new Error('相似零件独立面板未挂载');
  host.innerHTML = panelMarkup();
  const panel = host.firstElementChild;
  panel.__options = options || {};
  panel.__uploadId = '';
  panel.__result = null;
  panel.__candidateIndex = 0;
  panel.__closing = false;
  panel.__applied = false;
  activePanel = panel;
  showPanel(panel);

  const applyButton = panel.querySelector('[data-role="apply"]');

  const workbench = panel.querySelector('[data-role="workbench"]');
  const scaleSwitch = panel.querySelector('.similar-parts-scale-switch');
  panel.querySelector('.similar-parts-close').addEventListener('click', function() { closePanel(panel); });
  if (dom.similarPartsPanelBackdrop) {
    dom.similarPartsPanelBackdrop.onclick = function() { closePanel(panel); };
  }

  async function loadCurrentPart() {
    setPanelStatus(panel, '正在读取固定目录中的当前零件…', 'is-busy');
    const response = await requestJsonPromise(
      'POST', '/api/similar-parts/current', '{}', 60000
    );
    const result = response && response.result ? response.result : response;
    if (!result || !result.uploadId) throw new Error('固定目录中的当前 XML 不可用');
    panel.__uploadId = result.uploadId;
    const sourceLabel = panel.querySelector('[data-role="current-source"]');
    if (sourceLabel) {
      sourceLabel.textContent = 'XML：' + (result.filename || 'AIBasicInfo.xml') +
        ' · STEP：' + (result.stepFilename || 'stepModel.stp');
    }
    return result;
  }

  async function selectCandidate(index) {
    const result = panel.__result;
    if (!result || !result.candidates.length) return;
    const normalized = (index + result.candidates.length) % result.candidates.length;
    panel.__candidateIndex = normalized;
    const candidate = result.candidates[normalized];
    panel.querySelector('[data-role="candidate-name"]').textContent = candidate.name;
    panel.querySelector('[data-role="candidate-rank"]').textContent = '相似零件 #' + candidate.rank;
    panel.querySelector('[data-role="template-name"]').textContent = recommendedTemplateLabel(candidate, candidate.__editedTemplate);
    panel.querySelector('[data-role="template-edited"]').hidden = !candidate.__editedTemplate;
    panel.querySelector('[data-role="edit-template"]').disabled = false;
    panel.querySelectorAll('.similar-part-candidate').forEach(function(card, cardIndex) {
      card.classList.toggle('is-active', cardIndex === normalized);
    });
    applyButton.disabled = true;
    const sequence = ++requestSequence;
    if (activeController) activeController.abort();
    activeController = new AbortController();
    setPanelStatus(panel, '正在加载候选模型…', 'is-busy');
    try {
      const root = await loadGltf(candidate.modelUrl, activeController.signal);
      if (sequence !== requestSequence) { disposeObject(root); return; }
      // Bug修复#3：guard __viewer 防止首次查询失败后重试时 __viewer 还未初始化导致崩溃
      if (panel.__viewer) {
        panel.__viewer.setRoot('candidate', root);
      } else {
        disposeObject(root);
      }
      applyButton.disabled = false;
      setPanelStatus(panel, '候选模型已加载，可应用当前模板', 'is-ok');
    } catch (error) {
      if (panel.__closing || (error && error.name === 'AbortError')) return;
      setPanelStatus(panel, error.message || '候选模型加载失败', 'is-error');
    }
  }

  async function editCurrentTemplate() {
    const candidate = panel.__result && panel.__result.candidates[panel.__candidateIndex];
    if (!candidate) return;
    const button = panel.querySelector('[data-role="edit-template"]');
    button.disabled = true;
    setPanelStatus(panel, '正在读取映射的分组模板…', 'is-busy');
    try {
      const response = await requestJsonPromise('POST', '/api/similar-parts/template', JSON.stringify({
        uploadId: panel.__uploadId, candidateId: candidate.candidateId,
      }), 30000);
      const template = response && response.result ? response.result : response;
      openOptionCardEditor({
        title: template.filename,
        filename: template.filename,
        templateXml: template.xml,
        hideConfidence: true,
        compactStructureOnly: true,
        onSave: function(edited) {
          candidate.__editedTemplate = edited;
          if (panel.__result && panel.__result.candidates[panel.__candidateIndex] === candidate) {
            panel.querySelector('[data-role="template-name"]').textContent = recommendedTemplateLabel(candidate, edited);
            panel.querySelector('[data-role="template-edited"]').hidden = false;
            setPanelStatus(panel, '模板已编辑，点击应用当前分组模板后生效', 'is-ok');
          }
        },
      }, null);
      setPanelStatus(panel, '可编辑当前推荐模板', 'is-ok');
    } catch (error) {
      setPanelStatus(panel, error.message || '分组模板读取失败', 'is-error');
    } finally {
      button.disabled = false;
    }
  }

  // 自动查询函数（开面即触发，错误时可通过重试按钮再次调用）
  async function runQuery() {
    if (panel.__queryRunning) return;
    panel.__queryRunning = true;
    panel.__queryPending = true;
    const retryBtn = panel.querySelector('[data-role="retry"]');
    if (retryBtn) retryBtn.style.display = 'none';
    applyButton.disabled = true;
    setPanelStatus(panel, '正在提取模型特征并检索相似零件…', 'is-busy');
    try {
      await loadCurrentPart();
      requireOpenPanel(panel);
      await ensureFeatureIndexReady(panel);
      let response;
      try {
        response = await requestJsonPromise('POST', '/api/similar-parts/query', JSON.stringify({
          uploadId: panel.__uploadId,
        }), 120000);
      } catch (error) {
        if (!error || error.errorCode !== 'FEATURE_INDEX_BUILDING') throw error;
        await waitForFeatureIndex(panel, featureIndexState(error.payload));
        response = await requestJsonPromise('POST', '/api/similar-parts/query', JSON.stringify({
          uploadId: panel.__uploadId,
        }), 120000);
      }
      requireOpenPanel(panel);
      const result = response && response.result ? response.result : response;
      panel.__result = result;
      panel.__candidateIndex = 0;
      workbench.hidden = false;
      panel.querySelector('[data-role="candidate-count"]').textContent =
        'Top ' + result.candidates.length + ' 候选';
      panel.querySelector('[data-role="current-name"]').textContent = result.current.name;
      const cards = result.candidates.map(function(candidate, index) {
        const pct = Math.round(Number(candidate.similarity || 0) * 100);
        const level = pct >= 90 ? 'high' : pct >= 70 ? 'medium' : 'low';
        const rankAttr = String(candidate.rank);
        const rankLabel = candidate.rank < 10 ? ('0' + candidate.rank) : rankAttr;
        const category = escapeHtml(candidate.labelZh || candidate.geometryClass || '');
        const tmpl = escapeHtml(candidate.template.name);
        return '<button type="button" class="similar-part-candidate" data-index="' + index + '">' +
          '<span class="similar-part-rank" data-rank="' + rankAttr + '">' + rankLabel + '</span>' +
          '<span class="similar-part-copy">' +
            '<strong>' + escapeHtml(candidate.name) + '</strong>' +
            '<small>' + (category ? '<span class="sp-cat-chip">' + category + '</span>' : '') +
              '<span class="sp-tmpl-sub">' + tmpl + '</span></small>' +
          '</span>' +
          '<span class="similar-part-score" data-level="' + level + '">' + pct + '%</span>' +
        '</button>';
      }).join('');
      panel.querySelector('[data-role="candidates"]').innerHTML = cards;
      panel.querySelectorAll('.similar-part-candidate').forEach(function(card) {
        card.addEventListener('click', function() { selectCandidate(Number(card.dataset.index)); });
      });
      if (!panel.__viewer) panel.__viewer = createViewer(panel.querySelector('[data-role="canvas"]'));
      setPanelStatus(panel, '正在生成当前零件三维预览…', 'is-busy');
      const sequence = ++requestSequence;
      if (activeController) activeController.abort();
      activeController = new AbortController();
      const currentRoot = await loadGltf(result.current.modelUrl, activeController.signal);
      if (sequence !== requestSequence) { disposeObject(currentRoot); return; }
      panel.__viewer.setRoot('current', currentRoot);
      await selectCandidate(0);
      panel.__queryPending = false;
    } catch (error) {
      if (panel.__closing || (error && error.name === 'AbortError')) return;
      panel.__queryPending = false;
      let errMsg = error.message || '相似零件查询失败';
      setPanelStatus(panel, errMsg, 'is-error');
      addErrorMsg(errMsg);
      // 出错后显示重试按钮
      if (retryBtn) retryBtn.style.display = '';
    } finally {
      panel.__queryRunning = false;
      if (panel.__queryPending && !panel.__closing) panel.__resumeQuery();
    }
  }
  panel.__resumeQuery = runQuery;

  // 重试按钮事件
  const retryBtn = panel.querySelector('[data-role="retry"]');
  if (retryBtn) retryBtn.addEventListener('click', function() { runQuery(); });


  panel.querySelector('[data-role="edit-template"]').addEventListener('click', editCurrentTemplate);
  panel.querySelector('[data-role="prev"]').addEventListener('click', function() { selectCandidate(panel.__candidateIndex - 1); });
  panel.querySelector('[data-role="next"]').addEventListener('click', function() { selectCandidate(panel.__candidateIndex + 1); });
  panel.querySelector('[data-role="fit"]').addEventListener('click', function() { if (panel.__viewer) panel.__viewer.fit(); });
  scaleSwitch.querySelectorAll('[data-scale-mode]').forEach(function(button) {
    button.addEventListener('click', function() {
      const mode = String(button.dataset.scaleMode || DEFAULT_SCALE_MODE);
      if (panel.__viewer) panel.__viewer.setScaleMode(mode);
      scaleSwitch.title = scaleModeLabel(mode);
      scaleSwitch.querySelectorAll('[data-scale-mode]').forEach(function(item) {
        const active = item.dataset.scaleMode === mode;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    });
  });
  scaleSwitch.querySelector('[data-scale-mode="shape"]').classList.add('is-active');
  scaleSwitch.title = scaleModeLabel(DEFAULT_SCALE_MODE);

  applyButton.addEventListener('click', async function() {
    const candidate = panel.__result && panel.__result.candidates[panel.__candidateIndex];
    if (!candidate) return;
    applyButton.disabled = true;
    // 应用中：显示 spinner
    const applyLabel = applyButton.querySelector('[data-role="apply-label"]');
    if (applyLabel) applyLabel.textContent = '正在应用…';
    const applySpinner = document.createElement('span');
    applySpinner.className = 'sp-spinner';
    applyButton.insertBefore(applySpinner, applyButton.firstChild);
    const templateName = (candidate.__editedTemplate && candidate.__editedTemplate.filename) || candidate.template.name;
    setPanelStatus(panel, '正在写入并应用 ' + templateName + ' …', 'is-busy');
    try {
      await requestJsonPromise('POST', '/api/similar-parts/apply-template', JSON.stringify(
        buildTemplateApplyPayload(panel.__uploadId, candidate, candidate.__editedTemplate)
      ), 130000);
      setPanelStatus(panel, '模板已应用，工作流进入第 2 步', 'is-ok');
      // 成功态
      const sp2 = applyButton.querySelector('.sp-spinner');
      if (sp2) sp2.remove();
      if (applyLabel) applyLabel.textContent = '✓ 已应用，进入第 2 步 →';
      applyButton.classList.add('is-applied');
      applyButton.disabled = true;
      panel.__applied = true;
      addBotMsg('已应用相似零件"' + candidate.name + '"的分组模板：' + templateName);
      setStatus('ok', '相似零件模板应用完成');
      const workflow = await import('./workflow.js');
      workflow.markProcessWorkflowStepDone('select_group_template');
    } catch (error) {
      const sp2 = applyButton.querySelector('.sp-spinner');
      if (sp2) sp2.remove();
      if (applyLabel) applyLabel.textContent = '应用当前分组模板';
      applyButton.disabled = false;
      setPanelStatus(panel, error.message || '分组模板应用失败', 'is-error');
      addErrorMsg(error.message || '分组模板应用失败');
    }
  });

  // 开面自动触发查询
  runQuery();
  return panel;

}
