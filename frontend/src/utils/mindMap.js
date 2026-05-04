import { hierarchy, tree as d3Tree } from "d3-hierarchy";
import { linkHorizontal } from "d3-shape";

const DEFAULT_MAX_DEPTH = 5;
const DEFAULT_NODE_WIDTH = 184;
const DEFAULT_NODE_HEIGHT = 54;
const DEFAULT_X_GAP = 98;
const DEFAULT_Y_GAP = 28;
const DEFAULT_MARGIN = 32;
const DEFAULT_MIN_ZOOM = 0.35;
const DEFAULT_MAX_ZOOM = 2.5;
const DEFAULT_LABEL_LINE_LENGTH = 18;
const DEFAULT_LABEL_LINE_HEIGHT = 17;
const NODE_VERTICAL_PADDING = 22;
const DEFAULT_VISIBLE_DEPTH = 3;

const BRANCH_COLORS = [
  "#0f766e",
  "#2563eb",
  "#b45309",
  "#16a34a",
  "#be123c",
  "#0891b2",
  "#7c3aed",
  "#4d7c0f"
];

const BRANCH_TINTS = [
  "#d9f5f1",
  "#e6efff",
  "#fff1d6",
  "#e3f8e7",
  "#ffe5ed",
  "#dcf7fb",
  "#efe8ff",
  "#e8f5d7"
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

export function createVisibleMindMap(tree, options = {}) {
  if (!tree) return null;

  const visibleDepth = normalizeVisibleDepth(options.visibleDepth);
  const query = normalizeSearchText(options.query);
  const includeSearchPaths = query.length > 0;

  function cloneVisible(node) {
    const isSearchMatch = includeSearchPaths && normalizeSearchText(node.label).includes(query);
    const children = [];
    let hiddenCount = 0;

    for (const child of node.children || []) {
      const childHasMatch = includeSearchPaths && subtreeIncludesQuery(child, query);
      const isWithinDepth = child.depth <= visibleDepth;

      if (isWithinDepth || childHasMatch) {
        children.push(cloneVisible(child));
        continue;
      }

      hiddenCount += countDescendants(child);
    }

    if (hiddenCount > 0) {
      children.push({
        id: `${node.id}-collapsed-${hiddenCount}`,
        label: `还有 ${hiddenCount} 个要点`,
        depth: node.depth + 1,
        children: [],
        isCollapsedSummary: true,
        hiddenCount
      });
    }

    const isSearchAncestor =
      includeSearchPaths &&
      !isSearchMatch &&
      children.some((child) => child.isSearchMatch || child.isSearchAncestor);

    return {
      id: node.id,
      label: node.label,
      depth: node.depth,
      children,
      isSearchMatch,
      isSearchAncestor
    };
  }

  return cloneVisible(tree);
}

function normalizeVisibleDepth(value) {
  if (value === "all" || value === Infinity) return Infinity;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_VISIBLE_DEPTH;
  return Math.max(0, Math.min(DEFAULT_MAX_DEPTH, Math.round(numeric)));
}

function normalizeSearchText(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase();
}

function subtreeIncludesQuery(node, query) {
  if (!query) return false;
  if (normalizeSearchText(node.label).includes(query)) return true;
  return (node.children || []).some((child) => subtreeIncludesQuery(child, query));
}

function countDescendants(node) {
  return 1 + (node.children || []).reduce((sum, child) => sum + countDescendants(child), 0);
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

  const xGap = options.xGap || DEFAULT_X_GAP;
  const yGap = options.yGap || DEFAULT_Y_GAP;
  const margin = options.margin || DEFAULT_MARGIN;
  const maxLineLength = options.maxLineLength || DEFAULT_LABEL_LINE_LENGTH;
  const root = hierarchy(tree, (node) => node.children || []);
  const dimensionsById = new Map();
  const columnWidths = [];
  let maxNodeHeight = DEFAULT_NODE_HEIGHT;

  root.each((hierarchyNode) => {
    const dimensions = measureNode(hierarchyNode.data, {
      maxLineLength,
      nodeWidth: options.nodeWidth
    });
    dimensionsById.set(hierarchyNode.data.id, dimensions);
    columnWidths[hierarchyNode.depth] = Math.max(columnWidths[hierarchyNode.depth] || 0, dimensions.width);
    maxNodeHeight = Math.max(maxNodeHeight, dimensions.height);
  });

  d3Tree()
    .nodeSize([maxNodeHeight + yGap, 1])
    .separation((a, b) => (a.parent === b.parent ? 1.05 : 1.48))(root);

  const rootNodes = root.descendants();
  const minTop = Math.min(...rootNodes.map((node) => node.x - dimensionsById.get(node.data.id).height / 2));
  const columnX = columnWidths.reduce((positions, width, index) => {
    if (index === 0) {
      positions.push(margin);
      return positions;
    }
    positions.push(positions[index - 1] + columnWidths[index - 1] + xGap);
    return positions;
  }, []);

  const nodes = rootNodes.map((hierarchyNode) => {
    const source = hierarchyNode.data;
    const dimensions = dimensionsById.get(source.id);
    const branchIndex = branchIndexForHierarchyNode(hierarchyNode);
    const color = source.depth === 0 ? "#0f172a" : BRANCH_COLORS[branchIndex % BRANCH_COLORS.length];
    const tint = source.depth === 0 ? "#0f172a" : BRANCH_TINTS[branchIndex % BRANCH_TINTS.length];

    return {
      id: source.id,
      label: source.label,
      labelLines: dimensions.labelLines,
      depth: source.depth,
      branchIndex,
      x: columnX[hierarchyNode.depth] || margin,
      y: Math.round(margin + hierarchyNode.x - dimensions.height / 2 - minTop),
      width: dimensions.width,
      height: dimensions.height,
      color,
      tint,
      isCollapsedSummary: Boolean(source.isCollapsedSummary),
      hiddenCount: source.hiddenCount || 0,
      isSearchMatch: Boolean(source.isSearchMatch),
      isSearchAncestor: Boolean(source.isSearchAncestor),
      childrenCount: (source.children || []).length
    };
  });

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const curve = linkHorizontal()
    .x((point) => point.x)
    .y((point) => point.y);
  const links = root.links().map((link) => {
    const source = nodeById.get(link.source.data.id);
    const target = nodeById.get(link.target.data.id);
    return {
      source: source.id,
      target: target.id,
      color: target.color,
      path: curve({
        source: {
          x: source.x + source.width - 4,
          y: source.y + source.height / 2
        },
        target: {
          x: target.x + 4,
          y: target.y + target.height / 2
        }
      })
    };
  });

  const width = Math.ceil(Math.max(...nodes.map((node) => node.x + node.width), margin + DEFAULT_NODE_WIDTH) + margin);
  const height = Math.ceil(Math.max(...nodes.map((node) => node.y + node.height), margin + DEFAULT_NODE_HEIGHT) + margin);

  return {
    nodes,
    links,
    width,
    height,
    nodeWidth: DEFAULT_NODE_WIDTH,
    nodeHeight: DEFAULT_NODE_HEIGHT
  };
}

function measureNode(node, options = {}) {
  const labelLines = wrapLabel(node.label, options.maxLineLength || DEFAULT_LABEL_LINE_LENGTH);
  const longestLine = Math.max(...labelLines.map((line) => [...line].length), 1);
  const depth = node.depth || 0;
  const minWidth = depth === 0 ? 224 : depth === 1 ? 214 : 178;
  const maxWidth = depth === 0 ? 292 : depth === 1 ? 260 : 232;
  const measuredWidth = options.nodeWidth || Math.round(34 + longestLine * 9.2);
  const width = node.isCollapsedSummary ? 150 : clampNumber(measuredWidth, minWidth, maxWidth);
  const baseHeight = node.isCollapsedSummary ? 42 : DEFAULT_NODE_HEIGHT;
  const height = Math.max(baseHeight, NODE_VERTICAL_PADDING + labelLines.length * DEFAULT_LABEL_LINE_HEIGHT);

  return {
    width,
    height,
    labelLines
  };
}

function branchIndexForHierarchyNode(node) {
  if (!node.parent) return 0;
  let current = node;
  while (current.parent && current.parent.depth > 0) {
    current = current.parent;
  }
  return current.parent?.children?.indexOf(current) || 0;
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
  const background = options.background || "#f6f8fb";
  const title = options.title || tree?.label || "Mind map";
  const focusRelatedIds = collectFocusRelatedIds(tree, options.focusedNodeId);
  const hasFocus = focusRelatedIds.size > 0;
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const paths = layout.links
    .map((link) => {
      const target = nodeById.get(link.target);
      const isDimmed = hasFocus && !focusRelatedIds.has(link.source) && !focusRelatedIds.has(link.target);
      return `<path class="mind-map-link${isDimmed ? " is-dimmed" : ""}" d="${escapeXml(link.path)}" fill="none" stroke="${escapeXml(link.color)}" stroke-width="${target?.isCollapsedSummary ? "2" : "3.5"}" stroke-linecap="round" opacity="${isDimmed ? "0.16" : "0.64"}"/>`;
    })
    .join("");

  const nodeGroups = layout.nodes
    .map((node) => renderNodeGroup(node, { focusRelatedIds, hasFocus }))
    .join("");

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(title)}" viewBox="0 0 ${layout.width} ${layout.height}" width="${layout.width}" height="${layout.height}">`,
    "<defs>",
    '<linearGradient id="mind-map-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#fbfdff"/><stop offset="55%" stop-color="#f2f7f8"/><stop offset="100%" stop-color="#eef6f3"/></linearGradient>',
    '<pattern id="mind-map-grid" width="34" height="34" patternUnits="userSpaceOnUse"><path d="M 34 0 L 0 0 0 34" fill="none" stroke="#d7e2e5" stroke-width="1" opacity="0.46"/></pattern>',
    '<filter id="mind-map-shadow" x="-20%" y="-30%" width="140%" height="170%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.10"/></filter>',
    "</defs>",
    `<rect width="100%" height="100%" fill="${escapeXml(background)}"/>`,
    '<rect width="100%" height="100%" fill="url(#mind-map-bg)"/>',
    '<rect width="100%" height="100%" fill="url(#mind-map-grid)"/>',
    `<g class="mind-map-links">${paths}</g>`,
    `<g class="mind-map-nodes" role="list">${nodeGroups}</g>`,
    "</svg>"
  ].join("");
}

function renderNodeGroup(node, options) {
  const classes = ["mind-map-node"];
  if (node.isCollapsedSummary) classes.push("is-collapsed-summary");
  if (node.isSearchMatch) classes.push("is-search-match");
  if (node.isSearchAncestor) classes.push("is-search-ancestor");
  if (options.hasFocus && options.focusRelatedIds.has(node.id)) classes.push("is-focus-related");
  if (options.hasFocus && !options.focusRelatedIds.has(node.id)) classes.push("is-dimmed");

  const lineHeight = DEFAULT_LABEL_LINE_HEIGHT;
  const firstY = node.y + node.height / 2 - ((node.labelLines.length - 1) * lineHeight) / 2 + 5;
  const textColor = node.depth === 0 ? "#f8fafc" : node.isCollapsedSummary ? "#526172" : "#0f172a";
  const fontWeight = node.depth === 0 ? "800" : node.isCollapsedSummary ? "700" : node.depth === 1 ? "780" : "650";
  const fill = node.depth === 0 ? "#0f172a" : node.isCollapsedSummary ? "#f1f5f9" : node.depth === 1 ? node.tint : "#ffffff";
  const stroke = node.isSearchMatch ? "#14b8a6" : node.color;
  const strokeWidth = node.isSearchMatch ? 3 : node.isCollapsedSummary ? 1.5 : 2;
  const opacity = classes.includes("is-dimmed") ? "0.34" : "1";
  const fontSize = node.isCollapsedSummary ? "13" : node.depth <= 1 ? "15" : "14";
  const textX = node.x + node.width / 2 + (node.depth > 0 && !node.isCollapsedSummary ? 4 : 0);
  const text = node.labelLines
    .map((line, index) => {
      return `<tspan x="${textX}" y="${firstY + index * lineHeight}">${escapeXml(line)}</tspan>`;
    })
    .join("");
  const accent =
    node.depth > 0 && !node.isCollapsedSummary
      ? `<rect x="${node.x + 8}" y="${node.y + 9}" width="4" height="${Math.max(24, node.height - 18)}" rx="2" fill="${escapeXml(node.color)}" opacity="${node.isSearchAncestor ? "0.9" : "0.72"}"/>`
      : "";
  const searchRing = node.isSearchMatch
    ? `<rect x="${node.x - 4}" y="${node.y - 4}" width="${node.width + 8}" height="${node.height + 8}" rx="12" fill="none" stroke="#14b8a6" stroke-width="2" stroke-dasharray="5 5" opacity="0.9"/>`
    : "";

  return [
    `<g class="${classes.join(" ")}" role="listitem" tabindex="0" aria-label="${escapeXml(node.label)}" data-node-id="${escapeXml(node.id)}" data-depth="${node.depth}" opacity="${opacity}">`,
    searchRing,
    `<rect x="${node.x}" y="${node.y}" width="${node.width}" height="${node.height}" rx="8" fill="${escapeXml(fill)}" stroke="${escapeXml(stroke)}" stroke-width="${strokeWidth}"${node.isCollapsedSummary ? ' stroke-dasharray="4 5"' : ""} filter="url(#mind-map-shadow)"/>`,
    accent,
    `<text fill="${escapeXml(textColor)}" font-family="Fira Sans, PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif" font-size="${fontSize}" font-weight="${fontWeight}" text-anchor="middle">${text}</text>`,
    "</g>"
  ].join("");
}

function collectFocusRelatedIds(tree, focusedNodeId) {
  const related = new Set();
  if (!tree || !focusedNodeId) return related;

  const path = findPathToNode(tree, focusedNodeId);
  if (path.length === 0) return related;
  path.forEach((node) => related.add(node.id));
  addDescendantIds(path[path.length - 1], related);
  return related;
}

function findPathToNode(node, targetId, path = []) {
  const nextPath = [...path, node];
  if (node.id === targetId) return nextPath;
  for (const child of node.children || []) {
    const result = findPathToNode(child, targetId, nextPath);
    if (result.length) return result;
  }
  return [];
}

function addDescendantIds(node, target) {
  target.add(node.id);
  for (const child of node.children || []) {
    addDescendantIds(child, target);
  }
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

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
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

export function buildInteractiveMindMapHtml(tree, options = {}) {
  const normalizedTree = isNormalizedMindMapTree(tree) ? tree : normalizeMindMap(tree);
  if (!normalizedTree) {
    return "";
  }

  const title = normalizeLabel(options.title) || normalizedTree.label || "思维导图";
  const state = {
    title,
    visibleDepth: options.visibleDepth || "1",
    searchQuery: normalizeLabel(options.searchQuery),
    focusedNodeId: normalizeLabel(options.focusedNodeId)
  };
  const visibleTree = createVisibleMindMap(normalizedTree, {
    visibleDepth: state.visibleDepth,
    query: state.searchQuery
  });
  const initialSvg = renderMindMapSvg(visibleTree, { focusedNodeId: state.focusedNodeId });
  const documentTitle = `${title} - 交互式思维导图`;

  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>${escapeXml(documentTitle)}</title>`,
    "<style>",
    getInteractiveMindMapCss(),
    "</style>",
    "</head>",
    "<body>",
    '<main class="mind-map-export" data-mind-map-app>',
    '<header class="mind-map-export-header">',
    "<div>",
    '<p class="mind-map-export-eyebrow">交互式思维导图</p>',
    `<h1>${escapeXml(title)}</h1>`,
    "</div>",
    '<div class="mind-map-export-toolbar" aria-label="思维导图工具">',
    '<button type="button" id="mind-map-zoom-out" aria-label="缩小思维导图">-</button>',
    '<output id="mind-map-zoom-value" aria-live="polite">100%</output>',
    '<button type="button" id="mind-map-zoom-in" aria-label="放大思维导图">+</button>',
    '<button type="button" id="mind-map-fit" aria-label="适配窗口显示完整思维导图">适配</button>',
    '<button type="button" id="mind-map-reset" aria-label="重置思维导图缩放">重置</button>',
    '<button type="button" id="mind-map-download-svg" aria-label="下载当前思维导图 SVG">SVG</button>',
    "</div>",
    "</header>",
    '<section class="mind-map-export-controls" aria-label="思维导图筛选">',
    '<label class="mind-map-export-search">',
    '<span>搜索</span>',
    '<input id="mind-map-search" type="search" aria-label="搜索思维导图节点" placeholder="搜索节点">',
    '<button type="button" id="mind-map-clear-search" aria-label="清空搜索">清空</button>',
    "</label>",
    '<label class="mind-map-export-level">',
    '<span>层级</span>',
    '<select id="mind-map-level" aria-label="显示思维导图层级">',
    '<option value="1">1 层</option>',
    '<option value="2">2 层</option>',
    '<option value="3">3 层</option>',
    '<option value="all">全部</option>',
    "</select>",
    "</label>",
    '<button type="button" id="mind-map-clear-focus" aria-label="清除思维导图节点聚焦" hidden>清除聚焦</button>',
    "</section>",
    '<section class="mind-map-export-meta" aria-live="polite">',
    '<span id="mind-map-node-count">节点 0</span>',
    '<span id="mind-map-match-count" hidden>匹配 0</span>',
    '<span id="mind-map-focus-label" hidden></span>',
    "</section>",
    '<section class="mind-map-export-viewport" data-mind-map-viewport tabindex="0">',
    '<div class="mind-map-export-canvas" data-mind-map-canvas>',
    `<div class="mind-map-export-surface" data-mind-map-surface>${initialSvg}</div>`,
    "</div>",
    "</section>",
    "</main>",
    "<script>",
    getInteractiveMindMapScript(safeScriptJson(normalizedTree), safeScriptJson(state)),
    "</script>",
    "</body>",
    "</html>"
  ].join("\n");
}

function isNormalizedMindMapTree(value) {
  return Boolean(value && typeof value === "object" && typeof value.label === "string" && Array.isArray(value.children));
}

function safeScriptJson(value) {
  return JSON.stringify(value)
    .replaceAll("<", "\\u003c")
    .replaceAll(">", "\\u003e")
    .replaceAll("&", "\\u0026")
    .replaceAll("\u2028", "\\u2028")
    .replaceAll("\u2029", "\\u2029");
}

function getInteractiveMindMapCss() {
  return `
:root {
  color-scheme: light;
  --page-bg: #edf3f4;
  --ink: #10202f;
  --muted: #5d6b78;
  --line: #cfdade;
  --panel: rgba(255, 255, 255, 0.82);
  --accent: #0f766e;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at 12% 10%, rgba(20, 184, 166, 0.11), transparent 30%),
    linear-gradient(135deg, #f8fbfc 0%, var(--page-bg) 100%);
  color: var(--ink);
  font-family: "Fira Sans", "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
}

button,
input,
select {
  font: inherit;
}

button {
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #ffffff;
  color: var(--ink);
  cursor: pointer;
  font-weight: 760;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

button:hover {
  border-color: #8fb4b1;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

button:focus-visible,
input:focus-visible,
select:focus-visible,
.mind-map-export-viewport:focus-visible {
  outline: 3px solid rgba(20, 184, 166, 0.34);
  outline-offset: 2px;
}

.mind-map-export {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 12px;
  min-height: 100vh;
  padding: 18px;
}

.mind-map-export-header,
.mind-map-export-controls,
.mind-map-export-meta {
  width: min(1400px, 100%);
  margin: 0 auto;
}

.mind-map-export-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid rgba(207, 218, 222, 0.78);
  border-radius: 8px;
  background: var(--panel);
  backdrop-filter: blur(18px);
  box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
}

.mind-map-export-eyebrow {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 860;
  letter-spacing: 0;
}

.mind-map-export h1 {
  margin: 0;
  font-size: clamp(20px, 3vw, 32px);
  line-height: 1.15;
}

.mind-map-export-toolbar,
.mind-map-export-controls,
.mind-map-export-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.mind-map-export-toolbar button,
.mind-map-export-controls button {
  padding: 0 12px;
}

#mind-map-zoom-value {
  min-width: 58px;
  text-align: center;
  color: var(--muted);
  font-weight: 800;
}

.mind-map-export-controls {
  padding: 10px;
  border: 1px solid rgba(207, 218, 222, 0.76);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.7);
}

.mind-map-export-search,
.mind-map-export-level {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #ffffff;
}

.mind-map-export-search span,
.mind-map-export-level span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 780;
}

.mind-map-export-search input,
.mind-map-export-level select {
  height: 34px;
  min-width: 170px;
  border: 0;
  background: transparent;
  color: var(--ink);
}

.mind-map-export-level select {
  min-width: 92px;
}

#mind-map-clear-search[hidden],
#mind-map-clear-focus[hidden],
#mind-map-match-count[hidden],
#mind-map-focus-label[hidden] {
  display: none;
}

.mind-map-export-meta {
  min-height: 28px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 740;
}

.mind-map-export-meta span {
  padding: 5px 9px;
  border: 1px solid rgba(207, 218, 222, 0.72);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
}

.mind-map-export-viewport {
  width: min(1400px, 100%);
  min-height: 58vh;
  margin: 0 auto;
  overflow: auto;
  border: 1px solid rgba(207, 218, 222, 0.82);
  border-radius: 8px;
  background:
    linear-gradient(rgba(215, 226, 229, 0.48) 1px, transparent 1px),
    linear-gradient(90deg, rgba(215, 226, 229, 0.48) 1px, transparent 1px),
    #f8fbfc;
  background-size: 34px 34px, 34px 34px, auto;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.72);
  cursor: grab;
}

.mind-map-export-viewport.dragging {
  cursor: grabbing;
  user-select: none;
}

.mind-map-export-canvas {
  display: grid;
  place-items: center;
  min-width: 100%;
  min-height: 100%;
  padding: 34px;
}

.mind-map-export-surface {
  transform: scale(var(--mind-map-zoom, 1));
  transform-origin: top left;
}

.mind-map-export-surface svg {
  display: block;
  max-width: none;
  overflow: visible;
}

.mind-map-node {
  cursor: pointer;
}

.mind-map-node:hover {
  filter: brightness(1.02);
}

@media (max-width: 760px) {
  .mind-map-export {
    padding: 10px;
  }

  .mind-map-export-header {
    align-items: stretch;
    flex-direction: column;
  }

  .mind-map-export-toolbar,
  .mind-map-export-controls {
    align-items: stretch;
  }

  .mind-map-export-search,
  .mind-map-export-level,
  .mind-map-export-search input {
    width: 100%;
  }

  .mind-map-export-viewport {
    min-height: 62vh;
  }
}
`.trim();
}

function getInteractiveMindMapScript(treeJson, stateJson) {
  return `
const MIND_MAP_TREE = ${treeJson};
const INITIAL_STATE = ${stateJson};
const DEFAULT_MAX_DEPTH = ${DEFAULT_MAX_DEPTH};
const DEFAULT_NODE_WIDTH = ${DEFAULT_NODE_WIDTH};
const DEFAULT_NODE_HEIGHT = ${DEFAULT_NODE_HEIGHT};
const DEFAULT_X_GAP = ${DEFAULT_X_GAP};
const DEFAULT_Y_GAP = ${DEFAULT_Y_GAP};
const DEFAULT_MARGIN = ${DEFAULT_MARGIN};
const DEFAULT_LABEL_LINE_LENGTH = ${DEFAULT_LABEL_LINE_LENGTH};
const DEFAULT_LABEL_LINE_HEIGHT = ${DEFAULT_LABEL_LINE_HEIGHT};
const NODE_VERTICAL_PADDING = ${NODE_VERTICAL_PADDING};
const BRANCH_COLORS = ${safeScriptJson(BRANCH_COLORS)};
const BRANCH_TINTS = ${safeScriptJson(BRANCH_TINTS)};
const state = {
  visibleDepth: INITIAL_STATE.visibleDepth || "1",
  searchQuery: INITIAL_STATE.searchQuery || "",
  focusedNodeId: INITIAL_STATE.focusedNodeId || "",
  zoom: 1,
  title: INITIAL_STATE.title || "思维导图"
};
const elements = {};
let dragState = null;
let ignoreNextNodeClick = false;

document.addEventListener("DOMContentLoaded", initMindMap);

function initMindMap() {
  elements.app = document.querySelector("[data-mind-map-app]");
  elements.viewport = document.querySelector("[data-mind-map-viewport]");
  elements.canvas = document.querySelector("[data-mind-map-canvas]");
  elements.surface = document.querySelector("[data-mind-map-surface]");
  elements.search = document.getElementById("mind-map-search");
  elements.clearSearch = document.getElementById("mind-map-clear-search");
  elements.level = document.getElementById("mind-map-level");
  elements.clearFocus = document.getElementById("mind-map-clear-focus");
  elements.nodeCount = document.getElementById("mind-map-node-count");
  elements.matchCount = document.getElementById("mind-map-match-count");
  elements.focusLabel = document.getElementById("mind-map-focus-label");
  elements.zoomValue = document.getElementById("mind-map-zoom-value");

  elements.search.value = state.searchQuery;
  elements.level.value = String(state.visibleDepth);
  elements.search.addEventListener("input", function (event) {
    state.searchQuery = event.target.value;
    renderMindMap();
  });
  elements.clearSearch.addEventListener("click", function () {
    state.searchQuery = "";
    elements.search.value = "";
    renderMindMap();
  });
  elements.level.addEventListener("change", function (event) {
    state.visibleDepth = event.target.value;
    renderMindMap();
    fitMap();
  });
  elements.clearFocus.addEventListener("click", function () {
    state.focusedNodeId = "";
    renderMindMap();
  });
  document.getElementById("mind-map-zoom-out").addEventListener("click", function () {
    setZoom(state.zoom - 0.16);
  });
  document.getElementById("mind-map-zoom-in").addEventListener("click", function () {
    setZoom(state.zoom + 0.16);
  });
  document.getElementById("mind-map-reset").addEventListener("click", function () {
    setZoom(1);
  });
  document.getElementById("mind-map-fit").addEventListener("click", fitMap);
  document.getElementById("mind-map-download-svg").addEventListener("click", downloadCurrentSvg);
  elements.viewport.addEventListener("click", handleMindMapNodeClick);
  elements.viewport.addEventListener("pointerdown", handleViewportPointerDown);
  elements.viewport.addEventListener("pointermove", handleViewportPointerMove);
  elements.viewport.addEventListener("pointerup", handleViewportPointerUp);
  elements.viewport.addEventListener("pointerleave", handleViewportPointerUp);
  elements.viewport.addEventListener("pointercancel", handleViewportPointerUp);
  elements.viewport.addEventListener("wheel", handleViewportWheel, { passive: false });
  window.addEventListener("resize", fitMap);
  renderMindMap();
  fitMap();
}

function renderMindMap() {
  const visibleTree = createVisibleMindMap(MIND_MAP_TREE, {
    visibleDepth: state.visibleDepth,
    query: state.searchQuery
  });
  const svg = renderMindMapSvg(visibleTree, { focusedNodeId: state.focusedNodeId });
  elements.surface.innerHTML = svg;
  const size = getMindMapSvgSize(svg);
  elements.canvas.style.width = Math.max(1, Math.ceil(size.width * state.zoom)) + "px";
  elements.canvas.style.height = Math.max(1, Math.ceil(size.height * state.zoom)) + "px";
  elements.surface.style.setProperty("--mind-map-zoom", String(state.zoom));
  updateMeta(visibleTree);
}

function updateMeta(visibleTree) {
  const matches = countMatches(MIND_MAP_TREE, state.searchQuery);
  const focusLabel = findNodeLabel(visibleTree, state.focusedNodeId) || findNodeLabel(MIND_MAP_TREE, state.focusedNodeId);
  elements.nodeCount.textContent = "节点 " + countNodes(visibleTree);
  elements.matchCount.textContent = "匹配 " + matches;
  elements.matchCount.hidden = !state.searchQuery;
  elements.focusLabel.textContent = focusLabel ? "聚焦 " + focusLabel : "";
  elements.focusLabel.hidden = !focusLabel;
  elements.clearFocus.hidden = !focusLabel;
  elements.clearSearch.hidden = !state.searchQuery;
  elements.zoomValue.textContent = Math.round(state.zoom * 100) + "%";
}

function setZoom(value) {
  const nextZoom = clampZoom(value);
  const previousZoom = state.zoom;
  if (nextZoom === previousZoom) return;
  state.zoom = nextZoom;
  renderMindMap();
}

function fitMap() {
  const svg = elements.surface.querySelector("svg");
  if (!svg || !elements.viewport) return;
  const size = getMindMapSvgSize(svg.outerHTML);
  const availableWidth = Math.max(1, elements.viewport.clientWidth - 68);
  const availableHeight = Math.max(1, elements.viewport.clientHeight - 68);
  setZoom(Math.min(1.8, availableWidth / size.width, availableHeight / size.height));
}

function handleMindMapNodeClick(event) {
  if (ignoreNextNodeClick) {
    ignoreNextNodeClick = false;
    return;
  }
  const target = event.target.closest("[data-node-id]");
  const nodeId = target ? target.getAttribute("data-node-id") : "";
  if (!nodeId || nodeId.indexOf("-collapsed-") !== -1) return;
  state.focusedNodeId = state.focusedNodeId === nodeId ? "" : nodeId;
  renderMindMap();
  if (state.focusedNodeId) centerNodeInViewport(nodeId);
}

function handleViewportPointerDown(event) {
  if (event.button !== 0) return;
  if (event.target.closest("button, input, select, textarea, a")) return;
  dragState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    scrollLeft: elements.viewport.scrollLeft,
    scrollTop: elements.viewport.scrollTop
  };
  elements.viewport.classList.add("dragging");
  elements.viewport.setPointerCapture(event.pointerId);
}

function handleViewportPointerMove(event) {
  if (!dragState || dragState.pointerId !== event.pointerId) return;
  const dx = event.clientX - dragState.startX;
  const dy = event.clientY - dragState.startY;
  if (Math.abs(dx) + Math.abs(dy) > 4) ignoreNextNodeClick = true;
  elements.viewport.scrollLeft = dragState.scrollLeft - dx;
  elements.viewport.scrollTop = dragState.scrollTop - dy;
}

function handleViewportPointerUp(event) {
  if (!dragState || dragState.pointerId !== event.pointerId) return;
  elements.viewport.releasePointerCapture(event.pointerId);
  dragState = null;
  elements.viewport.classList.remove("dragging");
  if (ignoreNextNodeClick) {
    window.setTimeout(function () {
      ignoreNextNodeClick = false;
    }, 0);
  }
}

function handleViewportWheel(event) {
  event.preventDefault();
  const previousZoom = state.zoom;
  const nextZoom = clampZoom(previousZoom + (event.deltaY > 0 ? -0.12 : 0.12));
  if (nextZoom === previousZoom) return;
  const rect = elements.viewport.getBoundingClientRect();
  const offsetX = event.clientX - rect.left;
  const offsetY = event.clientY - rect.top;
  const ratio = nextZoom / previousZoom;
  state.zoom = nextZoom;
  renderMindMap();
  elements.viewport.scrollLeft = (elements.viewport.scrollLeft + offsetX) * ratio - offsetX;
  elements.viewport.scrollTop = (elements.viewport.scrollTop + offsetY) * ratio - offsetY;
}

function centerNodeInViewport(nodeId) {
  const nodeElement = Array.from(elements.viewport.querySelectorAll("[data-node-id]")).find(function (element) {
    return element.getAttribute("data-node-id") === nodeId;
  });
  if (!nodeElement) return;
  const nodeRect = nodeElement.getBoundingClientRect();
  const viewportRect = elements.viewport.getBoundingClientRect();
  elements.viewport.scrollLeft += nodeRect.left - viewportRect.left - viewportRect.width / 2 + nodeRect.width / 2;
  elements.viewport.scrollTop += nodeRect.top - viewportRect.top - viewportRect.height / 2 + nodeRect.height / 2;
}

function downloadCurrentSvg() {
  const svg = elements.surface.querySelector("svg");
  if (!svg) return;
  const blob = new Blob([svg.outerHTML], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = safeFilename(state.title) + ".svg";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(function () {
    URL.revokeObjectURL(url);
  }, 0);
}

function createVisibleMindMap(tree, options) {
  const visibleDepth = normalizeVisibleDepth(options.visibleDepth);
  const query = normalizeSearchText(options.query);
  const includeSearchPaths = query.length > 0;

  function cloneVisible(node) {
    const isSearchMatch = includeSearchPaths && normalizeSearchText(node.label).indexOf(query) !== -1;
    const children = [];
    let hiddenCount = 0;

    for (const child of node.children || []) {
      const childHasMatch = includeSearchPaths && subtreeIncludesQuery(child, query);
      const isWithinDepth = child.depth <= visibleDepth;
      if (isWithinDepth || childHasMatch) {
        children.push(cloneVisible(child));
      } else {
        hiddenCount += countDescendants(child);
      }
    }

    if (hiddenCount > 0) {
      children.push({
        id: node.id + "-collapsed-" + hiddenCount,
        label: "还有 " + hiddenCount + " 个要点",
        depth: node.depth + 1,
        children: [],
        isCollapsedSummary: true,
        hiddenCount: hiddenCount
      });
    }

    const isSearchAncestor = includeSearchPaths && !isSearchMatch && children.some(function (child) {
      return child.isSearchMatch || child.isSearchAncestor;
    });

    return {
      id: node.id,
      label: node.label,
      depth: node.depth,
      children: children,
      isSearchMatch: isSearchMatch,
      isSearchAncestor: isSearchAncestor
    };
  }

  return cloneVisible(tree);
}

function layoutMindMap(tree) {
  if (!tree) return { nodes: [], links: [], width: 0, height: 0 };
  const dimensionsById = new Map();
  const columnWidths = [];
  const centersById = new Map();
  let cursorY = DEFAULT_MARGIN;

  visitTree(tree, function (node) {
    const dimensions = measureNode(node);
    dimensionsById.set(node.id, dimensions);
    columnWidths[node.depth] = Math.max(columnWidths[node.depth] || 0, dimensions.width);
  });

  assignCenters(tree);
  const columnX = columnWidths.reduce(function (positions, width, index) {
    if (index === 0) {
      positions.push(DEFAULT_MARGIN);
    } else {
      positions.push(positions[index - 1] + columnWidths[index - 1] + DEFAULT_X_GAP);
    }
    return positions;
  }, []);

  const nodes = [];
  flattenNodes(tree, 0);
  const nodeById = new Map(nodes.map(function (node) {
    return [node.id, node];
  }));
  const links = [];
  visitTree(tree, function (node) {
    for (const child of node.children || []) {
      const source = nodeById.get(node.id);
      const target = nodeById.get(child.id);
      links.push({
        source: source.id,
        target: target.id,
        color: target.color,
        path: curvedPath(source.x + source.width - 4, source.y + source.height / 2, target.x + 4, target.y + target.height / 2)
      });
    }
  });

  const width = Math.ceil(Math.max.apply(null, nodes.map(function (node) {
    return node.x + node.width;
  }).concat(DEFAULT_MARGIN + DEFAULT_NODE_WIDTH)) + DEFAULT_MARGIN);
  const height = Math.ceil(Math.max.apply(null, nodes.map(function (node) {
    return node.y + node.height;
  }).concat(DEFAULT_MARGIN + DEFAULT_NODE_HEIGHT)) + DEFAULT_MARGIN);

  return { nodes: nodes, links: links, width: width, height: height };

  function assignCenters(node) {
    const dimensions = dimensionsById.get(node.id);
    if (!node.children || node.children.length === 0) {
      const center = cursorY + dimensions.height / 2;
      centersById.set(node.id, center);
      cursorY += dimensions.height + DEFAULT_Y_GAP;
      return center;
    }
    const childCenters = node.children.map(assignCenters);
    const center = childCenters.reduce(function (sum, value) {
      return sum + value;
    }, 0) / childCenters.length;
    centersById.set(node.id, center);
    return center;
  }

  function flattenNodes(node, branchIndex) {
    const dimensions = dimensionsById.get(node.id);
    const nextBranchIndex = node.depth === 0 ? branchIndex : branchIndex;
    const color = node.depth === 0 ? "#0f172a" : BRANCH_COLORS[nextBranchIndex % BRANCH_COLORS.length];
    const tint = node.depth === 0 ? "#0f172a" : BRANCH_TINTS[nextBranchIndex % BRANCH_TINTS.length];
    nodes.push({
      id: node.id,
      label: node.label,
      labelLines: dimensions.labelLines,
      depth: node.depth,
      branchIndex: nextBranchIndex,
      x: columnX[node.depth] || DEFAULT_MARGIN,
      y: Math.round(centersById.get(node.id) - dimensions.height / 2),
      width: dimensions.width,
      height: dimensions.height,
      color: color,
      tint: tint,
      isCollapsedSummary: Boolean(node.isCollapsedSummary),
      hiddenCount: node.hiddenCount || 0,
      isSearchMatch: Boolean(node.isSearchMatch),
      isSearchAncestor: Boolean(node.isSearchAncestor)
    });

    (node.children || []).forEach(function (child, index) {
      flattenNodes(child, node.depth === 0 ? index : nextBranchIndex);
    });
  }
}

function renderMindMapSvg(tree, options) {
  const layout = layoutMindMap(tree);
  const title = options && options.title ? options.title : tree.label || "Mind map";
  const focusRelatedIds = collectFocusRelatedIds(tree, options && options.focusedNodeId);
  const hasFocus = focusRelatedIds.size > 0;
  const nodeById = new Map(layout.nodes.map(function (node) {
    return [node.id, node];
  }));
  const paths = layout.links.map(function (link) {
    const target = nodeById.get(link.target);
    const isDimmed = hasFocus && !focusRelatedIds.has(link.source) && !focusRelatedIds.has(link.target);
    return '<path class="mind-map-link' + (isDimmed ? " is-dimmed" : "") + '" d="' + escapeXml(link.path) + '" fill="none" stroke="' + escapeXml(link.color) + '" stroke-width="' + (target && target.isCollapsedSummary ? "2" : "3.5") + '" stroke-linecap="round" opacity="' + (isDimmed ? "0.16" : "0.64") + '"/>';
  }).join("");
  const nodeGroups = layout.nodes.map(function (node) {
    return renderNodeGroup(node, { focusRelatedIds: focusRelatedIds, hasFocus: hasFocus });
  }).join("");

  return [
    '<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="' + escapeXml(title) + '" viewBox="0 0 ' + layout.width + " " + layout.height + '" width="' + layout.width + '" height="' + layout.height + '">',
    "<defs>",
    '<linearGradient id="mind-map-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#fbfdff"/><stop offset="55%" stop-color="#f2f7f8"/><stop offset="100%" stop-color="#eef6f3"/></linearGradient>',
    '<pattern id="mind-map-grid" width="34" height="34" patternUnits="userSpaceOnUse"><path d="M 34 0 L 0 0 0 34" fill="none" stroke="#d7e2e5" stroke-width="1" opacity="0.46"/></pattern>',
    '<filter id="mind-map-shadow" x="-20%" y="-30%" width="140%" height="170%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.10"/></filter>',
    "</defs>",
    '<rect width="100%" height="100%" fill="#f6f8fb"/>',
    '<rect width="100%" height="100%" fill="url(#mind-map-bg)"/>',
    '<rect width="100%" height="100%" fill="url(#mind-map-grid)"/>',
    '<g class="mind-map-links">' + paths + "</g>",
    '<g class="mind-map-nodes" role="list">' + nodeGroups + "</g>",
    "</svg>"
  ].join("");
}

function renderNodeGroup(node, options) {
  const classes = ["mind-map-node"];
  if (node.isCollapsedSummary) classes.push("is-collapsed-summary");
  if (node.isSearchMatch) classes.push("is-search-match");
  if (node.isSearchAncestor) classes.push("is-search-ancestor");
  if (options.hasFocus && options.focusRelatedIds.has(node.id)) classes.push("is-focus-related");
  if (options.hasFocus && !options.focusRelatedIds.has(node.id)) classes.push("is-dimmed");

  const lineHeight = DEFAULT_LABEL_LINE_HEIGHT;
  const firstY = node.y + node.height / 2 - ((node.labelLines.length - 1) * lineHeight) / 2 + 5;
  const textColor = node.depth === 0 ? "#f8fafc" : node.isCollapsedSummary ? "#526172" : "#0f172a";
  const fontWeight = node.depth === 0 ? "800" : node.isCollapsedSummary ? "700" : node.depth === 1 ? "780" : "650";
  const fill = node.depth === 0 ? "#0f172a" : node.isCollapsedSummary ? "#f1f5f9" : node.depth === 1 ? node.tint : "#ffffff";
  const stroke = node.isSearchMatch ? "#14b8a6" : node.color;
  const strokeWidth = node.isSearchMatch ? 3 : node.isCollapsedSummary ? 1.5 : 2;
  const opacity = classes.indexOf("is-dimmed") !== -1 ? "0.34" : "1";
  const fontSize = node.isCollapsedSummary ? "13" : node.depth <= 1 ? "15" : "14";
  const textX = node.x + node.width / 2 + (node.depth > 0 && !node.isCollapsedSummary ? 4 : 0);
  const text = node.labelLines.map(function (line, index) {
    return '<tspan x="' + textX + '" y="' + (firstY + index * lineHeight) + '">' + escapeXml(line) + "</tspan>";
  }).join("");
  const accent = node.depth > 0 && !node.isCollapsedSummary ? '<rect x="' + (node.x + 8) + '" y="' + (node.y + 9) + '" width="4" height="' + Math.max(24, node.height - 18) + '" rx="2" fill="' + escapeXml(node.color) + '" opacity="' + (node.isSearchAncestor ? "0.9" : "0.72") + '"/>' : "";
  const searchRing = node.isSearchMatch ? '<rect x="' + (node.x - 4) + '" y="' + (node.y - 4) + '" width="' + (node.width + 8) + '" height="' + (node.height + 8) + '" rx="12" fill="none" stroke="#14b8a6" stroke-width="2" stroke-dasharray="5 5" opacity="0.9"/>' : "";

  return [
    '<g class="' + classes.join(" ") + '" role="listitem" tabindex="0" aria-label="' + escapeXml(node.label) + '" data-node-id="' + escapeXml(node.id) + '" data-depth="' + node.depth + '" opacity="' + opacity + '">',
    searchRing,
    '<rect x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8" fill="' + escapeXml(fill) + '" stroke="' + escapeXml(stroke) + '" stroke-width="' + strokeWidth + '"' + (node.isCollapsedSummary ? ' stroke-dasharray="4 5"' : "") + ' filter="url(#mind-map-shadow)"/>',
    accent,
    '<text fill="' + escapeXml(textColor) + '" font-family="Fira Sans, PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif" font-size="' + fontSize + '" font-weight="' + fontWeight + '" text-anchor="middle">' + text + "</text>",
    "</g>"
  ].join("");
}

function measureNode(node) {
  const labelLines = wrapLabel(node.label, DEFAULT_LABEL_LINE_LENGTH);
  const longestLine = Math.max.apply(null, labelLines.map(function (line) {
    return Array.from(line).length;
  }).concat(1));
  const depth = node.depth || 0;
  const minWidth = depth === 0 ? 224 : depth === 1 ? 214 : 178;
  const maxWidth = depth === 0 ? 292 : depth === 1 ? 260 : 232;
  const measuredWidth = Math.round(34 + longestLine * 9.2);
  const width = node.isCollapsedSummary ? 150 : clampNumber(measuredWidth, minWidth, maxWidth);
  const baseHeight = node.isCollapsedSummary ? 42 : DEFAULT_NODE_HEIGHT;
  const height = Math.max(baseHeight, NODE_VERTICAL_PADDING + labelLines.length * DEFAULT_LABEL_LINE_HEIGHT);
  return { width: width, height: height, labelLines: labelLines };
}

function normalizeVisibleDepth(value) {
  if (value === "all" || value === Infinity) return Infinity;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 3;
  return Math.max(0, Math.min(DEFAULT_MAX_DEPTH, Math.round(numeric)));
}

function normalizeSearchText(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

function subtreeIncludesQuery(node, query) {
  if (!query) return false;
  if (normalizeSearchText(node.label).indexOf(query) !== -1) return true;
  return (node.children || []).some(function (child) {
    return subtreeIncludesQuery(child, query);
  });
}

function countDescendants(node) {
  return 1 + (node.children || []).reduce(function (sum, child) {
    return sum + countDescendants(child);
  }, 0);
}

function countNodes(node) {
  if (!node) return 0;
  return 1 + (node.children || []).reduce(function (sum, child) {
    return sum + countNodes(child);
  }, 0);
}

function countMatches(node, query) {
  if (!node) return 0;
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return 0;
  const ownMatch = normalizeSearchText(node.label).indexOf(normalizedQuery) !== -1 ? 1 : 0;
  return ownMatch + (node.children || []).reduce(function (sum, child) {
    return sum + countMatches(child, normalizedQuery);
  }, 0);
}

function findNodeLabel(node, nodeId) {
  if (!node || !nodeId) return "";
  if (node.id === nodeId) return node.label;
  for (const child of node.children || []) {
    const label = findNodeLabel(child, nodeId);
    if (label) return label;
  }
  return "";
}

function collectFocusRelatedIds(tree, focusedNodeId) {
  const related = new Set();
  if (!tree || !focusedNodeId) return related;
  const path = findPathToNode(tree, focusedNodeId);
  if (path.length === 0) return related;
  path.forEach(function (node) {
    related.add(node.id);
  });
  addDescendantIds(path[path.length - 1], related);
  return related;
}

function findPathToNode(node, targetId, path) {
  const nextPath = (path || []).concat(node);
  if (node.id === targetId) return nextPath;
  for (const child of node.children || []) {
    const result = findPathToNode(child, targetId, nextPath);
    if (result.length) return result;
  }
  return [];
}

function addDescendantIds(node, target) {
  target.add(node.id);
  for (const child of node.children || []) {
    addDescendantIds(child, target);
  }
}

function wrapLabel(label, maxLineLength) {
  const text = String(label).replace(/\\s+/g, " ").trim();
  if (text.length <= maxLineLength) return [text];
  const lines = [];
  let current = "";
  for (const part of text.split(" ")) {
    const chunks = chunkText(part, maxLineLength);
    for (const chunk of chunks) {
      if (!chunk) continue;
      if ((current + " " + chunk).trim().length <= maxLineLength) {
        current = (current + " " + chunk).trim();
      } else {
        if (current) lines.push(current);
        current = chunk;
      }
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [text];
}

function chunkText(text, maxLineLength) {
  const chars = Array.from(text);
  if (chars.length <= maxLineLength) return [text];
  const chunks = [];
  for (let index = 0; index < chars.length; index += maxLineLength) {
    chunks.push(chars.slice(index, index + maxLineLength).join(""));
  }
  return chunks;
}

function getMindMapSvgSize(svg) {
  const text = String(svg || "");
  const viewBox = text.match(/\\bviewBox=(["'])([^"']+)\\1/i);
  if (viewBox) {
    const parts = viewBox[2].trim().split(/[\\s,]+/).map(Number);
    if (parts.length >= 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3]) && parts[2] > 0 && parts[3] > 0) {
      return { width: parts[2], height: parts[3] };
    }
  }
  return { width: 0, height: 0 };
}

function visitTree(node, visitor) {
  visitor(node);
  for (const child of node.children || []) {
    visitTree(child, visitor);
  }
}

function curvedPath(sourceX, sourceY, targetX, targetY) {
  const middleX = (sourceX + targetX) / 2;
  return "M" + sourceX + "," + sourceY + "C" + middleX + "," + sourceY + " " + middleX + "," + targetY + " " + targetX + "," + targetY;
}

function clampZoom(value) {
  const numeric = Number.isFinite(value) ? value : 1;
  return Math.round(Math.min(2.5, Math.max(0.12, numeric)) * 100) / 100;
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function safeFilename(value) {
  return String(value || "mind-map").trim().replace(/[^\\p{L}\\p{N}_-]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "mind-map";
}
`.trim();
}

export function downloadHtml(html, filename = "mind-map.html") {
  if (typeof document === "undefined" || typeof URL === "undefined") {
    return;
  }
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, filename);
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
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
