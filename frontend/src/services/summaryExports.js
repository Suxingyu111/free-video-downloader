const DANGEROUS_FILENAME_CHARS = /[\/\\:*?"<>|]/g;
const DEFAULT_TITLE = "video-summary";

export function buildSafeSummaryFilename(title, suffix, extension) {
  const safeTitle = cleanFilenamePart(title) || DEFAULT_TITLE;
  const safeSuffix = cleanFilenamePart(suffix);
  const safeExtension = cleanFilenamePart(extension).replace(/^\.+/, "");
  const name = safeSuffix ? `${safeTitle}-${safeSuffix}` : safeTitle;

  return safeExtension ? `${name}.${safeExtension}` : name;
}

export function buildSummaryMarkdown(summary = {}) {
  const title = normalizeText(summary.title) || "AI 视频总结";
  const sections = [
    ["总览", formatParagraph(summary.overview, "暂无总结内容")],
    ["大纲", formatList(summary.outline, formatOutlineItem, "暂无大纲内容")],
    ["关键要点", formatList(summary.key_points, formatPlainListItem, "暂无关键要点")],
    ["高光片段", formatList(summary.highlights, formatTimedItem, "暂无高光片段")],
    ["术语表", formatList(summary.terms, formatTermItem, "暂无术语内容")],
    ["延伸问题", formatList(summary.questions, formatQuestionPromptItem, "暂无延伸问题")]
  ];

  return [`# ${title}`, ...sections.map(([heading, body]) => `## ${heading}\n\n${body}`)].join("\n\n");
}

export function buildTranscriptText(summary = {}) {
  const segments = Array.isArray(summary.transcript_segments) ? summary.transcript_segments : [];
  const segmentText = segments
    .map(formatTranscriptSegment)
    .filter(Boolean)
    .join("\n");

  if (segmentText) return segmentText;

  return normalizeText(summary.transcript_text) || "暂无字幕文本";
}

export function buildQaMarkdown(summary = {}, history = []) {
  const title = normalizeText(summary.title);
  const qaPairs = [
    ...normalizeArray(summary.qa_pairs),
    ...normalizeArray(history)
  ]
    .map(normalizeQaPair)
    .filter((pair) => pair.question || pair.answer);

  const heading = title ? `# ${title} - AI 问答` : "# AI 问答";
  if (!qaPairs.length) return `${heading}\n\n暂无问答内容`;

  const body = qaPairs
    .map((pair, index) => {
      const question = pair.question || `问题 ${index + 1}`;
      const answer = pair.answer || "暂无回答";
      return `## ${index + 1}. ${question}\n\n${answer}`;
    })
    .join("\n\n");

  return `${heading}\n\n${body}`;
}

export function downloadTextFile(filename, content, mimeType = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mimeType });
  downloadBlob(blob, filename);
}

export function downloadBlob(blob, filename) {
  if (typeof document === "undefined" || typeof URL === "undefined") {
    return;
  }

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function cleanFilenamePart(value) {
  return normalizeText(value)
    .replace(DANGEROUS_FILENAME_CHARS, "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeText(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function normalizeArray(value) {
  return Array.isArray(value) ? value : [];
}

function formatParagraph(value, fallback) {
  return normalizeText(value) || fallback;
}

function formatList(value, formatter, fallback) {
  const lines = normalizeArray(value)
    .map(formatter)
    .filter(Boolean);

  return lines.length ? lines.join("\n") : fallback;
}

function formatPlainListItem(item) {
  const text = normalizeText(item);
  return text ? `- ${text}` : "";
}

function formatOutlineItem(item) {
  if (!item || typeof item !== "object") return formatPlainListItem(item);

  const time = normalizeText(item.time || item.timestamp || item.start);
  const title = normalizeText(item.title || item.heading || item.text);
  const summary = normalizeText(item.summary || item.description);
  const label = [time ? `[${time}]` : "", title].filter(Boolean).join(" ");
  const body = [label, summary].filter(Boolean).join(" - ");

  return body ? `- ${body}` : "";
}

function formatTimedItem(item) {
  if (!item || typeof item !== "object") return formatPlainListItem(item);

  const time = normalizeText(item.time || item.timestamp || item.start);
  const text = normalizeText(item.text || item.summary || item.title);
  const body = time ? `[${time}] ${text}` : text;

  return body ? `- ${body}` : "";
}

function formatTermItem(item) {
  if (!item || typeof item !== "object") return formatPlainListItem(item);

  const term = normalizeText(item.term || item.title || item.name);
  const explanation = normalizeText(item.explanation || item.definition || item.summary || item.text);
  if (term && explanation) return `- **${term}**：${explanation}`;
  if (term) return `- **${term}**`;
  return explanation ? `- ${explanation}` : "";
}

function formatQuestionPromptItem(item) {
  if (!item || typeof item !== "object") return formatPlainListItem(item);

  const question = normalizeText(item.question || item.prompt || item.title || item.text);
  const answer = normalizeText(item.answer || item.response || item.summary);
  if (question && answer) return `- **${question}** ${answer}`;
  return question ? `- ${question}` : "";
}

function formatTranscriptSegment(segment) {
  if (!segment || typeof segment !== "object") return normalizeText(segment);

  const time = normalizeText(segment.time || segment.timestamp || segment.start);
  const text = normalizeText(segment.text || segment.content || segment.caption);
  if (!text) return "";

  return time ? `[${time}] ${text}` : text;
}

function normalizeQaPair(item) {
  if (!item || typeof item !== "object") {
    return { question: normalizeText(item), answer: "" };
  }

  return {
    question: normalizeText(item.question || item.prompt || item.title),
    answer: normalizeText(item.answer || item.response || item.content)
  };
}
