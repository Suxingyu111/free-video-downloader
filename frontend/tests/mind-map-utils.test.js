import assert from "node:assert/strict";
import test from "node:test";

import * as mindMapUtils from "../src/utils/mindMap.js";
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

test("createVisibleMindMap folds deeper branches into a readable count node", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [
      {
        title: "Branch",
        children: [
          { title: "Hidden A", children: [{ title: "Hidden A1" }] },
          { title: "Hidden B" }
        ]
      }
    ]
  });

  assert.equal(typeof mindMapUtils.createVisibleMindMap, "function");
  const visible = mindMapUtils.createVisibleMindMap(tree, { visibleDepth: 1 });

  assert.equal(visible.children[0].label, "Branch");
  assert.equal(visible.children[0].children.length, 1);
  assert.equal(visible.children[0].children[0].isCollapsedSummary, true);
  assert.equal(visible.children[0].children[0].hiddenCount, 3);
  assert.equal(visible.children[0].children[0].label, "还有 3 个要点");
});

test("createVisibleMindMap keeps matching deep search paths visible and marks matched nodes", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [
      { title: "章节背景", children: [{ title: "普通信息" }] },
      { title: "实践路径", children: [{ title: "字幕转思维导图" }] }
    ]
  });

  const visible = mindMapUtils.createVisibleMindMap(tree, { visibleDepth: 1, query: "思维导图" });
  const matchedBranch = visible.children.find((node) => node.label === "实践路径");
  const matchedLeaf = matchedBranch.children.find((node) => node.label === "字幕转思维导图");

  assert.equal(matchedBranch.isSearchAncestor, true);
  assert.equal(matchedLeaf.isSearchMatch, true);
  assert.equal(matchedLeaf.children.length, 0);
});

test("renderMindMapSvg exposes node metadata and focus styling for interactive maps", () => {
  const tree = normalizeMindMap({
    title: "Root",
    children: [{ title: "Branch", children: [{ title: "Leaf" }] }, { title: "Other" }]
  });
  const visible = mindMapUtils.createVisibleMindMap(tree, { visibleDepth: 3, query: "leaf" });
  const leafId = visible.children[0].children[0].id;
  const svg = renderMindMapSvg(visible, { focusedNodeId: leafId });

  assert.match(svg, /data-node-id="0-0-0"/);
  assert.match(svg, /data-depth="2"/);
  assert.match(svg, /mind-map-node is-search-match is-focus-related/);
  assert.match(svg, /mind-map-node is-dimmed/);
  assert.match(svg, /<defs>/);
  assert.match(svg, /font-family="Fira Sans, PingFang SC/);
});

test("buildInteractiveMindMapHtml packages the styled mind map with standalone interactions", () => {
  const tree = normalizeMindMap({
    title: "Root <Topic>",
    children: [
      { title: "字幕与转写", children: [{ title: "时间轴" }] },
      { title: "导出格式" }
    ]
  });

  assert.equal(typeof mindMapUtils.buildInteractiveMindMapHtml, "function");
  const html = mindMapUtils.buildInteractiveMindMapHtml(tree, {
    title: "Root <Topic>",
    visibleDepth: 1,
    searchQuery: "字幕",
    focusedNodeId: "0-0"
  });

  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<title>Root &lt;Topic&gt; - 交互式思维导图<\/title>/);
  assert.match(html, /data-mind-map-app/);
  assert.match(html, /aria-label="搜索思维导图节点"/);
  assert.match(html, /id="mind-map-level"/);
  assert.match(html, /id="mind-map-download-svg"/);
  assert.match(html, /function renderMindMap/);
  assert.match(html, /function handleViewportWheel/);
  assert.match(html, /const MIND_MAP_TREE = /);
  assert.match(html, /"searchQuery":"字幕"/);
  assert.match(html, /Root \\u003cTopic\\u003e/);
  assert.doesNotMatch(html, /Root <Topic>/);
});
