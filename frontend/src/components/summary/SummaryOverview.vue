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
const readableSummaryLines = computed(() =>
  String(props.summaryResult?.readable_summary || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
);
const understandingFacts = computed(() =>
  [
    { label: "主题", value: props.summaryResult?.topic },
    { label: "适合人群", value: props.summaryResult?.audience }
  ].filter((item) => String(item.value || "").trim())
);
const mainThreadItems = computed(() => normalizeList(props.summaryResult?.main_thread));
const exampleItems = computed(() => normalizeList(props.summaryResult?.examples));
const actionItems = computed(() => normalizeList(props.summaryResult?.action_items));
const limitationItems = computed(() => normalizeList(props.summaryResult?.limitations));

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

function formatExample(item) {
  if (typeof item === "string") return item;
  const time = item?.time || item?.timestamp || item?.start || "时间未知";
  return `[${time}] ${item?.text || item?.summary || item?.title || "未命名例子"}`;
}

function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => normalizeListItemText(item));
}

function normalizeListItemText(item) {
  if (!item || typeof item !== "object") return String(item || "").trim();
  return String(item.text || item.title || item.summary || item.term || item.question || "").trim();
}

function lineRevealStyle(sectionIndex, itemIndex = 0) {
  return { "--line-delay": `${sectionIndex * 150 + itemIndex * 80}ms` };
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
      <section v-if="readableSummaryLines.length" class="summary-section">
        <h5>快速导读</h5>
        <ul class="summary-list">
          <li v-for="(line, index) in readableSummaryLines" :key="`${line}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(0, index)">
            {{ line }}
          </li>
        </ul>
      </section>

      <section class="summary-section">
        <h5>结构化增强</h5>
        <p class="summary-line-reveal" :style="lineRevealStyle(1)">以下内容基于同一份字幕继续整理，用于章节回看、导图和追问。</p>
      </section>

      <section class="summary-section">
        <h5>一句话结论</h5>
        <p class="summary-line-reveal" :style="lineRevealStyle(2)">{{ summaryResult.overview || "当前总结结果没有返回概览。" }}</p>
      </section>

      <section v-if="understandingFacts.length" class="summary-section">
        <h5>完整理解</h5>
        <dl class="summary-fact-grid">
          <div v-for="(item, index) in understandingFacts" :key="item.label" class="summary-line-reveal" :style="lineRevealStyle(3, index)">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="mainThreadItems.length" class="summary-section">
        <h5>主线脉络</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in mainThreadItems" :key="`${item}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(4, index)">
            {{ item }}
          </li>
        </ul>
      </section>

      <section v-if="exampleItems.length" class="summary-section">
        <h5>例子和证据</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in exampleItems" :key="`${formatExample(item)}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(5, index)">
            {{ formatExample(item) }}
          </li>
        </ul>
      </section>

      <section v-if="actionItems.length" class="summary-section">
        <h5>行动清单</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in actionItems" :key="`${item}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(6, index)">
            {{ item }}
          </li>
        </ul>
      </section>

      <section v-if="limitationItems.length" class="summary-section">
        <h5>边界和限制</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in limitationItems" :key="`${item}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(7, index)">
            {{ item }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.outline?.length" class="summary-section">
        <h5>章节时间轴</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.outline" :key="`${formatOutlineItem(item)}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(8, index)">
            {{ formatOutlineItem(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.key_points?.length" class="summary-section">
        <h5>核心知识点</h5>
        <ul class="summary-list">
          <li v-for="(point, index) in summaryResult.key_points" :key="`${point}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(9, index)">{{ point }}</li>
        </ul>
      </section>

      <section v-if="summaryResult.highlights?.length" class="summary-section">
        <h5>关键片段</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.highlights" :key="`${formatHighlight(item)}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(10, index)">
            {{ formatHighlight(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.terms?.length" class="summary-section">
        <h5>术语解释</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.terms" :key="`${formatTerm(item)}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(11, index)">
            {{ formatTerm(item) }}
          </li>
        </ul>
      </section>

      <section v-if="summaryResult.questions?.length" class="summary-section">
        <h5>可以继续追问</h5>
        <div class="question-chips">
          <button
            v-for="(question, index) in summaryResult.questions"
            :key="typeof question === 'string' ? question : question.question"
            class="question-chip summary-line-reveal"
            :style="lineRevealStyle(12, index)"
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
