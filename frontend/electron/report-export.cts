import { basename } from "node:path";

export type ReportExportFormat = "json" | "markdown" | "html";

export interface ReportExportInput {
  format: ReportExportFormat;
  fileName: string;
  mediaType: string;
  content: string;
}

const MAX_REPORT_BYTES = 10 * 1024 * 1024;
const FORMAT_CONFIG = {
  json: { extension: ".json", mediaType: "application/json" },
  markdown: { extension: ".md", mediaType: "text/markdown" },
  html: { extension: ".html", mediaType: "text/html" },
} as const;

export function validateReportExportInput(value: unknown): ReportExportInput {
  if (typeof value !== "object" || value === null) {
    throw new Error("报告导出参数不正确。");
  }
  const candidate = value as Record<string, unknown>;
  const format = candidate.format;
  if (format !== "json" && format !== "markdown" && format !== "html") {
    throw new Error("报告导出参数不正确。");
  }
  const fileName = candidate.file_name;
  const content = candidate.content;
  const mediaType = candidate.media_type;
  const config = FORMAT_CONFIG[format];
  const validFileName =
    typeof fileName === "string" &&
    fileName.length > config.extension.length &&
    fileName.length <= 180 &&
    basename(fileName) === fileName &&
    !/[\\/]/.test(fileName) &&
    !fileName.includes("\0") &&
    fileName.toLowerCase().endsWith(config.extension);
  const validContent =
    typeof content === "string" &&
    content.length > 0 &&
    Buffer.byteLength(content, "utf8") <= MAX_REPORT_BYTES;
  if (!validFileName || mediaType !== config.mediaType || !validContent) {
    throw new Error("报告导出参数不正确。");
  }
  return {
    format,
    fileName: fileName as string,
    mediaType: mediaType as string,
    content: content as string,
  };
}

export function reportFileFilter(format: ReportExportFormat): { name: string; extensions: string[] } {
  if (format === "json") return { name: "JSON 报告", extensions: ["json"] };
  if (format === "markdown") return { name: "Markdown 报告", extensions: ["md"] };
  return { name: "HTML 报告", extensions: ["html"] };
}

export interface ReportSaveDialogOptions {
  title: string;
  buttonLabel: string;
  defaultPath: string;
  filters: Array<{ name: string; extensions: string[] }>;
}

type ShowSaveDialog = (
  options: ReportSaveDialogOptions,
) => Promise<{ canceled: boolean; filePath?: string }>;
type WriteReport = (filePath: string, content: string) => Promise<void>;

export async function saveReportArtifact(
  value: unknown,
  showSaveDialog: ShowSaveDialog,
  writeReport: WriteReport,
): Promise<string | null> {
  const report = validateReportExportInput(value);
  const result = await showSaveDialog({
    title: "导出 QA 报告",
    buttonLabel: "保存报告",
    defaultPath: report.fileName,
    filters: [reportFileFilter(report.format)],
  });
  if (result.canceled || !result.filePath) return null;
  await writeReport(result.filePath, report.content);
  return result.filePath;
}
