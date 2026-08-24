// @vitest-environment node

import { describe, expect, it } from "vitest";

import { buildSquirrelStartupAction, handleSquirrelStartup } from "./squirrel-startup.cts";

describe("Squirrel startup events", () => {
  it.each([
    ["--squirrel-install", "--createShortcut=ai-qa-assistant.exe"],
    ["--squirrel-updated", "--createShortcut=ai-qa-assistant.exe"],
    ["--squirrel-uninstall", "--removeShortcut=ai-qa-assistant.exe"],
  ])("maps %s to a shell-free Update.exe action", (event, expectedArgument) => {
    expect(
      buildSquirrelStartupAction(
        ["C:\\app\\app-0.1.0\\ai-qa-assistant.exe", event],
        "C:\\app\\app-0.1.0\\ai-qa-assistant.exe",
        "win32",
      ),
    ).toEqual({
      handled: true,
      quitImmediately: false,
      executable: "C:\\app\\Update.exe",
      args: [expectedArgument],
    });
  });

  it("quits obsolete versions without launching Update.exe", () => {
    expect(
      buildSquirrelStartupAction(
        ["C:\\app\\app-0.1.0\\ai-qa-assistant.exe", "--squirrel-obsolete"],
        "C:\\app\\app-0.1.0\\ai-qa-assistant.exe",
        "win32",
      ),
    ).toEqual({
      handled: true,
      quitImmediately: true,
      executable: null,
      args: [],
    });
  });

  it("ignores normal launches and non-Windows platforms", () => {
    expect(
      buildSquirrelStartupAction(
        ["C:\\app\\app-0.1.0\\ai-qa-assistant.exe"],
        "C:\\app\\app-0.1.0\\ai-qa-assistant.exe",
        "win32",
      ),
    ).toEqual({ handled: false });
    expect(
      buildSquirrelStartupAction(
        ["/app/ai-qa-assistant", "--squirrel-install"],
        "/app/ai-qa-assistant",
        "linux",
      ),
    ).toEqual({ handled: false });
  });

  it("schedules a prompt quit without waiting for Update.exe to close", () => {
    let scheduledQuit: (() => void) | null = null;
    let errorHandler: (() => void) | null = null;
    let unreferenced = false;
    let quitCalls = 0;

    const handled = handleSquirrelStartup(
      ["C:\\app\\app-0.1.0\\ai-qa-assistant.exe", "--squirrel-uninstall"],
      "C:\\app\\app-0.1.0\\ai-qa-assistant.exe",
      () => {
        quitCalls += 1;
      },
      "win32",
      (executable, args) => {
        expect(executable).toBe("C:\\app\\Update.exe");
        expect(args).toEqual(["--removeShortcut=ai-qa-assistant.exe"]);
        return {
          once(event: "error", listener: () => void): void {
            expect(event).toBe("error");
            errorHandler = listener;
          },
          unref(): void {
            unreferenced = true;
          },
        };
      },
      (callback, delayMilliseconds) => {
        expect(delayMilliseconds).toBe(1000);
        scheduledQuit = callback;
      },
    );

    expect(handled).toBe(true);
    expect(unreferenced).toBe(true);
    expect(quitCalls).toBe(0);
    expect(scheduledQuit).not.toBeNull();
    scheduledQuit?.();
    expect(quitCalls).toBe(1);
    errorHandler?.();
    expect(quitCalls).toBe(1);
  });
});
