const { existsSync } = require("node:fs");
const { extname, resolve } = require("node:path");

const DEFAULT_TIMESTAMP_SERVER = "http://timestamp.digicert.com";
const ARTIFACT_SIGNING_MODE = "artifact_signing";
const ARTIFACT_SIGNING_VARIABLES = [
  "AI_QA_ARTIFACT_SIGNING_ENDPOINT",
  "AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME",
  "AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME",
];

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
  const requestedMode = environment.AI_QA_WINDOWS_SIGN_MODE;
  const certificateFile = environment.WINDOWS_CERTIFICATE_FILE;
  const certificatePassword = environment.WINDOWS_CERTIFICATE_PASSWORD;
  const timestampServer = environment.WINDOWS_TIMESTAMP_SERVER;
  const pfxValues = [certificateFile, certificatePassword, timestampServer];
  const anyPfxValue = pfxValues.some(hasValue);
  const artifactValues = ARTIFACT_SIGNING_VARIABLES.map(
    (name) => environment[name],
  );
  const anyArtifactValue = artifactValues.some(hasValue);

  if (
    hasValue(requestedMode) &&
    requestedMode !== ARTIFACT_SIGNING_MODE &&
    requestedMode !== "pfx"
  ) {
    throw new Error(`不支持的 Windows 签名模式：${requestedMode}。`);
  }
  if (requestedMode === ARTIFACT_SIGNING_MODE) {
    if (anyPfxValue) {
      throw new Error("不能同时配置 PFX 和 Artifact Signing。");
    }
    if (!artifactValues.every(hasValue)) {
      throw new Error("Artifact Signing 配置不完整。");
    }
    let endpoint;
    try {
      endpoint = new URL(environment.AI_QA_ARTIFACT_SIGNING_ENDPOINT);
    } catch {
      throw new Error("Artifact Signing endpoint 无效。");
    }
    if (endpoint.protocol !== "https:") {
      throw new Error("Artifact Signing endpoint 必须使用 HTTPS。");
    }
    return {
      hookModulePath: require.resolve("./artifact-signing-hook.cjs"),
      continueOnError: false,
    };
  }
  if (anyArtifactValue) {
    throw new Error(
      "配置 Artifact Signing 时必须将 AI_QA_WINDOWS_SIGN_MODE 设为 artifact_signing。",
    );
  }
  if (!anyPfxValue) {
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
    mode:
      environment.AI_QA_WINDOWS_SIGN_MODE === ARTIFACT_SIGNING_MODE
        ? ARTIFACT_SIGNING_MODE
        : config
          ? "pfx"
          : "unsigned_internal_candidate",
  };
}

module.exports = {
  buildWindowsSigningEnvironment,
  resolveWindowsSigningConfig,
};
