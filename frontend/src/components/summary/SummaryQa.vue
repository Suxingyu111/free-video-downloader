<script setup>
import { Download, Loader2, MessageCircle, XCircle } from "lucide-vue-next";
import { computed } from "vue";
import { buildQaMarkdown, buildSafeSummaryFilename, downloadTextFile } from "../../services/summaryExports";

const props = defineProps({
  summaryResult: {
    type: Object,
    default: null
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
  }
});

const emit = defineEmits(["update:question", "submit-question"]);

const generatedPairs = computed(() => props.summaryResult?.qa_pairs || []);
const hasQa = computed(() => generatedPairs.value.length || props.summaryQaHistory.length);
const canSubmit = computed(
  () => props.summaryQuestion.trim() && !props.askingSummaryQuestion && !props.questionQuotaExhausted
);

function handleDownloadQa() {
  const markdown = buildQaMarkdown(props.summaryResult || {}, props.summaryQaHistory);
  const filename = buildSafeSummaryFilename(props.summaryResult?.title || "video-summary", "qa", "md");
  downloadTextFile(filename, markdown, "text/markdown;charset=utf-8");
}
</script>

<template>
  <section class="summary-module summary-qa" aria-labelledby="summary-qa-title">
    <div class="summary-module-header">
      <div>
        <p class="summary-module-eyebrow">AI 问答</p>
        <h4 id="summary-qa-title">问题与回答</h4>
      </div>
      <button class="summary-action-button" type="button" :disabled="!hasQa" @click="handleDownloadQa">
        <Download :size="18" aria-hidden="true" />
        <span>下载问答</span>
      </button>
    </div>

    <div v-if="generatedPairs.length" class="qa-group">
      <p class="summary-module-eyebrow">推荐问答</p>
      <div class="qa-list">
        <article v-for="(item, index) in generatedPairs" :key="`${item.question}-${index}`" class="qa-item">
          <strong>问：{{ item.question }}</strong>
          <p>答：{{ item.answer }}</p>
        </article>
      </div>
    </div>

    <form class="qa-form" @submit.prevent="emit('submit-question')">
      <label class="qa-form-label" for="summary-question">继续追问</label>
      <textarea
        id="summary-question"
        :value="summaryQuestion"
        rows="3"
        placeholder="基于字幕继续提问，例如：这段内容最重要的结论是什么？"
        :disabled="askingSummaryQuestion || questionQuotaExhausted"
        @input="emit('update:question', $event.target.value)"
      ></textarea>
      <p v-if="questionQuotaText" class="summary-module-eyebrow">本月 {{ questionQuotaText }}</p>
      <p v-if="questionQuotaExhausted" class="message error" role="alert">
        <XCircle :size="18" aria-hidden="true" />
        <span>本月 AI 问答次数已用完</span>
      </p>
      <button class="primary-button" type="submit" :disabled="!canSubmit">
        <Loader2 v-if="askingSummaryQuestion" :size="18" class="animate-spin" aria-hidden="true" />
        <MessageCircle v-else :size="18" aria-hidden="true" />
        <span>{{ askingSummaryQuestion ? "回答中" : "提问" }}</span>
      </button>
    </form>

    <div v-if="summaryQuestionError" class="message error" role="alert">
      <XCircle :size="18" aria-hidden="true" />
      <span>{{ summaryQuestionError }}</span>
    </div>

    <div v-if="summaryQaHistory.length" class="qa-group qa-history">
      <p class="summary-module-eyebrow">本次追问</p>
      <div class="qa-list">
        <article v-for="(item, index) in summaryQaHistory" :key="`${item.question}-${index}`" class="qa-item">
          <strong>问：{{ item.question }}</strong>
          <p>答：{{ item.answer }}</p>
        </article>
      </div>
    </div>

    <p v-if="!hasQa" class="summary-empty">这里会显示生成问答和本次会话追问记录。</p>
  </section>
</template>
