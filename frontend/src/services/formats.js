export const RELIABLE_MP4_FORMAT =
  "18/" +
  "bestvideo[ext=mp4][vcodec^=avc][height<=360]+bestaudio[ext=m4a]/" +
  "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/" +
  "best[ext=mp4][vcodec^=avc][height<=360]/best[height<=360]/best";

export const BEST_QUALITY_FORMAT = "bestvideo+bestaudio/best";

export function resolveDownloadFormat(format) {
  const formatId = String(format?.format_id || "");
  if (!formatId || formatId.includes("+") || formatId.includes("/")) {
    return formatId;
  }
  if (format?.vcodec && format.vcodec !== "none" && format?.acodec === "none") {
    return `${formatId}+bestaudio[ext=m4a]/${formatId}+bestaudio/${formatId}`;
  }
  return formatId;
}
