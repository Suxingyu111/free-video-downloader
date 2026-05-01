const metaVerifications = [
  ["GOOGLE_SITE_VERIFICATION", "google-site-verification"],
  ["BING_SITE_VERIFICATION", "msvalidate.01"],
  ["BAIDU_SITE_VERIFICATION", "baidu-site-verification"],
  ["SO_SITE_VERIFICATION", "360-site-verification"],
  ["QIHOO_SITE_VERIFICATION", "360-site-verification"],
  ["SOGOU_SITE_VERIFICATION", "sogou_site_verification"],
  ["YANDEX_SITE_VERIFICATION", "yandex-verification"]
];

const fileVerifications = [
  ["GOOGLE_SITE_VERIFICATION_FILE", "GOOGLE_SITE_VERIFICATION_FILE_CONTENT"],
  ["BING_SITE_VERIFICATION_FILE", "BING_SITE_VERIFICATION_FILE_CONTENT"],
  ["BAIDU_SITE_VERIFICATION_FILE", "BAIDU_SITE_VERIFICATION_FILE_CONTENT"],
  ["SO_SITE_VERIFICATION_FILE", "SO_SITE_VERIFICATION_FILE_CONTENT"],
  ["QIHOO_SITE_VERIFICATION_FILE", "QIHOO_SITE_VERIFICATION_FILE_CONTENT"],
  ["SOGOU_SITE_VERIFICATION_FILE", "SOGOU_SITE_VERIFICATION_FILE_CONTENT"],
  ["YANDEX_SITE_VERIFICATION_FILE", "YANDEX_SITE_VERIFICATION_FILE_CONTENT"]
];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalizeFileName(fileName) {
  const normalized = String(fileName || "").trim().replace(/^\/+/, "");
  if (!normalized || normalized.includes("..") || normalized.includes("/") || normalized.includes("\\")) {
    throw new Error(`Invalid webmaster verification file name: ${fileName}`);
  }
  return normalized;
}

export function getWebmasterMetaTags(env = process.env) {
  return metaVerifications
    .map(([envName, metaName]) => {
      const content = String(env[envName] || "").trim();
      if (!content) return "";
      return `<meta name="${metaName}" content="${escapeHtml(content)}" />`;
    })
    .filter(Boolean)
    .join("\n    ");
}

export function getWebmasterVerificationFiles(env = process.env) {
  return fileVerifications
    .map(([fileEnvName, contentEnvName]) => {
      const fileName = String(env[fileEnvName] || "").trim();
      if (!fileName) return null;
      return {
        fileName: normalizeFileName(fileName),
        content: String(env[contentEnvName] || "").trim() || `${normalizeFileName(fileName)}`
      };
    })
    .filter(Boolean);
}
