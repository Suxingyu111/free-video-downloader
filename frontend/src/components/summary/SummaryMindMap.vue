<script setup>
import { Crosshair, Download, Expand, FileCode, FileImage, Layers, RotateCcw, Search, X, ZoomIn, ZoomOut } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  buildInteractiveMindMapHtml,
  calculateMindMapFitZoom,
  clampMindMapZoom,
  createVisibleMindMap,
  downloadHtml,
  downloadPngFromSvg,
  downloadSvg,
  getMindMapSvgSize,
  normalizeMindMap,
  renderMindMapSvg
} from "../../utils/mindMap";
import { buildSafeSummaryFilename } from "../../services/summaryExports";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
  }
});

const isFullscreen = ref(false);
const exportError = ref("");
const inlineViewport = ref(null);
const fullscreenViewport = ref(null);
const closeButton = ref(null);
const inlineZoom = ref(1);
const fullscreenZoom = ref(1);
const searchQuery = ref("");
const visibleDepth = ref("1");
const focusedNodeId = ref("");
const isDragging = ref(false);
let previousBodyOverflow = "";
let dragState = null;
let ignoreNextNodeClick = false;

const ZOOM_STEP = 0.16;
const WHEEL_ZOOM_STEP = 0.12;
const LEVEL_OPTIONS = [
  { value: "1", label: "1 层" },
  { value: "2", label: "2 层" },
  { value: "3", label: "3 层" },
  { value: "all", label: "全部" }
];

const mindMapTree = computed(() => {
  if (!props.summaryResult?.mind_map) return null;
  return normalizeMindMap(props.summaryResult.mind_map);
});

const visibleMindMapTree = computed(() => {
  if (!mindMapTree.value) return null;
  return createVisibleMindMap(mindMapTree.value, {
    visibleDepth: visibleDepth.value,
    query: searchQuery.value
  });
});

const svgMarkup = computed(() => {
  if (!visibleMindMapTree.value) return "";
  return renderMindMapSvg(visibleMindMapTree.value, {
    focusedNodeId: focusedNodeId.value
  });
});

const baseFilename = computed(() => buildSafeSummaryFilename(props.summaryResult?.title || "video-summary", "mind-map", "svg").replace(/\.svg$/i, ""));
const svgSize = computed(() => getMindMapSvgSize(svgMarkup.value));
const activeZoom = computed(() => (isFullscreen.value ? fullscreenZoom.value : inlineZoom.value));
const zoomPercent = computed(() => `${Math.round(activeZoom.value * 100)}%`);
const matchCount = computed(() => countMatches(mindMapTree.value, searchQuery.value));
const visibleNodeCount = computed(() => countNodes(visibleMindMapTree.value));
const focusedNodeLabel = computed(() => findNodeLabel(visibleMindMapTree.value, focusedNodeId.value) || findNodeLabel(mindMapTree.value, focusedNodeId.value));

function handleDownloadSvg() {
  if (!svgMarkup.value) return;
  exportError.value = "";
  downloadSvg(svgMarkup.value, `${baseFilename.value}.svg`);
}

async function handleDownloadPng() {
  if (!svgMarkup.value) return;
  exportError.value = "";
  try {
    await downloadPngFromSvg(svgMarkup.value, `${baseFilename.value}.png`);
  } catch {
    exportError.value = "PNG 导出失败，请先下载 SVG 或稍后重试。";
  }
}

function handleDownloadInteractiveHtml() {
  if (!mindMapTree.value) return;
  exportError.value = "";
  const html = buildInteractiveMindMapHtml(mindMapTree.value, {
    title: props.summaryResult?.title || mindMapTree.value.label,
    visibleDepth: visibleDepth.value,
    searchQuery: searchQuery.value,
    focusedNodeId: focusedNodeId.value
  });
  downloadHtml(html, `${baseFilename.value}.html`);
}

async function openFullscreen() {
  isFullscreen.value = true;
  if (typeof document !== "undefined") {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  await nextTick();
  fitFullscreenMap();
  closeButton.value?.focus();
}

function closeFullscreen() {
  isFullscreen.value = false;
  if (typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
  }
}

function zoomIn() {
  setActiveZoom(activeZoom.value + ZOOM_STEP);
}

function zoomOut() {
  setActiveZoom(activeZoom.value - ZOOM_STEP);
}

function resetZoom() {
  setActiveZoom(1);
}

function setActiveZoom(value) {
  const options = isFullscreen.value ? { minZoom: 0.12, maxZoom: 2.5 } : { minZoom: 0.35, maxZoom: 2.2 };
  const nextZoom = clampMindMapZoom(value, options);
  if (isFullscreen.value) {
    fullscreenZoom.value = nextZoom;
    return nextZoom;
  }
  inlineZoom.value = nextZoom;
  return nextZoom;
}

function fitInlineMap() {
  const box = viewportBox(inlineViewport.value);
  const size = svgSize.value;
  if (!box.width || !size.width || !size.height) return;
  inlineZoom.value = calculateMindMapFitZoom({
    viewportWidth: box.width,
    viewportHeight: Math.max(box.height, size.height + 56),
    contentWidth: size.width,
    contentHeight: size.height,
    padding: 28,
    maxZoom: 1,
    minZoom: 0.35
  });
}

function fitFullscreenMap() {
  const box = viewportBox(fullscreenViewport.value);
  const size = svgSize.value;
  if (!box.width || !box.height || !size.width || !size.height) return;
  fullscreenZoom.value = calculateMindMapFitZoom({
    viewportWidth: box.width,
    viewportHeight: box.height,
    contentWidth: size.width,
    contentHeight: size.height,
    padding: 36,
    maxZoom: 1.8,
    minZoom: 0.12
  });
}

function fitActiveMap() {
  if (isFullscreen.value) {
    fitFullscreenMap();
    return;
  }
  fitInlineMap();
}

function canvasStyle(zoom) {
  const size = svgSize.value;
  return {
    width: `${Math.max(1, Math.ceil(size.width * zoom))}px`,
    height: `${Math.max(1, Math.ceil(size.height * zoom))}px`,
    "--mind-map-zoom": zoom
  };
}

function clearSearch() {
  searchQuery.value = "";
}

function clearFocus() {
  focusedNodeId.value = "";
}

async function handleMindMapNodeClick(event) {
  if (ignoreNextNodeClick) {
    ignoreNextNodeClick = false;
    return;
  }
  const target = event.target?.closest?.("[data-node-id]");
  const nodeId = target?.getAttribute?.("data-node-id") || "";
  if (!nodeId || nodeId.includes("-collapsed-")) return;

  focusedNodeId.value = focusedNodeId.value === nodeId ? "" : nodeId;
  if (focusedNodeId.value) {
    await nextTick();
    centerNodeInViewport(nodeId, event.currentTarget);
  }
}

function handleViewportPointerDown(event) {
  if (event.button !== 0 || !svgMarkup.value) return;
  if (event.target?.closest?.("button, input, select, textarea, a")) return;

  const viewport = event.currentTarget;
  dragState = {
    viewport,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    scrollLeft: viewport.scrollLeft,
    scrollTop: viewport.scrollTop
  };
  isDragging.value = true;
  viewport.setPointerCapture?.(event.pointerId);
}

function handleViewportPointerMove(event) {
  if (!dragState || dragState.pointerId !== event.pointerId) return;
  const dx = event.clientX - dragState.startX;
  const dy = event.clientY - dragState.startY;
  if (Math.abs(dx) + Math.abs(dy) > 4) {
    ignoreNextNodeClick = true;
  }
  dragState.viewport.scrollLeft = dragState.scrollLeft - dx;
  dragState.viewport.scrollTop = dragState.scrollTop - dy;
}

function handleViewportPointerUp(event) {
  if (!dragState || dragState.pointerId !== event.pointerId) return;
  event.currentTarget.releasePointerCapture?.(event.pointerId);
  isDragging.value = false;
  dragState = null;
  if (ignoreNextNodeClick && typeof window !== "undefined") {
    window.setTimeout(() => {
      ignoreNextNodeClick = false;
    }, 0);
  }
}

function handleViewportWheel(event) {
  if (!svgMarkup.value) return;
  const previousZoom = activeZoom.value;
  const nextZoom = setActiveZoom(previousZoom + (event.deltaY > 0 ? -WHEEL_ZOOM_STEP : WHEEL_ZOOM_STEP));
  if (nextZoom === previousZoom) return;

  const viewport = event.currentTarget;
  const rect = viewport.getBoundingClientRect();
  const offsetX = event.clientX - rect.left;
  const offsetY = event.clientY - rect.top;
  const ratio = nextZoom / previousZoom;

  nextTick(() => {
    viewport.scrollLeft = (viewport.scrollLeft + offsetX) * ratio - offsetX;
    viewport.scrollTop = (viewport.scrollTop + offsetY) * ratio - offsetY;
  });
}

function viewportBox(element) {
  if (!element) return { width: 0, height: 0 };
  const rect = element.getBoundingClientRect?.();
  return {
    width: rect?.width || element.clientWidth || 0,
    height: rect?.height || element.clientHeight || 0
  };
}

function countNodes(node) {
  if (!node) return 0;
  return 1 + (node.children || []).reduce((sum, child) => sum + countNodes(child), 0);
}

function countMatches(node, query) {
  if (!node) return 0;
  const normalizedQuery = String(query || "").trim().toLocaleLowerCase();
  if (!normalizedQuery) return 0;
  const ownMatch = String(node.label || "").toLocaleLowerCase().includes(normalizedQuery) ? 1 : 0;
  return ownMatch + (node.children || []).reduce((sum, child) => sum + countMatches(child, normalizedQuery), 0);
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

function centerNodeInViewport(nodeId, viewport) {
  if (!viewport) return;
  const nodeElement = viewport.querySelector?.(`[data-node-id="${nodeId.replaceAll('"', '\\"')}"]`);
  if (!nodeElement) return;
  const nodeRect = nodeElement.getBoundingClientRect();
  const viewportRect = viewport.getBoundingClientRect();
  viewport.scrollLeft += nodeRect.left - viewportRect.left - viewportRect.width / 2 + nodeRect.width / 2;
  viewport.scrollTop += nodeRect.top - viewportRect.top - viewportRect.height / 2 + nodeRect.height / 2;
}

function handleResize() {
  fitInlineMap();
  if (isFullscreen.value) {
    fitFullscreenMap();
  }
}

watch(
  mindMapTree,
  () => {
    searchQuery.value = "";
    visibleDepth.value = "1";
    focusedNodeId.value = "";
  },
  { flush: "post" }
);

watch(visibleMindMapTree, (tree) => {
  if (focusedNodeId.value && !findNodeLabel(tree, focusedNodeId.value)) {
    focusedNodeId.value = "";
  }
});

watch(
  svgMarkup,
  async () => {
    await nextTick();
    fitInlineMap();
    if (isFullscreen.value) {
      fitFullscreenMap();
    }
  },
  { immediate: true }
);

onMounted(() => {
  fitInlineMap();
  if (typeof window !== "undefined") {
    window.addEventListener("resize", handleResize);
  }
});

onBeforeUnmount(() => {
  if (isFullscreen.value && typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
  }
  dragState = null;
  if (typeof window !== "undefined") {
    window.removeEventListener("resize", handleResize);
  }
});
</script>

<template>
  <section class="summary-module summary-mind-map" aria-labelledby="summary-mind-map-title">
    <div class="summary-module-header">
      <div>
        <p class="summary-module-eyebrow">思维导图</p>
        <h4 id="summary-mind-map-title">知识结构</h4>
      </div>
      <div class="summary-action-group mind-map-toolbar">
        <div class="mind-map-zoom-controls" aria-label="思维导图缩放">
          <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="缩小思维导图" title="缩小" @click="zoomOut">
            <ZoomOut :size="17" aria-hidden="true" />
          </button>
          <span class="mind-map-zoom-value" aria-live="polite">{{ zoomPercent }}</span>
          <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="放大思维导图" title="放大" @click="zoomIn">
            <ZoomIn :size="17" aria-hidden="true" />
          </button>
          <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="适配窗口显示完整思维导图" title="适配窗口" @click="fitActiveMap">
            <Expand :size="17" aria-hidden="true" />
          </button>
          <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="重置思维导图缩放" title="重置缩放" @click="resetZoom">
            <RotateCcw :size="17" aria-hidden="true" />
          </button>
        </div>
        <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="下载思维导图 PNG" @click="handleDownloadPng">
          <FileImage :size="18" aria-hidden="true" />
          <span>PNG</span>
        </button>
        <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="下载思维导图 SVG" @click="handleDownloadSvg">
          <Download :size="18" aria-hidden="true" />
          <span>SVG</span>
        </button>
        <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="下载交互式思维导图 HTML" @click="handleDownloadInteractiveHtml">
          <FileCode :size="18" aria-hidden="true" />
          <span>HTML</span>
        </button>
        <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="全屏查看思维导图" @click="openFullscreen">
          <Expand :size="18" aria-hidden="true" />
          <span>全屏</span>
        </button>
      </div>
    </div>

    <div class="mind-map-filterbar">
      <label class="mind-map-search">
        <Search :size="17" aria-hidden="true" />
        <input v-model="searchQuery" type="search" :disabled="!mindMapTree" aria-label="搜索思维导图节点" placeholder="搜索节点" />
        <button v-if="searchQuery" class="mind-map-input-clear" type="button" aria-label="清空搜索" @click="clearSearch">
          <X :size="15" aria-hidden="true" />
        </button>
      </label>
      <label class="mind-map-level-select">
        <Layers :size="17" aria-hidden="true" />
        <select v-model="visibleDepth" :disabled="!mindMapTree" aria-label="显示思维导图层级">
          <option v-for="option in LEVEL_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <button v-if="focusedNodeId" class="summary-icon-button mind-map-focus-clear" type="button" aria-label="清除思维导图节点聚焦" @click="clearFocus">
        <Crosshair :size="17" aria-hidden="true" />
        <span>清除聚焦</span>
      </button>
    </div>

    <div v-if="svgMarkup" class="mind-map-hintbar" aria-live="polite">
      <span>节点 {{ visibleNodeCount }}</span>
      <span v-if="searchQuery">匹配 {{ matchCount }}</span>
      <span v-if="focusedNodeLabel">聚焦 {{ focusedNodeLabel }}</span>
    </div>

    <p v-if="exportError" class="summary-export-error" role="alert">{{ exportError }}</p>
    <div
      v-if="svgMarkup"
      ref="inlineViewport"
      class="mind-map-viewport"
      :class="{ dragging: isDragging }"
      @click="handleMindMapNodeClick"
      @pointerdown="handleViewportPointerDown"
      @pointermove="handleViewportPointerMove"
      @pointerup="handleViewportPointerUp"
      @pointerleave="handleViewportPointerUp"
      @pointercancel="handleViewportPointerUp"
      @wheel.prevent="handleViewportWheel"
    >
      <div class="mind-map-canvas" :style="canvasStyle(inlineZoom)">
        <div class="mind-map-surface" v-html="svgMarkup"></div>
      </div>
    </div>
    <p v-else class="summary-empty">当前总结结果没有返回思维导图。</p>

    <div
      v-if="isFullscreen"
      class="mind-map-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="summary-mind-map-fullscreen-title"
      tabindex="-1"
      @keydown.esc="closeFullscreen"
    >
      <div class="mind-map-overlay-header">
        <h4 id="summary-mind-map-fullscreen-title">思维导图</h4>
        <div class="summary-action-group mind-map-toolbar">
          <div class="mind-map-zoom-controls" aria-label="全屏思维导图缩放">
            <button class="summary-icon-button" type="button" aria-label="缩小全屏思维导图" title="缩小" @click="zoomOut">
              <ZoomOut :size="17" aria-hidden="true" />
            </button>
            <span class="mind-map-zoom-value" aria-live="polite">{{ zoomPercent }}</span>
            <button class="summary-icon-button" type="button" aria-label="放大全屏思维导图" title="放大" @click="zoomIn">
              <ZoomIn :size="17" aria-hidden="true" />
            </button>
            <button class="summary-icon-button" type="button" aria-label="全屏适配显示完整思维导图" title="适配窗口" @click="fitFullscreenMap">
              <Expand :size="17" aria-hidden="true" />
            </button>
            <button class="summary-icon-button" type="button" aria-label="重置全屏思维导图缩放" title="重置缩放" @click="resetZoom">
              <RotateCcw :size="17" aria-hidden="true" />
            </button>
          </div>
          <button ref="closeButton" class="summary-icon-button" type="button" aria-label="关闭全屏思维导图" @click="closeFullscreen">
            <X :size="20" aria-hidden="true" />
            <span>关闭</span>
          </button>
        </div>
      </div>
      <div class="mind-map-filterbar mind-map-filterbar-compact">
        <label class="mind-map-search">
          <Search :size="17" aria-hidden="true" />
          <input v-model="searchQuery" type="search" aria-label="搜索思维导图节点" placeholder="搜索节点" />
          <button v-if="searchQuery" class="mind-map-input-clear" type="button" aria-label="清空搜索" @click="clearSearch">
            <X :size="15" aria-hidden="true" />
          </button>
        </label>
        <label class="mind-map-level-select">
          <Layers :size="17" aria-hidden="true" />
          <select v-model="visibleDepth" aria-label="显示思维导图层级">
            <option v-for="option in LEVEL_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <button v-if="focusedNodeId" class="summary-icon-button mind-map-focus-clear" type="button" aria-label="清除思维导图节点聚焦" @click="clearFocus">
          <Crosshair :size="17" aria-hidden="true" />
          <span>清除聚焦</span>
        </button>
      </div>
      <div
        ref="fullscreenViewport"
        class="mind-map-overlay-body"
        :class="{ dragging: isDragging }"
        @click="handleMindMapNodeClick"
        @pointerdown="handleViewportPointerDown"
        @pointermove="handleViewportPointerMove"
        @pointerup="handleViewportPointerUp"
        @pointerleave="handleViewportPointerUp"
        @pointercancel="handleViewportPointerUp"
        @wheel.prevent="handleViewportWheel"
      >
        <div class="mind-map-canvas" :style="canvasStyle(fullscreenZoom)">
          <div class="mind-map-surface" v-html="svgMarkup"></div>
        </div>
      </div>
    </div>
  </section>
</template>
