const DEFAULT_MAX_DEPTH = 5;
const DEFAULT_NODE_WIDTH = 184;
const DEFAULT_NODE_HEIGHT = 54;
const DEFAULT_X_GAP = 104;
const DEFAULT_Y_GAP = 28;
const DEFAULT_MARGIN = 32;
const DEFAULT_MIN_ZOOM = 0.35;
const DEFAULT_MAX_ZOOM = 2.5;
const DEFAULT_LABEL_LINE_LENGTH = 18;
const DEFAULT_LABEL_LINE_HEIGHT = 17;
const NODE_VERTICAL_PADDING = 22;

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
  const { maxDepth } = measureTree(tree);
  const dimensionsById = new Map();
  const yById = new Map();
  const nodes = [];
  const links = [];
  let nextLeafY = margin;

  function getDimensions(node) {
    if (!dimensionsById.has(node.id)) {
      const labelLines = wrapLabel(node.label, options.maxLineLength || DEFAULT_LABEL_LINE_LENGTH);
      dimensionsById.set(node.id, {
        width: nodeWidth,
        height: Math.max(nodeHeight, NODE_VERTICAL_PADDING + labelLines.length * DEFAULT_LABEL_LINE_HEIGHT),
        labelLines
      });
    }
    return dimensionsById.get(node.id);
  }

  function assignY(node) {
    const dimensions = getDimensions(node);
    if (node.children.length === 0) {
      const y = nextLeafY;
      nextLeafY += dimensions.height + yGap;
      yById.set(node.id, y);
      return y + dimensions.height / 2;
    }

    const childCenters = node.children.map(assignY);
    const center = childCenters.reduce((sum, value) => sum + value, 0) / childCenters.length;
    yById.set(node.id, center - dimensions.height / 2);
    return center;
  }

  assignY(tree);

  function flatten(node, branchIndex = 0) {
    const color = node.depth === 0 ? "#334155" : BRANCH_COLORS[branchIndex % BRANCH_COLORS.length];
    const dimensions = getDimensions(node);
    const layoutNode = {
      id: node.id,
      label: node.label,
      labelLines: dimensions.labelLines,
      depth: node.depth,
      x: margin + node.depth * (nodeWidth + xGap),
      y: Math.max(margin, Math.round(yById.get(node.id))),
      width: dimensions.width,
      height: dimensions.height,
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
  const height = Math.ceil(Math.max(...nodes.map((node) => node.y + node.height), margin + nodeHeight) + margin);

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

function wrapLabel(label, maxLineLength = DEFAULT_LABEL_LINE_LENGTH) {
  const text = String(label).replace(/\s+/g, " ").trim();
  if (text.length <= maxLineLength) {
    return [text];
  }

  const lines = [];
  let current = "";
  for (const part of text.split(" ")) {
    const chunks = chunkText(part, maxLineLength);
    for (const chunk of chunks) {
      if (!chunk) {
        continue;
      }
      if ((current + " " + chunk).trim().length <= maxLineLength) {
        current = (current + " " + chunk).trim();
        continue;
      }
      if (current) {
        lines.push(current);
      }
      current = chunk;
    }
  }
  if (current) {
    lines.push(current);
  }

  return lines.length ? lines : [text];
}

function chunkText(text, maxLineLength) {
  const chars = [...text];
  if (chars.length <= maxLineLength) {
    return [text];
  }
  const chunks = [];
  for (let index = 0; index < chars.length; index += maxLineLength) {
    chunks.push(chars.slice(index, index + maxLineLength).join(""));
  }
  return chunks;
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
      const lines = node.labelLines?.length ? node.labelLines : wrapLabel(node.label);
      const lineHeight = DEFAULT_LABEL_LINE_HEIGHT;
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

export function getMindMapSvgSize(svg) {
  const text = String(svg || "");
  const viewBox = text.match(/\bviewBox=(["'])([^"']+)\1/i);
  if (viewBox) {
    const [, , value] = viewBox;
    const parts = value
      .trim()
      .split(/[\s,]+/)
      .map(Number);
    if (parts.length >= 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3]) && parts[2] > 0 && parts[3] > 0) {
      return { width: parts[2], height: parts[3] };
    }
  }

  const width = numericSvgAttribute(text, "width");
  const height = numericSvgAttribute(text, "height");
  return {
    width,
    height
  };
}

export function calculateMindMapFitZoom(options = {}) {
  const viewportWidth = positiveNumber(options.viewportWidth);
  const viewportHeight = positiveNumber(options.viewportHeight);
  const contentWidth = positiveNumber(options.contentWidth);
  const contentHeight = positiveNumber(options.contentHeight);
  if (!viewportWidth || !viewportHeight || !contentWidth || !contentHeight) {
    return clampMindMapZoom(options.fallbackZoom || 1, options);
  }

  const padding = Math.max(0, Number.isFinite(options.padding) ? options.padding : DEFAULT_MARGIN);
  const availableWidth = Math.max(1, viewportWidth - padding * 2);
  const availableHeight = Math.max(1, viewportHeight - padding * 2);
  return clampMindMapZoom(Math.min(availableWidth / contentWidth, availableHeight / contentHeight), options);
}

export function clampMindMapZoom(value, options = {}) {
  const minZoom = positiveNumber(options.minZoom) || DEFAULT_MIN_ZOOM;
  const maxZoom = positiveNumber(options.maxZoom) || DEFAULT_MAX_ZOOM;
  const lower = Math.min(minZoom, maxZoom);
  const upper = Math.max(minZoom, maxZoom);
  const numeric = Number.isFinite(value) ? value : 1;
  return Math.round(Math.min(upper, Math.max(lower, numeric)) * 100) / 100;
}

function numericSvgAttribute(text, name) {
  const match = text.match(new RegExp(`\\b${name}=(["'])([0-9.]+)(?:px)?\\1`, "i"));
  if (!match) return 0;
  const value = Number(match[2]);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function positiveNumber(value) {
  return Number.isFinite(value) && value > 0 ? value : 0;
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
