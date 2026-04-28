import assert from "node:assert/strict";
import test from "node:test";

import { RELIABLE_MP4_FORMAT } from "../src/services/formats.js";

test("reliable mp4 format prefers progressive mp4 before youtube dash formats", () => {
  assert.match(RELIABLE_MP4_FORMAT, /^18\//);
  assert.match(RELIABLE_MP4_FORMAT, /\[vcodec\^=avc\]/);
  assert.match(RELIABLE_MP4_FORMAT, /bestaudio\[ext=m4a\]/);
});
