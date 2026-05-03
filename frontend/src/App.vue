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
  confirmBillingCheckout,
  confirmPasswordReset,
  connectSummaryEvents,
  connectTaskEvents,
  createBillingCheckout,
  createBillingPortal,
  createDownloadTask,
  createSummaryTask,
  getBillingStatus,
  getEntitlementStatus,
  getMe,
  getSummary,
  getTask,
  loginAccount,
  logoutAccount,
  registerAccount,
  requestPasswordReset
} from "./services/api";
import {
  applyUsageState,
  authInitialState,
  clearAuthState,
  membershipLabel,
  membershipStatusText,
  quotaMeterRatio,
  quotaMeterText,
  remainingSummaryText,
  updateAuthState
} from "./services/authSession";
import { BEST_QUALITY_FORMAT, RELIABLE_MP4_FORMAT, resolveDownloadFormat } from "./services/formats";
import { applyWorkspaceSnapshot, loadWorkspaceSnapshot, pickWorkspaceSnapshot, saveWorkspaceSnapshot } from "./services/workspacePersistence";
import { seoCompliancePoints, seoFaqs } from "./seo/pages";

const SummaryPanel = defineAsyncComponent(() => import("./components/summary/SummaryPanel.vue"));

const HOME_PAGE_ID = "download";
const PRICING_PAGE_ID = "pricing";
const HOME_DOWNLOAD_ANCHOR_ID = "download-console";
const FREE_QUOTA_EXHAUSTED_MESSAGE = "今日免费 AI 总结额度已用完，请开通 Pro 个人版或购买按量包继续使用。";
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
    badge: "免费开始",
    name: "免费版",
    price: "¥0",
    cycle: "登录后额度更多",
    description: "适合偶尔保存公开视频、试用 AI 总结，把几个视频整理成可复习笔记。",
    features: ["每天 30 次视频解析", "每天 10 次视频下载", "每天 3 次 AI 总结", "每月 30 分钟语音转写试用", "每月 10 次 AI 问答", "单视频总结 30 分钟以内"],
    cta: "开始免费使用",
    target: "download"
  },
  {
    id: "pro",
    badge: "推荐",
    name: "Pro 个人版",
    price: "¥19",
    cycle: "/月",
    description: "适合高频学习、课程整理、播客复习和创作者素材笔记。",
    features: ["每月 120 次 AI 总结", "每月 600 分钟语音转写", "每月 200 次 AI 问答", "单视频总结 120 分钟以内", "单视频下载 180 分钟以内"],
    cta: "开通 Pro",
    target: "download",
    featured: true
  }
];
const creditPacks = [
  { id: "summary_small", group: "AI 总结次数包", name: "总结小包", price: "¥6", amount: "20 次 AI 总结", validity: "90 天有效" },
  { id: "summary_large", group: "AI 总结次数包", name: "总结加量包", price: "¥19", amount: "100 次 AI 总结", validity: "180 天有效" },
  { id: "transcription_small", group: "语音转写分钟包", name: "转写小包", price: "¥8", amount: "120 分钟语音转写", validity: "90 天有效" },
  { id: "transcription_large", group: "语音转写分钟包", name: "转写大包", price: "¥29", amount: "600 分钟语音转写", validity: "180 天有效" }
];
const pricingGuarantees = ["只处理用户有权访问的公开视频", "不托管登录态或付费绕过能力", "会员状态以服务端和 Stripe webhook 为准"];
const compactFaqs = seoFaqs.slice(0, 3);
const compactCompliancePoints = seoCompliancePoints.slice(0, 3);
const initialWorkspaceSnapshot = loadWorkspaceSnapshot();

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
  summaryGate: "",
  tasks: [],
  checkoutStatus: "",
  checkoutPurchaseType: "",
  checkoutConfirming: false,
  checkoutConfirmedSessionId: "",
  billingBusy: false,
  billingMessage: "",
  accountMenuOpen: false,
  pendingWorkspaceSnapshot: initialWorkspaceSnapshot,
  workspaceRestoreVisible: hasPersistedWorkspace(initialWorkspaceSnapshot)
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

if (typeof window !== "undefined") {
  if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  state.currentPage = normalizePageHash(window.location.hash);
  state.activeAnchor = state.currentPage === HOME_PAGE_ID ? normalizeHomeAnchorHash(window.location.hash) : "";
  state.checkoutStatus = hashParams(window.location.hash).get("checkout") || "";
  state.checkoutPurchaseType = hashParams(window.location.hash).get("purchase_type") || "";
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
let workspaceRestoreTimer = null;
let accountMenuCloseTimer = null;

const currentPage = computed(() => state.currentPage);
const authMembershipLabel = computed(() => membershipLabel(auth).replace("专业版", "Pro 个人版"));
const authUsageText = computed(() => remainingSummaryText(auth).replace("专业版", "Pro 个人版"));
const summaryQuotaText = computed(() => quotaMeterText(auth, "summary") || authUsageText.value);
const transcriptionQuotaText = computed(() => quotaMeterText(auth, "transcription_minutes"));
const questionQuotaText = computed(() => quotaMeterText(auth, "question"));
const summaryQuotaRatio = computed(() => quotaMeterRatio(auth, "summary"));
const transcriptionQuotaRatio = computed(() => quotaMeterRatio(auth, "transcription_minutes"));
const questionQuotaRatio = computed(() => quotaMeterRatio(auth, "question"));
const questionQuotaRemaining = computed(() => {
  const meter = auth.usage?.meters?.question;
  if (!meter) return null;
  return Math.max(Number(meter.remaining ?? 0), 0);
});
const questionQuotaExhausted = computed(() => questionQuotaRemaining.value === 0);
const billingStateText = computed(() => membershipStatusText(auth).replace("专业版", "Pro 个人版"));
const accountAvatarLabel = computed(() => {
  const emailPrefix = (auth.user?.email || "用户").split("@")[0].trim();
  return (emailPrefix || "用户").slice(0, 2).toUpperCase();
});
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
  if (state.checkoutStatus === "success" && state.checkoutPurchaseType === "credit_pack") return "按量包支付已返回，额度会自动同步。";
  if (state.checkoutStatus === "cancel" && state.checkoutPurchaseType === "credit_pack") return "已取消按量包支付，可以稍后重新购买。";
  if (state.checkoutStatus === "success" && state.checkoutConfirming) return "正在确认支付，请稍等。";
  if (state.checkoutStatus === "success" && auth.membership?.active) return "Pro 个人版已开通。";
  if (state.checkoutStatus === "success") return "正在确认会员状态，请稍等几秒。";
  if (state.checkoutStatus === "cancel") return "已取消支付，可以稍后继续开通 Pro 个人版。";
  return "";
});
const proPlanButtonLabel = computed(() => {
  if (auth.membership?.active || auth.membership?.status === "past_due") return "管理订阅";
  if (auth.membership?.plan === "pro") return "重新选择 Pro ¥19/月";
  return "开通 Pro ¥19/月";
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
const workspaceRestoredTitle = computed(() => {
  const snapshot = state.pendingWorkspaceSnapshot;
  if (snapshot?.result?.title) return snapshot.result.title;
  if (snapshot?.analyzedUrl) return snapshot.analyzedUrl;
  if (snapshot?.url) return snapshot.url;
  return "上次解析的视频工作区";
});
const workspaceRestoredMeta = computed(() => {
  const snapshot = state.pendingWorkspaceSnapshot;
  if (snapshot?.currentSummaryId && snapshot?.currentTaskId) return "包含下载任务与 AI 总结记录";
  if (snapshot?.currentSummaryId || snapshot?.summaryTask) return "包含 AI 总结记录";
  if (snapshot?.currentTaskId || snapshot?.tasks?.length) return "包含下载任务记录";
  return "已保留视频链接和解析结果";
});
const showWorkspaceRestore = computed(() => state.workspaceRestoreVisible && hasPersistedWorkspace(state.pendingWorkspaceSnapshot));
const billingPanelVisible = computed(() => Boolean(auth.user || checkoutNotice.value || state.billingMessage));

function scrollPageToTop(behavior = "auto") {
  if (typeof window === "undefined") return;
  const scroll = () => window.scrollTo({ top: 0, behavior });
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(scroll);
  } else {
    scroll();
  }
}

function resetPageScrollOnRefresh() {
  if (typeof window === "undefined") return;
  const target = hashTarget(window.location.hash);
  if (target && target !== HOME_PAGE_ID) return;
  scrollPageToTop("auto");
  const scroll = () => scrollPageToTop("auto");
  if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(scroll);
  window.setTimeout(scroll, 0);
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

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function syncCurrentPageFromHash() {
  if (typeof window === "undefined") return;
  const nextPage = normalizePageHash(window.location.hash);
  const nextAnchor = nextPage === HOME_PAGE_ID ? normalizeHomeAnchorHash(window.location.hash) : "";
  const params = hashParams(window.location.hash);
  state.currentPage = nextPage;
  state.activeAnchor = nextAnchor;
  state.checkoutStatus = params.get("checkout") || "";
  state.checkoutPurchaseType = params.get("purchase_type") || "";
  if (state.checkoutStatus === "success") {
    if (state.checkoutPurchaseType === "credit_pack") {
      await handleCreditPackCheckoutReturn();
    } else {
      await refreshMe({ silent: true });
      await confirmCheckoutReturn();
    }
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
  state.accountMenuOpen = false;
  if (link.type === "page") {
    navigateToPage(link.id);
  } else {
    navigateToHomeAnchor(link.id);
  }
}

async function navigateToPage(pageId) {
  state.accountMenuOpen = false;
  const nextPage = normalizePageHash(`#${pageId}`);
  state.currentPage = nextPage;
  state.activeAnchor = "";
  state.checkoutStatus = "";
  state.checkoutPurchaseType = "";
  if (typeof window === "undefined") return;

  const nextHash = `#${nextPage}`;
  updateHash(nextHash);
  await nextTick();
  scrollPageToTop("smooth");
}

function toggleAccountMenu() {
  clearAccountMenuCloseTimer();
  state.accountMenuOpen = !state.accountMenuOpen;
}

function openAccountMenu() {
  clearAccountMenuCloseTimer();
  state.accountMenuOpen = true;
}

function closeAccountMenu() {
  clearAccountMenuCloseTimer();
  state.accountMenuOpen = false;
}

function scheduleCloseAccountMenu() {
  clearAccountMenuCloseTimer();
  if (typeof window === "undefined") {
    closeAccountMenu();
    return;
  }
  accountMenuCloseTimer = window.setTimeout(() => {
    state.accountMenuOpen = false;
    accountMenuCloseTimer = null;
  }, 180);
}

function clearAccountMenuCloseTimer() {
  if (typeof window === "undefined" || !accountMenuCloseTimer) return;
  window.clearTimeout(accountMenuCloseTimer);
  accountMenuCloseTimer = null;
}

function openAccountCenter() {
  state.accountMenuOpen = false;
  navigateToPage(PRICING_PAGE_ID);
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
    try {
      const entitlements = await getEntitlementStatus();
      applyUsageState(auth, {
        meters: entitlements.meters || {},
        credit_packs: entitlements.credit_packs || {}
      });
    } catch {
      // Keep legacy /api/me usage when entitlement status is unavailable.
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
    state.billingMessage = "";
    if (state.checkoutStatus === "success") {
      if (state.checkoutPurchaseType === "credit_pack") {
        await handleCreditPackCheckoutReturn({ force: true });
      } else {
        await confirmCheckoutReturn({ force: true });
      }
    }
    authForm.open = false;
    authForm.password = "";
    if (state.summaryGate === "login" && state.result) {
      state.summaryGate = "";
      await startSummaryForResult(state.result, { mode: "auto" });
    }
  } catch (error) {
    authForm.error = error.message;
  } finally {
    authForm.busy = false;
  }
}

async function logout() {
  state.accountMenuOpen = false;
  try {
    await logoutAccount();
  } catch (error) {
    console.warn("Logout request failed", error);
  } finally {
    state.billingMessage = "";
    state.checkoutStatus = "";
    state.checkoutPurchaseType = "";
    state.checkoutConfirming = false;
    state.checkoutConfirmedSessionId = "";
    if (typeof window !== "undefined" && hashParams(window.location.hash).get("checkout")) updateHash("#pricing");
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
    const returnOrigin = typeof window !== "undefined" ? window.location.origin : undefined;
    const result = await createBillingCheckout(returnOrigin ? { return_url: returnOrigin } : undefined);
    if (result.url && typeof window !== "undefined") window.location.href = result.url;
  } catch (error) {
    state.billingMessage = localizeStatus(error.message);
  } finally {
    state.billingBusy = false;
  }
}

async function startCreditPackCheckout(packId) {
  if (!auth.user) {
    openAuth("login");
    return;
  }
  state.billingBusy = true;
  state.billingMessage = "";
  try {
    const returnOrigin = typeof window !== "undefined" ? window.location.origin : undefined;
    const result = await createBillingCheckout({
      return_url: returnOrigin,
      purchase_type: "credit_pack",
      pack_id: packId
    });
    if (result.credit_pack) {
      state.billingMessage = "按量包已加入账号。";
      await refreshMe({ silent: true });
      return;
    }
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

function isProPlanRecord() {
  return auth.membership?.plan === "pro";
}

function shouldManageProPlan() {
  return Boolean(auth.membership?.active || auth.membership?.status === "past_due");
}

function pricingPlanStateLabel(plan) {
  if (!auth.user) return "";
  if (plan.id === "free" && !auth.membership?.active && !isProPlanRecord()) return "当前套餐";
  if (plan.id !== "pro" || !isProPlanRecord()) return "";
  if (auth.membership?.active) return "当前已开通";
  if (auth.membership?.status === "past_due") return "付款失败";
  return "已过期";
}

function pricingPlanStatusCopy(plan) {
  if (!auth.user) {
    return plan.id === "pro" ? "登录后选择套餐，确认后再进入 Stripe 支付页面。" : "";
  }
  if (plan.id === "free") {
    if (!auth.membership?.active && !isProPlanRecord()) return `当前套餐，${authUsageText.value}`;
    return "下载功能继续免费，可随时保留本地工作区。";
  }
  if (plan.id !== "pro") return "";
  if (auth.membership?.active && auth.membership?.cancel_at_period_end) return "已取消续费，本周期内仍可使用";
  if (auth.membership?.active) return "当前已开通";
  if (auth.membership?.status === "past_due") return "付款失败，请更新支付方式";
  if (isProPlanRecord()) return "Pro 个人版已过期，可重新开通恢复高频 AI 总结。";
  return "选择这个套餐后再进入支付页面，支付成功会自动回到这里确认状态。";
}

async function goToPricingForUpgrade() {
  state.billingMessage = "请选择 Pro 个人版套餐，确认后再进入支付页面。";
  await navigateToPage(PRICING_PAGE_ID);
}

async function handleProPlanAction() {
  if (shouldManageProPlan()) {
    await openBillingPortal();
    return;
  }
  await startCheckout();
}

async function confirmCheckoutReturn({ force = false } = {}) {
  if (typeof window === "undefined") return;
  const params = hashParams(window.location.hash);
  state.checkoutPurchaseType = params.get("purchase_type") || state.checkoutPurchaseType;
  if (state.checkoutPurchaseType === "credit_pack") return;
  const sessionId = params.get("session_id") || "";
  if (state.checkoutStatus !== "success" || !sessionId) return;
  if (!force && state.checkoutConfirmedSessionId === sessionId) return;
  if (!auth.user) {
    await refreshMe({ silent: true });
  }
  if (!auth.user) {
    state.billingMessage = "登录后继续确认支付。";
    openAuth("login");
    return;
  }

  state.checkoutConfirming = true;
  state.billingBusy = true;
  state.billingMessage = "正在确认支付，请稍等。";
  const retryDelays = [0, 1200, 1800, 2400];
  try {
    for (let attempt = 0; attempt < retryDelays.length; attempt += 1) {
      if (retryDelays[attempt]) await wait(retryDelays[attempt]);
      try {
        const result = await confirmBillingCheckout(sessionId);
        if (result.membership) auth.membership = result.membership;
        auth.billingMode = result.mode || auth.billingMode;
        state.checkoutConfirmedSessionId = sessionId;
        await refreshMe({ silent: true });
        state.billingMessage = "Pro 个人版已开通。";
        return;
      } catch (error) {
        if (error.status === 409 && attempt < retryDelays.length - 1) continue;
        if (error.status === 409) {
          state.billingMessage = "支付已返回，仍在等待 Stripe 确认，可稍后刷新。";
          await refreshMe({ silent: true });
          return;
        }
        state.billingMessage = localizeStatus(error.message);
        return;
      }
    }
  } finally {
    state.checkoutConfirming = false;
    state.billingBusy = false;
  }
}

async function handleCreditPackCheckoutReturn({ force = false } = {}) {
  if (typeof window === "undefined") return;
  const params = hashParams(window.location.hash);
  const sessionId = params.get("session_id") || "";
  if (!force && sessionId && state.checkoutConfirmedSessionId === sessionId) return;
  await refreshMe({ silent: true });
  if (sessionId) state.checkoutConfirmedSessionId = sessionId;
  state.checkoutConfirming = false;
  state.billingBusy = false;
  state.billingMessage = "按量包支付已返回，额度会自动同步。";
}

async function handleAnalyze() {
  if (showWorkspaceRestore.value) dismissWorkspaceRestore();
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
    state.summaryGate = "login";
    state.summaryError = "";
    return;
  }

  clearCurrentSummary();
  state.summaryGate = "";
  state.summaryError = "";
  resetSummaryInteraction();
  state.summarizing = true;
  try {
    const summary = await createSummaryTask({
      url: result.webpage_url || state.url.trim(),
      title: result.title,
      language: "zh-CN",
      force: true,
      analysis_token: result.analysis_token
    });
    if (summary.usage) applyUsageState(auth, summary.usage);
    refreshMe({ silent: true });
    const { summary_id: summaryId, cache_hit: cacheHit } = summary;
    registerSummary(summaryId, {
      message: cacheHit ? "Restored summary from cache" : mode === "auto" ? "正在自动总结视频内容" : "AI 总结任务已排队"
    });
  } catch (error) {
    const message = localizeSummaryStatus(error.message);
    if (error.message.includes("请先登录")) {
      state.summaryGate = "login";
      state.summaryError = "";
    } else if (message.includes(FREE_QUOTA_EXHAUSTED_MESSAGE.slice(0, 14))) {
      state.summaryGate = "quota";
      state.summaryError = message;
    } else {
      state.summaryError = message;
    }
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
      analysis_token: state.result.analysis_token,
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
  state.summaryGate = "";
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
  const { usage, ...taskSnapshot } = snapshot || {};
  state.summaryTask = {
    ...(state.summaryTask || {}),
    ...taskSnapshot,
    message: localizeSummaryStatus(taskSnapshot.message || state.summaryTask?.message || "")
  };
  if (usage) applyUsageState(auth, usage);
  if (taskSnapshot.status === "failed" && taskSnapshot.error) state.summaryError = localizeSummaryStatus(taskSnapshot.error);
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
    .replaceAll("今日免费 AI 总结额度已用完，请开通专业版继续使用。", FREE_QUOTA_EXHAUSTED_MESSAGE)
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

function hasPersistedWorkspace(snapshot) {
  return Boolean(snapshot?.url || snapshot?.result || snapshot?.currentTaskId || snapshot?.currentSummaryId || snapshot?.summaryTask);
}

function clearWorkspaceRestoreTimer() {
  if (typeof window === "undefined" || !workspaceRestoreTimer) return;
  window.clearTimeout(workspaceRestoreTimer);
  workspaceRestoreTimer = null;
}

function dismissWorkspaceRestore() {
  clearWorkspaceRestoreTimer();
  state.workspaceRestoreVisible = false;
  state.pendingWorkspaceSnapshot = null;
  saveWorkspaceSnapshot(pickWorkspaceSnapshot(state));
}

function startWorkspaceRestoreTimer() {
  if (typeof window === "undefined" || !showWorkspaceRestore.value || workspaceRestoreTimer) return;
  workspaceRestoreTimer = window.setTimeout(() => {
    dismissWorkspaceRestore();
  }, 10000);
}

async function restoreWorkspaceSnapshot() {
  const snapshot = state.pendingWorkspaceSnapshot;
  if (!hasPersistedWorkspace(snapshot)) {
    dismissWorkspaceRestore();
    return;
  }
  clearWorkspaceRestoreTimer();
  applyWorkspaceSnapshot(state, snapshot);
  state.pendingWorkspaceSnapshot = null;
  state.workspaceRestoreVisible = false;
  await nextTick();
  resumePersistedWorkspace();
  navigateToHomeAnchor(HOME_DOWNLOAD_ANCHOR_ID);
}

function localizeStatus(message = "") {
  if (message.includes("访客解析次数已用完")) return "今天的访客解析次数已用完，登录后可获得更多免费额度。";
  if (message.includes("访客下载次数已用完")) return "今天的访客下载次数已用完，登录后可获得更多免费额度。";
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
    const { answer, usage } = await askSummaryQuestion(state.currentSummaryId, {
      question,
      language: "zh-CN"
    });
    if (usage) applyUsageState(auth, usage);
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
  resetPageScrollOnRefresh();
  refreshMe({ silent: true });
  window.addEventListener("hashchange", syncCurrentPageFromHash);
  window.addEventListener("popstate", syncCurrentPageFromHash);
  startWorkspaceRestoreTimer();
});

onBeforeUnmount(() => {
  clearWorkspaceRestoreTimer();
  clearAccountMenuCloseTimer();
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
        <div
          v-else
          class="account-profile"
          :class="{ open: state.accountMenuOpen }"
          @mouseenter="openAccountMenu"
          @mouseleave="scheduleCloseAccountMenu"
          @keydown.escape="closeAccountMenu"
        >
          <button
            class="account-avatar-button"
            type="button"
            aria-haspopup="menu"
            aria-controls="account-dropdown"
            :aria-expanded="state.accountMenuOpen ? 'true' : 'false'"
            @click="toggleAccountMenu"
            @focus="openAccountMenu"
          >
            <span class="account-avatar" aria-hidden="true">{{ accountAvatarLabel }}</span>
            <span class="sr-only">打开账号菜单</span>
          </button>
          <section id="account-dropdown" class="account-dropdown" role="menu" aria-label="账号菜单">
            <div class="account-dropdown-profile">
              <span class="account-avatar account-avatar-large" aria-hidden="true">{{ accountAvatarLabel }}</span>
              <div>
                <strong>{{ auth.user.email }}</strong>
                <span>{{ authMembershipLabel }} · {{ summaryQuotaText }}</span>
              </div>
            </div>
            <div class="account-quota-list">
              <div class="account-quota-row">
                <span>{{ summaryQuotaText }}</span>
                <div class="account-quota-track"><span :style="{ width: `${summaryQuotaRatio}%` }"></span></div>
              </div>
              <div v-if="transcriptionQuotaText" class="account-quota-row">
                <span>{{ transcriptionQuotaText }}</span>
                <div class="account-quota-track"><span :style="{ width: `${transcriptionQuotaRatio}%` }"></span></div>
              </div>
              <div v-if="questionQuotaText" class="account-quota-row">
                <span>{{ questionQuotaText }}</span>
                <div class="account-quota-track"><span :style="{ width: `${questionQuotaRatio}%` }"></span></div>
              </div>
            </div>
            <button class="account-menu-row" role="menuitem" type="button" @click="openAccountCenter">
              <UserRound :size="20" aria-hidden="true" />
              <span>个人中心</span>
              <small>账号与套餐信息</small>
              <span class="account-row-arrow" aria-hidden="true">›</span>
            </button>
            <button class="account-menu-row account-logout-row" role="menuitem" type="button" @click="logout">
              <LogOut :size="20" aria-hidden="true" />
              <span>退出登录</span>
            </button>
          </section>
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

        <section
          v-if="showWorkspaceRestore"
          class="restore-toast"
          role="dialog"
          aria-modal="false"
          aria-labelledby="restore-toast-title"
          aria-live="polite"
        >
          <div class="restore-toast-copy">
            <span class="restore-status">发现上次解析结果</span>
            <strong id="restore-toast-title">{{ workspaceRestoredTitle }}</strong>
            <small>{{ workspaceRestoredMeta }}，10 秒后保持首页清空。</small>
          </div>
          <div class="restore-toast-actions">
            <button class="secondary-button" type="button" @click="restoreWorkspaceSnapshot">
              <CheckCircle2 :size="18" aria-hidden="true" />
              <span>恢复工作区</span>
            </button>
            <button class="secondary-button subtle-button" type="button" @click="dismissWorkspaceRestore">
              <XCircle :size="18" aria-hidden="true" />
              <span>保持清空</span>
            </button>
          </div>
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
            <section v-if="state.summaryGate === 'login'" class="summary-fallback-card summary-gate-card" aria-live="polite">
              <UserRound :size="24" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">AI 总结门禁</p>
                <h3>登录后继续自动总结</h3>
                <p>解析结果已保留。登录或注册后会继续生成摘要、字幕、思维导图和 AI 问答；你也可以先下载视频文件。</p>
                <p class="summary-gate-quota">{{ authUsageText }}</p>
              </div>
              <div class="summary-gate-actions">
                <button class="primary-button" type="button" @click="openAuth('login')">
                  <UserRound :size="18" aria-hidden="true" />
                  <span>登录 / 注册</span>
                </button>
                <button class="secondary-button" type="button" :disabled="state.downloading || isTaskRunning" @click="handleDownload">
                  <Download :size="18" aria-hidden="true" />
                  <span>先下载视频</span>
                </button>
              </div>
            </section>

            <section v-else-if="state.summaryGate === 'quota' || (state.summaryError && hasSummaryQuotaError)" class="summary-fallback-card summary-upgrade-card" role="alert">
              <Star :size="24" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">AI 总结额度</p>
                <h3>今日免费额度已用完</h3>
                <p>{{ state.summaryError || FREE_QUOTA_EXHAUSTED_MESSAGE }}</p>
              </div>
              <button class="primary-button" type="button" :disabled="state.billingBusy" @click="goToPricingForUpgrade">
                <Star :size="18" aria-hidden="true" />
                <span>查看套餐方案</span>
              </button>
            </section>

            <section v-else-if="state.summaryError" class="summary-fallback-card summary-error-card" role="alert">
              <XCircle :size="22" aria-hidden="true" />
              <div>
                <p class="summary-fallback-eyebrow">接口失败</p>
                <h3>总结没有完成，下载结果仍可用</h3>
                <p>{{ state.summaryError }}</p>
              </div>
              <button class="secondary-button" type="button" :disabled="state.summarizing || isSummaryRunning" @click="retrySummary">
                <Sparkles :size="18" aria-hidden="true" />
                <span>重试总结</span>
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
              :question-quota-text="questionQuotaText"
              :question-quota-exhausted="questionQuotaExhausted"
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

      <div class="pricing-grid" aria-label="套餐方案">
        <article v-for="plan in pricingPlans" :key="plan.id" class="pricing-card" :class="{ featured: plan.featured }" :data-plan="plan.id">
          <div class="pricing-card-head">
            <span class="plan-badge">{{ plan.badge }}</span>
            <span v-if="pricingPlanStateLabel(plan)" class="current-plan-badge">{{ pricingPlanStateLabel(plan) }}</span>
            <h3>{{ plan.name }}</h3>
            <p>{{ plan.description }}</p>
            <p v-if="pricingPlanStatusCopy(plan)" class="plan-status-copy">{{ pricingPlanStatusCopy(plan) }}</p>
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
            v-if="plan.id === 'pro'"
            :class="shouldManageProPlan() ? 'secondary-button' : 'primary-button'"
            type="button"
            :disabled="state.billingBusy"
            @click="handleProPlanAction"
          >
            <Loader2 v-if="state.billingBusy" :size="20" class="animate-spin" aria-hidden="true" />
            <CreditCard v-else-if="shouldManageProPlan()" :size="20" aria-hidden="true" />
            <Star v-else :size="20" aria-hidden="true" />
            <span>{{ proPlanButtonLabel }}</span>
          </button>
          <a v-else :class="plan.featured ? 'primary-button' : 'secondary-button'" :href="`#${plan.target}`" @click.prevent="navigateToPage(plan.target)">
            <Star v-if="plan.featured" :size="20" aria-hidden="true" />
            <span>{{ plan.cta }}</span>
          </a>
        </article>
      </div>

      <div class="pricing-assurance" aria-label="套餐边界说明">
        <span v-for="item in pricingGuarantees" :key="item"><ShieldCheck :size="18" aria-hidden="true" />{{ item }}</span>
      </div>

      <section class="credit-pack-section" aria-label="按量包">
        <div class="credit-pack-head">
          <p class="section-eyebrow">额度不够时再买</p>
          <h3>按量包不会强迫升级，更适合偶尔的长视频和课程整理高峰</h3>
        </div>
        <div class="credit-pack-grid">
          <article v-for="pack in creditPacks" :key="pack.id" class="credit-pack-card">
            <span class="plan-badge">{{ pack.group }}</span>
            <h4>{{ pack.name }}</h4>
            <strong>{{ pack.price }}</strong>
            <p>{{ pack.amount }}</p>
            <small>{{ pack.validity }}</small>
            <button class="secondary-button" type="button" :disabled="state.billingBusy" @click="startCreditPackCheckout(pack.id)">
              <CreditCard :size="18" aria-hidden="true" />
              <span>购买按量包</span>
            </button>
          </article>
        </div>
      </section>

      <section v-if="billingPanelVisible" class="billing-status-panel" aria-label="会员账单状态">
        <div class="billing-status-copy">
          <CreditCard :size="20" aria-hidden="true" />
          <div>
            <p class="billing-status-label">账单状态</p>
            <strong v-if="state.billingMessage">{{ state.billingMessage }}</strong>
            <strong v-else-if="checkoutNotice">{{ checkoutNotice }}</strong>
            <strong v-else>{{ billingStateText }}</strong>
            <span>
              {{ authMembershipLabel }} · {{ summaryQuotaText }}
              <template v-if="transcriptionQuotaText"> · {{ transcriptionQuotaText }}</template>
              <template v-if="questionQuotaText"> · {{ questionQuotaText }}</template>
            </span>
          </div>
        </div>
        <div class="account-quota-list billing-quota-list" aria-label="额度余量">
          <div class="account-quota-row">
            <span>{{ summaryQuotaText }}</span>
            <div class="account-quota-track"><span :style="{ width: `${summaryQuotaRatio}%` }"></span></div>
          </div>
          <div v-if="transcriptionQuotaText" class="account-quota-row">
            <span>{{ transcriptionQuotaText }}</span>
            <div class="account-quota-track"><span :style="{ width: `${transcriptionQuotaRatio}%` }"></span></div>
          </div>
          <div v-if="questionQuotaText" class="account-quota-row">
            <span>{{ questionQuotaText }}</span>
            <div class="account-quota-track"><span :style="{ width: `${questionQuotaRatio}%` }"></span></div>
          </div>
        </div>
      </section>
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
