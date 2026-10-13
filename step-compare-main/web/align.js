export function translationToOrigin(min, max) {
  const axis = (a, b) => -(a + b) / 2 + 0;
  return {
    x: axis(min[0], max[0]),
    y: axis(min[1], max[1]),
    z: axis(min[2], max[2]),
  };
}

export function frameDistance(maxSize, fovDeg, padding = 1.5) {
  const fov = (fovDeg * Math.PI) / 180;
  return ((Math.max(maxSize, 1) / 2) / Math.tan(fov / 2)) * padding;
}

export function frameFromBox(min, max, dir, fovDeg, zoom = 1) {
  const size = [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  const target = [
    (min[0] + max[0]) / 2 + 0,
    (min[1] + max[1]) / 2 + 0,
    (min[2] + max[2]) / 2 + 0,
  ];
  const distance = frameDistance(Math.max(size[0], size[1], size[2], 1), fovDeg) * zoom;
  const len = Math.hypot(dir[0], dir[1], dir[2]) || 1;
  return {
    target,
    position: [
      target[0] + (dir[0] / len) * distance,
      target[1] + (dir[1] / len) * distance,
      target[2] + (dir[2] / len) * distance,
    ],
    distance,
  };
}

export function splitViewports(width, height) {
  const w = Math.max(width, 1);
  const h = Math.max(height, 1);
  const half = w / 2;
  return {
    aspect: half / h,
    left: [0, 0, half, h],
    right: [half, 0, w - half, h],
  };
}
