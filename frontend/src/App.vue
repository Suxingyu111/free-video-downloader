<script setup>
import { CheckCircle2, Download, FileKey2, FileVideo2, Link2, Loader2, Play, Search, ShieldCheck, Sparkles, Star, XCircle, Zap } from "lucide-vue-next";
import { computed, onBeforeUnmount, reactive } from "vue";
import { analyzeUrl, connectTaskEvents, createDownloadTask, getTask } from "./services/api";
import { BEST_QUALITY_FORMAT, RELIABLE_MP4_FORMAT } from "./services/formats";

const platforms = ["YouTube", "Bilibili", "TikTok", "Instagram", "X / Twitter", "Vimeo", "Facebook", "小红书", "抖音", "Reddit"];
const features = [
  ["主流平台全覆盖", "支持 YouTube、Bilibili、TikTok、Instagram 等主流平台，常见公开视频直接粘贴即可解析。"],
  ["清晰度自由选择", "自动识别标题、封面、时长和可用格式，按需选择稳定 MP4 或原始最高画质。"],
  ["列表与长视频更省心", "遇到合集、课程、播客或播放列表时，可一次创建任务，后台持续处理进度。"],
  ["本地部署更安心", "解析与下载任务在自己的服务中完成，减少广告跳转、弹窗劫持和不透明的第三方中转。"]
];

const quickLinks = ["YouTube", "Bilibili", "抖音"];

const state = reactive({
  url: "",
  analyzedUrl: "",
  selectedFormatId: RELIABLE_MP4_FORMAT,
  analyzing: false,
  downloading: false,
  cookiesFile: null,
  error: "",
  result: null,
  currentTaskId: null,
  tasks: []
});

const disconnectors = new Map();
const pollers = new Map();

const hasResult = computed(() => Boolean(state.result && state.analyzedUrl === state.url.trim()));
const playlistEntries = computed(() => state.result?.entries || []);
const formatOptions = computed(() => {
  const seen = new Set();
  const sourceFormats = (state.result?.formats || [])
    .filter((format) => format.vcodec !== "none")
    .sort((a, b) => (b.height || 0) - (a.height || 0))
    .filter((format) => {
      const key = `${format.height || format.resolution || format.label}-${format.ext}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 8)
    .map((format) => ({ format_id: format.format_id, label: formatLabel(format) }));

  return [
    { format_id: RELIABLE_MP4_FORMAT, label: "稳定 MP4（推荐）" },
    { format_id: BEST_QUALITY_FORMAT, label: "原始最高画质" },
    ...sourceFormats
  ];
});
const currentTask = computed(() => state.tasks.find((task) => task.id === state.currentTaskId) || null);
const isTaskRunning = computed(() => ["queued", "processing", "downloading"].includes(currentTask.value?.status));
const isBusy = computed(() => state.analyzing || state.downloading || isTaskRunning.value);
const canSaveFile = computed(() => currentTask.value?.status === "completed" && currentTask.value.download_url);
const progressValue = computed(() => Math.min(currentTask.value?.progress || 0, 100));
const statusText = computed(() => {
  if (state.error) return "";
  if (canSaveFile.value) return "下载完成，文件已准备好";
  if (currentTask.value?.message) return localizeStatus(currentTask.value.message);
  if (state.analyzing) return "正在解析链接，请稍等";
  if (state.downloading) return "正在创建下载任务";
  return "";
});

async function handleAnalyze() {
  state.error = "";
  state.result = null;
  state.analyzedUrl = "";
  state.currentTaskId = null;
  state.analyzing = true;
  try {
    const result = await analyzeUrl({ url: state.url.trim(), cookiesFile: state.cookiesFile });
    state.result = result;
    state.analyzedUrl = state.url.trim();
    state.selectedFormatId = RELIABLE_MP4_FORMAT;
  } catch (error) {
    state.error = localizeStatus(error.message);
  } finally {
    state.analyzing = false;
  }
}

function handleCookieFileChange(event) {
  const [file] = event.target.files || [];
  state.cookiesFile = file || null;
}

async function handleDownload() {
  if (canSaveFile.value) {
    window.location.href = currentTask.value.download_url;
    return;
  }
  if (!hasResult.value || isBusy.value) return;

  state.error = "";
  state.downloading = true;
  try {
    const entryIds = playlistEntries.value.map((entry) => entry.id).filter(Boolean);
    const { task_id: taskId } = await createDownloadTask({
      url: state.result.webpage_url || state.url.trim(),
      entry_ids: entryIds,
      format_id: state.selectedFormatId,
      subtitle_langs: [],
      write_auto_subs: false,
      prefer_srt: true,
      cookie_ref: state.result.cookie_ref || null
    });
    registerTask(taskId);
  } catch (error) {
    state.error = localizeStatus(error.message);
  } finally {
    state.downloading = false;
  }
}

function registerTask(taskId) {
  const task = {
    id: taskId,
    status: "queued",
    progress: 0,
    message: "任务已排队，正在准备下载环境",
    speed: null,
    eta: null,
    download_url: null,
    error: null
  };
  state.currentTaskId = taskId;
  state.tasks.unshift(task);

  const disconnect = connectTaskEvents(
    taskId,
    (snapshot) => {
      applyTaskSnapshot(taskId, snapshot);
      if (snapshot.status === "completed" || snapshot.status === "failed") {
        disconnectors.get(taskId)?.();
        disconnectors.delete(taskId);
      }
    },
    (message) => {
      task.status = "failed";
      task.error = localizeStatus(message);
      state.error = task.error;
    }
  );
  disconnectors.set(taskId, disconnect);

  const poller = window.setInterval(async () => {
    try {
      const snapshot = await getTask(taskId);
      applyTaskSnapshot(taskId, snapshot);
      if (snapshot.status === "completed" || snapshot.status === "failed") {
        window.clearInterval(poller);
        pollers.delete(taskId);
        disconnectors.get(taskId)?.();
        disconnectors.delete(taskId);
      }
    } catch (error) {
      task.error = localizeStatus(error.message);
      state.error = task.error;
    }
  }, 1000);
  pollers.set(taskId, poller);
}

function applyTaskSnapshot(taskId, snapshot) {
  const existingTask = state.tasks.find((item) => item.id === taskId);
  if (existingTask) {
    Object.assign(existingTask, snapshot);
    existingTask.message = localizeStatus(snapshot.message || existingTask.message);
    if (snapshot.status === "failed" && snapshot.error) state.error = localizeStatus(snapshot.error);
  }
}

function localizeStatus(message = "") {
  return message
    .replaceAll("Queued", "排队中")
    .replaceAll("Starting download", "正在启动下载")
    .replaceAll("Downloading media", "正在下载媒体文件")
    .replaceAll("Processing downloaded file", "正在处理下载文件")
    .replaceAll("Download complete", "下载完成")
    .replaceAll("Download failed", "下载失败")
    .replaceAll("Failed to fetch", "网络请求失败，请确认后端服务已启动");
}

function formatLabel(format) {
  const quality = format.height ? `${format.height}p` : format.resolution || format.label || "视频";
  const ext = format.ext ? format.ext.toUpperCase() : "自动格式";
  const size = format.filesize ? ` · ${formatFileSize(format.filesize)}` : "";
  return `${quality} · ${ext}${size}`;
}

function formatFileSize(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDuration(seconds) {
  if (!seconds) return "时长未知";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${rest}`;
}

onBeforeUnmount(() => {
  disconnectors.forEach((disconnect) => disconnect());
  pollers.forEach((poller) => window.clearInterval(poller));
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <a class="brand" href="#" aria-label="万能视频下载器首页">
        <span class="brand-mark" aria-hidden="true"><FileVideo2 :size="21" /></span>
        <span class="brand-name">SaveAny</span>
        <span class="brand-pill">万能视频下载</span>
      </a>
      <nav class="nav-links" aria-label="主导航">
        <a href="#features">功能特性</a>
        <a href="#pricing">套餐价格</a>
        <a href="#platforms">支持平台</a>
        <a class="nav-cta" href="#download"><Star :size="18" aria-hidden="true" />开通 VIP</a>
      </nav>
    </header>

    <section id="download" class="hero" aria-labelledby="page-title">
      <div class="hero-copy-block">
        <p class="kicker"><span aria-hidden="true"></span>支持 1800+ 平台，永久免费使用</p>
        <h1 id="page-title" aria-label="复制链接，一键保存高清视频">
          <span class="title-main">万能视频下载器，</span><span>一键保存</span>
        </h1>
        <p class="hero-copy">粘贴视频链接，自动解析标题、封面、清晰度和音频。YouTube、Bilibili、抖音、TikTok... 随时随地，想下就下。</p>
      </div>

      <section class="console" aria-label="视频下载控制台">
        <form class="search-panel" @submit.prevent="handleAnalyze">
          <label class="sr-only" for="video-url">视频链接</label>
          <div class="url-field">
            <Link2 :size="20" aria-hidden="true" />
            <input id="video-url" v-model="state.url" type="url" inputmode="url" autocomplete="url" placeholder="粘贴 YouTube、Bilibili、TikTok 等公开视频链接" required />
            <button class="primary-button inline-button" type="submit" :disabled="state.analyzing || !state.url.trim()">
              <Loader2 v-if="state.analyzing" :size="21" class="animate-spin" aria-hidden="true" />
              <Search v-else :size="21" aria-hidden="true" />
              <span>{{ state.analyzing ? "解析中" : "解析视频" }}</span>
            </button>
          </div>
          <div class="quick-row" aria-label="平台示例">
            <span>试试:</span>
            <span v-for="link in quickLinks" :key="link" class="quick-chip">{{ link }}</span>
            <label class="cookie-chip" :class="{ selected: state.cookiesFile }">
              <FileKey2 :size="16" aria-hidden="true" />
              <span>{{ state.cookiesFile?.name || "cookies.txt" }}</span>
              <input type="file" accept=".txt,text/plain" @change="handleCookieFileChange" />
            </label>
          </div>
        </form>

        <section v-if="state.error" class="message error" role="alert">
          <XCircle :size="18" aria-hidden="true" />
          <span>{{ state.error }}</span>
        </section>

        <section v-if="hasResult" class="result-card" aria-label="视频信息">
          <img v-if="state.result.thumbnail" class="cover" :src="state.result.thumbnail" :alt="state.result.title" />
          <div v-else class="cover empty-cover" aria-hidden="true"><Play :size="34" /></div>
          <div class="result-main">
            <p class="result-meta">
              <span>{{ state.result.extractor || state.result.kind }}</span>
              <span>{{ formatDuration(state.result.duration) }}</span>
              <span v-if="playlistEntries.length">{{ playlistEntries.length }} 个视频</span>
            </p>
            <h2>{{ state.result.title }}</h2>
            <div class="download-row">
              <label class="sr-only" for="format-select">选择清晰度</label>
              <select id="format-select" v-model="state.selectedFormatId">
                <option v-for="format in formatOptions" :key="format.format_id" :value="format.format_id">{{ format.label }}</option>
              </select>
              <button v-if="!canSaveFile" class="primary-button" type="button" :disabled="state.downloading || isTaskRunning" @click="handleDownload">
                <Loader2 v-if="state.downloading || isTaskRunning" :size="20" class="animate-spin" aria-hidden="true" />
                <Download v-else :size="20" aria-hidden="true" />
                <span>{{ state.downloading || isTaskRunning ? "下载中" : "立即下载" }}</span>
              </button>
              <a v-else class="primary-button" :href="currentTask.download_url" download>
                <CheckCircle2 :size="20" aria-hidden="true" />
                <span>保存文件</span>
              </a>
            </div>
            <div v-if="statusText && !state.error" class="message" aria-live="polite">
              <span>{{ statusText }}</span>
              <span v-if="isTaskRunning">{{ Math.round(progressValue) }}%</span>
            </div>
            <div v-if="currentTask && !state.error" class="progress-track" aria-hidden="true">
              <div class="progress-fill" :style="{ width: `${progressValue}%` }"></div>
            </div>
          </div>
        </section>

        <ol v-else class="workflow" aria-label="下载流程">
          <li><span>1</span>粘贴链接</li>
          <li><span>2</span>智能解析</li>
          <li><span>3</span>选择清晰度</li>
          <li><span>4</span>一键保存</li>
        </ol>
      </section>

      <div class="trust-strip" aria-label="产品亮点">
        <span><ShieldCheck :size="18" />无广告跳转</span>
        <span><Zap :size="18" />批量任务</span>
        <span><Sparkles :size="18" />高清画质</span>
      </div>
    </section>

    <section id="platforms" class="section">
      <p class="kicker">覆盖你每天会遇到的视频来源</p>
      <h2>从长视频到短视频，从公开视频到播放列表</h2>
      <div class="platform-grid">
        <span v-for="platform in platforms" :key="platform">{{ platform }}</span>
      </div>
      <p class="section-copy">抖音公开视频免登录下载；受平台风控影响，少数链接可能失败。其他平台兼容能力基于 yt-dlp 的站点解析器，遇到登录态、地区限制或平台风控时，可能需要 cookies 或稍后重试。</p>
    </section>

    <section id="features" class="section">
      <p class="kicker">为什么它看起来值得付费</p>
      <h2>不只是“能下”，而是把下载变成可靠工作流</h2>
      <div class="feature-grid">
        <article v-for="[title, text] in features" :key="title">
          <CheckCircle2 :size="22" aria-hidden="true" />
          <h3>{{ title }}</h3>
          <p>{{ text }}</p>
        </article>
      </div>
    </section>

    <section id="pricing" class="section pricing-section">
      <p class="kicker">轻量开始，需要时再升级</p>
      <h2>免费版覆盖常用下载，高频任务可以切到 VIP 队列</h2>
      <div class="pricing-card">
        <div>
          <h3>SaveAny VIP</h3>
          <p>更高并发、批量队列、长视频优先处理，适合素材整理和内容运营。</p>
        </div>
        <a class="primary-button" href="#download"><Star :size="20" aria-hidden="true" />开通 VIP</a>
      </div>
    </section>
  </main>
</template>
