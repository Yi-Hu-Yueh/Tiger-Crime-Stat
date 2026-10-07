(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MapNavigation = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MIN_ZOOM = 1;
  const MAX_ZOOM = 6;
  const ZOOM_STEP = 1.15;
  const OVERSCAN_RATIO = 1.5;
  const PAN_THRESHOLD = 4;

  function clamp(value) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  }

  function nextZoom(current, deltaY) {
    if (!deltaY) return clamp(current);
    return clamp(deltaY < 0 ? current * ZOOM_STEP : current / ZOOM_STEP);
  }

  function wheelResult(current, event) {
    if (!event.ctrlKey || !event.deltaY) return { handled: false, zoom: current };
    return { handled: true, zoom: nextZoom(current, event.deltaY) };
  }

  function canvasSize(viewportWidth, viewportHeight, zoom) {
    const value = clamp(zoom);
    return {
      width: Math.max(1, viewportWidth) * OVERSCAN_RATIO * value,
      height: Math.max(1, viewportHeight) * OVERSCAN_RATIO * value,
    };
  }

  function centeredScroll(viewportWidth, viewportHeight, canvasWidth, canvasHeight) {
    return {
      left: Math.max(0, (canvasWidth - viewportWidth) / 2),
      top: Math.max(0, (canvasHeight - viewportHeight) / 2),
    };
  }

  function anchoredScroll(scrollLeft, scrollTop, pointerX, pointerY, oldZoom, newZoom) {
    const ratio = clamp(newZoom) / clamp(oldZoom);
    return {
      left: Math.max(0, (scrollLeft + pointerX) * ratio - pointerX),
      top: Math.max(0, (scrollTop + pointerY) * ratio - pointerY),
    };
  }

  function passedPanThreshold(startX, startY, currentX, currentY) {
    return Math.hypot(currentX - startX, currentY - startY) >= PAN_THRESHOLD;
  }

  function panPosition(startLeft, startTop, startX, startY, currentX, currentY, maxLeft, maxTop) {
    return {
      left: Math.min(Math.max(0, maxLeft), Math.max(0, startLeft - (currentX - startX))),
      top: Math.min(Math.max(0, maxTop), Math.max(0, startTop - (currentY - startY))),
    };
  }

  return Object.freeze({ MIN_ZOOM, MAX_ZOOM, ZOOM_STEP, OVERSCAN_RATIO, PAN_THRESHOLD, clamp, nextZoom, wheelResult, canvasSize, centeredScroll, anchoredScroll, passedPanThreshold, panPosition });
}));
