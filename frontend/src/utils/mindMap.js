const DEFAULT_MAX_DEPTH = 5;
const DEFAULT_NODE_WIDTH = 184;
const DEFAULT_NODE_HEIGHT = 54;
const DEFAULT_X_GAP = 104;
const DEFAULT_Y_GAP = 28;
const DEFAULT_MARGIN = 32;

const BRANCH_COLORS = [
  "#2563eb",
  "#059669",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#be123c",
  "#4d7c0f"
];

function normalizeLabel(value) {
  if (typeof value === "string" || typeof value === "number") {
    return String(value).trim();
  }
  return "";
}

function getNodeLabel(node) {
  if (!node || typeof node !== "object") {
    return "";
  }
  return normalizeLabel(node.title) || normalizeLabel(node.text) || normalizeLabel(node.name);
}

function getChildren(node) {
  if (!node || typeof node !== "object") {
    return [];
  }

  if (Array.isArray(node.children)) {
    return node.children;
  }
  if (Array.isArray(node.items)) {
    return node.items;
  }
  if (Array.isArray(node.nodes)) {
    return node.nodes;
  }
  return [];
}

function unwrapInput(input) {
  if (Array.isArray(input)) {
    return input;
  }
  if (input && typeof input === "object") {
    if (input.mind_map) {
      return unwrapInput(input.mind_map);
    }
    if (input.mindMap) {
      return unwrapInput(input.mindMap);
    }
  }
  return input;
}

function normalizeNode(node, depth, path, maxDepth) {
  const label = getNodeLabel(node);
  if (!label) {
    return null;
  }

  const normalized = {
    id: path.join("-"),
    label,
    depth,
    children: []
  };

  if (depth >= maxDepth) {
    return normalized;
  }

  const children = getChildren(node);
  for (const child of children) {
    const normalizedChild = normalizeNode(child, depth + 1, [...path, normalized.children.length], maxDepth);
    if (normalizedChild) {
      normalized.children.push(normalizedChild);
    }
  }

  return normalized;
}

export function normalizeMindMap(input, options = {}) {
  const maxDepth = Number.isFinite(options.maxDepth) ? Math.max(0, options.maxDepth) : DEFAULT_MAX_DEPTH;
  const source = unwrapInput(input);

  if (Array.isArray(source)) {
    const roots = [];
    for (const item of source) {
      const root = normalizeNode(item, 0, [roots.length], maxDepth);
      if (root) {
        roots.push(root);
      }
    }

    if (roots.length === 0) {
      return null;
    }
    if (roots.length === 1) {
      return roots[0];
    }
    return {
      id: "0",
      label: options.rootLabel || "Mind Map",
      depth: 0,
      children: roots.map((root, index) => rebaseNode(root, [0, index], 1))
    };
  }

  return normalizeNode(source, 0, [0], maxDepth);
}

function rebaseNode(node, path, depth) {
  return {
    id: path.join("-"),
    label: node.label,
    depth,
    children: node.children.map((child, index) => rebaseNode(child, [...path, index], depth + 1))
  };
}

function measureTree(tree) {
  const leaves = [];
  const nodes = [];
  let maxDepth = 0;

  function visit(node, branchIndex) {
    maxDepth = Math.max(maxDepth, node.depth);
    nodes.push({ node, branchIndex });

    if (node.children.length === 0) {
      leaves.push(node);
      return;
    }

    node.children.forEach((child, index) => {
      visit(child, node.depth === 0 ? index : branchIndex);
    });
  }

  visit(tree, 0);
  return { leaves, nodes, maxDepth };
}

export function layoutMindMap(tree, options = {}) {
  if (!tree) {
    return { nodes: [], links: [], width: 0, height: 0 };
  }

  const nodeWidth = options.nodeWidth || DEFAULT_NODE_WIDTH;
  const nodeHeight = options.nodeHeight || DEFAULT_NODE_HEIGHT;
  const xGap = options.xGap || DEFAULT_X_GAP;
  const yGap = options.yGap || DEFAULT_Y_GAP;
  const margin = options.margin || DEFAULT_MARGIN;
  const { leaves, maxDepth } = measureTree(tree);
  const yById = new Map();
  const nodes = [];
  const links = [];
  let nextLeafY = margin;

  function assignY(node) {
    if (node.children.length === 0) {
      const y = nextLeafY;
      nextLeafY += nodeHeight + yGap;
      yById.set(node.id, y);
      return y + nodeHeight / 2;
    }

    const childCenters = node.children.map(assignY);
    const center = childCenters.reduce((sum, value) => sum + value, 0) / childCenters.length;
    yById.set(node.id, center - nodeHeight / 2);
    return center;
  }

  assignY(tree);

  function flatten(node, branchIndex = 0) {
    const color = node.depth === 0 ? "#334155" : BRANCH_COLORS[branchIndex % BRANCH_COLORS.length];
    const layoutNode = {
      id: node.id,
      label: node.label,
      depth: node.depth,
      x: margin + node.depth * (nodeWidth + xGap),
      y: Math.max(margin, Math.round(yById.get(node.id))),
      width: nodeWidth,
      height: nodeHeight,
      color
    };
    nodes.push(layoutNode);

    node.children.forEach((child, index) => {
      const childBranchIndex = node.depth === 0 ? index : branchIndex;
      links.push({
        source: node.id,
        target: child.id,
        color: BRANCH_COLORS[childBranchIndex % BRANCH_COLORS.length]
      });
      flatten(child, childBranchIndex);
    });
  }

  flatten(tree);

  const width = margin * 2 + (maxDepth + 1) * nodeWidth + maxDepth * xGap;
  const height = margin * 2 + Math.max(1, leaves.length) * nodeHeight + Math.max(0, leaves.length - 1) * yGap;

  return {
    nodes,
    links,
    width,
    height,
    nodeWidth,
    nodeHeight
  };
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function wrapLabel(label, maxLineLength = 18) {
  const text = String(label);
  if (text.length <= maxLineLength) {
    return [text];
  }

  const lines = [];
  let current = "";
  for (const part of text.split(/\s+/)) {
    if (!part) {
      continue;
    }
    if ((current + " " + part).trim().length <= maxLineLength) {
      current = (current + " " + part).trim();
      continue;
    }
    if (current) {
      lines.push(current);
    }
    current = part;
  }
  if (current) {
    lines.push(current);
  }

  if (lines.length <= 1 && text.length > maxLineLength) {
    return [text.slice(0, maxLineLength), text.slice(maxLineLength, maxLineLength * 2)];
  }
  return lines.slice(0, 2);
}

export function renderMindMapSvg(tree, options = {}) {
  const layout = layoutMindMap(tree, options);
  const background = options.background || "#f8fafc";
  const title = options.title || tree?.label || "Mind map";
  const nodeTextColor = options.nodeTextColor || "#0f172a";
  const rootFill = options.rootFill || "#e2e8f0";
  const childFill = options.childFill || "#ffffff";

  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const paths = layout.links
    .map((link) => {
      const source = nodeById.get(link.source);
      const target = nodeById.get(link.target);
      const startX = source.x + source.width;
      const startY = source.y + source.height / 2;
      const endX = target.x;
      const endY = target.y + target.height / 2;
      const curve = Math.max(48, (endX - startX) * 0.5);
      const d = `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`;
      return `<path d="${d}" fill="none" stroke="${escapeXml(link.color)}" stroke-width="3" stroke-linecap="round" opacity="0.78"/>`;
    })
    .join("");

  const nodeGroups = layout.nodes
    .map((node) => {
      const lines = wrapLabel(node.label);
      const lineHeight = 17;
      const firstY = node.y + node.height / 2 - ((lines.length - 1) * lineHeight) / 2 + 5;
      const text = lines
        .map((line, index) => {
          return `<tspan x="${node.x + 16}" y="${firstY + index * lineHeight}">${escapeXml(line)}</tspan>`;
        })
        .join("");
      const fill = node.depth === 0 ? rootFill : childFill;
      return [
        `<g class="mind-map-node" role="listitem" aria-label="${escapeXml(node.label)}">`,
        `<rect x="${node.x}" y="${node.y}" width="${node.width}" height="${node.height}" rx="10" fill="${escapeXml(fill)}" stroke="${escapeXml(node.color)}" stroke-width="2"/>`,
        `<text fill="${escapeXml(nodeTextColor)}" font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="14" font-weight="${node.depth === 0 ? "700" : "600"}">${text}</text>`,
        "</g>"
      ].join("");
    })
    .join("");

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(title)}" viewBox="0 0 ${layout.width} ${layout.height}" width="${layout.width}" height="${layout.height}">`,
    `<rect width="100%" height="100%" fill="${escapeXml(background)}"/>`,
    `<g class="mind-map-links">${paths}</g>`,
    `<g class="mind-map-nodes" role="list">${nodeGroups}</g>`,
    "</svg>"
  ].join("");
}

export function downloadSvg(svg, filename = "mind-map.svg") {
  if (typeof document === "undefined" || typeof URL === "undefined") {
    return;
  }
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, filename);
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadPngFromSvg(svg, filename = "mind-map.png", options = {}) {
  if (typeof document === "undefined" || typeof URL === "undefined" || typeof Image === "undefined") {
    return Promise.resolve(null);
  }
  return new Promise((resolve, reject) => {
    const scale = options.scale || 2;
    const image = new Image();
    const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const imageUrl = URL.createObjectURL(svgBlob);

    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil((options.width || image.width) * scale);
      canvas.height = Math.ceil((options.height || image.height) * scale);
      const context = canvas.getContext("2d");
      if (!context) {
        URL.revokeObjectURL(imageUrl);
        reject(new Error("Unable to create canvas context"));
        return;
      }
      context.fillStyle = options.background || "#ffffff";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(imageUrl);

      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Unable to render mind map PNG"));
          return;
        }
        const pngUrl = URL.createObjectURL(blob);
        triggerDownload(pngUrl, filename);
        window.setTimeout(() => URL.revokeObjectURL(pngUrl), 0);
        resolve(blob);
      }, "image/png");
    };

    image.onerror = () => {
      URL.revokeObjectURL(imageUrl);
      reject(new Error("Unable to load mind map SVG"));
    };

    image.src = imageUrl;
  });
}

function triggerDownload(url, filename) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}
