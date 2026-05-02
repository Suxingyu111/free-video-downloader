import assert from "node:assert/strict";
import test from "node:test";

import {
  authInitialState,
  clearAuthState,
  membershipLabel,
  membershipStatusText,
  quotaMeterRatio,
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
        transcription_minutes: { limit: 30, used: 5, remaining: 25, plan_remaining: 25, pack_remaining: 0 },
        analyze: { limit: 10, used: 3, remaining: 7, plan_remaining: 7, pack_remaining: 0 },
        download: { limit: 20, used: 4, remaining: 16, plan_remaining: 16, pack_remaining: 0 }
      }
    }
  });

  assert.equal(quotaMeterText(state, "summary"), "AI 总结还剩 2 次");
  assert.equal(quotaMeterText(state, "transcription_minutes"), "语音转写还剩 25 分钟");
  assert.equal(quotaMeterText(state, "analyze"), "解析还剩 7 次");
  assert.equal(quotaMeterText(state, "download"), "下载还剩 16 次");
});

test("quotaMeterRatio calculates remaining percentage with safe boundaries", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: {
      meters: {
        summary: { limit: 10, used: 3, remaining: 7 },
        transcription_minutes: { limit: 0, used: 0, remaining: 0 },
        analyze: { limit: 10, used: 12, remaining: 0 },
        download: { limit: 10, used: -2, remaining: 10 }
      }
    }
  });

  assert.equal(quotaMeterRatio(state, "summary"), 70);
  assert.equal(quotaMeterRatio(state, "missing"), 0);
  assert.equal(quotaMeterRatio(state, "transcription_minutes"), 0);
  assert.equal(quotaMeterRatio(state, "analyze"), 0);
  assert.equal(quotaMeterRatio(state, "download"), 100);
});

test("quotaMeterRatio coerces partial meter payloads safely", () => {
  const state = authInitialState();
  updateAuthState(state, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: {
      meters: {
        summary: { limit: 10, remaining: 10 },
        transcription_minutes: { limit: 10, used: "not-a-number", remaining: 10 },
        analyze: { limit: "10", used: Number.NaN, remaining: 10 },
        download: { limit: "0", used: 0, remaining: 0 },
        conversion: { limit: "10", used: "3", remaining: 7 }
      }
    }
  });

  assert.equal(quotaMeterRatio(state, "summary"), 100);
  assert.equal(quotaMeterRatio(state, "transcription_minutes"), 100);
  assert.equal(quotaMeterRatio(state, "analyze"), 100);
  assert.equal(quotaMeterRatio(state, "download"), 0);
  assert.equal(quotaMeterRatio(state, "conversion"), 70);
});

test("auth usage defaults include isolated meter and credit pack objects", () => {
  const first = authInitialState();
  const second = authInitialState();

  assert.deepEqual(first.usage.meters, {});
  assert.deepEqual(first.usage.credit_packs, {});
  assert.notEqual(first.usage.meters, second.usage.meters);
  assert.notEqual(first.usage.credit_packs, second.usage.credit_packs);

  const withoutUsage = authInitialState();
  updateAuthState(withoutUsage, {
    user: { email: "user@example.com" },
    membership: { active: false, plan: "free", status: "free" }
  });

  assert.deepEqual(withoutUsage.usage.meters, {});
  assert.deepEqual(withoutUsage.usage.credit_packs, {});
  assert.notEqual(withoutUsage.usage.meters, first.usage.meters);
  assert.notEqual(withoutUsage.usage.credit_packs, first.usage.credit_packs);

  const partialUsage = authInitialState();
  updateAuthState(partialUsage, {
    user: { email: "partial@example.com" },
    membership: { active: false, plan: "free", status: "free" },
    usage: { remaining_today: 1 }
  });

  assert.deepEqual(partialUsage.usage.meters, {});
  assert.deepEqual(partialUsage.usage.credit_packs, {});
  assert.equal(partialUsage.usage.remaining_today, 1);
  assert.notEqual(partialUsage.usage.meters, withoutUsage.usage.meters);
  assert.notEqual(partialUsage.usage.credit_packs, withoutUsage.usage.credit_packs);

  partialUsage.usage.meters.summary = { limit: 3, used: 1, remaining: 2 };
  partialUsage.usage.credit_packs.summary = { remaining: 5 };
  clearAuthState(partialUsage);

  assert.deepEqual(partialUsage.usage.meters, {});
  assert.deepEqual(partialUsage.usage.credit_packs, {});
  assert.notEqual(partialUsage.usage.meters, withoutUsage.usage.meters);
  assert.notEqual(partialUsage.usage.credit_packs, withoutUsage.usage.credit_packs);
});
