import assert from "node:assert/strict";
import { test } from "node:test";
import { frameFromBox, splitViewports, translationToOrigin } from "../web/align.js";

test("offset bounding box translates so the center sits at the origin", () => {
  const t = translationToOrigin([100, 200, 300], [140, 260, 380]);
  assert.deepEqual(t, { x: -120, y: -230, z: -340 });
});

test("already-centered box needs no translation", () => {
  const t = translationToOrigin([-25, -25, -12.5], [25, 25, 12.5]);
  assert.deepEqual(t, { x: 0, y: 0, z: 0 });
});

test("split viewports use CSS pixels so Three.js can apply devicePixelRatio", () => {
  const panes = splitViewports(1496, 432);
  assert.deepEqual(panes.left, [0, 0, 748, 432]);
  assert.deepEqual(panes.right, [748, 0, 748, 432]);
  assert.equal(panes.aspect, 748 / 432);
  assert.notEqual(panes.left[2], (1496 * 1.25) / 2);
});

test("each part is framed around its own bounding-box center", () => {
  const dir = [0.9, -0.95, 0.55];
  const small = frameFromBox([-10, -10, -5], [10, 10, 5], dir, 35);
  const large = frameFromBox([80, -40, 0], [280, 160, 120], dir, 35);
  assert.deepEqual(small.target, [0, 0, 0]);
  assert.deepEqual(large.target, [180, 60, 60]);
  assert.ok(large.distance > small.distance * 5);
});

test("applying the translation moves the center to origin", () => {
  const min = [80, -10, 5];
  const max = [120, 50, 35];
  const t = translationToOrigin(min, max);
  const cx = (min[0] + t.x + max[0] + t.x) / 2;
  const cy = (min[1] + t.y + max[1] + t.y) / 2;
  const cz = (min[2] + t.z + max[2] + t.z) / 2;
  assert.equal(cx, 0);
  assert.equal(cy, 0);
  assert.equal(cz, 0);
});
