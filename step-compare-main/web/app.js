import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { frameFromBox, splitViewports, translationToOrigin } from "./align.js";

const COLOR = { a: 0x8aa0b8, b: 0xc9894a };
const slots = { a: null, b: null };
const requests = {
  a: { sequence: 0, controller: null },
  b: { sequence: 0, controller: null },
};
let mode = "split";

const canvas = document.getElementById("c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0xf7f8fb, 1);
renderer.localClippingEnabled = true;

const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
const ISO_DIR = new THREE.Vector3(0.9, -0.95, 0.55).normalize();
const orbitOrigin = new THREE.Vector3();
let fittedDist = 1;
let lastW = 0;
let lastH = 0;

const scenes = {
  a: makeScene(),
  b: makeScene(),
  overlay: makeScene(),
};

function makeScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf7f8fb);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a9098, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.05);
  key.position.set(0.8, 1.1, 1.4);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xd5e4ff, 0.45);
  fill.position.set(-1.0, 0.3, 0.5);
  scene.add(fill);
  return scene;
}

function setStatus(text) {
  document.getElementById("status").textContent = text || "";
}

function disposeMaterial(material, seen) {
  if (!material || seen.has(material)) return;
  seen.add(material);
  for (const value of Object.values(material)) {
    if (value && value.isTexture) value.dispose();
  }
  material.dispose();
}

function disposeObject(root, seen = new Set()) {
  if (!root) return;
  root.traverse((obj) => {
    if (obj.geometry && !seen.has(obj.geometry)) {
      seen.add(obj.geometry);
      obj.geometry.dispose();
    }
    const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
    materials.forEach((material) => disposeMaterial(material, seen));
  });
}

function paintModel(root, hex) {
  root.traverse((obj) => {
    if (!obj.isMesh) return;
    if (!obj.geometry.attributes.normal) obj.geometry.computeVertexNormals();
    let material = obj.userData.stepViewerMaterial;
    if (!material) {
      material = new THREE.MeshLambertMaterial({ side: THREE.DoubleSide, vertexColors: false });
      obj.userData.stepViewerMaterial = material;
      obj.material = material;
    }
    material.color.setHex(hex);
    material.transparent = mode === "overlay";
    material.opacity = mode === "overlay" ? 0.55 : 1;
    material.depthWrite = mode !== "overlay";
    material.needsUpdate = true;
  });
}

function removeSlotObjects(slot) {
  const current = slots[slot];
  if (!current) return;
  for (const scene of Object.values(scenes)) {
    if (current.root) scene.remove(current.root);
    if (current.copy) scene.remove(current.copy);
  }
  const seen = new Set();
  disposeObject(current.root, seen);
  disposeObject(current.copy, seen);
}

function boundsOf(slot) {
  if (!slots[slot]?.root) return null;
  return new THREE.Box3().setFromObject(slots[slot].root);
}

function centerAtOrigin(root) {
  root.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const t = translationToOrigin(box.min.toArray(), box.max.toArray());
  root.position.x += t.x;
  root.position.y += t.y;
  root.position.z += t.z;
  root.updateWorldMatrix(true, true);
}

function viewAspect() {
  const w = Math.max(canvas.clientWidth, 1);
  const h = Math.max(canvas.clientHeight, 1);
  const split = mode === "split" && slots.a && slots.b;
  return split ? splitViewports(w, h).aspect : w / h;
}

function viewDir() {
  const dir = new THREE.Vector3().subVectors(camera.position, controls.target);
  if (dir.lengthSq() < 1e-12) return ISO_DIR.clone();
  return dir.normalize();
}

function currentZoom() {
  const d = camera.position.distanceTo(controls.target);
  return fittedDist > 1e-6 ? d / fittedDist : 1;
}

function applyFrame(box, aspect, dir, zoom) {
  const pan = new THREE.Vector3().subVectors(controls.target, orbitOrigin);
  const frame = frameFromBox(
    box.min.toArray(),
    box.max.toArray(),
    dir.toArray(),
    camera.fov,
    zoom,
  );
  camera.aspect = aspect;
  camera.near = Math.max(frame.distance / 100, 0.01);
  camera.far = Math.max(frame.distance * 40, 100);
  camera.updateProjectionMatrix();
  camera.up.set(0, 0, 1);
  camera.position.set(
    frame.position[0] + pan.x,
    frame.position[1] + pan.y,
    frame.position[2] + pan.z,
  );
  camera.lookAt(frame.target[0] + pan.x, frame.target[1] + pan.y, frame.target[2] + pan.z);
}

function fitCamera() {
  resize();
  const boxes = ["a", "b"].map(boundsOf).filter(Boolean);
  if (!boxes.length) return;
  const box = boxes[0].clone();
  boxes.slice(1).forEach((b) => box.union(b));
  const frame = frameFromBox(
    box.min.toArray(),
    box.max.toArray(),
    ISO_DIR.toArray(),
    camera.fov,
    1,
  );
  fittedDist = frame.distance;
  camera.up.set(0, 0, 1);
  camera.aspect = viewAspect();
  camera.near = Math.max(frame.distance / 100, 0.01);
  camera.far = Math.max(frame.distance * 40, 100);
  camera.updateProjectionMatrix();
  camera.position.set(...frame.position);
  controls.target.set(...frame.target);
  orbitOrigin.copy(controls.target);
  controls.update();
}

function place(slot, root, info) {
  removeSlotObjects(slot);
  centerAtOrigin(root);
  const copy = root.clone(true);
  const importedMaterials = new Set();
  root.traverse((obj) => {
    const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
    materials.filter(Boolean).forEach((material) => importedMaterials.add(material));
  });
  slots[slot] = { root, copy, info };
  paintModel(root, COLOR[slot]);
  paintModel(copy, COLOR[slot]);
  const disposed = new Set();
  importedMaterials.forEach((material) => disposeMaterial(material, disposed));
  scenes[slot].add(root);
  scenes.overlay.add(copy);
  document.querySelector(`[data-name="${slot}"]`).textContent = info.name;
  document.querySelector(`[data-meta="${slot}"]`).textContent =
    `${info.extents.map((v) => v.toFixed(1)).join(" × ")} mm  ·  ${info.faces} 面`;
  document.querySelector(`[data-clear="${slot}"]`).hidden = false;
  document.getElementById(`slot-${slot}`).classList.add("loaded");
  updateChrome();
  fitCamera();
}

function clearSlot(slot) {
  const request = requests[slot];
  request.sequence += 1;
  request.controller?.abort();
  request.controller = null;
  removeSlotObjects(slot);
  slots[slot] = null;
  document.querySelector(`[data-name="${slot}"]`).textContent =
    slot === "a" ? "点击或拖入 STEP" : "点击或拖入 STEP（可选）";
  document.querySelector(`[data-meta="${slot}"]`).textContent = "";
  document.querySelector(`[data-clear="${slot}"]`).hidden = true;
  document.getElementById(`slot-${slot}`).classList.remove("loaded");
  const input = document.querySelector(`input[data-slot="${slot}"]`);
  if (input) input.value = "";
  updateChrome();
  fitCamera();
}

function updateChrome() {
  const both = slots.a && slots.b;
  const stage = document.getElementById("stage");
  stage.classList.toggle("overlay", mode === "overlay" && both);
  stage.classList.toggle("single", !both);
  document.getElementById("label-a").textContent = slots.a ? `A  ${slots.a.info.name}` : "A";
  document.getElementById("label-b").textContent = slots.b ? `B  ${slots.b.info.name}` : "B";
  if (slots.a?.root) paintModel(slots.a.root, COLOR.a);
  if (slots.a?.copy) paintModel(slots.a.copy, COLOR.a);
  if (slots.b?.root) paintModel(slots.b.root, COLOR.b);
  if (slots.b?.copy) paintModel(slots.b.copy, COLOR.b);
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
  });
}

async function responseError(response, fallback) {
  const text = await response.text();
  let detail = null;
  try {
    detail = JSON.parse(text);
  } catch {
    // A proxy or server error may return HTML/plain text; keep it user-safe.
  }
  const message = detail?.message || detail?.detail || fallback;
  const error = new Error(message);
  error.code = detail?.code || `HTTP_${response.status}`;
  return error;
}

function parseGltf(loader, buffer) {
  return new Promise((resolve, reject) => {
    loader.parse(buffer, "", resolve, reject);
  });
}

function isCurrentRequest(slot, sequence) {
  return requests[slot].sequence === sequence;
}

async function upload(slot, file) {
  const label = document.getElementById(`slot-${slot}`);
  const request = requests[slot];
  request.controller?.abort();
  const controller = new AbortController();
  request.controller = controller;
  const sequence = ++request.sequence;
  label.classList.add("busy");
  setStatus(`正在读取 ${file.name} …`);
  const body = new FormData();
  body.append("file", file);
  try {
    const metadataResponse = await fetch("/api/tessellate/v2", {
      method: "POST",
      body,
      signal: controller.signal,
    });
    if (!metadataResponse.ok) throw await responseError(metadataResponse, "打开失败");
    const info = await metadataResponse.json();
    if (!isCurrentRequest(slot, sequence)) return;

    const glbResponse = await fetch(info.glb_url, { signal: controller.signal });
    if (!glbResponse.ok) throw await responseError(glbResponse, "模型下载失败");
    const buffer = await glbResponse.arrayBuffer();
    if (!isCurrentRequest(slot, sequence)) return;

    const loader = new GLTFLoader();
    const gltf = await parseGltf(loader, buffer);
    if (!isCurrentRequest(slot, sequence)) {
      disposeObject(gltf.scene);
      return;
    }
    place(slot, gltf.scene, info);
    setStatus(slots.a && slots.b ? "两个模型已打开，可分屏或叠加比对" : "已打开");
  } catch (err) {
    if (err?.name === "AbortError") return;
    setStatus(err?.message || "打开失败");
  } finally {
    if (isCurrentRequest(slot, sequence)) {
      request.controller = null;
      label.classList.remove("busy");
    }
  }
}

function onFiles(slot, files) {
  const file = files && files[0];
  if (!file) return;
  upload(slot, file);
}

document.querySelectorAll("input[type=file]").forEach((input) => {
  input.addEventListener("change", () => {
    onFiles(input.dataset.slot, input.files);
    input.value = "";
  });
});
document.querySelectorAll(".slot").forEach((slotEl) => {
  slotEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    slotEl.classList.add("loaded");
  });
  slotEl.addEventListener("dragleave", () => {
    if (!slots[slotEl.id.replace("slot-", "")]) slotEl.classList.remove("loaded");
  });
  slotEl.addEventListener("drop", (e) => {
    e.preventDefault();
    const slot = slotEl.id.replace("slot-", "");
    onFiles(slot, e.dataTransfer.files);
  });
});
document.querySelectorAll("[data-clear]").forEach((btn) => {
  btn.addEventListener("click", () => {
    clearSlot(btn.dataset.clear);
    setStatus("");
  });
});
document.querySelectorAll("[data-mode]").forEach((btn) => {
  btn.addEventListener("click", () => {
    mode = btn.dataset.mode;
    updateChrome();
    fitCamera();
  });
});
document.getElementById("fit").addEventListener("click", fitCamera);

function resize() {
  const stage = document.getElementById("stage");
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  if (w === lastW && h === lastH) return;
  lastW = w;
  lastH = h;
  renderer.setSize(w, h, false);
}

function render() {
  requestAnimationFrame(render);
  resize();
  controls.update();
  const w = Math.max(canvas.clientWidth, 1);
  const h = Math.max(canvas.clientHeight, 1);
  const both = slots.a && slots.b;
  renderer.setScissorTest(false);
  renderer.clear();

  if (mode === "overlay" && both) {
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, w, h);
    renderer.render(scenes.overlay, camera);
    return;
  }

  if (!both) {
    const key = slots.a ? "a" : slots.b ? "b" : "a";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, w, h);
    renderer.render(scenes[key], camera);
    return;
  }

  renderer.setScissorTest(true);
  const panes = splitViewports(w, h);
  const dir = viewDir();
  const zoom = currentZoom();
  const snap = {
    position: camera.position.clone(),
    target: controls.target.clone(),
    near: camera.near,
    far: camera.far,
    aspect: camera.aspect,
  };

  applyFrame(boundsOf("a"), panes.aspect, dir, zoom);
  renderer.setViewport(...panes.left);
  renderer.setScissor(...panes.left);
  renderer.render(scenes.a, camera);

  applyFrame(boundsOf("b"), panes.aspect, dir, zoom);
  renderer.setViewport(...panes.right);
  renderer.setScissor(...panes.right);
  renderer.render(scenes.b, camera);

  camera.position.copy(snap.position);
  controls.target.copy(snap.target);
  camera.near = snap.near;
  camera.far = snap.far;
  camera.aspect = snap.aspect;
  camera.up.set(0, 0, 1);
  camera.lookAt(snap.target);
  camera.updateProjectionMatrix();
}

window.addEventListener("resize", resize);
resize();
updateChrome();
render();
