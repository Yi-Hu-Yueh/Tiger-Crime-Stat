(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DashboardLayoutState = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_VERTICAL_RATIO = 0.54;
  const DEFAULT_HORIZONTAL_RATIO = 0.62;

  function numberOr(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clampRatio(ratio, total, minimumFirst, minimumSecond, fallback = 0.5) {
    const size = Math.max(0, numberOr(total, 0));
    if (!size) return fallback;
    const lower = Math.min(0.5, Math.max(0, minimumFirst / size));
    const upper = Math.max(0.5, Math.min(1, 1 - minimumSecond / size));
    return Math.min(upper, Math.max(lower, numberOr(ratio, fallback)));
  }

  function vertical(ratio, total) {
    const size = Math.max(0, numberOr(total, 0));
    const mapMinimum = Math.max(320, size * 0.30);
    const detailMinimum = Math.max(300, size * 0.30);
    return clampRatio(ratio, size, mapMinimum, detailMinimum, DEFAULT_VERTICAL_RATIO);
  }

  function horizontal(ratio, total) {
    const size = Math.max(0, numberOr(total, 0));
    const upperMinimum = Math.max(300, size * 0.45);
    const lowerMinimum = Math.max(180, size * 0.25);
    return clampRatio(ratio, size, upperMinimum, lowerMinimum, DEFAULT_HORIZONTAL_RATIO);
  }

  function fromPosition(position, total, orientation) {
    const size = Math.max(1, numberOr(total, 1));
    const raw = numberOr(position, 0) / size;
    return orientation === "horizontal" ? horizontal(raw, size) : vertical(raw, size);
  }

  function create(verticalRatio = DEFAULT_VERTICAL_RATIO, horizontalRatio = DEFAULT_HORIZONTAL_RATIO) {
    return {
      verticalRatio: numberOr(verticalRatio, DEFAULT_VERTICAL_RATIO),
      horizontalRatio: numberOr(horizontalRatio, DEFAULT_HORIZONTAL_RATIO),
      verticalMode: null,
      horizontalMode: null,
    };
  }

  function toggleVertical(layout, requestedMode) {
    if (!["left", "right"].includes(requestedMode)) return { ...layout };
    return { ...layout, verticalMode: layout.verticalMode === requestedMode ? null : requestedMode };
  }

  function toggleHorizontal(layout, requestedMode) {
    if (!["up", "down"].includes(requestedMode)) return { ...layout };
    return { ...layout, horizontalMode: layout.horizontalMode === requestedMode ? null : requestedMode };
  }

  return Object.freeze({
    DEFAULT_VERTICAL_RATIO,
    DEFAULT_HORIZONTAL_RATIO,
    clampRatio,
    vertical,
    horizontal,
    fromPosition,
    create,
    toggleVertical,
    toggleHorizontal,
  });
}));
