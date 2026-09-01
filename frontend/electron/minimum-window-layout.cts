export const MAIN_WINDOW_MIN_WIDTH = 760;
export const MAIN_WINDOW_MIN_HEIGHT = 520;

export const MINIMUM_WINDOW_NAVIGATION_TEST_IDS = [
  "task-event-status",
  "open-workspaces",
  "open-reports",
  "open-analysis",
  "open-documents",
  "open-http-execution",
  "open-websocket-execution",
  "open-proto-assets",
  "open-protobuf-execution",
  "open-maintenance",
  "open-settings",
] as const;

interface NavigationControlBounds {
  testId: string;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

interface MinimumWindowNavigationLayout {
  viewportWidth: number;
  viewportHeight: number;
  documentScrollWidth: number;
  controls: NavigationControlBounds[];
}

function readFiniteNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`最小窗口导航验收数据缺少有效的 ${key}。`);
  }
  return value;
}

function readLayout(value: unknown): MinimumWindowNavigationLayout {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("最小窗口导航验收数据无效。");
  }
  const record = value as Record<string, unknown>;
  const viewportWidth = readFiniteNumber(record, "viewportWidth");
  const viewportHeight = readFiniteNumber(record, "viewportHeight");
  const documentScrollWidth = readFiniteNumber(record, "documentScrollWidth");
  if (!Array.isArray(record.controls)) {
    throw new Error("最小窗口导航验收数据缺少控件边界。");
  }
  const controls = record.controls.map((control) => {
    if (typeof control !== "object" || control === null || Array.isArray(control)) {
      throw new Error("最小窗口导航控件边界无效。");
    }
    const bounds = control as Record<string, unknown>;
    if (typeof bounds.testId !== "string" || bounds.testId === "") {
      throw new Error("最小窗口导航控件缺少测试标识。");
    }
    return {
      testId: bounds.testId,
      left: readFiniteNumber(bounds, "left"),
      right: readFiniteNumber(bounds, "right"),
      top: readFiniteNumber(bounds, "top"),
      bottom: readFiniteNumber(bounds, "bottom"),
    };
  });
  return { viewportWidth, viewportHeight, documentScrollWidth, controls };
}

export function assertMinimumWindowNavigationLayout(value: unknown): void {
  const layout = readLayout(value);
  if (
    layout.viewportWidth <= 0 ||
    layout.viewportWidth > MAIN_WINDOW_MIN_WIDTH ||
    layout.viewportHeight <= 0 ||
    layout.viewportHeight > MAIN_WINDOW_MIN_HEIGHT
  ) {
    throw new Error("Electron 未在声明的最小窗口尺寸执行导航验收。");
  }
  if (layout.documentScrollWidth > layout.viewportWidth + 1) {
    throw new Error("最小窗口出现页面水平溢出。");
  }

  for (const testId of MINIMUM_WINDOW_NAVIGATION_TEST_IDS) {
    const matchingControls = layout.controls.filter((control) => control.testId === testId);
    if (matchingControls.length !== 1) {
      throw new Error(`最小窗口导航控件 ${testId} 缺失或重复。`);
    }
    const control = matchingControls[0];
    if (
      control === undefined ||
      control.left < -0.5 ||
      control.right > layout.viewportWidth + 0.5 ||
      control.top < -0.5 ||
      control.bottom > layout.viewportHeight + 0.5
    ) {
      throw new Error(`最小窗口导航控件 ${testId} 不在可视区域内。`);
    }
  }
}
