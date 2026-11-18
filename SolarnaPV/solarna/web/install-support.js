(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SOLARNA_INSTALL = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function isIosDevice(navigatorLike) {
    const navigatorValue = navigatorLike || {};
    const userAgent = String(navigatorValue.userAgent || "");
    const platform = String(navigatorValue.platform || "");
    return /iPad|iPhone|iPod/i.test(userAgent) ||
      (platform === "MacIntel" && Number(navigatorValue.maxTouchPoints) > 1);
  }

  function isStandalone(navigatorLike, matchMedia) {
    if (navigatorLike && navigatorLike.standalone === true) return true;
    if (typeof matchMedia !== "function") return false;
    return matchMedia("(display-mode: standalone)").matches === true;
  }

  function shouldOfferIosInstall(nativeShell, navigatorLike, matchMedia) {
    return nativeShell !== true &&
      isIosDevice(navigatorLike) &&
      !isStandalone(navigatorLike, matchMedia);
  }

  return Object.freeze({
    isIosDevice,
    isStandalone,
    shouldOfferIosInstall
  });
});
