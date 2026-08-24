export const GET_BACKEND_CONNECTION_CHANNEL = "desktop:get-backend-connection";
export const SELECT_WORKSPACE_DIRECTORY_CHANNEL = "desktop:select-workspace-directory";
export const SELECT_DOCUMENT_FILE_CHANNEL = "desktop:select-document-file";
export const SELECT_DOCUMENT_FILES_CHANNEL = "desktop:select-document-files";
export const SELECT_PROTO_FILE_CHANNEL = "desktop:select-proto-file";
export const SAVE_REPORT_FILE_CHANNEL = "desktop:save-report-file";

type Invoke = (channel: string, ...args: unknown[]) => Promise<unknown>;
type GetPathForFile = (file: File) => string;

export interface DesktopBridge {
  getBackendConnection: () => Promise<unknown>;
  selectWorkspaceDirectory: () => Promise<unknown>;
  selectDocumentFile: () => Promise<unknown>;
  selectDocumentFiles: () => Promise<unknown>;
  selectProtoFile: () => Promise<unknown>;
  saveReportFile: (artifact: unknown) => Promise<unknown>;
  getPathForFile: (file: File) => unknown;
}

export function createDesktopBridge(
  invoke: Invoke,
  getPathForFile: GetPathForFile,
): DesktopBridge {
  return Object.freeze({
    getBackendConnection: () => invoke(GET_BACKEND_CONNECTION_CHANNEL),
    selectWorkspaceDirectory: () => invoke(SELECT_WORKSPACE_DIRECTORY_CHANNEL),
    selectDocumentFile: () => invoke(SELECT_DOCUMENT_FILE_CHANNEL),
    selectDocumentFiles: () => invoke(SELECT_DOCUMENT_FILES_CHANNEL),
    selectProtoFile: () => invoke(SELECT_PROTO_FILE_CHANNEL),
    saveReportFile: (artifact: unknown) => invoke(SAVE_REPORT_FILE_CHANNEL, artifact),
    getPathForFile: (file: File) => getPathForFile(file),
  });
}
