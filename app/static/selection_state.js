(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DistrictSelectionState = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function identity(county, district) {
    return district ? { county, district } : null;
  }

  function sameIdentity(value, county, district) {
    return Boolean(value && value.county === county && value.district === district);
  }

  function reconcileIdentity(value, rows) {
    return value && rows.some(row => sameIdentity(value, row.county, row.district)) ? value : null;
  }

  function displayedIdentity(hoveredDistrict, selectedDistrict, isDistrictPinned) {
    return isDistrictPinned ? selectedDistrict : hoveredDistrict;
  }

  function canApplyDetail(requestIdentity, hoveredDistrict, selectedDistrict, isDistrictPinned) {
    const displayed = displayedIdentity(hoveredDistrict, selectedDistrict, isDistrictPinned);
    return Boolean(displayed && sameIdentity(displayed, requestIdentity.county, requestIdentity.district));
  }

  function identityFromElement(element, viewport) {
    const path = element && typeof element.closest === "function" ? element.closest(".district-shape") : null;
    return path && viewport && viewport.contains(path) ? identity(path.dataset.county, path.dataset.district) : null;
  }

  function isCurrent(requestVersion, currentVersion, requestScope, currentScope) {
    return requestVersion === currentVersion && requestScope === currentScope;
  }

  return Object.freeze({ identity, sameIdentity, reconcileIdentity, displayedIdentity, canApplyDetail, identityFromElement, isCurrent });
}));
