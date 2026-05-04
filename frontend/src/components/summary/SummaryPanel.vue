<script setup>
import { Brain, FileText, Loader2, MessageCircle, NotebookText } from "lucide-vue-next";
import { computed } from "vue";
import SummaryMindMap from "./SummaryMindMap.vue";
import SummaryOverview from "./SummaryOverview.vue";
import SummaryQa from "./SummaryQa.vue";
import SummaryTranscript from "./SummaryTranscript.vue";
import { normalizeSummaryStreamPreview } from "../../utils/summaryStream";

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
  questionQuotaText: {
    type: String,
    default: ""
  },
  questionQuotaExhausted: {
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
const STREAM_STABLE_LINE_LIMIT = 5;
const streamPreview = computed(() =>
  normalizeSummaryStreamPreview(props.summaryTask?.streamed_text || "", {
    maxStableLines: STREAM_STABLE_LINE_LIMIT
  })
);
const streamHeadlineText = computed(() => streamPreview.value.headline || streamPreview.value.headlineDraft);
const hasHeadlineDraft = computed(() => Boolean(streamPreview.value.headlineDraft));
const streamBodyLines = computed(() => streamPreview.value.bodyLines);
const streamDraftLine = computed(() => {
  const draft = streamPreview.value.draftLine || "";
  return hasHeadlineDraft.value ? "" : draft;
});
const hasStreamPreview = computed(() =>
  Boolean(streamHeadlineText.value || streamBodyLines.value.length || streamDraftLine.value)
);
const generationSteps = computed(() => {
  const stage = props.summaryTask?.stage || "queued";
  const status = props.summaryTask?.status || "queued";
  const transcriptActive = ["subtitle", "speech_to_text"].includes(stage) || status === "transcribing";
  const transcriptDone = ["summary", "completed"].includes(stage) || ["summarizing", "completed"].includes(status);
  const summaryActive = stage === "summary" || status === "summarizing";
  const summaryDone = status === "completed";
  return [
    { label: transcriptDone ? "字幕已提取" : "提取字幕", state: transcriptDone ? "done" : transcriptActive ? "active" : "waiting" },
    { label: summaryDone ? "摘要已生成" : "提炼摘要", state: summaryDone ? "done" : summaryActive ? "active" : "waiting" },
    { label: summaryDone ? "结构已完成" : "整理章节结构", state: summaryDone ? "done" : summaryActive && hasStreamPreview.value ? "active" : "waiting" }
  ];
});

function moduleStatus(moduleId) {
  if (props.summaryResult) {
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
    if (stage === "summary" || status === "summarizing") return "生成中";
    return "等待摘要";
  }

  if (moduleId === "mindmap") return stage === "summary" || status === "summarizing" ? "构建中" : "等待摘要";
  return "待完成";
}

function moduleTone(moduleId) {
  const status = moduleStatus(moduleId);
  if (["已完成", "已生成", "可追问", "已提取"].includes(status)) return "done";
  if (["生成中", "提取中", "构建中", "预览中"].includes(status)) return "active";
  return "waiting";
}

function selectView(view) {
  emit("update:view", view);
}

function useQuestion(question) {
  emit("use-question", question);
}
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
      <SummaryQa
        v-else-if="summaryView === 'qa' && summaryResult"
        :summary-result="resultWithTitle"
        :summary-qa-history="summaryQaHistory"
        :summary-question="summaryQuestion"
        :summary-question-error="summaryQuestionError"
        :asking-summary-question="askingSummaryQuestion"
        :question-quota-text="questionQuotaText"
        :question-quota-exhausted="questionQuotaExhausted"
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
            <div class="summary-generation-steps" aria-label="总结生成步骤">
              <span v-for="step in generationSteps" :key="step.label" :data-state="step.state">{{ step.label }}</span>
            </div>
            <div v-if="hasStreamPreview" class="summary-stream-preview" aria-label="AI 实时总结内容">
              <div v-if="streamHeadlineText" class="summary-stream-headline">
                <span>一句话结论</span>
                <p>
                  {{ streamHeadlineText }}
                  <span v-if="isSummaryRunning && hasHeadlineDraft" class="summary-stream-cursor" aria-hidden="true"></span>
                </p>
              </div>
              <div v-if="streamBodyLines.length" class="summary-stream-body">
                <span>已生成内容</span>
                <ul>
                  <li v-for="(line, index) in streamBodyLines" :key="`${line}-${index}`">{{ line }}</li>
                </ul>
              </div>
              <p v-if="streamDraftLine" class="summary-stream-draft">
                <span>{{ streamDraftLine }}</span>
                <span v-if="isSummaryRunning" class="summary-stream-cursor" aria-hidden="true"></span>
              </p>
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
