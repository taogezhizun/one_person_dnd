(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DndTurnStreamState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  function translate(key) {
    if (root.DndI18n && typeof root.DndI18n.t === "function") return root.DndI18n.t(key);
    // Standalone CommonJS compatibility; the browser always uses the request catalog.
    if (key === "game.error.stream_ended") {
      return "\u7f51\u7edc\u8fde\u63a5\u63d0\u524d\u7ed3\u675f\uff0c\u884c\u52a8\u8349\u7a3f\u5df2\u4fdd\u7559\uff0c\u8bf7\u91cd\u8bd5\u3002";
    }
    return key;
  }

  function createTerminalTracker() {
    let terminalEvent = "";

    return {
      observe(eventName) {
        if (eventName === "final" || eventName === "error") terminalEvent = eventName;
      },
      assertClosed() {
        if (!terminalEvent) {
          throw new Error(translate("game.error.stream_ended"));
        }
      },
    };
  }

  return { createTerminalTracker };
});
