<script setup>
import { Download, Expand, FileImage, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  calculateMindMapFitZoom,
  clampMindMapZoom,
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
let previousBodyOverflow = "";

const ZOOM_STEP = 0.16;

const mindMapTree = computed(() => {
  if (!props.summaryResult?.mind_map) return null;
  return normalizeMindMap(props.summaryResult.mind_map);
});

const svgMarkup = computed(() => {
  if (!mindMapTree.value) return "";
  return renderMindMapSvg(mindMapTree.value);
});

const baseFilename = computed(() => buildSafeSummaryFilename(props.summaryResult?.title || "video-summary", "mind-map", "svg").replace(/\.svg$/i, ""));
const svgSize = computed(() => getMindMapSvgSize(svgMarkup.value));
const activeZoom = computed(() => (isFullscreen.value ? fullscreenZoom.value : inlineZoom.value));
const zoomPercent = computed(() => `${Math.round(activeZoom.value * 100)}%`);

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
  if (isFullscreen.value) {
    fullscreenZoom.value = clampMindMapZoom(value, options);
    return;
  }
  inlineZoom.value = clampMindMapZoom(value, options);
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

function viewportBox(element) {
  if (!element) return { width: 0, height: 0 };
  const rect = element.getBoundingClientRect?.();
  return {
    width: rect?.width || element.clientWidth || 0,
    height: rect?.height || element.clientHeight || 0
  };
}

function handleResize() {
  fitInlineMap();
  if (isFullscreen.value) {
    fitFullscreenMap();
  }
}

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
        <button class="summary-icon-button" type="button" :disabled="!svgMarkup" aria-label="全屏查看思维导图" @click="openFullscreen">
          <Expand :size="18" aria-hidden="true" />
          <span>全屏</span>
        </button>
      </div>
    </div>

    <p v-if="exportError" class="summary-export-error" role="alert">{{ exportError }}</p>
    <div v-if="svgMarkup" ref="inlineViewport" class="mind-map-viewport">
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
      <div ref="fullscreenViewport" class="mind-map-overlay-body">
        <div class="mind-map-canvas" :style="canvasStyle(fullscreenZoom)">
          <div class="mind-map-surface" v-html="svgMarkup"></div>
        </div>
      </div>
    </div>
  </section>
</template>
