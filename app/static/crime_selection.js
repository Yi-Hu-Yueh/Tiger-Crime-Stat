(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CrimeSelectionState = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalize(selected, order) {
    const chosen = new Set(selected);
    return order.filter(value => chosen.has(value));
  }

  function selectAll(order) {
    return [...order];
  }

  function toggle(selected, value, order) {
    const current = normalize(selected, order);
    if (current.includes(value)) {
      return current.length === 1 ? current : current.filter(item => item !== value);
    }
    return normalize([...current, value], order);
  }

  function isAll(selected, order) {
    return normalize(selected, order).length === order.length;
  }

  function summary(selected, order) {
    const current = normalize(selected, order);
    return isAll(current, order) ? `全部案類（${order.length}）` : `${current.join("、")}（${current.length}）`;
  }

  return Object.freeze({ normalize, selectAll, toggle, isAll, summary });
}));
