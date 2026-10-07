(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MapProjection = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function flatten(value, result = []) {
    if (Array.isArray(value) && value.length >= 2 && typeof value[0] === "number") result.push(value);
    else if (Array.isArray(value)) value.forEach(item => flatten(item, result));
    return result;
  }

  function fit(features, viewWidth, viewHeight) {
    const points = features.flatMap(feature => flatten(feature.geometry.coordinates));
    if (!points.length) throw new Error("cannot fit empty geography");
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    points.forEach(point => {
      minX = Math.min(minX, point[0]);
      maxX = Math.max(maxX, point[0]);
      minY = Math.min(minY, point[1]);
      maxY = Math.max(maxY, point[1]);
    });
    const padding = Math.max(24, Math.min(48, Math.min(viewWidth, viewHeight) * 0.08));
    const drawableWidth = Math.max(1, viewWidth - padding * 2);
    const drawableHeight = Math.max(1, viewHeight - padding * 2);
    const geometryWidth = Math.max(maxX - minX, 0.001);
    const geometryHeight = Math.max(maxY - minY, 0.001);
    const scale = Math.min(drawableWidth / geometryWidth, drawableHeight / geometryHeight);
    const fittedWidth = geometryWidth * scale;
    const fittedHeight = geometryHeight * scale;
    const offsetX = (viewWidth - fittedWidth) / 2;
    const offsetY = (viewHeight - fittedHeight) / 2;
    return {
      viewWidth,
      viewHeight,
      padding,
      fittedWidth,
      fittedHeight,
      centerX: offsetX + fittedWidth / 2,
      centerY: offsetY + fittedHeight / 2,
      project(point) {
        return [offsetX + (point[0] - minX) * scale, offsetY + (maxY - point[1]) * scale];
      },
    };
  }

  return Object.freeze({ flatten, fit });
}));
