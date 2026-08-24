interface DesktopBridge {
  getBackendConnection: () => Promise<unknown>;
  selectWorkspaceDirectory: () => Promise<unknown>;
  selectDocumentFile: () => Promise<unknown>;
  selectDocumentFiles: () => Promise<unknown>;
  selectProtoFile: () => Promise<unknown>;
  saveReportFile: (artifact: unknown) => Promise<unknown>;
  getPathForFile: (file: File) => unknown;
}

interface Window {
  desktopBridge?: DesktopBridge;
}
