<script setup>
import { Download, HelpCircle } from "lucide-vue-next";
import { computed } from "vue";
import { buildSafeSummaryFilename, buildSummaryMarkdown, downloadTextFile } from "../../services/summaryExports";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
  }
});

const emit = defineEmits(["use-question"]);

const title = computed(() => props.summaryResult?.title || "AI 总结");
const hasSummary = computed(() => Boolean(props.summaryResult));

function formatOutlineItem(item) {
  if (typeof item === "string") return item;
  const label = item?.title || item?.text || "未命名章节";
  const time = item?.time || item?.timestamp;
  const summary = item?.summary || item?.text || "";
  return `${time ? `[${time}] ` : ""}${label}${summary && summary !== label ? `：${summary}` : ""}`;
}

function formatHighlight(item) {
  if (typeof item === "string") return item;
  const time = item?.time || item?.timestamp || "时间未知";
  return `[${time}] ${item?.text || item?.summary || "未命名要点"}`;
}

function formatTerm(item) {
  if (typeof item === "string") return item;
  return `${item?.term || item?.name || "术语"}：${item?.explanation || item?.definition || item?.summary || ""}`;
}

function handleDownloadSummary() {
  const markdown = buildSummaryMarkdown(props.summaryResult || {});
  const filename = buildSafeSummaryFilename(title.value, "summary", "md");
  downloadTextFile(filename, markdown, "text/markdown;charset=utf-8");
}
</script>

<template>
  <section class="summary-module summary-overview" aria-labelledby="summary-overview-title">
    <div class="summary-module-header">
      <div>
        <p class="summary-module-eyebrow">总结内容</p>
        <h4 id="summary-overview-title">学习摘要</h4>
      </div>
      <button class="summary-action-button" type="button" :disabled="!hasSummary" @click="handleDownloadSummary">
        <Download :size="18" aria-hidden="true" />
        <span>下载总结</span>
      </button>
    </div>

    <div v-if="summaryResult" class="summary-overview-body">
      <section class="summary-section">
        <h5>一句话概览</h5>
        <p>{{ summaryResult.overview || "当前总结结果没有返回概览。" }}</p>
      </section>

      <section v-if="summaryResult.outline?.length" class="summary-section">
        <h5>章节大纲</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.outline" :key="`${formatOutlineItem(item)}-${index}`">
            {{ formatOutlineItem(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.key_points?.length" class="summary-section">
        <h5>核心知识点</h5>
        <ul class="summary-list">
          <li v-for="(point, index) in summaryResult.key_points" :key="`${point}-${index}`">{{ point }}</li>
        </ul>
      </section>

      <section v-if="summaryResult.highlights?.length" class="summary-section">
        <h5>时间轴要点</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.highlights" :key="`${formatHighlight(item)}-${index}`">
            {{ formatHighlight(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.terms?.length" class="summary-section">
        <h5>术语解释</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.terms" :key="`${formatTerm(item)}-${index}`">
            {{ formatTerm(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.questions?.length" class="summary-section">
        <h5>可以继续追问</h5>
        <div class="question-chips">
          <button
            v-for="question in summaryResult.questions"
            :key="typeof question === 'string' ? question : question.question"
            class="question-chip"
            type="button"
            @click="emit('use-question', typeof question === 'string' ? question : question.question)"
          >
            <HelpCircle :size="16" aria-hidden="true" />
            <span>{{ typeof question === "string" ? question : question.question }}</span>
          </button>
        </div>
      </section>
    </div>

    <p v-else class="summary-empty">总结完成后会在这里显示摘要内容。</p>
  </section>
</template>
