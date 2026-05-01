import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { SEO_PAGES, seoSite } from "../src/seo/pages.js";
import { normalizeSiteUrl } from "./generate-seo-assets.mjs";

const defaultEndpoint = "https://api.indexnow.org/indexnow";
const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const defaultPublicDir = resolve(frontendRoot, "public");
const defaultStateFile = resolve(frontendRoot, ".seo", "indexnow-state.json");

function pageUrl(siteUrl, path) {
  return `${normalizeSiteUrl(siteUrl)}${path}`;
}

function requireIndexNowKey(key) {
  const normalizedKey = String(key || "").trim();
  if (!normalizedKey) {
    throw new Error("INDEXNOW_KEY is required to submit URLs.");
  }
  return normalizedKey;
}

export function buildIndexNowKeyFile(key) {
  return requireIndexNowKey(key);
}

export function getIndexNowUrls(siteUrl = normalizeSiteUrl()) {
  const origin = normalizeSiteUrl(siteUrl);
  return SEO_PAGES.map((page) => pageUrl(origin, page.path));
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function fingerprintPage(page) {
  const content = stableStringify({
    path: page.path,
    title: page.title,
    description: page.description,
    keywords: page.keywords,
    heading: page.heading,
    lead: page.lead,
    geoSummary: page.geoSummary,
    sections: page.sections,
    useCases: page.useCases,
    howToSteps: page.howToSteps,
    failureReasons: page.failureReasons,
    questions: page.questions,
    relatedPaths: page.relatedPaths,
    lastUpdated: page.lastUpdated || seoSite.lastUpdated
  });
  return createHash("sha256").update(content).digest("hex");
}

export function buildIndexNowState({ siteUrl = normalizeSiteUrl(), pages = SEO_PAGES } = {}) {
  const origin = normalizeSiteUrl(siteUrl);
  return Object.fromEntries(pages.map((page) => [pageUrl(origin, page.path), fingerprintPage(page)]));
}

export function selectChangedIndexNowUrls({ siteUrl = normalizeSiteUrl(), previousState = {}, pages = SEO_PAGES } = {}) {
  const currentState = buildIndexNowState({ siteUrl, pages });
  const urlList = Object.entries(currentState)
    .filter(([url, fingerprint]) => previousState[url] !== fingerprint)
    .map(([url]) => url);

  return { urlList, currentState };
}

export async function readIndexNowState({ stateFile = process.env.INDEXNOW_STATE_FILE || defaultStateFile } = {}) {
  try {
    return JSON.parse(await readFile(stateFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw error;
  }
}

export async function writeIndexNowState({ stateFile = process.env.INDEXNOW_STATE_FILE || defaultStateFile, state } = {}) {
  await mkdir(dirname(stateFile), { recursive: true });
  await writeFile(stateFile, JSON.stringify(state, null, 2), "utf8");
  return stateFile;
}

export async function writeIndexNowKeyFile({ publicDir = defaultPublicDir, key = process.env.INDEXNOW_KEY, keyFileName } = {}) {
  const normalizedKey = buildIndexNowKeyFile(key);
  const resolvedFileName = keyFileName || `indexnow-${normalizedKey}.txt`;
  const resolvedPublicDir = resolve(publicDir);
  await mkdir(resolvedPublicDir, { recursive: true });
  const keyFilePath = resolve(resolvedPublicDir, resolvedFileName);
  await writeFile(keyFilePath, normalizedKey, "utf8");
  return keyFilePath;
}

export function buildIndexNowPayload({ siteUrl = normalizeSiteUrl(), key, keyFileName, keyLocation, urls } = {}) {
  const normalizedKey = requireIndexNowKey(key);

  const origin = normalizeSiteUrl(siteUrl);
  if (origin === seoSite.defaultUrl) {
    throw new Error("Set PUBLIC_SITE_URL or VITE_PUBLIC_SITE_URL to your production domain before submitting IndexNow URLs.");
  }

  const parsed = new URL(origin);
  const resolvedKeyFileName = keyFileName || `indexnow-${normalizedKey}.txt`;
  const resolvedKeyLocation = keyLocation || `${origin}/${resolvedKeyFileName}`;
  const urlList = urls || getIndexNowUrls(origin);

  if (new URL(resolvedKeyLocation).host !== parsed.host) {
    throw new Error(`IndexNow keyLocation host must match ${parsed.host}: ${resolvedKeyLocation}`);
  }

  for (const url of urlList) {
    if (new URL(url).host !== parsed.host) {
      throw new Error(`IndexNow URL host must match ${parsed.host}: ${url}`);
    }
  }

  return {
    host: parsed.host,
    key: normalizedKey,
    keyLocation: resolvedKeyLocation,
    urlList
  };
}

export async function submitIndexNow({ endpoint = process.env.INDEXNOW_ENDPOINT || defaultEndpoint, payload, fetchImpl = globalThis.fetch } = {}) {
  if (!fetchImpl) {
    throw new Error("This Node.js runtime does not provide fetch. Use Node 18+.");
  }

  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`IndexNow submission failed with ${response.status}: ${body}`);
  }

  return response.status;
}

async function main() {
  const args = process.argv.slice(2);
  const key = process.env.INDEXNOW_KEY;
  const keyFileName = process.env.INDEXNOW_KEY_FILE;
  const shouldWriteKey = args.includes("--write-key");
  const isDryRun = args.includes("--dry-run") || process.env.INDEXNOW_DRY_RUN === "true";
  const submitAll = args.includes("--all");
  const stateFile = process.env.INDEXNOW_STATE_FILE || defaultStateFile;
  const siteUrl = normalizeSiteUrl();

  if (shouldWriteKey) {
    const keyFilePath = await writeIndexNowKeyFile({ key, keyFileName });
    console.log(`IndexNow key file written to ${keyFilePath}`);
    if (!isDryRun && !args.includes("--submit")) return;
  }

  const previousState = submitAll ? {} : await readIndexNowState({ stateFile });
  const { urlList, currentState } = selectChangedIndexNowUrls({ siteUrl, previousState });

  if (!urlList.length) {
    console.log("IndexNow skipped: no changed SEO URLs since the last successful submission.");
    return;
  }

  const payload = buildIndexNowPayload({
    siteUrl,
    key,
    keyFileName,
    keyLocation: process.env.INDEXNOW_KEY_LOCATION,
    urls: urlList
  });

  if (isDryRun) {
    console.log(JSON.stringify(payload, null, 2));
  } else {
    const status = await submitIndexNow({ payload });
    await writeIndexNowState({ stateFile, state: currentState });
    console.log(`IndexNow submitted ${payload.urlList.length} URLs with HTTP ${status}.`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
