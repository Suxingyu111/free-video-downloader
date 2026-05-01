<script setup>
import { Brain, FileText, Loader2, MessageCircle, NotebookText } from "lucide-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import SummaryMindMap from "./SummaryMindMap.vue";
import SummaryOverview from "./SummaryOverview.vue";
import SummaryQa from "./SummaryQa.vue";
import SummaryTranscript from "./SummaryTranscript.vue";
import { diffSummaryStreamLines, normalizeSummaryStreamLines } from "../../utils/summaryStream";

const props = defineProps({
  summaryTask: {
    type: Object,
    default: null
  },
  summaryResult: {
    type: Object,
    default: null
  },
  isDraftResult: {
    type: Boolean,
    default: false
  },
  summaryStatusText: {
    type: String,
    default: ""
  },
  isSummaryRunning: {
    type: Boolean,
    default: false
  },
  canExportMarkdown: {
    type: Boolean,
    default: false
  },
  summaryQaHistory: {
    type: Array,
    default: () => []
  },
  summaryQuestion: {
    type: String,
    default: ""
  },
  summaryQuestionError: {
    type: String,
    default: ""
  },
  askingSummaryQuestion: {
    type: Boolean,
    default: false
  },
  summaryView: {
    type: String,
    default: "summary"
  }
});

const emit = defineEmits(["update:view", "update:question", "submit-question", "use-question"]);

const moduleCards = [
  { id: "summary", label: "总结内容", caption: "摘要与要点", icon: NotebookText, loadingTitle: "正在生成学习摘要", loadingText: "AI 会把视频压缩成一句话概览、章节大纲和核心知识点。" },
  { id: "transcript", label: "字幕文本", caption: "原文轨道", icon: FileText, loadingTitle: "正在提取字幕文本", loadingText: "优先读取公开视频字幕，没有字幕时会等待后续转写结果。" },
  { id: "mindmap", label: "思维导图", caption: "结构视图", icon: Brain, loadingTitle: "等待摘要结构生成", loadingText: "结构化摘要完成后，会自动生成可查看和导出的知识结构图。" },
  { id: "qa", label: "AI 问答", caption: "继续追问", icon: MessageCircle, loadingTitle: "总结完成后可追问", loadingText: "摘要生成后，可以围绕字幕和知识点继续提问。" }
];

const sourceText = computed(() => {
  const source = props.summaryResult?.transcript_source;
  return {
    subtitle: "字幕",
    auto_subtitle: "自动字幕",
    speech_to_text: "语音转写"
  }[source] || (props.summaryResult ? "未知来源" : "准备中");
});

const resultWithTitle = computed(() => {
  if (!props.summaryResult) return null;
  return {
    ...props.summaryResult,
    title: props.summaryResult.title || props.summaryTask?.title || "视频学习笔记"
  };
});
const activeCard = computed(() => moduleCards.find((card) => card.id === props.summaryView) || moduleCards[0]);
const shouldShowLoadingState = computed(() => !props.summaryResult);
const STREAM_LINE_LIMIT = 18;
const STREAM_SOURCE_LIMIT = 36;
const STREAM_LINE_REVEAL_MS = 360;
const streamSourceLines = ref([]);
const revealedStreamLines = ref([]);
const streamRevealQueue = ref([]);
let streamRevealTimer = null;

watch(
  () => props.summaryTask?.id,
  () => {
    resetStreamReveal();
    enqueueStreamLines(props.summaryTask?.streamed_text || "");
  },
  { immediate: true }
);

watch(
  () => props.summaryTask?.streamed_text,
  (text) => {
    enqueueStreamLines(text);
  },
  { immediate: true }
);

function moduleStatus(moduleId) {
  if (props.summaryResult) {
    if (props.isDraftResult) {
      if (moduleId === "summary") return "快速版";
      if (moduleId === "transcript") return "已提取";
      if (moduleId === "mindmap") return "预览中";
      return "完整后可问";
    }
    return moduleId === "qa" ? "可追问" : moduleId === "mindmap" ? "已生成" : "已完成";
  }

  const stage = props.summaryTask?.stage;
  const status = props.summaryTask?.status;

  if (moduleId === "transcript") {
    if (["subtitle", "speech_to_text"].includes(stage) || status === "transcribing") return "提取中";
    if (stage === "summary" || status === "summarizing") return "已提取";
    return "等待中";
  }

  if (moduleId === "summary") {
    if (stage === "summary" || status === "summarizing") return props.summaryTask?.draft_result ? "快速版" : "生成中";
    return "等待摘要";
  }

  if (moduleId === "mindmap") return stage === "summary" || status === "summarizing" ? "构建中" : "等待摘要";
  return "待完成";
}

function moduleTone(moduleId) {
  const status = moduleStatus(moduleId);
  if (["已完成", "已生成", "可追问", "已提取"].includes(status)) return "done";
  if (["生成中", "提取中", "构建中", "快速版", "预览中"].includes(status)) return "active";
  return "waiting";
}

function selectView(view) {
  emit("update:view", view);
}

function useQuestion(question) {
  emit("use-question", question);
}

function enqueueStreamLines(text) {
  const nextLines = normalizeSummaryStreamLines(text || "", { maxLines: STREAM_SOURCE_LIMIT });
  const pendingLines = diffSummaryStreamLines(streamSourceLines.value, nextLines);
  streamSourceLines.value = nextLines;
  if (!nextLines.length) {
    resetStreamReveal();
    return;
  }
  if (!pendingLines.length) return;

  streamRevealQueue.value.push(...pendingLines);
  if (!revealedStreamLines.value.length) {
    revealNextStreamLine();
    return;
  }
  scheduleNextStreamLine();
}

function revealNextStreamLine() {
  if (streamRevealTimer && typeof window !== "undefined") {
    window.clearTimeout(streamRevealTimer);
  }
  streamRevealTimer = null;
  const nextLine = streamRevealQueue.value.shift();
  if (!nextLine) return;
  revealedStreamLines.value = [...revealedStreamLines.value, nextLine].slice(-STREAM_LINE_LIMIT);
  scheduleNextStreamLine();
}

function scheduleNextStreamLine() {
  if (streamRevealTimer || !streamRevealQueue.value.length) return;
  if (typeof window === "undefined") {
    revealNextStreamLine();
    return;
  }
  streamRevealTimer = window.setTimeout(revealNextStreamLine, STREAM_LINE_REVEAL_MS);
}

function resetStreamReveal() {
  if (streamRevealTimer && typeof window !== "undefined") {
    window.clearTimeout(streamRevealTimer);
  }
  streamRevealTimer = null;
  streamSourceLines.value = [];
  revealedStreamLines.value = [];
  streamRevealQueue.value = [];
}

onBeforeUnmount(() => {
  resetStreamReveal();
});
</script>

<template>
  <section v-if="summaryTask" class="summary-card" aria-label="视频学习笔记">
    <div class="summary-header">
      <div>
        <p class="summary-eyebrow">视频学习笔记</p>
        <h3>AI 总结</h3>
      </div>
      <div class="summary-actions">
        <span class="summary-source">{{ sourceText }}</span>
        <a v-if="canExportMarkdown && summaryTask.markdown_url" class="summary-export" :href="summaryTask.markdown_url" download>导出 Markdown</a>
      </div>
    </div>

    <div v-if="summaryStatusText" class="summary-status-message" :data-running="isSummaryRunning ? 'true' : 'false'" aria-live="polite">
      <span class="summary-status-dot" aria-hidden="true"></span>
      <span>{{ summaryStatusText }}</span>
    </div>

    <div v-if="isDraftResult" class="summary-draft-note" aria-live="polite">
      <strong>快速版</strong>
      <span>已可先阅读，完整总结正在完善中。</span>
    </div>

    <nav class="summary-module-grid" aria-label="AI 视频学习功能">
      <button
        v-for="card in moduleCards"
        :key="card.id"
        type="button"
        class="summary-module-card"
        :class="{ active: summaryView === card.id }"
        :data-tone="moduleTone(card.id)"
        :aria-current="summaryView === card.id ? 'page' : undefined"
        @click="selectView(card.id)"
      >
        <span class="summary-module-icon">
          <component :is="card.icon" :size="18" aria-hidden="true" />
        </span>
        <span class="summary-module-copy">
          <span class="summary-module-title">{{ card.label }}</span>
          <span class="summary-module-description">{{ card.caption }}</span>
        </span>
        <span class="summary-status-pill">{{ moduleStatus(card.id) }}</span>
      </button>
    </nav>

    <div class="summary-content">
      <SummaryOverview v-if="summaryView === 'summary' && summaryResult" :summary-result="resultWithTitle" @use-question="useQuestion" />
      <SummaryTranscript v-else-if="summaryView === 'transcript' && summaryResult" :summary-result="resultWithTitle" />
      <SummaryMindMap v-else-if="summaryView === 'mindmap' && summaryResult" :summary-result="resultWithTitle" />
      <section v-else-if="summaryView === 'qa' && isDraftResult" class="summary-loading-state" aria-live="polite">
        <div class="summary-loading-shell" data-tone="waiting">
          <span class="summary-loading-icon">
            <MessageCircle :size="20" aria-hidden="true" />
          </span>
          <div class="summary-loading-copy">
            <p class="summary-module-eyebrow">AI 问答</p>
            <h4>完整总结完成后可追问</h4>
            <p>现在可以先阅读快速版摘要和字幕文本，后台会继续生成可追问的完整结构。</p>
          </div>
        </div>
      </section>
      <SummaryQa
        v-else-if="summaryView === 'qa' && summaryResult"
        :summary-result="resultWithTitle"
        :summary-qa-history="summaryQaHistory"
        :summary-question="summaryQuestion"
        :summary-question-error="summaryQuestionError"
        :asking-summary-question="askingSummaryQuestion"
        @update:question="emit('update:question', $event)"
        @submit-question="emit('submit-question')"
      />
      <section v-else-if="shouldShowLoadingState" class="summary-loading-state" aria-live="polite">
        <div class="summary-loading-shell" :data-tone="moduleTone(activeCard.id)">
          <span class="summary-loading-icon">
            <Loader2 v-if="moduleTone(activeCard.id) === 'active'" :size="20" class="animate-spin" aria-hidden="true" />
            <component v-else :is="activeCard.icon" :size="20" aria-hidden="true" />
          </span>
          <div class="summary-loading-copy">
            <p class="summary-module-eyebrow">{{ activeCard.label }}</p>
            <h4>{{ activeCard.loadingTitle }}</h4>
            <p>{{ activeCard.loadingText }}</p>
            <div v-if="revealedStreamLines.length || streamRevealQueue.length" class="summary-stream-preview" aria-label="AI 实时总结内容">
              <ol>
                <li v-for="(line, index) in revealedStreamLines" :key="`${line}-${index}`">
                  <span>{{ line }}</span>
                </li>
              </ol>
              <span v-if="isSummaryRunning" class="summary-stream-cursor" aria-hidden="true"></span>
            </div>
            <div v-else class="summary-loading-bars" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
