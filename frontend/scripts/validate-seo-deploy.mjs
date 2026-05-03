import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { SEO_PAGES, seoSite } from "../src/seo/pages.js";
import { loadProjectEnv } from "./env-file.mjs";
import { normalizeSiteUrl } from "./generate-seo-assets.mjs";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const defaultPublicDir = resolve(frontendRoot, "public");

export const REQUIRED_GEO_PATHS = [
  "/_headers",
  "/_redirects",
  "/404.html",
  "/robots.txt",
  "/sitemap.xml",
  "/llms.txt",
  "/llms-full.txt",
  "/.well-known/ai.json",
  "/index.html.md",
  "/sitemap/",
  ...SEO_PAGES.filter((page) => page.path !== "/").map((page) => page.path),
  ...SEO_PAGES.filter((page) => page.path !== "/").map((page) => `${page.path}index.html.md`)
];

export const REQUIRED_REMOTE_GEO_PATHS = ["/", ...REQUIRED_GEO_PATHS];

function isReservedHost(hostname) {
  return hostname === "localhost" || hostname.endsWith(".local") || hostname.endsWith(".example") || hostname.endsWith(".test") || hostname.endsWith(".invalid");
}

export function validateProductionSiteUrl(siteUrl = normalizeSiteUrl(), { allowReserved = false } = {}) {
  const origin = normalizeSiteUrl(siteUrl);
  const url = new URL(origin);
  const errors = [];

  if (origin === seoSite.defaultUrl) errors.push(`PUBLIC_SITE_URL/VITE_PUBLIC_SITE_URL still uses fallback ${seoSite.defaultUrl}.`);
  if (url.protocol !== "https:") errors.push("Production canonical URL must use HTTPS.");
  if (!allowReserved && isReservedHost(url.hostname)) errors.push(`Production canonical host must be a real public domain, got ${url.hostname}.`);

  return { origin, ok: errors.length === 0, errors };
}

function filePathForUrlPath(publicDir, urlPath) {
  if (urlPath === "/") return resolve(publicDir, "index.html");
  if (urlPath === "/sitemap/") return resolve(publicDir, "sitemap", "index.html");
  if (urlPath.endsWith("/")) return resolve(publicDir, urlPath.replace(/^\/|\/$/g, ""), "index.html");
  return resolve(publicDir, urlPath.replace(/^\//, ""));
}

export async function validateGeneratedAssets({ publicDir = defaultPublicDir, siteUrl = normalizeSiteUrl(), allowReserved = false } = {}) {
  const site = validateProductionSiteUrl(siteUrl, { allowReserved });
  const errors = [...site.errors];
  const origin = site.origin;

  for (const urlPath of REQUIRED_GEO_PATHS) {
    try {
      await stat(filePathForUrlPath(publicDir, urlPath));
    } catch {
      errors.push(`Missing generated GEO asset for ${urlPath}.`);
    }
  }

  const filesWithCanonical = ["404.html", "robots.txt", "sitemap.xml", "llms.txt", "llms-full.txt", ".well-known/ai.json", "index.html.md", "sitemap/index.html"];
  for (const file of filesWithCanonical) {
    try {
      const content = await readFile(resolve(publicDir, file), "utf8");
      if (!content.includes(origin)) {
        errors.push(`${file} does not contain canonical origin ${origin}.`);
      }
      if (origin !== seoSite.defaultUrl && content.includes(seoSite.defaultUrl)) {
        errors.push(`${file} still contains fallback origin ${seoSite.defaultUrl}.`);
      }
    } catch {
      errors.push(`Unable to read ${file}.`);
    }
  }

  return { ok: errors.length === 0, origin, checkedPaths: REQUIRED_GEO_PATHS.length, errors };
}

export async function checkRemoteGeoUrls({ siteUrl = normalizeSiteUrl(), fetchImpl = globalThis.fetch, timeoutMs = 12000, allowReserved = false } = {}) {
  const site = validateProductionSiteUrl(siteUrl, { allowReserved });
  if (!site.ok) return { ok: false, origin: site.origin, results: [], errors: site.errors };
  if (!fetchImpl) throw new Error("This Node.js runtime does not provide fetch. Use Node 18+.");

  const results = [];
  const errors = [];
  for (const urlPath of REQUIRED_REMOTE_GEO_PATHS) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const url = `${site.origin}${urlPath}`;
    try {
      const response = await fetchImpl(url, { method: "GET", signal: controller.signal, redirect: "follow" });
      const ok = response.status === 200;
      results.push({ url, status: response.status, ok });
      if (!ok) errors.push(`${url} returned HTTP ${response.status}.`);
    } catch (error) {
      results.push({ url, status: 0, ok: false, error: error.message });
      errors.push(`${url} failed: ${error.message}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  return { ok: errors.length === 0, origin: site.origin, results, errors };
}

async function main() {
  loadProjectEnv();
  const args = process.argv.slice(2);
  const siteUrl = normalizeSiteUrl();
  const allowReserved = args.includes("--allow-reserved");
  const isRemote = args.includes("--remote");
  const report = isRemote
    ? await checkRemoteGeoUrls({ siteUrl, allowReserved })
    : await validateGeneratedAssets({ siteUrl, allowReserved });

  if (!report.ok) {
    console.error(`SEO deployment validation failed for ${report.origin}:`);
    for (const error of report.errors) console.error(`- ${error}`);
    process.exitCode = 1;
    return;
  }

  if (isRemote) {
    console.log(`SEO remote validation passed for ${report.origin}: ${report.results.length} URLs returned 200.`);
  } else {
    console.log(`SEO asset validation passed for ${report.origin}: ${report.checkedPaths} local paths are present.`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
