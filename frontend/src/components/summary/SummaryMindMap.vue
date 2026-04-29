<script setup>
import { Download, Expand, FileImage, X } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { downloadPngFromSvg, downloadSvg, normalizeMindMap, renderMindMapSvg } from "../../utils/mindMap";
import { buildSafeSummaryFilename } from "../../services/summaryExports";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
  }
});

const isFullscreen = ref(false);
const exportError = ref("");
const closeButton = ref(null);
let previousBodyOverflow = "";

const mindMapTree = computed(() => {
  if (!props.summaryResult?.mind_map) return null;
  return normalizeMindMap(props.summaryResult.mind_map);
});

const svgMarkup = computed(() => {
  if (!mindMapTree.value) return "";
  return renderMindMapSvg(mindMapTree.value);
});

const baseFilename = computed(() => buildSafeSummaryFilename(props.summaryResult?.title || "video-summary", "mind-map", "svg").replace(/\.svg$/i, ""));

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
  closeButton.value?.focus();
}

function closeFullscreen() {
  isFullscreen.value = false;
  if (typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
  }
}

onBeforeUnmount(() => {
  if (isFullscreen.value && typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
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
      <div class="summary-action-group">
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
    <div v-if="svgMarkup" class="mind-map-viewport" v-html="svgMarkup"></div>
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
        <button ref="closeButton" class="summary-icon-button" type="button" aria-label="关闭全屏思维导图" @click="closeFullscreen">
          <X :size="20" aria-hidden="true" />
          <span>关闭</span>
        </button>
      </div>
      <div class="mind-map-overlay-body" v-html="svgMarkup"></div>
    </div>
  </section>
</template>
