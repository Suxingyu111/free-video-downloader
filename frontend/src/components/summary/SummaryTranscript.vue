<script setup>
import { Download } from "lucide-vue-next";
import { computed } from "vue";
import { buildSafeSummaryFilename, buildTranscriptText, downloadTextFile } from "../../services/summaryExports";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
  }
});

const transcriptLines = computed(() => {
  const segments = props.summaryResult?.transcript_segments;
  if (Array.isArray(segments) && segments.length) return segments;

  return (props.summaryResult?.transcript_text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text, index) => ({ text, start: index }));
});

function segmentTime(segment) {
  return segment?.time || segment?.timestamp || segment?.start || "";
}

function handleDownloadTranscript() {
  const text = buildTranscriptText(props.summaryResult || {});
  const filename = buildSafeSummaryFilename(props.summaryResult?.title || "video-summary", "transcript", "txt");
  downloadTextFile(filename, text, "text/plain;charset=utf-8");
}
</script>

<template>
  <section class="summary-module summary-transcript" aria-labelledby="summary-transcript-title">
    <div class="summary-module-header">
      <div>
        <p class="summary-module-eyebrow">字幕文本</p>
        <h4 id="summary-transcript-title">字幕记录</h4>
      </div>
      <button class="summary-action-button" type="button" :disabled="!summaryResult" @click="handleDownloadTranscript">
        <Download :size="18" aria-hidden="true" />
        <span>下载字幕</span>
      </button>
    </div>

    <div v-if="transcriptLines.length" class="transcript-list">
      <article v-for="(segment, index) in transcriptLines" :key="`${segmentTime(segment)}-${segment.text}-${index}`" class="transcript-item">
        <span class="transcript-time">{{ segmentTime(segment) || "字幕" }}</span>
        <p>{{ segment.text }}</p>
      </article>
    </div>
    <p v-else class="summary-empty">当前总结结果没有返回字幕文本。</p>
  </section>
</template>
