import assert from "node:assert/strict";
import test from "node:test";

import { RELIABLE_MP4_FORMAT, resolveDownloadFormat } from "../src/services/formats.js";

test("reliable mp4 format prefers progressive mp4 before youtube dash formats", () => {
  assert.match(RELIABLE_MP4_FORMAT, /^18\//);
  assert.match(RELIABLE_MP4_FORMAT, /\[vcodec\^=avc\]/);
  assert.match(RELIABLE_MP4_FORMAT, /bestaudio\[ext=m4a\]/);
});

test("video-only quality selections include an audio fallback", () => {
  assert.equal(
    resolveDownloadFormat({ format_id: "137", vcodec: "avc1.640028", acodec: "none" }),
    "137+bestaudio[ext=m4a]/137+bestaudio/137",
  );
});

test("progressive and custom format selectors stay unchanged", () => {
  assert.equal(resolveDownloadFormat({ format_id: "18", vcodec: "avc1.42001E", acodec: "mp4a.40.2" }), "18");
  assert.equal(resolveDownloadFormat({ format_id: "bestvideo+bestaudio/best" }), "bestvideo+bestaudio/best");
});
