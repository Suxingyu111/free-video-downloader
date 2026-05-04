import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { defaultBackendEnvFile, defaultProjectEnvFile, loadProjectEnv } from "../scripts/env-file.mjs";

test("default env file points at the backend .env", () => {
  assert.match(defaultBackendEnvFile, /backend\/\.env$/);
  assert.equal(defaultProjectEnvFile, defaultBackendEnvFile);
});

test("loadProjectEnv reads backend .env without overriding existing process env", async () => {
  const directory = await mkdtemp(join(tmpdir(), "saveany-env-"));
  const previousEnv = {
    PUBLIC_SITE_URL: process.env.PUBLIC_SITE_URL,
    VITE_BACKEND_URL: process.env.VITE_BACKEND_URL,
    INDEXNOW_KEY: process.env.INDEXNOW_KEY,
    INDEXNOW_ENDPOINT: process.env.INDEXNOW_ENDPOINT
  };
  try {
    const envFile = join(directory, ".env");
    await writeFile(
      envFile,
      [
        "PUBLIC_SITE_URL=https://env.example.com/",
        "VITE_BACKEND_URL=http://127.0.0.1:9000",
        "INDEXNOW_KEY=from-file",
        "INDEXNOW_ENDPOINT=https://indexnow.example.com/submit"
      ].join("\n"),
      "utf8"
    );

    process.env.VITE_BACKEND_URL = "http://127.0.0.1:8000";
    delete process.env.PUBLIC_SITE_URL;
    delete process.env.INDEXNOW_KEY;
    delete process.env.INDEXNOW_ENDPOINT;

    const loaded = loadProjectEnv({ envFile });

    assert.equal(loaded.PUBLIC_SITE_URL, "https://env.example.com/");
    assert.equal(process.env.PUBLIC_SITE_URL, "https://env.example.com/");
    assert.equal(process.env.VITE_BACKEND_URL, "http://127.0.0.1:8000");
    assert.equal(process.env.INDEXNOW_KEY, "from-file");
    assert.equal(process.env.INDEXNOW_ENDPOINT, "https://indexnow.example.com/submit");

  } finally {
    for (const [key, value] of Object.entries(previousEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
    await rm(directory, { recursive: true, force: true });
  }
});
