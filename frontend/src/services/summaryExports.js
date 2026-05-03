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
  const lines = [
    `# ${title}`,
    "",
    "> 这份学习笔记由 SaveAny 基于公开视频字幕或语音转写生成，适合复盘、检索和继续整理。",
    "",
    "| 项目 | 内容 |",
    "| --- | --- |",
    `| 视频标题 | ${formatTableCell(title)} |`,
    `| 转写来源 | ${formatTableCell(sourceLabel(summary.transcript_source))} |`,
    `| 总结语言 | ${formatTableCell(summary.language || summary.transcript_language || "zh-CN")} |`,
    "",
    "## 快速导读",
    "",
    ...formatReadableSummarySection(summary.readable_summary),
    "### 一句话概览",
    "",
    formatParagraph(summary.overview, "暂无总结内容"),
    "",
    "### 核心结论",
    "",
    formatStringList(summary.key_points, { limit: 3, fallback: "暂无核心结论" }),
    "",
    ...formatUnderstandingSection(summary),
    "",
    "## 章节大纲",
    "",
    formatNumberedOutline(summary.outline),
    "",
    "## 核心知识点",
    "",
    formatStringList(summary.key_points, { fallback: "暂无关键要点" }),
    "",
    "## 时间轴要点",
    "",
    formatTimedTable(summary.highlights),
    "",
    "## 术语解释",
    "",
    formatTermTable(summary.terms),
    "",
    "## 思维导图",
    "",
    formatMindMap(summary.mind_map),
    "",
    "## AI 问答",
    "",
    formatQaSection(summary.qa_pairs, summary.questions),
    "",
    "## 后续追问",
    "",
    formatQuestionList(summary.questions),
    "",
    "<details>",
    "<summary>字幕原文</summary>",
    "",
    "```text",
    buildTranscriptText(summary),
    "```",
    "",
    "</details>"
  ];

  return lines.join("\n");
}

function formatReadableSummarySection(value) {
  const text = normalizeText(value);
  return text ? ["### 流式可读总结", "", text, ""] : [];
}

function formatUnderstandingSection(summary = {}) {
  const topic = normalizeText(summary.topic);
  const audience = normalizeText(summary.audience);
  const mainThread = normalizeArray(summary.main_thread).map(normalizeText).filter(Boolean);
  const examples = normalizeArray(summary.examples);
  const actionItems = normalizeArray(summary.action_items).map(normalizeText).filter(Boolean);
  const limitations = normalizeArray(summary.limitations).map(normalizeText).filter(Boolean);

  if (!topic && !audience && !mainThread.length && !examples.length && !actionItems.length && !limitations.length) {
    return [];
  }

  const lines = ["## 完整理解", ""];
  if (topic || audience) {
    lines.push(`| 主题 | ${formatTableCell(topic || "暂无")} |`);
    lines.push("| --- | --- |");
    lines.push(`| 适合人群 | ${formatTableCell(audience || "暂无")} |`);
  }

  if (mainThread.length) {
    lines.push("", "### 主线脉络", "", formatStringList(mainThread, { fallback: "暂无主线脉络" }));
  }

  if (examples.length) {
    lines.push("", "### 例子和证据", "", formatTimedTable(examples, "暂无例子和证据"));
  }

  if (actionItems.length) {
    lines.push("", "### 行动清单", "", formatStringList(actionItems, { fallback: "暂无行动建议" }));
  }

  if (limitations.length) {
    lines.push("", "### 边界和限制", "", formatStringList(limitations, { fallback: "暂无边界说明" }));
  }

  return lines;
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

function formatStringList(value, options = {}) {
  const limit = Number.isFinite(options.limit) ? Math.max(1, Math.floor(options.limit)) : Infinity;
  const lines = normalizeArray(value)
    .map((item) => normalizeText(item))
    .filter(Boolean)
    .slice(0, limit)
    .map((item) => `- ${item}`);

  return lines.length ? lines.join("\n") : options.fallback || "暂无内容";
}

function formatNumberedOutline(value) {
  const lines = normalizeArray(value)
    .map(formatOutlineText)
    .filter(Boolean)
    .map((item, index) => `${index + 1}. ${item}`);

  return lines.length ? lines.join("\n") : "暂无大纲内容";
}

function formatOutlineText(item) {
  if (!item || typeof item !== "object") return normalizeText(item);

  const time = normalizeText(item.time || item.timestamp || item.start);
  const title = normalizeText(item.title || item.heading || item.text) || "未命名章节";
  const summary = normalizeText(item.summary || item.description);
  const label = [time ? `[${time}]` : "", title ? `**${title}**` : ""].filter(Boolean).join(" ");
  if (summary && summary !== title) return `${label}：${summary}`;
  return label;
}

function formatTimedTable(value, fallback = "暂无高光片段") {
  const rows = normalizeArray(value)
    .map((item) => {
      if (!item || typeof item !== "object") {
        const text = normalizeText(item);
        return text ? ["时间未知", text] : null;
      }
      const time = normalizeText(item.time || item.timestamp || item.start) || "时间未知";
      const text = normalizeText(item.text || item.summary || item.title);
      return text ? [time, text] : null;
    })
    .filter(Boolean);

  if (!rows.length) return fallback;
  return ["| 时间 | 内容 |", "| --- | --- |", ...rows.map(([time, text]) => `| ${formatTableCell(time)} | ${formatTableCell(text)} |`)].join("\n");
}

function formatTermTable(value) {
  const rows = normalizeArray(value)
    .map((item) => {
      if (!item || typeof item !== "object") {
        const text = normalizeText(item);
        return text ? [text, ""] : null;
      }
      const term = normalizeText(item.term || item.title || item.name) || "术语";
      const explanation = normalizeText(item.explanation || item.definition || item.summary || item.text);
      return term || explanation ? [term, explanation] : null;
    })
    .filter(Boolean);

  if (!rows.length) return "暂无术语内容";
  return ["| 术语 | 解释 |", "| --- | --- |", ...rows.map(([term, explanation]) => `| ${formatTableCell(term)} | ${formatTableCell(explanation)} |`)].join("\n");
}

function formatMindMap(node, depth = 0) {
  if (!node || typeof node !== "object") return "- 视频主题";
  const title = normalizeText(node.title) || "视频主题";
  const children = normalizeArray(node.children)
    .map((child) => formatMindMap(child, depth + 1))
    .filter(Boolean);
  return [`${"  ".repeat(depth)}- ${title}`, ...children].join("\n");
}

function formatQaSection(qaPairs, questions) {
  const generatedPairs = normalizeArray(qaPairs)
    .map(normalizeQaPair)
    .filter((pair) => pair.question || pair.answer);
  const fallbackPairs = normalizeArray(questions)
    .map(normalizeQaPair)
    .filter((pair) => pair.question || pair.answer);
  const pairs = generatedPairs.length ? generatedPairs : fallbackPairs;

  if (!pairs.length) return "暂无问答内容";
  return pairs
    .map((pair, index) => {
      const question = pair.question || `问题 ${index + 1}`;
      const answer = pair.answer || "可以在 AI 问答中继续追问这个问题。";
      return `### Q${index + 1}. ${question}\n\n${answer}`;
    })
    .join("\n\n");
}

function formatQuestionList(value) {
  const lines = normalizeArray(value)
    .map(questionText)
    .filter(Boolean)
    .map((item) => `- ${item}`);

  return lines.length ? lines.join("\n") : "暂无延伸问题";
}

function questionText(item) {
  if (!item || typeof item !== "object") return normalizeText(item);
  return normalizeText(item.question || item.prompt || item.title || item.text);
}

function sourceLabel(source) {
  return {
    subtitle: "字幕",
    auto_subtitle: "自动字幕",
    speech_to_text: "语音转写"
  }[source] || "未知";
}

function formatTableCell(value) {
  const text = normalizeText(value).replace(/\s+/g, " ");
  return (text || "暂无").replaceAll("|", "\\|");
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
