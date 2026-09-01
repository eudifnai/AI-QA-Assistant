// @vitest-environment node

import { describe, expect, it } from "vitest";

import {
  assertMinimumWindowNavigationLayout,
  MINIMUM_WINDOW_NAVIGATION_TEST_IDS,
} from "./minimum-window-layout.cts";

function createVisibleLayout() {
  return {
    viewportWidth: 744,
    viewportHeight: 481,
    documentScrollWidth: 744,
    controls: MINIMUM_WINDOW_NAVIGATION_TEST_IDS.map((testId, index) => {
      const row = Math.floor(index / 6);
      const column = index % 6;
      return {
        testId,
        left: 12 + column * 104,
        right: 96 + column * 104,
        top: 8 + row * 40,
        bottom: 40 + row * 40,
      };
    }),
  };
}

describe("minimum Electron window navigation layout", () => {
  it("accepts wrapped navigation controls that remain inside the minimum viewport", () => {
    expect(() => assertMinimumWindowNavigationLayout(createVisibleLayout())).not.toThrow();
  });

  it("rejects the previously observed left-clipped controls at 760px", () => {
    const layout = createVisibleLayout();
    const status = layout.controls[0];
    if (status === undefined) throw new Error("missing fixture control");
    status.left = -209;
    status.right = -105;

    expect(() => assertMinimumWindowNavigationLayout(layout)).toThrow(
      "task-event-status 不在可视区域内",
    );
  });

  it("rejects document-level horizontal overflow", () => {
    const layout = createVisibleLayout();
    layout.documentScrollWidth = 980;

    expect(() => assertMinimumWindowNavigationLayout(layout)).toThrow("页面水平溢出");
  });

  it("requires every navigation destination exactly once", () => {
    const layout = createVisibleLayout();
    layout.controls = layout.controls.filter(({ testId }) => testId !== "open-workspaces");

    expect(() => assertMinimumWindowNavigationLayout(layout)).toThrow(
      "open-workspaces 缺失或重复",
    );
  });
});
