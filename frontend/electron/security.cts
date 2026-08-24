export const APPLICATION_PROTOCOL = "app";
export const APPLICATION_HOST = "ai-qa-assistant";

export function isTrustedRendererUrl(
  candidateUrl: string,
  developmentUrl: string | null,
  packaged: boolean,
): boolean {
  try {
    const candidate = new URL(candidateUrl);
    if (developmentUrl !== null) {
      const development = new URL(developmentUrl);
      return (
        candidate.protocol === "http:" &&
        candidate.hostname === "127.0.0.1" &&
        candidate.origin === development.origin
      );
    }
    return packaged && candidate.protocol === `${APPLICATION_PROTOCOL}:` && candidate.host === APPLICATION_HOST;
  } catch {
    return false;
  }
}

export function contentSecurityPolicy(_development: boolean): string {
  void _development;
  const connectSources = "'self' http://127.0.0.1:* ws://127.0.0.1:*";
  return [
    "default-src 'self'",
    "base-uri 'none'",
    `connect-src ${connectSources}`,
    "font-src 'self' data:",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data: blob:",
    "object-src 'none'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
  ].join("; ");
}
