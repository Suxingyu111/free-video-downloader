<script setup>
import {
  BrainCircuit,
  CheckCircle2,
  CreditCard,
  Download,
  FileVideo2,
  Globe2,
  KeyRound,
  Link2,
  Loader2,
  LogOut,
  MonitorSmartphone,
  Play,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  UserRound,
  XCircle,
} from "lucide-vue-next";
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, watch } from "vue";
import {
  analyzeUrl,
  askSummaryQuestion,
  confirmPasswordReset,
  connectSummaryEvents,
  connectTaskEvents,
  createBillingCheckout,
  createBillingPortal,
  createDownloadTask,
  createSummaryTask,
  getBillingStatus,
  getMe,
  getSummary,
  getTask,
  loginAccount,
  logoutAccount,
  mockBillingAction,
  registerAccount,
  requestPasswordReset
} from "./services/api";
import { authInitialState, clearAuthState, membershipLabel, remainingSummaryText, updateAuthState } from "./services/authSession";
import { BEST_QUALITY_FORMAT, RELIABLE_MP4_FORMAT, resolveDownloadFormat } from "./services/formats";
import { applyWorkspaceSnapshot, loadWorkspaceSnapshot, pickWorkspaceSnapshot, saveWorkspaceSnapshot } from "./services/workspacePersistence";
import { seoCompliancePoints, seoFaqs } from "./seo/pages";

const SummaryPanel = defineAsyncComponent(() => import("./components/summary/SummaryPanel.vue"));

const HOME_PAGE_ID = "download";
const PRICING_PAGE_ID = "pricing";
const HOME_DOWNLOAD_ANCHOR_ID = "download-console";
const FREE_QUOTA_EXHAUSTED_MESSAGE = "今日免费 AI 总结额度已用完，请开通专业版继续使用。";
const homeHighlights = [
  {
    title: "公开视频平台",
    description: "支持 YouTube、Bilibili、TikTok、Instagram 等主流平台，也覆盖抖音、小红书等视频来源；抖音公开视频免登录下载；受平台风控影响，少数链接可能失败。",
    icon: Globe2,
    metric: "1800+",
    tone: "sky"
  },
  {
    title: "清晰度可选",
    description: "自动识别标题、封面、时长和可用格式，按需选择稳定 MP4 或原始最高画质。",
    icon: SlidersHorizontal,
    metric: "MP4",
    tone: "green"
  },
  {
    title: "解析后自动总结",
    description: "解析完成后自动生成摘要、字幕、思维导图和 AI 问答，把视频变成可复习的学习笔记。",
    icon: BrainCircuit,
    metric: "AI",
    tone: "orange",
    featured: true
  },
  {
    title: "手机浏览器可用",
    description: "无需安装 App，手机浏览器打开即可粘贴链接、解析视频、查看总结和下载内容。",
    icon: MonitorSmartphone,
    metric: "Web",
    tone: "rose"
  }
];

const pageLinks = [
  { id: HOME_DOWNLOAD_ANCHOR_ID, label: "回到下载", type: "anchor" },
  { id: "home-highlights", label: "核心能力", type: "anchor" },
  { id: "home-faq", label: "常见问题", type: "anchor" },
  { id: PRICING_PAGE_ID, label: "套餐方案", type: "page", accent: true }
];
const pageIds = [HOME_PAGE_ID, PRICING_PAGE_ID];
const homeAnchorIds = pageLinks.filter((link) => link.type === "anchor").map((link) => link.id);
const quickLinks = ["YouTube", "Bilibili", "抖音"];
const pricingPlans = [
  {
    id: "free",
    badge: "轻量体验",
    name: "免费版",
    price: "¥0",
    cycle: "永久免费",
    description: "适合偶尔保存公开视频、体验 AI 总结和验证本地工作流。",
    features: ["稳定 MP4 下载体验", "少量 AI 总结试用", "浏览器本地工作区缓存", "适合验证自托管流程"],
    cta: "开始免费使用",
    target: "download"
  },
  {
    id: "pro",
    badge: "推荐",
    name: "专业版",
    price: "¥29",
    cycle: "/月",
    description: "适合学习者、创作者和内容运营，把下载、字幕和总结变成高频工作流。",
    features: ["更高频的解析与总结方案", "长视频解析与字幕整理", "AI 摘要、字幕、思维导图导出", "适合个人知识库沉淀"],
    cta: "查看专业方案",
    target: "download",
    featured: true
  },
  {
    id: "team",
    badge: "团队协作",
    name: "团队版",
    price: "¥99",
    cycle: "/月起",
    description: "适合课程团队、MCN 和资料整理小组，共享公开视频素材与学习笔记。",
    features: ["多人共享工作区规划", "团队级 AI 总结额度方案", "自托管部署建议", "基础用量与任务报表规划"],
    cta: "咨询团队版",
    target: "download"
  }
];
const pricingGuarantees = ["只处理用户有权访问的公开视频", "不托管登录态或付费绕过能力", "会员状态以服务端和 Stripe webhook 为准"];
const compactFaqs = seoFaqs.slice(0, 3);
const compactCompliancePoints = seoCompliancePoints.slice(0, 3);

function hashTarget(hash = "") {
  return hash.replace(/^#/, "").split("?")[0].trim();
}

function hashParams(hash = "") {
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  return new URLSearchParams(query);
}

function normalizePageHash(hash = "") {
  const pageId = hashTarget(hash);
  return pageIds.includes(pageId) ? pageId : HOME_PAGE_ID;
}

function normalizeHomeAnchorHash(hash = "") {
  const anchorId = hashTarget(hash);
  return homeAnchorIds.includes(anchorId) ? anchorId : "";
}

const state = reactive({
  currentPage: "download",
  activeAnchor: "",
  url: "",
  analyzedUrl: "",
  selectedFormatId: RELIABLE_MP4_FORMAT,
  analyzing: false,
  downloading: false,
  summarizing: false,
  error: "",
  summaryError: "",
  summaryView: "summary",
  summaryQuestion: "",
  summaryQuestionError: "",
  summaryQaHistory: [],
  askingSummaryQuestion: false,
  result: null,
  currentTaskId: null,
  currentSummaryId: null,
  summaryTask: null,
  tasks: [],
  checkoutStatus: "",
  billingBusy: false,
  billingMessage: ""
});

const auth = reactive(authInitialState());
const authForm = reactive({
  open: false,
  mode: "login",
  email: "",
  password: "",
  token: "",
  busy: false,
  error: "",
  notice: ""
});

applyWorkspaceSnapshot(state, loadWorkspaceSnapshot());

if (typeof window !== "undefined") {
  state.currentPage = normalizePageHash(window.location.hash);
  state.activeAnchor = state.currentPage === HOME_PAGE_ID ? normalizeHomeAnchorHash(window.location.hash) : "";
  state.checkoutStatus = hashParams(window.location.hash).get("checkout") || "";
}

watch(
  () => pickWorkspaceSnapshot(state),
  (snapshot) => saveWorkspaceSnapshot(snapshot),
  { deep: true }
);

const disconnectors = new Map();
const pollers = new Map();
const summaryDisconnectors = new Map();
const summaryPollers = new Map();

const currentPage = computed(() => state.currentPage);
const authMembershipLabel = computed(() => membershipLabel(auth));
const authUsageText = computed(() => remainingSummaryText(auth));
const showMockBilling = computed(() => Boolean(auth.user && auth.billingMode === "mock"));
const authTitle = computed(() => {
  if (authForm.mode === "register") return "注册账号";
  if (authForm.mode === "reset-request") return "重置密码";
  if (authForm.mode === "reset-confirm") return "设置新密码";
  return "登录账号";
});
const authSubmitLabel = computed(() => {
  if (authForm.mode === "register") return "注册并登录";
  if (authForm.mode === "reset-request") return "发送重置链接";
  if (authForm.mode === "reset-confirm") return "更新密码";
  return "登录";
});
const checkoutNotice = computed(() => {
  if (state.checkoutStatus === "success") return "正在确认会员状态，请稍等几秒。";
  if (state.checkoutStatus === "cancel") return "已取消支付，可以稍后继续开通专业版。";
  return "";
});
const hasSummaryQuotaError = computed(() => state.summaryError.includes(FREE_QUOTA_EXHAUSTED_MESSAGE.slice(0, 14)));
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
    .map((format) => ({ format_id: resolveDownloadFormat(format), label: formatLabel(format) }));

  return [
    { format_id: RELIABLE_MP4_FORMAT, label: "稳定 MP4（推荐）" },
    { format_id: BEST_QUALITY_FORMAT, label: "原始最高画质" },
    ...sourceFormats
  ];
});
const currentTask = computed(() => state.tasks.find((task) => task.id === state.currentTaskId) || null);
const isTaskRunning = computed(() => ["queued", "processing", "downloading"].includes(currentTask.value?.status));
const isBusy = computed(() => state.analyzing || state.downloading || isTaskRunning.value);
const canSaveFile = computed(
  () =>
    currentTask.value?.status === "completed" &&
    currentTask.value.download_url &&
    currentTask.value.format_id === state.selectedFormatId
);
const progressValue = computed(() => Math.min(currentTask.value?.progress || 0, 100));
const isSummaryRunning = computed(() => ["queued", "transcribing", "summarizing"].includes(state.summaryTask?.status));
const summaryResult = computed(() => state.summaryTask?.result || state.summaryTask?.draft_result || null);
const isSummaryDraft = computed(() => Boolean(state.summaryTask?.draft_result && !state.summaryTask?.result));
const canExportMarkdown = computed(() => Boolean(state.summaryTask?.status === "completed" && state.summaryTask.markdown_url));
const statusText = computed(() => {
  if (state.error) return "";
  if (canSaveFile.value) return "下载完成，文件已准备好";
  if (currentTask.value?.message) return localizeStatus(currentTask.value.message);
  if (state.analyzing) return "正在解析链接，请稍等";
  if (state.downloading) return "正在创建下载任务";
  return "";
});
const summaryStatusText = computed(() => {
  if (state.summaryError) return "";
  if (state.summaryTask?.message) return localizeSummaryStatus(state.summaryTask.message);
  if (state.summarizing) return "正在自动总结视频内容";
  return "";
});
const summaryActionLabel = computed(() => (state.summaryError ? "重试总结" : "重新总结"));

function scrollPageToTop(behavior = "auto") {
  if (typeof window === "undefined") return;
  const scroll = () => window.scrollTo({ top: 0, behavior });
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

function scrollToHomeAnchor(anchorId, behavior = "auto") {
  if (typeof window === "undefined" || !anchorId) return;
  const scroll = () => {
    const target = document.getElementById(anchorId);
    if (!target) return;
    const topbarOffset = 88;
    const targetTop = target.getBoundingClientRect().top + window.scrollY - topbarOffset;
    window.scrollTo({ top: Math.max(targetTop, 0), behavior });
  };
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

function updateHash(hash) {
  if (typeof window === "undefined" || window.location.hash === hash) return;
  window.history.pushState(null, "", hash);
}

async function syncCurrentPageFromHash() {
  if (typeof window === "undefined") return;
  const nextPage = normalizePageHash(window.location.hash);
  const nextAnchor = nextPage === HOME_PAGE_ID ? normalizeHomeAnchorHash(window.location.hash) : "";
  const params = hashParams(window.location.hash);
  state.currentPage = nextPage;
  state.activeAnchor = nextAnchor;
  state.checkoutStatus = params.get("checkout") || "";
  if (state.checkoutStatus === "success") {
    refreshMe({ silent: true });
  }
  await nextTick();
  if (nextAnchor) {
    scrollToHomeAnchor(nextAnchor, "auto");
  } else {
    scrollPageToTop("auto");
  }
}

async function navigateToHomeAnchor(anchorId) {
  const nextAnchor = normalizeHomeAnchorHash(`#${anchorId}`);
  if (!nextAnchor) return;
  state.currentPage = HOME_PAGE_ID;
  state.activeAnchor = nextAnchor;
  await nextTick();
  updateHash(`#${nextAnchor}`);
  scrollToHomeAnchor(nextAnchor, "smooth");
}

function navigateToNavLink(link) {
  if (link.type === "page") {
    navigateToPage(link.id);
  } else {
    navigateToHomeAnchor(link.id);
  }
}

async function navigateToPage(pageId) {
  const nextPage = normalizePageHash(`#${pageId}`);
  state.currentPage = nextPage;
  state.activeAnchor = "";
  state.checkoutStatus = "";
  if (typeof window === "undefined") return;

  const nextHash = `#${nextPage}`;
  updateHash(nextHash);
  await nextTick();
  scrollPageToTop("smooth");
}

function isNavLinkCurrent(link) {
  if (link.id === HOME_DOWNLOAD_ANCHOR_ID) {
    return state.currentPage === HOME_PAGE_ID && (!state.activeAnchor || state.activeAnchor === HOME_DOWNLOAD_ANCHOR_ID);
  }
  if (link.type === "page") return state.currentPage === link.id && !state.activeAnchor;
  return state.currentPage === HOME_PAGE_ID && state.activeAnchor === link.id;
}

function openAuth(mode = "login") {
  authForm.mode = mode;
  authForm.open = true;
  authForm.error = "";
  authForm.notice = "";
  if (auth.user?.email && !authForm.email) authForm.email = auth.user.email;
}

function closeAuth() {
  authForm.open = false;
  authForm.error = "";
}

async function refreshMe({ silent = false } = {}) {
  if (!silent) auth.loading = true;
  try {
    const payload = await getMe();
    updateAuthState(auth, payload);
    try {
      const billing = await getBillingStatus();
      if (billing.membership) auth.membership = billing.membership;
      auth.billingMode = billing.mode || auth.billingMode;
    } catch {
      auth.billingMode = "";
    }
  } catch {
    clearAuthState(auth);
  } finally {
    auth.loading = false;
  }
}

async function submitAuth() {
  authForm.error = "";
  authForm.notice = "";
  authForm.busy = true;
  try {
    if (authForm.mode === "reset-request") {
      const payload = await requestPasswordReset({ email: authForm.email });
      authForm.notice = payload.reset_token
        ? "开发模式已生成重置 token，请设置新密码。"
        : "如果账号存在，重置链接会发送到邮箱。";
      if (payload.reset_token) authForm.token = payload.reset_token;
      authForm.mode = "reset-confirm";
      return;
    }
    if (authForm.mode === "reset-confirm") {
      await confirmPasswordReset({ token: authForm.token, password: authForm.password });
      authForm.notice = "密码已更新，请使用新密码登录。";
      authForm.mode = "login";
      authForm.password = "";
      authForm.token = "";
      return;
    }
    const payload =
      authForm.mode === "register"
        ? await registerAccount({ email: authForm.email, password: authForm.password })
        : await loginAccount({ email: authForm.email, password: authForm.password });
    updateAuthState(auth, payload);
    await refreshMe({ silent: true });
    authForm.open = false;
    authForm.password = "";
  } catch (error) {
    authForm.error = error.message;
  } finally {
    authForm.busy = false;
  }
}

async function logout() {
  try {
    await logoutAccount();
  } finally {
    clearAuthState(auth);
  }
}

async function startCheckout() {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  state.billingBusy = true;
  state.billingMessage = "";
  try {
    const result = await createBillingCheckout();
    if (result.url && typeof window !== "undefined") window.location.href = result.url;
  } catch (error) {
    state.billingMessage = localizeStatus(error.message);
  } finally {
    state.billingBusy = false;
  }
}

async function openBillingPortal() {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  state.billingBusy = true;
  state.billingMessage = "";
  try {
    const result = await createBillingPortal();
    if (result.url && typeof window !== "undefined") window.location.href = result.url;
  } catch (error) {
    state.billingMessage = localizeStatus(error.message);
  } finally {
    state.billingBusy = false;
  }
}

async function runMockBilling(action) {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  state.billingBusy = true;
  state.billingMessage = "";
  try {
    const result = await mockBillingAction(action);
    if (result.membership) auth.membership = result.membership;
    await refreshMe({ silent: true });
    state.billingMessage = "会员状态已更新。";
  } catch (error) {
    state.billingMessage = localizeStatus(error.message);
  } finally {
    state.billingBusy = false;
  }
}

async function handleAnalyze() {
  state.error = "";
  state.result = null;
  state.analyzedUrl = "";
  state.currentTaskId = null;
  clearCurrentSummary();
  resetSummaryInteraction();
  state.analyzing = true;
  try {
    const result = await analyzeUrl({ url: state.url.trim() });
    state.result = result;
    state.analyzedUrl = state.url.trim();
    state.selectedFormatId = RELIABLE_MP4_FORMAT;
    startSummaryForResult(result, { mode: "auto" });
  } catch (error) {
    state.error = localizeStatus(error.message);
  } finally {
    state.analyzing = false;
  }
}

async function startSummaryForResult(result, { mode = "manual" } = {}) {
  if (!result || state.summarizing || isSummaryRunning.value) return;
  if (!auth.user) {
    openAuth("login");
    state.summaryError = "登录后每天可免费总结 3 次。";
    return;
  }

  clearCurrentSummary();
  state.summaryError = "";
  resetSummaryInteraction();
  state.summarizing = true;
  try {
    const summary = await createSummaryTask({
      url: result.webpage_url || state.url.trim(),
      title: result.title,
      language: "zh-CN",
      force: mode !== "auto"
    });
    if (summary.usage) auth.usage = summary.usage;
    refreshMe({ silent: true });
    const { summary_id: summaryId, cache_hit: cacheHit } = summary;
    registerSummary(summaryId, {
      message: cacheHit ? "Restored summary from cache" : mode === "auto" ? "正在自动总结视频内容" : "AI 总结任务已排队"
    });
  } catch (error) {
    state.summaryError = localizeSummaryStatus(error.message);
    if (error.message.includes("请先登录")) openAuth("login");
  } finally {
    state.summarizing = false;
  }
}

function retrySummary() {
  startSummaryForResult(state.result, { mode: state.summaryError ? "retry" : "manual" });
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
      prefer_srt: true
    });
    registerTask(taskId, state.selectedFormatId);
  } catch (error) {
    state.error = localizeStatus(error.message);
  } finally {
    state.downloading = false;
  }
}

function registerSummary(summaryId, options = {}) {
  resetSummaryInteraction();
  state.currentSummaryId = summaryId;
  state.summaryTask = {
    id: summaryId,
    status: "queued",
    stage: "queued",
    progress: 0,
    message: options.message || "AI 总结任务已排队",
    result: null,
    draft_result: null,
    streamed_text: "",
    markdown_url: null,
    error: null
  };
  trackSummary(summaryId);
}

function resumeSummary(summaryId) {
  if (!summaryId) return;
  if (!state.summaryTask || state.summaryTask.id !== summaryId) {
    state.summaryTask = {
      id: summaryId,
      status: "queued",
      stage: "queued",
      progress: 0,
      message: "正在恢复上次 AI 总结",
      result: null,
      draft_result: null,
      streamed_text: "",
      markdown_url: null,
      error: null
    };
  }
  trackSummary(summaryId);
  refreshSummary(summaryId);
}

function trackSummary(summaryId) {
  if (typeof window === "undefined" || !summaryId || summaryDisconnectors.has(summaryId) || summaryPollers.has(summaryId)) return;
  const disconnect = connectSummaryEvents(
    summaryId,
    (snapshot) => {
      if (state.currentSummaryId !== summaryId) return;
      applySummarySnapshot(snapshot);
      if (snapshot.status === "completed" || snapshot.status === "failed") {
        stopSummaryTracking(summaryId);
      }
    },
    async (message) => {
      if (state.currentSummaryId !== summaryId) return;
      try {
        const snapshot = await getSummary(summaryId);
        if (state.currentSummaryId !== summaryId) return;
        applySummarySnapshot(snapshot);
        if (snapshot.status === "completed" || snapshot.status === "failed") {
          stopSummaryTracking(summaryId);
          return;
        }
      } catch {
        // Fall through to the connection message when the snapshot cannot confirm final state.
      }
      state.summaryError = localizeSummaryStatus(message);
    }
  );
  summaryDisconnectors.set(summaryId, disconnect);

  const poller = window.setInterval(() => refreshSummary(summaryId), 1000);
  summaryPollers.set(summaryId, poller);
}

async function refreshSummary(summaryId) {
  try {
    const snapshot = await getSummary(summaryId);
    if (state.currentSummaryId !== summaryId) return;
    applySummarySnapshot(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed") {
      stopSummaryTracking(summaryId);
    }
  } catch (error) {
    if (state.currentSummaryId === summaryId) state.summaryError = localizeSummaryStatus(error.message);
  }
}

function stopSummaryTracking(summaryId) {
  summaryDisconnectors.get(summaryId)?.();
  summaryDisconnectors.delete(summaryId);
  const poller = summaryPollers.get(summaryId);
  if (poller && typeof window !== "undefined") window.clearInterval(poller);
  summaryPollers.delete(summaryId);
}

function clearCurrentSummary() {
  const summaryId = state.currentSummaryId;
  if (summaryId) stopSummaryTracking(summaryId);
  state.currentSummaryId = null;
  state.summaryTask = null;
  state.summaryError = "";
}

function registerTask(taskId, formatId = state.selectedFormatId) {
  const task = {
    id: taskId,
    format_id: formatId,
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
  trackTask(taskId, task);
}

function resumeTask(taskId) {
  if (!taskId) return;
  let task = state.tasks.find((item) => item.id === taskId);
  if (!task) {
    task = {
      id: taskId,
      format_id: state.selectedFormatId,
      status: "queued",
      progress: 0,
      message: "正在恢复下载任务状态",
      speed: null,
      eta: null,
      download_url: null,
      error: null
    };
    state.tasks.unshift(task);
  }
  trackTask(taskId, task);
  refreshTask(taskId, task);
}

function trackTask(taskId, task) {
  if (typeof window === "undefined" || !taskId || disconnectors.has(taskId) || pollers.has(taskId)) return;
  const disconnect = connectTaskEvents(
    taskId,
    (snapshot) => {
      applyTaskSnapshot(taskId, snapshot);
      if (snapshot.status === "completed" || snapshot.status === "failed") {
        stopTaskTracking(taskId);
      }
    },
    async (message) => {
      try {
        const snapshot = await getTask(taskId);
        applyTaskSnapshot(taskId, snapshot);
        if (snapshot.status === "completed" || snapshot.status === "failed") {
          stopTaskTracking(taskId);
          return;
        }
      } catch {
        // Fall through to the connection message when the snapshot cannot confirm final state.
      }
      task.status = "failed";
      task.error = localizeStatus(message);
      state.error = task.error;
    }
  );
  disconnectors.set(taskId, disconnect);

  const poller = window.setInterval(() => refreshTask(taskId, task), 1000);
  pollers.set(taskId, poller);
}

async function refreshTask(taskId, task) {
  try {
    const snapshot = await getTask(taskId);
    applyTaskSnapshot(taskId, snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed") {
      stopTaskTracking(taskId);
    }
  } catch (error) {
    task.error = localizeStatus(error.message);
    state.error = task.error;
  }
}

function stopTaskTracking(taskId) {
  disconnectors.get(taskId)?.();
  disconnectors.delete(taskId);
  const poller = pollers.get(taskId);
  if (poller && typeof window !== "undefined") window.clearInterval(poller);
  pollers.delete(taskId);
}

function applySummarySnapshot(snapshot) {
  state.summaryTask = {
    ...(state.summaryTask || {}),
    ...snapshot,
    message: localizeSummaryStatus(snapshot.message || state.summaryTask?.message || "")
  };
  if (snapshot.status === "failed" && snapshot.error) state.summaryError = localizeSummaryStatus(snapshot.error);
}

function applyTaskSnapshot(taskId, snapshot) {
  const existingTask = state.tasks.find((item) => item.id === taskId);
  if (existingTask) {
    Object.assign(existingTask, snapshot);
    existingTask.message = localizeStatus(snapshot.message || existingTask.message);
    if (snapshot.status === "failed" && snapshot.error) state.error = localizeStatus(snapshot.error);
  }
}

function localizeSummaryStatus(message = "") {
  return message
    .replaceAll("Queued", "排队中")
    .replaceAll("Restored summary from cache", "已恢复上次 AI 总结")
    .replaceAll("Preparing transcript", "正在准备字幕文本")
    .replaceAll("Preparing subtitles", "正在准备字幕文本")
    .replaceAll("Extracting subtitles", "正在提取字幕")
    .replaceAll("Reusing previous transcript", "正在复用上次字幕文本")
    .replaceAll("Extracting audio for speech-to-text", "正在提取音频")
    .replaceAll("Preparing quick speech preview", "正在准备语音预览")
    .replaceAll("Transcribing quick speech preview", "正在快速转写开头片段")
    .replaceAll("Transcribing full audio", "正在继续完整语音转写")
    .replaceAll("Transcribing audio", "正在进行语音转写")
    .replaceAll("Draft summary ready", "快速版已生成，完整总结正在完善中")
    .replaceAll("Streaming structured summary", "AI 正在逐行生成总结")
    .replaceAll("Generating structured summary", "正在生成结构化总结")
    .replaceAll("Summary complete", "AI 总结完成")
    .replaceAll("Summary failed", "AI 总结失败")
    .replaceAll("Failed to fetch", "网络请求失败，请确认后端服务已启动");
}

function resumePersistedWorkspace() {
  if (state.currentTaskId) resumeTask(state.currentTaskId);
  if (state.currentSummaryId) resumeSummary(state.currentSummaryId);
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

function resetSummaryInteraction() {
  state.summaryView = "summary";
  state.summaryQuestion = "";
  state.summaryQuestionError = "";
  state.summaryQaHistory = [];
  state.askingSummaryQuestion = false;
}

async function submitSummaryQuestion() {
  const question = state.summaryQuestion.trim();
  if (!question || !state.currentSummaryId || state.askingSummaryQuestion) return;

  state.summaryQuestionError = "";
  state.askingSummaryQuestion = true;
  try {
    const { answer } = await askSummaryQuestion(state.currentSummaryId, {
      question,
      language: "zh-CN"
    });
    state.summaryQaHistory.unshift({ question, answer });
    state.summaryQuestion = "";
  } catch (error) {
    state.summaryQuestionError = localizeSummaryStatus(error.message);
  } finally {
    state.askingSummaryQuestion = false;
  }
}

function useSummaryQuestion(question) {
  state.summaryView = "qa";
  state.summaryQuestion = question;
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

onMounted(() => {
  syncCurrentPageFromHash();
  refreshMe({ silent: true });
  window.addEventListener("hashchange", syncCurrentPageFromHash);
  window.addEventListener("popstate", syncCurrentPageFromHash);
  resumePersistedWorkspace();
});

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("hashchange", syncCurrentPageFromHash);
    window.removeEventListener("popstate", syncCurrentPageFromHash);
  }
  disconnectors.forEach((disconnect) => disconnect());
  pollers.forEach((poller) => window.clearInterval(poller));
  summaryDisconnectors.forEach((disconnect) => disconnect());
  summaryPollers.forEach((poller) => window.clearInterval(poller));
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <a class="brand" href="#download" aria-label="万能视频下载器首页" :aria-current="currentPage === HOME_PAGE_ID && !state.activeAnchor ? 'page' : undefined" @click.prevent="navigateToPage(HOME_PAGE_ID)">
        <span class="brand-mark" aria-hidden="true"><FileVideo2 :size="21" /></span>
        <span class="brand-name">SaveAny</span>
        <span class="brand-pill">万能视频下载总结</span>
      </a>
      <nav class="nav-links" aria-label="主导航">
        <a
          v-for="link in pageLinks"
          :key="link.id"
          :class="{ 'nav-cta': link.accent }"
          :href="`#${link.id}`"
          :aria-current="isNavLinkCurrent(link) ? 'page' : undefined"
          @click.prevent="navigateToNavLink(link)"
        >
          <Star v-if="link.accent" :size="18" aria-hidden="true" />
          <span>{{ link.label }}</span>
        </a>
      </nav>
      <div class="account-menu">
        <button v-if="!auth.user" class="secondary-button account-button" type="button" @click="openAuth('login')">
          <UserRound :size="18" aria-hidden="true" />
          <span>登录 / 注册</span>
        </button>
        <div v-else class="account-chip">
          <div>
            <span>{{ auth.user.email }}</span>
            <strong>{{ authMembershipLabel }}</strong>
          </div>
          <small>{{ authUsageText }}</small>
          <button type="button" aria-label="退出登录" @click="logout">
            <LogOut :size="17" aria-hidden="true" />
            <span>退出登录</span>
          </button>
        </div>
      </div>
    </header>

    <section id="download" class="hero" v-show="currentPage === 'download'" aria-labelledby="page-title">
      <div class="hero-copy-block">
        <p class="kicker"><span aria-hidden="true"></span>支持 1800+ 平台，解析后自动总结</p>
        <h1 id="page-title" aria-label="复制链接，一键保存高清视频并生成视频学习笔记">
          <span class="title-main">万能视频下载总结器，</span><span>一键保存并总结</span>
        </h1>
        <p class="hero-copy">粘贴视频链接，自动解析标题、封面、清晰度和音频。YouTube、Bilibili、抖音、TikTok... 下载、字幕、AI 总结和思维导图一次完成。</p>
      </div>

      <section id="download-console" class="console" aria-label="视频下载控制台">
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
          </div>
        </form>

        <section v-if="state.error" class="message error" role="alert">
          <XCircle :size="18" aria-hidden="true" />
          <span>{{ state.error }}</span>
        </section>

        <section v-if="hasResult" class="analysis-workbench" aria-label="视频信息和 AI 总结">
          <aside class="video-column" aria-label="视频信息与下载">
            <section class="result-card" aria-label="视频信息">
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
                  <button class="secondary-button summary-retry-button" type="button" :disabled="state.summarizing || isSummaryRunning" @click="retrySummary">
                    <Loader2 v-if="state.summarizing || isSummaryRunning" :size="20" class="animate-spin" aria-hidden="true" />
                    <Sparkles v-else :size="20" aria-hidden="true" />
                    <span>{{ state.summarizing || isSummaryRunning ? "总结中" : summaryActionLabel }}</span>
                  </button>
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
          </aside>

          <section class="summary-column" aria-label="AI 总结工作区">
            <section v-if="state.summaryError" class="summary-fallback-card summary-error-card" role="alert">
              <XCircle :size="22" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">AI 总结失败</p>
                <h3>可以继续下载，也可以重试总结</h3>
                <p>{{ state.summaryError }}</p>
              </div>
              <button class="secondary-button" type="button" :disabled="state.summarizing || isSummaryRunning" @click="retrySummary">
                <Sparkles :size="18" aria-hidden="true" />
                <span>重试总结</span>
              </button>
              <button v-if="!auth.user" class="secondary-button" type="button" @click="openAuth('login')">
                <UserRound :size="18" aria-hidden="true" />
                <span>登录 / 注册</span>
              </button>
              <button v-else-if="!auth.membership?.active && hasSummaryQuotaError" class="primary-button" type="button" @click="startCheckout">
                <Star :size="18" aria-hidden="true" />
                <span>开通专业版 ¥29/月</span>
              </button>
            </section>

            <section v-else-if="state.summarizing && !state.summaryTask" class="summary-fallback-card summary-loading-card" aria-live="polite">
              <Loader2 :size="24" class="animate-spin" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">AI 总结工作区</p>
                <h3>正在自动总结视频内容</h3>
                <p>解析完成后已自动开始创建总结任务，右侧会持续显示字幕提取、结构化总结和导出入口。</p>
              </div>
            </section>

            <SummaryPanel
              v-else-if="state.summaryTask"
              :summary-task="state.summaryTask"
              :summary-result="summaryResult"
              :is-draft-result="isSummaryDraft"
              :summary-status-text="summaryStatusText"
              :is-summary-running="isSummaryRunning"
              :can-export-markdown="canExportMarkdown"
              :summary-qa-history="state.summaryQaHistory"
              :summary-question="state.summaryQuestion"
              :summary-question-error="state.summaryQuestionError"
              :asking-summary-question="state.askingSummaryQuestion"
              :summary-view="state.summaryView"
              @update:view="state.summaryView = $event"
              @update:question="state.summaryQuestion = $event"
              @submit-question="submitSummaryQuestion"
              @use-question="useSummaryQuestion"
            />

            <section v-else class="summary-fallback-card">
              <Sparkles :size="24" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">AI 总结工作区</p>
                <h3>解析后会自动总结</h3>
                <p>视频信息保留在左侧，学习摘要、字幕、思维导图和问答会集中显示在这里。</p>
              </div>
            </section>
          </section>
        </section>

        <ol v-if="!hasResult" class="workflow" aria-label="下载流程">
          <li><span>1</span>粘贴链接</li>
          <li><span>2</span>解析并自动总结</li>
          <li><span>3</span>选择清晰度下载</li>
        </ol>
      </section>

      <div class="trust-strip" aria-label="产品亮点">
        <span><ShieldCheck :size="18" />无广告跳转</span>
        <span><BrainCircuit :size="18" />AI 自动总结</span>
        <span><Sparkles :size="18" />高清画质</span>
      </div>

      <section id="home-highlights" class="home-highlights" aria-label="核心能力">
        <div class="home-section-header">
          <p class="section-eyebrow">核心能力</p>
        </div>
        <div class="highlights-grid">
          <article
            v-for="highlight in homeHighlights"
            :key="highlight.title"
            class="highlight-card"
            :class="{ featured: highlight.featured }"
            :data-tone="highlight.tone"
          >
            <div class="highlight-card-top">
              <span class="highlight-icon" aria-hidden="true">
                <component :is="highlight.icon" :size="24" stroke-width="2.2" />
              </span>
              <span class="highlight-metric">{{ highlight.metric }}</span>
            </div>
            <h3>{{ highlight.title }}</h3>
            <p>{{ highlight.description }}</p>
          </article>
        </div>
      </section>

      <section id="home-faq" class="home-faq-summary" aria-label="常见问题与边界">
        <div class="home-section-header">
          <p class="section-eyebrow">常见问题与边界</p>
        </div>
        <div class="home-faq-grid">
          <div class="compact-faq-list">
            <article v-for="faq in compactFaqs" :key="faq.question" class="compact-faq-card">
              <h3>{{ faq.question }}</h3>
              <p>{{ faq.answer }}</p>
            </article>
          </div>
          <aside class="compliance-summary" aria-labelledby="compliance-summary-title">
            <ShieldCheck :size="24" aria-hidden="true" />
            <div>
              <h3 id="compliance-summary-title">公开视频和版权边界</h3>
              <ul>
                <li v-for="point in compactCompliancePoints" :key="point">{{ point }}</li>
              </ul>
            </div>
          </aside>
        </div>
      </section>
    </section>

    <section id="pricing" class="section pricing-section page-view" v-if="currentPage === 'pricing'">
      <p class="kicker"><span aria-hidden="true"></span>轻量开始，需要时再升级</p>
      <h2>按使用频率选择套餐，下载、字幕和 AI 总结一起规划</h2>
      <p class="section-copy">套餐方案围绕公开视频处理量、AI 总结额度和团队协作设计。个人可以从免费版开始，高频学习和内容整理再升级。</p>

      <div class="pricing-grid" aria-label="套餐方案">
        <article v-for="plan in pricingPlans" :key="plan.id" class="pricing-card" :class="{ featured: plan.featured }" :data-plan="plan.id">
          <div class="pricing-card-head">
            <span class="plan-badge">{{ plan.badge }}</span>
            <h3>{{ plan.name }}</h3>
            <p>{{ plan.description }}</p>
          </div>
          <div class="plan-price">
            <strong>{{ plan.price }}</strong>
            <span>{{ plan.cycle }}</span>
          </div>
          <ul class="plan-feature-list">
            <li v-for="feature in plan.features" :key="feature">
              <CheckCircle2 :size="18" aria-hidden="true" />
              <span>{{ feature }}</span>
            </li>
          </ul>
          <button
            v-if="plan.id === 'pro' && !auth.membership?.active"
            class="primary-button"
            type="button"
            :disabled="state.billingBusy"
            @click="startCheckout"
          >
            <Loader2 v-if="state.billingBusy" :size="20" class="animate-spin" aria-hidden="true" />
            <Star v-if="plan.featured" :size="20" aria-hidden="true" />
            <span>开通专业版 ¥29/月</span>
          </button>
          <button
            v-else-if="plan.id === 'pro'"
            class="secondary-button"
            type="button"
            :disabled="state.billingBusy"
            @click="openBillingPortal"
          >
            <CreditCard :size="20" aria-hidden="true" />
            <span>管理订阅</span>
          </button>
          <a v-else :class="plan.featured ? 'primary-button' : 'secondary-button'" :href="`#${plan.target}`" @click.prevent="navigateToPage(plan.target)">
            <Star v-if="plan.featured" :size="20" aria-hidden="true" />
            <span>{{ plan.cta }}</span>
          </a>
        </article>
      </div>

      <p v-if="checkoutNotice" class="message pricing-message" aria-live="polite">
        <CreditCard :size="18" aria-hidden="true" />
        <span>{{ checkoutNotice }}</span>
      </p>
      <p v-if="state.billingMessage" class="message pricing-message" aria-live="polite">
        <span>{{ state.billingMessage }}</span>
      </p>

      <div class="pricing-assurance" aria-label="套餐边界说明">
        <span v-for="item in pricingGuarantees" :key="item"><ShieldCheck :size="18" aria-hidden="true" />{{ item }}</span>
      </div>

      <div v-if="showMockBilling" class="mock-billing-panel" aria-label="本地模拟支付">
        <p>本地 mock billing 可在无外网时验收会员状态。</p>
        <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="runMockBilling('activate')">模拟开通</button>
        <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="runMockBilling('cancel')">模拟取消</button>
        <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="runMockBilling('expire')">模拟过期</button>
        <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="runMockBilling('payment-failed')">模拟付款失败</button>
      </div>
    </section>

    <section v-if="authForm.open" class="auth-modal" role="dialog" aria-modal="true" aria-label="账号登录">
      <form class="auth-panel" @submit.prevent="submitAuth">
        <div class="auth-panel-head">
          <KeyRound :size="22" aria-hidden="true" />
          <h2>{{ authTitle }}</h2>
        </div>
        <label v-if="authForm.mode !== 'reset-confirm'">
          <span>邮箱</span>
          <input v-model="authForm.email" type="email" autocomplete="email" required />
        </label>
        <label v-if="authForm.mode === 'reset-confirm'">
          <span>重置 token</span>
          <input v-model="authForm.token" type="text" autocomplete="one-time-code" required />
        </label>
        <label v-if="authForm.mode !== 'reset-request'">
          <span>密码</span>
          <input v-model="authForm.password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="authForm.error" class="message error">{{ authForm.error }}</p>
        <p v-if="authForm.notice" class="message">{{ authForm.notice }}</p>
        <button class="primary-button" type="submit" :disabled="authForm.busy">
          <Loader2 v-if="authForm.busy" :size="20" class="animate-spin" aria-hidden="true" />
          <span>{{ authSubmitLabel }}</span>
        </button>
        <button
          v-if="authForm.mode === 'login'"
          class="secondary-button"
          type="button"
          @click="authForm.mode = 'register'"
        >
          <span>没有账号，去注册</span>
        </button>
        <button
          v-if="authForm.mode === 'register'"
          class="secondary-button"
          type="button"
          @click="authForm.mode = 'login'"
        >
          <span>已有账号，去登录</span>
        </button>
        <button class="secondary-button" type="button" @click="openAuth('reset-request')">
          <span>忘记密码</span>
        </button>
        <button class="secondary-button" type="button" @click="closeAuth">
          <span>关闭</span>
        </button>
      </form>
    </section>
  </main>
</template>
