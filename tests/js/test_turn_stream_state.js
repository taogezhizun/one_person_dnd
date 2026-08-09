const test = require("node:test");
const assert = require("node:assert/strict");

const { createTerminalTracker } = require("../../src/one_person_dnd/web/static/js/turn_stream_state.js");

test("delta followed by EOF is a retryable stream failure", () => {
  const tracker = createTerminalTracker();
  tracker.observe("delta");

  assert.throws(
    () => tracker.assertClosed(),
    /连接提前结束/,
  );
});

test("final and error are both terminal SSE events", () => {
  for (const event of ["final", "error"]) {
    const tracker = createTerminalTracker();
    tracker.observe(event);
    assert.doesNotThrow(() => tracker.assertClosed());
  }
});
