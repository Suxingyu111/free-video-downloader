import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const projectRoot = resolve(frontendRoot, "..");
const backendRoot = resolve(projectRoot, "backend");

export const defaultBackendEnvFile = resolve(backendRoot, ".env");
export const defaultProjectEnvFile = defaultBackendEnvFile;

export function parseEnvFile(content, { source = ".env" } = {}) {
  const values = {};
  const lines = String(content || "").split(/\r?\n/);
  lines.forEach((rawLine, index) => {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) return;
    if (line.startsWith("export ")) line = line.slice("export ".length).trim();
    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) {
      throw new Error(`${source} line ${index + 1} is missing '='.`);
    }
    const key = line.slice(0, separatorIndex).trim();
    if (!key) {
      throw new Error(`${source} line ${index + 1} is missing a variable name.`);
    }
    values[key] = stripOptionalQuotes(line.slice(separatorIndex + 1).trim());
  });
  return values;
}

export function loadProjectEnv({ envFile = process.env.SAVEANY_ENV_FILE || defaultProjectEnvFile, override = false } = {}) {
  if (!envFile || !existsSync(envFile)) return {};
  const values = parseEnvFile(readFileSync(envFile, "utf8"), { source: envFile });
  for (const [key, value] of Object.entries(values)) {
    if (override || process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
  return values;
}

function stripOptionalQuotes(value) {
  if (value.length >= 2 && value[0] === value[value.length - 1] && ["'", '"'].includes(value[0])) {
    return value.slice(1, -1);
  }
  return value;
}
