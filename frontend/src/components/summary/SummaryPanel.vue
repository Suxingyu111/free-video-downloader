<script setup>
import { Brain, FileText, MessageCircle, NotebookText } from "lucide-vue-next";
import { computed } from "vue";
import SummaryMindMap from "./SummaryMindMap.vue";
import SummaryOverview from "./SummaryOverview.vue";
import SummaryQa from "./SummaryQa.vue";
import SummaryTranscript from "./SummaryTranscript.vue";

const props = defineProps({
  summaryTask: {
    type: Object,
    default: null
  },
  summaryResult: {
    type: Object,
    default: null
  },
  summaryStatusText: {
    type: String,
    default: ""
  },
  isSummaryRunning: {
    type: Boolean,
    default: false
  },
  summaryProgressValue: {
    type: Number,
    default: 0
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

const tabs = [
  { id: "summary", label: "总结内容", icon: NotebookText },
  { id: "transcript", label: "字幕文本", icon: FileText },
  { id: "mindmap", label: "思维导图", icon: Brain },
  { id: "qa", label: "AI 问答", icon: MessageCircle }
];

const sourceText = computed(() => {
  const source = props.summaryResult?.transcript_source;
  return {
    subtitle: "字幕",
    auto_subtitle: "自动字幕"
  }[source] || (props.summaryResult ? "未知来源" : "准备中");
});

const progressWidth = computed(() => `${Math.min(Math.max(props.summaryProgressValue || 0, 0), 100)}%`);
const resultWithTitle = computed(() => {
  if (!props.summaryResult) return null;
  return {
    ...props.summaryResult,
    title: props.summaryResult.title || props.summaryTask?.title || "视频学习笔记"
  };
});

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

    <div v-if="summaryStatusText" class="message" aria-live="polite">
      <span>{{ summaryStatusText }}</span>
      <span v-if="isSummaryRunning">{{ Math.round(summaryProgressValue) }}%</span>
    </div>
    <div class="progress-track summary-progress" aria-hidden="true">
      <div class="progress-fill" :style="{ width: progressWidth }"></div>
    </div>

    <nav v-if="summaryResult" class="summary-tabs" aria-label="AI 视频学习功能">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: summaryView === tab.id }"
        :aria-current="summaryView === tab.id ? 'page' : undefined"
        @click="selectView(tab.id)"
      >
        <component :is="tab.icon" :size="18" aria-hidden="true" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <div v-if="summaryResult" class="summary-content">
      <SummaryOverview v-if="summaryView === 'summary'" :summary-result="resultWithTitle" @use-question="useQuestion" />
      <SummaryTranscript v-else-if="summaryView === 'transcript'" :summary-result="resultWithTitle" />
      <SummaryMindMap v-else-if="summaryView === 'mindmap'" :summary-result="resultWithTitle" />
      <SummaryQa
        v-else
        :summary-result="resultWithTitle"
        :summary-qa-history="summaryQaHistory"
        :summary-question="summaryQuestion"
        :summary-question-error="summaryQuestionError"
        :asking-summary-question="askingSummaryQuestion"
        @update:question="emit('update:question', $event)"
        @submit-question="emit('submit-question')"
      />
    </div>
  </section>
</template>
