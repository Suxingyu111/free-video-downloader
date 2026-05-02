import assert from "node:assert/strict";
import test from "node:test";

import {
  authInitialState,
  clearAuthState,
  membershipLabel,
  membershipStatusText,
  quotaMeterText,
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

test("membershipStatusText explains pro edge states", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "past-due@example.com" },
    membership: { active: false, plan: "pro", status: "past_due" },
    usage: { daily_free_limit: 3, used_today: 3, remaining_today: 0 }
  });

  assert.equal(membershipStatusText(state), "付款失败，请更新支付方式");
  assert.equal(membershipLabel(state), "专业版付款失败");
  assert.equal(remainingSummaryText(state), "付款失败后 AI 总结额度已暂停");
});

test("quotaMeterText renders plan and pack remaining values", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: {
      daily_free_limit: 3,
      used_today: 1,
      remaining_today: 2,
      membership_active: false,
      meters: {
        summary: { limit: 3, used: 1, remaining: 2, plan_remaining: 2, pack_remaining: 0 },
        transcription_minutes: { limit: 30, used: 5, remaining: 25, plan_remaining: 25, pack_remaining: 0 }
      }
    }
  });

  assert.equal(quotaMeterText(state, "summary"), "AI 总结还剩 2 次");
  assert.equal(quotaMeterText(state, "transcription_minutes"), "语音转写还剩 25 分钟");
});
