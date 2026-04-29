import assert from "node:assert/strict";
import test from "node:test";

import { layoutMindMap, normalizeMindMap, renderMindMapSvg } from "../src/utils/mindMap.js";

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
