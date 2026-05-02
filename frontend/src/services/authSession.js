const DEFAULT_USAGE = {
  daily_free_limit: 3,
  used_today: 0,
  remaining_today: 0,
  membership_active: false,
  meters: {},
  credit_packs: {}
};

export function authInitialState() {
  return {
    user: null,
    membership: { active: false, plan: "free", status: "anonymous" },
    usage: defaultUsage(),
    billingMode: "",
    loading: false,
    error: ""
  };
}

export function updateAuthState(state, payload = {}) {
  state.user = payload.user || null;
  state.membership = payload.membership || { active: false, plan: "free", status: state.user ? "free" : "anonymous" };
  state.usage = defaultUsage(payload.usage || {
    remaining_today: state.user ? DEFAULT_USAGE.daily_free_limit : 0,
    membership_active: Boolean(state.membership?.active)
  });
  if (payload.mode) state.billingMode = payload.mode;
  state.error = "";
}

export function clearAuthState(state) {
  state.user = null;
  state.membership = { active: false, plan: "free", status: "anonymous" };
  state.usage = defaultUsage();
  state.error = "";
}

export function membershipLabel(state) {
  if (state.membership?.active) return "专业版会员";
  if (state.membership?.status === "past_due") return "专业版付款失败";
  if (state.membership?.plan === "pro") return "专业版已过期";
  if (state.user) return "免费版";
  return "未登录";
}

export function membershipStatusText(state) {
  const membership = state.membership || {};
  if (!state.user) return "登录后查看套餐状态";
  if (membership.active && membership.cancel_at_period_end) return "已取消续费，本周期内仍可使用";
  if (membership.active) return "当前已开通";
  if (membership.status === "past_due") return "付款失败，请更新支付方式";
  if (membership.plan === "pro") return "专业版已过期";
  return "当前套餐";
}

export function remainingSummaryText(state) {
  if (state.membership?.active) return "专业版 AI 总结额度已解锁";
  if (state.membership?.status === "past_due") return "付款失败后 AI 总结额度已暂停";
  if (!state.user) return "登录后每天可免费总结 3 次";
  return `今日还可免费总结 ${Math.max(state.usage?.remaining_today || 0, 0)} 次`;
}

export function quotaMeterText(state, meter) {
  const value = state.usage?.meters?.[meter];
  if (!value) return "";
  const remaining = meterRemaining(value);
  if (meter === "summary") return `AI 总结还剩 ${remaining} 次`;
  if (meter === "transcription_minutes") return `语音转写还剩 ${remaining} 分钟`;
  if (meter === "analyze") return `解析还剩 ${remaining} 次`;
  if (meter === "download") return `下载还剩 ${remaining} 次`;
  return "";
}

export function quotaMeterRatio(state, meter) {
  const value = state.usage?.meters?.[meter];
  if (!value) return 0;
  const limit = safeNumber(value.limit);
  const used = safeNumber(value.used);
  const remaining = meterRemaining(value);
  const denominator = Math.max(limit, used + remaining);
  if (!Number.isFinite(denominator) || denominator <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((remaining / denominator) * 100)));
}

function defaultUsage(usage = {}) {
  return {
    ...DEFAULT_USAGE,
    ...usage,
    meters: { ...(usage.meters || {}) },
    credit_packs: { ...(usage.credit_packs || {}) }
  };
}

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function meterRemaining(value) {
  const rawRemaining = Number(value.remaining);
  const packRemaining = safeNumber(value.pack_remaining);
  if (Number.isFinite(rawRemaining)) {
    const remaining = Math.max(rawRemaining, 0);
    if (remaining <= 0 && packRemaining > 0) return packRemaining;
    return remaining;
  }
  const limit = safeNumber(value.limit);
  const used = safeNumber(value.used);
  return Math.max(limit - used + packRemaining, 0);
}
