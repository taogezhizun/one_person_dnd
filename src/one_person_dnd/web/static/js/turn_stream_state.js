(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DndTurnStreamState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function createTerminalTracker() {
    let terminalEvent = "";

    return {
      observe(eventName) {
        if (eventName === "final" || eventName === "error") terminalEvent = eventName;
      },
      assertClosed() {
        if (!terminalEvent) {
          throw new Error("网络连接提前结束，行动草稿已保留，请重试。");
        }
      },
    };
  }

  return { createTerminalTracker };
});
