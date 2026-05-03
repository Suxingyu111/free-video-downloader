const DEFAULT_STREAM_LINE_LIMIT = 18;
const DEFAULT_STREAM_LINE_LENGTH = 72;

export function normalizeSummaryStreamLines(text, options = {}) {
  const maxLines = Number.isFinite(options.maxLines) ? Math.max(1, Math.floor(options.maxLines)) : DEFAULT_STREAM_LINE_LIMIT;
  const maxLineLength = Number.isFinite(options.maxLineLength)
    ? Math.max(12, Math.floor(options.maxLineLength))
    : DEFAULT_STREAM_LINE_LENGTH;
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => splitReadableLine(line, maxLineLength))
    .slice(-maxLines);
}

export function diffSummaryStreamLines(previousLines = [], nextLines = []) {
  const previous = sanitizeLines(previousLines);
  const next = sanitizeLines(nextLines);
  if (!next.length) return [];
  if (!previous.length) return next;

  let prefixLength = 0;
  while (prefixLength < previous.length && prefixLength < next.length && previous[prefixLength] === next[prefixLength]) {
    prefixLength += 1;
  }
  if (prefixLength === previous.length) {
    return next.slice(prefixLength);
  }

  for (let size = Math.min(previous.length, next.length); size > 0; size -= 1) {
    const previousTail = previous.slice(previous.length - size);
    const nextHead = next.slice(0, size);
    if (previousTail.every((line, index) => line === nextHead[index])) {
      return next.slice(size);
    }
  }

  return next;
}

function sanitizeLines(lines) {
  return Array.isArray(lines)
    ? lines
        .map((line) => String(line || "").trim())
        .filter(Boolean)
    : [];
}

function splitReadableLine(line, maxLineLength) {
  const value = String(line || "").trim();
  if (!value || value.length <= maxLineLength) return value ? [value] : [];

  const chunks = [];
  let remaining = value;
  while (remaining.length > maxLineLength) {
    const slice = remaining.slice(0, maxLineLength + 1);
    const breakIndex = readableBreakIndex(slice, maxLineLength);
    const chunk = remaining.slice(0, breakIndex).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(breakIndex).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function readableBreakIndex(text, maxLineLength) {
  const punctuation = "。！？；;，,、";
  for (let index = Math.min(maxLineLength, text.length - 1); index >= 12; index -= 1) {
    if (punctuation.includes(text[index - 1])) return index;
  }
  for (let index = Math.min(maxLineLength, text.length - 1); index >= 12; index -= 1) {
    if (/\s/.test(text[index - 1])) return index;
  }
  return maxLineLength;
}
