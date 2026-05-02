export function authInitialState() {
  return {
    user: null,
    membership: { active: false, plan: "free", status: "anonymous" },
    usage: { daily_free_limit: 3, used_today: 0, remaining_today: 0, membership_active: false },
    billingMode: "",
    loading: false,
    error: ""
  };
}

export function updateAuthState(state, payload = {}) {
  state.user = payload.user || null;
  state.membership = payload.membership || { active: false, plan: "free", status: state.user ? "free" : "anonymous" };
  state.usage = payload.usage || {
    daily_free_limit: 3,
    used_today: 0,
    remaining_today: state.user ? 3 : 0,
    membership_active: Boolean(state.membership?.active)
  };
  if (payload.mode) state.billingMode = payload.mode;
  state.error = "";
}

export function clearAuthState(state) {
  state.user = null;
  state.membership = { active: false, plan: "free", status: "anonymous" };
  state.usage = { daily_free_limit: 3, used_today: 0, remaining_today: 0, membership_active: false };
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
