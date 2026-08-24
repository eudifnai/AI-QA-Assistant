const { existsSync } = require("node:fs");
const { extname, resolve } = require("node:path");

const DEFAULT_TIMESTAMP_SERVER = "http://timestamp.digicert.com";

function hasValue(value) {
  return typeof value === "string" && value.length > 0;
}

function validateTimestampServer(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Windows 签名时间戳服务 URL 无效。");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Windows 签名时间戳服务必须使用 HTTP 或 HTTPS。");
  }
  return url.toString();
}

function resolveWindowsSigningConfig(environment = process.env) {
  const certificateFile = environment.WINDOWS_CERTIFICATE_FILE;
  const certificatePassword = environment.WINDOWS_CERTIFICATE_PASSWORD;
  const timestampServer = environment.WINDOWS_TIMESTAMP_SERVER;
  const anySigningValue = [certificateFile, certificatePassword, timestampServer].some(
    hasValue,
  );
  if (!anySigningValue) {
    return undefined;
  }
  if (!hasValue(certificateFile) || !hasValue(certificatePassword)) {
    throw new Error("Windows 签名证书路径和口令必须同时配置。");
  }

  const resolvedCertificateFile = resolve(certificateFile);
  const extension = extname(resolvedCertificateFile).toLowerCase();
  if (extension !== ".pfx" && extension !== ".p12") {
    throw new Error("Windows 签名证书必须是 PFX 或 P12 文件。");
  }
  if (!existsSync(resolvedCertificateFile)) {
    throw new Error("Windows 签名证书不存在。");
  }

  return {
    certificateFile: resolvedCertificateFile,
    timestampServer: validateTimestampServer(
      hasValue(timestampServer) ? timestampServer : DEFAULT_TIMESTAMP_SERVER,
    ),
    description: "AI QA Assistant",
    continueOnError: false,
  };
}

function buildWindowsSigningEnvironment(environment = process.env) {
  const prepared = { ...environment };
  const aiQaValues = [
    environment.AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE,
    environment.AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD,
    environment.AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER,
  ];
  if (aiQaValues.some(hasValue)) {
    prepared.WINDOWS_CERTIFICATE_FILE =
      environment.AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE;
    prepared.WINDOWS_CERTIFICATE_PASSWORD =
      environment.AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD;
    prepared.WINDOWS_TIMESTAMP_SERVER =
      environment.AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER;
  }
  delete prepared.AI_QA_WINDOWS_SIGN_CERTIFICATE_FILE;
  delete prepared.AI_QA_WINDOWS_SIGN_CERTIFICATE_PASSWORD;
  delete prepared.AI_QA_WINDOWS_SIGN_TIMESTAMP_SERVER;

  const config = resolveWindowsSigningConfig(prepared);
  if (config) {
    prepared.WINDOWS_CERTIFICATE_FILE = config.certificateFile;
    prepared.WINDOWS_TIMESTAMP_SERVER = config.timestampServer;
  }
  return {
    environment: prepared,
    mode: config ? "pfx" : "unsigned_internal_candidate",
  };
}

module.exports = {
  buildWindowsSigningEnvironment,
  resolveWindowsSigningConfig,
};
