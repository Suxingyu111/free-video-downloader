export const RELIABLE_MP4_FORMAT =
  "18/" +
  "bestvideo[ext=mp4][vcodec^=avc][height<=360]+bestaudio[ext=m4a]/" +
  "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/" +
  "best[ext=mp4][vcodec^=avc][height<=360]/best[height<=360]/best";

export const BEST_QUALITY_FORMAT = "bestvideo+bestaudio/best";
