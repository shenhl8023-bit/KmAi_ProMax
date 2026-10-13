export const DEFAULT_SCALE_MODE = 'shape';
export const NORMALIZED_LONGEST_EXTENT = 100;

export function cameraFitDistance(radius, aspect, verticalFov) {
  const verticalHalfAngle = verticalFov * Math.PI / 360;
  const horizontalHalfAngle = Math.atan(Math.tan(verticalHalfAngle) * Math.max(aspect, 0.01));
  return Math.max(radius, 1) * 1.1 / Math.sin(Math.min(verticalHalfAngle, horizontalHalfAngle));
}

export function uniformScaleForExtents(extents, mode) {
  if (mode !== 'shape') return 1;
  const longest = Math.max.apply(null, (extents || []).map(function(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.abs(number) : 0;
  }));
  return longest > 0 ? NORMALIZED_LONGEST_EXTENT / longest : 1;
}

export function scaleModeLabel(mode) {
  return mode === 'actual' ? '真实尺寸' : '形状对比 · 尺寸已归一化';
}
