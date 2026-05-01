import assert from "node:assert/strict";
import test from "node:test";

import {
  authInitialState,
  clearAuthState,
  membershipLabel,
  remainingSummaryText,
  updateAuthState
} from "../src/services/authSession.js";

test("updateAuthState stores user membership and usage", () => {
  const state = authInitialState();

  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: { daily_free_limit: 3, used_today: 2, remaining_today: 1 }
  });

  assert.equal(state.user.email, "user@example.com");
  assert.equal(membershipLabel(state), "免费版");
  assert.equal(remainingSummaryText(state), "今日还可免费总结 1 次");
});

test("membership label describes active pro plan", () => {
  const state = authInitialState();

  updateAuthState(state, {
    user: { email: "pro@example.com" },
    membership: { active: true, plan: "pro", status: "active" },
    usage: { daily_free_limit: 3, used_today: 0, remaining_today: 3 }
  });

  assert.equal(membershipLabel(state), "专业版会员");
  assert.equal(remainingSummaryText(state), "专业版 AI 总结额度已解锁");
});

test("clearAuthState resets account state without losing billing mode", () => {
  const state = authInitialState();
  state.billingMode = "mock";

  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: true, plan: "pro", status: "active" },
    usage: { daily_free_limit: 3, used_today: 0, remaining_today: 3 }
  });
  clearAuthState(state);

  assert.equal(state.user, null);
  assert.equal(state.membership.status, "anonymous");
  assert.equal(state.billingMode, "mock");
  assert.equal(membershipLabel(state), "未登录");
  assert.equal(remainingSummaryText(state), "登录后每天可免费总结 3 次");
});
