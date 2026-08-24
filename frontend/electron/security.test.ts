// @vitest-environment node

import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, isTrustedRendererUrl } from "./security.cts";

describe("Electron renderer URL policy", () => {
  it("accepts only the configured loopback development origin", () => {
    expect(
      isTrustedRendererUrl(
        "http://127.0.0.1:1420/workspaces",
        "http://127.0.0.1:1420",
        false,
      ),
    ).toBe(true);
    expect(
      isTrustedRendererUrl("https://attacker.example", "http://127.0.0.1:1420", false),
    ).toBe(false);
  });

  it("accepts only the packaged application protocol and host", () => {
    expect(isTrustedRendererUrl("app://ai-qa-assistant/index.html", null, true)).toBe(true);
    expect(isTrustedRendererUrl("app://attacker/index.html", null, true)).toBe(false);
    expect(isTrustedRendererUrl("file:///tmp/index.html", null, true)).toBe(false);
  });

  it("allows only loopback HTTP and WebSocket backend connections", () => {
    const policy = contentSecurityPolicy(false);

    expect(policy).toContain("connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*");
    expect(policy).not.toContain("ws://*");
    expect(policy).not.toContain("wss://*");
  });
});
