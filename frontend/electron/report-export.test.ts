// @vitest-environment node

import { describe, expect, it, vi } from "vitest";

import { saveReportArtifact, validateReportExportInput } from "./report-export.cts";

describe("report export validation", () => {
  it("accepts bounded matching report artifacts", () => {
    expect(
      validateReportExportInput({
        format: "html",
        file_name: "payment-report.html",
        media_type: "text/html",
        content: "<!doctype html><title>safe</title>",
      }),
    ).toEqual({
      format: "html",
      fileName: "payment-report.html",
      mediaType: "text/html",
      content: "<!doctype html><title>safe</title>",
    });
  });

  it.each([
    [{ format: "pdf", file_name: "report.pdf", media_type: "application/pdf", content: "x" }],
    [{ format: "json", file_name: "../report.json", media_type: "application/json", content: "x" }],
    [{ format: "json", file_name: "..\\report.json", media_type: "application/json", content: "x" }],
    [{ format: "html", file_name: "report.exe", media_type: "text/html", content: "x" }],
    [{ format: "markdown", file_name: "report.md", media_type: "text/markdown", content: "" }],
    [{ format: "json", file_name: "report.json", media_type: "application/json", content: "x".repeat(10 * 1024 * 1024 + 1) }],
  ])("rejects unsafe or mismatched inputs", (input) => {
    expect(() => validateReportExportInput(input)).toThrow("报告导出参数不正确");
  });

  it("writes only to the path returned by the system dialog", async () => {
    const showSaveDialog = vi.fn().mockResolvedValue({
      canceled: false,
      filePath: "C:\\qa\\reports\\payment-report.html",
    });
    const writeReport = vi.fn().mockResolvedValue(undefined);
    const artifact = {
      format: "html",
      file_name: "payment-report.html",
      media_type: "text/html",
      content: "<!doctype html><title>safe</title>",
    };

    await expect(saveReportArtifact(artifact, showSaveDialog, writeReport)).resolves.toBe(
      "C:\\qa\\reports\\payment-report.html",
    );
    expect(showSaveDialog).toHaveBeenCalledWith(expect.objectContaining({
      defaultPath: "payment-report.html",
      filters: [{ name: "HTML 报告", extensions: ["html"] }],
    }));
    expect(writeReport).toHaveBeenCalledWith(
      "C:\\qa\\reports\\payment-report.html",
      artifact.content,
    );
  });

  it("does not write when the system dialog is cancelled", async () => {
    const writeReport = vi.fn();
    const result = await saveReportArtifact(
      {
        format: "json",
        file_name: "report.json",
        media_type: "application/json",
        content: "{}",
      },
      vi.fn().mockResolvedValue({ canceled: true }),
      writeReport,
    );

    expect(result).toBeNull();
    expect(writeReport).not.toHaveBeenCalled();
  });
});
