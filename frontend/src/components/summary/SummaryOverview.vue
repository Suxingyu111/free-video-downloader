<script setup>
import { Download, HelpCircle } from "lucide-vue-next";
import { computed } from "vue";
import { buildSafeSummaryFilename, buildSummaryMarkdown, downloadTextFile } from "../../services/summaryExports";
import SummaryMarkdownRenderer from "./SummaryMarkdownRenderer.vue";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
  }
});

const emit = defineEmits(["use-question"]);

const title = computed(() => props.summaryResult?.title || "AI 总结");
const hasSummary = computed(() => Boolean(props.summaryResult));
const summaryMarkdown = computed(() => buildOverviewMarkdown(props.summaryResult || {}));

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

function questionText(question) {
  return typeof question === "string" ? question : question?.question || "";
}

function buildOverviewMarkdown(summary) {
  const lines = ["## 快速导读", ""];
  const readableSummary = normalizeText(summary.readable_summary);
  lines.push(readableSummary ? formatReadableSummaryMarkdown(readableSummary) : "暂无快速导读。");

  lines.push("", "## 一句话结论", "", normalizeText(summary.overview) || "当前总结结果没有返回概览。");

  const facts = [
    ["主题", summary.topic],
    ["适合人群", summary.audience]
  ].filter(([, value]) => normalizeText(value));

  if (facts.length) {
    lines.push("", "## 完整理解", "", "| 项目 | 内容 |", "| --- | --- |");
    for (const [label, value] of facts) {
      lines.push(`| ${formatTableCell(label)} | ${formatTableCell(value)} |`);
    }
  }

  appendMarkdownList(lines, "核心知识点", summary.key_points);
  appendMarkdownList(lines, "主线脉络", summary.main_thread);
  appendMarkdownList(lines, "例子和证据", summary.examples, formatExample);
  appendMarkdownList(lines, "行动清单", summary.action_items);
  appendMarkdownList(lines, "边界和限制", summary.limitations);

  return lines.join("\n");
}

function formatReadableSummaryMarkdown(value) {
  const output = [];
  let previousWasList = false;
  const lines = normalizeText(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    const conclusion = line.match(/^一句话结论[:：]\s*(.+)$/);
    if (conclusion) {
      appendMarkdownBlock(output, `> **一句话结论：** ${conclusion[1]}`);
      previousWasList = false;
      continue;
    }

    if (/^[^#*\-\d].{1,28}[:：]$/.test(line)) {
      appendMarkdownBlock(output, `### ${line.replace(/[:：]$/, "")}`);
      previousWasList = false;
      continue;
    }

    if (/^[-*]\s+/.test(line) || /^\d+[.)]\s+/.test(line)) {
      if (!previousWasList && output.length && output.at(-1) !== "") output.push("");
      output.push(line);
      previousWasList = true;
      continue;
    }

    appendMarkdownBlock(output, line);
    previousWasList = false;
  }

  while (output[0] === "") output.shift();
  while (output.at(-1) === "") output.pop();
  return output.join("\n");
}

function appendMarkdownBlock(output, line) {
  if (output.length && output.at(-1) !== "") output.push("");
  output.push(line);
  output.push("");
}

function appendMarkdownList(lines, heading, value, formatter = normalizeListItemText) {
  const items = normalizeList(value)
    .map((item) => normalizeText(formatter(item)))
    .filter(Boolean);
  if (!items.length) return;
  lines.push("", `## ${heading}`, "", ...items.map((item) => `- ${item}`));
}

function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => normalizeListItemText(item));
}

function normalizeListItemText(item) {
  if (!item || typeof item !== "object") return String(item || "").trim();
  return String(item.text || item.title || item.summary || item.term || item.question || "").trim();
}

function normalizeText(value) {
  return String(value || "").trim();
}

function formatTableCell(value) {
  return normalizeText(value).replace(/\s+/g, " ").replaceAll("|", "\\|") || "暂无";
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
      <SummaryMarkdownRenderer :markdown="summaryMarkdown" />
      <section v-if="summaryResult.outline?.length" class="summary-section">
        <h5>章节时间轴</h5>
        <ul class="summary-list">
          <li v-for="(item, index) in summaryResult.outline" :key="`${formatOutlineItem(item)}-${index}`" class="summary-line-reveal" :style="lineRevealStyle(8, index)">
            {{ formatOutlineItem(item) }}
          </li>
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
            @click="emit('use-question', questionText(question))"
          >
            <HelpCircle :size="16" aria-hidden="true" />
            <span>{{ questionText(question) }}</span>
          </button>
        </div>
      </section>
    </div>

    <p v-else class="summary-empty">总结完成后会在这里显示摘要内容。</p>
  </section>
</template>
