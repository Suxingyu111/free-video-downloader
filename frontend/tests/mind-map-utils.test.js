import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateMindMapFitZoom,
  clampMindMapZoom,
  getMindMapSvgSize,
  layoutMindMap,
  normalizeMindMap,
  renderMindMapSvg
} from "../src/utils/mindMap.js";

test("normalizeMindMap accepts title, text, and name fields while filtering empty nodes", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [
      { text: "First branch", children: [{ name: "Leaf" }, { title: "   " }] },
      { name: "" },
      null
    ]
  });

  assert.deepEqual(tree, {
    id: "0",
    label: "Root",
    depth: 0,
    children: [
      {
        id: "0-0",
        label: "First branch",
        depth: 1,
        children: [{ id: "0-0-0", label: "Leaf", depth: 2, children: [] }]
      }
    ]
  });
});

test("normalizeMindMap supports array input and limits very deep trees without removing useful levels", () => {
  const tree = normalizeMindMap(
    [
      {
        name: "Root",
        children: [
          {
            name: "L1",
            children: [{ name: "L2", children: [{ name: "L3", children: [{ name: "L4" }] }] }]
          }
        ]
      }
    ],
    { maxDepth: 3 }
  );

  assert.equal(tree.label, "Root");
  assert.equal(tree.children[0].label, "L1");
  assert.equal(tree.children[0].children[0].label, "L2");
  assert.equal(tree.children[0].children[0].children[0].label, "L3");
  assert.deepEqual(tree.children[0].children[0].children[0].children, []);
});

test("layoutMindMap creates a deterministic left-to-right tree layout", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: "A" }, { title: "B", children: [{ title: "B1" }] }]
  });

  const layout = layoutMindMap(tree);

  assert.equal(layout.nodes.length, 4);
  assert.equal(layout.links.length, 3);
  assert.equal(layout.nodes[0].label, "Root");
  assert.equal(layout.nodes[0].x, 32);
  assert.equal(layout.nodes[0].depth, 0);

  const child = layout.nodes.find((node) => node.label === "B");
  const grandchild = layout.nodes.find((node) => node.label === "B1");
  assert.ok(child.x > layout.nodes[0].x);
  assert.ok(grandchild.x > child.x);
  assert.ok(layout.width > grandchild.x);
  assert.ok(layout.height >= 180);
});

test("layoutMindMap expands node height for long labels", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890TAILVISIBLE" }]
  });

  const layout = layoutMindMap(tree);
  const longNode = layout.nodes.find((node) => node.label.includes("TAILVISIBLE"));

  assert.ok(longNode.height > 54);
});

test("renderMindMapSvg returns a complete escaped horizontal SVG", () => {
  const tree = normalizeMindMap({
    title: "Root & Topic",
    children: [{ title: "<Branch>", children: [{ title: "\"Leaf\"" }] }]
  });

  const svg = renderMindMapSvg(tree, { background: "#ffffff" });

  assert.match(svg, /^<svg /);
  assert.match(svg, /viewBox="0 0 \d+ \d+"/);
  assert.match(svg, /<path /);
  assert.match(svg, /<g class="mind-map-node"/);
  assert.match(svg, /Root &amp; Topic/);
  assert.match(svg, /&lt;Branch&gt;/);
  assert.match(svg, /&quot;Leaf&quot;/);
  assert.doesNotMatch(svg, /<Branch>/);
});

test("renderMindMapSvg wraps long node labels without dropping visible text", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890TAILVISIBLE" }]
  });

  const svg = renderMindMapSvg(tree);

  assert.match(svg, /<tspan[^>]*>TAILVISIBLE<\/tspan>/);
});

test("getMindMapSvgSize reads dimensions from SVG viewBox before width attributes", () => {
  assert.deepEqual(getMindMapSvgSize('<svg viewBox="0 0 960 540" width="1200" height="800"></svg>'), {
    width: 960,
    height: 540
  });
  assert.deepEqual(getMindMapSvgSize('<svg width="640" height="360"></svg>'), {
    width: 640,
    height: 360
  });
});

test("calculateMindMapFitZoom keeps the whole map visible within the viewport", () => {
  assert.equal(
    calculateMindMapFitZoom({
      viewportWidth: 800,
      viewportHeight: 500,
      contentWidth: 1600,
      contentHeight: 800,
      padding: 40,
      maxZoom: 1
    }),
    0.45
  );
  assert.equal(
    calculateMindMapFitZoom({
      viewportWidth: 1280,
      viewportHeight: 720,
      contentWidth: 420,
      contentHeight: 260,
      padding: 32,
      maxZoom: 1.8
    }),
    1.8
  );
});

test("renderMindMapSvg preserves emoji and surrogate pairs in labels", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: "🎯 Task 🌍✨ completed ✅" }]
  });

  const svg = renderMindMapSvg(tree);

  assert.match(svg, /🎯/u);
  assert.match(svg, /🌍/u);
  assert.match(svg, /✅/u);
});

test("chunkText via renderMindMapSvg does not split surrogate pairs", () => {
  const emojiText = "🎯".repeat(20) + "VISIBLE";
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: emojiText }]
  });

  const svg = renderMindMapSvg(tree);

  assert.match(svg, /VISIBLE/);
  assert.match(svg, /🎯/u);
});

test("clampMindMapZoom constrains manual zoom steps", () => {
  assert.equal(clampMindMapZoom(0.1), 0.35);
  assert.equal(clampMindMapZoom(1.234), 1.23);
  assert.equal(clampMindMapZoom(4), 2.5);
});
