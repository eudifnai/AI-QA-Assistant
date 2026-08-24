import { contextBridge, ipcRenderer, webUtils } from "electron";

contextBridge.exposeInMainWorld(
  "desktopBridge",
  Object.freeze({
    getBackendConnection: () => ipcRenderer.invoke("desktop:get-backend-connection"),
    selectWorkspaceDirectory: () =>
      ipcRenderer.invoke("desktop:select-workspace-directory"),
    selectDocumentFile: () => ipcRenderer.invoke("desktop:select-document-file"),
    selectDocumentFiles: () => ipcRenderer.invoke("desktop:select-document-files"),
    selectProtoFile: () => ipcRenderer.invoke("desktop:select-proto-file"),
    saveReportFile: (artifact: unknown) =>
      ipcRenderer.invoke("desktop:save-report-file", artifact),
    getPathForFile: (file: File) => webUtils.getPathForFile(file),
  }),
);
