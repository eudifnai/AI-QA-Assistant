import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchHealth } from "../api/health";
import { useHealthStore } from "./health";

vi.mock("../api/health", () => ({
  fetchHealth: vi.fn(),
}));

describe("health store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(fetchHealth).mockReset();
  });

  it("records an online backend and its version", async () => {
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "0.1.0" });
    const store = useHealthStore();

    await store.refresh();

    expect(store.status).toBe("online");
    expect(store.version).toBe("0.1.0");
    expect(store.error).toBeNull();
  });

  it("shows an offline state and recovers on retry", async () => {
    vi.mocked(fetchHealth)
      .mockRejectedValueOnce(new Error("无法连接本地后端。"))
      .mockResolvedValueOnce({ status: "ok", version: "0.1.1" });
    const store = useHealthStore();

    await store.refresh();
    expect(store.status).toBe("offline");
    expect(store.error).toBe("无法连接本地后端。");

    await store.refresh();
    expect(store.status).toBe("online");
    expect(store.version).toBe("0.1.1");
  });
});

