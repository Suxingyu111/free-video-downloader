const DEFAULT_STREAM_LINE_LIMIT = 18;

export function normalizeSummaryStreamLines(text, options = {}) {
  const maxLines = Number.isFinite(options.maxLines) ? Math.max(1, Math.floor(options.maxLines)) : DEFAULT_STREAM_LINE_LIMIT;
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
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
